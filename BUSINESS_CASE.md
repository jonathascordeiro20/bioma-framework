# B.I.O.M.A. — Business Case & ROI

> **The reduction % is measured (ground truth). Prices are illustrative list prices,
> clearly labeled.** So the *savings ratio* is real; the absolute $ scales with your
> real prices and volumes.

## What B.I.O.M.A. is, in one line

A **local micro-kernel** you put in front of any LLM call. It **dehydrates the input
context** (apoptosis) and **hardens it** (secret redaction, cognitive-DDoS, latency
guard) — cutting **~94% of input-token cost** on every call, with any model, online or
offline.

## The main pain it kills

> Every AI agent and copilot re-sends bloated context on **every** call. At company
> scale — thousands to millions of calls a day — that wasted input is the single largest,
> most invisible line item in an AI budget. B.I.O.M.A. removes ~94% of it.

## Real benchmark — measured input-token reduction (6 frontier models)

| Vendor | Model | in_tok base→BIOMA | Reduction |
| :--- | :--- | :---: | :---: |
| OpenAI | GPT-5.5 | 1,605→78 | **−95%** |
| Anthropic | Claude Sonnet 5 | 2,489→123 | **−95%** |
| Anthropic | Claude Fable 5 | 2,489→123 | **−95%** |
| Google | Gemini 3.1 Pro | 1,835→81 | **−96%** |
| xAI | Grok 4.5 | 1,806→280 | **−84%** |
| Zhipu | GLM-5.2 | 1,610→83 | **−95%** |

Source: `tests/test_universal_integration.py` (real dispatch, real `prompt_tokens`).

## Cost model (transparent)

```
saved_per_call = avg_input_tokens × reduction × input_price_per_token
daily = saved_per_call × calls_per_day
weekly = daily × 7   ·   monthly = daily × 30   ·   yearly = daily × 365
```

Assumptions (adjustable in the interactive dashboard):
- `avg_input_tokens` = 2,000 (our measured workload; long agent sessions are far larger).
- `reduction` = 0.94 (blended measured average).
- `input_price` ≈ list price, USD / 1M input tokens: GPT-5.5 $5 · Sonnet 5 $3 ·
  Fable 5 $5 · Gemini 3.1 Pro $2 · Grok 4.5 $3 · GLM-5.2 $0.6.

## Company profiles (illustrative call volumes)

| Profile | Who | LLM calls/day |
| :--- | :--- | ---: |
| **SMB (PME)** | startup/SaaS: coding agents + a support bot | 5,000 |
| **Large enterprise** | bank/retailer: 500 seats + production agents | 250,000 |
| **Multinational** | global tech/telecom: agent fleets | 5,000,000 |

## Worked savings (Claude Sonnet 5, $3/1M in, 2,000 tok/call, −94%)

| Profile | Cost today/day | With B.I.O.M.A./day | Saved/day | Saved/month | **Saved/year** |
| :--- | ---: | ---: | ---: | ---: | ---: |
| SMB | $30 | $1.80 | $28.20 | $846 | **$10,293** |
| Large enterprise | $1,500 | $90 | $1,410 | $42,300 | **$514,650** |
| Multinational | $30,000 | $1,800 | $28,200 | $846,000 | **$10,293,000** |

> A multinational running frontier agents saves on the order of **$10M/year** in input
> tokens alone — from a layer that also redacts secrets and absorbs cognitive-DDoS.

## Where the calls come from (real usage)

- **Day-to-day agents:** customer-support triage, ops copilots, document analysis,
  internal Q&A — long, growing contexts (where apoptosis saves the most).
- **Software development:** coding agents, PR review, test generation, refactor agents —
  large repo/file context re-sent every step.

## Defense-in-depth impact (measured, model-agnostic)

| Without B.I.O.M.A. | With B.I.O.M.A. |
| :--- | :--- |
| Secret in context **leaks to the provider** (baseline `secret→provider = True` on all 6 models) | **Redacted** — `False` on all 6 (0 leaked) |
| 15k-token cognitive-DDoS **exhausts the context window** | **Dehydrated** 32,317→13 tokens (saturation 0.999) |
| Loop-injection **stalls the orchestrator** | **Contained** by the timeout guard |

> The interactive ROI dashboard (artifact) lets you plug in your own volumes and prices.
