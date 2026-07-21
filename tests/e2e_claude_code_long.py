#!/usr/bin/env python3
"""
tests/e2e_claude_code_long.py — E2E de SESSÃO LONGA com o Claude Code real.

O e2e_claude_code.py prova a transparência do gateway numa tarefa curta (8
requests → apoptose −0%, comportamento correto: sem peso morto não há poda).
Este teste fecha o degrau que faltava: uma sessão de 30+ turnos onde o audit
DEVE mostrar a apoptose agindo sobre o histórico acumulado de ferramentas,
com pytest verde nos dois braços.

Método: repositório com 5 módulos bugados, cada um com sua suíte de testes.
O prompt obriga o agente a trabalhar UM módulo por vez (ler → corrigir →
rodar o pytest daquele módulo), mais a leitura inicial de um CONVENTIONS.md
verboso — turnos antigos viram peso morto enquanto a sessão avança.

Mede, apples-to-apples (mesmo agente, mesma tarefa, só a base_url muda):
  * sucesso (pytest verde nos 5 módulos) por braço;
  * custo acumulado e turnos por braço;
  * no braço B, a redução POR REQUEST do audit — a curva da apoptose
    crescendo com o tamanho da sessão.

Requer gateway em modo ponte (recomendação para agentes: threshold 0.2):
    set BIOMA_FORCE_KEY=1
    set BIOMA_SAFE_THRESHOLD=0.2
    uvicorn bioma.gateway:app --port 8790

    python tests/e2e_claude_code_long.py --max-turns 45 --model anthropic/claude-sonnet-5
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

# --------------------------------------------------------------------------- #
#  O repositório — 5 bugs independentes, cada um com gate executável próprio
# --------------------------------------------------------------------------- #
MODULES = {
    "slugify.py": '''\
import re


def slugify(title):
    """BUG: consumers expect lowercase slugs; case is preserved."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")
    return slug
''',
    "test_slugify.py": '''\
from slugify import slugify


def test_lowercase():
    assert slugify("Hello World") == "hello-world"


def test_symbols_collapse():
    assert slugify("A  --  B!!") == "a-b"
''',
    "stats.py": '''\
def median(values):
    """BUG: even-length lists return the upper-middle element, not the mean."""
    s = sorted(values)
    return s[len(s) // 2]
''',
    "test_stats.py": '''\
from stats import median


def test_odd():
    assert median([3, 1, 2]) == 2


def test_even_is_mean_of_middles():
    assert median([1, 2, 3, 4]) == 2.5
''',
    "interval.py": '''\
def overlaps(a_start, a_end, b_start, b_end):
    """BUG: intervals are half-open [start, end); touching ends must NOT overlap."""
    return a_start <= b_end and b_start <= a_end
''',
    "test_interval.py": '''\
from interval import overlaps


def test_real_overlap():
    assert overlaps(1, 5, 4, 8)


def test_touching_is_not_overlap():
    assert not overlaps(1, 5, 5, 8)
''',
    "cart.py": '''\
def total(subtotal, discount_pct, tax_pct):
    """BUG: discount must apply BEFORE tax, and tax on the discounted amount."""
    taxed = subtotal * (1 + tax_pct / 100)
    return round(taxed * (1 - discount_pct / 100), 2)
''',
    "test_cart.py": '''\
from cart import total


def test_discount_then_tax():
    # 100 -10% = 90; 90 +8% tax = 97.2
    assert total(100, 10, 8) == 97.2


def test_no_discount():
    assert total(50, 0, 10) == 55.0
''',
    "paginate.py": '''\
def page_count(n_items, per_page):
    """BUG: partial last page is dropped (floor instead of ceil)."""
    if per_page <= 0:
        raise ValueError("per_page must be positive")
    return n_items // per_page
''',
    "test_paginate.py": '''\
import pytest
from paginate import page_count


def test_exact():
    assert page_count(20, 10) == 2


def test_partial_last_page():
    assert page_count(21, 10) == 3


def test_zero_items():
    assert page_count(0, 10) == 0


def test_invalid():
    with pytest.raises(ValueError):
        page_count(10, 0)
''',
}

CONVENTIONS = (
    "# Engineering conventions (read before touching code)\n\n"
    + "".join(
        f"{i}. Keep public signatures stable; fix behavior, not interfaces. "
        f"Prefer minimal diffs; never reformat unrelated lines. Run the module's "
        f"own test file right after each fix before moving on. (rule {i})\n"
        for i in range(1, 41)
    )
    + "\nSummary: fix one module at a time; verify each with its own test file; "
    "finish with the full suite.\n"
)

PROMPT = (
    "This repo has 5 modules with failing tests (slugify, stats, interval, cart, "
    "paginate). First read docs/CONVENTIONS.md. Then fix the modules STRICTLY ONE "
    "AT A TIME, in this order: slugify, stats, interval, cart, paginate. For each "
    "module: read it, read its test file, fix the bug, then run ONLY that module's "
    "test file with pytest and confirm it passes before moving to the next. Do not "
    "batch edits across modules. After all 5 are fixed, run the FULL pytest suite "
    "and reply DONE when everything is green."
)


def make_repo() -> str:
    d = tempfile.mkdtemp(prefix="bioma_cc_long_")
    os.makedirs(os.path.join(d, "docs"))
    with open(os.path.join(d, "docs", "CONVENTIONS.md"), "w", encoding="utf-8") as f:
        f.write(CONVENTIONS)
    for name, body in MODULES.items():
        with open(os.path.join(d, name), "w", encoding="utf-8") as f:
            f.write(body)
    return d


def pytest_green(repo: str) -> bool:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", repo],
                       capture_output=True, text=True, timeout=180)
    return r.returncode == 0


def run_claude(repo: str, base_url: Optional[str], model: str, max_turns: int,
               api_key: Optional[str]) -> dict:
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    if api_key is None:
        # modo ASSINATURA: sem chave — o CLI usa o login OAuth local. Sem
        # base_url no braço A (API nativa); no braço B só o base_url muda e o
        # gateway repassa o Bearer OAuth + anthropic-beta ao upstream nativo.
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
        if base_url:
            env["ANTHROPIC_BASE_URL"] = base_url
        else:
            env.pop("ANTHROPIC_BASE_URL", None)
    else:
        env.update({
            "ANTHROPIC_BASE_URL": base_url,
            "ANTHROPIC_AUTH_TOKEN": api_key,
            "ANTHROPIC_MODEL": model,
            "ANTHROPIC_SMALL_FAST_MODEL": model,
        })
    cmd = ["claude", "-p", PROMPT, "--output-format", "json",
           "--model", model, "--max-turns", str(max_turns),
           "--dangerously-skip-permissions"]
    r = subprocess.run(cmd, cwd=repo, env=env, capture_output=True,
                       text=True, timeout=2400)
    try:
        j = json.loads(r.stdout)
    except (ValueError, json.JSONDecodeError):
        return {"error": (r.stdout or r.stderr)[:200], "cost": 0.0,
                "turns": 0, "in_tok": 0}
    u = j.get("usage") or {}
    return {"error": None if not j.get("is_error") else j.get("result", "?")[:120],
            "cost": float(j.get("total_cost_usd", 0) or 0),
            "turns": int(j.get("num_turns", 0) or 0),
            "in_tok": int(u.get("input_tokens", 0) or 0),
            "out_tok": int(u.get("output_tokens", 0) or 0),
            # métricas REAIS de prompt cache reportadas pelo provedor
            "cache_read": int(u.get("cache_read_input_tokens", 0) or 0),
            "cache_creation": int(u.get("cache_creation_input_tokens", 0) or 0)}


def audit_rows(path: str) -> list[dict]:
    rows = []
    if not os.path.exists(path):
        return rows
    for line in open(path, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if "tokens_before" in r:
            rows.append(r)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="anthropic/claude-sonnet-5")
    ap.add_argument("--max-turns", type=int, default=45)
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--skip-a", action="store_true", help="roda só o braço B (gateway)")
    ap.add_argument("--subscription", action="store_true",
                    help="usa o login OAuth do Claude Code (sem chave); braço A = API "
                         "nativa, braço B = gateway com BIOMA_UPSTREAM nativo")
    args = ap.parse_args()
    if args.subscription and args.model.startswith("anthropic/"):
        args.model = "sonnet"  # alias nativo do CLI, janela reconhecida

    import httpx
    try:
        httpx.get(f"http://127.0.0.1:{args.port}/health", timeout=5).raise_for_status()
    except Exception:
        print(f"gateway não responde — inicie em modo ponte: set BIOMA_FORCE_KEY=1 & "
              f"set BIOMA_SAFE_THRESHOLD=0.2 & uvicorn bioma.gateway:app --port {args.port}")
        return 3

    audit = os.environ.get("BIOMA_AUDIT_LOG",
                           os.path.join(_ROOT, "bioma_gateway_audit.jsonl"))
    gw_url = f"http://127.0.0.1:{args.port}"
    print("=" * 96)
    print("  B.I.O.M.A. — E2E SESSÃO LONGA · Claude Code real · 5 bugs em série · direto vs gateway")
    print("=" * 96)
    print(f"  modelo {args.model} · max-turns {args.max_turns} · "
          f"threshold agente 0.2 esperado no gateway\n")

    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(_ROOT, ".env"))
    except Exception:
        pass
    real_key = os.environ.get("OPENROUTER_API_KEY", "")

    if args.subscription:
        arms = [("A direto", None, None),          # API nativa, OAuth do CLI
                ("B gateway", gw_url, None)]       # gateway pass-through OAuth
    else:
        arms = [("A direto", "https://openrouter.ai/api", real_key),
                ("B gateway", gw_url, "sk-bridge-dummy")]
    if args.skip_a:
        arms = arms[1:]

    rows = {}
    for arm, base, key in arms:
        repo = make_repo()
        if arm.startswith("B"):
            open(audit, "w").close()
        print(f"— braço {arm} (base_url {base}) ...", flush=True)
        res = run_claude(repo, base, args.model, args.max_turns, key)
        res["solved"] = pytest_green(repo) and not res["error"]
        rows[arm] = res
        shutil.rmtree(repo, ignore_errors=True)
        st = "RESOLVIDO" if res["solved"] else ("ERRO" if res["error"] else "FALHOU")
        extra = f" · {res['error']}" if res["error"] else ""
        print(f"    {st:10s} · {res['turns']} turnos · ${res['cost']:.4f}{extra}", flush=True)

    print("\n" + "=" * 96)
    print("## Veredito — sessão longa de ponta a ponta\n")
    print("| Métrica | " + " | ".join(rows) + " |")
    print("| :--- | " + " | ".join("---:" for _ in rows) + " |")
    print("| Custo acumulado | " + " | ".join(f"${r['cost']:.4f}" for r in rows.values()) + " |")
    print("| Turnos | " + " | ".join(str(r["turns"]) for r in rows.values()) + " |")
    print("| 5 módulos verdes (pytest) | "
          + " | ".join("✅" if r["solved"] else "❌" for r in rows.values()) + " |")
    a, b = rows.get("A direto"), rows.get("B gateway")
    if a and b and a["cost"] > 0:
        delta = (1 - b["cost"] / a["cost"]) * 100
        sinal = "economia" if delta >= 0 else "custo EXTRA"
        print(f"\nContabilidade do cliente (Claude Code): {sinal} do gateway de {abs(delta):.0f}%"
              f" (turnos {a['turns']} vs {b['turns']} — variância do agente incluída).")

    rws = audit_rows(audit)
    if rws:
        tb = sum(r["tokens_before"] for r in rws)
        ta = sum(r["tokens_after"] for r in rws)
        print(f"\n## Apoptose no braço B — {len(rws)} requests\n")
        print(f"Total histórico: {tb:,} → {ta:,} tokens "
              f"(−{(1 - ta / tb) * 100:.1f}%)" if tb else "audit vazio")
        print("\n| request | tokens antes | depois | redução | blocos purgados |")
        print("| ---: | ---: | ---: | ---: | ---: |")
        step = max(1, len(rws) // 12)
        for i, r in enumerate(rws):
            if i % step and i != len(rws) - 1:
                continue
            red = (1 - r["tokens_after"] / r["tokens_before"]) * 100 if r["tokens_before"] else 0
            print(f"| {i + 1} | {r['tokens_before']:,} | {r['tokens_after']:,} "
                  f"| −{red:.1f}% | {r.get('blocks_purged', 0)} |")

    out = os.path.join(_ROOT, "results", "e2e_claude_code_long.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"model": args.model, "arms": rows, "audit": rws}, f, indent=2)
    print(f"\n📄 dados: {out}")
    ok = all(r["solved"] for r in rows.values())
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
