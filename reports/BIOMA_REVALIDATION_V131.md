# Post-update A/B revalidation — kernel 1.1.0 + gateway 1.3.1

**Date:** 2026-07-20 · **Real spend:** ~$0.87 total (OpenRouter, cost via `usage.cost`)
**Goal:** repeat the comparative A/B benchmark on the "purpose context" updates
(cache-aware apoptosis, `effort_gauge`, `BIOMA_AUTO_EFFORT`) and measure the new
lever (dynamic thinking budgets), which until then was only projected.

## 1. Integrity (free, offline)

- Local suites: kernel + gateway + firewall + efficiency → **40/40 passed**.
- `run_benchmark.py --mock`: pipeline intact on kernel 1.1.0 (~85% reduction
  visible in the integration pass; mock success rates are meaningless by design).

## 2. Paired A/B pilot (paid) — the comparative benchmark repeated

4 models × 5 tasks × 1 rep × 2 arms = **40 real calls** via OpenRouter
(`benchmarks/ab-publico/results/rerun_v131.jsonl`). Same harness as the public
1,440-call dataset; arm B uses `CognitiveFirewall.shield` → kernel **1.1.0**.

| Metric | v1.3.1 pilot (20 pairs) | Published reference (720 pairs) |
| :--- | ---: | ---: |
| Input reduction (median) | **−82.2%** | −83.8% |
| Input reduction (min–max) | −80.8% … −85.8% | — |
| Success parity | **17 both-ok · 3 both-fail · 0 divergent** | aggregate parity |
| Real billed cost | **−65.0%** ($0.274 → $0.096) | — |
| Kernel latency | median **1.1 µs** (max 2.7 µs) | ~1 µs |

Reading: kernel 1.1.0 **reproduces** the published result within the expected
noise of a pilot (Δ 1.6 p.p. on the median with 36× smaller N). No pair where
the baseline solved and BIOMA didn't — the only failing task
(`py-token-bucket`) failed in both arms on 3 of the 4 models (task difficulty,
not pruned context; on claude-opus both arms solved it).

Models: claude-haiku-4.5, deepseek-v4-flash, gpt-5.4-mini, claude-opus-4.8.

## 3. Auto-effort × real thinking (paid) — NEW measurement

The release's evidence gap: the dynamic-thinking-budget gain was projected
(30–60%), not measured. Experiment
(`tests/measure_auto_effort.py`, data in `results/auto_effort.json`):

- Workload: 10 turns, realistic calibration mix (7 trivial / 3 hard),
  claude-haiku-4.5, same context and order in both arms.
- **Arm A (naive agent):** direct to OpenRouter, every turn with
  `reasoning={"max_tokens": 4000}` (fixed budget — the common
  "thinking on, set and forget" agent pattern).
- **Arm B (BIOMA):** via the gateway with `BIOMA_AUTO_EFFORT=1`, no reasoning
  param — the `effort_gauge` decides per turn.

| Total (10 turns) | A (naive, fixed budget) | B (BIOMA auto-effort) |
| :--- | ---: | ---: |
| reasoning tokens | 6,174 | **670** |
| output tokens (total) | 31,447 | 27,501 |
| real cost | $0.1588 | **$0.1388** |

**Reasoning tokens: −89%. Total cost: −13% on this mix.**

Mechanics confirmed in the JSONL audit: the 7 trivial turns became
`{"enabled": false}` (0 thinking tokens) and the 3 hard turns kept reasoning
with a per-tier budget. The decision cost ~1 µs per request.

### Honest caveats

1. The −13% cost (vs −89% reasoning) is because *responses* dominate the output
   in this workload — the model answered at length even on trivial turns. In
   workloads where thinking dominates the output (agents with 16k+ budgets),
   the saved fraction trends toward the reasoning number.
2. Quality was not gated in THIS experiment (it is a cost-mechanics
   measurement); hard turns hit the `max_tokens` ceiling in BOTH arms.
   → **closed in §4.3**: same design with a pytest gate, 0 divergent pairs.
3. A pilot is a pilot: N=20 pairs on the A/B and N=10 turns on auto-effort. The
   numbers match the large dataset, but the full re-run (1,440 calls, ~$30–60)
   is the next step when budget allows.

## 4. Output-QUALITY validation (addendum 2026-07-20, ~$0.20)

Three layers, all with objective gates (never an LLM judge):

**4.1 The §2 A/B re-analyzed per pair.** All 40 runs used the EXECUTABLE gate
(pytest over the generated code — the suite's strongest): **0/20 divergent
pairs**. In no case did the baseline deliver and BIOMA not.

**4.2 Chat probes (`test_quality_preservation.py`, kernel 1.1.0).** Exact
values planted in a long, noisy session; the final answer must contain them.
3 models (Sonnet 5, Haiku 4.5, DeepSeek V4) × 3 scenarios:

| Scenario | baseline | BIOMA | tokens |
| :--- | ---: | ---: | ---: |
| S1 facts tagged FACT (designed usage) | 100% | **100%** | −97.2% |
| S2 info in recent turns | 100% | **100%** | −97.3% |
| S3 OLD untagged fact (by-design limit) | 100% | 0% | −97.9% |

Parity **6/6** on the contract scenarios; S3 is the documented, expected
degradation (durable information must be tagged `FACT` — the product's honest
contract, not a bug).

**4.3 Auto-effort with an executable gate (`measure_auto_effort_quality.py`).**
Closes the §3 caveat: 5 real tasks with the pytest gate, IDENTICAL context in
both arms (apoptosis off via `BIOMA_SAFE_THRESHOLD=0` to isolate the thinking
variable), arm A with a fixed 4000 budget vs arm B with auto-effort:

| Metric | Result |
| :--- | :--- |
| Parity (pytest) | **4 both-ok · 1 both-fail · 0 divergent** |
| reasoning tokens | 2,352 → 844 (**−64%**) |
| real cost | $0.0453 → $0.0379 (−16%) |

The gauge disabled thinking on 3 of the 5 tasks and **all of them still passed
the gate** — thinking was pure waste on those tasks. The only both-fail is
`py-token-bucket`, which fails in both arms across the whole pilot (task
difficulty). Data: `results/auto_effort_quality.json`.

**Quality conclusion:** on every layer with an objective gate, what was asked
via chat was delivered with EQUAL quality with and without BIOMA — 0 divergent
pairs across 25 executable comparisons + 6/6 on the contract probes. The only
existing degradation (S3) is the product's documented limit, reproduced on
purpose to keep it honest.

## 5. Verdict

The update **regressed nothing** (reduction and parity reproduced, kernel in
the same latency class) and **added a measured lever**: −89% reasoning tokens
on a realistic mix, with an auditable per-request decision. Both LLM cost
phases now have a measured number: input −82% (pilot, consistent with the
published −84%) and reasoning −89% (new).
