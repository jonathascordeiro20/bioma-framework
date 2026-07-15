"""
`bioma/esg_report.py` — the design-partner instrument: turn a deployment's REAL
gateway audit log into a per-deployment ESG + cost case report.

The gateway writes one JSONL line per request (`tokens_before`, `tokens_after`,
`reduction`, kernel μs). This reads that ground-truth log and reports, for the
deployment: tokens avoided, and — via the declared literature coefficients in
`bioma.esg` — bounded Wh / gCO2e / USD avoided. Every input is measured on the
partner's own traffic; only the energy conversion is an estimate (with bounds).

A partner runs their real workload through the gateway, then:

    python -m bioma.esg_report bioma_gateway_audit.jsonl --grid eu --price-in 2.0

No third-party data is invented here — the report is empty until a real log exists.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from bioma.esg import GRID_GCO2_PER_KWH, KWH_PER_MTOK, estimate_saving


def read_audit(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def build_report(rows: list[dict], *, grid: str = "world",
                 price_in_per_mtok: float | None = None,
                 cache_hit: float = 0.0) -> dict:
    n = len(rows)
    before = sum(int(r.get("tokens_before", 0)) for r in rows)
    after = sum(int(r.get("tokens_after", 0)) for r in rows)
    saved = before - after
    est = estimate_saving(saved, grid=grid, cache_hit=cache_hit) if saved > 0 else None
    usd = None
    if price_in_per_mtok is not None and saved > 0:
        usd = saved / 1e6 * price_in_per_mtok
    return {
        "requests": n,
        "tokens_before": before, "tokens_after": after, "tokens_saved": saved,
        "reduction": (1 - after / before) if before else 0.0,
        "grid": grid,
        "wh_avoided": est["wh"] if est else (0.0, 0.0, 0.0),
        "gco2e_avoided": est["gco2e"] if est else (0.0, 0.0, 0.0),
        "usd_avoided": usd,
    }


def render_md(rep: dict, coeff_note: str) -> str:
    wl, wm, wh = rep["wh_avoided"]
    gl, gm, gh = rep["gco2e_avoided"]
    L = [
        "# Relatório ESG de deployment — B.I.O.M.A. (dados do seu tráfego real)",
        "",
        f"> Gerado de {rep['requests']:,} requests do audit do gateway. Tokens = medidos "
        "no seu tráfego; Wh/gCO2e = estimativa com coeficientes declarados "
        f"({coeff_note}); limites baixo/central/alto.",
        "",
        "| Métrica | Valor |",
        "| :--- | ---: |",
        f"| Requests medidos | {rep['requests']:,} |",
        f"| Tokens de entrada | {rep['tokens_before']:,} → {rep['tokens_after']:,} |",
        f"| **Tokens evitados** | **{rep['tokens_saved']:,}** (−{rep['reduction']*100:.1f}%) |",
        f"| Energia evitada (grid {rep['grid']}) | {wl:,.1f} / **{wm:,.1f}** / {wh:,.1f} Wh |",
        f"| Emissões evitadas | {gl:,.1f} / **{gm:,.1f}** / {gh:,.1f} gCO2e |",
    ]
    if rep["usd_avoided"] is not None:
        L.append(f"| Custo de entrada evitado | **${rep['usd_avoided']:,.4f}** |")
    L += ["",
          "Escopo: redução auditável POR DEPLOYMENT (não global). A energia herda a "
          "incerteza declarada do coeficiente; substitua pelo fator do seu grid/provedor.",
          ""]
    return "\n".join(L)


def _main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="ESG deployment report from a gateway audit log.")
    ap.add_argument("audit", help="path to bioma_gateway_audit.jsonl")
    ap.add_argument("--grid", default="world", choices=sorted(GRID_GCO2_PER_KWH))
    ap.add_argument("--price-in", type=float, default=None,
                    help="input price $/M tokens for your model (optional → $ avoided)")
    ap.add_argument("--cache-hit", type=float, default=0.0)
    ap.add_argument("--out", default=None, help="write the markdown report here")
    args = ap.parse_args(argv)
    if not os.path.exists(args.audit):
        print(f"audit log não encontrado: {args.audit} — rode seu tráfego pelo gateway primeiro.")
        return 2
    rows = read_audit(args.audit)
    if not rows:
        print("audit vazio — nenhum request medido ainda.")
        return 2
    rep = build_report(rows, grid=args.grid, price_in_per_mtok=args.price_in,
                       cache_hit=args.cache_hit)
    coeff = f"{KWH_PER_MTOK['low']}–{KWH_PER_MTOK['high']} kWh/Mtok, grid {args.grid}"
    md = render_md(rep, coeff)
    print(md)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"📄 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
