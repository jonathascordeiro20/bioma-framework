#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/measure_auto_effort.py — BIOMA_AUTO_EFFORT × thinking real (medição paga).

Pergunta: quanto custa um agente "naive" que liga extended thinking com
orçamento fixo em TODO turno, versus o gateway BIOMA decidindo o orçamento por
turno via effort_gauge (kernel ≥ 1.1.0)?

Workload: 10 turnos com mistura realista (7 triviais / 3 difíceis — proporção
da calibração com 1.223 prompts reais). Mesmo modelo, mesmo contexto, mesma
ordem nos dois braços:

  Braço A (naive):  direto no OpenRouter, todo turno com
                    reasoning={"max_tokens": 4000} (orçamento fixo).
  Braço B (BIOMA):  via gateway com BIOMA_AUTO_EFFORT=1, SEM parâmetro de
                    reasoning — o gateway decide (trivial → enabled:false;
                    difícil → effort por tier).

Requer o gateway com auto-effort:
    BIOMA_AUTO_EFFORT=1 uvicorn bioma.gateway:app --port 8792

    python tests/measure_auto_effort.py
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

PORT = int(os.environ.get("BIOMA_GW_PORT_EFFORT", "8792"))
GW = f"http://127.0.0.1:{PORT}/v1/chat/completions"
DIRECT = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "anthropic/claude-haiku-4.5"      # extended thinking, in $1 / out $5 por M
PRICE = {"in": 1.0, "out": 5.0}
NAIVE_BUDGET = 4000                        # orçamento fixo do braço A
MAX_TOKENS = 5000                          # precisa exceder o budget (Anthropic)

_SYSTEM = "You are a senior engineer pairing on a Python rate-limiter service."
_CONTEXT = [
    {"role": "user", "content": "We are building a sliding-window rate limiter "
     "(Redis sorted-set, 350 req/min per key, HTTP 429 + Retry-After on breach)."},
    {"role": "assistant", "content": "Understood. Middleware order: auth, then "
     "rate-limit, then handler. I'll keep decisions auditable."},
]

# 7 triviais / 3 difíceis — mesma proporção da calibração (68/23/9 off/low/med)
TURNS = [
    ("trivial", "sim, continue"),
    ("hard", "Projete e implemente a estratégia de eviction do sliding window: "
             "analise os trade-offs entre ZREMRANGEBYSCORE por chamada versus "
             "expiração preguiçosa em lote, derive o custo de memória esperado "
             "por chave ativa, compare o comportamento sob rajada adversarial e "
             "prove que o limite de 350 req/min nunca é excedido. Requisito: "
             "p99 abaixo de 2ms; restrição: nenhuma chamada Redis extra no "
             "caminho feliz."),
    ("trivial", "ok, pode seguir"),
    ("trivial", "valeu, ficou bom"),
    ("hard", "Analise o modo de falha quando o Redis particiona: derive o que "
             "acontece com contadores divergentes, compare fail-open versus "
             "fail-closed para este SLA, projete a reconciliação pós-partição "
             "e prove o limite superior de requisições extras admitidas. "
             "Restrição dura: nunca bloquear tráfego legítimo por mais de 60s."),
    ("trivial", "continua"),
    ("trivial", "sim"),
    ("hard", "Otimize o caminho quente: analise onde estão as alocações, "
             "compare pipeline Redis versus script Lua atômico, derive a "
             "latência esperada de cada um sob 10k rps e implemente a opção "
             "vencedora com justificativa. Requisito obrigatório: zero "
             "race-conditions entre instâncias."),
    ("trivial", "beleza, próximo passo"),
    ("trivial", "ok"),
]


def call(url: str, key: str, prompt: str, naive: bool) -> dict:
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": _SYSTEM}] + _CONTEXT
                    + [{"role": "user", "content": prompt}],
        "max_tokens": MAX_TOKENS,
        "usage": {"include": True},
    }
    if naive:
        body["reasoning"] = {"max_tokens": NAIVE_BUDGET}
    r = httpx.post(url, headers={"Authorization": f"Bearer {key}",
                                 "Content-Type": "application/json"},
                   json=body, timeout=300)
    r.raise_for_status()
    d = r.json()
    u = d.get("usage", {}) or {}
    det = u.get("completion_tokens_details", {}) or {}
    return {"in": int(u.get("prompt_tokens", 0) or 0),
            "out": int(u.get("completion_tokens", 0) or 0),
            "reasoning": int(det.get("reasoning_tokens", 0) or 0),
            "cost": float(u.get("cost", 0) or 0)}


def main() -> int:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key.startswith("sk-or"):
        print("OPENROUTER_API_KEY ausente."); return 2
    try:
        httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=5).raise_for_status()
    except Exception:
        print(f"gateway auto-effort não responde — inicie: "
              f"BIOMA_AUTO_EFFORT=1 uvicorn bioma.gateway:app --port {PORT}")
        return 3

    print("=" * 88)
    print("  B.I.O.M.A. — auto-effort × thinking real "
          f"({MODEL}, {len(TURNS)} turnos, braço A budget fixo {NAIVE_BUDGET})")
    print("=" * 88)

    rows = []
    tot = {"A": {"out": 0, "reasoning": 0, "cost": 0.0},
           "B": {"out": 0, "reasoning": 0, "cost": 0.0}}
    for kind, prompt in TURNS:
        a = call(DIRECT, key, prompt, naive=True)
        b = call(GW, key, prompt, naive=False)
        for arm, c in (("A", a), ("B", b)):
            tot[arm]["out"] += c["out"]
            tot[arm]["reasoning"] += c["reasoning"]
            tot[arm]["cost"] += c["cost"]
        rows.append({"kind": kind, "prompt": prompt[:60], "A": a, "B": b})
        print(f"  {kind:>7} | A: think {a['reasoning']:5,} out {a['out']:5,} "
              f"${a['cost']:.5f} | B: think {b['reasoning']:5,} out {b['out']:5,} "
              f"${b['cost']:.5f}")

    print("=" * 88)
    print("## Veredito\n")
    ta, tb = tot["A"], tot["B"]
    print(f"| Total ({len(TURNS)} turnos) | A (naive, budget fixo) | B (BIOMA auto-effort) |")
    print(f"| :--- | ---: | ---: |")
    print(f"| reasoning tokens | {ta['reasoning']:,} | {tb['reasoning']:,} |")
    print(f"| output tokens (total) | {ta['out']:,} | {tb['out']:,} |")
    print(f"| custo real (usage.cost) | ${ta['cost']:.4f} | ${tb['cost']:.4f} |")
    if ta["reasoning"]:
        print(f"\nreasoning tokens: −{(1-tb['reasoning']/ta['reasoning'])*100:.0f}%"
              f" · custo: −{(1-tb['cost']/ta['cost'])*100:.0f}%")

    out = os.path.join(_ROOT, "resultados", "auto_effort.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"model": MODEL, "naive_budget": NAIVE_BUDGET,
                   "turns": rows, "totals": tot}, f, indent=2)
    print(f"\n📄 dados brutos: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
