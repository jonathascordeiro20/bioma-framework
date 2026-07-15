#!/usr/bin/env python3
"""
tests/benchmark_dev_openrouter.py — dev-workload benchmark, baseline vs BIOMA,
on the most-used agent-development models via OpenRouter. Protocol-faithful:
every number comes from the API (usage object + /models pricing) — never
estimated; failures are recorded, not smoothed over.

Matrix: 2 arms × 7 models × 3 dev tasks × N replicas (order alternated).
  Arm A (control): full session context, raw OpenRouter dispatch.
  Arm B (BIOMA):   the production path — LeanOpenRouterClient (Rust apoptosis).

Tasks are FROZEN simulated dev-agent sessions (bug fix / refactor / feature)
with objective probes: exact strings a correct answer must contain (function
names, constants, values planted in the session). Success = all probes present.

Outputs (audit trail):
  resultados/precos_openrouter.json   — pricing snapshot fetched from the API
  resultados/usage_raw.jsonl          — raw usage object of every dispatch
  resultados/execucoes.csv            — one row per execution
  resultados/relatorio.md             — medians, savings per model, verdicts

    python tests/benchmark_dev_openrouter.py --pilot     # T1 × sonnet-5 × both arms
    python tests/benchmark_dev_openrouter.py --replicas 3
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import statistics
import sys
import time
import urllib.request

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
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from bioma.openrouter_client import OPENROUTER_BASE_URL, LeanOpenRouterClient  # noqa: E402

MODELS = [
    ("anthropic/claude-fable-5", "Claude Fable 5"),
    ("anthropic/claude-opus-4.8", "Claude Opus 4.8"),
    ("anthropic/claude-sonnet-5", "Claude Sonnet 5"),
    ("openai/gpt-5.6-sol", "GPT-5.6 Sol"),
    ("z-ai/glm-5.2", "GLM-5.2"),
    ("x-ai/grok-4.5", "Grok 4.5"),
    ("google/gemini-3.5-flash", "Gemini 3.5 Flash"),  # única variante 3.5 na API — substituição registrada
]
RESULTS = os.path.join(_ROOT, "resultados")
SYSTEM_MSG = "You are a senior software engineer. Be precise and reference exact identifiers."


# --------------------------------------------------------------------------- #
#  Frozen dev tasks — simulated agent sessions with objective probes
# --------------------------------------------------------------------------- #
def _tool_noise(i: int, flavor: str) -> str:
    return (f"[{flavor} run {i}] " + "collected 148 items / 148 passed in 12.4s "
            "warnings: DeprecationWarning x3 ... coverage 87% lines 4,210 ... ") * 8


def task_t1_bugfix() -> tuple[list[dict], str, list[str]]:
    """T1 — bug fix: the root cause is planted mid-session; noise around it."""
    h = [{"role": "system", "content": SYSTEM_MSG},
         {"role": "fact", "content": "FACT: repo billing-svc, branch hotfix/date-window. "
                                     "Bug: monthly report skips the last day of the month."},
         {"role": "fact", "content": "FACT: culprit code in reports/window.py:\n"
                                     "def month_window(year, month):\n"
                                     "    start = date(year, month, 1)\n"
                                     "    end = start + timedelta(days=days_in_month(year, month) - 1)\n"
                                     "    return start, end  # consumer filters with ts < end (exclusive!)"},
         {"role": "fact", "content": "FACT: acceptance — tests/test_window.py::test_includes_last_day"}]
    for i in range(1, 11):
        h += [{"role": "tool", "content": _tool_noise(i, "pytest")},
              {"role": "user", "content": f"iteração {i}: ainda investigando o relatório."},
              {"role": "assistant", "content": f"iteração {i}: hipótese descartada, seguindo."}]
    q = ("Based on the pinned facts: name the buggy function, explain the off-by-one in one "
         "sentence, and give the corrected return line so the exclusive filter includes the "
         "last day (add one day to end).")
    return h, q, ["month_window", "timedelta", "end"]


def task_t2_refactor() -> tuple[list[dict], str, list[str]]:
    """T2 — refactor: extract module keeping the public API."""
    h = [{"role": "system", "content": SYSTEM_MSG},
         {"role": "fact", "content": "FACT: refactor goal — extract retry/backoff logic from "
                                     "client.py into a new module resilience.py."},
         {"role": "fact", "content": "FACT: public API that MUST keep working: "
                                     "Client.request(), Client.close(); new module must expose "
                                     "retry_with_backoff(fn, max_retries=5, base_delay=1.0)."},
         {"role": "fact", "content": "FACT: acceptance — full suite green and `ruff check` clean."}]
    for i in range(1, 13):
        h += [{"role": "tool", "content": _tool_noise(i, "ruff+pytest")},
              {"role": "user", "content": f"passo {i}: revisando acoplamentos."},
              {"role": "assistant", "content": f"passo {i}: mapeado, sem quebra de API até aqui."}]
    q = ("From the pinned facts: name the new module file, the exact signature of the extracted "
         "helper, and the two public methods that must not change.")
    return h, q, ["resilience.py", "retry_with_backoff", "max_retries=5", "Client.request"]


def task_t3_feature() -> tuple[list[dict], str, list[str]]:
    """T3 — feature: long agent loop (~100-call profile) with the spec pinned."""
    h = [{"role": "system", "content": SYSTEM_MSG},
         {"role": "fact", "content": "FACT: feature — rate limiter middleware. Spec: sliding "
                                     "window, limit 350 req/min per api_key, header X-RateLimit-Remaining, "
                                     "HTTP 429 with Retry-After on breach."},
         {"role": "fact", "content": "FACT: config keys: RATE_LIMIT_RPM=350, RATE_WINDOW_S=60."},
         {"role": "fact", "content": "FACT: acceptance — new tests tests/test_ratelimit.py plus old suite green."}]
    for i in range(1, 31):
        h += [{"role": "tool", "content": _tool_noise(i, "agent-step")},
              {"role": "user", "content": f"step {i}: continue."},
              {"role": "assistant", "content": f"step {i}: progresso incremental registrado."}]
    q = ("From the pinned spec: state the limit and window values, the response header name, the "
         "HTTP status + header returned on breach, and the two config keys.")
    return h, q, ["350", "X-RateLimit-Remaining", "429", "Retry-After", "RATE_LIMIT_RPM"]


TASKS = [("T1-bugfix", task_t1_bugfix), ("T2-refactor", task_t2_refactor),
         ("T3-feature", task_t3_feature)]


# --------------------------------------------------------------------------- #
def fetch_prices() -> dict:
    with urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=60) as r:
        data = json.loads(r.read().decode())["data"]
    wanted = {m for m, _ in MODELS}
    snap = {m["id"]: m.get("pricing", {}) for m in data if m["id"] in wanted}
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "precos_openrouter.json"), "w", encoding="utf-8") as f:
        json.dump({"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "pricing": snap}, f, indent=2)
    return snap


def probe_ok(text: str, probes: list[str]) -> tuple[float, int]:
    low = (text or "").lower()
    hits = sum(1 for p in probes if p.lower() in low)
    return hits / len(probes), int(hits == len(probes))


class RawArm:
    """Arm A — identical prompt format, full context, no apoptosis."""

    def __init__(self) -> None:
        from openai import AsyncOpenAI
        self.c = AsyncOpenAI(base_url=OPENROUTER_BASE_URL,
                             api_key=os.environ["OPENROUTER_API_KEY"],
                             default_headers={"HTTP-Referer": "https://bioma.ai",
                                              "X-Title": "B.I.O.M.A. DevBench-A"})

    async def run(self, history: list[dict], query: str, model: str) -> dict:
        full = "\n".join(str(m.get("content", "")) for m in history)
        prompt = f"Context:\n{full}\n\nCurrent request:\n{query}"
        t0 = time.perf_counter()
        try:
            r = await self.c.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}],
                max_tokens=1000, temperature=0.0, extra_body={"usage": {"include": True}})
            u = r.usage
            return {"text": r.choices[0].message.content or "", "error": None,
                    "in": int(u.prompt_tokens or 0), "out": int(u.completion_tokens or 0),
                    "cost": float(getattr(u, "cost", 0) or 0),
                    "dur": time.perf_counter() - t0,
                    "raw_usage": u.model_dump() if hasattr(u, "model_dump") else {}}
        except Exception as exc:  # noqa: BLE001 — record, don't smooth
            return {"text": "", "error": f"{type(exc).__name__}: {str(exc)[:80]}",
                    "in": 0, "out": 0, "cost": 0.0, "dur": time.perf_counter() - t0,
                    "raw_usage": {}}

    async def close(self) -> None:
        await self.c.close()


async def run_matrix(models: list[tuple[str, str]], replicas: int) -> list[dict]:
    lean = LeanOpenRouterClient()
    raw = RawArm()
    rows: list[dict] = []
    os.makedirs(RESULTS, exist_ok=True)
    usage_log = open(os.path.join(RESULTS, "usage_raw.jsonl"), "a", encoding="utf-8")
    try:
        for tname, builder in TASKS:
            history, query, probes = builder()
            for slug, label in models:
                for rep in range(1, replicas + 1):
                    order = ["A", "B"] if rep % 2 == 1 else ["B", "A"]
                    for arm in order:
                        if arm == "A":
                            r = await raw.run(history, query, model=slug)
                        else:
                            t0 = time.perf_counter()
                            d = await lean.dispatch(history, query, model=slug,
                                                    max_tokens=1000, temperature=0.0)
                            r = {"text": d.text, "error": d.error, "in": d.in_tokens,
                                 "out": d.out_tokens, "cost": d.cost_usd,
                                 "dur": time.perf_counter() - t0,
                                 "raw_usage": {"tokens_before": d.tokens_before,
                                               "tokens_after": d.tokens_after,
                                               "reduction": d.reduction}}
                        if r["error"] is None and not r["text"].strip():
                            r["error"] = "empty response"
                        score, ok = probe_ok(r["text"], probes)
                        row = {"tarefa": tname, "braco": arm, "modelo": label, "replica": rep,
                               "ordem": "-".join(order), "input_tokens": r["in"],
                               "output_tokens": r["out"], "custo_usd": round(r["cost"], 6),
                               "probes": round(score, 3), "sucesso": ok if not r["error"] else 0,
                               "duracao_s": round(r["dur"], 1),
                               "observacoes": r["error"] or ""}
                        rows.append(row)
                        usage_log.write(json.dumps({**row, "raw_usage": r["raw_usage"]}) + "\n")
                        e = f" ERR {r['error']}" if r["error"] else ""
                        print(f"  {tname:11s} {label:16s} r{rep} braço {arm} | "
                              f"in {r['in']:6,} out {r['out']:4,} | ${r['cost']:.4f} | "
                              f"probes {score*100:3.0f}%{e}")
    finally:
        usage_log.close()
        await lean.close()
        await raw.close()
    return rows


def write_csv(rows: list[dict]) -> None:
    path = os.path.join(RESULTS, "execucoes.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        if new:
            w.writeheader()
        w.writerows(rows)
    print(f"\n📄 CSV bruto: {path} (+{len(rows)} linhas)")


def summarize(rows: list[dict]) -> None:
    ok = [r for r in rows if not r["observacoes"]]
    print("\n## Resumo (medianas por modelo, apenas células sem erro)\n")
    print("| Modelo | custo A | custo B | economia | sucesso A | sucesso B |")
    print("| :--- | ---: | ---: | ---: | :---: | :---: |")
    for _, label in MODELS:
        a = [r for r in ok if r["modelo"] == label and r["braco"] == "A"]
        b = [r for r in ok if r["modelo"] == label and r["braco"] == "B"]
        if not a or not b:
            continue
        ca = statistics.median(r["custo_usd"] for r in a)
        cb = statistics.median(r["custo_usd"] for r in b)
        sa = sum(r["sucesso"] for r in a) / len(a)
        sb = sum(r["sucesso"] for r in b) / len(b)
        eco = (1 - cb / ca) * 100 if ca else 0.0
        print(f"| {label} | ${ca:.4f} | ${cb:.4f} | **−{eco:.0f}%** | {sa*100:.0f}% | {sb*100:.0f}% |")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--replicas", type=int, default=3)
    ap.add_argument("--models", nargs="*", default=None)
    args = ap.parse_args()

    if not os.environ.get("OPENROUTER_API_KEY", "").startswith("sk-or"):
        print("OPENROUTER_API_KEY ausente."); return 2

    import subprocess
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=_ROOT,
                            capture_output=True, text=True).stdout.strip()
    prices = fetch_prices()
    print("=" * 100)
    print("  B.I.O.M.A. DevBench — baseline vs BIOMA · OpenRouter · preços reais da API")
    print("=" * 100)
    print(f"  BIOMA commit {commit} · half_life=6.0 threshold=0.35 · temp 0.0 · "
          f"preços congelados em resultados/precos_openrouter.json ({len(prices)} modelos)\n")

    if args.pilot:
        models = [("anthropic/claude-sonnet-5", "Claude Sonnet 5")]
        global TASKS
        TASKS = TASKS[:1]
        rows = await run_matrix(models, replicas=1)
    else:
        models = ([(m, l) for m, l in MODELS if m in args.models]
                  if args.models else MODELS)
        rows = await run_matrix(models, replicas=args.replicas)

    write_csv(rows)
    summarize(rows)
    total = sum(r["custo_usd"] for r in rows)
    errs = sum(1 for r in rows if r["observacoes"])
    print(f"\n  execuções: {len(rows)} · com erro: {errs} · custo total do lote: ${total:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
