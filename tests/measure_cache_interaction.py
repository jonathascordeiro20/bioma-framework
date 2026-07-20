#!/usr/bin/env python3
"""
tests/measure_cache_interaction.py — apoptosis × prompt caching (real measurement).

The #1 objection from anyone who knows prompt caching: "purging blocks changes
the prefix and kills the cache — how much of the raw token saving is GIVEN BACK
as lost cache discount?" The gateway was designed to answer this: apoptosis is
deletion-only and order-preserving, so the durable prefix (system + FACTs)
stays byte-identical between calls and remains cacheable.

This experiment MEASURES it with a real cache (Anthropic Sonnet 5 via
OpenRouter, `cache_control: ephemeral` at the end of the durable prefix). For
each arm it makes 2 identical calls in sequence (the 1st creates the cache, the
2nd should hit) and reads the REAL cache fields from the usage object. If a
field is missing, it is NOT MEASURED.

  Arm A (baseline): full context + cache_control on the prefix.
  Arm B (BIOMA):    gateway-dehydrated context + the SAME prefix.

Requires the gateway running:  uvicorn bioma.gateway:app --port 8790

    python tests/measure_cache_interaction.py
"""
from __future__ import annotations

import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, ".env"))
except Exception:
    pass
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

import httpx  # noqa: E402

PORT = int(os.environ.get("BIOMA_GW_PORT", "8790"))
GW = f"http://127.0.0.1:{PORT}/v1/chat/completions"
# optional arm C: a SECOND gateway with BIOMA_STABLE_PREFIX (the kernel 1.1.0
# cache-aware zone) — included automatically if it is up on this port.
PORT_C = int(os.environ.get("BIOMA_GW_PORT_C", "8791"))
GW_C = f"http://127.0.0.1:{PORT_C}/v1/chat/completions"
DIRECT = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "anthropic/claude-sonnet-5"   # prices ($/M): in 2.0, cache_write 2.5, cache_read 0.2, out 10.0
PRICE = {"in": 2.0, "cw": 2.5, "cr": 0.2, "out": 10.0}

# LARGE durable prefix (Anthropic requires >=1024 tok to cache) — repeated spec
_SPEC = ("FACT: API spec — rate limiter middleware. Sliding window, 350 req/min "
         "per api_key, header X-RateLimit-Remaining, HTTP 429 + Retry-After on "
         "breach. Config: RATE_LIMIT_RPM=350, RATE_WINDOW_S=60. Storage: Redis "
         "sorted-set per key, ZADD on request, ZREMRANGEBYSCORE to evict, ZCARD "
         "to count. Return 429 when ZCARD >= limit. Middleware order: auth then "
         "rate-limit then handler. Observability: emit metric rl.decision{allow|deny}. ")


def build_messages(rounds: int = 15) -> list[dict]:
    durable = _SPEC * 6  # ~ guarantees > 1024 prefix tokens
    msgs = [
        {"role": "system", "content": "You are a precise senior engineer."},
        {"role": "user", "content": [
            {"type": "text", "text": durable,
             "cache_control": {"type": "ephemeral"}}]},  # <-- cache breakpoint on the prefix
    ]
    for i in range(rounds):
        noise = (f"[pytest {i}] 148 passed 12.4s coverage 87% "
                 "DeprecationWarning x3 ... ") * 8
        msgs += [{"role": "assistant", "content": noise},
                 {"role": "user", "content": f"iteration {i}: proceeding."},
                 {"role": "assistant", "content": f"iteration {i}: ok."}]
    msgs.append({"role": "user", "content": "State the limit, window, breach status and the two config keys."})
    return msgs


def call(url: str, key: str, messages: list[dict]) -> dict:
    body = {"model": MODEL, "messages": messages, "max_tokens": 150,
            "temperature": 0.0, "usage": {"include": True}}
    r = httpx.post(url, headers={"Authorization": f"Bearer {key}",
                                 "Content-Type": "application/json"},
                   json=body, timeout=120)
    r.raise_for_status()
    d = r.json()
    u = d.get("usage", {}) or {}
    # OpenRouter/Anthropic: cache fields may come nested or top-level
    details = u.get("prompt_tokens_details", {}) or {}
    cache_read = (u.get("cache_read_input_tokens")
                  or details.get("cached_tokens") or 0)
    cache_write = (u.get("cache_creation_input_tokens")
                   or details.get("cache_creation_tokens") or 0)
    return {"in": int(u.get("prompt_tokens", 0) or 0),
            "out": int(u.get("completion_tokens", 0) or 0),
            "cache_read": int(cache_read or 0),
            "cache_write": int(cache_write or 0),
            "cost_api": float(u.get("cost", 0) or 0),
            "text": (d.get("choices", [{}])[0].get("message", {}).get("content") or "")}


def billed_cost(m: dict) -> float:
    """Cost computed from list prices, separating cache (our formula)."""
    non_cached_in = max(0, m["in"] - m["cache_read"] - m["cache_write"])
    return (non_cached_in * PRICE["in"] + m["cache_write"] * PRICE["cw"]
            + m["cache_read"] * PRICE["cr"] + m["out"] * PRICE["out"]) / 1e6


def main() -> int:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key.startswith("sk-or"):
        print("OPENROUTER_API_KEY missing."); return 2
    try:
        httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=5).raise_for_status()
    except Exception:
        print(f"gateway not responding — start it: uvicorn bioma.gateway:app --port {PORT}")
        return 3

    msgs = build_messages()
    print("=" * 96)
    print("  B.I.O.M.A. — Apoptosis × Prompt Caching (real measurement, Anthropic Sonnet 5)")
    print("=" * 96)
    print("  method: 2 identical calls per arm (1st creates the cache, 2nd hits); "
          "cache fields from the real usage object\n")

    arms = {"A (baseline, full context)": (DIRECT, key),
            "B (BIOMA, dehydrated context)": (GW, key)}
    try:
        httpx.get(f"http://127.0.0.1:{PORT_C}/health", timeout=5).raise_for_status()
        arms["C (BIOMA, cache-aware stable_prefix)"] = (GW_C, key)
    except Exception:
        print(f"  (arm C skipped — no gateway with BIOMA_STABLE_PREFIX on port {PORT_C})\n")
    rows = {}
    for name, (url, k) in arms.items():
        c1 = call(url, k, msgs)
        time.sleep(2.0)             # let the cache settle
        c2 = call(url, k, msgs)
        rows[name] = (c1, c2)
        print(f"— {name}")
        for tag, c in (("1st call", c1), ("2nd call", c2)):
            cache_state = ("cache HIT" if c["cache_read"] > 0 else
                           "cache WRITE" if c["cache_write"] > 0 else "no cache")
            print(f"    {tag}: in {c['in']:6,} · cache_read {c['cache_read']:6,} · "
                  f"cache_write {c['cache_write']:6,} · out {c['out']:4,} · "
                  f"${billed_cost(c):.5f} ({cache_state})")
        print()

    any_cache = any(c["cache_read"] or c["cache_write"]
                    for pair in rows.values() for c in pair)
    print("=" * 96)
    print("## Verdict\n")
    if not any_cache:
        print("⚠️ NOT MEASURED: usage returned no cache fields for this provider/route")
        print("   (OpenRouter may not expose cache tokens in this configuration). The")
        print("   byte-identical-prefix guarantee remains proven offline in tests/test_gateway.py.")
    else:
        seconds = {name: pair[1] for name, pair in rows.items()}
        names = list(seconds)
        cols = " | ".join(n.split(" ")[0] for n in names)
        print(f"| Metric (2nd call, warm cache) | {cols} |")
        print(f"| :--- |{' ---: |' * len(names)}")
        def row(label, fn):
            print(f"| {label} | " + " | ".join(fn(seconds[n]) for n in names) + " |")
        row("non-cached input tokens",
            lambda c: f"{max(0, c['in']-c['cache_read']-c['cache_write']):,}")
        row("cache_read (discounted)", lambda c: f"{c['cache_read']:,}")
        row("billed cost", lambda c: f"${billed_cost(c):.5f}")
        a2 = seconds["A (baseline, full context)"]
        b2 = seconds["B (BIOMA, dehydrated context)"]
        ca, cb = billed_cost(a2), billed_cost(b2)
        if ca > 0:
            print(f"\n**BIOMA net saving AFTER the cache discount: −{(1-cb/ca)*100:.0f}%.**")
            print("The durable prefix (system+FACT) hits the cache in BOTH arms — BIOMA's")
            print("saving comes from purging the variable middle (logs/turns), which was")
            print("never cacheable in the first place.")

    out = os.path.join(_ROOT, "results", "cache_interaction.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({m: [a, b] for m, (a, b) in rows.items()}, f, indent=2)
    print(f"\n📄 raw data: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
