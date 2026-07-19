#!/usr/bin/env python3
"""Item 1b — the GROWING-conversation scenario (BIOMA's home turf).

The static-reuse test (run_benchmark_cached.py) is BIOMA's worst case: the same
context reused, fully cacheable. Real sessions GROW — each turn appends history.
Native caching discounts the stable prefix but you STILL pay the cache-read rate
on the ENTIRE growing history every turn. BIOMA deletes stale turns, keeping the
sent history bounded. So over a long conversation:

  baseline + cache : per-turn cost ~ 0.1x x (accumulated history) + new delta
                     -> cumulative grows ~quadratically with turns
  BIOMA    + cache : apoptosis caps the history -> cumulative grows ~linearly

This measures that divergence with real billed cost. Each step t reveals more of
the task's session history; the query is held fixed so only history growth moves
cost. cache_control marks the (growing) stable prefix each turn.

Two arms only (baseline+cache vs bioma+cache) — Item 1 already covered no-cache.
Anthropic models (opt-in caching). No --mock. Writes results/cached/results_growing.jsonl.

Usage:
  python run_benchmark_growing.py --models claude-haiku --tasks 5 --steps 8
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time

import httpx

from run_benchmark import CognitiveFirewall, load_roster
from run_benchmark_cached import call_once, ANTHROPIC

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "results" / "cached" / "results_growing.jsonl"


def history_text(task: dict, k: int) -> str:
    """System + the first k session turns, as one string."""
    parts = []
    if task.get("system"):
        parts.append(task["system"])
    for m in task["session_turns"][:k]:
        c = m.get("content", "")
        parts.append(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))
    return "\n".join(parts)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models", default="claude-haiku")
    ap.add_argument("--tasks", type=int, default=5)
    ap.add_argument("--steps", type=int, default=8, help="conversation turns simulated")
    ap.add_argument("--base-turns", type=int, default=4, help="history turns at step 1")
    ap.add_argument("--chunk", type=int, default=6, help="turns added per step")
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("OPENROUTER_API_KEY not set", file=sys.stderr)
        return 2
    roster = load_roster()
    names = [n.strip() for n in args.models.split(",")]
    bad = [n for n in names if n not in roster or n not in ANTHROPIC]
    if bad:
        print(f"not controllable-cache Anthropic models: {bad}", file=sys.stderr)
        return 2

    with open(ROOT / "tasks.json", encoding="utf-8") as f:
        tasks = json.load(f)[: args.tasks]

    fw = CognitiveFirewall()
    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n = 0
    with httpx.Client() as client, open(out_path, "a", encoding="utf-8") as out:
        for name in names:
            model_id = roster[name]["openrouter_id"]
            for task in tasks:
                n_turns = len(task["session_turns"])
                for t in range(1, args.steps + 1):
                    k = min(args.base_turns + (t - 1) * args.chunk, n_turns)
                    base_hist = history_text(task, k)
                    base_stable = base_hist + "\n" + task["final_prompt"]
                    h = fw.shield(task["session_turns"][:k], task["final_prompt"],
                                  system=task.get("system"))
                    bioma_stable = ((h.system or "") + "\n" + h.prompt)
                    for arm, stable in (("baseline", base_stable), ("bioma", bioma_stable)):
                        try:
                            c = call_once(client, key, model_id, stable, True, args.max_tokens)
                        except Exception as exc:
                            row = {"model": name, "task": task["id"], "arm": arm,
                                   "step": t, "history_turns": k,
                                   "error": f"{type(exc).__name__}: {exc}"}
                            out.write(json.dumps(row) + "\n"); out.flush(); os.fsync(out.fileno())
                            print(f"  ERROR {name}/{task['id']}/{arm}/step{t}: {exc}", file=sys.stderr)
                            n += 1
                            continue
                        row = {"model": name, "task": task["id"],
                               "stale_ratio": task.get("stale_ratio"), "arm": arm,
                               "step": t, "history_turns": k,
                               "prompt_tokens": c["prompt_tokens"],
                               "cached_tokens": c["cached_tokens"],
                               "cache_write_tokens": c["cache_write_tokens"],
                               "cost_usd": c["cost_usd"]}
                        out.write(json.dumps(row) + "\n"); out.flush(); os.fsync(out.fileno())
                        n += 1
                        print(f"  {name:>12} {task['id']:>18} step{t:>2} k={k:>2} "
                              f"{arm:>8}: in={c['prompt_tokens']:>6} cost=${c['cost_usd']:.5f}")
                        time.sleep(0.8)
    print(f"\n{n} rows -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
