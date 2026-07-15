# Frugal by Payload — B.I.O.M.A. as a Client-Side Frugal-AI Layer

**🌐 English · [Português](FRUGAL_AI_WHITEPAPER.pt-BR.md)**

> Whitepaper aligned with the AFNOR SPEC 2314 frugal-AI framework. Every measured
> number below has a reproducible script and a versioned report in this repository;
> every estimated number carries declared coefficients and explicit bounds.

## Official claim (scope declared)

B.I.O.M.A. is a **client-side Frugal-AI layer that auditably reduces the energy
cost of LLM inference per deployment**. It is not a global-impact claim: the
effect scales with adoption and with the operator's grid. The official KPI is
**energy per token**; its reduction percentage is exact and coefficient-independent,
because it is derived from the kernel's own per-dispatch token audit.

## 1. Problem

Inference — not training — dominates the lifecycle energy of production models
(~80–90% of compute), and agentic workloads multiply tokens per task by up to
three orders of magnitude, mostly by **resending context on every step**. The
fastest-growing component of AI's energy bill is therefore redundant input
payload — dead weight that the application layer controls and the provider
cannot remove.

## 2. Method

**Context apoptosis** (Rust micro-kernel, 0.8–1.6 μs per dispatch, in-process):
each history block gets a metabolic weight by class; a recency half-life decays
it; blocks below the safe threshold are purged before dispatch. Durable classes
(`SYSTEM`, `FACT`) are never purged; the current query never enters the filter.
The same pass powers the cognitive firewall (secret redaction, flood detection,
timeout guard). The layer is model-agnostic: it hardens the payload, not the model.

**Usage contract** (verified in §4): durable information must be tagged `FACT`
or live in recent turns; stale untagged turns are purged by design.

## 3. Measurement methodology

- **Baseline = same prompt, same model, no dehydration** — the only variable is
  the apoptosis filter.
- **Quality by objective probes**: exact values planted in the history and
  checked in the answer (no LLM judge), temperature 0.
- **Tokens and cost from the provider's real usage** (OpenRouter), not price sheets.
- **Energy measured on hardware**: local model (Ollama, Llama 3.2 1B), battery
  fuel gauge at 2 Hz, idle baseline subtracted, interleaved arms.
- **Conversion to Wh/gCO2e is an estimate, kept separate from measurements**,
  with declared literature coefficients and low/mid/high bounds (`bioma/esg.py`).

## 4. Measured results (ground truth)

| Layer | Without B.I.O.M.A. | With B.I.O.M.A. | Reduction | Source |
|---|---|---|---|---|
| Input tokens / dispatch (6 online models) | 1,605–2,489 | 63–280 | −84 to −96% | `reports/BIOMA_UNIVERSAL_GAINS.md` |
| 16-round session, cumulative input | 47,890 | 2,022 | −95.8% | `tests/test_enxuto_efficiency.py` |
| Answer quality (probes, 5 models, S1+S2) | 100% | 100% | 10/10 parity | `reports/BIOMA_QUALITY_PRESERVATION.md` |
| Prefill compute (local hardware) | 411.1 s | 1.8 s | −99.6% | `reports/BIOMA_ENERGY_LOCAL.md` |
| **Marginal energy / dispatch (measured)** | **2,714.7 J** | **69.5 J** | **−97.4%** | `reports/BIOMA_ENERGY_LOCAL.md` |
| Secrets leaked to provider | 6/6 | 0/6 | contained | `reports/BIOMA_IMMUNITY_VERDICT.md` |

The measured energy reduction (−97.4%) tracks the token reduction (−97.2%)
almost 1:1 — validating, by direct measurement, the tokens↔energy
proportionality that the estimation layer assumes.

## 5. Estimation layer (declared coefficients)

`tests/test_esg_benchmark.py` → `reports/BIOMA_ESG_BENCHMARK.md` converts the
measured savings using 0.5–1.3 kWh/M tokens (mid 0.9; consistent with Epoch AI's
~0.3 Wh/query), grid presets (world 445, EU 230, US 385, BR 100 gCO2e/kWh), and
an honest caching-adjusted counterfactual (a cache hit is not a saving we claim).
Illustrative deployment (100k dispatches/day, long-session load): **52–136 MWh/yr
avoided (mid 94)** ≈ 42 tCO2e on the world grid — dropping to ~31 MWh under
aggressive caching. Our own hardware point (0.10 kWh/Mtok, marginal, 1B model)
sits below the frontier-inference range, as expected; it bounds the small-model
case and does not inflate the claim.

## 6. Alignment with AFNOR SPEC 2314 (frugal-AI framework)

| Frugal principle | B.I.O.M.A. practice | Evidence |
|---|---|---|
| Resource efficiency with maintained performance | −80–97% input tokens with 100% probe parity | §4 |
| Measure before claiming | per-dispatch kernel audit; hardware energy bench | §3–4 |
| Declared estimation methodology | bounded coefficients, caching counterfactual | §5 |
| Transparency & communicability | versioned reports, CI, raw run data (`reports/energy_local_runs.jsonl`) | repo |
| Accessibility / low barrier | client-side, model-agnostic, no provider lock-in, runs offline | §2 |

## 7. Declared limits

Stale untagged turns are purged by design (the contract: tag durable info as
`FACT`). One provider endpoint (Claude Fable 5 via OpenRouter) was excluded from
the quality suite (`content_filter` on both arms). Grok 4.5 showed −84% tokens
with unchanged API-reported cost. The layer does not touch training, image/video
generation, output tokens, or embodied hardware carbon. Efficiency can induce
more usage (Jevons); the per-dispatch audit exists precisely so operators can
report both sides. Laptop-CPU energy values do not transfer to datacenter GPUs —
the ratio does.

## 8. Reproducibility

All scripts live in `tests/`; all reports in `reports/`; unit tests (including
the ESG conversion) run in CI on every push. Key commits: quality suite
`43927a0`, energy bench `7ac8d57`, ESG KPI `9bfda63`.
