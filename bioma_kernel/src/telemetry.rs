//! The Nervous-System Metrics — an ultra-light, in-memory telemetry collector.
//!
//! Every counter is a lock-free atomic, so recording a sample from the hot path
//! costs a couple of `fetch_add`s and adds no measurable latency to the kernel.
//! A small sampled ring (behind an `RwLock`, written 1-in-256) keeps recent
//! latency samples for percentiles without contending the hot path.

use std::sync::atomic::{AtomicU32, AtomicU64, AtomicUsize, Ordering};
use std::sync::RwLock;

#[inline(always)]
fn store_f32(cell: &AtomicU32, v: f32) {
    cell.store(v.to_bits(), Ordering::Relaxed);
}
#[inline(always)]
fn load_f32(cell: &AtomicU32) -> f32 {
    f32::from_bits(cell.load(Ordering::Relaxed))
}

/// A tiny fixed-capacity ring of latency samples (microseconds) for percentiles.
struct LatencyRing {
    buf: Vec<u32>,
    idx: usize,
    filled: bool,
}
impl LatencyRing {
    fn new(cap: usize) -> Self {
        Self { buf: vec![0u32; cap.max(1)], idx: 0, filled: false }
    }
    #[inline]
    fn push(&mut self, us: u32) {
        self.buf[self.idx] = us;
        self.idx += 1;
        if self.idx >= self.buf.len() {
            self.idx = 0;
            self.filled = true;
        }
    }
    fn sorted(&self) -> Vec<u32> {
        let n = if self.filled { self.buf.len() } else { self.idx };
        let mut v: Vec<u32> = self.buf[..n].to_vec();
        v.sort_unstable();
        v
    }
}

/// A point-in-time read of the whole nervous system.
pub struct TelemetrySnapshot {
    pub signals: u64,
    pub avg_latency_us: f64,
    pub max_latency_us: f64,
    pub p99_latency_us: f64,
    pub tokens_saved: u64,
    pub agents_active: usize,
    pub peak_agents: usize,
    pub density: f32,
    pub apoptosis_events: u64,
}

/// Lock-free metrics core.  Cheap to write, safe to read from any thread.
pub struct Telemetry {
    signals: AtomicU64,
    total_latency_ns: AtomicU64,
    max_latency_ns: AtomicU64,
    tokens_saved: AtomicU64,
    apoptosis_events: AtomicU64,
    agents_active: AtomicUsize,
    peak_agents: AtomicUsize,
    density_bits: AtomicU32, // densidade_hormonal (f32 bits), refreshed by the monitor
    recent: RwLock<LatencyRing>,
}

impl Telemetry {
    pub fn new() -> Self {
        Self {
            signals: AtomicU64::new(0),
            total_latency_ns: AtomicU64::new(0),
            max_latency_ns: AtomicU64::new(0),
            tokens_saved: AtomicU64::new(0),
            apoptosis_events: AtomicU64::new(0),
            agents_active: AtomicUsize::new(0),
            peak_agents: AtomicUsize::new(0),
            density_bits: AtomicU32::new(0),
            recent: RwLock::new(LatencyRing::new(8192)),
        }
    }

    /// Record a hormone round-trip latency (ns).  Hot path — atomics only, with a
    /// 1-in-256 sampled ring write for percentiles.
    #[inline]
    pub fn record_latency(&self, ns: u64) {
        let count = self.signals.fetch_add(1, Ordering::Relaxed) + 1;
        self.total_latency_ns.fetch_add(ns, Ordering::Relaxed);
        let mut m = self.max_latency_ns.load(Ordering::Relaxed);
        while ns > m {
            match self.max_latency_ns.compare_exchange_weak(m, ns, Ordering::Relaxed, Ordering::Relaxed) {
                Ok(_) => break,
                Err(x) => m = x,
            }
        }
        if count & 0xFF == 0 {
            if let Ok(mut r) = self.recent.write() {
                r.push((ns / 1000) as u32);
            }
        }
    }

    #[inline]
    pub fn add_tokens_saved(&self, n: u64) {
        self.tokens_saved.fetch_add(n, Ordering::Relaxed);
    }

    #[inline]
    pub fn inc_apoptosis(&self, n: u64) {
        self.apoptosis_events.fetch_add(n, Ordering::Relaxed);
    }

    pub fn set_agents(&self, n: usize) {
        self.agents_active.store(n, Ordering::Relaxed);
        let mut p = self.peak_agents.load(Ordering::Relaxed);
        while n > p {
            match self.peak_agents.compare_exchange_weak(p, n, Ordering::Relaxed, Ordering::Relaxed) {
                Ok(_) => break,
                Err(x) => p = x,
            }
        }
    }

    #[inline]
    pub fn set_density(&self, d: f32) {
        store_f32(&self.density_bits, d);
    }

    pub fn density(&self) -> f32 {
        load_f32(&self.density_bits)
    }

    pub fn snapshot(&self) -> TelemetrySnapshot {
        let signals = self.signals.load(Ordering::Relaxed);
        let total = self.total_latency_ns.load(Ordering::Relaxed);
        let avg_us = if signals > 0 { (total as f64 / signals as f64) / 1000.0 } else { 0.0 };
        let p99_us = {
            let s = self.recent.read().map(|r| r.sorted()).unwrap_or_default();
            if s.is_empty() { 0.0 } else { s[((s.len() as f64 * 0.99) as usize).min(s.len() - 1)] as f64 }
        };
        TelemetrySnapshot {
            signals,
            avg_latency_us: avg_us,
            max_latency_us: self.max_latency_ns.load(Ordering::Relaxed) as f64 / 1000.0,
            p99_latency_us: p99_us,
            tokens_saved: self.tokens_saved.load(Ordering::Relaxed),
            agents_active: self.agents_active.load(Ordering::Relaxed),
            peak_agents: self.peak_agents.load(Ordering::Relaxed),
            density: self.density(),
            apoptosis_events: self.apoptosis_events.load(Ordering::Relaxed),
        }
    }
}

impl Default for Telemetry {
    fn default() -> Self {
        Self::new()
    }
}
