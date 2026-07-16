# Changelog

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
