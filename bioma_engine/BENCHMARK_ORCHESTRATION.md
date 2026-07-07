# B.I.O.M.A. — orchestration performance & token economy

_Generated 2026-07-06T18:40:11Z_

## 1 · Token economy (verified code-optimization workload)

| Metric | B.I.O.M.A. | LLM approach (est.) |
|---|---|---|
| Tokens spent | **0** | 695 (est.) |
| Illustrative cost (USD) | **$0.00** | $0.005409 (est.) |
| Network bytes | **0** | (cloud round-trips) |
| **Token savings** | colspan → | **100%** on this workload |

- Tasks: **6** · verified-improved: **6/6** (100%)
- Mean code speed-up produced: **99.81%** · throughput **1.493 tasks/s** (total 4.019s local)

| Task | Verified? | Code speed-up | Transform | Tokens | LLM tok (est.) |
|---|---|---|---|---|---|
| recursive-fibonacci | ✅ | 99.87% | `ast:insert_lru_cache` | **0** | 92 |
| newton-sqrt-1800 | ✅ | 99.8% | `ast:perturb_int` | **0** | 121 |
| newton-sqrt-2100 | ✅ | 99.76% | `ast:perturb_int` | **0** | 121 |
| newton-sqrt-2400 | ✅ | 99.79% | `ast:insert_lru_cache` | **0** | 120 |
| newton-sqrt-2700 | ✅ | 99.78% | `ast:perturb_int` | **0** | 121 |
| newton-sqrt-3000 | ✅ | 99.87% | `ast:insert_lru_cache` | **0** | 120 |

## 2 · Orchestration performance (multi-agent vs monolithic)

- Coverage: multi-agent **0.9923** vs monolithic **0.4966** → **+0.4957** (99.8% lift)
- Cascade recovery: multi-agent **0.5829** vs **0.2732** → **+0.3097**
- Agents spawned by the orchestrator: **None**

## Honesty

- 0 tokens = deterministic LOCAL optimizer, not a cheaper LLM.
- 100% token saving applies ONLY to the verified code-optimization niche.
- LLM baseline is a conservative estimate; real agent loops cost more.
- 'Performance' = verified correctness + local latency + code speed-up.

> LLM baseline is an estimate (~4 chars/token, 1 call/task, price illustrative). No external model was called.
