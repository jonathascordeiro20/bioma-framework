# Changelog

All notable changes to the B.I.O.M.A. distributions (`bioma-framework` and
`bioma-micro`) are documented here. Versions follow [SemVer](https://semver.org).

## [1.4.0] — 2026-07-21

### bioma-framework — cache-aware batching, protocol invariants, Auto-FACT, rehydration

Born from a real end-to-end validation with the actual Claude Code CLI
(5-bug long session through the gateway against the native Anthropic API —
see `reports/BIOMA_E2E_LONG_SESSION.md` and
`reports/BIOMA_VALIDATION_EVOLUTIONS.md`). Measured on the same task, old vs
new config: **same quality (5/5 pytest green), −28% total accounted cost,
−63% cache-write waste, provider cache hit-rate 91.3% → 97.2%.**
All new knobs are opt-in; defaults preserve 1.3.x behavior.

- **`BIOMA_PURGE_QUANTUM`** (0 = off): quantized purge boundary — purge
  decisions freeze in steps of K units, so the pruned output stays
  byte-identical for K consecutive turns and the provider prompt cache hits
  on the PRUNED context; the invalidation is paid once per batch.
- **`BIOMA_CACHE_HYSTERESIS`** (0.0 = off): purges below this potential
  reduction are HELD (history forwarded untouched, cache prefix intact);
  audit records `held` + `potential_reduction`.
- **`BIOMA_STABLE_PREFIX=auto`**: stable zone derived per request from the
  client's first `cache_control` breakpoint — no manual tuning.
- **`BIOMA_AUTO_FACT`** (off): conservative heuristic (EN + pt-BR) that
  promotes short USER turns that read like durable constraints to FACT —
  closes the untagged-requirement gap (scenario S3) without user discipline.
  Never promotes tool output or texts >600 chars.
- **`BIOMA_REHYDRATE_STORE=<dir>`** (off): purged units persist locally,
  content-addressed by SHA-256 (`purged_hashes` in the audit line);
  `GET /v1/rehydrate/{hash}` returns any pruned block byte-identical.
  Apoptosis becomes hibernation — nothing is lost.
- **Protocol invariants (always on):** the Anthropic surface now floors the
  stable prefix at 1 (the conversation anchor is never pruned — strict
  Messages endpoints 400 otherwise) and a deletion-only repair pass
  guarantees no leading non-user turn, no orphan `tool_result`, no dangling
  `tool_use` in the pruned output.
- **Gateway:** forwards the `anthropic-beta` header (enables native Anthropic
  upstream with subscription OAuth pass-through; OpenRouter-style upstreams
  ignore it).
- **Tests:** +23 (protocol invariants incl. seeded fuzz, evolutions incl. an
  Auto-FACT precision corpus with zero tolerated false positives, quantum
  prefix-stability property) plus a deterministic Claude Code session
  simulator (`tests/simulate_claude_code_session.py`) and a long-session E2E
  harness (`tests/e2e_claude_code_long.py`).

Recommended agent-traffic config (e.g. Claude Code):
`BIOMA_SAFE_THRESHOLD=0.2 BIOMA_STABLE_PREFIX=auto BIOMA_PURGE_QUANTUM=8
BIOMA_CACHE_HYSTERESIS=0.30 BIOMA_AUTO_FACT=1
BIOMA_REHYDRATE_STORE=~/.bioma/hibernation`

## [1.3.1] — 2026-07-20

### bioma-framework — dynamic thinking budgets at the proxy

- `BIOMA_AUTO_EFFORT` (opt-in): the gateway now runs the kernel's
  `effort_gauge` on each request's current query and sets the reasoning
  budget accordingly. Conservative contract — never raises effort beyond what
  the client asked for; OpenAI surface only fills absent `reasoning` params
  (trivial turn → `{"enabled": false}`); Anthropic surface only downgrades an
  explicit `thinking.budget_tokens` to the 1024 minimum on confidently-trivial
  turns, and only adds thinking for medium/high tasks when the request is
  compatible (temperature absent or 1, room under `max_tokens`). Every
  decision is logged to the JSONL audit (`effort: {tier, score, action}`).

## [1.3.0] — 2026-07-20

### bioma-micro 1.1.0 — "purpose context": both cost phases covered

Backed by the feasibility study in `PURPOSE_CONTEXT_STUDY.md`
(input cost grows quadratically with agent-session length; reasoning grows
linearly; cache reads at 0.1× make prefix consolidation a real decision).

- `dehydrate(..., stable_prefix=N)` — cache-aware zone kept verbatim so a
  provider prompt-cache prefix stays byte-identical (+ `stable_prefix_tokens`
  in the audit dict).
- `consolidation_gain()` — cache economics: net gain + break-even calls for
  rewriting a cached prefix (defaults = Anthropic read 0.1× / write 1.25×).
- `effort_gauge()` — O(n) task-complexity gauge → dynamic thinking budget
  (`tier` off/low/medium/high, `budget_tokens` 0/1k/4k/16k, raw signals
  exposed). Calibrated on 1223 real agent prompts (68/23/9/0.5% split).
- `ContextApoptosis`: `set_purpose()` (stable contract header), `note_state()`
  (bounded deduplicated STATE ledger), `dehydrate(absorb=True)` (purged
  USER/ASSISTANT turns leave a one-line digest in STATE). New `THINKING`
  signal class — cheapest weight (0.15), purged before `TOOL`.

### bioma-framework — cache-aware gateway

- `BIOMA_STABLE_PREFIX` (default 0): leading history *units* the gateway keeps
  verbatim before apoptosis — the kernel 1.1.0 cache-aware zone, end to end.
  Measured live (Sonnet, real `cache_control`): identical token profile to the
  plain dehydration arm (no regression) with the byte-identical-prefix
  guarantee formalized; net BIOMA saving **after** the cache discount: −71%
  (`results/cache_interaction.json`).

## [1.2.0] — 2026-07-19

### bioma-framework — auditable carbon ledger

- `bioma.carbon_ledger` — signed, tamper-evident efficiency & carbon report
  (`bioma-carbon-ledger`, extra `[ledger]`): hash-chains the gateway audit log,
  aggregates measured tokens into bounded Wh/gCO2e/USD avoided (declared,
  versioned `bioma.esg` coefficients — reduction % exact, absolutes bounded),
  and Ed25519-signs the result. `verify` catches both a forged ledger
  (`signature INVALID`) and a tampered audit (`recompute MISMATCH`). Avoided
  emissions reported as a counterfactual, never netted against Scope 1/2/3.

### bioma-suite 1.0.1

- `bioma-doctor` now verifies the **carbon ledger** tier (cryptography +
  `bioma.carbon_ledger`) alongside the existing components.

## [1.1.0] — 2026-07-18

### bioma-suite 1.0.0 (new distribution)

- One-shot meta-package: `pip install bioma-suite` pulls `bioma_micro`,
  `bioma-framework[all]` and `bioma-langchain` in a single command.
- `bioma-doctor` — stdlib-only install checkup: per-component import + version
  report and a real kernel smoke test (exit 0 = core healthy).
- Release: new `pypi-suite` environment in `release.yml` (one Trusted
  Publishing environment per package); publishes after the components so the
  pinned versions are always resolvable.

### bioma-framework 1.1.0

- `bioma.monitor` — live terminal cockpit (`bioma-monitor`, extra `[monitor]`):
  follows the gateway's per-request audit JSONL in real time (`tail -f`
  semantics, rotation-safe) — session totals, reduction sparkline, kernel μs
  p50/max, per-model table, request feed, gateway `/health` status, and the
  bounded ESG / cost estimate from `bioma.esg` (always labeled an estimate).
  `--tail` (live traffic only), `--once` (single frame, CI-friendly).
- tests: `tests/test_server.py` now clears `OPENROUTER_API_KEY` at test time
  (autouse fixture) — the full-suite run is deterministic even when a local
  `.env` holds a real key (importing `bioma.gateway` runs `load_dotenv`).

## [1.0.1] — 2026-07-16

### bioma-micro 1.0.1

- **security**: PyO3 0.22.6 → 0.29 (clears the Dependabot advisories: 1 high,
  1 medium, 1 low). No behavior change; full kernel test suite green.

## [1.0.0] — 2026-07-16

First public release on PyPI, via Trusted Publishing (OIDC).

### bioma-micro 1.0.0 (Rust kernel)

- `dehydrate()` — one-shot history dehydration (half-life decay, protected
  `SYSTEM`/`FACT` classes, audited savings, ~1 µs decision, GIL released).
- `ContextApoptosis` — stateful incremental engine with atomic audit counters.
- `saturation_scan()` — O(n) duplicate-shingle flood detector.
- `HormonalBus` / `HormonalSignal` — lock-free in-memory signal bus.
- abi3 wheels (`cp38-abi3`) for Linux x86_64, macOS arm64 and Windows x64.

### bioma-framework 1.0.0 (Python layer, `import bioma`)

> PyPI name is `bioma-framework` (the name `bioma` is taken since 2017);
> the import remains `import bioma`.

- `bioma.gateway` — drop-in FastAPI proxy (OpenAI `/v1/chat/completions` +
  Anthropic `/v1/messages` surfaces) with per-request apoptosis audit (JSONL),
  bridge mode (`BIOMA_FORCE_KEY`) and tuning env vars.
- `bioma.openrouter_client.LeanOpenRouterClient` — resilient async client with
  kernel-side apoptosis on every dispatch.
- `bioma.vision` — pixel secret redaction (OCR + region masking) and image
  distillation; `bioma.esg` / `bioma.esg_report` — energy & CO2e accounting.
- Benchmarks shipped with raw data: A/B vs real Claude Code across 8 models,
  consolidated in `benchmarks/ab-publico/results/RESULTS.md`.

### Operational notes

- Recommended tuning for tool-calling agents: `BIOMA_SAFE_THRESHOLD=0.2`
  (default 0.35 purges even the freshest tool_result — measured to cause agent
  rework).
