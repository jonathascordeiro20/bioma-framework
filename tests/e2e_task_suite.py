#!/usr/bin/env python3
"""
tests/e2e_task_suite.py — A/B com Claude Code REAL em N=30 tarefas distintas.

Sucessor estatístico do e2e_claude_code.py (N=1): 30 bugs de classes diferentes
(task_suite_defs.py), mesmos braços (A direto vs B gateway BIOMA), critério
objetivo (pytest verde), resultados incrementais em JSONL (retomável) e
agregação com IC bootstrap 95%.

Integridade do benchmark (offline, $0):
    python tests/e2e_task_suite.py --selftest
        prova que cada tarefa FALHA com o código bugado e PASSA com o fix de
        referência — ou seja, o critério de sucesso é real nos dois sentidos.

Execução paga (requer gateway em modo ponte + OPENROUTER_API_KEY):
    python tests/e2e_task_suite.py --run --limit 5            # piloto barato
    python tests/e2e_task_suite.py --run                      # suite completa
    python tests/e2e_task_suite.py --run --arms B             # só o braço gateway
    python tests/e2e_task_suite.py --report                   # agrega o JSONL
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

from tests.task_suite_defs import TASKS, Task  # noqa: E402

RESULTS = os.path.join(_ROOT, "resultados", "task_suite_results.jsonl")
PROMPT = ("The repo has failing tests. Read {module}, fix the bug so `pytest` "
          "passes, then run pytest to confirm. Reply DONE when green.")


# --------------------------------------------------------------------------- #
#  Task materialisation + objective verdict
# --------------------------------------------------------------------------- #
def materialize(task: Task, variant: str) -> str:
    d = tempfile.mkdtemp(prefix=f"bioma_suite_{task.key}_")
    code = task.buggy if variant == "buggy" else task.fixed
    with open(os.path.join(d, task.module), "w", encoding="utf-8") as f:
        f.write(code)
    with open(os.path.join(d, f"test_{task.module}"), "w", encoding="utf-8") as f:
        f.write(task.tests)
    return d


def pytest_green(repo: str) -> bool:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", repo],
                       capture_output=True, text=True, timeout=120)
    return r.returncode == 0


def selftest() -> int:
    """Benchmark integrity: buggy must FAIL, reference fix must PASS — all 30."""
    bad = []
    for t in TASKS:
        for variant, expect in (("buggy", False), ("fixed", True)):
            d = materialize(t, variant)
            try:
                ok = pytest_green(d)
            finally:
                shutil.rmtree(d, ignore_errors=True)
            mark = "✅" if ok == expect else "❌"
            if ok != expect:
                bad.append(f"{t.key}/{variant}")
            print(f"  {mark} {t.key:26s} {variant:5s} -> pytest {'green' if ok else 'red'}"
                  f" (esperado {'green' if expect else 'red'})")
    if bad:
        print(f"\n❌ integridade violada: {bad}")
        return 1
    print(f"\n✅ integridade comprovada: 30/30 tarefas falham bugadas e passam corrigidas.")
    return 0


# --------------------------------------------------------------------------- #
#  Claude Code arms (same mechanics the N=1 e2e validated)
# --------------------------------------------------------------------------- #
def run_claude(repo: str, base_url: str, model: str, max_turns: int,
               api_key: str, module: str) -> dict:
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env.update({
        "ANTHROPIC_BASE_URL": base_url,
        "ANTHROPIC_AUTH_TOKEN": api_key,
        "ANTHROPIC_MODEL": model,
        "ANTHROPIC_SMALL_FAST_MODEL": model,
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    })
    cmd = ["claude", "-p", PROMPT.format(module=module), "--output-format", "json",
           "--model", model, "--max-turns", str(max_turns),
           "--dangerously-skip-permissions"]
    t0 = time.perf_counter()
    try:
        r = subprocess.run(cmd, cwd=repo, env=env, capture_output=True,
                           text=True, timeout=900)
        j = json.loads(r.stdout)
        err = None if not j.get("is_error") else str(j.get("result", "?"))[:160]
        out = {"error": err,
               "cost": float(j.get("total_cost_usd", 0) or 0),
               "turns": int(j.get("num_turns", 0) or 0)}
    except Exception as exc:  # noqa: BLE001 — a arm failure is a data point
        out = {"error": f"{type(exc).__name__}: {exc}"[:160], "cost": 0.0, "turns": 0}
    out["wall_s"] = round(time.perf_counter() - t0, 1)
    return out


def load_done() -> set[tuple[str, str]]:
    done = set()
    if os.path.exists(RESULTS):
        for line in open(RESULTS, encoding="utf-8"):
            try:
                r = json.loads(line)
                done.add((r["task"], r["arm"]))
            except (ValueError, KeyError):
                continue
    return done


def run_suite(args) -> int:
    import httpx
    try:
        httpx.get(f"http://127.0.0.1:{args.port}/health", timeout=5).raise_for_status()
    except Exception:
        print(f"gateway não responde na porta {args.port} — inicie: "
              f"BIOMA_FORCE_KEY=1 BIOMA_SAFE_THRESHOLD=0.2 "
              f"python -m uvicorn bioma.gateway:app --port {args.port}")
        return 3
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(_ROOT, ".env"))
    except Exception:
        pass
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        print("OPENROUTER_API_KEY ausente.")
        return 2

    arms = {"A": ("https://openrouter.ai/api", key),
            "B": (f"http://127.0.0.1:{args.port}", "sk-bridge-dummy")}
    arms = {k: v for k, v in arms.items() if k in args.arms}
    tasks = [t for t in TASKS if not args.tasks or t.key in args.tasks][:args.limit or None]
    done = load_done() if args.resume else set()

    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    total_cost = 0.0
    print(f"suite: {len(tasks)} tarefas × braços {list(arms)} · modelo {args.model} "
          f"· máx {args.max_turns} turnos · resume={args.resume}\n")
    for t in tasks:
        for arm, (base, k) in arms.items():
            if (t.key, arm) in done:
                print(f"  ↷ {t.key:26s} {arm} (já no JSONL)")
                continue
            repo = materialize(t, "buggy")
            try:
                res = run_claude(repo, base, args.model, args.max_turns, k, t.module)
                res["solved"] = (res["error"] is None) and pytest_green(repo)
            finally:
                shutil.rmtree(repo, ignore_errors=True)
            row = {"task": t.key, "arm": arm, "model": args.model, **res,
                   "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
            with open(RESULTS, "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            total_cost += res["cost"]
            st = "✅" if res["solved"] else ("⚠ " + (res["error"] or "falhou"))[:44]
            print(f"  {t.key:26s} {arm}: {st} · {res['turns']} turnos · "
                  f"${res['cost']:.3f} · {res['wall_s']}s")
    print(f"\ncusto estimado da rodada (contabilidade do cliente): ${total_cost:.2f}")
    return report()


# --------------------------------------------------------------------------- #
#  Aggregation — success rates + bootstrap CI over per-task cost deltas
# --------------------------------------------------------------------------- #
def report() -> int:
    if not os.path.exists(RESULTS):
        print("sem resultados ainda — rode com --run.")
        return 1
    rows = [json.loads(l) for l in open(RESULTS, encoding="utf-8") if l.strip()]
    by = {}
    for r in rows:
        by.setdefault(r["arm"], {})[r["task"]] = r  # last write wins per (task, arm)

    print("\n" + "=" * 78)
    print("## Suite N=30 — agregado (JSONL: resultados/task_suite_results.jsonl)\n")
    print("| Braço | n | resolvidas | taxa | custo médio (cliente) | turnos médios |")
    print("| :--- | ---: | ---: | ---: | ---: | ---: |")
    for arm in sorted(by):
        rs = list(by[arm].values())
        ok = [r for r in rs if r.get("solved")]
        cm = sum(r["cost"] for r in rs) / len(rs)
        tm = sum(r["turns"] for r in rs) / len(rs)
        print(f"| {arm} | {len(rs)} | {len(ok)} | {len(ok)/len(rs)*100:.0f}% "
              f"| ${cm:.3f} | {tm:.1f} |")

    if "A" in by and "B" in by:
        common = sorted(set(by["A"]) & set(by["B"]))
        pairs = [(by["A"][t], by["B"][t]) for t in common
                 if by["A"][t].get("solved") and by["B"][t].get("solved")]
        if len(pairs) >= 5:
            deltas = [a["cost"] - b["cost"] for a, b in pairs]  # >0 = gateway mais barato
            rng = random.Random(42)
            boots = sorted(
                sum(rng.choices(deltas, k=len(deltas))) / len(deltas)
                for _ in range(10_000))
            lo, hi = boots[249], boots[9749]
            mean = sum(deltas) / len(deltas)
            print(f"\nΔ custo por tarefa (A−B, ambas resolvidas, n={len(pairs)}): "
                  f"média ${mean:.4f} · IC95% bootstrap [${lo:.4f}, ${hi:.4f}]")
            print("Leitura: IC inteiramente > 0 ⇒ gateway mais barato com 95% de "
                  "confiança; IC cruzando 0 ⇒ diferença não distinguível de variância "
                  "do agente. Custos = contabilidade do cliente; a redução de tokens "
                  "auditável vem do JSONL do gateway, como sempre.")
        else:
            print(f"\n(só {len(pairs)} pares com ambos os braços resolvidos — "
                  "IC exige ≥5; rode mais tarefas)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--model", default="anthropic/claude-sonnet-5")
    ap.add_argument("--max-turns", type=int, default=15)
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--limit", type=int, default=0, help="primeiras N tarefas (0 = todas)")
    ap.add_argument("--arms", default="AB", help="braços a rodar: A, B ou AB")
    ap.add_argument("--tasks", nargs="*", default=None, help="chaves específicas")
    ap.add_argument("--resume", action="store_true", default=True,
                    help="pula pares (tarefa, braço) já no JSONL (default)")
    ap.add_argument("--fresh", dest="resume", action="store_false")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if args.run:
        return run_suite(args)
    if args.report:
        return report()
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
