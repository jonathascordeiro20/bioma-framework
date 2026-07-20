# bioma-micro

**B.I.O.M.A. Micro-Kernel** — a lean efficiency & resilience core for LLM infrastructure,
written in Rust, exposed to Python via PyO3.

Proven primitives only, nothing else:

- **Context apoptosis** — autonomous history dehydration. Long agent sessions accumulate
  low-value ballast (verbose tool logs, stale turns). The kernel assigns each message a
  metabolic weight by class, applies half-life decay, and purges dead weight *before* the
  payload hits the API. Microsecond-scale, GIL-released, allocation-light. Cache-aware
  since 1.1.0: a `stable_prefix` zone kept byte-identical for provider prompt caching.
- **Effort gauge** (1.1.0) — O(n) task-complexity score → recommended per-request
  thinking budget, so trivial turns stop paying for a full reasoning budget.
- **Hormonal bus** — lock-free in-memory signal injection (~2M signals/s, ~5 µs).

Plus `saturation_scan()` (O(n) repetition detector for cognitive-DDoS / flood inputs)
and `consolidation_gain()` (the economics of rewriting a provider-cached prefix).

## Install

```bash
pip install bioma-micro
```

Prebuilt wheel for Windows (Python ≥ 3.8, abi3). Other platforms build from the sdist
(requires a Rust toolchain: `pip` will invoke `maturin` automatically).

## Quick start

```python
import bioma_micro as bm

messages = [
    ("You are a precise operations copilot.", bm.SYSTEM),   # never purged
    ("FACT: the deploy freeze ends on 2026-07-18.", bm.FACT),  # never purged
    ("[tool log] 40 KB of verbose audit output ...", bm.TOOL),  # prime target
    ("Round 1: any anomaly?", bm.USER),
    ("Nothing above baseline.", bm.ASSISTANT),
    # ... hundreds of turns later ...
    ("What is the freeze end date?", bm.USER),
]

result = bm.dehydrate(messages, half_life=6.0, safe_threshold=0.35)
print(result["reduction"])          # fraction of input tokens purged (0..1)
print(result["kernel_latency_us"])  # pure-Rust decision pass, microseconds
prompt = "\n".join(result["kept"])  # dispatch this instead of the full history
```

Flood detection:

```python
bm.saturation_scan(suspicious_text)  # ~1.0 = repetitive flood, ~0.0 = natural text
```

## The honest contract

Measured, auditable behavior (full methodology and raw data in the
[framework repo](https://github.com/jonathascordeiro20/bioma-framework)):

| Client behavior | Measured effect |
| :--- | :--- |
| Naive tool-calling agent (resends growing history) | **−84%** input tokens |
| Generic long session (16 rounds, resends everything) | **−95.8%** input tokens |
| Claude Code (already self-manages context) | **~0%** — safe no-op |

- Values tagged `FACT` and recent turns survive; answer quality stays at parity with the
  full-context baseline (verified with objective probes against real online models).
- Durable info buried in old untagged turns **is purged by design** — tag it `FACT`.
- Against an already-lean agent the kernel is a no-op: it never helps, never hurts.

This is a safety net for agents that do **not** manage their own context — not a
universal "−X%" claim.

## API surface

| Symbol | Kind | Purpose |
| :--- | :--- | :--- |
| `dehydrate(messages, half_life=6.0, safe_threshold=0.35, stable_prefix=0)` | function | one-shot history dehydration; `stable_prefix` = cache-aware zone kept verbatim; returns kept blocks + audit dict |
| `saturation_scan(text, window=8)` | function | duplicate-shingle flood score (0..1) |
| `consolidation_gain(prefix_tokens, purgeable_tokens, calls_ahead=8, ...)` | function | cache economics: is rewriting a cached prefix worth it? net gain + break-even calls |
| `effort_gauge(text)` | function | O(n) task-complexity score → recommended thinking budget (`tier`, `budget_tokens`, raw `signals`) |
| `ContextApoptosis(half_life, safe_threshold, capacity, state_capacity=64)` | class | stateful engine (`insert` / `dehydrate(absorb=)` / `render`) + purpose contract (`set_purpose`) + STATE ledger (`note_state`, `state_entries`) |
| `HormonalBus`, `HormonalSignal` | class | lock-free signal bus |
| `SYSTEM`, `USER`, `ASSISTANT`, `FACT`, `TOOL`, `THINKING` | flags | metabolic signal classes |

### Cache-aware dehydration & thinking budgets (1.1.0)

Two cost phases, two levers:

- **Input (prefill):** apoptosis is deletion-only and order-preserving, so a durable
  prefix stays byte-identical. With provider prompt caching, pass `stable_prefix` to
  guarantee it, and ask `consolidation_gain()` *when* purging cached ballast actually
  pays off (cache reads at 0.1× make stale prefixes cheap — break-even is often 15+
  calls away; the kernel does this arithmetic for you).
- **Reasoning (decode):** thinking tokens are output-priced (~5×) and sequential.
  `effort_gauge()` scores each request with cheap lexical signals and returns the
  budget to forward as `budget_tokens` (Anthropic) / `reasoning_effort` (OpenAI) —
  trivial turns ("yes", "continue") stop paying for a full thinking budget.

## License

[FSL-1.1-MIT](https://fsl.software/) — Functional Source License 1.1 with MIT future
license. Free for internal use, non-commercial use, and professional services; converts
to MIT two years after each release.
