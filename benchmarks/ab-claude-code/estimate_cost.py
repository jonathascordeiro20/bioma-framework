#!/usr/bin/env python3
"""Estimate the cost of the FULL benchmark run per model — without calling any API.

Full run = every task x 2 arms (baseline + bioma) x N reps.

Input tokens are measured from the real tasks.json payloads:
  * arm A: system + all session_turns + final_prompt, verbatim
  * arm B: the ACTUAL CognitiveFirewall.shield() output for each task
    (shield is pure/local — no network involved)

Output tokens per call are an assumption (--out-tokens, default 400; the runner
caps generation at 1024), so treat the totals as estimates, not quotes.

Usage: python estimate_cost.py [--reps 3] [--out-tokens 400]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib

import yaml

from bioma.firewall_client import CognitiveFirewall
from run_benchmark import approx_tokens, load_roster, usable

ROOT = pathlib.Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--out-tokens", type=int, default=400,
                    help="assumed completion tokens per call (runner cap: 1024)")
    args = ap.parse_args()

    with open(ROOT / "tasks.json") as f:
        tasks = json.load(f)

    fw = CognitiveFirewall()
    a_in = b_in = 0
    for t in tasks:
        system = t.get("system", "")
        history = "\n".join(m["content"] for m in t["session_turns"])
        a_in += approx_tokens(system + "\n" + history + "\n" + t["final_prompt"])
        h = fw.shield(t["session_turns"], t["final_prompt"], system=t.get("system"))
        b_in += approx_tokens((h.system or "") + "\n" + h.prompt)

    n_calls_per_arm = len(tasks) * args.reps
    out_tok_per_arm = n_calls_per_arm * args.out_tokens

    print(f"tasks={len(tasks)}  reps={args.reps}  arms=2  "
          f"-> {n_calls_per_arm * 2} calls per model")
    print(f"measured input tokens per rep-sweep: arm A={a_in:,}  arm B={b_in:,} "
          f"(shield reduction {100 * (1 - b_in / a_in):.1f}%)")
    print(f"assumed output tokens/call: {args.out_tokens}\n")

    header = (f"{'model':>14} {'tier':>9} {'key':>4} {'in $/M':>7} {'out $/M':>8} "
              f"{'arm A $':>8} {'arm B $':>8} {'total $':>8}")
    print(header)
    print("-" * len(header))
    grand = 0.0
    for m in load_roster().values():
        cost_a = (a_in * args.reps) / 1e6 * m["price_in"] + out_tok_per_arm / 1e6 * m["price_out"]
        cost_b = (b_in * args.reps) / 1e6 * m["price_in"] + out_tok_per_arm / 1e6 * m["price_out"]
        total = cost_a + cost_b
        has_key = "yes" if usable(m) else "no"
        if usable(m):
            grand += total
        print(f"{m['name']:>14} {m['tier']:>9} {has_key:>4} {m['price_in']:>7.2f} "
              f"{m['price_out']:>8.2f} {cost_a:>8.2f} {cost_b:>8.2f} {total:>8.2f}")
    print("-" * len(header))
    print(f"{'total (models with keys only)':>{len(header) - 9}} {grand:>8.2f}")
    print("\nNOTE: token counts use tiktoken/4-chars-per-token approximation; each")
    print("provider tokenizes differently, so expect roughly +/-25% on real usage.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
