#!/usr/bin/env python3
"""
bioma_verified_selection_eval.py — the corrected mitosis test (verified selection)
====================================================================================
Tests the ONLY version of mitosis with a theoretical path to improve security:

  • HARD security-remediation tasks (many subtle edge cases → single-shot < 100%)
  • CROSS-MODEL candidate pool (different providers catch different bypasses)
  • BASELINE-IN-POOL (each model's plain answer is a candidate → selection >= baseline)
  • OBJECTIVE verification (run the security checks) as the selector — never LLM synthesis

Question answered with ground truth: does verified cross-model selection beat the
BEST single-shot model? If yes, mitosis-as-verified-selection genuinely improves
security remediation. If it only ties, the honest verdict stands: no gain.

Safety: checks are pure string/logic on the returned value — no shell, no I/O, no
network. Even an unfixed candidate executes nothing dangerous.

Real only (valid OPENROUTER_API_KEY). Usage: python bioma_verified_selection_eval.py
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_HERE, ".env"))
except Exception:
    pass

from bioma_orchestrator.openrouter_async import AsyncOpenRouterProvider  # noqa: E402
from bioma_defense_eval import run_checks, extract_code  # noqa: E402  (reuse validated harness)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PRETTY = {"openai/gpt-4o": "GPT-4o", "x-ai/grok-4.3": "Grok-4.3",
          "meta-llama/llama-3.3-70b-instruct": "Llama-3.3-70B"}


def pretty(m):
    return PRETTY.get(m, m.split("/")[-1])


# --------------------------------------------------------------------------- #
#  HARD security tasks (many edge cases; benign checks)
# --------------------------------------------------------------------------- #
TASKS = [
    {
        "entry": "sanitize_filename",
        "prompt": (
            "Implement `sanitize_filename(name: str) -> str` returning a filename safe for "
            "cross-platform use. Requirements: strip path separators '/' and '\\\\'; remove "
            "null bytes and ASCII control characters; neutralize '..'; if the name (case-"
            "insensitive) is a Windows reserved device name (CON, PRN, AUX, NUL, COM1-9, "
            "LPT1-9) it must NOT be returned unchanged (prefix it); truncate to 255 chars; "
            "if the result would be empty, return 'unnamed'. Return ONE python code block."),
        "checks": [
            "'/' not in sanitize_filename('a/b/c.txt')",
            "'\\\\' not in sanitize_filename('a\\\\b.txt')",
            "'\\x00' not in sanitize_filename('a\\x00b')",
            "'\\n' not in sanitize_filename('a\\nb') and '\\t' not in sanitize_filename('a\\tb')",
            "sanitize_filename('CON').upper() != 'CON'",
            "sanitize_filename('com1').lower() != 'com1'",
            "sanitize_filename('..') not in ('..', '', '.')",
            "sanitize_filename('') == 'unnamed'",
            "len(sanitize_filename('a'*400)) <= 255",
            "sanitize_filename('report.pdf') == 'report.pdf'",
        ],
    },
    {
        "entry": "is_safe_redirect_url",
        "prompt": (
            "Implement `is_safe_redirect_url(url: str, allowed_hosts: list) -> bool` for "
            "open-redirect prevention. Return True ONLY for: a relative path starting with a "
            "single '/' (but not '//' or '/\\\\'), OR an absolute http/https URL whose host is "
            "in allowed_hosts. Reject protocol-relative ('//x'), backslash tricks, "
            "javascript:/data:, and userinfo tricks like 'https://allowed@evil'. "
            "Return ONE python code block."),
        "checks": [
            "is_safe_redirect_url('/dashboard', ['example.com']) == True",
            "is_safe_redirect_url('//evil.com', ['example.com']) == False",
            "is_safe_redirect_url('https://evil.com', ['example.com']) == False",
            "is_safe_redirect_url('https://example.com/x', ['example.com']) == True",
            "is_safe_redirect_url('javascript:alert(1)', ['example.com']) == False",
            "is_safe_redirect_url('https://example.com@evil.com', ['example.com']) == False",
            "is_safe_redirect_url('/\\\\evil.com', ['example.com']) == False",
            "is_safe_redirect_url('\\\\\\\\evil.com', ['example.com']) == False",
            "is_safe_redirect_url('data:text/html,x', ['example.com']) == False",
            "is_safe_redirect_url('http://example.com/y', ['example.com']) == True",
        ],
    },
    {
        "entry": "mask_pii",
        "prompt": (
            "Implement `mask_pii(text: str) -> str` that redacts PII from a log line: replace "
            "every email address with '[EMAIL]' and every credit-card-like number (13-16 "
            "digits, possibly separated by spaces or hyphens) with '[CARD]'. Do NOT redact "
            "short numbers (e.g. a 4-digit year). Leave all other text unchanged. "
            "Return ONE python code block."),
        "checks": [
            "'a@b.com' not in mask_pii('contact a@b.com now')",
            "'[EMAIL]' in mask_pii('a@b.com')",
            "'4111 1111 1111 1111' not in mask_pii('card 4111 1111 1111 1111 ok')",
            "'4111-1111-1111-1111' not in mask_pii('card 4111-1111-1111-1111')",
            "'4111111111111111' not in mask_pii('card 4111111111111111')",
            "mask_pii('hello world') == 'hello world'",
            "mask_pii('year 2024 report') == 'year 2024 report'",
            "mask_pii('id 123 ok') == 'id 123 ok'",
            "mask_pii('x@y.com and z@w.org').count('[EMAIL]') == 2",
            "'[CARD]' in mask_pii('4111111111111111')",
        ],
    },
]

STYLES = [
    ("plain", "Expert security engineer. Return ONE python code block."),
    ("auditor", "You are a security auditor. Implement the fix and specifically hunt every "
                "edge case and bypass that others miss. Return ONE python code block."),
]


async def gen(provider, prompt, model, system):
    return await provider.complete(prompt=prompt, model=model, system=system,
                                   max_tokens=2048, temperature=0.2)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=[
        "openai/gpt-4o", "x-ai/grok-4.3", "meta-llama/llama-3.3-70b-instruct"])
    args = ap.parse_args()

    key = os.environ.get("OPENROUTER_API_KEY")
    if not (key and key.startswith("sk-or")):
        print("Needs a valid OPENROUTER_API_KEY."); return 2
    provider = AsyncOpenRouterProvider()

    total = sum(len(t["checks"]) for t in TASKS)
    print("=" * 92)
    print("  B.I.O.M.A. — VERIFIED CROSS-MODEL SELECTION vs best single-shot (ground truth)")
    print("=" * 92)
    print(f"  {len(TASKS)} HARD tasks · {total} checks · pool = {len(args.models)} models × "
          f"{len(STYLES)} styles (baseline in pool)\n")

    per_model_single = {m: 0 for m in args.models}   # each model's plain single-shot
    selection_total = 0
    try:
        for task in TASKS:
            # build the cross-model pool; remember each model's plain (baseline) score
            pool = []
            plain_scores = {}
            for m in args.models:
                for style_name, sysmsg in STYLES:
                    c = await gen(provider, task["prompt"], m, sysmsg)
                    score = run_checks(extract_code(c.text), task["checks"])
                    pool.append((m, style_name, score))
                    if style_name == "plain":
                        plain_scores[m] = score
                        per_model_single[m] += score
            best_single = max(plain_scores.values())
            best_single_model = max(plain_scores, key=plain_scores.get)
            selection = max(s for _m, _st, s in pool)         # verified selection (baseline in pool)
            sel_src = max(pool, key=lambda x: x[2])
            selection_total += selection
            n = len(task["checks"])
            print(f"  {task['entry']:22s} best single-shot {best_single}/{n} ({pretty(best_single_model)}) "
                  f"→ verified selection {selection}/{n} (from {pretty(sel_src[0])}/{sel_src[1]})")
            print(f"      pool: " + ", ".join(f"{pretty(m)}/{st}={s}" for m, st, s in pool))
    finally:
        await provider.close()

    print("\n" + "=" * 92)
    print("## B.I.O.M.A. — Verified cross-model selection (security, ground truth)\n")
    print("| Referência | Acertos | % |")
    print("| :--- | :---: | :---: |")
    for m in args.models:
        print(f"| {pretty(m)} single-shot | {per_model_single[m]}/{total} | {per_model_single[m]/total:.0%} |")
    best_single_agg = max(per_model_single.values())
    print(f"| **Melhor modelo único** | **{best_single_agg}/{total}** | **{best_single_agg/total:.0%}** |")
    print(f"| **Seleção verificada (cross-modelo, baseline no pool)** | **{selection_total}/{total}** "
          f"| **{selection_total/total:.0%}** |")
    delta = selection_total - best_single_agg
    print(f"\n**Veredito:** Δ(seleção verificada − melhor modelo único) = "
          f"**{'+' if delta >= 0 else ''}{delta}** acertos.")
    if delta > 0:
        print("> 🟢 A seleção verificada SUPERA o melhor single-shot → mitose-como-seleção "
              "melhora segurança (com verificador objetivo + headroom). Alegação promovida.")
    else:
        print("> 🔴 Sem ganho sobre o melhor modelo único → mesmo a versão corrigida não agrega. "
              "Veredito honesto mantido: o valor é a apoptose.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
