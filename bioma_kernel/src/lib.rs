//! B.I.O.M.A. Rust kernel — the microsecond hot-path + stress & telemetry.
//!
//! * [`HormonalBus`]  — lock-free hormonal signalling (atomic `f32` concentrations,
//!   bitwise signal flags), GIL released on the hot path.
//! * [`StateContext`] — self-pruning agent memory (`memory.rs`).
//! * [`StressTester`] — spawns 1k–10k concurrent Tokio micro-agents that flood the
//!   bus and force apoptosis under load, with a CPU-pinned telemetry collector
//!   (`telemetry.rs`) so monitoring never distorts the measured performance.

use std::sync::atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use crossbeam_channel::{bounded, Receiver, Sender};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

mod memory;
mod mitosis_test;
mod telemetry;
use memory::{CtxCore, StateContext};
use mitosis_test::MitosisBenchmark;
use telemetry::Telemetry;

// --------------------------------------------------------------------------- //
//  Lock-free atomic `f32` cells (concentration stored as its bit pattern)
// --------------------------------------------------------------------------- //
#[inline(always)]
fn add_f32(cell: &AtomicU32, delta: f32) -> f32 {
    let mut cur = cell.load(Ordering::Relaxed);
    loop {
        let new = f32::from_bits(cur) + delta;
        match cell.compare_exchange_weak(cur, new.to_bits(), Ordering::AcqRel, Ordering::Relaxed) {
            Ok(_) => return new,
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
fn store_f32(cell: &AtomicU32, v: f32) {
    cell.store(v.to_bits(), Ordering::Relaxed);
}
#[inline(always)]
fn valid_mask(n: usize) -> u32 {
    if n >= 32 { u32::MAX } else { (1u32 << n) - 1 }
}
/// Fast deterministic PRNG (splitmix64) — no `rand` dependency, reproducible.
#[inline(always)]
fn splitmix64(mut x: u64) -> u64 {
    x = x.wrapping_add(0x9E37_79B9_7F4A_7C15);
    let mut z = x;
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

// --------------------------------------------------------------------------- //
//  BusCore — the shareable, lock-free signalling substrate
// --------------------------------------------------------------------------- //
pub struct BusCore {
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
//  HormonalBus (Python)
// --------------------------------------------------------------------------- //
#[derive(Clone, Copy)]
struct HormoneEvent {
    flags: u32,
    intensity: f32,
}
struct Subscription {
    mask: u32,
    threshold: f32,
    hits: u64,
}

#[pyclass]
pub struct HormonalBus {
    core: Arc<BusCore>,
    subs: Mutex<Vec<Subscription>>,
    tx: Sender<HormoneEvent>,
    rx: Receiver<HormoneEvent>,
}

#[pymethods]
impl HormonalBus {
    #[new]
    #[pyo3(signature = (num_signals = 32, event_capacity = 4096))]
    fn new(num_signals: usize, event_capacity: usize) -> Self {
        let n = num_signals.clamp(1, 32);
        let (tx, rx) = bounded(event_capacity.max(1));
        Self { core: Arc::new(BusCore::new(n)), subs: Mutex::new(Vec::new()), tx, rx }
    }

    fn secrete(&self, py: Python<'_>, flags: u32, intensity: f32) {
        py.allow_threads(|| {
            self.core.secrete(flags, intensity);
            let _ = self.tx.try_send(HormoneEvent { flags, intensity });
        });
    }
    fn sense(&self, py: Python<'_>, mask: u32) -> f32 {
        py.allow_threads(|| self.core.sense(mask))
    }
    fn concentration(&self, signal_bit: usize) -> f32 {
        if signal_bit < self.core.n { load_f32(&self.core.conc[signal_bit]) } else { 0.0 }
    }
    fn tick(&self, py: Python<'_>, decay: f32) {
        py.allow_threads(|| self.core.tick(decay));
    }
    fn snapshot(&self) -> Vec<f32> {
        self.core.snapshot()
    }
    fn subscribe(&self, mask: u32, threshold: f32) -> usize {
        let mut subs = self.subs.lock().unwrap();
        subs.push(Subscription { mask, threshold, hits: 0 });
        subs.len() - 1
    }
    fn poll(&self, py: Python<'_>, sub_id: usize) -> Option<f32> {
        let (mask, threshold) = {
            let subs = self.subs.lock().unwrap();
            let s = subs.get(sub_id)?;
            (s.mask, s.threshold)
        };
        let cur = py.allow_threads(|| self.core.sense(mask));
        if cur >= threshold {
            if let Some(s) = self.subs.lock().unwrap().get_mut(sub_id) {
                s.hits += 1;
            }
            Some(cur)
        } else {
            None
        }
    }
    fn drain_events(&self, max: usize) -> Vec<(u32, f32)> {
        let mut out = Vec::new();
        while out.len() < max {
            match self.rx.try_recv() {
                Ok(e) => out.push((e.flags, e.intensity)),
                Err(_) => break,
            }
        }
        out
    }
    fn stats(&self) -> std::collections::HashMap<String, f64> {
        let mut m = std::collections::HashMap::new();
        m.insert("num_signals".into(), self.core.n as f64);
        m.insert("secretions".into(), self.core.secretions.load(Ordering::Relaxed) as f64);
        m.insert("total_concentration".into(), self.core.total() as f64);
        m.insert("subscriptions".into(), self.subs.lock().unwrap().len() as f64);
        m
    }
}

// --------------------------------------------------------------------------- //
//  StressTester — 1k–10k concurrent Tokio micro-agents + pinned telemetry
// --------------------------------------------------------------------------- //
#[allow(clippy::too_many_arguments)]
async fn agent_loop(
    id: usize,
    n: usize,
    bus: Arc<BusCore>,
    ctx: Arc<CtxCore>,
    telem: Arc<Telemetry>,
    glow: Arc<Vec<AtomicU32>>,
    running: Arc<AtomicBool>,
    insert_every: u64,
) {
    let mut it: u64 = id as u64 + 1;
    while running.load(Ordering::Relaxed) {
        // Deterministic multi-signal pattern for this agent/iteration.
        let h = splitmix64(it ^ ((id as u64) << 20));
        let mut flags = (h as u32) & valid_mask(n);
        if flags == 0 {
            flags = 1;
        }
        let intensity = 0.001 + ((h >> 33) & 0xFF) as f32 * 0.0004;

        // --- the measured hormone round-trip (lock-free) --- //
        let t0 = Instant::now();
        bus.secrete(flags, intensity);
        let received = bus.sense(flags);
        let dt = t0.elapsed().as_nanos() as u64;
        telem.record_latency(dt);
        store_f32(&glow[id], received);

        // sparsely feed memory so apoptosis has something to prune under load
        if insert_every > 0 && it % insert_every == 0 {
            ctx.insert(format!("agent {id} log {it}"), 0.5, flags);
        }
        it += 1;
        if it % 64 == 0 {
            tokio::task::yield_now().await; // cooperative scheduling point
        }
    }
}

#[pyclass]
pub struct StressTester {
    bus: Arc<BusCore>,
    ctx: Arc<CtxCore>,
    telem: Arc<Telemetry>,
    node_glow: Arc<Vec<AtomicU32>>,
    n_signals: usize,
    max_agents: usize,
}

#[pymethods]
impl StressTester {
    #[new]
    #[pyo3(signature = (num_signals = 16, max_agents = 10000))]
    fn new(num_signals: usize, max_agents: usize) -> Self {
        let n = num_signals.clamp(1, 32);
        let cap = max_agents.max(1);
        let node_glow = Arc::new((0..cap).map(|_| AtomicU32::new(0)).collect::<Vec<_>>());
        Self {
            bus: Arc::new(BusCore::new(n)),
            ctx: Arc::new(CtxCore::new(0.05, 4096)),
            telem: Arc::new(Telemetry::new()),
            node_glow,
            n_signals: n,
            max_agents: cap,
        }
    }

    /// Spawn `num_agents` Tokio micro-agents flooding the bus for `duration_secs`.
    /// The telemetry collector runs on its own **pinned** core; Tokio workers take
    /// the remaining cores, so monitoring never distorts the measured latency.
    #[pyo3(signature = (num_agents, duration_secs, insert_every = 64, decay_interval_us = 250, decay_rate = 0.6, dissipation = 0.90))]
    fn run(
        &self,
        py: Python<'_>,
        num_agents: usize,
        duration_secs: f64,
        insert_every: u64,
        decay_interval_us: u64,
        decay_rate: f32,
        dissipation: f32,
    ) -> std::collections::HashMap<String, f64> {
        let num_agents = num_agents.clamp(1, self.max_agents);
        py.allow_threads(|| {
            let running = Arc::new(AtomicBool::new(true));

            // ---- CPU-pinned telemetry collector (isolated core) ---- //
            let monitor = {
                let bus = self.bus.clone();
                let ctx = self.ctx.clone();
                let telem = self.telem.clone();
                let running = running.clone();
                std::thread::spawn(move || {
                    if let Some(ids) = core_affinity::get_core_ids() {
                        if let Some(last) = ids.last() {
                            core_affinity::set_for_current(*last); // isolate the collector
                        }
                    }
                    while running.load(Ordering::Relaxed) {
                        telem.set_density(bus.total());
                        bus.tick(dissipation); // temporal dissipation → bounded, meaningful density/glow
                        let (purged, freed) = ctx.decay(decay_rate, 0, 0.0);
                        if purged > 0 {
                            telem.inc_apoptosis(purged as u64);
                            telem.add_tokens_saved(freed);
                        }
                        std::thread::sleep(Duration::from_micros(decay_interval_us.max(1)));
                    }
                })
            };

            // ---- Tokio flood: workers = cores-1 (leave the last for the monitor) ---- //
            let cores = std::thread::available_parallelism().map(|c| c.get()).unwrap_or(4);
            let workers = cores.saturating_sub(1).max(1);
            let rt = tokio::runtime::Builder::new_multi_thread()
                .worker_threads(workers)
                .enable_time()
                .build()
                .expect("tokio runtime");
            rt.block_on(async {
                self.telem.set_agents(num_agents);
                let mut handles = Vec::with_capacity(num_agents);
                for id in 0..num_agents {
                    handles.push(tokio::spawn(agent_loop(
                        id,
                        self.n_signals,
                        self.bus.clone(),
                        self.ctx.clone(),
                        self.telem.clone(),
                        self.node_glow.clone(),
                        running.clone(),
                        insert_every,
                    )));
                }
                tokio::time::sleep(Duration::from_secs_f64(duration_secs)).await;
                running.store(false, Ordering::Relaxed);
                for h in handles {
                    let _ = h.await;
                }
            });
            running.store(false, Ordering::Relaxed);
            let _ = monitor.join();
        });
        self.metricas()
    }

    /// Flat metrics map (for quick reads / CSV).
    fn metricas(&self) -> std::collections::HashMap<String, f64> {
        let s = self.telem.snapshot();
        let mut m = std::collections::HashMap::new();
        m.insert("latencia_comunicacao_us".into(), s.avg_latency_us);
        m.insert("latencia_p99_us".into(), s.p99_latency_us);
        m.insert("latencia_max_us".into(), s.max_latency_us);
        m.insert("tokens_salvos_apoptose".into(), s.tokens_saved as f64);
        m.insert("agentes_ativos".into(), s.agents_active as f64);
        m.insert("pico_agentes".into(), s.peak_agents as f64);
        m.insert("densidade_hormonal".into(), s.density as f64);
        m.insert("sinais_processados".into(), s.signals as f64);
        m.insert("apoptosis_events".into(), s.apoptosis_events as f64);
        m
    }

    /// Rich snapshot for the React/D3 dashboard: totals + the graph (sampled nodes
    /// with their hormonal glow, and per-signal-channel concentration).
    fn obter_estado_sistema_nervoso<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let s = self.telem.snapshot();
        let d = PyDict::new_bound(py);
        d.set_item("agentes_ativos", s.agents_active)?;
        d.set_item("pico_agentes", s.peak_agents)?;
        d.set_item("densidade_hormonal", s.density)?;
        d.set_item("latencia_comunicacao_us", s.avg_latency_us)?;
        d.set_item("latencia_p99_us", s.p99_latency_us)?;
        d.set_item("latencia_max_us", s.max_latency_us)?;
        d.set_item("sinais_processados", s.signals)?;
        d.set_item("tokens_salvos_apoptose", s.tokens_saved)?;
        d.set_item("apoptosis_events", s.apoptosis_events)?;
        d.set_item("concentracao_por_sinal", self.bus.snapshot())?;

        // Down-sample the node graph to <=256 nodes for the dashboard.
        let nos = PyList::empty_bound(py);
        let sample = 256usize.min(self.max_agents.max(1));
        let step = (self.max_agents / sample).max(1);
        let mut id = 0usize;
        while id < self.max_agents && nos.len() < sample {
            let node = PyDict::new_bound(py);
            node.set_item("id", id)?;
            node.set_item("brilho", load_f32(&self.node_glow[id]))?;
            nos.append(node)?;
            id += step;
        }
        d.set_item("nos", nos)?;
        Ok(d)
    }
}

/// The native module — `import bioma_kernel`.
#[pymodule]
fn bioma_kernel(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<HormonalBus>()?;
    m.add_class::<StateContext>()?;
    m.add_class::<StressTester>()?;
    m.add_class::<MitosisBenchmark>()?;
    m.add("__doc__", "B.I.O.M.A. Rust kernel — hormonal bus, memory apoptosis, stress, telemetry, mitosis.")?;
    Ok(())
}
