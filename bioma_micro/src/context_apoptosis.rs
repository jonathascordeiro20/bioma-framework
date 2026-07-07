//! `context_apoptosis.rs` — autonomous history dehydration.
//!
//! Long agent sessions (audit logs, massive chats) accumulate low-value ballast:
//! verbose tool output, stale turns, resolved chatter. This engine assigns each
//! message a **metabolic weight** by class, applies an aggressive **half-life
//! decay** (older + lower-value → drains faster), and **purges** any block whose
//! oxygen falls below the safe threshold — before the payload is dispatched to the
//! API. Durable classes (SYSTEM, FACT) are reinforced and never purged.
//!
//! Result: the input context window is dehydrated (universal input-token savings)
//! with a pure-Rust, thread-safe, allocation-light pass.

use std::collections::hash_map::DefaultHasher;
use std::collections::HashSet;
use std::hash::{Hash, Hasher};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::Instant;

use pyo3::prelude::*;
use pyo3::types::PyDict;

// Metabolic signal classes (bitwise flags shared with the Python layer).
pub const SYSTEM: u32 = 1 << 0; // durable instructions — never purge
pub const USER: u32 = 1 << 1; // user turns
pub const ASSISTANT: u32 = 1 << 2; // model turns
pub const FACT: u32 = 1 << 3; // retrieved facts / decisions to keep
pub const TOOL: u32 = 1 << 4; // verbose tool logs / scratchpad — prime target
const PROTECTED: u32 = SYSTEM | FACT;

/// ~4 chars/token — identical to the Python side so 'full' and 'pruned' counts agree.
#[inline]
pub fn est_tokens(s: &str) -> u32 {
    ((s.len() / 4) + 1) as u32
}

/// Initial metabolic weight (oxygen) by signal class. Durable data start rich;
/// verbose tool output starts oxygen-poor and dehydrates first.
#[inline]
fn metabolic_weight(signal: u32) -> f32 {
    if signal & PROTECTED != 0 {
        4.0
    } else if signal & (USER | ASSISTANT) != 0 {
        1.0
    } else if signal & TOOL != 0 {
        0.25
    } else {
        0.6
    }
}

struct Cell {
    content: String,
    oxygen: f32,
    signal: u32,
    tokens: u32,
}

// --------------------------------------------------------------------------- //
//  ContextApoptosis — stateful, incremental engine
// --------------------------------------------------------------------------- //
/// A self-dehydrating context window. Insert blocks, then run `dehydrate` cycles;
/// each cycle halves oxygen over `half_life` and purges anything below the
/// `safe_threshold` (durable classes are reinforced and survive).
#[pyclass]
pub struct ContextApoptosis {
    half_life: f32,
    safe_threshold: f32,
    items: Mutex<Vec<Cell>>,
    inserted_tokens: AtomicU64,
    apoptosed_tokens: AtomicU64,
    apoptosed_count: AtomicU64,
}

#[pymethods]
impl ContextApoptosis {
    #[new]
    #[pyo3(signature = (half_life = 2.0, safe_threshold = 0.35, capacity = 256))]
    fn new(half_life: f32, safe_threshold: f32, capacity: usize) -> Self {
        Self {
            half_life: half_life.max(0.1),
            safe_threshold,
            items: Mutex::new(Vec::with_capacity(capacity)),
            inserted_tokens: AtomicU64::new(0),
            apoptosed_tokens: AtomicU64::new(0),
            apoptosed_count: AtomicU64::new(0),
        }
    }

    /// Insert a context block. `oxygen < 0` (default) → auto metabolic weight.
    #[pyo3(signature = (content, signal = 0, oxygen = -1.0))]
    fn insert(&self, content: String, signal: u32, oxygen: f32) {
        let tokens = est_tokens(&content);
        self.inserted_tokens.fetch_add(tokens as u64, Ordering::Relaxed);
        let oxy = if oxygen < 0.0 { metabolic_weight(signal) } else { oxygen };
        self.items.lock().unwrap().push(Cell { content, oxygen: oxy, signal, tokens });
    }

    /// One half-life decay cycle → returns the number of purged blocks. Durable
    /// classes are reinforced by `reinforce_boost`; everything else decays by
    /// `2^(-1/half_life)` and is purged in place if it drops below the threshold.
    #[pyo3(signature = (reinforce_boost = 0.5))]
    fn dehydrate(&self, py: Python<'_>, reinforce_boost: f32) -> usize {
        let factor = 2f32.powf(-1.0 / self.half_life);
        let eps = self.safe_threshold;
        py.allow_threads(|| {
            let mut items = self.items.lock().unwrap();
            for c in items.iter_mut() {
                if c.signal & PROTECTED != 0 {
                    c.oxygen += reinforce_boost;
                } else {
                    c.oxygen *= factor;
                }
            }
            let before = items.len();
            let mut freed: u64 = 0;
            items.retain(|c| {
                let alive = (c.signal & PROTECTED != 0) || c.oxygen >= eps;
                if !alive {
                    freed += c.tokens as u64;
                }
                alive
            });
            let purged = before - items.len();
            self.apoptosed_count.fetch_add(purged as u64, Ordering::Relaxed);
            self.apoptosed_tokens.fetch_add(freed, Ordering::Relaxed);
            purged
        })
    }

    fn active_context(&self) -> Vec<String> {
        self.items.lock().unwrap().iter().map(|c| c.content.clone()).collect()
    }
    /// The dehydrated context, newline-joined, ready to dispatch.
    fn render(&self) -> String {
        self.items.lock().unwrap().iter().map(|c| c.content.as_str()).collect::<Vec<_>>().join("\n")
    }
    fn active_tokens(&self) -> u64 {
        self.items.lock().unwrap().iter().map(|c| c.tokens as u64).sum()
    }
    fn inserted_tokens(&self) -> u64 {
        self.inserted_tokens.load(Ordering::Relaxed)
    }
    fn __len__(&self) -> usize {
        self.items.lock().unwrap().len()
    }
    /// Fraction of inserted tokens reclaimed by apoptosis (0..1).
    fn reduction_ratio(&self) -> f32 {
        let ins = self.inserted_tokens();
        if ins == 0 { 0.0 } else { self.apoptosed_tokens.load(Ordering::Relaxed) as f32 / ins as f32 }
    }
}

// --------------------------------------------------------------------------- //
//  dehydrate() — the one-shot stateless filter used by the OpenRouter client
// --------------------------------------------------------------------------- //
/// Dehydrate a whole message history in a single pass (oldest → newest).
///
/// `messages` is a list of `(content, signal_flags)`. Older, lower-value blocks
/// are decayed by recency-weighted half-life and purged below `safe_threshold`;
/// durable classes (SYSTEM, FACT) always survive. Returns the surviving blocks
/// plus audited savings and the pure-kernel latency in microseconds.
#[pyfunction]
#[pyo3(signature = (messages, half_life = 6.0, safe_threshold = 0.35))]
pub fn dehydrate<'py>(
    py: Python<'py>,
    messages: Vec<(String, u32)>,
    half_life: f32,
    safe_threshold: f32,
) -> PyResult<Bound<'py, PyDict>> {
    let hl = half_life.max(0.1);
    let n = messages.len();

    // --- the measured kernel hot-path: decide survivors (pure compute, GIL released) ---
    let t0 = Instant::now();
    let decisions: Vec<bool> = py.allow_threads(|| {
        let mut keep = Vec::with_capacity(n);
        for (i, (content, signal)) in messages.iter().enumerate() {
            let protected = signal & PROTECTED != 0;
            if protected {
                keep.push(true);
                continue;
            }
            let age = (n - 1 - i) as f32; // 0 = newest
            let oxygen = metabolic_weight(*signal) * 2f32.powf(-age / hl);
            let _ = content; // content length already priced into tokens below
            keep.push(oxygen >= safe_threshold);
        }
        keep
    });
    let latency_us = t0.elapsed().as_nanos() as f64 / 1000.0;

    // --- marshal survivors + audit token savings (not counted in kernel latency) ---
    let kept = pyo3::types::PyList::empty_bound(py);
    let mut tokens_before: u64 = 0;
    let mut tokens_after: u64 = 0;
    let mut purged: usize = 0;
    for ((content, _sig), &alive) in messages.iter().zip(decisions.iter()) {
        let tok = est_tokens(content) as u64;
        tokens_before += tok;
        if alive {
            tokens_after += tok;
            kept.append(content)?;
        } else {
            purged += 1;
        }
    }
    let reduction = if tokens_before == 0 {
        0.0
    } else {
        1.0 - (tokens_after as f64 / tokens_before as f64)
    };

    let d = PyDict::new_bound(py);
    d.set_item("kept", kept)?;
    d.set_item("blocks_in", n)?;
    d.set_item("blocks_kept", n - purged)?;
    d.set_item("blocks_purged", purged)?;
    d.set_item("tokens_before", tokens_before)?;
    d.set_item("tokens_after", tokens_after)?;
    d.set_item("reduction", reduction)?;
    d.set_item("kernel_latency_us", latency_us)?;
    Ok(d)
}

// --------------------------------------------------------------------------- //
//  saturation_scan() — cognitive-DDoS / flood detector
// --------------------------------------------------------------------------- //
/// Detect input saturation: the fraction of the payload that is **repetition**.
///
/// Cognitive-DDoS, forged-log floods and jailbreak spam are highly repetitive —
/// they reuse the same phrases to exhaust the context window. This scores the
/// fraction of duplicate `w`-token shingles (default 8): ~1.0 = a repetitive
/// flood (RED ALERT), ~0.0 = natural, high-entropy text. Pure O(n), no
/// allocation (shingles are hashed, not materialised), microsecond-scale.
#[pyfunction]
#[pyo3(signature = (text, window = 8))]
pub fn saturation_scan(text: &str, window: usize) -> f32 {
    let w = window.max(1);
    let tokens: Vec<&str> = text.split_whitespace().collect();
    let n = tokens.len();
    if n < w * 2 {
        return 0.0;
    }
    let windows = n - w + 1;
    let mut seen: HashSet<u64> = HashSet::with_capacity(windows);
    let mut dupes = 0usize;
    for i in 0..windows {
        let mut h = DefaultHasher::new();
        for t in &tokens[i..i + w] {
            t.hash(&mut h);
        }
        if !seen.insert(h.finish()) {
            dupes += 1;
        }
    }
    dupes as f32 / windows as f32
}
