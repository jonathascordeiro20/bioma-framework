//! `hormonal_bus.rs` — the lock-free in-memory signalling substrate.
//!
//! A fixed bank of atomic `f32` concentration cells (one per signal channel) is
//! updated with lock-free CAS loops, so `inject`/`sense` never take a lock and the
//! GIL is released on the hot path. Signal *events* are additionally fanned out
//! through a bounded `crossbeam-channel` for consumers that want the stream.
//!
//! Design target (measured on the reference host): ~2M signals/s at ~5μs mean
//! latency, bounded under 10× concurrent load. See `tests/`.

use std::collections::HashMap;
use std::sync::atomic::{AtomicU32, AtomicU64, Ordering};
use std::sync::Arc;

use crossbeam_channel::{bounded, Receiver, Sender};
use pyo3::prelude::*;

// --------------------------------------------------------------------------- //
//  Lock-free atomic f32 cells (concentration stored as its IEEE-754 bit pattern)
// --------------------------------------------------------------------------- //
#[inline(always)]
fn add_f32(cell: &AtomicU32, delta: f32) {
    let mut cur = cell.load(Ordering::Relaxed);
    loop {
        let new = f32::from_bits(cur) + delta;
        match cell.compare_exchange_weak(cur, new.to_bits(), Ordering::AcqRel, Ordering::Relaxed) {
            Ok(_) => break,
            Err(actual) => cur = actual,
        }
    }
}
#[inline(always)]
fn mul_f32(cell: &AtomicU32, factor: f32) {
    let mut cur = cell.load(Ordering::Relaxed);
    loop {
        let new = f32::from_bits(cur) * factor;
        match cell.compare_exchange_weak(cur, new.to_bits(), Ordering::AcqRel, Ordering::Relaxed) {
            Ok(_) => break,
            Err(actual) => cur = actual,
        }
    }
}
#[inline(always)]
fn load_f32(cell: &AtomicU32) -> f32 {
    f32::from_bits(cell.load(Ordering::Relaxed))
}
#[inline(always)]
fn valid_mask(n: usize) -> u32 {
    if n >= 32 { u32::MAX } else { (1u32 << n) - 1 }
}

// --------------------------------------------------------------------------- //
//  HormonalSignal — the lightweight payload on the wire
// --------------------------------------------------------------------------- //
/// A single hormonal signal: bitwise channel `flags` (`u32`) + `intensity` (`f32`).
// from_py_object: keep the pre-0.29 behavior of extracting the struct by value
// from Python (the bus API receives signals as arguments).
#[pyclass(from_py_object)]
#[derive(Clone, Copy)]
pub struct HormonalSignal {
    #[pyo3(get, set)]
    pub flags: u32,
    #[pyo3(get, set)]
    pub intensity: f32,
}

#[pymethods]
impl HormonalSignal {
    #[new]
    #[pyo3(signature = (flags, intensity = 1.0))]
    fn new(flags: u32, intensity: f32) -> Self {
        Self { flags, intensity }
    }
    fn __repr__(&self) -> String {
        format!("HormonalSignal(flags=0x{:X}, intensity={:.3})", self.flags, self.intensity)
    }
}

// --------------------------------------------------------------------------- //
//  BusCore — the shareable, lock-free core
// --------------------------------------------------------------------------- //
struct BusCore {
    conc: Box<[AtomicU32]>,
    n: usize,
    secretions: AtomicU64,
}

impl BusCore {
    fn new(n: usize) -> Self {
        let conc = (0..n).map(|_| AtomicU32::new(0)).collect::<Vec<_>>().into_boxed_slice();
        Self { conc, n, secretions: AtomicU64::new(0) }
    }
    #[inline(always)]
    fn secrete(&self, flags: u32, intensity: f32) {
        let mut f = flags & valid_mask(self.n);
        while f != 0 {
            let bit = f.trailing_zeros() as usize;
            add_f32(&self.conc[bit], intensity);
            f &= f - 1;
        }
        self.secretions.fetch_add(1, Ordering::Relaxed);
    }
    #[inline(always)]
    fn sense(&self, mask: u32) -> f32 {
        let mut acc = 0.0f32;
        let mut m = mask & valid_mask(self.n);
        while m != 0 {
            let bit = m.trailing_zeros() as usize;
            acc += load_f32(&self.conc[bit]);
            m &= m - 1;
        }
        acc
    }
    fn tick(&self, decay: f32) {
        for c in self.conc.iter() {
            mul_f32(c, decay);
        }
    }
    fn snapshot(&self) -> Vec<f32> {
        self.conc.iter().map(load_f32).collect()
    }
    fn total(&self) -> f32 {
        self.conc.iter().map(load_f32).sum()
    }
}

// --------------------------------------------------------------------------- //
//  HormonalBus — the Python-facing signalling bus
// --------------------------------------------------------------------------- //
/// Lock-free hormonal signalling bus. `inject`/`secrete` are O(popcount) and
/// release the GIL; `sense` reads the current concentration for a channel mask.
#[pyclass]
pub struct HormonalBus {
    core: Arc<BusCore>,
    tx: Sender<(u32, f32)>,
    rx: Receiver<(u32, f32)>,
}

#[pymethods]
impl HormonalBus {
    #[new]
    #[pyo3(signature = (num_signals = 32, event_capacity = 4096))]
    fn new(num_signals: usize, event_capacity: usize) -> Self {
        let n = num_signals.clamp(1, 32);
        let (tx, rx) = bounded(event_capacity.max(1));
        Self { core: Arc::new(BusCore::new(n)), tx, rx }
    }

    /// Inject a typed `HormonalSignal` (the primary API).
    fn inject(&self, py: Python<'_>, signal: HormonalSignal) {
        py.detach(|| {
            self.core.secrete(signal.flags, signal.intensity);
            let _ = self.tx.try_send((signal.flags, signal.intensity));
        });
    }

    /// Raw injection by `(flags, intensity)` — the microsecond hot path.
    fn secrete(&self, py: Python<'_>, flags: u32, intensity: f32) {
        py.detach(|| {
            self.core.secrete(flags, intensity);
            let _ = self.tx.try_send((flags, intensity));
        });
    }

    /// Current summed concentration across every channel in `mask`.
    fn sense(&self, py: Python<'_>, mask: u32) -> f32 {
        py.detach(|| self.core.sense(mask))
    }

    /// Concentration of a single channel bit.
    fn concentration(&self, signal_bit: usize) -> f32 {
        if signal_bit < self.core.n {
            load_f32(&self.core.conc[signal_bit])
        } else {
            0.0
        }
    }

    /// Multiplicative decay/dissipation of every channel (temporal homeostasis).
    fn tick(&self, py: Python<'_>, decay: f32) {
        py.detach(|| self.core.tick(decay));
    }

    fn snapshot(&self) -> Vec<f32> {
        self.core.snapshot()
    }

    /// Drain up to `max` buffered signal events as `(flags, intensity)` pairs.
    fn drain_events(&self, max: usize) -> Vec<(u32, f32)> {
        let mut out = Vec::new();
        while out.len() < max {
            match self.rx.try_recv() {
                Ok(e) => out.push(e),
                Err(_) => break,
            }
        }
        out
    }

    fn stats(&self) -> HashMap<String, f64> {
        let mut m = HashMap::new();
        m.insert("num_signals".into(), self.core.n as f64);
        m.insert("secretions".into(), self.core.secretions.load(Ordering::Relaxed) as f64);
        m.insert("total_concentration".into(), self.core.total() as f64);
        m
    }
}
