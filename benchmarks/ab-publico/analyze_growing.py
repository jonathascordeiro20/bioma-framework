#!/usr/bin/env python3
"""Analyze the GROWING-conversation A/B (Item 1b).

Reads results/cached/results_growing.jsonl. Per model, at each conversation step
it pools the real billed cost across tasks (baseline+cache vs bioma+cache) and
reports the cumulative cost divergence — the metric that shows caching discounts
but does not eliminate the growing history, while BIOMA keeps it bounded.

Also emits results/charts/growing_conversation_cost.png: cumulative cost vs turn.
"""
from __future__ import annotations

import json
import pathlib
from collections import defaultdict

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "results" / "cached" / "results_growing.jsonl"
CHARTS = ROOT / "results" / "charts"
REPO = "jonathascordeiro20/bioma-framework"
BASELINE_C = "#475569"
BIOMA_C = "#0f766e"


def load():
    rows = []
    for line in SRC.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            r = json.loads(line)
            if "error" not in r:
                rows.append(r)
    return rows


def per_step_median(rows, field="cost_usd"):
    """{model: {arm: {step: median `field` across tasks}}} and history_turns per step."""
    acc = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    turns = defaultdict(dict)
    for r in rows:
        acc[r["model"]][r["arm"]][r["step"]].append(r[field])
        turns[r["model"]][r["step"]] = r["history_turns"]
    med = {}
    for model, arms in acc.items():
        med[model] = {}
        for arm, steps in arms.items():
            med[model][arm] = {s: float(np.median(v)) for s, v in steps.items()}
    return med, turns


def main() -> int:
    rows = load()
    cost, turns = per_step_median(rows, "cost_usd")
    toks, _ = per_step_median(rows, "prompt_tokens")
    models = [m for m in ("claude-opus", "claude-haiku") if m in cost]

    print("growing-conversation A/B — median across tasks per step (real billed cost)\n")
    for model in models:
        steps = sorted(cost[model]["baseline"])
        tb = np.array([toks[model]["baseline"][s] for s in steps])
        tm = np.array([toks[model]["bioma"][s] for s in steps])
        b = np.array([cost[model]["baseline"][s] for s in steps])
        m = np.array([cost[model]["bioma"][s] for s in steps])
        cb, cm = np.cumsum(b), np.cumsum(m)
        last = steps[-1]
        print(f"== {model} — {len(steps)} steps, up to {turns[model][last]} history turns ==")
        print(f"  input tokens sent (last step): baseline {int(tb[-1]):,}  "
              f"bioma {int(tm[-1]):,}  ({tb[-1]/tm[-1]:.1f}x fewer, BOUNDED vs growing)")
        print(f"  cumulative billed cost       : baseline+cache ${cb[-1]:.4f}  "
              f"bioma+cache ${cm[-1]:.4f}  ({100*(1-cm[-1]/cb[-1]):.0f}% saved)")
        print()
    print("caveat: task histories cap at 36-50 turns, so the last 1-2 steps plateau\n"
          "(same context reused -> cached read), narrowing the $ gap there. The TOKEN\n"
          "divergence is the clean signal: caching discounts price but the model still\n"
          "carries the full context (latency, window pressure, decode energy).\n")

    # chart: tokens sent per turn (the coefficient-free mechanism) + cumulative cost
    fig, axes = plt.subplots(2, len(models), figsize=(6.2 * len(models), 8.2), squeeze=False)
    for j, model in enumerate(models):
        steps = sorted(cost[model]["baseline"])
        xt = [turns[model][s] for s in steps]
        # top: tokens sent per turn
        ax = axes[0][j]
        ax.plot(xt, [toks[model]["baseline"][s] for s in steps], color=BASELINE_C,
                lw=2.4, marker="o", ms=4, label="baseline (full history)")
        ax.plot(xt, [toks[model]["bioma"][s] for s in steps], color=BIOMA_C,
                lw=2.4, marker="o", ms=4, label="BIOMA shield")
        ax.set_title(model, fontweight="bold", fontsize=13)
        ax.set_ylabel("Input tokens sent per turn")
        ax.set_ylim(bottom=0); ax.set_xlim(left=0)
        ax.grid(color="#e5e7eb"); ax.set_axisbelow(True)
        ax.legend(loc="upper left", frameon=False, fontsize=9)
        # bottom: cumulative billed cost
        ax2 = axes[1][j]
        cb = np.cumsum([cost[model]["baseline"][s] for s in steps]) * 1000
        cm = np.cumsum([cost[model]["bioma"][s] for s in steps]) * 1000
        ax2.plot(xt, cb, color=BASELINE_C, lw=2.4, marker="o", ms=4,
                 label="baseline + native caching")
        ax2.plot(xt, cm, color=BIOMA_C, lw=2.4, marker="o", ms=4, label="BIOMA + caching")
        ax2.fill_between(xt, cm, cb, color=BIOMA_C, alpha=0.08)
        ax2.annotate(f"{100*(1-cm[-1]/cb[-1]):.0f}% saved", xy=(xt[-1], cm[-1]),
                     xytext=(-8, 16), textcoords="offset points", fontsize=9,
                     color=BIOMA_C, fontweight="bold", ha="right")
        ax2.set_xlabel("Conversation length (history turns)")
        ax2.set_ylabel("Cumulative cost (milli-USD)")
        ax2.set_ylim(bottom=0); ax2.set_xlim(left=0)
        ax2.grid(color="#e5e7eb"); ax2.set_axisbelow(True)
        ax2.legend(loc="upper left", frameon=False, fontsize=9)

    fig.suptitle("Growing conversations: BIOMA bounds what caching only discounts",
                 fontweight="bold", fontsize=15, y=0.995)
    fig.text(0.5, 0.955, "top: tokens the model actually carries (apoptosis caps it; "
             "baseline grows unbounded). bottom: billed cost, caching on both arms.",
             ha="center", fontsize=9.5, color="#6b7280")
    fig.text(0.005, 0.004, f"Anthropic models, cache on both arms, temperature=0.2. "
             f"Raw data & methodology: github.com/{REPO}/benchmarks/ab-publico",
             fontsize=7, color="#6b7280")
    CHARTS.mkdir(parents=True, exist_ok=True)
    out = CHARTS / "growing_conversation_cost.png"
    fig.tight_layout(rect=(0, 0.02, 1, 0.95))
    fig.savefig(out, dpi=300)
    plt.close(fig)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
