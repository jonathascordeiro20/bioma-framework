#!/usr/bin/env python3
"""
tests/reference_pilot.py — a REFERENCE self-run pilot through the gateway.

This is NOT a third-party design partner (that needs a real external org). It is
a labeled, honest reference run: a realistic accumulating agent workload — the
scenario where apoptosis actually helps — driven through the real gateway on a
real model, so the gateway's audit log captures genuine before/after per request.
The resulting ESG report is the TEMPLATE a real partner would receive, computed on
real measured traffic (ours), not invented.

Requires the gateway running:  uvicorn bioma.gateway:app --port 8790

    python tests/reference_pilot.py --rounds 20 --model z-ai/glm-5.2
"""
from __future__ import annotations

import argparse
import os
import sys

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
from openai import OpenAI  # noqa: E402

PORT = int(os.environ.get("BIOMA_GW_PORT", "8790"))
SYS = ("You are a senior SRE assistant embedded in an incident-response agent. "
       "Answer concisely and reference exact identifiers.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=20)
    ap.add_argument("--model", default="z-ai/glm-5.2")  # cheap, strong — reference run
    args = ap.parse_args()
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key.startswith("sk-or"):
        print("OPENROUTER_API_KEY ausente."); return 2
    try:
        httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=5).raise_for_status()
    except Exception:
        print(f"gateway não responde — inicie: uvicorn bioma.gateway:app --port {PORT}")
        return 3

    gw = OpenAI(base_url=f"http://127.0.0.1:{PORT}/v1", api_key=key)
    # a growing incident-response session: pinned facts + accumulating noisy tool logs
    messages = [
        {"role": "system", "content": SYS},
        {"role": "user", "content": "FACT: incident INC-7743 open; runbook RB-22; on-call rotation OPS-EU."},
        {"role": "user", "content": "FACT: SLO error budget 0.2%; alert threshold p99 > 800ms."},
    ]
    print("=" * 92)
    print("  B.I.O.M.A. — Piloto de REFERÊNCIA (self-run, rotulado) pelo gateway")
    print("=" * 92)
    print(f"  modelo {args.model} · {args.rounds} rodadas · agente que ACUMULA contexto\n")
    total = 0.0
    for i in range(1, args.rounds + 1):
        burst = (f"[metrics {i}] cpu=91 mem=68 p50=120 p95=410 p99={780+i} rps=3.4k "
                 "errors=ERR-2210 retries=312 pods=48/50 ... trace ... span ... ") * 8
        messages += [{"role": "tool", "content": burst},
                     {"role": "assistant", "content": f"round {i}: p99 trending, watching."}]
        q = f"Round {i}: given the pinned facts, what incident code and runbook apply, and is the SLO breached?"
        r = gw.chat.completions.create(
            model=args.model, messages=messages + [{"role": "user", "content": q}],
            max_tokens=120, temperature=0.0)
        total += float(getattr(r.usage, "cost", 0) or 0)
        messages.append({"role": "user", "content": q})
        messages.append({"role": "assistant", "content": r.choices[0].message.content or ""})
        if i % 5 == 0:
            print(f"  round {i:2d} | in_tok {r.usage.prompt_tokens:5,} | ${total:.4f} acum")
    print(f"\n  piloto concluído · custo real ${total:.4f} · audit em bioma_gateway_audit.jsonl")
    print("  → gere o relatório de caso: python -m bioma.esg_report bioma_gateway_audit.jsonl "
          "--grid eu --price-in 0.86")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
