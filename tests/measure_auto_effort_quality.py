#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/measure_auto_effort_quality.py — auto-effort com GATE DE QUALIDADE.

Complementa `measure_auto_effort.py` (que mediu a mecânica de custo): aqui a
pergunta é se o orçamento dinâmico de thinking preserva a QUALIDADE da entrega.
Tasks reais da suíte A/B com gate EXECUTÁVEL (pytest sobre o código gerado),
mesmo contexto completo nos dois braços — a única variável é o thinking:

  Braço A (naive):  direto no OpenRouter, reasoning={"max_tokens": 4000} fixo.
  Braço B (BIOMA):  via gateway BIOMA_AUTO_EFFORT=1 + BIOMA_SAFE_THRESHOLD=0
                    (apoptose DESLIGADA para isolar a variável de effort).

Requer:  BIOMA_AUTO_EFFORT=1 BIOMA_SAFE_THRESHOLD=0 \
             uvicorn bioma.gateway:app --port 8793

    python tests/measure_auto_effort_quality.py
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_AB = os.path.join(_ROOT, "benchmarks", "ab-publico")
if _AB not in sys.path:
    sys.path.insert(0, _AB)
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

from run_benchmark import evaluate_success  # noqa: E402  (gate pytest da suíte A/B)

PORT = int(os.environ.get("BIOMA_GW_PORT_EFFORT", "8793"))
GW = f"http://127.0.0.1:{PORT}/v1/chat/completions"
DIRECT = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "anthropic/claude-haiku-4.5"
NAIVE_BUDGET = 4000
MAX_TOKENS = 6000
N_TASKS = 5


def call(url: str, key: str, task: dict, naive: bool) -> dict:
    msgs = []
    if task.get("system"):
        msgs.append({"role": "system", "content": task["system"]})
    msgs += list(task["session_turns"])
    msgs.append({"role": "user", "content": task["final_prompt"]})
    body = {"model": MODEL, "messages": msgs, "max_tokens": MAX_TOKENS,
            "usage": {"include": True}}
    if naive:
        body["reasoning"] = {"max_tokens": NAIVE_BUDGET}
    r = httpx.post(url, headers={"Authorization": f"Bearer {key}",
                                 "Content-Type": "application/json"},
                   json=body, timeout=300)
    r.raise_for_status()
    d = r.json()
    u = d.get("usage", {}) or {}
    det = u.get("completion_tokens_details", {}) or {}
    text = (d.get("choices", [{}])[0].get("message", {}).get("content") or "")
    return {"text": text,
            "in": int(u.get("prompt_tokens", 0) or 0),
            "out": int(u.get("completion_tokens", 0) or 0),
            "reasoning": int(det.get("reasoning_tokens", 0) or 0),
            "cost": float(u.get("cost", 0) or 0)}


def main() -> int:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key.startswith("sk-or"):
        print("OPENROUTER_API_KEY ausente."); return 2
    try:
        h = httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=5)
        h.raise_for_status()
        if h.json().get("threshold") != 0.0:
            print("gateway precisa de BIOMA_SAFE_THRESHOLD=0 (isolar o effort)")
            return 3
    except httpx.HTTPError:
        print(f"gateway não responde — inicie: BIOMA_AUTO_EFFORT=1 "
              f"BIOMA_SAFE_THRESHOLD=0 uvicorn bioma.gateway:app --port {PORT}")
        return 3

    with open(os.path.join(_AB, "tasks.json"), encoding="utf-8") as f:
        tasks = [t for t in json.load(f) if t.get("test_code")][:N_TASKS]

    print("=" * 92)
    print(f"  B.I.O.M.A. — auto-effort × QUALIDADE (gate pytest, {MODEL}, "
          f"{len(tasks)} tasks, contexto idêntico nos 2 braços)")
    print("=" * 92)

    rows, par = [], {"both_ok": 0, "both_fail": 0, "a_only": 0, "b_only": 0}
    tot = {"A": {"reasoning": 0, "cost": 0.0}, "B": {"reasoning": 0, "cost": 0.0}}
    for t in tasks:
        a = call(DIRECT, key, t, naive=True)
        b = call(GW, key, t, naive=False)
        ga = evaluate_success(t, a["text"])
        gb = evaluate_success(t, b["text"])
        sa, sb = ga["success"], gb["success"]
        par["both_ok" if sa and sb else "both_fail" if not (sa or sb)
            else "a_only" if sa else "b_only"] += 1
        for arm, c in (("A", a), ("B", b)):
            tot[arm]["reasoning"] += c["reasoning"]
            tot[arm]["cost"] += c["cost"]
        rows.append({"task": t["id"], "gate": ga.get("gate"),
                     "A": {**{k: a[k] for k in ("in", "out", "reasoning", "cost")},
                           "success": sa},
                     "B": {**{k: b[k] for k in ("in", "out", "reasoning", "cost")},
                           "success": sb}})
        print(f"  {t['id']:>22} [{ga.get('gate')}] | "
              f"A: ok={sa} think {a['reasoning']:5,} ${a['cost']:.5f} | "
              f"B: ok={sb} think {b['reasoning']:5,} ${b['cost']:.5f}")

    print("=" * 92)
    print("## Veredito\n")
    print(f"| Paridade (gate executável) | {par['both_ok']} both-ok · "
          f"{par['both_fail']} both-fail · {par['a_only']} só-A · "
          f"{par['b_only']} só-B |")
    ta, tb = tot["A"], tot["B"]
    print(f"| reasoning tokens | A {ta['reasoning']:,} → B {tb['reasoning']:,} |")
    print(f"| custo real | A ${ta['cost']:.4f} → B ${tb['cost']:.4f} |")
    divergent = par["a_only"] + par["b_only"]
    print(f"\n{'✅ QUALIDADE PRESERVADA' if divergent == 0 else '⚠️ DIVERGÊNCIA'}: "
          f"{divergent} par(es) divergente(s) em {len(tasks)}.")

    out = os.path.join(_ROOT, "resultados", "auto_effort_quality.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"model": MODEL, "naive_budget": NAIVE_BUDGET,
                   "parity": par, "totals": tot, "tasks": rows}, f, indent=2)
    print(f"📄 dados brutos: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
