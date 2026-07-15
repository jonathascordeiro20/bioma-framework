#!/usr/bin/env python3
"""
tests/e2e_claude_code.py — o E2E que o protocolo de benchmark original pedia:
o Claude Code REAL (CLI headless) corrigindo um bug real num repositório real,
direto na API vs pela `ANTHROPIC_BASE_URL` do gateway BIOMA.

Mede, apples-to-apples (mesmo agente, mesma tarefa, só a base_url muda):
custo acumulado (`total_cost_usd`) e sucesso (pytest verde) por braço, mais a
redução por request registrada no audit log do gateway.

Requer:
  * gateway rodando em modo ponte:
      set BIOMA_FORCE_KEY=1 ; uvicorn bioma.gateway:app --port 8790
  * `claude` CLI instalado.

    python tests/e2e_claude_code.py --max-turns 15 --model anthropic/claude-sonnet-5
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

BUGGY = '''\
from datetime import date, timedelta


def days_in_month(year, month):
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def month_window(year, month):
    """BUG: consumers filter with ts < end (exclusive), dropping the last day."""
    start = date(year, month, 1)
    end = start + timedelta(days=days_in_month(year, month) - 1)
    return start, end
'''

TEST = '''\
from datetime import date
from window import month_window


def test_includes_last_day():
    start, end = month_window(2026, 2)
    assert start == date(2026, 2, 1)
    assert end == date(2026, 3, 1)   # exclusive filter must include Feb 28


def test_december_rolls_over():
    _, end = month_window(2026, 12)
    assert end == date(2027, 1, 1)
'''

PROMPT = ("The repo has failing tests. Read window.py, fix the off-by-one bug in "
          "month_window so `pytest` passes, then run pytest to confirm. Reply DONE "
          "when green.")


def make_repo() -> str:
    d = tempfile.mkdtemp(prefix="bioma_cc_")
    with open(os.path.join(d, "window.py"), "w") as f:
        f.write(BUGGY)
    with open(os.path.join(d, "test_window.py"), "w") as f:
        f.write(TEST)
    return d


def pytest_green(repo: str) -> bool:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", repo],
                       capture_output=True, text=True, timeout=120)
    return r.returncode == 0


def run_claude(repo: str, base_url: str, model: str, max_turns: int,
               api_key: str) -> dict:
    env = dict(os.environ)
    env.update({
        "ANTHROPIC_BASE_URL": base_url,
        "ANTHROPIC_API_KEY": api_key,
        "ANTHROPIC_MODEL": model,
        "ANTHROPIC_SMALL_FAST_MODEL": model,
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    })
    cmd = ["claude", "-p", PROMPT, "--output-format", "json",
           "--model", model, "--max-turns", str(max_turns),
           "--dangerously-skip-permissions"]
    r = subprocess.run(cmd, cwd=repo, env=env, capture_output=True,
                       text=True, timeout=900)
    try:
        j = json.loads(r.stdout)
    except (ValueError, json.JSONDecodeError):
        return {"error": (r.stdout or r.stderr)[:200], "cost": 0.0,
                "turns": 0, "in_tok": 0}
    return {"error": None if not j.get("is_error") else j.get("result", "?")[:120],
            "cost": float(j.get("total_cost_usd", 0) or 0),
            "turns": int(j.get("num_turns", 0) or 0),
            "in_tok": int((j.get("usage") or {}).get("input_tokens", 0) or 0)}


def audit_reduction(path: str) -> dict:
    if not os.path.exists(path):
        return {"before": 0, "after": 0, "requests": 0}
    before = after = n = 0
    for line in open(path, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        before += r.get("tokens_before", 0)
        after += r.get("tokens_after", 0)
        n += 1
    return {"before": before, "after": after, "requests": n}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="anthropic/claude-sonnet-5")
    ap.add_argument("--max-turns", type=int, default=15)
    ap.add_argument("--port", type=int, default=8790)
    args = ap.parse_args()

    import httpx
    try:
        httpx.get(f"http://127.0.0.1:{args.port}/health", timeout=5).raise_for_status()
    except Exception:
        print(f"gateway não responde — inicie em modo ponte: "
              f"set BIOMA_FORCE_KEY=1 & uvicorn bioma.gateway:app --port {args.port}")
        return 3

    audit = os.environ.get("BIOMA_AUDIT_LOG",
                           os.path.join(_ROOT, "bioma_gateway_audit.jsonl"))
    gw_url = f"http://127.0.0.1:{args.port}"
    print("=" * 96)
    print("  B.I.O.M.A. — E2E com o Claude Code REAL (CLI) · direto vs gateway")
    print("=" * 96)
    print(f"  modelo {args.model} · repo real (off-by-one) · claude -p headless · "
          f"max-turns {args.max_turns}\n")

    # braço A (direto) exige a chave REAL do OpenRouter (Claude Code a envia como
    # x-api-key, e o OpenRouter aceita); braço B (gateway em modo ponte) ignora a
    # chave do cliente e usa a OPENROUTER_API_KEY do .env — dummy serve.
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(_ROOT, ".env"))
    except Exception:
        pass
    real_key = os.environ.get("OPENROUTER_API_KEY", "")

    rows = {}
    for arm, base, key in (("A direto", "https://openrouter.ai/api", real_key),
                           ("B gateway", gw_url, "sk-bridge-dummy")):
        repo = make_repo()
        if arm.startswith("B"):
            open(audit, "w").close()  # zera o audit para medir só o braço B
        print(f"— braço {arm} (base_url {base}) ...", flush=True)
        res = run_claude(repo, base, args.model, args.max_turns, key)
        res["solved"] = pytest_green(repo) and not res["error"]
        rows[arm] = res
        shutil.rmtree(repo, ignore_errors=True)
        st = "RESOLVIDO" if res["solved"] else ("ERRO" if res["error"] else "FALHOU")
        extra = f" · {res['error']}" if res["error"] else ""
        print(f"    {st:10s} · {res['turns']} turnos · ${res['cost']:.4f}{extra}")

    red = audit_reduction(audit)
    print("\n" + "=" * 96)
    print("## Veredito — Claude Code real de ponta a ponta\n")
    print("| Métrica | A direto | B gateway |")
    print("| :--- | ---: | ---: |")
    a, b = rows["A direto"], rows["B gateway"]
    print(f"| Custo acumulado (Claude Code) | ${a['cost']:.4f} | ${b['cost']:.4f} |")
    print(f"| Turnos | {a['turns']} | {b['turns']} |")
    print(f"| Bug resolvido (pytest verde) | {'✅' if a['solved'] else '❌'} "
          f"| {'✅' if b['solved'] else '❌'} |")
    if a["cost"] > 0:
        print(f"\nEconomia de custo do gateway: **−{(1-b['cost']/a['cost'])*100:.0f}%**")
    if red["before"]:
        print(f"\nApoptose no histórico de conversa (audit do braço B, {red['requests']} "
              f"requests): {red['before']:,} → {red['after']:,} tokens "
              f"(−{(1-red['after']/red['before'])*100:.0f}%). O system prompt gigante do "
              "Claude Code é preservado (top-level, nunca purgado); a economia vem do "
              "histórico acumulado de ferramentas/turnos.")
    out = os.path.join(_ROOT, "resultados", "e2e_claude_code.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"model": args.model, "A": a, "B": b, "audit": red}, f, indent=2)
    print(f"\n📄 dados: {out}")
    return 0 if (b["solved"] or not a["solved"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
