# Changelog

## 1.0.0 — 2026-07-16

First public release on PyPI.

- `dehydrate()` — one-shot, stateless history dehydration (recency-weighted half-life
  decay, protected `SYSTEM`/`FACT` classes, audited token savings, GIL-released hot path).
- `ContextApoptosis` — stateful incremental engine (`insert` / `dehydrate` / `render`,
  atomic audit counters).
- `saturation_scan()` — O(n) duplicate-shingle flood detector (cognitive-DDoS guard).
- `HormonalBus` / `HormonalSignal` — lock-free in-memory signal bus (crossbeam).
- abi3 wheel (`cp38-abi3`): one binary wheel covers CPython ≥ 3.8.
