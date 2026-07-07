//! Context Apoptosis — self-pruning agent memory.
//!
//! Every datum carries `oxygen`; a decay cycle drains it (signal-matched data are
//! reinforced), and data below `epsilon` are purged in place (capacity reused) —
//! shrinking the LLM context window autonomously.
//!
//! The pure-Rust [`CtxCore`] holds the state and is `Arc`-shareable, so both the
//! Python [`StateContext`] pyclass and the concurrent stress engine drive the
//! same apoptosis logic.

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

use pyo3::prelude::*;

struct MemoryCell {
    #[allow(dead_code)]
    seq: u64,
    content: String,
    oxygen: f32,
    signal: u32,
    tokens: u32,
}

#[inline]
fn est_tokens(s: &str) -> u32 {
    ((s.len() / 4) + 1) as u32
}

/// Shareable, thread-safe apoptosis core.
pub struct CtxCore {
    items: Mutex<Vec<MemoryCell>>,
    seq: AtomicU64,
    epsilon: f32,
    inserted_tokens: AtomicU64,
    apoptosed_tokens: AtomicU64,
    apoptosed_count: AtomicU64,
}

impl CtxCore {
    pub fn new(epsilon: f32, capacity: usize) -> Self {
        Self {
            items: Mutex::new(Vec::with_capacity(capacity)),
            seq: AtomicU64::new(0),
            epsilon,
            inserted_tokens: AtomicU64::new(0),
            apoptosed_tokens: AtomicU64::new(0),
            apoptosed_count: AtomicU64::new(0),
        }
    }

    pub fn insert(&self, content: String, oxygen: f32, signal: u32) -> u64 {
        let seq = self.seq.fetch_add(1, Ordering::Relaxed);
        let tokens = est_tokens(&content);
        self.inserted_tokens.fetch_add(tokens as u64, Ordering::Relaxed);
        self.items.lock().unwrap().push(MemoryCell { seq, content, oxygen, signal, tokens });
        seq
    }

    /// One decay cycle → `(apoptosed_count, freed_tokens)`.  Purges in place.
    pub fn decay(&self, rate: f32, reinforce_mask: u32, reinforce_amount: f32) -> (usize, u64) {
        let eps = self.epsilon;
        let mut items = self.items.lock().unwrap();
        let before = items.len();
        for c in items.iter_mut() {
            if reinforce_mask != 0 && (c.signal & reinforce_mask) != 0 {
                c.oxygen += reinforce_amount;
            }
            c.oxygen -= rate;
        }
        let mut freed: u64 = 0;
        items.retain(|c| {
            let alive = c.oxygen > eps;
            if !alive {
                freed += c.tokens as u64;
            }
            alive
        });
        let purged = before - items.len();
        self.apoptosed_count.fetch_add(purged as u64, Ordering::Relaxed);
        self.apoptosed_tokens.fetch_add(freed, Ordering::Relaxed);
        (purged, freed)
    }

    pub fn active_context(&self) -> Vec<String> {
        self.items.lock().unwrap().iter().map(|c| c.content.clone()).collect()
    }
    pub fn active_tokens(&self) -> u64 {
        self.items.lock().unwrap().iter().map(|c| c.tokens as u64).sum()
    }
    pub fn len(&self) -> usize {
        self.items.lock().unwrap().len()
    }
    pub fn inserted_tokens(&self) -> u64 {
        self.inserted_tokens.load(Ordering::Relaxed)
    }
    pub fn apoptosed_tokens(&self) -> u64 {
        self.apoptosed_tokens.load(Ordering::Relaxed)
    }
    pub fn apoptosed_count(&self) -> u64 {
        self.apoptosed_count.load(Ordering::Relaxed)
    }
    pub fn reduction_ratio(&self) -> f32 {
        let ins = self.inserted_tokens();
        if ins == 0 { 0.0 } else { self.apoptosed_tokens() as f32 / ins as f32 }
    }
}

/// Python-facing self-pruning memory (wraps a shared [`CtxCore`]).
#[pyclass]
pub struct StateContext {
    core: Arc<CtxCore>,
}

#[pymethods]
impl StateContext {
    #[new]
    #[pyo3(signature = (epsilon = 0.05, capacity = 256))]
    fn new(epsilon: f32, capacity: usize) -> Self {
        Self { core: Arc::new(CtxCore::new(epsilon, capacity)) }
    }

    #[pyo3(signature = (content, oxygen = 1.0, signal = 0))]
    fn insert(&self, content: String, oxygen: f32, signal: u32) -> u64 {
        self.core.insert(content, oxygen, signal)
    }

    #[pyo3(signature = (rate = 0.2, reinforce_mask = 0, reinforce_amount = 0.0))]
    fn decay(&self, py: Python<'_>, rate: f32, reinforce_mask: u32, reinforce_amount: f32) -> usize {
        py.allow_threads(|| self.core.decay(rate, reinforce_mask, reinforce_amount).0)
    }

    fn active_context(&self) -> Vec<String> {
        self.core.active_context()
    }
    fn active_tokens(&self) -> u64 {
        self.core.active_tokens()
    }
    fn __len__(&self) -> usize {
        self.core.len()
    }
    fn len(&self) -> usize {
        self.core.len()
    }
    fn reduction_ratio(&self) -> f32 {
        self.core.reduction_ratio()
    }

    fn stats(&self) -> std::collections::HashMap<String, f64> {
        let mut m = std::collections::HashMap::new();
        m.insert("alive".into(), self.core.len() as f64);
        m.insert("active_tokens".into(), self.core.active_tokens() as f64);
        m.insert("inserted_tokens".into(), self.core.inserted_tokens() as f64);
        m.insert("apoptosed_tokens".into(), self.core.apoptosed_tokens() as f64);
        m.insert("apoptosed_count".into(), self.core.apoptosed_count() as f64);
        m
    }
}
