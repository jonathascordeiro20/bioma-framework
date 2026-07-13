# B.I.O.M.A. — What it is, what it solves, and the proof

**🌐 English · [Português](OVERVIEW.pt-BR.md)**

## What B.I.O.M.A. is (now)

B.I.O.M.A. is a **local, provider-agnostic efficiency & security micro-kernel for
LLM applications** — a lock-free Rust core (`bioma_micro`) plus a thin Python layer
(`bioma`) that you embed *in front of any LLM call*, in-process, before your prompt
ever leaves the machine. It works with **Anthropic, Google, OpenAI** — or any
provider — because it hardens the payload and hands it back to *your* SDK.

It is **not** a model and it does **not** try to make a model "smarter." We tested
that thesis (multi-LLM orchestration / "mitosis") and **refuted it with ground truth**
— see below. B.I.O.M.A. makes the *processing* cheaper, faster and safer.

## Main objective

> Make LLM processing **viable, sustainable, and safe at scale** — cut the token cost,
> resist floods, protect secrets, and bound latency — as a drop-in local artifact,
> with no vendor lock-in.

## The pain it attacks

1. **Token/cost bleed.** Every call re-sends bloated context (verbose tool logs, stale
   turns). On long sessions the input grows unbounded and the bill explodes.
2. **Cognitive DDoS / context-window exhaustion.** Repetitive floods and forged-log
   spam blow the context window → denial of service on the reasoning pipeline.
3. **Secret leakage via prompt injection.** Apps leave secrets in the working context;
   an injection asks the model to print them.
4. **Latency & hangs.** Unbounded calls (or loop-injection) stall the pipeline.
5. **Vendor lock-in.** Coupling the whole stack to one provider's API.

## How it works — three real mechanisms

| Mechanism | What it does |
| :--- | :--- |
| **Context apoptosis** | Assigns each context block a metabolic weight, applies aggressive half-life decay, and **purges** low-value blocks (old logs, resolved chatter) before dispatch — dehydrating the input. |
| **Cognitive firewall** | **Secret redaction** (vault values scrubbed from the outbound payload AND the response), **saturation detection** (`saturation_scan` flags repetitive floods → `0x0F` red alert → apoptosis), and a **timeout guard** bounding every dispatch. |
| **Hormonal bus** | A lock-free, atomic in-memory signalling substrate (μs), used for the alert state. |

## Proof — real, reproducible benchmarks (ground truth)

Every number below was measured this project, not asserted. Scripts are in the repo.

### Efficiency — context apoptosis
- **−80% input tokens** universally (every model, every task); **up to −97%** on long,
  noisy sessions.
- **16-round real session** (live OpenRouter, `tests/test_enxuto_efficiency.py`):
  input **47,890 → 2,022 tokens** (93.8% avg/round, 97.5% by round 16), apoptosis
  latency **~1.6μs** avg, **0/16** dispatch errors, whole session cost **$0.0191**.

### Resilience — the Rust kernel (`bioma_kernel_loadtest.py`)
- **~2M signals/s** at **~5μs mean latency**.
- **1k → 10k concurrent agents (10× load):** mean latency 4.5μs → 5.0μs (**1.1×**),
  p99 21μs → 15μs — **bounded, sub-linear** under load.

### Security — cognitive firewall APT war-game (real, `reports/BIOMA_IMMUNITY_VERDICT.md`)
- **Prompt-injection secret exfiltration:** 2 secrets redacted, **0 leaked** → CONTAINED.
- **Cognitive DDoS:** a **32,317-token** flood detected (saturation **0.999** → `0x0F`)
  and dehydrated to **13 tokens** in **0.6μs** → MITIGATED.
- **Code-injection loop:** contained by the timeout guard → CONTAINED.

### Engineering
- **20 unit tests** (kernel, firewall, server), offline/deterministic, green in CI.

## Proof of *truth*: what we refuted (and kept out of the pitch)

Rigor cuts both ways. We tested the "orchestrate many LLMs → better answers" thesis
and it **failed** on ground truth (`FINDINGS.md`):

- **Objective executed-test correctness:** baseline **95% → mitosis 83%** (−17 tests;
  synthesis *corrupted* correct answers). Neutral on frontier models (ceiling),
  harmful on weaker ones.
- Confirmed across **three independent experiments** (code eval, security remediation,
  verified cross-model selection) — always **≤ 0** gain, at **4–6× the cost**.

So we **removed** it from the product. The value is the apoptosis + kernel + firewall —
measured — not a quality claim we can't defend.

## Positioning in one line

> B.I.O.M.A. turns an expensive, fragile LLM call into a **cheap, flood-resistant,
> secret-safe, bounded-latency** one — locally, with any provider. Proven, honest,
> auditable.

See [`README.md`](README.md) for usage and [`FINDINGS.md`](FINDINGS.md) for the full
evaluation (proven *and* refuted).
