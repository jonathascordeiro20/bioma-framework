#!/usr/bin/env python3
"""Analyze the caching A/B: does BIOMA still save on top of prompt caching?

Reads results/cached/results_cached.jsonl (written by run_benchmark_cached.py).
Every number is the real billed `cost` from OpenRouter per call. Reports, per
model and pooled:

  * session cost of each arm (baseline±cache, bioma±cache)
  * BIOMA's saving ON TOP of caching  = (baseline+cache) vs (bioma+cache)
  * whether the shielded payload was cacheable at all
  * the crossover point K* — how many reuses of the SAME context until warm
    caching on the big baseline overtakes the small uncacheable BIOMA payload
    (from the measured cold + warm per-call costs; None if BIOMA always wins)

No fabricated numbers: if an arm is missing for a task it is skipped and noted.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from collections import defaultdict

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent
DEFAULT = ROOT / "results" / "cached" / "results_cached.jsonl"


def load(path):
    rows = []
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            r = json.loads(line)
            if "error" not in r:
                rows.append(r)
    return rows


def crossover_k(cold_b, warm_b, cold_m, warm_m):
    """Smallest integer K>=1 where baseline+cache session <= bioma session.
    session_baseline(K) = cold_b + (K-1)*warm_b ; likewise bioma.
    Returns None if baseline never catches up (warm_b >= warm_m)."""
    if warm_b >= warm_m:
        return None  # baseline warm call is not cheaper -> never overtakes
    # cold_b + (K-1) wb <= cold_m + (K-1) wm  ->  (K-1)(wb-wm) <= cold_m-cold_b
    k_minus_1 = (cold_m - cold_b) / (warm_b - warm_m)  # both sides handled by sign
    k = int(np.ceil(k_minus_1 + 1))
    return max(k, 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", default=str(DEFAULT))
    args = ap.parse_args()
    rows = load(args.results)
    if not rows:
        print("no rows")
        return 1

    # index by (model, task) -> {(arm,cache): row}
    idx = defaultdict(dict)
    for r in rows:
        idx[(r["model"], r["task"])][(r["arm"], r["cache"])] = r

    warmup = rows[0].get("warmup")
    print(f"caching A/B — {len(idx)} (model,task) cells, warmup={warmup} reused calls, "
          f"real OpenRouter billed cost\n")

    per_model = defaultdict(list)
    bioma_cacheable = 0
    cells = 0
    uninformative = 0
    for (model, task), arms in sorted(idx.items()):
        need = [("baseline", True), ("bioma", True), ("baseline", False), ("bioma", False)]
        if not all(k in arms for k in need):
            print(f"  skip {model}/{task}: missing arms {[k for k in need if k not in arms]}")
            continue
        bc = arms[("baseline", True)]     # baseline + cache = the buyer's world
        mc = arms[("bioma", True)]        # bioma + cache
        # A safety-refused call is billed at $0 by OpenRouter. If the baseline
        # session is ~free, the model refused the big payload for free while
        # BIOMA (smaller payload) may have escaped the refusal and paid — a
        # refusal artifact, NOT a caching signal. Exclude from the cost headline.
        if bc["session_cost_usd"] < 5e-4:
            uninformative += 1
            continue
        cells += 1
        save = bc["session_cost_usd"] - mc["session_cost_usd"]
        save_pct = 100 * save / bc["session_cost_usd"] if bc["session_cost_usd"] else 0
        if mc.get("cacheable"):
            bioma_cacheable += 1
        # crossover from measured cold (call 0) and warm (call 1) costs
        cold_b, warm_b = bc["cold_cost_usd"], bc["warm_cost_usd"]
        cold_m, warm_m = mc["cold_cost_usd"], mc["warm_cost_usd"]
        k = crossover_k(cold_b, warm_b, cold_m, warm_m) if warm_b and warm_m else None
        per_model[model].append({"task": task, "save_pct": save_pct,
                                 "bc": bc["session_cost_usd"], "mc": mc["session_cost_usd"],
                                 "k": k, "bioma_cacheable": bool(mc.get("cacheable"))})

    for model, items in per_model.items():
        print(f"== {model} — {len(items)} tasks ==")
        sp = np.array([i["save_pct"] for i in items])
        ks = [i["k"] for i in items if i["k"] is not None]
        always = [i for i in items if i["k"] is None]  # baseline never overtakes
        print(f"  BIOMA saving on top of caching : median {np.median(sp):.0f}%  "
              f"(min {sp.min():.0f}%, max {sp.max():.0f}%)")
        print(f"  shielded payload cacheable     : {sum(i['bioma_cacheable'] for i in items)}/{len(items)} tasks")
        print(f"  BIOMA cheaper at EVERY length  : {len(always)}/{len(items)} tasks")
        if ks:
            print(f"  of the {len(ks)} that cross   : caching-alone overtakes at K* "
                  f"median {int(np.median(ks))} reuses (range {min(ks)}-{max(ks)})")
        print()

    # pooled headline
    all_sp = np.array([i["save_pct"] for items in per_model.values() for i in items])
    all_k = [i["k"] for items in per_model.values() for i in items if i["k"] is not None]
    print("== pooled ==")
    print(f"  cells analyzed                 : {cells} "
          f"(excluded {uninformative} free-refusal cells: baseline billed $0)")
    print(f"  BIOMA vs baseline+caching      : median {np.median(all_sp):.0f}% cheaper "
          f"per {warmup}-reuse session")
    print(f"  shielded payload cacheable     : {bioma_cacheable}/{cells} cells "
          f"(too small for the ~4-6k-token Anthropic minimum)")
    all_always = sum(1 for items in per_model.values() for i in items if i["k"] is None)
    print(f"  BIOMA cheaper at EVERY length   : {all_always}/{cells} cells")
    if all_k:
        print(f"  of the {len(all_k)} that cross  : caching-alone overtakes at K* "
              f"median {int(np.median(all_k))} reuses (same-context worst case)")
    print("\n  Note: 'same context reused K times' is the WORST case for BIOMA (best for")
    print("  caching). In growing conversations the added tail is never in the cached")
    print("  prefix, so BIOMA's advantage holds longer. Output tokens are equal across")
    print("  arms and are included in the billed cost above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
