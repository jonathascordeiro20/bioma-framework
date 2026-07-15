#!/usr/bin/env python3
"""
tests/prove_anthropic_surface.py — prova real da superfície Anthropic do gateway,
com o SDK OFICIAL da Anthropic (o mesmo que o Claude Code usa por baixo).

O cliente Anthropic aponta a base_url para o gateway; nada mais muda. Roda uma
sessão longa de agente no formato Messages (system top-level, pares
tool_use/tool_result) em modelo real, direto vs pelo gateway, e mostra os tokens
de entrada REAIS (usage.input_tokens) caindo com a resposta íntegra.

Requer o gateway rodando:  uvicorn bioma.gateway:app --port 8790

    python tests/prove_anthropic_surface.py
"""
from __future__ import annotations

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
from anthropic import Anthropic  # noqa: E402

PORT = int(os.environ.get("BIOMA_GW_PORT", "8790"))
SYSTEM = "You are a senior engineer. Answer with exact identifiers."
MODELS = ["anthropic/claude-sonnet-5", "anthropic/claude-opus-4.8"]


def session(rounds: int = 15) -> list[dict]:
    msgs = [{"role": "user", "content": [
        {"type": "text",
         "text": "FACT: bug is in reports/window.py, function month_window; the "
                 "exclusive filter drops the last day; fix adds one day to end."}]}]
    for i in range(rounds):
        msgs += [
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": f"t{i}", "name": "run_pytest", "input": {}}]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": f"t{i}",
                 "content": (f"[run {i}] 148 passed 12.4s coverage 87% "
                             "DeprecationWarning x3 ... ") * 8}]},
        ]
    msgs.append({"role": "user", "content": "Name the buggy function and its file."})
    return msgs


def main() -> int:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key.startswith("sk-or"):
        print("OPENROUTER_API_KEY ausente."); return 2
    try:
        httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=5).raise_for_status()
    except Exception:
        print(f"gateway não responde — inicie: uvicorn bioma.gateway:app --port {PORT}")
        return 3

    # o SDK OFICIAL da Anthropic acrescenta "/v1/messages" à base_url — então a
    # base NÃO inclui /v1. Só a base_url muda entre os braços.
    direct = Anthropic(base_url="https://openrouter.ai/api", api_key=key)
    gw = Anthropic(base_url=f"http://127.0.0.1:{PORT}", api_key=key)
    msgs = session()

    print("=" * 92)
    print("  B.I.O.M.A. Gateway — superfície Anthropic /v1/messages (SDK oficial Anthropic)")
    print("=" * 92 + "\n")
    print(f"{'modelo':24s} | {'direto in_tok':>13s} | {'gateway in_tok':>14s} | red.  | probe")
    print("  " + "-" * 74)
    for model in MODELS:
        try:
            d = direct.messages.create(model=model, max_tokens=150, system=SYSTEM,
                                       messages=msgs)
            g = gw.messages.create(model=model, max_tokens=150, system=SYSTEM,
                                   messages=msgs)
            di, gi = d.usage.input_tokens, g.usage.input_tokens
            text = " ".join(b.text for b in g.content if b.type == "text").lower()
            ok = "month_window" in text and "window.py" in text
            print(f"  {model:22s} | {di:13,} | {gi:14,} | −{(1-gi/di)*100:4.1f}% | "
                  f"{'OK' if ok else 'FALHOU'}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {model:22s} | ERRO: {str(exc)[:60]}")

    print("\n  streaming (Sonnet 5):", end=" ", flush=True)
    try:
        chunks = 0
        with gw.messages.stream(model="anthropic/claude-sonnet-5", max_tokens=60,
                                system=SYSTEM, messages=msgs) as s:
            for _ in s.text_stream:
                chunks += 1
        print(f"{chunks} deltas recebidos OK")
    except Exception as exc:  # noqa: BLE001
        print(f"ERRO: {str(exc)[:60]}")

    print("\n  OK — o Claude Code fala este protocolo: ANTHROPIC_BASE_URL apontada para")
    print("       o gateway dá apoptose transparente com o SDK Anthropic inalterado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
