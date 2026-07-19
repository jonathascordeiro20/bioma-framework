#!/usr/bin/env python3
"""Item 1 — does BIOMA still save ON TOP of prompt caching?

The main A/B (run_benchmark.py) measured raw tokens with NO caching. A cloud
buyer's honest objection is "native prompt caching already discounts my resent
history — why BIOMA?". This script answers it with measured cost, not rhetoric.

Design — four arms per (task, model), each a session of R reused turns:

  baseline / nocache : full history, no cache_control        (raw baseline)
  baseline / cache   : full history, cache_control on prefix (the buyer's world)
  bioma    / nocache : shielded history, no cache_control     (BIOMA raw)
  bioma    / cache   : shielded history, cache_control        (BIOMA + caching)

A "session" sends the SAME payload R times (default 3): call 0 is a cold cache
WRITE (1.25x), calls 1..R-1 are warm READs (0.10x on Anthropic). Summing the
real per-call `cost` (which already reflects caching, verified via OpenRouter
usage: cache_creation / prompt_tokens_details.cached_tokens) gives each arm's
true session cost.

HONEST CRUX this measures: Anthropic's minimum cacheable prefix (~4-6k tokens on
the Bedrock route) is ABOVE the shielded BIOMA payload (~1k tokens). So the big
baseline caches (0.10x on warm) while the small BIOMA payload often CANNOT cache
at all. Whether BIOMA still wins therefore depends on session length — this run
finds the crossover instead of assuming one.

Anthropic-only by default: caching there is opt-in (cache_control), so the
nocache arm is a true no-cache control. OpenAI/DeepSeek auto-cache and cannot be
cleanly turned off, so they are excluded from this controlled 4-arm test.

Usage:
  python run_benchmark_cached.py --tasks 3 --warmup 3            # small pilot
  python run_benchmark_cached.py --models claude-haiku --tasks 10 --warmup 5
NO --mock path: this measures real billed cost. Writes results/cached/results_cached.jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time

import httpx

from run_benchmark import (CognitiveFirewall, evaluate_success,  # reuse;
                           load_roster)                          # run_benchmark.py untouched

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "results" / "cached" / "results_cached.jsonl"
UPSTREAM = "https://openrouter.ai/api/v1/chat/completions"
ANTHROPIC = {"fable-5", "claude-opus", "claude-haiku"}  # explicit cache_control models


def baseline_payload(task: dict) -> str:
    """The full baseline text: system + every session turn + the final prompt."""
    parts = []
    if task.get("system"):
        parts.append(task["system"])
    for m in task["session_turns"]:
        c = m.get("content", "")
        parts.append(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))
    parts.append(task["final_prompt"])
    return "\n".join(parts)


def bioma_payload(task: dict, fw: CognitiveFirewall) -> tuple[str, str]:
    """The shielded payload (system, prompt) exactly as the main benchmark sends it."""
    h = fw.shield(task["session_turns"], task["final_prompt"], system=task.get("system"))
    return (h.system or ""), h.prompt


def call_once(client: httpx.Client, key: str, model_id: str, stable: str,
              cache: bool, max_tokens: int) -> dict:
    """One real call. The whole stable payload is one text block; with cache=True
    it carries a cache_control breakpoint so call 0 writes and later calls read."""
    block = {"type": "text", "text": stable}
    if cache:
        block["cache_control"] = {"type": "ephemeral"}
    body = {
        "model": model_id, "max_tokens": max_tokens, "temperature": 0.2,
        "usage": {"include": True},
        "messages": [{"role": "user", "content": [block,
                     {"type": "text", "text": "\n\nRespond now."}]}],
    }
    r = client.post(UPSTREAM, headers={"Authorization": f"Bearer {key}",
                    "Content-Type": "application/json"}, json=body, timeout=600.0)
    d = r.json()
    if "error" in d:
        raise RuntimeError(str(d["error"])[:200])
    ch = d["choices"][0]
    u = d.get("usage", {}) or {}
    ptd = u.get("prompt_tokens_details") or {}
    return {
        "text": ch.get("message", {}).get("content") or "",
        "finish_reason": ch.get("finish_reason"),
        "prompt_tokens": u.get("prompt_tokens", 0),
        "cache_write_tokens": ptd.get("cache_write_tokens", 0) or 0,
        "cached_tokens": ptd.get("cached_tokens", 0) or 0,
        "output_tokens": u.get("completion_tokens", 0),
        "cost_usd": u.get("cost", 0.0),
        "input_cost_usd": (u.get("cost_details") or {}).get("upstream_inference_prompt_cost"),
    }


def run_session(client, key, model_id, stable, cache, warmup, max_tokens):
    """R reused calls; returns per-call rows + the session cost."""
    calls = []
    for i in range(warmup):
        out = call_once(client, key, model_id, stable, cache, max_tokens)
        out["call_index"] = i
        calls.append(out)
        time.sleep(1.0)  # stay within the 5-min ephemeral TTL, avoid rate spikes
    return calls


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models", help="comma-separated Anthropic model names "
                    "(default: fable-5,claude-opus,claude-haiku)")
    ap.add_argument("--tasks", type=int, default=3, help="first N tasks (0 = all)")
    ap.add_argument("--warmup", type=int, default=3, help="reused calls per session (>=1)")
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("OPENROUTER_API_KEY not set", file=sys.stderr)
        return 2

    roster = load_roster()
    names = ([n.strip() for n in args.models.split(",")] if args.models
             else ["fable-5", "claude-opus", "claude-haiku"])
    bad = [n for n in names if n not in roster or n not in ANTHROPIC]
    if bad:
        print(f"not controllable-cache Anthropic models: {bad}; "
              f"available: {sorted(ANTHROPIC)}", file=sys.stderr)
        return 2

    with open(ROOT / "tasks.json", encoding="utf-8") as f:
        tasks = json.load(f)
    if args.tasks:
        tasks = tasks[: args.tasks]

    fw = CognitiveFirewall()
    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n = 0
    with httpx.Client() as client, open(out_path, "a", encoding="utf-8") as out:
        for name in names:
            model_id = roster[name]["openrouter_id"]
            for task in tasks:
                base = baseline_payload(task)
                b_sys, b_prompt = bioma_payload(task, fw)
                bioma = (b_sys + "\n" + b_prompt) if b_sys else b_prompt
                arms = [("baseline", base, False), ("baseline", base, True),
                        ("bioma", bioma, False), ("bioma", bioma, True)]
                for arm, stable, cache in arms:
                    tag = f"{arm}/{'cache' if cache else 'nocache'}"
                    try:
                        calls = run_session(client, key, model_id, stable, cache,
                                            args.warmup, args.max_tokens)
                    except Exception as exc:
                        row = {"model": name, "task": task["id"], "arm": arm,
                               "cache": cache, "error": f"{type(exc).__name__}: {exc}"}
                        out.write(json.dumps(row) + "\n"); out.flush()
                        os.fsync(out.fileno())
                        print(f"  ERROR {name}/{task['id']}/{tag}: {exc}", file=sys.stderr)
                        n += 1
                        continue
                    session_cost = sum(c["cost_usd"] for c in calls)
                    cached_any = any(c["cache_write_tokens"] > 0 for c in calls)
                    gate = evaluate_success(task, calls[-1]["text"])
                    row = {
                        "model": name, "task": task["id"],
                        "stale_ratio": task.get("stale_ratio"), "arm": arm,
                        "cache": cache, "warmup": args.warmup,
                        "cacheable": cached_any,
                        "session_cost_usd": session_cost,
                        "cold_cost_usd": calls[0]["cost_usd"],
                        "warm_cost_usd": (calls[1]["cost_usd"] if len(calls) > 1 else None),
                        "prompt_tokens": calls[0]["prompt_tokens"],
                        "success": gate.get("success"),
                        "calls": calls,
                    }
                    out.write(json.dumps(row) + "\n"); out.flush()
                    os.fsync(out.fileno())
                    n += 1
                    print(f"  {name:>12} {task['id']:>20} {tag:>16}: "
                          f"cacheable={cached_any} session=${session_cost:.5f} "
                          f"warm=${row['warm_cost_usd']}")
    print(f"\n{n} arm-sessions -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
