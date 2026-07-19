# Changelog

All notable changes to the B.I.O.M.A. distributions (`bioma-framework` and
`bioma-micro`) are documented here. Versions follow [SemVer](https://semver.org).

## [Unreleased]

### bioma-framework — auditable carbon ledger

- `bioma.carbon_ledger` — signed, tamper-evident efficiency & carbon report
  (`bioma-carbon-ledger`, extra `[ledger]`): hash-chains the gateway audit log,
  aggregates measured tokens into bounded Wh/gCO2e/USD avoided (declared,
  versioned `bioma.esg` coefficients — reduction % exact, absolutes bounded),
  and Ed25519-signs the result. `verify` catches both a forged ledger
  (`signature INVALID`) and a tampered audit (`recompute MISMATCH`). Avoided
  emissions reported as a counterfactual, never netted against Scope 1/2/3.

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
- Benchmarks shipped with raw data: A/B vs real Claude Code
  (`resultados/E2E_CLAUDE_CODE.md`), head-to-head vs LLMLingua-2
  (`reports/BIOMA_VS_LLMLINGUA.md`), consolidated honest comparative
  (`reports/BIOMA_BENCHMARK_COMPARATIVO.md`).

### Operational notes

- Recommended tuning for tool-calling agents: `BIOMA_SAFE_THRESHOLD=0.2`
  (default 0.35 purges even the freshest tool_result — measured to cause agent
  rework).
