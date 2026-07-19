#!/usr/bin/env python3
"""Analyze paired A/B benchmark results.

Reads results/results.jsonl, pairs baseline vs. bioma arms per
(model, task, rep), and reports per model:

  * paired Wilcoxon signed-rank test on input tokens (A vs B)
  * bootstrap 95% CI on the mean token-reduction percentage
  * success rate per arm (quality gate)
  * dollars saved (models.yaml prices) and estimated energy saved
    (bioma.esg declared literature coefficients — never invented here)
  * a cross-tier summary table

Usage: python analyze.py [--results results/results.jsonl]
"""
from __future__ import annotations

import argparse
import json
import pathlib
from collections import defaultdict

import numpy as np
import yaml
from scipy import stats

from bioma.esg import estimate_saving

ROOT = pathlib.Path(__file__).resolve().parent


def load_rows(path: pathlib.Path) -> list[dict]:
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return [r for r in rows if "error" not in r]


def load_prices() -> dict:
    with open(ROOT / "models.yaml") as f:
        cfg = yaml.safe_load(f)
    prices = {}
    for tier, models in cfg["tiers"].items():
        for name, m in models.items():
            prices[name] = {"in": m["price_in"], "out": m["price_out"], "tier": tier}
    return prices


def pair_rows(rows: list[dict]) -> dict:
    """{model: [(baseline_row, bioma_row), ...]} paired on (task, rep)."""
    index = defaultdict(dict)
    for r in rows:
        index[(r["model"], r["task"], r.get("rep", 0))][r["arm"]] = r
    pairs = defaultdict(list)
    for (model, _task, _rep), arms in index.items():
        if "baseline" in arms and "bioma" in arms:
            pairs[model].append((arms["baseline"], arms["bioma"]))
    return pairs


def bootstrap_ci(values: np.ndarray, n_boot: int = 10_000, seed: int = 7) -> tuple:
    rng = np.random.default_rng(seed)
    means = rng.choice(values, size=(n_boot, len(values)), replace=True).mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def analyze_model(model: str, pairs: list, prices: dict) -> dict:
    a_in = np.array([p[0]["input_tokens"] for p in pairs], dtype=float)
    b_in = np.array([p[1]["input_tokens"] for p in pairs], dtype=float)
    a_out = np.array([p[0]["output_tokens"] for p in pairs], dtype=float)
    b_out = np.array([p[1]["output_tokens"] for p in pairs], dtype=float)
    reduction_pct = np.where(a_in > 0, (a_in - b_in) / a_in * 100.0, 0.0)

    if len(pairs) >= 2 and not np.allclose(a_in, b_in):
        w = stats.wilcoxon(a_in, b_in)
        wilcoxon = {"statistic": float(w.statistic), "p_value": float(w.pvalue)}
    else:
        wilcoxon = None

    price = prices[model]
    dollars = float(
        (a_in - b_in).sum() / 1e6 * price["in"] + (a_out - b_out).sum() / 1e6 * price["out"]
    )
    tokens_saved = int((a_in - b_in).sum() + (a_out - b_out).sum())
    energy = estimate_saving(max(0, tokens_saved))

    return {
        "model": model,
        "tier": price["tier"],
        "n_pairs": len(pairs),
        "mean_reduction_pct": float(reduction_pct.mean()),
        "reduction_ci95": bootstrap_ci(reduction_pct),
        "wilcoxon": wilcoxon,
        "success_baseline": float(np.mean([p[0]["success"] for p in pairs])),
        "success_bioma": float(np.mean([p[1]["success"] for p in pairs])),
        "tokens_saved": tokens_saved,
        "dollars_saved": dollars,
        "wh_saved_mid": energy["wh"][1],
        "gco2e_saved_mid": energy["gco2e"][1],
    }


def print_report(reports: list[dict], rows: list[dict]) -> None:
    if any(r.get("mock") for r in rows):
        print("NOTE: results contain --mock runs; success rates for those are meaningless.\n")

    for rep in reports:
        print(f"== {rep['model']} ({rep['tier']}) — {rep['n_pairs']} pairs ==")
        lo, hi = rep["reduction_ci95"]
        print(f"  input-token reduction : {rep['mean_reduction_pct']:.1f}% "
              f"(95% CI [{lo:.1f}, {hi:.1f}])")
        if rep["wilcoxon"]:
            print(f"  Wilcoxon signed-rank  : W={rep['wilcoxon']['statistic']:.1f} "
                  f"p={rep['wilcoxon']['p_value']:.2e}")
        else:
            print("  Wilcoxon signed-rank  : n/a (too few pairs or zero variance)")
        print(f"  success A -> B        : {rep['success_baseline']:.0%} -> "
              f"{rep['success_bioma']:.0%}")
        print(f"  tokens saved          : {rep['tokens_saved']:,}")
        print(f"  dollars saved         : ${rep['dollars_saved']:.4f}")
        print(f"  energy saved (mid)    : {rep['wh_saved_mid']:.2f} Wh / "
              f"{rep['gco2e_saved_mid']:.2f} gCO2e")
        print()

    # stale_ratio breakdown (pooled across models)
    by_stale = defaultdict(list)
    index = defaultdict(dict)
    for r in rows:
        index[(r["model"], r["task"], r.get("rep", 0))][r["arm"]] = r
    for arms in index.values():
        if "baseline" in arms and "bioma" in arms and arms["baseline"].get("stale_ratio"):
            by_stale[arms["baseline"]["stale_ratio"]].append(
                (arms["baseline"], arms["bioma"]))
    if by_stale:
        print("== by stale_ratio (all models pooled) ==")
        header = f"{'stale':>7} {'pairs':>5} {'tok red %':>9} {'ci95':>16} " \
                 f"{'succ A':>6} {'succ B':>6}"
        print(header)
        print("-" * len(header))
        for label in ("high", "medium", "low"):
            pairs = by_stale.get(label)
            if not pairs:
                continue
            a = np.array([p[0]["input_tokens"] for p in pairs], dtype=float)
            b = np.array([p[1]["input_tokens"] for p in pairs], dtype=float)
            red = np.where(a > 0, (a - b) / a * 100.0, 0.0)
            lo, hi = bootstrap_ci(red)
            sa = np.mean([p[0]["success"] for p in pairs])
            sb = np.mean([p[1]["success"] for p in pairs])
            print(f"{label:>7} {len(pairs):>5} {red.mean():>8.1f}% "
                  f"[{lo:>6.1f}, {hi:>5.1f}] {sa:>6.0%} {sb:>6.0%}")
        print()

    # cross-tier table
    print("== cross-tier summary ==")
    header = f"{'model':>14} {'tier':>9} {'pairs':>5} {'tok red %':>9} " \
             f"{'succ A':>6} {'succ B':>6} {'$ saved':>9}"
    print(header)
    print("-" * len(header))
    for rep in sorted(reports, key=lambda r: (r["tier"], -r["mean_reduction_pct"])):
        print(f"{rep['model']:>14} {rep['tier']:>9} {rep['n_pairs']:>5} "
              f"{rep['mean_reduction_pct']:>8.1f}% "
              f"{rep['success_baseline']:>6.0%} {rep['success_bioma']:>6.0%} "
              f"${rep['dollars_saved']:>8.4f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", default=str(ROOT / "results" / "results.jsonl"))
    args = ap.parse_args()

    rows = load_rows(pathlib.Path(args.results))
    if not rows:
        print("no valid result rows found")
        return 1
    prices = load_prices()
    pairs = pair_rows(rows)
    reports = [analyze_model(m, p, prices) for m, p in sorted(pairs.items())]
    print_report(reports, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
