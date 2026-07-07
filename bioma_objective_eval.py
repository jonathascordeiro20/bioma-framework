#!/usr/bin/env python3
"""
bioma_objective_eval.py — the DEFINITIVE, judge-free efficiency test for B.I.O.M.A.
================================================================================
Instead of an LLM judge (noisy), this measures GROUND TRUTH: each model generates
code, we EXECUTE it against hidden edge-case test suites in an isolated subprocess,
and count passing tests. We compare, per model, the pure baseline (one call) vs
B.I.O.M.A. forced mitosis (N sub-agents + synthesis).

This answers the only question that matters honestly:
    Does mitosis actually make the code MORE CORRECT — or not?

Tasks are edge-case-heavy algorithmic problems (where a single shot often misses a
corner case, so mitosis has real headroom). Generated code runs in a subprocess
with a hard timeout (kills infinite loops); nothing here touches the network.

Real only (needs a valid OPENROUTER_API_KEY). Usage:
    python bioma_objective_eval.py
    python bioma_objective_eval.py --models openai/gpt-4o x-ai/grok-4.3
    python bioma_objective_eval.py --mitosis 3
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
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_HERE, ".env"))
except Exception:
    pass

from bioma_orchestrator.live_pipeline import evolve  # noqa: E402
from bioma_orchestrator.openrouter_async import AsyncOpenRouterProvider, MockAsyncProvider  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PRETTY = {"openai/gpt-4o": "GPT-4o", "x-ai/grok-4.3": "Grok-4.3",
          "meta-llama/llama-3.3-70b-instruct": "Llama-3.3-70B",
          "anthropic/claude-fable-5": "Fable-5", "anthropic/claude-opus-4.8": "Opus 4.8"}


def pretty(m):
    return PRETTY.get(m, m.split("/")[-1])


# --------------------------------------------------------------------------- #
#  Tasks — edge-case-heavy; the test suites are the ground truth
# --------------------------------------------------------------------------- #
TASKS = [
    {
        "entry": "longest_valid_parentheses",
        "prompt": ("Implement `longest_valid_parentheses(s: str) -> int` returning the length "
                   "of the longest substring of well-formed parentheses. O(n) time. "
                   "Handle '', '(', ')(', deeply nested and interleaved cases."),
        "tests": [(("",), 0), ((")(",), 0), (("()(()",), 2), (("()(())",), 6), (("(()",), 2),
                  ((")()())",), 4), (("()()",), 4), (("((()))",), 6),
                  (("()(()))))",), 6), ((")(((((()())()()))()(()))(",), 22)],
    },
    {
        "entry": "decode_string",
        "prompt": ("Implement `decode_string(s: str) -> str`. The encoding rule is k[encoded], "
                   "repeating `encoded` k times; brackets nest. e.g. '3[a2[c]]' -> 'accaccacc'."),
        "tests": [(("3[a]2[bc]",), "aaabcbc"), (("3[a2[c]]",), "accaccacc"),
                  (("2[abc]3[cd]ef",), "abcabccdcdcdef"), (("",), ""), (("abc",), "abc"),
                  (("10[a]",), "a" * 10), (("2[2[2[a]]]",), "a" * 8)],
    },
    {
        "entry": "eval_rpn",
        "prompt": ("Implement `eval_rpn(tokens: list[str]) -> int` evaluating a Reverse Polish "
                   "Notation expression. Operators + - * /. Division truncates toward zero."),
        "tests": [((["2", "1", "+", "3", "*"],), 9), ((["4", "13", "5", "/", "+"],), 6),
                  ((["10", "6", "9", "3", "+", "-11", "*", "/", "*", "17", "+", "5", "+"],), 22),
                  ((["-3", "4", "+"],), 1), ((["7", "-3", "/"],), -2), ((["-7", "3", "/"],), -2),
                  ((["5"],), 5)],
    },
    {
        "entry": "is_valid_number",
        "prompt": ("Implement `is_valid_number(s: str) -> bool` (LeetCode 65, no surrounding "
                   "spaces). A valid number is a decimal or integer, optionally followed by "
                   "'e'/'E' and an integer. Decimal allows an optional sign and forms like "
                   "'2.', '.8', '46.e3'."),
        "tests": [(("0",), True), (("e",), False), ((".",), False), ((".1",), True),
                  (("3.",), True), (("2e10",), True), (("-90e3",), True), (("1a",), False),
                  (("99e2.5",), False), (("--6",), False), (("-+3",), False),
                  (("95a54e53",), False), (("+.8",), True), (("46.e3",), True),
                  (("e3",), False), (("+",), False), (("53.5e93",), True)],
    },
    {
        "entry": "merge_intervals",
        "prompt": ("Implement `merge_intervals(intervals: list[list[int]]) -> list[list[int]]` "
                   "merging all overlapping intervals, returned sorted by start."),
        "tests": [(([[1, 3], [2, 6], [8, 10], [15, 18]],), [[1, 6], [8, 10], [15, 18]]),
                  (([[1, 4], [4, 5]],), [[1, 5]]), (([[1, 4], [2, 3]],), [[1, 4]]),
                  (([],), []), (([[1, 4], [0, 4]],), [[0, 4]]), (([[1, 4], [5, 6]],), [[1, 4], [5, 6]]),
                  (([[2, 3], [4, 5], [6, 7], [1, 10]],), [[1, 10]])],
    },
]

_HARNESS = '''

def __norm(x):
    if isinstance(x, (list, tuple)):
        return [__norm(i) for i in x]
    return x

def __run():
    import json as __json
    __tests = {tests!r}
    __passed = 0
    for __args, __expected in __tests:
        try:
            __got = {entry}(*__args)
            if __norm(__got) == __norm(__expected):
                __passed += 1
        except Exception:
            pass
    print("###RESULT###" + __json.dumps({{"passed": __passed, "total": len(__tests)}}))

__run()
'''


def extract_code(text: str) -> str:
    """Pull the Python code out of a markdown answer (last fenced block wins)."""
    blocks = re.findall(r"```(?:python)?\s*\n(.*?)```", text or "", re.S)
    return blocks[-1] if blocks else (text or "")


def run_tests(code: str, entry: str, tests) -> tuple[int, int]:
    """Execute `code` in an isolated subprocess and count passing tests."""
    src = code + _HARNESS.format(tests=tests, entry=entry)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(src)
        path = f.name
    try:
        proc = subprocess.run([sys.executable, path], capture_output=True, text=True,
                              timeout=10, cwd=tempfile.gettempdir())
        for line in proc.stdout.splitlines():
            if line.startswith("###RESULT###"):
                d = json.loads(line[len("###RESULT###"):])
                return d["passed"], d["total"]
        return 0, len(tests)
    except subprocess.TimeoutExpired:
        return 0, len(tests)
    except Exception:
        return 0, len(tests)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=[
        "openai/gpt-4o", "x-ai/grok-4.3", "meta-llama/llama-3.3-70b-instruct"])
    ap.add_argument("--mitosis", type=int, default=3)
    args = ap.parse_args()

    key = os.environ.get("OPENROUTER_API_KEY")
    if not (key and key.startswith("sk-or")):
        print("This objective eval needs a valid OPENROUTER_API_KEY (real code, real tests).")
        return 2
    provider = AsyncOpenRouterProvider()

    print("=" * 78)
    print("  B.I.O.M.A. — OBJECTIVE EVAL (execute generated code vs hidden tests)")
    print("=" * 78)
    total_tests = sum(len(t["tests"]) for t in TASKS)
    print(f"  {len(TASKS)} tasks · {total_tests} total tests · models: "
          f"{', '.join(pretty(m) for m in args.models)}\n")

    rows = []
    try:
        for model in args.models:
            base_pass = bioma_pass = 0
            base_cost = bioma_cost = 0.0
            for task in TASKS:
                # baseline: one call
                b = await provider.complete(prompt=task["prompt"], model=model, max_tokens=2048,
                                            system="Expert engineer. Return ONE python code block.",
                                            temperature=0.2)
                bp, tot = run_tests(extract_code(b.text), task["entry"], task["tests"])
                base_pass += bp
                base_cost += b.cost_usd
                # B.I.O.M.A. forced mitosis
                r = await evolve(task["prompt"], model=model, mitosis=args.mitosis,
                                 context=[], provider=provider, adaptive=False)
                mp, _ = run_tests(extract_code(r["answer"]), task["entry"], task["tests"])
                bioma_pass += mp
                bioma_cost += r["telemetry"]["usage"]["cost_usd"]
                print(f"  {pretty(model):14s} {task['entry']:26s} baseline {bp}/{tot}  →  BIOMA {mp}/{tot}")
            rows.append((model, base_pass, bioma_pass, total_tests, base_cost, bioma_cost))
            print(f"  {pretty(model):14s} {'TOTAL':26s} baseline {base_pass}/{total_tests}  →  "
                  f"BIOMA {bioma_pass}/{total_tests}\n")
    finally:
        await provider.close()

    print("=" * 78)
    print("## B.I.O.M.A. — Objective Correctness (executed tests, no LLM judge)\n")
    print("| Modelo | Baseline (testes ok) | B.I.O.M.A. mitose (testes ok) | Δ acertos | Custo base → BIOMA |")
    print("| :--- | :---: | :---: | :---: | :---: |")
    tb = tm = 0
    for model, bp, mp, tot, bc, mc in rows:
        d = mp - bp
        tb += bp; tm += mp
        sign = "✅ +" if d > 0 else ("➖ " if d == 0 else "❌ ")
        print(f"| **{pretty(model)}** | {bp}/{tot} ({bp/tot:.0%}) | {mp}/{tot} ({mp/tot:.0%}) "
              f"| {sign}{d} | ${bc:.4f} → ${mc:.4f} |")
    n = len(rows) * total_tests
    print(f"\n**Agregado:** baseline **{tb}/{n} ({tb/n:.0%})** · B.I.O.M.A. **{tm}/{n} ({tm/n:.0%})** "
          f"· Δ = {'+' if tm-tb>=0 else ''}{tm-tb} acertos.")
    print("\n> Ground truth: código executado contra testes reais. Sem juiz. "
          "Se Δ ≤ 0, a mitose não melhora a correção nestes modelos/tarefas — e isso é a verdade citável.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
