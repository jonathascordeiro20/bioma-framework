# Technical & Feasibility Study — "Purpose Context" (BIOMA Core Evolution)

**Date:** 2026-07-20
**Scope:** where the processing cost of an LLM really is (context ingestion vs.
deep thinking), and how BIOMA should evolve to reduce tokens in both phases.

> Historical note: this is the study that motivated the kernel 1.1.0 / gateway
> 1.3.x "purpose context" release. Its projections have since been measured —
> see `reports/BIOMA_REVALIDACAO_V131.pt-BR.md` for the numbers.

---

## 1. Fundamentals: the two processing phases of an LLM

Every LLM call has two physically distinct phases on the hardware:

### 1.1 Prefill (context ingestion)

- All N input tokens are processed **in parallel**, in a single pass.
- It is **compute-bound**: the GPU reaches high FLOP utilization (60–80% MFU).
- Approximate FLOP cost: `2 · P · N` (P = model parameters) **+ attention
  O(N²·d)** — the quadratic attention term makes very long contexts (100k+)
  dominate the compute cost.
- Fast in wall-clock per token (it parallelizes), but expensive in total energy
  when N is large.

### 1.2 Decode (generation / deep thinking)

- Generates **one token at a time**, autoregressively. Every token requires
  re-reading all model weights + the entire KV cache.
- It is **memory-bandwidth-bound**: FLOP utilization typically < 10% MFU. The
  hardware sits idle waiting on memory.
- Per token, decode costs **10–100× more wall-clock time and energy** than a
  prefill token.
- "Deep thinking" (extended thinking / reasoning) is pure decode: thousands of
  tokens generated sequentially before the final answer.

### 1.3 Direct answer to the study's question

> *"Is LLM processing higher at context ingestion or during deep thinking?"*

**It depends on the metric — and both answers matter for BIOMA:**

| Metric | Which dominates | Why |
| :--- | :--- | :--- |
| **Total FLOPs per call** | Input (prefill), in the typical agent case | Agents resend 20k–100k tokens of history to generate 1k–3k. Input volume ≫ output, and attention grows O(N²). |
| **Cost per token (energy, time, price)** | Thinking (decode) | Sequential + memory-bound. Providers reflect it in pricing: output costs **4–5× input** (e.g. Claude Sonnet $3/M in vs $15/M out; thinking tokens are billed as output). |
| **Perceived latency** | Thinking (decode) | A 50k-token prefill takes ~1–2 s; 5k thinking tokens take tens of seconds. |
| **Accumulated cost of an agent session** | Input — and **quadratically** | See §2. This is the study's central result. |

---

## 2. The central result: in agent sessions, input cost grows quadratically

Cost model for a session with T turns, average context C_t at turn t, R_t
reasoning tokens and O_t response tokens:

```
Total_cost = Σ_t [ c_in · C_t  +  c_out · (R_t + O_t) ]
```

- Without pruning, C_t grows linearly with t (each turn accumulates history +
  tool logs). → the input term sums a **quadratic series in T**.
- R_t and O_t are roughly constant per turn → the output term is **linear in T**.

**Conclusion:** even with output costing 5× more per token, in any long session
the **input cost overtakes and dominates**. That is exactly the regime
`bioma_micro` already attacks (−84% on a naive agent, −95.8% on a 16-round long
session — measured data from the framework itself). BIOMA's thesis is aimed at
the right place.

**Corollary:** reducing thinking is the complementary lever — it dominates only
in **short-session + hard-task** workloads (one question, lots of reasoning). A
complete core needs both.

---

## 3. Critical constraint discovered: apoptosis × prompt caching

Provider prompt caching (cache read = **10× cheaper** than normal input;
~$0.30/M vs $3/M on Sonnet) works by **exact prefix**. Any change at the start
of the history invalidates the cache from that point on.

**Real risk for BIOMA at the time:** `dehydrate()` rewrote the history on every
call. Against a client using prompt caching, pruning 30% of the context could
**increase** the net cost — trading 70k cached tokens ($0.021) for 49k uncached
tokens ($0.147), plus the cache write ($3.75/M).

**Evolution requirement (P0):** a *cache-aware* mode:

1. Keep a **stable prefix** (system + FACTs + already-consolidated history)
   that is never rewritten between calls.
2. Apply apoptosis only to the **mobile suffix** (after the last cache
   breakpoint).
3. Consolidate prunes into "generations": rewrite the prefix only when the
   projected saving beats the re-cache cost (computable threshold — otherwise
   defer).

Without this, BIOMA's sales argument breaks against any modern stack (Claude
API, OpenAI, Bedrock — all have caching).

---

## 4. Feasibility: reducing "deep thinking" tokens

You cannot compress tokens the model generates — but you can **control how many
it generates** and **stop old reasoning from becoming input ballast**. Four
mechanisms, in feasibility order:

### 4.1 Dynamic thinking budget (feasible now, high impact)

The APIs expose direct control: `budget_tokens` (Anthropic), `reasoning_effort`
(OpenAI). What frameworks lack is **deciding the budget per task**. BIOMA can
do it with an O(n) classifier in the spirit of `saturation_scan`:

- Cheap signals (no LLM): request size and entropy, presence of code/numbers,
  number of constraints, whether it continues an already-solved task.
- Mapping: trivial → thinking off; medium → 1–2k; hard → 8k+.
- Expected saving: real workloads have a majority of trivial turns
  ("continue", "yes", short corrections) that currently pay a full thinking
  budget. A plausible 30–60% reasoning-token reduction with no quality loss —
  verifiable with the same objective probes used in the framework benchmark.

### 4.2 Purpose Contract (the "purpose context" proper)

Inject a compact, **stable** block at the top of the context:

```
PURPOSE: <session goal in 1 sentence>
CONSTRAINTS: <3–5 invariants>
STATE: <what has already been decided — replaces re-reading the history>
```

Double effect, both measurable:

- **Input:** the STATE block replaces old turns (apoptosis can be more
  aggressive because durable information migrated into the contract — the
  generalization of the existing `FACT` flag).
- **Thinking:** a crisp goal reduces wandering reasoning (the model spends
  fewer tokens "rediscovering" what to do). Testable hypothesis: A/B with and
  without the contract, same tasks, measure reasoning tokens and accuracy.

Natural fit: it is the evolution of the stateful `ContextApoptosis` — the
kernel maintains, besides the weighted history, a **consolidated summary** that
absorbs the content of apoptosed items instead of discarding them blindly.

### 4.3 Apoptosis of thinking blocks in the agent loop

The Anthropic API already drops previous-turn thinking automatically, but
frameworks that persist the full transcript (LangChain, home-grown tool-calling
logs) resend everything. The kernel should classify thinking/scratchpad blocks
as class `TOOL` (prime target) — implementation cost ~zero, it's just tagging.

### 4.4 Model cascade (feasible, but outside the core)

Route to a small model first and escalate only on low confidence. High gain,
but it is the orchestrator's job (`bioma_orchestrator`), not the micro-kernel's
— keeping the core to "exactly the proven primitives" is the product's
identity.

---

## 5. Feasibility verdict

| Front | Feasibility | Impact | Priority |
| :--- | :--- | :--- | :--- |
| Cache-aware apoptosis mode | High (Rust only, no new API) | Avoids a real cost regression | **P0** |
| Dynamic thinking budget | High (O(n) classifier + API params) | 30–60% of reasoning tokens | **P1** |
| Purpose Contract + consolidated summary | Medium (changes the `ContextApoptosis` contract) | More aggressive pruning without loss + less wandering thinking | **P1** |
| Tagging old thinking as `TOOL` | Trivial | Marginal, but free | P2 |
| Model cascade | High, but in the orchestrator | Large, out of core scope | P3 |

**Synthesis:** the physics of the problem confirms BIOMA's current bet — in
agent sessions the cost is dominated by **input**, which grows quadratically
with the number of turns, while thinking grows linearly. The right evolution is
not to shift focus to thinking, but to (1) shield apoptosis against prompt
caching, which could invert the gain, and (2) add reasoning-budget control as a
second primitive — cheap, measurable and complementary. The "purpose context"
(contract + consolidated summary) is the bridge between the two: it improves
input pruning and reduces reasoning at the same time.

**Suggested acceptance benchmark:** repeat the existing protocol (naive agent,
16 rounds, objective probes) under 3 conditions — baseline, current BIOMA,
BIOMA + P0/P1 — measuring input tokens, reasoning tokens, USD cost (with and
without prompt caching active) and probe accuracy.

---

*Post-release outcome (measured after this study): P0, P1 and P2 shipped in
kernel 1.1.0 / gateway 1.3.x. Measured results: −71% net cost after the cache
discount (real `cache_control`), −89% reasoning tokens on a realistic mix
(−64% under an executable quality gate, 0 divergent pairs), A/B reproduced at
−82.2% median with 0 divergent pairs.*
