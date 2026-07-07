# B.I.O.M.A. — context-apoptosis FinOps (kernel → orchestrator)

_backend: **rust** · price: $3.0/1M input · 2026-07-07T13:40:43Z_

## 1 · Single window (the product claim)

- Context composition: system(400t) + 6 recent(240t) + 8 tool-logs(150t, noise)
- **Reduction: 39.3%** — 1233 of 3134 tokens pruned per request
- **$3,699.0 saved per 1M requests** ($0.003699/request)

## 2 · Multi-turn session (compounding)

- 200 sessions × 20 turns
- **Reduction: 69.8%** vs. re-sending full history (4376 tokens/call)
- **$13,127.7 saved per 1M calls**

## Honesty

- Token counts are REAL (the kernel removes items); reduction depends on context noise.
- USD is a calculation from a stated input price — no external model was called (offline).
- Savings apply to INPUT tokens; output tokens are unaffected by pruning.
