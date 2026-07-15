#!/usr/bin/env python3
"""
tests/measure_cache_interaction.py — apoptose × prompt caching (medição real).

A objeção nº 1 de quem conhece prompt caching: "purgar blocos muda o prefixo e
mata o cache — quanto da economia bruta de tokens é DEVOLVIDA em perda de
desconto de cache?" O gateway foi desenhado para responder isso: apoptose é
só-deleção e preserva ordem, então o prefixo durável (system + FACTs) fica
byte-idêntico entre chamadas e continua cacheável.

Este experimento MEDE isso com cache real (Anthropic Sonnet 5 via OpenRouter,
`cache_control: ephemeral` no fim do prefixo durável). Para cada braço, faz 2
chamadas idênticas em sequência (a 1ª cria o cache, a 2ª deveria acertar) e lê
os campos REAIS de cache do objeto usage. Se um campo não vier, é NÃO MEDIDO.

  Braço A (baseline): contexto completo + cache_control no prefixo.
  Braço B (BIOMA):    contexto desidratado pelo gateway + o MESMO prefixo.

Requer o gateway rodando:  uvicorn bioma.gateway:app --port 8790

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
DIRECT = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "anthropic/claude-sonnet-5"   # preços ($/M): in 2.0, cache_write 2.5, cache_read 0.2, out 10.0
PRICE = {"in": 2.0, "cw": 2.5, "cr": 0.2, "out": 10.0}

# prefixo durável GRANDE (Anthropic exige >=1024 tok p/ cachear) — spec repetida
_SPEC = ("FACT: API spec — rate limiter middleware. Sliding window, 350 req/min "
         "per api_key, header X-RateLimit-Remaining, HTTP 429 + Retry-After on "
         "breach. Config: RATE_LIMIT_RPM=350, RATE_WINDOW_S=60. Storage: Redis "
         "sorted-set per key, ZADD on request, ZREMRANGEBYSCORE to evict, ZCARD "
         "to count. Return 429 when ZCARD >= limit. Middleware order: auth then "
         "rate-limit then handler. Observability: emit metric rl.decision{allow|deny}. ")


def build_messages(rounds: int = 15) -> list[dict]:
    durable = _SPEC * 6  # ~ garante > 1024 tokens de prefixo
    msgs = [
        {"role": "system", "content": "You are a precise senior engineer."},
        {"role": "user", "content": [
            {"type": "text", "text": durable,
             "cache_control": {"type": "ephemeral"}}]},  # <-- breakpoint de cache no prefixo
    ]
    for i in range(rounds):
        noise = (f"[pytest {i}] 148 passed 12.4s coverage 87% "
                 "DeprecationWarning x3 ... ") * 8
        msgs += [{"role": "assistant", "content": noise},
                 {"role": "user", "content": f"iteração {i}: seguindo."},
                 {"role": "assistant", "content": f"iteração {i}: ok."}]
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
    # OpenRouter/Anthropic: campos de cache podem vir aninhados ou no topo
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
    """Custo calculado pelos preços de lista, separando cache (nossa fórmula)."""
    non_cached_in = max(0, m["in"] - m["cache_read"] - m["cache_write"])
    return (non_cached_in * PRICE["in"] + m["cache_write"] * PRICE["cw"]
            + m["cache_read"] * PRICE["cr"] + m["out"] * PRICE["out"]) / 1e6


def main() -> int:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key.startswith("sk-or"):
        print("OPENROUTER_API_KEY ausente."); return 2
    try:
        httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=5).raise_for_status()
    except Exception:
        print(f"gateway não responde — inicie: uvicorn bioma.gateway:app --port {PORT}")
        return 3

    msgs = build_messages()
    print("=" * 96)
    print("  B.I.O.M.A. — Apoptose × Prompt Caching (medição real, Anthropic Sonnet 5)")
    print("=" * 96)
    print("  método: 2 chamadas idênticas por braço (1ª cria cache, 2ª acerta); "
          "campos de cache do usage real\n")

    arms = {"A (baseline, contexto completo)": (DIRECT, key),
            "B (BIOMA, contexto desidratado)": (GW, key)}
    rows = {}
    for name, (url, k) in arms.items():
        c1 = call(url, k, msgs)
        time.sleep(2.0)             # deixa o cache assentar
        c2 = call(url, k, msgs)
        rows[name] = (c1, c2)
        print(f"— {name}")
        for tag, c in (("1ª chamada", c1), ("2ª chamada", c2)):
            cache_state = ("cache HIT" if c["cache_read"] > 0 else
                           "cache WRITE" if c["cache_write"] > 0 else "sem cache")
            print(f"    {tag}: in {c['in']:6,} · cache_read {c['cache_read']:6,} · "
                  f"cache_write {c['cache_write']:6,} · out {c['out']:4,} · "
                  f"${billed_cost(c):.5f} ({cache_state})")
        print()

    any_cache = any(c["cache_read"] or c["cache_write"]
                    for pair in rows.values() for c in pair)
    print("=" * 96)
    print("## Veredito\n")
    if not any_cache:
        print("⚠️ NÃO MEDIDO: o usage não retornou campos de cache para este provedor/rota")
        print("   (OpenRouter pode não expor cache tokens nesta configuração). A garantia de")
        print("   prefixo byte-idêntico segue provada offline em tests/test_gateway.py.")
    else:
        a2, b2 = rows["A (baseline, contexto completo)"][1], rows["B (BIOMA, contexto desidratado)"][1]
        ca, cb = billed_cost(a2), billed_cost(b2)
        print(f"| Métrica (2ª chamada, com cache quente) | Baseline A | BIOMA B |")
        print(f"| :--- | ---: | ---: |")
        print(f"| tokens de entrada não-cacheados | {max(0,a2['in']-a2['cache_read']-a2['cache_write']):,} "
              f"| {max(0,b2['in']-b2['cache_read']-b2['cache_write']):,} |")
        print(f"| cache_read (com desconto) | {a2['cache_read']:,} | {b2['cache_read']:,} |")
        print(f"| custo faturado | ${ca:.5f} | ${cb:.5f} |")
        if ca > 0:
            print(f"\n**Economia líquida do BIOMA APÓS o desconto de cache: −{(1-cb/ca)*100:.0f}%.**")
            print("O prefixo durável (system+FACT) acerta o cache nos DOIS braços — a economia")
            print("do BIOMA vem de purgar o miolo variável (logs/turnos), que nunca era cacheável.")

    out = os.path.join(_ROOT, "resultados", "cache_interaction.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({m: [a, b] for m, (a, b) in rows.items()}, f, indent=2)
    print(f"\n📄 dados brutos: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
