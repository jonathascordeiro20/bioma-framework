"""
`benchmark_orchestration.py` — measure B.I.O.M.A. as a local orchestrator.

Answers, with HONEST numbers, two questions:

  1. **Token economy** — for the class of tasks B.I.O.M.A. actually handles
     (verified code optimization), it does the work with a **deterministic local
     optimizer** that spends **zero model tokens** and never touches the network.
     We run a real workload through it (measuring wall-clock latency, the verified
     speed-up it produces, and 0 tokens) and compare against a **documented
     estimate** of what an LLM-based approach would spend on the same workload.

  2. **Orchestration performance** — the mitosis engine is a multi-agent
     orchestrator.  We measure, live, the task-quality lift of the orchestrated
     (multi-agent) colony vs a monolithic single-agent baseline.

Honesty boundaries (stated up front, not buried):
  • The 0-token result is because B.I.O.M.A. is a deterministic local optimizer —
    NOT because it made an LLM cheaper.  The 100% token saving applies ONLY to its
    verified niche (the AST-transform catalog), not to general reasoning/chat.
  • The LLM baseline is an ESTIMATE — no external model is called here (the system
    is offline/autarkic and holds no API key).  Assumptions: one call per task,
    completion ≈ the emitted code, price illustrative.  It is a conservative floor
    (real LLM agent loops make several calls + emit explanations → more tokens).
  • "Performance" here means verified correctness + local latency + the code
    speed-up produced — not beating an LLM at open-ended reasoning.

Run:  python -m bioma_engine.benchmark_orchestration
"""

from __future__ import annotations

import json
import math
import os
import sys
import time

from .config import DEFAULT_CONFIG
from .bioma_integration_hook import process_external_prompt_sync
from .simulation_harness import SimulationHarness, generate_scenario

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))

# Illustrative frontier-class token prices (USD per 1M tokens).  Vendor-neutral
# ballpark — the token SAVING is price-independent (100%); only the $ is illustrative.
PRICE_IN_PER_M = 3.0
PRICE_OUT_PER_M = 15.0

SYSTEM_PROMPT = (
    "You are an expert Python performance engineer. Optimize the following function "
    "for speed while keeping it correct. Return only the optimized code."
)


def est_tokens(text: str) -> int:
    """~4 chars/token heuristic (standard rough estimate for English + code)."""
    return math.ceil(len(text) / 4)


def _newton(bound: int) -> str:
    return (
        "def solve(x):\n"
        "    guess = x if x > 1 else 1.0\n"
        f"    for _ in range({bound}):\n"
        "        guess = (guess + x / guess) / 2.0\n"
        "    return round(guess, 4)\n"
    )


# A workload the AST catalog genuinely optimizes (memoization / loop-bound tuning),
# each with a hard correctness gate so only VERIFIED speed-ups count.
NEWTON_TESTS = [[[4.0], 2.0], [[9.0], 3.0], [[16.0], 4.0]]
FIB = ("def solve(n):\n    if n < 2:\n        return n\n    return solve(n - 1) + solve(n - 2)\n")
FIB_TESTS = [[[10], 55], [[15], 610], [[20], 6765]]

WORKLOAD = [
    {"label": "recursive-fibonacci", "source": FIB, "entrypoint": "solve", "tests": FIB_TESTS},
    {"label": "newton-sqrt-1800", "source": _newton(1800), "entrypoint": "solve", "tests": NEWTON_TESTS},
    {"label": "newton-sqrt-2100", "source": _newton(2100), "entrypoint": "solve", "tests": NEWTON_TESTS},
    {"label": "newton-sqrt-2400", "source": _newton(2400), "entrypoint": "solve", "tests": NEWTON_TESTS},
    {"label": "newton-sqrt-2700", "source": _newton(2700), "entrypoint": "solve", "tests": NEWTON_TESTS},
    {"label": "newton-sqrt-3000", "source": _newton(3000), "entrypoint": "solve", "tests": NEWTON_TESTS},
]


def run_benchmark(*, generations: int = 3, population: int = 4) -> dict:
    cfg = DEFAULT_CONFIG

    # ---- 1. Token economy over the real workload ------------------------- #
    rows = []
    for task in WORKLOAD:
        t0 = time.perf_counter()
        res = process_external_prompt_sync(
            task["label"], source=task["source"], entrypoint=task["entrypoint"],
            test_cases=task["tests"], generations=generations, population=population,
            use_cache=False,
        )
        latency = time.perf_counter() - t0
        # LLM-equivalent token estimate for the SAME task (conservative floor).
        prompt_tok = est_tokens(SYSTEM_PROMPT + "\n" + task["source"])
        completion_tok = est_tokens(res.code)
        llm_tok = prompt_tok + completion_tok
        rows.append({
            "task": task["label"],
            "bioma_tokens": 0,
            "bioma_latency_s": round(latency, 4),
            "bioma_verified_improved": bool(res.improved),
            "code_speedup_pct": round(float(res.latency_gain_pct), 2),
            "winning_transform": res.winning_transform,
            "llm_prompt_tokens_est": prompt_tok,
            "llm_completion_tokens_est": completion_tok,
            "llm_total_tokens_est": llm_tok,
        })

    n = len(rows)
    total_bioma_tok = 0
    total_llm_tok = sum(r["llm_total_tokens_est"] for r in rows)
    total_lat = sum(r["bioma_latency_s"] for r in rows)
    improved = sum(1 for r in rows if r["bioma_verified_improved"])
    mean_speedup = round(sum(r["code_speedup_pct"] for r in rows) / n, 2) if n else 0.0
    llm_in = sum(r["llm_prompt_tokens_est"] for r in rows)
    llm_out = sum(r["llm_completion_tokens_est"] for r in rows)
    illustrative_cost = round(llm_in / 1e6 * PRICE_IN_PER_M + llm_out / 1e6 * PRICE_OUT_PER_M, 6)
    token_savings_pct = 100.0 if total_llm_tok > 0 else 0.0

    economy = {
        "tasks": n,
        "verified_improved": improved,
        "verified_improved_rate": round(improved / n, 3) if n else 0.0,
        "mean_code_speedup_pct": mean_speedup,
        "bioma_tokens_total": total_bioma_tok,
        "llm_tokens_total_est": total_llm_tok,
        "token_savings_pct": token_savings_pct,
        "illustrative_llm_cost_usd": illustrative_cost,
        "illustrative_bioma_cost_usd": 0.0,
        "bioma_total_latency_s": round(total_lat, 3),
        "throughput_tasks_per_s": round(n / total_lat, 3) if total_lat else 0.0,
        "network_bytes": 0,
        "per_task": rows,
    }

    # ---- 2. Orchestration performance: multi-agent vs monolithic --------- #
    h = SimulationHarness(cfg)
    sc = generate_scenario("bench", K=4, M=20, d=cfg.embed_dim, sigma=0.05, gamma=0.6, seed=1000)
    multi = h.run_scenario(sc, mitosis=True, bus=True)     # orchestrated colony
    mono = h.run_scenario(sc, mitosis=False, bus=True)     # single monolithic agent
    cov_lift = round(multi["coverage_soft"] - mono["coverage_soft"], 4)
    cas_lift = round(multi.get("cascade_score", 0.0) - mono.get("cascade_score", 0.0), 4)
    orchestration = {
        "multi_agent_coverage": round(multi["coverage_soft"], 4),
        "monolithic_coverage": round(mono["coverage_soft"], 4),
        "coverage_lift_absolute": cov_lift,
        "coverage_lift_pct": round(100.0 * cov_lift / mono["coverage_soft"], 1) if mono["coverage_soft"] else None,
        "multi_agent_cascade": round(multi.get("cascade_score", 0.0), 4),
        "monolithic_cascade": round(mono.get("cascade_score", 0.0), 4),
        "cascade_lift_absolute": cas_lift,
        "agents_spawned": multi.get("dag_nodes"),
    }

    return {
        "benchmark": "B.I.O.M.A. — orchestration performance & token economy",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "assumptions": {
            "llm_baseline": "ESTIMATE — no external model called (offline/autarkic).",
            "calls_per_task": 1,
            "completion_estimate": "≈ emitted optimized code (conservative floor)",
            "token_heuristic": "~4 chars/token",
            "illustrative_price_usd_per_1M": {"input": PRICE_IN_PER_M, "output": PRICE_OUT_PER_M},
        },
        "honesty": [
            "0 tokens = deterministic LOCAL optimizer, not a cheaper LLM.",
            "100% token saving applies ONLY to the verified code-optimization niche.",
            "LLM baseline is a conservative estimate; real agent loops cost more.",
            "'Performance' = verified correctness + local latency + code speed-up.",
        ],
        "token_economy": economy,
        "orchestration_performance": orchestration,
    }


def _write_md(rep: dict, path: str) -> None:
    e, o = rep["token_economy"], rep["orchestration_performance"]
    L = [f"# {rep['benchmark']}", "", f"_Generated {rep['generated_utc']}_", ""]
    L += ["## 1 · Token economy (verified code-optimization workload)", ""]
    L += ["| Metric | B.I.O.M.A. | LLM approach (est.) |", "|---|---|---|"]
    L += [f"| Tokens spent | **0** | {e['llm_tokens_total_est']:,} (est.) |"]
    L += [f"| Illustrative cost (USD) | **$0.00** | ${e['illustrative_llm_cost_usd']} (est.) |"]
    L += [f"| Network bytes | **0** | (cloud round-trips) |"]
    L += [f"| **Token savings** | colspan → | **{e['token_savings_pct']:.0f}%** on this workload |"]
    L += ["", f"- Tasks: **{e['tasks']}** · verified-improved: **{e['verified_improved']}/{e['tasks']}** "
          f"({e['verified_improved_rate']*100:.0f}%)"]
    L += [f"- Mean code speed-up produced: **{e['mean_code_speedup_pct']}%** "
          f"· throughput **{e['throughput_tasks_per_s']} tasks/s** "
          f"(total {e['bioma_total_latency_s']}s local)"]
    L += ["", "| Task | Verified? | Code speed-up | Transform | Tokens | LLM tok (est.) |",
          "|---|---|---|---|---|---|"]
    for r in e["per_task"]:
        L += [f"| {r['task']} | {'✅' if r['bioma_verified_improved'] else '—'} | "
              f"{r['code_speedup_pct']}% | `{r['winning_transform']}` | **0** | {r['llm_total_tokens_est']} |"]
    L += ["", "## 2 · Orchestration performance (multi-agent vs monolithic)", ""]
    L += [f"- Coverage: multi-agent **{o['multi_agent_coverage']}** vs monolithic "
          f"**{o['monolithic_coverage']}** → **+{o['coverage_lift_absolute']}** "
          f"({o['coverage_lift_pct']}% lift)"]
    L += [f"- Cascade recovery: multi-agent **{o['multi_agent_cascade']}** vs "
          f"**{o['monolithic_cascade']}** → **+{o['cascade_lift_absolute']}**"]
    L += [f"- Agents spawned by the orchestrator: **{o['agents_spawned']}**"]
    L += ["", "## Honesty", ""]
    for h in rep["honesty"]:
        L += [f"- {h}"]
    L += ["", f"> LLM baseline is an estimate ({rep['assumptions']['token_heuristic']}, "
          f"1 call/task, price illustrative). No external model was called."]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


def main() -> int:  # pragma: no cover - reporting entry point
    rep = run_benchmark()
    jp = os.path.join(_PKG_DIR, "BENCHMARK_ORCHESTRATION.json")
    mp = os.path.join(_PKG_DIR, "BENCHMARK_ORCHESTRATION.md")
    with open(jp, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=2, ensure_ascii=False)
    _write_md(rep, mp)

    e, o = rep["token_economy"], rep["orchestration_performance"]
    w = 74
    print("=" * w)
    print(" B.I.O.M.A. — ORCHESTRATION BENCHMARK ".center(w, "="))
    print("=" * w)
    print("  TOKEN ECONOMY (verified code-optimization workload)")
    print(f"    tasks .................. {e['tasks']}  (verified-improved {e['verified_improved']}/{e['tasks']})")
    print(f"    B.I.O.M.A. tokens ...... {e['bioma_tokens_total']}   (network bytes: {e['network_bytes']})")
    print(f"    LLM tokens (est.) ...... {e['llm_tokens_total_est']:,}  → illustrative ${e['illustrative_llm_cost_usd']}")
    print(f"    TOKEN SAVINGS .......... {e['token_savings_pct']:.0f}%  on this workload")
    print(f"    mean code speed-up ..... {e['mean_code_speedup_pct']}%   throughput {e['throughput_tasks_per_s']} tasks/s")
    print("  ORCHESTRATION PERFORMANCE (multi-agent vs monolithic)")
    print(f"    coverage ............... {o['multi_agent_coverage']} vs {o['monolithic_coverage']}  "
          f"(+{o['coverage_lift_absolute']}, {o['coverage_lift_pct']}%)")
    print(f"    cascade recovery ....... {o['multi_agent_cascade']} vs {o['monolithic_cascade']}  "
          f"(+{o['cascade_lift_absolute']})")
    print("-" * w)
    print(f"  written: {jp}")
    print(f"           {mp}")
    print("=" * w)
    return 0


if __name__ == "__main__":
    _rc = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_rc)
