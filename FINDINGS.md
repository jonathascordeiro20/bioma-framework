# B.I.O.M.A. — Empirical Findings (ground-truth evaluation)

> Honest, reproducible evaluation of every B.I.O.M.A. mechanism against real data.
> Written to survive technical due diligence: it states what is **proven**, what is
> **refuted**, and what remains a **design goal**. Numbers below are measured, not
> asserted. Where a claim did not hold up, it is marked as such.

## TL;DR

- 🟢 **Context apoptosis (−78–80% input tokens) is the real, universal, sellable win.** Every model, every task.
- 🟢 **The Rust kernel is genuinely fast and resilient**: ~2M signals/s at ~5μs mean latency, latency stays **bounded under 10× load**.
- 🔴 **Multi-LLM mitosis+synthesis does NOT improve answer quality or security remediation.** On ground-truth executed tests it was **neutral on frontier models (ceiling) and harmful on weaker ones** (synthesis corrupts correct answers). Even the **corrected best-case design** (verified cross-model selection, baseline-in-pool) delivered **+0** on hard security tasks. This thesis is **refuted** by our own data across three independent experiments and is **not** part of the honest pitch.
- ✅ **Positioning:** B.I.O.M.A. makes AI processing *viable, sustainable, and resilient* — an **efficiency/infrastructure layer**, not a system that makes AI "smarter."

---

## The evidence ledger

| Claim | Status | Basis |
| :--- | :--- | :--- |
| Context apoptosis cuts ~80% of input tokens | 🟢 **Proven** | Measured in every run (`ContextPruner`, kernel-backed) |
| Kernel sustains 10k concurrent agents at μs latency | 🟢 **Proven** | `bioma_kernel_loadtest.py` |
| Kernel latency stays bounded under 10× load | 🟢 **Proven** | avg 4.5μs→5.0μs (1.1×), p99 21μs→15μs |
| Mitosis+synthesis improves quality | 🔴 **Refuted** | Objective code eval: 95%→83% (−17 tests) |
| Mitosis improves security remediation | 🔴 **Refuted** | Defense eval: baseline 98% ≥ synthesis 90% = selection 90% |
| Verified cross-model selection improves security (corrected best-case design) | 🔴 **Refuted** | +0 vs best single-shot; all models 100% on hard tasks (no headroom) |
| "Selection-by-execution is provably ≥ baseline" | 🟢 **Corrected & validated** | With the baseline **in the pool** it held exactly (30/30 = 30/30, monotonic) — but delivered +0 |
| Resilient "at industrial level" (end-to-end system) | 🟡 **Goal** | Kernel primitive proven; full system not load-tested |

---

## Experiments & results

All LLM calls go through OpenRouter (`bioma_orchestrator/openrouter_async.py`) with
exponential backoff. "Real" = a valid `sk-or` key; otherwise a clearly-labelled
deterministic mock. Quality was measured two ways: a noisy LLM judge (early runs)
and — decisively — **objective execution against test suites** (no judge).

### 1. Context apoptosis — 🟢 the universal win
`ContextPruner` (Rust `StateContext` oxygen/decay, Python fallback) prunes a bloated
agent context before the model call. Measured reduction: **−78% to −80%** of input
tokens, consistent across GPT-4o, Fable-5, Opus 4.8, Grok-4.3, Llama-3.3-70B and on
every task. This is the one mechanism that helps unconditionally (cost + focus),
including on frontier models. *Repro:* any of the sim scripts print `apoptose −80%`.

### 2. Kernel resilience — 🟢 proven (`bioma_kernel_loadtest.py`)
1k → 10k concurrent Tokio micro-agents flooding the lock-free hormonal bus, with
live apoptosis on a CPU-pinned telemetry core (12-core host):

| Concurrent agents | Throughput | Mean latency | p99 latency |
| ---: | ---: | ---: | ---: |
| 1,000 | 2.31 M sig/s | 4.54 μs | 21 μs |
| 2,500 | 1.75 M sig/s | 6.04 μs | 20 μs |
| 5,000 | 1.84 M sig/s | 5.76 μs | 27 μs |
| 10,000 | 2.12 M sig/s | 4.99 μs | 15 μs |

Under **10× load**, mean latency moved only 4.5→5.0μs (1.1×) and p99 *improved*.
**Defensible claim:** *"the sovereign kernel sustains 10,000 concurrent agents at
~2M signals/s with bounded ~5μs latency."* Caveat: `max` latency shows 10–37ms tail
spikes = OS scheduling on a non-realtime OS (userspace); mean/p99 are the meaningful
bounded metrics. Scope = the kernel primitive, not an end-to-end LLM system.

### 3. Objective code correctness — 🔴 mitosis refuted (`bioma_objective_eval.py`)
5 edge-case-heavy algorithmic tasks, **144 hidden tests**, code executed in an
isolated subprocess (no judge). Baseline (1 call) vs B.I.O.M.A. forced mitosis:

| Model | Baseline | B.I.O.M.A. mitosis | Δ |
| :--- | :---: | :---: | :---: |
| GPT-4o | 48/48 (100%) | 48/48 (100%) | 0 (ceiling) |
| Grok-4.3 | 48/48 (100%) | 48/48 (100%) | 0 (ceiling) |
| Llama-3.3-70B | 41/48 (85%) | 24/48 (50%) | **−17** |
| **Aggregate** | **137/144 (95%)** | **120/144 (83%)** | **−17** |

**Smoking gun:** Llama `is_valid_number` went **17/17 → 0/17** — the model was correct
single-shot, and the **LLM synthesis of 3 hypotheses corrupted the correct answer.**
This is the mechanism of harm: blind synthesis has no ground truth and can merge a
flawed hypothesis over a correct one.

### 4. Multi-model efficiency (LLM judge) — mitosis neutral-to-negative (`bioma_efficiency_simulation.py`)
Neutral algorithmic task, 5 models, judge = gpt-4o-mini (noisy ±5):

| Model | Quality Base→BIOMA | Cost | Latency |
| :--- | :---: | :---: | :---: |
| GPT-4o | 90→85 | $0.006→$0.024 | 7→10s |
| Fable-5 | 95→100 | $0.045→$0.302 | 12→45s |
| Opus 4.8 | 95→95 | $0.031→$0.152 | 19→44s |
| Grok-4.3 | 95→95 | $0.003→$0.010 | 9→17s |
| Llama-3.3-70B | 95→90 | $0.0003→$0.001 | 15→114s |

Aggregate: **−1.0 pt quality, 5.7× cost.** Most deltas are within judge noise. On
tasks frontier models already solve there is no headroom for mitosis to help.
*Engineering note:* an earlier run mis-attributed a −25 Opus "regression" and a
Fable-5 failure to B.I.O.M.A. — both were bugs: a low `max_tokens` truncated verbose
models and starved reasoning models; Fable-5 also tripped its **content filter** on a
security-flavoured task. Fixed (2048/2560 token budgets, staggered fan-out, neutral
task). After the fix the results are the honest ones above.

### 5. Security remediation — 🔴 mitosis no gain (`bioma_defense_eval.py`)
3 vulnerabilities (unsafe eval, SQL injection, command injection), **17 executed
security/functionality checks**, benign-by-construction (no shell exec, no I/O).
Baseline vs synthesis vs **selection-by-execution**:

| Model | Baseline | Synthesis | Selection |
| :--- | :---: | :---: | :---: |
| GPT-4o | 17/17 | 17/17 | 17/17 |
| Grok-4.3 | 17/17 | 17/17 | 17/17 |
| Llama-3.3-70B | 16/17 (94%) | 12/17 | 12/17 |
| **Aggregate** | **98%** | **90%** | **90%** |

Frontier models: ceiling (all tie). Weak model: **both mitosis arms fell below
baseline.** Llama `build_query` candidates scored **[0,0,0]** — the role-specialised
prompts were worse than the plain baseline prompt for a weak model on a structural
task, and the baseline was **not** in the selection pool.

### 6. Adaptive mitosis — cost-saving works, confidence signal is weak (`live_pipeline.py`)
A scout cell probes difficulty; only low self-confidence escalates to full mitosis.
- ✅ Easy task → **1 call instead of 4** (real cost cut).
- ⚠️ Hard task → GPT-4o self-rated **95** on a lock-free concurrency proof → did not
  escalate. **LLM self-confidence is overconfident**, so it is a weak escalation
  trigger. A robust gate needs a consistency/critic signal, not self-report.

### 7. Corrected mitosis: verified cross-model selection — 🔴 still +0 (`bioma_verified_selection_eval.py`)
The best-case design the analysis pointed to: **baseline-in-pool** (each model's plain
answer is a candidate → selection can't drop below baseline) + **cross-model** diversity
(GPT-4o + Grok-4.3 + Llama-3.3-70B) + **objective verification** (run the checks) as the
selector — never LLM synthesis. Tested on 3 harder security tasks (30 checks: Windows
reserved-name filename sanitizer, open-redirect validator with userinfo/backslash
bypasses, PII masker with separated card numbers):

| Reference | Score |
| :--- | :---: |
| GPT-4o single-shot | 30/30 (100%) |
| Grok-4.3 single-shot | 30/30 (100%) |
| Llama-3.3-70B single-shot | 30/30 (100%) |
| Best single model | 30/30 (100%) |
| **Verified cross-model selection** | **30/30 (100%)** |

**Δ = +0.** Two things are true and both matter: (1) the corrected design *worked as
designed* — selection held exactly at baseline (monotonic, **never worse**); (2) it
delivered **no gain**, because all models hit the **ceiling** even on the harder tasks.
Three independent experiments (§3, §5, §7) now converge on the same verdict: on
well-defined, objectively-verifiable tasks, modern single-shot is already at ceiling, so
mitosis — even in its best-case corrected form — has no headroom to add value, at 6× cost.

---

## Honest corrections we made to our own claims

1. **"Mitosis/orchestration improves answer quality."** Refuted by ground truth.
2. **"Selection-by-execution is provably ≥ baseline."** Overstated. It is ≥ the best
   *candidate*; to be ≥ baseline the baseline generation must be included in the
   candidate pool. Even then, on our tasks it only ties (no headroom).
3. **"Resilient at industrial level / ready for the planet's hardest problems."** The
   kernel primitive is proven resilient; the end-to-end system is not yet load-tested,
   and the security simulation is inert. State it as a design goal, not a result.

---

## Product recommendation

1. **Ship:** context apoptosis (always on) + the μs Rust kernel. Proven, auditable.
2. **Mitosis:** OFF by default. If offered, only as optional escalation with the
   **baseline-in-pool selection** design (guarantees "never worse") — and **without**
   any quality claim.
3. **Position** on efficiency/infrastructure and resilience, not intelligence — the
   only framing the evidence supports.

## Where the mitosis story *could* still earn value (unproven, needs testing)
- Tasks genuinely **beyond a single model's frontier** (our tasks were at ceiling).
- **Objective verification** as the selector (execution/property tests), never blind
  synthesis, with the baseline in the pool.
- **Cross-model** diversity (different providers) instead of same-model temperature —
  same model shares its blind spots.
- Reframe the target from average quality to **tail-failure reduction** (95%→99%),
  which only matters with objective verification.

## Reproducibility

> The harnesses below are **archived in a private research repo** — they depend on the legacy
> multi-LLM orchestrator (`bioma_orchestrator`), removed from the lean product once mitosis was
> refuted. This document preserves the full method and results; the product's own claims
> (apoptosis + firewall) are reproducible from [`tests/`](tests/).

| Script | What it measures | Cost |
| :--- | :--- | :--- |
| `bioma_kernel_loadtest.py` | kernel throughput/latency under 1k–10k agents | free |
| `bioma_objective_eval.py` | code correctness, executed tests | ~$0.4 |
| `bioma_defense_eval.py` | security remediation, executed checks | ~$0.3 |
| `bioma_efficiency_simulation.py` | per-model efficiency (judge) | ~$0.7 |
| `bioma_sakana_console_test.py` | demo console (μs lab notebook) | ~$0.15 |
| `bioma_sovereign_defense_simulation.py` | defensive immune-system demo (inert) | ~$0.01 |

All scripts run offline in a labelled **mock** mode without a key. Real mode needs a
valid `OPENROUTER_API_KEY` (in `.env`, git-ignored — never commit a key).
