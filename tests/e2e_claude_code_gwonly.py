#!/usr/bin/env python3
"""Braço gateway do E2E Claude Code, medindo a redução pelo audit log (o
`tokens_before` é exatamente o que uma chamada direta enviaria). Tarefa um pouco
mais longa (adicionar uma função + testes) para acumular histórico de ferramentas."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

BUGGY = '''\
from datetime import date, timedelta


def days_in_month(year, month):
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def month_window(year, month):
    """BUG: exclusive filter drops the last day."""
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
    assert end == date(2026, 3, 1)


def test_quarter_window_exists():
    from window import quarter_window
    start, end = quarter_window(2026, 1)  # Q1 = Jan..Mar
    assert start == date(2026, 1, 1)
    assert end == date(2026, 4, 1)
'''
PROMPT = ("The tests are failing. (1) Fix the off-by-one bug in month_window so the "
          "exclusive filter includes the last day. (2) Add a new function "
          "quarter_window(year, quarter) mirroring month_window for a 3-month quarter "
          "(quarter 1 = Jan..Mar, end = first day of the next quarter). Run pytest "
          "after each change until all tests pass. Reply DONE when green.")


def main() -> int:
    port = 8790
    audit = os.path.join(_ROOT, "bioma_gateway_audit.jsonl")
    import httpx
    httpx.get(f"http://127.0.0.1:{port}/health", timeout=5).raise_for_status()
    open(audit, "w").close()

    repo = tempfile.mkdtemp(prefix="bioma_cc2_")
    for name, content in (("window.py", BUGGY), ("test_window.py", TEST)):
        with open(os.path.join(repo, name), "w") as f:
            f.write(content)

    env = dict(os.environ)
    env.update({"ANTHROPIC_BASE_URL": f"http://127.0.0.1:{port}",
                "ANTHROPIC_API_KEY": "sk-bridge-dummy",
                "ANTHROPIC_MODEL": "anthropic/claude-sonnet-5",
                "ANTHROPIC_SMALL_FAST_MODEL": "anthropic/claude-sonnet-5",
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"})
    print("— Claude Code real pelo gateway (tarefa: fix + nova função + testes) ...", flush=True)
    r = subprocess.run(["claude", "-p", PROMPT, "--output-format", "json",
                        "--model", "anthropic/claude-sonnet-5", "--max-turns", "25",
                        "--dangerously-skip-permissions"],
                       cwd=repo, env=env, capture_output=True, text=True, timeout=1200)
    try:
        j = json.loads(r.stdout)
    except ValueError:
        print("saída não-JSON:", (r.stdout or r.stderr)[:300]); return 1

    green = subprocess.run([sys.executable, "-m", "pytest", "-q", repo],
                           capture_output=True, text=True).returncode == 0

    before = after = n = 0
    for line in open(audit, encoding="utf-8"):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        before += rec.get("tokens_before", 0)
        after += rec.get("tokens_after", 0)
        n += 1

    print("\n" + "=" * 92)
    print("## Claude Code real pelo gateway — resultado\n")
    print(f"  bug + feature resolvidos (pytest verde): {'SIM' if green else 'NÃO'}")
    print(f"  turnos: {j.get('num_turns')} · custo Claude Code: ${j.get('total_cost_usd', 0):.4f} "
          f"· is_error: {j.get('is_error')}")
    print(f"\n  Apoptose no histórico de conversa ({n} requests ao modelo):")
    print(f"    tokens_before {before:,} → tokens_after {after:,}")
    if before:
        print(f"    redução: −{(1-after/before)*100:.1f}%  "
              "(before = o que uma chamada direta enviaria; system prompt do Claude Code")
        print("    é preservado top-level e NÃO entra nesta contagem — isto é só o histórico)")
    import shutil
    shutil.rmtree(repo, ignore_errors=True)
    out = os.path.join(_ROOT, "resultados", "e2e_claude_code.json")
    json.dump({"solved": green, "turns": j.get("num_turns"),
               "cost": j.get("total_cost_usd"),
               "audit": {"before": before, "after": after, "requests": n}},
              open(out, "w", encoding="utf-8"), indent=2)
    print(f"\n📄 {out}")
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
