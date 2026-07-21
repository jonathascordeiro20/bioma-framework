# B.I.O.M.A. — Real-world validation of the v1.4.0 evolutions (old vs recommended config)

> 2026-07-21 · Claude Code CLI 2.1.210 headless, subscription auth, model
> `sonnet[1m]` (claude-sonnet-5), native Anthropic upstream with OAuth
> pass-through. Same task in both runs: repository with 5 buggy modules
> (slugify, stats, interval, cart, paginate), fixed one at a time, per-module
> pytest + full suite as the judge (`tests/e2e_claude_code_long.py`).
> Raw data: `results/validation_config_{OLD,NEW}.json` +
> `results/validation_audit_{OLD,NEW}.jsonl`.

## Configurations compared

| Knob | OLD (control) | NEW (recommended for agents) |
| :--- | :--- | :--- |
| `BIOMA_SAFE_THRESHOLD` | 0.2 | 0.2 |
| `BIOMA_STABLE_PREFIX` | 0 (min 1 enforced) | **auto** (client cache breakpoint) |
| `BIOMA_PURGE_QUANTUM` | off | **8** |
| `BIOMA_CACHE_HYSTERESIS` | off | **0.30** |
| `BIOMA_AUTO_FACT` | off | **on** |
| `BIOMA_REHYDRATE_STORE` | off | **on** |

## Result — same quality, 28–37% cheaper process

| Metric | OLD | NEW | Δ |
| :--- | ---: | ---: | :--- |
| 5 modules green (pytest) | ✅ | ✅ | identical quality |
| Turns | 29 | 33 | +4 (agent variance, N=1) |
| CLI accounted cost (API prices) | $4.0556 | $2.9135 | **−28.2%** |
| Cost per turn | $0.1399 | $0.0883 | **−36.9%** |
| Wire reduction (apoptosis) | −69.1% | −50.6% | expected trade-off |
| **Cache written (invalidation waste)** | 420,925 tok | 157,046 tok | **−62.7%** |
| **Cache read (reuse)** | 4,653,852 tok | 6,053,045 tok | +30.1% |
| **Real provider cache hit-rate** | 91.3% | **97.2%** | +5.9 pp |

Cache metrics come from the provider itself
(`cache_read_input_tokens` / `cache_creation_input_tokens` in the API usage),
not from our own estimates.

The mechanics the design predicts are literally visible in the NEW audit:

* **Hysteresis** — requests 3–7 and 13–15 at −0.0% (HOLD: prefix intact,
  full cache hit) instead of the OLD run's micro-purges;
* **Quantum** — `blocks_purged` advances in plateaus (4 → 12 → 20), constant
  across several consecutive requests: batched purges, byte-identical output
  between boundary advances, invalidation paid once per batch;
* **Net economics** — trading ~18 pp of wire reduction bought −62.7% of
  cache re-writing, closing at −28% total cost with the SAME final quality.

## Rehydration validated live

The store hibernated **20 unique blocks** (referenced 232× across audit lines
via `purged_hashes`). `GET /v1/rehydrate/{hash}` against the running gateway
returned the block **byte-identical** (including a signed thinking block from
the session itself) — apoptosis is reversible: nothing is lost, it hibernates.

## Auto-FACT

Validated by the offline suite (precision corpus): 10/10 durable constraints
detected (EN + pt-BR), 0 false positives on casual chatter and tool logs, and
an old untagged constraint ("Never deploy on Fridays") that died under the
OLD config **survives** with Auto-FACT — the S3 gap closed without requiring
user discipline. No effect on tool-output purge volume.

## Honest caveats

1. **N=1 per configuration.** The turn delta (29 vs 33) and part of the cost
   delta carry agent variance. The direction of the result is supported by
   the mechanical metrics (cache_creation, purge plateaus), which do not
   depend on the agent's path; the exact magnitude calls for the statistical
   E2E (N≥10 pairs).
2. **Accounted cost, not an invoice.** Dollars are the CLI's computation at
   API prices; the subscription is not billed. The ratio (−28%) is valid
   because both runs use the same price table.
3. The smaller wire reduction (−50.6% vs −69.1%) is **by design**: quantum
   and hysteresis keep tokens on the wire to buy cache stability. The optimal
   point of the trade-off (K, threshold) is exactly what the statistical E2E
   should sweep.

## Regression suite

66 green tests after the changes: 23 original gateway, 14 protocol
invariants, 9 evolutions, 20 kernel/firewall/server; the Claude Code
simulation's retention contract 100% intact (`tests/test_evolutions.py`,
`tests/test_protocol_invariants.py`, `tests/simulate_claude_code_session.py`).

## Conclusion

With the recommended config (`threshold 0.2 · stable_prefix auto · quantum 8
· hysteresis 0.30 · auto-FACT · rehydrate store`), BIOMA delivered, in a real
end-to-end agent: **same final quality, −28% total cost, −63% cache waste and
full reversibility of pruning** — resolving the three weaknesses identified in
the feasibility analysis (cache interaction, invalid-payload risk, and
dependence on manual tagging).
