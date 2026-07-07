# B.I.O.M.A. — Technical Performance Dossier

**Version 1.0** · generated 2026-07-07T14:35:04Z · built in 23.4s

> **Provenance.** The M8 certification is read from its persisted certificate; every other figure is **re-run live** by `build_dossier.py`. Latency, throughput, token counts and speedup are **measured** (Rust + psutil + gc). Dollar figures are a **calculation** at $3/1M input tokens — **no external model is called** (the stack is offline/autarkic).

## Executive summary

| Capability | Proven result | Evidence |
|---|---|---|
| Neuronal mitosis (speed) | **4.01× faster** · 579.4ms → 144.6ms | measured |
| Hormonal bus (throughput) | **1.77M signals/s** @ 6.037µs | measured |
| Context apoptosis (FinOps) | **−39.6% tokens** · $3,744.0/1M req | measured + calc |
| Orchestration (quality) | **99.8% coverage lift** vs monolithic | measured |
| Sovereign core (certified) | **ACCEPTED** · 10/10 criteria | M8 cert |
| Accuracy under parallelism | **5/5 vs 5/5** — identical to ground truth | measured |

## 1 · Sovereign engine — M8 acceptance

- Verdict: **ACCEPTED** (10/10 critical criteria).
- Mitosis → coverage: **Δ 0.4961**, Cliff δ = 1.0 (perfect separation).
- Bus → cascade recovery: **Δ 0.2468**, Cliff δ = 1.0.
- CSR: **1.0** (Wilson LB 0.903578, N=36 births) · leak-free soak (slope -0.73069 MB/cyc, gc-live 0).
- Mitosis decision: precision 1.0, accuracy 1.0.
- Source: `bioma_engine/M8_CERTIFICATE.json`

## 2 · Neuronal mitosis — E2E speed & accuracy

- **4.01× speedup**: 579.4ms (linear) → 144.6ms (BIOMA) over 20 child nodes on 12 cores.
- **Accuracy preserved**: 5/5 vs 5/5 — identical to ground truth. Parallelism does not corrupt the result.
- Context per call cut **−59.1%** by apoptosis before duplication.
- Source: `live · bioma_kernel.MitosisBenchmark (5 tasks × 1.5M keyspace)`

## 3 · Rust kernel — stress under load

- **1.77M signals/s** (7,070,744 signals from 2,000 concurrent agents in 4s).
- Communication latency **6.037µs** under contention.
- **542,313 tokens** apoptosed under load.
- Source: `live · bioma_kernel.StressTester (2,000 agents × 4s)`

## 4 · Context apoptosis — FinOps

- Single window: **−39.6%** input tokens (3149 avg) → **$3,744.0 / 1M requests**.
- Multi-turn session: **−70.0%** → **$13,225.2 / 1M calls**.
- Kernel backend: **rust** · Source: `live · bioma_orchestrator.finops_benchmark`

## 5 · Orchestration — quality & economy

- Multi-agent coverage **0.9923** vs monolithic **0.4966** (**+99.8%**); cascade lift +0.4304.
- Verified code optimizations: **6/6** · mean speed-up 99.83% · token savings 100.0% (deterministic, local).
- Result-quality tuning: cascade **0.2762 → 0.6519** (+0.3757) at coordination γ=0.9.
- Source: `live · bioma_engine.benchmark_orchestration`

## 6 · Autonomy & test coverage

- Sovereign core: **FULLY AUTONOMOUS** · network required to run core: False.
- Automated tests green: **89** (78 engine + 11 orchestrator) · Rust: `cargo check`/`build --release` clean, no `unsafe`.

## Honesty appendix

- **Measured**: mitosis speedup, bus throughput/latency, token reduction, RSS/leak, coverage/cascade (Rust + psutil + gc + analytic ground truth).
- **Calculated**: dollar figures, at $3/1M input tokens. No external model was ever called — the stack is offline/autarkic.
- **Bounds**: kernel latency rises from ~0.15µs single-thread to a few µs under thousands-way contention; mitosis speedup is bounded by core count; token savings depend on context noise (composition stated per benchmark).

## Reproduce

```bash
python -m bioma_engine.certify_m8            # M8 certificate
python -m bioma_engine.benchmark_orchestration
python -m bioma_orchestrator.finops_benchmark
cd bioma_kernel && python stress_benchmark.py && python bioma_vs_traditional.py
python build_dossier.py                      # regenerate this dossier
```
