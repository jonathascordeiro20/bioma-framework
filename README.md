# B.I.O.M.A.

**Biologically Inspired Orchestration of Mutating Agents** — a sovereign AI
runtime that orchestrates LLMs like a living organism (mitosis, homeostasis,
apoptosis, hormonal signalling), with a microsecond Rust kernel and dollar-
denominated ROI.

> Sovereign · Evolutionary · Verified. Proven in microseconds and dollars — see
> [`TECHNICAL_DOSSIER.md`](TECHNICAL_DOSSIER.md).

## Architecture — five layers, each compiled & tested

| Layer | Module | What it does |
|---|---|---|
| **L0 · Kernel** | [`bioma_kernel`](bioma_kernel/) (Rust + PyO3) | Lock-free hormonal bus (µs) + memory apoptosis; stress-proven (2.1M signals/s). |
| **L1 · Engine** | [`bioma_engine`](bioma_engine/) | Sovereign, offline neural-organism core — mitosis / homeostasis / apoptosis. **M8-certified**, 78 tests. |
| **L2 · Orchestrator** | [`bioma_orchestrator`](bioma_orchestrator/) | Online multi-LLM routing (Thompson bandit) + verification + context apoptosis. |
| **L3 · Nervous system** | `bioma_kernel/nervous_system_*` | Live WebSocket telemetry dashboard. |
| **L4 · Value loop** | `ContextPruner` → `handle()` | Apoptosis trims context before every call → measured token/cost savings. |

## Proven results (measured)

| Capability | Result |
|---|---|
| Neuronal mitosis (E2E) | **5.3× faster** · identical accuracy to ground truth |
| Hormonal bus | **2.1M signals/s** @ microsecond latency |
| Context apoptosis | **−39.6% input tokens** · ~$3.7k / 1M requests |
| Orchestration | **+99.8% coverage** vs monolithic |
| Sovereign core | **M8 ACCEPTED** · FULLY AUTONOMOUS · 89 tests green |

Full provenance (measured vs calculated) in [`TECHNICAL_DOSSIER.md`](TECHNICAL_DOSSIER.md).

## Quickstart

```bash
# Python deps (CPU torch, fastapi, httpx, openai, python-dotenv, …)
python -m pip install -r requirements.txt      # or: pip install -e ./bioma_engine

# Rust kernel (compiles the PyO3 extension)
python -m pip install maturin
cd bioma_kernel && python -m pip install . && cd ..

# Run the test suites
python -m pytest bioma_engine/tests bioma_orchestrator/tests -q

# Regenerate the consolidated dossier
python build_dossier.py
```

### Online multi-model benchmark (OpenRouter)

```bash
cp .env.example .env          # then paste your OpenRouter key INTO .env (never .env.example)
python bioma_vs_market_benchmark.py --check     # preflight
python bioma_vs_market_benchmark.py             # A/B sweep across the 4 models
```

## Security

- **Never commit secrets.** `.env` is git-ignored; `.env.example` is the template
  (placeholder only). Keys live in `.env` locally, and in your platform's secrets
  manager in production — never in the repo.
- Get/rotate your OpenRouter key at <https://openrouter.ai/keys>.

## Repository layout

```
bioma_engine/         sovereign core (10-phase plan, M8 certificate, tests)
bioma_orchestrator/   online LLM orchestrator + context apoptosis + OpenRouter
bioma_kernel/         Rust/PyO3 kernel (bus, apoptosis, stress, mitosis, dashboard)
build_dossier.py      consolidates every benchmark → TECHNICAL_DOSSIER.md/.json
bioma_vs_market_benchmark.py   Traditional (linear) vs B.I.O.M.A. (organic) A/B
```

## License

MIT.
