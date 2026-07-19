#!/usr/bin/env python3
"""Publication charts for the paired A/B benchmark — computed from raw results.

Every number in every chart is computed from the raw per-arm rows in
`results/results.jsonl` (one JSON object per model×task×rep×arm), or from
`models.yaml` (list prices) / `coefficients.yaml` (energy). Nothing is
hardcoded. If a datum a chart needs is absent from the run, that chart is
skipped and the reason is printed — never fabricated.

Outputs (results/charts/, 300 dpi, white background):
  1. hero_cross_model.png        — median input tokens, baseline vs BIOMA, per model
  2. reduction_by_stale_ratio.png— reduction % boxplot by stale_ratio (+ jittered points)
  3. quality_vs_savings.png      — reduction % vs BIOMA success, one point per model×task
  4. cost_savings_usd.png        — $ saved per 1,000 sessions (input-token list price)
  5. energy_estimate.png         — estimated Wh baseline vs BIOMA per model
  + summary_table.md             — markdown table ready to paste into RESULTS.md / HN

Design honesty: bar axes start at zero; medians and 95% CIs (never maxima, never
"up to"); every figure carries a footer stating N, reps, temperature and the
data/methodology link.

Usage:
  python make_charts.py                       # newest summary_*.json, else results.jsonl
  python make_charts.py --summary results/results.jsonl --formato svg
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import pathlib
from collections import defaultdict

import numpy as np
import yaml

import matplotlib
matplotlib.use("Agg")  # headless: no display needed
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent          # .../results
BENCH = ROOT.parent                                      # .../ab-claude-code
CHARTS = ROOT / "charts"
REPO = "jonathascordeiro20/bioma-framework"
PRICE_DATE = "2026-07-19"                                # date list prices were read from the OpenRouter catalog

# --------------------------------------------------------------------------- #
# palette — two fixed arm hues; within each, frontier darker / budget lighter
# --------------------------------------------------------------------------- #
BASELINE = {"frontier": "#475569", "budget": "#94a3b8"}   # slate: dark / light
BIOMA = {"frontier": "#0f766e", "budget": "#5eead4"}      # teal:  dark / light
BASELINE_FLAT = "#64748b"
BIOMA_FLAT = "#0f766e"
TIER_POINT = {"frontier": "#0f766e", "budget": "#5eead4"} # tier encoded by shade
TIER_MARKER = {"frontier": "o", "budget": "^"}
GRID = "#e5e7eb"

plt.rcParams.update({
    "font.size": 11, "axes.titlesize": 14, "axes.titleweight": "bold",
    "axes.edgecolor": "#94a3b8", "axes.linewidth": 0.8,
    "figure.facecolor": "white", "axes.facecolor": "white",
    "savefig.facecolor": "white",
})


# --------------------------------------------------------------------------- #
# data loading — raw rows are the single source of truth
# --------------------------------------------------------------------------- #
def resolve_source(summary_arg: str | None) -> pathlib.Path:
    """Default: newest results/summary_*.json if present, else results.jsonl."""
    if summary_arg:
        return pathlib.Path(summary_arg)
    summaries = sorted(glob.glob(str(ROOT / "summary_*.json")), key=os.path.getmtime)
    if summaries:
        return pathlib.Path(summaries[-1])
    return ROOT / "results.jsonl"


def load_rows(src: pathlib.Path) -> list[dict]:
    """Load per-arm rows. Accepts a JSONL of rows, or a summary JSON that
    embeds the raw rows under a 'rows'/'results' key. Error rows are dropped."""
    text = src.read_text(encoding="utf-8")
    rows: list[dict] = []
    if src.suffix == ".jsonl":
        for line in text.splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    else:
        obj = json.loads(text)
        if isinstance(obj, list):
            rows = obj
        else:
            rows = obj.get("rows") or obj.get("results") or obj.get("raw") or []
        if not rows:
            raise SystemExit(f"{src} has no embedded raw rows; point --summary at "
                             f"results.jsonl instead.")
    return [r for r in rows if "error" not in r and not r.get("mock")]


def load_prices() -> dict:
    cfg = yaml.safe_load((BENCH / "models.yaml").read_text(encoding="utf-8"))
    out = {}
    for tier, models in cfg["tiers"].items():
        for name, m in models.items():
            out[name] = {"in": float(m["price_in"]), "out": float(m["price_out"]),
                         "tier": tier}
    return out


def load_energy_coeff() -> float | None:
    p = ROOT / "coefficients.yaml"
    if not p.exists():
        return None
    c = yaml.safe_load(p.read_text(encoding="utf-8"))
    return float(c["cloud_inference_kwh_per_mtok"]["mid"])


def pair_rows(rows: list[dict]) -> dict:
    """{model: [(baseline_row, bioma_row), ...]} paired on (task, rep)."""
    idx = defaultdict(dict)
    for r in rows:
        idx[(r["model"], r["task"], r.get("rep", 0))][r["arm"]] = r
    pairs = defaultdict(list)
    for (model, _t, _rep), arms in idx.items():
        if "baseline" in arms and "bioma" in arms:
            pairs[model].append((arms["baseline"], arms["bioma"]))
    return pairs


def boot_ci(values: np.ndarray, stat=np.median, n_boot=10_000, seed=7) -> tuple:
    if len(values) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(values), size=(n_boot, len(values)))
    stats = stat(values[idx], axis=1)
    return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def tier_of(model: str, prices: dict, pairs: dict) -> str:
    if model in prices:
        return prices[model]["tier"]
    return pairs[model][0][0].get("tier", "frontier")


# --------------------------------------------------------------------------- #
# per-model aggregation
# --------------------------------------------------------------------------- #
def model_stats(pairs: dict, prices: dict) -> list[dict]:
    out = []
    for model, ps in pairs.items():
        a_in = np.array([p[0]["input_tokens"] for p in ps], float)
        b_in = np.array([p[1]["input_tokens"] for p in ps], float)
        red = np.where(a_in > 0, (a_in - b_in) / a_in * 100.0, 0.0)
        lo, hi = boot_ci(red, stat=np.median)
        out.append({
            "model": model,
            "tier": tier_of(model, prices, pairs),
            "n": len(ps),
            "median_a_in": float(np.median(a_in)),
            "median_b_in": float(np.median(b_in)),
            "median_red": float(np.median(red)),
            "red_ci": (lo, hi),
            "succ_a": float(np.mean([bool(p[0].get("success")) for p in ps])),
            "succ_b": float(np.mean([bool(p[1].get("success")) for p in ps])),
            "mean_in_saved": float(np.mean(a_in - b_in)),
        })
    # frontier first (dark), then budget; each block sorted by reduction desc
    return sorted(out, key=lambda s: (s["tier"] != "frontier", -s["median_red"]))


def titled(ax, main: str, sub: str):
    """Bold centered title with a gray subtitle placed BELOW it (never overlapping)."""
    ax.set_title(main, fontweight="bold", fontsize=14, pad=30)
    ax.annotate(sub, xy=(0, 1), xytext=(0, 11), xycoords="axes fraction",
                textcoords="offset points", ha="left", va="bottom",
                fontsize=10, color="#6b7280")


def footer(ax_or_fig, n_tasks: int, reps: int, temp: float):
    ax_or_fig.text(
        0.005, 0.005,
        f"Paired A/B, N={n_tasks} tasks, {reps} reps, temperature={temp}. "
        f"Raw data & methodology: github.com/{REPO}/benchmarks/ab-claude-code",
        transform=ax_or_fig.transFigure, fontsize=7, color="#6b7280", ha="left", va="bottom")


# --------------------------------------------------------------------------- #
# CHART 1 — hero: median input tokens baseline vs bioma, grouped by tier
# --------------------------------------------------------------------------- #
def chart_hero(stats, n_tasks, reps, temp, ext):
    order = stats  # already frontier-then-budget
    labels, ypos, seps = [], [], []
    y, last_tier = 0, None
    rowmap = []
    for s in order:
        if last_tier is not None and s["tier"] != last_tier:
            seps.append(y - 0.5)
            y += 0.6
        rowmap.append((y, s))
        labels.append(f"{s['model']}  (n={s['n']})")
        ypos.append(y)
        last_tier = s["tier"]
        y += 1

    fig, ax = plt.subplots(figsize=(10, 7))
    bar_h = 0.38
    for yy, s in rowmap:
        ca = BASELINE[s["tier"]]
        cb = BIOMA[s["tier"]]
        ax.barh(yy + bar_h / 2 + 0.02, s["median_a_in"], height=bar_h, color=ca,
                edgecolor="white", zorder=3)
        ax.barh(yy - bar_h / 2 - 0.02, s["median_b_in"], height=bar_h, color=cb,
                edgecolor="white", zorder=3)
        xmax = max(s["median_a_in"], s["median_b_in"])
        ax.annotate(f"-{s['median_red']:.0f}%", xy=(xmax, yy),
                    xytext=(8, 0), textcoords="offset points", va="center",
                    fontsize=10, fontweight="bold", color=BIOMA["frontier"])
        ax.text(s["median_a_in"] - xmax * 0.01, yy + bar_h / 2 + 0.02,
                f"{s['median_a_in']:,.0f}", va="center", ha="right", fontsize=8,
                color="white", fontweight="bold")
        ax.text(max(s["median_b_in"] - xmax * 0.01, xmax * 0.06), yy - bar_h / 2 - 0.02,
                f"{s['median_b_in']:,.0f}", va="center", ha="right", fontsize=8,
                color="white", fontweight="bold")
    for sy in seps:
        ax.axhline(sy, color="#cbd5e1", lw=1, ls="--", zorder=1)

    ax.set_yticks(ypos)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlim(left=0)  # honest: bars start at zero
    ax.set_xlabel("Median input tokens per task")
    titled(ax, "Input tokens per task: baseline vs. BIOMA shield",
           f"median over {n_tasks} tasks × {reps} reps, temperature={temp}")
    legend = [Patch(facecolor=BASELINE_FLAT, label="baseline (full history)"),
              Patch(facecolor=BIOMA_FLAT, label="BIOMA shield"),
              Patch(facecolor="#1f2937", label="frontier (dark) / budget (light)")]
    ax.legend(handles=legend, loc="lower right", frameon=False, fontsize=9)
    ax.grid(axis="x", color=GRID, zorder=0)
    ax.set_axisbelow(True)
    footer(fig, n_tasks, reps, temp)
    fig.tight_layout(rect=(0.02, 0.03, 1, 1))
    out = CHARTS / f"hero_cross_model.{ext}"
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out


# --------------------------------------------------------------------------- #
# CHART 2 — reduction % by stale_ratio (boxplot + jittered points by tier)
# --------------------------------------------------------------------------- #
def chart_stale(rows, prices, n_tasks, reps, temp, ext):
    idx = defaultdict(dict)
    for r in rows:
        idx[(r["model"], r["task"], r.get("rep", 0))][r["arm"]] = r
    by_stale = defaultdict(list)  # stale -> list of (reduction%, tier)
    for arms in idx.values():
        if "baseline" in arms and "bioma" in arms:
            b, m = arms["baseline"], arms["bioma"]
            sr = b.get("stale_ratio")
            if sr is None or b["input_tokens"] <= 0:
                continue
            red = (b["input_tokens"] - m["input_tokens"]) / b["input_tokens"] * 100.0
            by_stale[sr].append((red, b.get("tier", "frontier")))
    order = [s for s in ("high", "medium", "low") if s in by_stale]
    if not order:
        print("chart 2 skipped: no stale_ratio present in the run")
        return None

    fig, ax = plt.subplots(figsize=(9, 6.5))
    data = [[v for v, _ in by_stale[s]] for s in order]
    bp = ax.boxplot(data, positions=range(len(order)), widths=0.5,
                    patch_artist=True, showfliers=False, zorder=2,
                    medianprops=dict(color="#111827", lw=2))
    for patch in bp["boxes"]:
        patch.set(facecolor="#f1f5f9", edgecolor="#64748b")
    rng = np.random.default_rng(3)
    for i, s in enumerate(order):
        vals = by_stale[s]
        xs = i + rng.uniform(-0.16, 0.16, size=len(vals))
        for (v, tier), x in zip(vals, xs):
            ax.scatter(x, v, s=16, color=TIER_POINT[tier], alpha=0.55,
                       edgecolors="white", linewidths=0.3, zorder=3)
        med = float(np.median([v for v, _ in vals]))
        ax.annotate(f"median {med:.0f}%", xy=(i, med), xytext=(0, 10),
                    textcoords="offset points", ha="center", fontsize=10,
                    fontweight="bold", color="#111827")
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels([f"{s}\n(n={len(by_stale[s])} pairs)" for s in order])
    ax.set_ylabel("Input-token reduction (%)")
    ax.set_ylim(0, 100)  # honest: full 0-100% scale
    titled(ax, "Token savings depend on how much context is stale",
           "reduction % per task, all models pooled, grouped by stale_ratio")
    legend = [Line2D([], [], marker="o", ls="", color=TIER_POINT["frontier"],
                     label="frontier task", markersize=7),
              Line2D([], [], marker="o", ls="", color=TIER_POINT["budget"],
                     label="budget task", markersize=7)]
    ax.legend(handles=legend, loc="lower left", frameon=False, fontsize=9)
    ax.grid(axis="y", color=GRID, zorder=0)
    ax.set_axisbelow(True)
    footer(fig, n_tasks, reps, temp)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    out = CHARTS / f"reduction_by_stale_ratio.{ext}"
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out


# --------------------------------------------------------------------------- #
# CHART 3 — quality vs savings, one point per model×task
# --------------------------------------------------------------------------- #
def chart_quality(rows, prices, pairs, n_tasks, reps, temp, ext):
    idx = defaultdict(dict)
    for r in rows:
        idx[(r["model"], r["task"], r.get("rep", 0))][r["arm"]] = r
    agg = defaultdict(lambda: {"red": [], "succ_b": [], "tier": None})
    base_succ_all = []
    for arms in idx.values():
        if "baseline" in arms and "bioma" in arms:
            b, m = arms["baseline"], arms["bioma"]
            base_succ_all.append(bool(b.get("success")))
            if b["input_tokens"] <= 0:
                continue
            k = (b["model"], b["task"])
            agg[k]["red"].append((b["input_tokens"] - m["input_tokens"]) / b["input_tokens"] * 100)
            agg[k]["succ_b"].append(bool(m.get("success")))
            agg[k]["tier"] = b.get("tier", "frontier")
    if not agg:
        print("chart 3 skipped: no paired rows")
        return None
    base_rate = float(np.mean(base_succ_all)) * 100

    fig, ax = plt.subplots(figsize=(9, 6.5))
    for tier in ("frontier", "budget"):
        xs = [np.mean(v["red"]) for v in agg.values() if v["tier"] == tier]
        ys = [np.mean(v["succ_b"]) * 100 for v in agg.values() if v["tier"] == tier]
        # jitter y a hair so 0/33/67/100% stacks are visible
        jit = np.random.default_rng(5).uniform(-1.5, 1.5, size=len(ys))
        ax.scatter(xs, np.array(ys) + jit, s=40, marker=TIER_MARKER[tier],
                   color=TIER_POINT[tier], alpha=0.6, edgecolors="white",
                   linewidths=0.4, label=f"{tier} (model×task)", zorder=3)
    ax.axhline(base_rate, color="#b91c1c", lw=1.5, ls="--", zorder=2)
    ax.annotate(f"aggregate baseline success = {base_rate:.0f}%",
                xy=(ax.get_xlim()[0], base_rate), xytext=(4, 4),
                textcoords="offset points", color="#b91c1c", fontsize=9, va="bottom")
    ax.set_xlabel("Input-token reduction (%)")
    ax.set_ylabel("BIOMA-arm success rate (%)")
    ax.set_ylim(-5, 105)
    ax.set_xlim(left=0)
    titled(ax, "Savings vs. quality: does compression break answers?",
           "one point per model × task (success averaged over reps)")
    ax.legend(loc="lower left", frameon=False, fontsize=9)
    ax.grid(color=GRID, zorder=0)
    ax.set_axisbelow(True)
    footer(fig, n_tasks, reps, temp)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    out = CHARTS / f"quality_vs_savings.{ext}"
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out


# --------------------------------------------------------------------------- #
# CHART 4 — $ saved per 1,000 sessions (input-token list price)
# --------------------------------------------------------------------------- #
def chart_cost(stats, prices, n_tasks, reps, temp, ext):
    have = [s for s in stats if s["model"] in prices]
    missing = [s["model"] for s in stats if s["model"] not in prices]
    if missing:
        print(f"chart 4 note: no list price for {missing} — omitted from cost chart")
    if not have:
        print("chart 4 skipped: no priced models")
        return None
    # $ saved per session = mean input tokens saved * price_in / 1e6 ; ×1000
    for s in have:
        s["usd_per_1k"] = s["mean_in_saved"] * prices[s["model"]]["in"] / 1e6 * 1000

    have = sorted(have, key=lambda s: (s["tier"] != "frontier", -s["usd_per_1k"]))
    labels = [f"{s['model']}\n(n={s['n']})" for s in have]
    vals = [s["usd_per_1k"] for s in have]
    colors = [BIOMA[s["tier"]] for s in have]

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(range(len(have)), vals, color=colors, edgecolor="white", zorder=3)
    for i, (b, s) in enumerate(zip(bars, have)):
        ax.annotate(f"${s['usd_per_1k']:,.0f}", xy=(i, s["usd_per_1k"]),
                    xytext=(0, 4), textcoords="offset points", ha="center",
                    fontsize=9, fontweight="bold", color="#111827")
    ax.set_xticks(range(len(have)))
    ax.set_xticklabels(labels)
    ax.set_ylim(bottom=0)  # honest
    ax.set_ylabel("Input-token cost saved per 1,000 sessions (USD)")
    titled(ax, "Input-token cost avoided per 1,000 equivalent sessions",
           "linear extrapolation from the measured run × models.yaml input price")
    legend = [Patch(facecolor=BIOMA["frontier"], label="frontier"),
              Patch(facecolor=BIOMA["budget"], label="budget")]
    ax.legend(handles=legend, loc="upper right", frameon=False, fontsize=9)
    ax.grid(axis="y", color=GRID, zorder=0)
    ax.set_axisbelow(True)
    fig.text(0.005, 0.028, f"List prices as of {PRICE_DATE}, linear extrapolation "
             f"from measured run.", fontsize=7, color="#6b7280")
    footer(fig, n_tasks, reps, temp)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    out = CHARTS / f"cost_savings_usd.{ext}"
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out


# --------------------------------------------------------------------------- #
# CHART 5 — estimated Wh baseline vs bioma per model
# --------------------------------------------------------------------------- #
def chart_energy(pairs, prices, coeff, n_tasks, reps, temp, ext):
    if coeff is None:
        print("chart 5 skipped: coefficients.yaml missing (no energy coefficient)")
        return None
    # Wh = tokens/1e6 * kWh/Mtok * 1000. Use total INPUT tokens per arm per model
    # (the quantity the shield changes); reduction % is coefficient-independent.
    rowdata = []
    for model, ps in pairs.items():
        a_in = sum(p[0]["input_tokens"] for p in ps)
        b_in = sum(p[1]["input_tokens"] for p in ps)
        tier = tier_of(model, prices, pairs)
        rowdata.append({"model": model, "tier": tier, "n": len(ps),
                        "wh_a": a_in / 1e6 * coeff * 1000,
                        "wh_b": b_in / 1e6 * coeff * 1000})
    rowdata = sorted(rowdata, key=lambda s: (s["tier"] != "frontier", -(s["wh_a"] - s["wh_b"])))

    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(rowdata))
    w = 0.38
    ax.bar(x - w / 2, [s["wh_a"] for s in rowdata], width=w,
           color=[BASELINE[s["tier"]] for s in rowdata], edgecolor="white",
           label="baseline", zorder=3)
    ax.bar(x + w / 2, [s["wh_b"] for s in rowdata], width=w,
           color=[BIOMA[s["tier"]] for s in rowdata], edgecolor="white",
           label="BIOMA shield", zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{s['model']}\n(n={s['n']})" for s in rowdata])
    ax.set_ylim(bottom=0)  # honest
    ax.set_ylabel(f"Estimated Wh over the run ({n_tasks}×{reps} input payloads)")
    titled(ax, "Estimated input-processing energy: baseline vs. BIOMA",
           "sum over the run, input tokens × cited coefficient")
    legend = [Patch(facecolor=BASELINE_FLAT, label="baseline (full history)"),
              Patch(facecolor=BIOMA_FLAT, label="BIOMA shield"),
              Patch(facecolor="#1f2937", label="frontier (dark) / budget (light)")]
    ax.legend(handles=legend, loc="upper right", frameon=False, fontsize=9)
    ax.grid(axis="y", color=GRID, zorder=0)
    ax.set_axisbelow(True)
    fig.text(0.005, 0.028,
             "Cloud energy ESTIMATED via cited coefficients (coefficients.yaml, "
             "editable). Local kernel overhead measured.",
             fontsize=7, color="#6b7280")
    footer(fig, n_tasks, reps, temp)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    out = CHARTS / f"energy_estimate.{ext}"
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out


# --------------------------------------------------------------------------- #
# summary_table.md
# --------------------------------------------------------------------------- #
def write_table(stats, prices, n_tasks, reps, temp) -> pathlib.Path:
    lines = [
        "| Model | Tier | N | Median reduction (95% CI) | Success baseline | "
        "Success BIOMA | $ saved / 1k sessions |",
        "| :--- | :--- | ---: | :--- | ---: | ---: | ---: |",
    ]
    for s in stats:
        lo, hi = s["red_ci"]
        if s["model"] in prices:
            usd = s["mean_in_saved"] * prices[s["model"]]["in"] / 1e6 * 1000
            usd_s = f"${usd:,.0f}"
        else:
            usd_s = "n/a (no list price)"
        lines.append(
            f"| {s['model']} | {s['tier']} | {s['n']} | "
            f"{s['median_red']:.0f}% [{lo:.0f}, {hi:.0f}] | "
            f"{s['succ_a']*100:.0f}% | {s['succ_b']*100:.0f}% | {usd_s} |")
    lines += [
        "",
        f"_Paired A/B, N={n_tasks} tasks, {reps} reps, temperature={temp}. "
        f"Reduction = input-token reduction, median over pairs with bootstrap 95% CI. "
        f"$ saved extrapolates the measured mean input-token saving × models.yaml "
        f"input price to 1,000 sessions (list prices {PRICE_DATE}). "
        f"Raw data & methodology: github.com/{REPO}/benchmarks/ab-claude-code._",
        "",
    ]
    out = CHARTS / "summary_table.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# --------------------------------------------------------------------------- #
def main() -> int:
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--summary", default=None,
                    help="path to summary_*.json or results.jsonl "
                         "(default: newest summary_*.json, else results.jsonl)")
    ap.add_argument("--formato", choices=["png", "svg"], default="png",
                    help="output format (png default; svg also supported)")
    args = ap.parse_args()

    src = resolve_source(args.summary)
    if not src.exists():
        raise SystemExit(f"data source not found: {src}")
    rows = load_rows(src)
    if not rows:
        raise SystemExit(f"no usable rows in {src}")
    prices = load_prices()
    coeff = load_energy_coeff()
    pairs = pair_rows(rows)
    stats = model_stats(pairs, prices)

    n_tasks = len({r["task"] for r in rows})
    reps = len({r.get("rep", 0) for r in rows})
    # Real generation temperature: run_benchmark.py's OpenAI-compatible call used
    # temperature=0.2 (rows carry no temperature field). Reported verbatim — the
    # run was NOT temperature=0, so charts must not claim it was.
    temp = 0.2

    CHARTS.mkdir(parents=True, exist_ok=True)
    print(f"source: {src}")
    print(f"rows: {len(rows)}  models: {len(pairs)}  tasks: {n_tasks}  reps: {reps}  "
          f"temperature: {temp}")
    generated = []
    for fn in (
        lambda: chart_hero(stats, n_tasks, reps, temp, args.formato),
        lambda: chart_stale(rows, prices, n_tasks, reps, temp, args.formato),
        lambda: chart_quality(rows, prices, pairs, n_tasks, reps, temp, args.formato),
        lambda: chart_cost(stats, prices, n_tasks, reps, temp, args.formato),
        lambda: chart_energy(pairs, prices, coeff, n_tasks, reps, temp, args.formato),
    ):
        out = fn()
        if out:
            generated.append(out)
            print(f"  wrote {out}")
    table = write_table(stats, prices, n_tasks, reps, temp)
    generated.append(table)
    print(f"  wrote {table}")

    print("\n===== summary_table.md =====\n")
    print(table.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
