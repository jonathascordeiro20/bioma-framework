# B.I.O.M.A. — result-quality lever sweep (coverage/cascade vs S*)

_Generated 2026-07-06T21:02:04Z_

Ground truth: **analytic S* = (I − γC)^-1 P** · 4 domains × 20 pts · 2 seeds.

**Monolithic baseline:** coverage **0.4962**, cascade **0.2762**

## Lever 1 — adaptation cycles (`metabolic_cycles`)

| cycles | coverage | cascade | cov lift | cascade lift |
|---|---|---|---|---|
| 2 | 0.9926 | 0.5879 | +0.4963 | +0.3117 |
| 4 | 0.9926 | 0.5879 | +0.4963 | +0.3117 |
| 8 | 0.9926 | 0.5879 | +0.4963 | +0.3117 |
| 12 | 0.9926 | 0.5879 | +0.4963 | +0.3117 |

## Lever 2 — coordination strength (`coordination_gamma`)

| gamma | coverage | cascade | cascade lift |
|---|---|---|---|
| 0.0 | 0.9926 | 0.4614 | +0.1852 |
| 0.3 | 0.9926 | 0.5235 | +0.2473 |
| 0.6 | 0.9926 | 0.5879 | +0.3117 |
| 0.9 | 0.9926 | 0.6519 | +0.3757 |

## Lever 3 — bus on/off (coordination channel)

- cascade **with bus 0.5879** vs **without 0.4614** → bus contributes **+0.1265** cascade (coverage moves +0.0 — bus-invariant, as expected)

## Best combined config

- `metabolic_cycles=2`, `coordination_gamma=0.9` → coverage **0.9926** (+0.4963), cascade **0.6519** (+0.3757) vs monolithic

## Honesty

- Measured against an ANALYTIC ground-truth S* (real, not mock).
- coverage is mitosis-driven and coordination-invariant; cascade is the coordination-improvable metric.
- Proves result gains on multi-domain latent coordination — not on general language reasoning.
