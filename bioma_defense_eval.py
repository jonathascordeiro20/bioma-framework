#!/usr/bin/env python3
"""
bioma_defense_eval.py — objective security-remediation eval (ground truth, no judge)
====================================================================================
The decisive DEFENSE experiment. Given vulnerable code, each model generates a
remediation; we EXECUTE it against security + functionality checks and count passes.
Three coordination arms are compared head-to-head:

  • baseline  — one model call
  • synthesis — B.I.O.M.A. current: N candidates merged by an LLM (proven to corrupt)
  • selection — B.I.O.M.A. FIX: N candidates, keep the one that passes the most checks
                (selection-by-execution → provably >= the best candidate, can't corrupt)

SAFETY: the tasks are STRUCTURAL/benign by construction — they build an argv list
(no shell execution) or evaluate arithmetic with harmless payloads (math.pi). Even an
UNFIXED candidate executes nothing dangerous. No file/network/destructive operations.

Real only (needs a valid OPENROUTER_API_KEY). Usage:
    python bioma_defense_eval.py
    python bioma_defense_eval.py --models openai/gpt-4o x-ai/grok-4.3
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_HERE, ".env"))
except Exception:
    pass

from bioma_orchestrator.openrouter_async import AsyncOpenRouterProvider  # noqa: E402
from bioma_orchestrator.live_pipeline import ROLES  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PRETTY = {"openai/gpt-4o": "GPT-4o", "x-ai/grok-4.3": "Grok-4.3",
          "meta-llama/llama-3.3-70b-instruct": "Llama-3.3-70B",
          "anthropic/claude-fable-5": "Fable-5"}


def pretty(m):
    return PRETTY.get(m, m.split("/")[-1])


# --------------------------------------------------------------------------- #
#  Vulnerable snippets + objective security/functionality checks (all benign)
# --------------------------------------------------------------------------- #
TASKS = [
    {
        "entry": "safe_eval",
        "prompt": (
            "This function is vulnerable to arbitrary code execution. Rewrite it as "
            "`safe_eval(expr: str) -> float` that evaluates ONLY arithmetic (+ - * / and "
            "parentheses over numbers) and rejects anything else by raising an exception. "
            "Do NOT use eval/exec on the input.\n"
            "```python\n"
            "def safe_eval(expr):\n"
            "    return eval(expr)\n"
            "```"),
        "checks": [
            "safe_eval('2+3*4') == 14",
            "safe_eval('10-2') == 8",
            "abs(safe_eval('(1+2)/3') - 1.0) < 1e-9",
            "_raises(lambda: safe_eval(\"__import__('math').pi\"))",
            "_raises(lambda: safe_eval('(2).__class__'))",
            "_raises(lambda: safe_eval('[].append'))",
        ],
    },
    {
        "entry": "build_query",
        "prompt": (
            "This function is vulnerable to SQL injection via string concatenation. Rewrite "
            "it as `build_query(name: str) -> tuple` returning a PARAMETERIZED query: a tuple "
            "`(sql, params)` where `sql` uses a placeholder ('?' or '%s') and `params` carries "
            "the value. The raw `name` must never be interpolated into the SQL text.\n"
            "```python\n"
            "def build_query(name):\n"
            "    return \"SELECT * FROM users WHERE name = '\" + name + \"'\"\n"
            "```"),
        "checks": [
            "isinstance(build_query('alice'), tuple)",
            "('?' in build_query('alice')[0]) or ('%s' in build_query('alice')[0])",
            "tuple(build_query('alice')[1]) == ('alice',)",
            "\"DROP TABLE\" not in build_query(\"x'; DROP TABLE users; --\")[0]",
            "\"alice\" not in build_query('alice')[0]",
        ],
    },
    {
        "entry": "build_ping_command",
        "prompt": (
            "This function is vulnerable to command injection (shell string). Rewrite it as "
            "`build_ping_command(host: str) -> list[str]` that VALIDATES `host` (only a "
            "hostname or IPv4; reject anything with shell metacharacters) and returns an argv "
            "LIST like ['ping', host] to be run WITHOUT a shell. Raise on invalid input. Do "
            "not execute anything.\n"
            "```python\n"
            "def build_ping_command(host):\n"
            "    return 'ping ' + host   # later run with shell=True\n"
            "```"),
        "checks": [
            "isinstance(build_ping_command('8.8.8.8'), list)",
            "'8.8.8.8' in build_ping_command('8.8.8.8')",
            "all(not any(c in str(a) for c in ';&|$`<>') for a in build_ping_command('8.8.8.8'))",
            "_raises(lambda: build_ping_command('8.8.8.8; echo x'))",
            "_raises(lambda: build_ping_command('$(id)'))",
            "_raises(lambda: build_ping_command('a && b'))",
        ],
    },
]

_HARNESS = '''

def _raises(fn):
    try:
        fn(); return False
    except Exception:
        return True

def __run():
    import json as __json
    __checks = {checks!r}
    __passed = 0
    for __c in __checks:
        try:
            if eval(__c):
                __passed += 1
        except Exception:
            pass
    print("###RESULT###" + __json.dumps({{"passed": __passed, "total": len(__checks)}}))

__run()
'''


def extract_code(text: str) -> str:
    blocks = re.findall(r"```(?:python)?\s*\n(.*?)```", text or "", re.S)
    return blocks[-1] if blocks else (text or "")


def run_checks(code: str, checks) -> int:
    src = code + _HARNESS.format(checks=checks)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(src)
        path = f.name
    try:
        proc = subprocess.run([sys.executable, path], capture_output=True, text=True,
                              timeout=8, cwd=tempfile.gettempdir())
        for line in proc.stdout.splitlines():
            if line.startswith("###RESULT###"):
                return json.loads(line[len("###RESULT###"):])["passed"]
        return 0
    except Exception:
        return 0
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


async def gen_candidate(provider, prompt, model, idx):
    _n, _f, _h, sysmsg, temp = ROLES[idx]
    return await provider.complete(prompt=prompt, model=model, system=sysmsg,
                                   max_tokens=2048, temperature=temp)


async def synthesize(provider, prompt, cands, model):
    viable = [c for c in cands if not c.error and c.text]
    if len(viable) <= 1:
        return viable[0] if viable else cands[0]
    joined = "\n\n".join(f"[Candidate {i+1}]\n{c.text}" for i, c in enumerate(viable))
    sp = (f"{prompt}\n\nCandidate remediations from parallel specialists:\n{joined}\n\n"
          "Synthesise the single best, fully-correct consolidated remediation.")
    return await provider.complete(prompt=sp, model=model, system="Rigorous synthesis agent.",
                                   max_tokens=2560, temperature=0.1)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=[
        "openai/gpt-4o", "x-ai/grok-4.3", "meta-llama/llama-3.3-70b-instruct"])
    ap.add_argument("--n", type=int, default=3, help="parallel candidates")
    args = ap.parse_args()
    n = max(2, min(len(ROLES), args.n))

    key = os.environ.get("OPENROUTER_API_KEY")
    if not (key and key.startswith("sk-or")):
        print("Needs a valid OPENROUTER_API_KEY."); return 2
    provider = AsyncOpenRouterProvider()

    total = sum(len(t["checks"]) for t in TASKS)
    print("=" * 88)
    print("  B.I.O.M.A. — DEFENSE EVAL: security remediation vs executed checks (no judge)")
    print("=" * 88)
    print(f"  {len(TASKS)} vulnerabilities · {total} security/functionality checks · "
          f"models: {', '.join(pretty(m) for m in args.models)}\n")

    rows = []
    try:
        for model in args.models:
            b = s = sel = 0
            for task in TASKS:
                base = await provider.complete(prompt=task["prompt"], model=model, max_tokens=2048,
                                               system="Expert security engineer. Return ONE python code block.",
                                               temperature=0.2)
                cands = await asyncio.gather(*(gen_candidate(provider, task["prompt"], model, i)
                                               for i in range(n)))
                synth = await synthesize(provider, task["prompt"], cands, model)
                sb = run_checks(extract_code(base.text), task["checks"])
                ss = run_checks(extract_code(synth.text), task["checks"])
                cand_scores = [run_checks(extract_code(c.text), task["checks"]) for c in cands]
                ssel = max(cand_scores)
                b += sb; s += ss; sel += ssel
                print(f"  {pretty(model):14s} {task['entry']:20s} "
                      f"baseline {sb}/{len(task['checks'])} · synthesis {ss}/{len(task['checks'])} "
                      f"· selection {ssel}/{len(task['checks'])}  (cands {cand_scores})")
            rows.append((model, b, s, sel))
            print(f"  {pretty(model):14s} {'TOTAL':20s} baseline {b}/{total} · "
                  f"synthesis {s}/{total} · selection {sel}/{total}\n")
    finally:
        await provider.close()

    print("=" * 88)
    print("## B.I.O.M.A. — Defense: remediação verificada (checks executados, sem juiz)\n")
    print("| Modelo | Baseline | Síntese (atual) | Seleção-execução (fix) |")
    print("| :--- | :---: | :---: | :---: |")
    tb = ts = tsel = 0
    for model, b, s, sel in rows:
        tb += b; ts += s; tsel += sel
        print(f"| **{pretty(model)}** | {b}/{total} ({b/total:.0%}) | {s}/{total} ({s/total:.0%}) "
              f"| {sel}/{total} ({sel/total:.0%}) |")
    N = len(rows) * total
    print(f"\n**Agregado:** baseline **{tb}/{N} ({tb/N:.0%})** · síntese **{ts}/{N} ({ts/N:.0%})** "
          f"· seleção **{tsel}/{N} ({tsel/N:.0%})**.")
    print(f"\n> Ground truth: remediações executadas contra checks de segurança/funcionalidade. "
          f"Δ(seleção − baseline) = {'+' if tsel-tb>=0 else ''}{tsel-tb}; "
          f"Δ(síntese − baseline) = {'+' if ts-tb>=0 else ''}{ts-tb}. "
          f"Seleção-por-execução é monotônica: nunca abaixo do melhor candidato.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
