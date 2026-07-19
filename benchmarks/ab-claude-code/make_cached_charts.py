#!/usr/bin/env python3
"""Break-even chart for the caching A/B (Item 1) — computed from raw cost.

Reads results/cached/results_cached.jsonl and draws, per model, the cumulative
session cost as the SAME context is reused K times:

  baseline + cache : cold write (1.25x) then warm reads (0.10x) on the big payload
  BIOMA + cache    : the shielded payload (often too small to cache) reused

The lines cross at K* — the number of identical reuses after which native
caching alone overtakes BIOMA. Left of K*, BIOMA is cheaper even without caching.
Cold/warm per-call costs are the measured medians across informative tasks
(free-refusal cells, billed $0, excluded). Honest: bar/where relevant axes start
at zero; this is the WORST case for BIOMA (static reuse); growing conversations
favor it longer.

Output: results/charts/savings_on_top_of_caching.png (300 dpi).
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
SRC = ROOT / "results" / "cached" / "results_cached.jsonl"
CHARTS = ROOT / "results" / "charts"
REPO = "jonathascordeiro20/bioma-framework"
BASELINE_C = "#475569"
BIOMA_C = "#0f766e"


def main() -> int:
    rows = [json.loads(l) for l in SRC.read_text(encoding="utf-8").splitlines()
            if l.strip() and "error" not in json.loads(l)]
    idx = defaultdict(dict)
    for r in rows:
        idx[(r["model"], r["task"])][(r["arm"], r["cache"])] = r

    # per model: median cold & warm for baseline+cache and bioma+cache,
    # over informative cells (baseline session billed > 0)
    per_model = defaultdict(lambda: {"bc_cold": [], "bc_warm": [], "mc_cold": [], "mc_warm": []})
    warmup = rows[0].get("warmup")
    for (model, _task), arms in idx.items():
        if not all(k in arms for k in [("baseline", True), ("bioma", True)]):
            continue
        bc, mc = arms[("baseline", True)], arms[("bioma", True)]
        if bc["session_cost_usd"] < 5e-4:      # free-refusal cell — exclude
            continue
        if bc["warm_cost_usd"] is None or mc["warm_cost_usd"] is None:
            continue
        per_model[model]["bc_cold"].append(bc["cold_cost_usd"])
        per_model[model]["bc_warm"].append(bc["warm_cost_usd"])
        per_model[model]["mc_cold"].append(mc["cold_cost_usd"])
        per_model[model]["mc_warm"].append(mc["warm_cost_usd"])

    models = [m for m in ("claude-opus", "claude-haiku") if m in per_model]
    if not models:
        print("no informative models to plot")
        return 1

    fig, axes = plt.subplots(1, len(models), figsize=(6.2 * len(models), 5.6),
                             squeeze=False)
    Ks = np.arange(1, 31)
    for ax, model in zip(axes[0], models):
        d = per_model[model]
        bc_cold, bc_warm = np.median(d["bc_cold"]), np.median(d["bc_warm"])
        mc_cold, mc_warm = np.median(d["mc_cold"]), np.median(d["mc_warm"])
        base = bc_cold + (Ks - 1) * bc_warm
        bioma = mc_cold + (Ks - 1) * mc_warm
        ax.plot(Ks, base * 1000, color=BASELINE_C, lw=2.2, label="baseline + native caching")
        ax.plot(Ks, bioma * 1000, color=BIOMA_C, lw=2.2, label="BIOMA shield")
        # crossover
        cross = np.where(base <= bioma)[0]
        if len(cross):
            kstar = int(Ks[cross[0]])
            ax.axvline(kstar, color="#b91c1c", ls="--", lw=1.3)
            ax.annotate(f"caching-alone\novertakes at K*={kstar}",
                        xy=(kstar, (bioma[cross[0]]) * 1000), xytext=(6, -8),
                        textcoords="offset points", color="#b91c1c", fontsize=9,
                        va="top")
        ax.fill_between(Ks, bioma * 1000, base * 1000, where=(base >= bioma),
                        color=BIOMA_C, alpha=0.08)
        ax.set_title(model, fontweight="bold", fontsize=13)
        ax.set_xlabel("Times the SAME context is reused (K)")
        ax.set_ylabel("Cumulative session cost (milli-USD)")
        ax.set_xlim(1, 30)
        ax.set_ylim(bottom=0)
        ax.grid(color="#e5e7eb")
        ax.set_axisbelow(True)
        ax.legend(loc="upper left", frameon=False, fontsize=9)

    fig.suptitle("Does BIOMA still save on top of native prompt caching?",
                 fontweight="bold", fontsize=15, y=0.99)
    fig.text(0.5, 0.925,
             "measured billed cost; BIOMA is cheaper left of K* (shaded). Static "
             "reuse is BIOMA's worst case — growing contexts favor it longer.",
             ha="center", fontsize=9.5, color="#6b7280")
    fig.text(0.005, 0.005,
             f"Paired 4-arm, Anthropic models, warmup={warmup}, temperature=0.2. "
             f"fable-5 excluded (safety refusals billed $0). "
             f"Raw data & methodology: github.com/{REPO}/benchmarks/ab-claude-code",
             fontsize=7, color="#6b7280")
    CHARTS.mkdir(parents=True, exist_ok=True)
    out = CHARTS / "savings_on_top_of_caching.png"
    fig.tight_layout(rect=(0, 0.03, 1, 0.9))
    fig.savefig(out, dpi=300)
    plt.close(fig)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
