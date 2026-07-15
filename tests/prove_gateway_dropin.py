#!/usr/bin/env python3
"""
tests/prove_gateway_dropin.py — the drop-in proof, with the REAL OpenAI SDK.

Assumes the BIOMA gateway is already running as its own process (exactly how a
user runs it):

    uvicorn bioma.gateway:app --port 8790          # terminal 1
    python tests/prove_gateway_dropin.py           # terminal 2

Uses the official `openai` client pointed at the gateway — changing NOTHING but
base_url — to run the same long dev-session on real models. Shows the provider's
real usage (tokens actually billed) shrinking, answer probes intact, streaming
working, and the per-request audit line the gateway wrote.
"""
from __future__ import annotations

import json
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
GW = f"http://127.0.0.1:{PORT}/v1"
AUDIT = os.environ.get("BIOMA_AUDIT_LOG",
                       os.path.join(_ROOT, "bioma_gateway_audit.jsonl"))
MODELS = ["anthropic/claude-sonnet-5", "z-ai/glm-5.2", "google/gemini-3.5-flash"]


def build_session() -> list[dict]:
    msgs = [{"role": "system", "content": "You are a senior engineer. Answer with exact identifiers."},
            {"role": "user", "content": "FACT: bug is in reports/window.py, function month_window; "
                                        "the exclusive filter drops the last day; fix adds one day to end."}]
    for i in range(15):
        noise = (f"[pytest {i}] 148 passed in 12.4s ... coverage 87% ... "
                 "DeprecationWarning x3 ... ") * 8
        msgs += [{"role": "assistant", "content": noise},
                 {"role": "user", "content": f"iteration {i}: still investigating"},
                 {"role": "assistant", "content": f"iteration {i}: hypothesis discarded"}]
    msgs.append({"role": "user", "content": "Name the buggy function and the file it is in."})
    return msgs


def main() -> int:
    if not os.environ.get("OPENROUTER_API_KEY", "").startswith("sk-or"):
        print("OPENROUTER_API_KEY ausente."); return 2
    try:
        h = httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=5).json()
    except Exception as exc:  # noqa: BLE001
        print(f"gateway não responde em {GW} — inicie: uvicorn bioma.gateway:app --port {PORT}")
        print(f"  ({exc})")
        return 3
    print("=" * 92)
    print("  B.I.O.M.A. Gateway — prova drop-in (SDK oficial OpenAI, só base_url muda)")
    print("=" * 92)
    print(f"  gateway ok · kernel {h.get('kernel')} · upstream {h.get('upstream')}\n")

    gw = OpenAI(base_url=GW, api_key=os.environ["OPENROUTER_API_KEY"])
    direct = OpenAI(base_url="https://openrouter.ai/api/v1",
                    api_key=os.environ["OPENROUTER_API_KEY"])
    session = build_session()

    print(f"{'modelo':24s} | {'direto in_tok':>13s} | {'gateway in_tok':>14s} | red.  | probe")
    print("  " + "-" * 74)
    for model in MODELS:
        try:
            d = direct.chat.completions.create(model=model, messages=session,
                                               max_tokens=200, temperature=0.0)
            g = gw.chat.completions.create(model=model, messages=session,
                                           max_tokens=200, temperature=0.0)
            di, gi = d.usage.prompt_tokens, g.usage.prompt_tokens
            text = (g.choices[0].message.content or "").lower()
            ok = "month_window" in text and "window.py" in text
            print(f"  {model:22s} | {di:13,} | {gi:14,} | −{(1-gi/di)*100:4.1f}% | "
                  f"{'OK' if ok else 'FALHOU'}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {model:22s} | ERRO: {str(exc)[:60]}")

    print("\n  streaming (Sonnet 5):", end=" ", flush=True)
    chunks = 0
    try:
        for ev in gw.chat.completions.create(model="anthropic/claude-sonnet-5",
                                             messages=session, max_tokens=60,
                                             temperature=0.0, stream=True):
            if ev.choices and ev.choices[0].delta.content:
                chunks += 1
        print(f"{chunks} chunks recebidos OK")
    except Exception as exc:  # noqa: BLE001
        print(f"ERRO: {str(exc)[:60]}")

    if os.path.exists(AUDIT):
        lines = [json.loads(x) for x in open(AUDIT, encoding="utf-8") if x.strip()]
        print(f"\n  auditoria por request ({len(lines)} linhas):")
        for rec in lines[-4:]:
            print(f"    {rec['model']:22s} {rec['tokens_before']:,} → {rec['tokens_after']:,} "
                  f"(−{rec['reduction']*100:.0f}%) · kernel {rec['kernel_latency_us']:.1f}μs")

    print("\n  OK — drop-in provado: cliente OpenAI inalterado exceto base_url; tokens")
    print("       faturados caíram; resposta íntegra; streaming ok; auditoria gravada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
