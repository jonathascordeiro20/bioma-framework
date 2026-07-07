# B.I.O.M.A. Kernel (Rust + PyO3)

The **microsecond hot-path** of B.I.O.M.A., written in Rust and exposed to Python
as a native extension (`import bioma_kernel`). It takes the two latency-critical,
allocation-heavy primitives off the Python interpreter:

1. **Hormonal Bus** — lock-free in-memory signalling. "Hormones" are bitwise
   signal flags (`u32`) carrying an `f32` concentration; routing is a bounded
   atomic CAS loop per set bit — **no heap allocation on `secrete`/`sense`/`tick`**,
   GIL released so many threads signal concurrently.
2. **Context Apoptosis** — self-pruning agent memory. Each datum carries `oxygen`;
   a decay cycle drains it (relevant, signal-tagged data are reinforced), and data
   that fall below `epsilon` are **purged in place** (capacity reused) — shrinking
   the context window sent to the LLM autonomously.

## File layout
```
bioma_kernel/
├── Cargo.toml          # crate-type = ["cdylib"]; pyo3 + crossbeam; release LTO
├── pyproject.toml      # maturin build backend
├── src/
│   ├── lib.rs          # HormonalBus + StressTester + #[pymodule]
│   ├── memory.rs       # CtxCore/StateContext + oxygen decay + in-place apoptosis
│   └── telemetry.rs    # lock-free metrics collector (atomics + sampled ring)
├── app.py              # bus + apoptosis demo + hot-path microbenchmark
├── stress_benchmark.py # 5,000 agents × 30s market-grade stress report
├── nervous_system_server.py     # FastAPI: serves the dashboard + /ws snapshot @10Hz
├── nervous_system_dashboard.html# single-file Canvas "Sistema Nervoso Visível"
└── README.md
```

## Live dashboard — "Sistema Nervoso Visível"
A zero-dependency, Canvas-powered dashboard (works offline — no D3 CDN) that
streams the kernel's live state over a WebSocket: a glowing neuron field (node
brightness = sensed hormone concentration), live latency / throughput / density
gauges, a per-channel hormone equalizer, and crimson bursts when cells apoptose.
```bash
cd bioma_kernel
python nervous_system_server.py          # → open http://127.0.0.1:8080
#   BIOMA_AGENTS=5000 BIOMA_PORT=8080 python nervous_system_server.py
```
The Rust `StressTester` floods in a background thread (GIL released), FastAPI
streams `obter_estado_sistema_nervoso()` at 10 Hz, and the page renders it live.

## Stress engine & telemetry (nervous-system metrics)
`StressTester` spawns 1k–10k concurrent **Tokio** micro-agents that flood the bus
and force apoptosis under load.  The telemetry collector is a lock-free atomic
core; its sampling thread is **pinned to an isolated CPU core** (`core_affinity`)
and Tokio workers take the remaining cores, so monitoring never distorts the
measured latency.

```python
import bioma_kernel as bk
t = bk.StressTester(num_signals=16, max_agents=5000)
metrics = t.run(num_agents=5000, duration_secs=30)     # releases the GIL
state = t.obter_estado_sistema_nervoso()               # snapshot for React/D3:
#   { agentes_ativos, densidade_hormonal, latencia_comunicacao_us, latencia_p99_us,
#     tokens_salvos_apoptose, sinais_processados, apoptosis_events,
#     concentracao_por_sinal:[...], nos:[{id, brilho}, ...] }
```

### Measured (this machine · 5,000 agents × 30 s)
| Metric | Value |
|---|---|
| Hormone signals processed | **62.9 M** |
| Throughput | **2.1 M signals/s** |
| Avg communication latency | **5.0 µs** (p99 19 µs) |
| Apoptosis events | **981 k** |
| Tokens saved by apoptosis | **5.25 M** |
| Hormonal density (steady-state) | ~59.6 k |

> Honest note: the **~5 µs** figure is under **5,000-way contention** on the
> shared atomic cells — vs ~0.15 µs single-threaded. That is the real cost of
> shared-state concurrency, still firmly in the microsecond regime. The `max`
> latency shows rare tens-of-ms scheduling outliers (task descheduling), which is
> why the report leads with avg + p99, not max.

## Build
```bash
cd bioma_kernel
pip install maturin
pip install .            # compiles the Rust extension (release + LTO) and installs it
python app.py            # runs the demo
# dev loop inside a virtualenv:  maturin develop --release
```
> On Windows, a transient antivirus file-lock can fail the first parallel build
> (`os error 32`) — just re-run; `cargo build --release` warms the cache.

## Measured (this machine · Win / Py 3.12)
- **Hormonal bus hot-path:** ~**306 ns/op** for a `secrete + sense` pair over 500k
  ops — i.e. **~0.15 µs per Python→Rust call**, including the FFI boundary + GIL
  toggle. The pure-Rust op is far below that; the Python boundary is the cost.
- **Context apoptosis:** 32 items → 1 survivor after 6 decay cycles; reduction is
  tunable via the oxygen policy (the demo shows an aggressive 96%; a realistic
  relevance policy lands in the commercial **30–40%** target).

## API
```python
import bioma_kernel as bk

# ---- Hormonal bus ----
bus = bk.HormonalBus(num_signals=32, event_capacity=4096)
bus.secrete(flags: int, intensity: float)      # add intensity to each set signal bit
bus.sense(mask: int) -> float                  # aggregate gradient over masked bits
bus.concentration(bit: int) -> float
bus.tick(decay: float)                         # temporal dissipation (×decay)
sid = bus.subscribe(mask: int, threshold: float)
bus.poll(sid) -> float | None                  # gradient if ≥ threshold, else None
bus.snapshot() -> list[float]
bus.drain_events(max) -> list[tuple[int,float]]
bus.stats() -> dict

# ---- Context apoptosis ----
ctx = bk.StateContext(epsilon=0.05, capacity=256)
ctx.insert(content: str, oxygen=1.0, signal=0) -> int
ctx.decay(rate=0.2, reinforce_mask=0, reinforce_amount=0.0) -> int   # returns #apoptosed
ctx.active_context() -> list[str]              # the pruned window for the LLM
ctx.active_tokens() -> int
ctx.reduction_ratio() -> float                 # fraction of tokens pruned (the FinOps win)
ctx.stats() -> dict
```

## Honest engineering notes
- **Memory safety + concurrency:** the bus uses interior mutability (atomics for
  the lock-free concentration cells; a mutex only for the cold subscription list),
  so every method is `&self`, `Sync`, and runs with the GIL released. No `unsafe`.
- **Zero-cost / no-alloc hot path:** `secrete`/`sense`/`tick` allocate nothing;
  apoptosis compacts the vector in place (`retain`), reusing capacity.
- **What this is / isn't:** it's the local, in-process kernel. It does **not** call
  any LLM — it *reduces* what you later send to one. Wire it under the
  `bioma_orchestrator` (online) or `bioma_engine` (sovereign) layer to cut real
  API context cost.
