"""
`certify_m8.py` — M8 acceptance certifier for B.I.O.M.A. (plan Seção 12).

Executes the plan's terminal validation machinery to completion and **persists**
an auditable acceptance certificate (JSON + Markdown).  It runs, and gates on:

  * the 2×2 factorial (mitosis × bus) with K seeded replicates + Welch/MWU,
    Cohen d / Cliff δ, bootstrap CI, Holm-Bonferroni correction, and an a-priori
    power target (plan Fase 9);
  * the mitosis-decision confusion matrix on the control curriculum (fires on
    multi-domain, suppresses on uni-domain / adversarial — plan Fase 6);
  * the identifiability sweep (cos(P, S*) falls as coupling γ grows);
  * the statistical CSR over R runs (Wilson lower bound, necrosis == 0 — Fase 7);
  * a prolonged leak soak (no significant RSS trend ∧ gc-live == 0 ∧ gauge == 0);
  * the bus read-after-write race probe;
  * logical reproducibility (same seed → same topology / verdict);
  * the final invariant audit + the autonomy audit.

Honest by construction: every criterion reports its OBSERVED value against its
declared threshold and a PASS/FAIL — a failing criterion is certified as FAIL,
never masked.  Exit code 0 iff all critical criteria pass.

Run:  python -m bioma_engine.certify_m8   [--K 10] [--soak-cycles 30] [--runs 8]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback

from .config import DEFAULT_CONFIG, THRESHOLD_REGISTRY
from .validation import (
    run_factorial, analyze_factorial, power_analysis_n,
    logical_reproducibility, final_invariant_audit, PRE_REGISTERED, LITERATURE_MAP,
)
from .observability import csr_over_runs, leak_soak, race_probe
from .simulation_harness import SimulationHarness, curriculum
from .autonomy import autonomy_audit

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))


def certify(K: int = 10, soak_cycles: int = 30, runs: int = 8) -> dict:
    """Run the full M8 validation and return the certificate report dict.

    Importable + parameterizable so CI can run a fast profile (small K/cycles)
    and assert the verdict stays ACCEPTED on every change."""
    cfg = DEFAULT_CONFIG
    d = cfg.embed_dim
    THR = THRESHOLD_REGISTRY
    criteria: list[dict] = []

    def crit(name, observed, threshold, passed, *, critical=True):
        criteria.append({"name": name, "observed": observed, "threshold": threshold,
                         "pass": bool(passed), "critical": bool(critical)})

    def guard(label, fn):
        """Run a check; a raised error is itself a FAIL (never a masked pass)."""
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            crit(f"{label} (execution)", {"error": f"{type(exc).__name__}: {exc}",
                 "trace": traceback.format_exc()[-600:]}, "runs without fault", False)
            return None

    t0 = time.time()

    # -- 1. A-priori power + 2×2 factorial ---------------------------------- #
    k_apriori = power_analysis_n(0.8, alpha=PRE_REGISTERED["alpha"], power=PRE_REGISTERED["target_power"])

    def _factorial():
        cells = run_factorial(cfg, K=K, gamma=0.6, seed0=1000)
        fa = analyze_factorial(cells)
        H1 = next(t for t in fa["tests"] if t["hypothesis"] == "H1_mitosis_coverage")
        H2 = next(t for t in fa["tests"] if t["hypothesis"] == "H2_bus_cascade")
        crit("H1 · mitose→cobertura: |d|≥0.8 ∧ significativo (Holm)",
             {"cohens_d": H1["cohens_d"], "cliffs_delta": H1["cliffs_delta"],
              "mean_diff": H1["mean_diff"], "welch_p_holm": H1["welch_p_holm"], "ci95": H1["ci95_diff"]},
             "|d| ≥ 0.8 ∧ p_holm < 0.05",
             abs(H1["cohens_d"]) >= 0.8 and H1["significant_after_correction"])
        crit("H2 · barramento→cascata: |d|≥0.3 ∧ significativo (Holm)",
             {"cohens_d": H2["cohens_d"], "cliffs_delta": H2["cliffs_delta"],
              "mean_diff": H2["mean_diff"], "welch_p_holm": H2["welch_p_holm"], "ci95": H2["ci95_diff"]},
             "|d| ≥ 0.3 ∧ p_holm < 0.05",
             abs(H2["cohens_d"]) >= 0.3 and H2["significant_after_correction"])
        crit("H3 · interação (cascata) positiva [informativo]",
             {"interaction": fa["interaction_cascade"], "ci95": fa["interaction_ci95"],
              "ci_excludes_zero": fa["interaction_significant"]},
             "interação > 0 (direcional)", fa["interaction_cascade"] > 0.0, critical=False)
        return {"K_used": K, "K_apriori_for_d0.8": k_apriori,
                "analysis": fa, "cell_means": fa["cell_means"]}

    factorial = guard("Fatorial 2×2", _factorial)

    # -- 2. Mitosis-decision confusion matrix + identifiability ------------- #
    def _confusion():
        h = SimulationHarness(cfg)
        cm = h.decision_confusion_matrix(curriculum(d))
        crit("Matriz de confusão da mitose (precisão ∧ acurácia)",
             {"precision": cm["precision"], "recall": cm["recall"], "accuracy": cm["accuracy"],
              "tp": cm["tp"], "tn": cm["tn"], "fp": cm["fp"], "fn": cm["fn"]},
             f"precision ≥ {THR['mitosis_precision_floor']} ∧ accuracy = 1.0",
             cm["precision"] >= THR["mitosis_precision_floor"] and cm["accuracy"] == 1.0)
        sweep = h.identifiability_sweep()
        crit("Identificabilidade: cos(P,S*) cai com γ (coordenação necessária)",
             {"cos@min_gamma": sweep[0]["cos_P_vs_Sstar"], "cos@max_gamma": sweep[-1]["cos_P_vs_Sstar"],
              "sweep": sweep},
             "cos decresce quando γ cresce", sweep[-1]["cos_P_vs_Sstar"] < sweep[0]["cos_P_vs_Sstar"])
        return {"confusion": cm, "identifiability": sweep}

    honesty = guard("Matriz de confusão / identificabilidade", _confusion)

    # -- 3. Statistical CSR over R runs ------------------------------------- #
    def _csr():
        prompts = [
            "global market collapse energy grid medical cyber food water strategy",
            "optimize distributed database sharding replication consensus latency",
            "climate model ocean atmosphere ice carbon feedback simulation",
            "supply chain logistics routing inventory demand forecast risk",
            "protein folding docking binding affinity molecular dynamics",
            "network intrusion detection anomaly traffic packet signature",
            "portfolio hedging volatility options greeks risk allocation",
            "compiler optimization loop vectorization register allocation",
        ][: max(3, runs)]
        csr = csr_over_runs(cfg, prompts)
        necrosis = sum(r["necrosis"] for r in csr["per_run"])
        crit("CSR estatístico (=1.0 ∧ necrose=0; Wilson LB reportado)",
             {"csr": csr["csr"], "wilson_lower_bound": csr["wilson_lower_bound"],
              "N_births": csr["total_births"], "survivors": csr["total_survivors"],
              "necrosis_total": necrosis, "runs": csr["runs"]},
             "csr = 1.0 ∧ necrose = 0 (cruzamento gc)", csr["csr"] >= 1.0 and necrosis == 0)
        return csr

    csr = guard("CSR estatístico", _csr)

    # -- 4. Prolonged leak soak -------------------------------------------- #
    def _soak():
        soak = leak_soak(cfg, "global market medical cyber energy grid water food strategy parallel",
                         cycles=soak_cycles, b_max=0.5)
        crit("Soak prolongado sem vazamento (tendência ns ∧ gc=0 ∧ gauge=0)",
             {"cycles": soak["cycles"], "rss_slope_mb_per_cycle": soak["rss_slope_mb_per_cycle"],
              "p_value": soak["p_value"], "gc_live": soak["gc_live_organisms"],
              "gauge_after": soak["gauge_after"], "rss_first": soak["rss_first"], "rss_last": soak["rss_last"]},
             "slope ≤ 0.5 MB/ciclo OU p ≥ 0.05 — E gc_live=0 E gauge=0", soak["leak_free"])
        return soak

    soak = guard("Soak de vazamento", _soak)

    # -- 5. Race probe ------------------------------------------------------ #
    def _race():
        r = race_probe(cfg, n=64)
        crit("Race probe (read-after-write; 0 erros, manifold finito)",
             {"writers": r["writers"], "errors": r["errors"], "shape_consistent": r["shape_consistent"],
              "manifold_finite": r["manifold_finite"], "occupancy": r["occupancy"]},
             "race_free = True", r["race_free"])
        return r

    race = guard("Race probe", _race)

    # -- 6. Logical reproducibility + invariants + autonomy ----------------- #
    def _repro():
        rp = logical_reproducibility(cfg)
        crit("Reprodutibilidade lógica (mesma seed → mesma topologia/veredicto)",
             {"logically_deterministic": rp["logically_deterministic"], "signatures": rp["signatures"]},
             "logically_deterministic = True", rp["logically_deterministic"])
        return rp

    repro = guard("Reprodutibilidade lógica", _repro)

    def _invariants():
        fia = final_invariant_audit(cfg)
        crit("Auditoria final de invariantes (todos)",
             fia, "all_pass = True", fia["all_pass"])
        return fia

    invariants = guard("Auditoria de invariantes", _invariants)

    def _autonomy():
        au = autonomy_audit()
        crit("Autonomia (sem modelo externo/vendor; rede não requerida)",
             {"autonomous": au["autonomous"], "no_external_model_libs": au["no_external_model_libs"],
              "no_vendor_references": au["no_vendor_references"],
              "network_required_to_run_core": au["network_required_to_run_core"]},
             "autonomous = True", au["autonomous"])
        return au

    autonomy = guard("Autonomia", _autonomy)

    # -- Verdict ------------------------------------------------------------ #
    critical = [c for c in criteria if c["critical"]]
    passed = sum(1 for c in critical if c["pass"])
    accepted = all(c["pass"] for c in critical)

    return {
        "certificate": "B.I.O.M.A. — M8 Acceptance Certificate",
        "plan": "PLANO_BIOMA.md · Seção 12 (Definição de Pronto)",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_s": round(time.time() - t0, 1),
        "params": {"K": K, "K_apriori_for_d0.8": k_apriori,
                   "soak_cycles": soak_cycles, "csr_runs": runs},
        "config": {"embed_dim": d, "cell_budget": cfg.cell_budget, "device": "cpu",
                   "fission_mode": "silhouette (validation)", "seed": cfg.seed},
        "pre_registered": PRE_REGISTERED,
        "literature_map": LITERATURE_MAP,
        "criteria": criteria,
        "summary": {"critical_total": len(critical), "critical_passed": passed,
                    "critical_failed": len(critical) - passed},
        "verdict": "ACCEPTED" if accepted else "NOT ACCEPTED",
        "details": {"factorial": factorial, "honesty": honesty, "csr": csr,
                    "soak": soak, "race": race, "repro": repro,
                    "invariants": invariants, "autonomy": autonomy},
    }


def _write_markdown(rep: dict, path: str) -> None:
    L = []
    v = rep["verdict"]
    badge = "✅ ACCEPTED" if v == "ACCEPTED" else "❌ NOT ACCEPTED"
    L.append(f"# {rep['certificate']}")
    L.append("")
    L.append(f"> **Verdict: {badge}** — {rep['summary']['critical_passed']}/"
             f"{rep['summary']['critical_total']} critical criteria passed.")
    L.append("")
    L.append(f"- **Plan:** {rep['plan']}")
    L.append(f"- **Generated (UTC):** {rep['generated_utc']} · elapsed {rep['elapsed_s']}s")
    L.append(f"- **Params:** K={rep['params']['K']} replicates "
             f"(a-priori K for d=0.8 ≈ {rep['params']['K_apriori_for_d0.8']}), "
             f"soak={rep['params']['soak_cycles']} cycles, CSR runs={rep['params']['csr_runs']}")
    L.append(f"- **Config:** embed_dim={rep['config']['embed_dim']}, "
             f"cell_budget={rep['config']['cell_budget']}, device={rep['config']['device']}, "
             f"seed={rep['config']['seed']}")
    L.append("")
    L.append("## Acceptance criteria")
    L.append("")
    L.append("| # | Criterion | Threshold | Result |")
    L.append("|---|---|---|---|")
    for i, c in enumerate(rep["criteria"], 1):
        tag = "" if c["critical"] else " _(informativo)_"
        res = "✅ PASS" if c["pass"] else "❌ FAIL"
        L.append(f"| {i} | {c['name']}{tag} | {c['threshold']} | {res} |")
    L.append("")
    L.append("## Key measured values")
    L.append("")
    det = rep["details"]
    if det.get("factorial"):
        fa = det["factorial"]["analysis"]
        h1 = next(t for t in fa["tests"] if t["hypothesis"] == "H1_mitosis_coverage")
        h2 = next(t for t in fa["tests"] if t["hypothesis"] == "H2_bus_cascade")
        L.append(f"- **H1 mitose→cobertura:** Δ={h1['mean_diff']}, d={h1['cohens_d']}, "
                 f"δ={h1['cliffs_delta']}, p_holm={h1['welch_p_holm']}, CI95={h1['ci95_diff']}")
        L.append(f"- **H2 barramento→cascata:** Δ={h2['mean_diff']}, d={h2['cohens_d']}, "
                 f"δ={h2['cliffs_delta']}, p_holm={h2['welch_p_holm']}, CI95={h2['ci95_diff']}")
        L.append(f"- **Interação (cascata):** {fa['interaction_cascade']} CI95={fa['interaction_ci95']}")
    if det.get("csr"):
        c = det["csr"]
        L.append(f"- **CSR:** {c['csr']} (Wilson LB {c['wilson_lower_bound']}, "
                 f"N={c['total_births']} births, survivors={c['total_survivors']})")
    if det.get("soak"):
        s = det["soak"]
        L.append(f"- **Soak:** slope={s['rss_slope_mb_per_cycle']} MB/cycle (p={s['p_value']}), "
                 f"gc_live={s['gc_live_organisms']}, gauge={s['gauge_after']} over {s['cycles']} cycles")
    if det.get("honesty"):
        cm = det["honesty"]["confusion"]
        L.append(f"- **Mitosis decision:** precision={cm['precision']}, recall={cm['recall']}, "
                 f"accuracy={cm['accuracy']} (tp={cm['tp']},tn={cm['tn']},fp={cm['fp']},fn={cm['fn']})")
    L.append("")
    L.append("## Epistemic honesty")
    L.append("")
    L.append("Every mechanism cites a technical family (no invented papers):")
    for k, val in rep["literature_map"].items():
        L.append(f"- **{k}** → {val}")
    L.append("")
    L.append("_This certificate is reproducible: same seed → same logical topology and verdict._")
    L.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))


def _run() -> dict:
    ap = argparse.ArgumentParser(prog="certify_m8", description="B.I.O.M.A. M8 acceptance certifier")
    ap.add_argument("--K", type=int, default=10, help="factorial replicates per cell")
    ap.add_argument("--soak-cycles", dest="soak_cycles", type=int, default=30, help="prolonged-soak colony count")
    ap.add_argument("--runs", type=int, default=8, help="CSR runs (declared denominator source)")
    args = ap.parse_args()
    return certify(K=args.K, soak_cycles=args.soak_cycles, runs=args.runs)


def main() -> int:  # pragma: no cover - reporting entry point
    rep = _run()
    json_path = os.path.join(_PKG_DIR, "M8_CERTIFICATE.json")
    md_path = os.path.join(_PKG_DIR, "M8_CERTIFICATE.md")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=2, ensure_ascii=False)
    _write_markdown(rep, md_path)

    w = 74
    print("=" * w)
    print(" B.I.O.M.A. — M8 ACCEPTANCE CERTIFICATE ".center(w, "="))
    print("=" * w)
    for i, c in enumerate(rep["criteria"], 1):
        mark = "PASS" if c["pass"] else "FAIL"
        tag = "" if c["critical"] else " (info)"
        print(f"  [{mark}] {i:>2}. {c['name']}{tag}")
    print("-" * w)
    s = rep["summary"]
    print(f"  critical: {s['critical_passed']}/{s['critical_total']} passed  ·  elapsed {rep['elapsed_s']}s")
    print(f"  VERDICT: {rep['verdict']}")
    print(f"  written: {json_path}")
    print(f"           {md_path}")
    print("=" * w)
    return 0 if rep["verdict"] == "ACCEPTED" else 1


if __name__ == "__main__":
    # os._exit avoids the Windows OpenMP atexit teardown crash (0xC0000409).
    _rc = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_rc)
