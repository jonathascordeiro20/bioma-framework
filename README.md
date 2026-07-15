# B.I.O.M.A.

**🌐 English · [Português](README.pt-BR.md)**

[![CI](https://github.com/jonathascordeiro20/bioma-framework/actions/workflows/ci.yml/badge.svg)](https://github.com/jonathascordeiro20/bioma-framework/actions/workflows/ci.yml)
[![License: FSL-1.1-MIT](https://img.shields.io/badge/license-FSL--1.1--MIT-blue.svg)](LICENSE)
![Built with Rust + Python](https://img.shields.io/badge/built%20with-Rust%20%2B%20Python-orange.svg)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Tokens saved: up to 97%](https://img.shields.io/badge/tokens%20saved-up%20to%2097%25-success.svg)

**A local, provider-agnostic efficiency & security micro-kernel for LLM applications.**

<p align="center">
  <img src="assets/bioma-concept-map.png" width="760"
       alt="B.I.O.M.A. concept map: what it is, its three mechanisms (context apoptosis, cognitive firewall, hormonal bus), what it honestly generates, and why sovereignty depends on where the model runs.">
</p>

B.I.O.M.A. is a drop-in artifact — a lock-free Rust kernel (`bioma_micro`) plus a
thin Python layer — that you embed in *any* project or architecture that talks to an
LLM. It does not try to make the model "smarter". It makes the *processing* cheaper,
faster and safer, in-process, before your prompt ever leaves the machine:

- **Context apoptosis** — dehydrates wasted/stale context (−80% input tokens; up to
  −97% on long sessions).
- **Cognitive firewall** — secret redaction, cognitive-DDoS/flood detection, and a
  dispatch timeout guard.
- **Hormonal bus** — lock-free μs signalling substrate (~2M signals/s).

100% local. Provider-agnostic: harden the payload here, then send it to **Anthropic,
Google, OpenAI** — or anything — with *your* SDK.

> **New here?** [`OVERVIEW.md`](OVERVIEW.md) explains what B.I.O.M.A. is, the pain it
> attacks, and the real benchmarks as proof. Step-by-step deployment (local & online
> providers) is in [`IMPLEMENTATION.md`](IMPLEMENTATION.md). Every claim is measured and
> audited in [`FINDINGS.md`](FINDINGS.md), including what we tested and **refuted** (multi-LLM
> "mitosis" does not improve quality — it is not part of the product).

## Use it as a library (any provider)

```python
from bioma.firewall_client import CognitiveFirewall

fw = CognitiveFirewall(vault={"db_password": DB_PW})   # secrets to protect

# (a) PURE artifact — harden, then call YOUR provider with YOUR SDK:
h = fw.shield(history, "refactor this function")
#   h.prompt / h.system  → clean, dehydrated, secret-free payload
#   h.telemetry          → saturation, red_alert, apoptosis_reduction, kernel_latency_us

import anthropic                                        # or google.genai, or openai
msg = anthropic.Anthropic().messages.create(
    model="claude-sonnet-5", max_tokens=1024,
    system=h.system or "", messages=[{"role": "user", "content": h.prompt}])

# (b) Bring your own async dispatcher (Anthropic/Google/OpenAI), keep the guards:
shield = await fw.harden(history, "refactor", dispatch_fn=my_async_provider_call)
#   → timeout guard + response-side secret redaction applied automatically
```

The Rust kernel is usable directly too:

```python
import bioma_micro as k
k.dehydrate([("system rules", k.SYSTEM), ("verbose log " * 200, k.TOOL)])  # → -80% tokens
k.saturation_scan(payload)     # cognitive-DDoS score 0..1 (flood ≈ 1.0)
```

## Proven results (ground truth)

| Capability | Result | Source |
|---|---|---|
| Context apoptosis | **−80% input tokens** (up to −97% long sessions) | `tests/test_enxuto_efficiency.py` |
| Answer-quality preservation | **10/10 parity, 100% correct answers at −97% tokens** (5 online models, objective probes) | `tests/test_quality_preservation.py` · `reports/BIOMA_QUALITY_PRESERVATION.md` |
| Measured energy per dispatch | **2,714.7 J → 69.5 J (−97.4%)**, quality parity (local Llama 3.2 1B, battery fuel gauge, idle subtracted) | `tests/test_energy_local.py` · `reports/BIOMA_ENERGY_LOCAL.md` |
| Vision context apoptosis (agent screenshot loops) | **6/6 parity, 100% correct at −56% real tokens** (−77% at 24 steps; dehydrated payload is O(1) in session length) — 3 vision models, probes rendered into the pixels | `tests/test_vision_quality_preservation.py` · `reports/BIOMA_VISION_QUALITY.md` |
| Image distillation (keep-latest dedup + OCR + deterministic shape structure) | **100% answers at −74% tokens vs sending every image** — stale images become ~25–86-token text blocks; local VLM captions measured and rejected (label confabulation) | `tests/test_vision_distill.py` · `reports/BIOMA_VISION_DISTILL.md` |
| Dev-workload cost benchmark (7 agent models, real OpenRouter usage & prices) | **−57% to −86% median cost at quality parity** — 126 real executions, paired replicas, failures reported first-page (Fable 5×T1 arm-B empty 3/3) | `tests/benchmark_dev_openrouter.py` · `resultados/relatorio.md` · `resultados/SIMULACAO_MERCADO.md` |
| Drop-in gateway (OpenAI-compatible, cache-safe, tool-pair aware) | **−78% billed input tokens, answer intact** with only `base_url` changed — proven with the official OpenAI SDK on real models | `bioma/gateway.py` · `tests/test_gateway.py` · `tests/prove_gateway_dropin.py` |
| Apoptosis × prompt caching (real Anthropic cache) | **−65% net cost after the cache discount** — the durable prefix hits the *same* cache in both arms; savings come from purging the never-cacheable middle | `tests/measure_cache_interaction.py` · `resultados/MEDICOES_GATEWAY.md` |
| E2E real tool-calling agent (fixes a real bug to green pytest) | **−84% accumulated input tokens at task parity** on a long-running agent (−0% on a 3-turn task — apoptosis is a correct no-op with no dead weight) | `tests/e2e_agent_gateway.py` · `resultados/MEDICOES_GATEWAY.md` |
| Hormonal bus | **~2M signals/s @ ~5μs**, bounded under 10× load | archived bench (research repo) |
| Cognitive-DDoS mitigation | 15k-token flood → dehydrated pre-dispatch | `tests/test_sovereign_defense.py` |
| Secret redaction | vault values never reach the model | `reports/BIOMA_IMMUNITY_VERDICT.md` |

## Drop-in gateway — apoptosis with zero code changes

Point any OpenAI-compatible client's `base_url` at the gateway and every request
gets context apoptosis transparently — no SDK swap, no prompt rewrite:

```bash
pip install fastapi "uvicorn[standard]" httpx
uvicorn bioma.gateway:app --port 8790
```

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8790/v1", api_key="...")  # the only change
```

Proven drop-in (`tests/prove_gateway_dropin.py`, official OpenAI SDK, real
models): billed input tokens **−78%** on Sonnet 5 / GLM-5.2 / Gemini 3.5 Flash,
answer intact, streaming works, one audit line written per request. Design
guarantees (each unit-tested in `tests/test_gateway.py`): the current query is
never filtered; the surviving `system`+`FACT` prefix stays **byte-identical**
across calls (prompt-cache-safe); `tool_call`/`tool` pairs survive or purge as a
unit (never orphaned). The Anthropic `/v1/messages` surface (Claude Code E2E) is
the next iteration.

## Frugal AI — the official KPI: energy per token

B.I.O.M.A. is a **client-side Frugal AI layer that auditably reduces the energy
cost of LLM inference per deployment**. The kernel's per-dispatch audit
(tokens before/after) *is* the KPI: the reduction percentage is exact and
coefficient-independent. A reproducible benchmark (`tests/test_esg_benchmark.py`
→ `reports/BIOMA_ESG_BENCHMARK.md`) converts the measured token savings into
bounded Wh/gCO2e estimates using declared literature coefficients
(0.5–1.3 kWh/M tokens; grid presets; caching-adjusted counterfactual), with the
conversion helpers shipped in `bioma/esg.py`. This is a per-deployment claim —
not a global one; it scales with adoption and with your grid.

## Quickstart (local)

```bash
# Build & install the Rust micro-kernel (PyO3 extension)
python -m pip install maturin
cd bioma_micro && maturin build --release && \
  pip install --force-reinstall target/wheels/bioma_micro-*.whl && cd ..

# Run the test suite (offline, deterministic)
pip install pytest fastapi "openai>=1"
python -m pytest tests/test_kernel.py tests/test_firewall.py tests/test_server.py -q
```

Optional: a local FastAPI runner (`bioma.server`, `GET /health` + `POST /v1/dispatch`)
and a local container image (`deploy/Dockerfile.lean`) are included — no hosted
service required.

## Layout

```
bioma_micro/   Rust/PyO3 micro-kernel — hormonal bus + apoptosis + saturation_scan
bioma/         Python: CognitiveFirewall, LeanOpenRouterClient, local server
tests/         unit suite (kernel, firewall, server) + real end-to-end validations
FINDINGS.md    ground-truth evaluation (proven / refuted), reproducible
reports/       immunity verdict (APT war-game)
```

## License

Fair-source under the **Functional Source License (FSL-1.1-MIT)** ([`LICENSE`](LICENSE)):
read it, run it, and build on it for any non-competing purpose. The only limit is repackaging
it as a competing product, and each release automatically becomes MIT two years after its date.
