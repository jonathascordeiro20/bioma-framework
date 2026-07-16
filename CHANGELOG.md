# Changelog

All notable changes to the B.I.O.M.A. distributions (`bioma-framework` and
`bioma-micro`) are documented here. Versions follow [SemVer](https://semver.org).

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
