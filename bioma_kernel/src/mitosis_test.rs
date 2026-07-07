//! Neuronal Mitosis — end-to-end functional + performance benchmark.
//!
//! Scenario: "Dynamic vulnerability sweep + auto-refactor" modelled as 5 heavy,
//! CPU-bound search meta-tasks (find the unique `x` whose expensive hash matches a
//! target — a deterministic, verifiable proof-of-work).  Two engines solve the
//! SAME problem:
//!
//!   * **Traditional** — one thread, tasks solved sequentially (LangGraph/DAG style).
//!   * **B.I.O.M.A.**   — the root agent reads task complexity, secretes a stress
//!     hormone on the bus; when the sensed stress crosses a threshold it triggers
//!     **mitosis**: it apoptoses the context (shrinking the snapshot the children
//!     inherit), then spawns specialist children across Tokio's blocking pool that
//!     search disjoint shards **in parallel**, converging in a fraction of the time.
//!
//! Both engines return the SAME correct answers (parallelism never corrupts the
//! result); the win is wall-clock speed + fewer context tokens per call.

use std::collections::HashMap;
use std::time::Instant;

use pyo3::prelude::*;

use crate::memory::CtxCore;
use crate::{splitmix64, BusCore};

const CORTISOL: u32 = 1 << 0; // stress signal
const KEEP: u32 = 1 << 0;     // relevance channel kept through apoptosis

/// Deliberately expensive hash — makes each probe real CPU work.
#[inline]
fn heavy_hash(x: u64, seed: u64, rounds: u32) -> u64 {
    let mut h = x ^ seed.wrapping_mul(0x9E37_79B9_7F4A_7C15);
    for _ in 0..rounds {
        h = splitmix64(h) ^ 0xD1B5_4A32_D192_ED03;
    }
    h
}

/// Scan `[lo, hi)` for the unique `x` with `heavy_hash(x) == target`.
fn solve_shard(seed: u64, target: u64, lo: u64, hi: u64, rounds: u32) -> Option<u64> {
    let mut x = lo;
    while x < hi {
        if heavy_hash(x, seed, rounds) == target {
            return Some(x);
        }
        x += 1;
    }
    None
}

struct Task {
    seed: u64,
    target: u64,
    keyspace: u64,
    answer: u64, // hidden ground truth (for correctness scoring)
}

/// End-to-end mitosis benchmark exposed to Python.
#[pyclass]
pub struct MitosisBenchmark {
    tasks: Vec<Task>,
    rounds: u32,
}

#[pymethods]
impl MitosisBenchmark {
    #[new]
    #[pyo3(signature = (n_tasks = 5, keyspace = 1_500_000, base_seed = 1337, answer_frac = 0.85, hash_rounds = 32))]
    fn new(n_tasks: usize, keyspace: u64, base_seed: u64, answer_frac: f64, hash_rounds: u32) -> Self {
        let ks = keyspace.max(64);
        let mut tasks = Vec::with_capacity(n_tasks);
        for i in 0..n_tasks {
            let seed = splitmix64(base_seed ^ (i as u64).wrapping_mul(0x1_0000_01B3));
            let jitter = splitmix64(seed) % (ks / 8).max(1);
            let answer = (((ks as f64) * answer_frac) as u64 + jitter).min(ks - 1);
            let target = heavy_hash(answer, seed, hash_rounds);
            tasks.push(Task { seed, target, keyspace: ks, answer });
        }
        Self { tasks, rounds: hash_rounds }
    }

    /// Ground-truth answers (for the caller to cross-check).
    fn known_answers(&self) -> Vec<u64> {
        self.tasks.iter().map(|t| t.answer).collect()
    }

    /// Motor A — traditional: sequential, single-thread, full context every call.
    fn run_traditional(&self, py: Python<'_>) -> HashMap<String, f64> {
        py.allow_threads(|| {
            let (_ctx, full) = self.build_ctx(); // no apoptosis → full window per call
            let t0 = Instant::now();
            let mut answers = Vec::with_capacity(self.tasks.len());
            for t in &self.tasks {
                answers.push(solve_shard(t.seed, t.target, 0, t.keyspace, self.rounds));
            }
            let us = t0.elapsed().as_micros() as f64;
            self.result(us, &answers, full, full, 0, 0.0, 1)
        })
    }

    /// Motor B — B.I.O.M.A.: hormonal-triggered mitosis, apoptosis, Tokio parallel.
    #[pyo3(signature = (shards = 4, stress_threshold = 0.5))]
    fn run_bioma(&self, py: Python<'_>, shards: u64, stress_threshold: f32) -> HashMap<String, f64> {
        let shards = shards.max(1);
        py.allow_threads(|| {
            // --- Perception: read task complexity → secrete stress on the bus --- #
            let bus = BusCore::new(8);
            let max_ks = self.tasks.iter().map(|t| t.keyspace).max().unwrap_or(1).max(1);
            for t in &self.tasks {
                bus.secrete(CORTISOL, t.keyspace as f32 / max_ks as f32);
            }
            let stress = bus.sense(CORTISOL);
            let trigger = stress >= stress_threshold;

            // --- Apoptosis BEFORE duplication: shrink the inherited snapshot --- #
            let (ctx, full) = self.build_ctx();
            for _ in 0..3 {
                ctx.decay(0.5, KEEP, 0.4);
            }
            let lean = ctx.active_tokens();

            let cores = std::thread::available_parallelism().map(|c| c.get()).unwrap_or(4);
            let mut mitosis_events: u64 = 0;
            let mut answers = vec![None; self.tasks.len()];

            let t0 = Instant::now();
            if trigger {
                // --- Mitosis: one specialist child per (task, shard) in parallel --- #
                let rt = tokio::runtime::Builder::new_multi_thread()
                    .worker_threads(2)
                    .max_blocking_threads(cores)
                    .build()
                    .expect("tokio runtime");
                rt.block_on(async {
                    let mut handles = Vec::new();
                    for (ti, t) in self.tasks.iter().enumerate() {
                        let step = (t.keyspace / shards).max(1);
                        for s in 0..shards {
                            let lo = s * step;
                            if lo >= t.keyspace {
                                continue;
                            }
                            let hi = if s == shards - 1 { t.keyspace } else { (s + 1) * step };
                            let (seed, target, rounds) = (t.seed, t.target, self.rounds);
                            mitosis_events += 1;
                            handles.push((ti, tokio::task::spawn_blocking(move || {
                                solve_shard(seed, target, lo, hi, rounds)
                            })));
                        }
                    }
                    for (ti, h) in handles {
                        if let Ok(Some(x)) = h.await {
                            answers[ti] = Some(x);
                        }
                    }
                });
            } else {
                for (ti, t) in self.tasks.iter().enumerate() {
                    answers[ti] = solve_shard(t.seed, t.target, 0, t.keyspace, self.rounds);
                }
            }
            let us = t0.elapsed().as_micros() as f64;
            self.result(us, &answers, lean, full, mitosis_events, stress as f64, cores)
        })
    }
}

impl MitosisBenchmark {
    /// Build the working context (system + recent hypotheses + verbose noise).
    fn build_ctx(&self) -> (CtxCore, u64) {
        let ctx = CtxCore::new(0.05, 64);
        ctx.insert(
            "SYSTEM: cybersecurity vulnerability-sweep and auto-refactor specialist; \
             obey the ruleset and the target spec at all times."
                .to_string(),
            50.0,
            KEEP,
        );
        for i in 0..self.tasks.len() {
            ctx.insert(
                format!("[hypothesis {i}] candidate exploit path + the key invariants to verify"),
                2.0,
                KEEP,
            );
            ctx.insert(
                format!("[scan-log {i}] verbose stack dump json blob trace detail entry value \
                         context payload bytes offset register frame heap slot noise noise noise"),
                0.5,
                0,
            );
        }
        let full = ctx.inserted_tokens();
        (ctx, full)
    }

    #[allow(clippy::too_many_arguments)]
    fn result(&self, us: f64, answers: &[Option<u64>], avg_tokens: u64, full: u64,
              mitosis_events: u64, stress: f64, workers: usize) -> HashMap<String, f64> {
        let mut correct = 0usize;
        for (t, a) in self.tasks.iter().zip(answers.iter()) {
            if *a == Some(t.answer) {
                correct += 1;
            }
        }
        let solved = answers.iter().filter(|a| a.is_some()).count();
        let mut m = HashMap::new();
        m.insert("elapsed_us".into(), us);
        m.insert("solved".into(), solved as f64);
        m.insert("correct".into(), correct as f64);
        m.insert("total".into(), self.tasks.len() as f64);
        m.insert("avg_tokens_per_call".into(), avg_tokens as f64);
        m.insert("full_context_tokens".into(), full as f64);
        m.insert("context_reduction_pct".into(),
                 if full > 0 { 100.0 * (1.0 - avg_tokens as f64 / full as f64) } else { 0.0 });
        m.insert("mitosis_events".into(), mitosis_events as f64);
        m.insert("total_stress".into(), stress);
        m.insert("workers".into(), workers as f64);
        m
    }
}
