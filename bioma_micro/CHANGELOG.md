# Changelog

## 1.1.0 — 2026-07-20

"Purpose context" evolution — the kernel now covers both cost phases of an LLM
call: input context (prefill) and reasoning (decode). Fully backward compatible.

- `dehydrate(..., stable_prefix=N)` — cache-aware zone: the first N messages are
  kept verbatim regardless of class, so a provider prompt-cache prefix stays
  byte-identical between calls. Audit dict gains `stable_prefix_tokens`.
- `consolidation_gain()` — cache economics: decides whether rewriting a cached
  prefix (to purge ballast) beats keeping it stale, in input-token equivalents;
  returns net gain and break-even call count. Defaults match Anthropic pricing
  (read 0.1×, write 1.25×).
- `effort_gauge()` — O(n) task-complexity gauge for dynamic thinking budgets.
  Cheap lexical signals (length, hard verbs, constraints, code, digits, novelty;
  en + pt-BR) → `tier` (off/low/medium/high) + `budget_tokens` (0/1k/4k/16k),
  with every raw signal exposed for auditability. Repetitive boilerplate is
  down-scored by design. Calibrated against 1223 real agent-session prompts
  (resulting split: 68% off / 23% low / 9% medium / 0.5% high); pt verbs match
  by stem so imperatives and infinitives both count, and one explicit
  hard-task verb guarantees at least the small budget.
- `ContextApoptosis`: purpose contract + consolidated STATE ledger.
  `set_purpose()` renders a stable header above the history; `note_state()`
  keeps bounded, deduplicated durable facts; `dehydrate(absorb=True)` absorbs a
  one-line digest of purged USER/ASSISTANT turns into STATE instead of dropping
  them without trace (TOOL/THINKING ballast still vanishes silently).
  `render()` layout: [purpose] + [STATE] + [survivors]. New constructor arg
  `state_capacity=64`.
- New `THINKING` signal class (stale reasoning blocks) — cheapest metabolic
  weight (0.15), purged before `TOOL`.

## 1.0.1 — 2026-07-16

- security: upgrade PyO3 0.22.6 → 0.29 (fixes GHSA advisories flagged by
  Dependabot: 1 high, 1 medium, 1 low). API migration (`detach`,
  `PyDict::new`, `PyList::empty`, explicit `from_py_object`); zero behavior
  change — full kernel test suite green.

## 1.0.0 — 2026-07-16

First public release on PyPI.

- `dehydrate()` — one-shot, stateless history dehydration (recency-weighted half-life
  decay, protected `SYSTEM`/`FACT` classes, audited token savings, GIL-released hot path).
- `ContextApoptosis` — stateful incremental engine (`insert` / `dehydrate` / `render`,
  atomic audit counters).
- `saturation_scan()` — O(n) duplicate-shingle flood detector (cognitive-DDoS guard).
- `HormonalBus` / `HormonalSignal` — lock-free in-memory signal bus (crossbeam).
- abi3 wheel (`cp38-abi3`): one binary wheel covers CPython ≥ 3.8.
