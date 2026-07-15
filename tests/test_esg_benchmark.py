#!/usr/bin/env python3
"""
tests/test_esg_benchmark.py — the reproducible Frugal-AI benchmark.

Converts the project's MEASURED token savings (ground truth from the published
reports) into bounded energy/emissions estimates using the declared literature
coefficients in `bioma.esg`. Deterministic and offline: every input below is a
published measurement; every output carries (low, mid, high) bounds and a
caching-adjusted variant. Prints the report and, with --report, writes
`reports/BIOMA_ESG_BENCHMARK.md`.

    python tests/test_esg_benchmark.py --report
"""
from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from bioma.esg import GRID_GCO2_PER_KWH, KWH_PER_MTOK, estimate_saving  # noqa: E402

# ---- MEASURED inputs (ground truth, published in the repo) ----------------- #
UNIVERSAL = [(1605, 78), (2489, 123), (2489, 123), (1835, 81), (1806, 280), (1610, 83)]
SESSION = (47_890, 2_022, 16)              # tokens before, after, rounds
QUALITY_S1 = [(7612, 193), (11694, 298), (8793, 215), (7812, 393), (7619, 200)]
LOCAL_WH_MEASURED = (0.754, 7_481)         # Wh, tokens — laptop CPU (upper bracket)

DEPLOY_DISPATCHES_PER_DAY = 100_000        # illustrative deployment scenario
CACHE_SCENARIO = (0.75, 0.10)              # aggressive caching counterfactual


def f3(t: tuple[float, float, float], unit: str, k: float = 1.0) -> str:
    return f"{t[0]*k:,.1f} / {t[1]*k:,.1f} / {t[2]*k:,.1f} {unit}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    lines: list[str] = []
    say = lines.append

    say("# B.I.O.M.A. — Benchmark Frugal AI: tokens medidos → Wh → gCO2e")
    say("")
    say("> Gerado por `tests/test_esg_benchmark.py` (determinístico, offline).")
    say("> **Tokens = medição** (relatórios publicados neste repo). **Energia/CO2 =")
    say("> estimativa** com coeficientes declarados da literatura: "
        f"{KWH_PER_MTOK['low']}–{KWH_PER_MTOK['high']} kWh/milhão de tokens "
        f"(central {KWH_PER_MTOK['mid']}), grid mundial {GRID_GCO2_PER_KWH['world']:.0f} gCO2e/kWh (IEA).")
    say("> Todo número traz limites (baixo/central/alto) e variante ajustada por caching.")
    say("")
    say("## KPI oficial do projeto: energia por token")
    say("")
    say("A redução percentual é **exata e independente do coeficiente** (ele cancela):")
    say("a mesma auditoria do kernel que conta tokens antes/depois define o KPI.")
    say("A conversão para Wh/gCO2e herda a incerteza declarada do coeficiente.")
    say("")

    # ---- per-dispatch (universal integration) ------------------------------ #
    saved_disp = [b - a for b, a in UNIVERSAL]
    avg_saved = sum(saved_disp) / len(saved_disp)
    est = estimate_saving(int(avg_saved))
    say("## 1. Por dispatch (média dos 6 modelos online, medido)")
    say("")
    say(f"- Tokens economizados/dispatch (média): **{avg_saved:,.0f}**")
    say(f"- Energia evitada/dispatch: **{f3(est['wh'], 'Wh')}**")
    say(f"- Emissões evitadas/dispatch (grid mundial): **{f3(est['gco2e'], 'gCO2e')}**")
    say("")

    # ---- per-session (16 rounds, measured) --------------------------------- #
    b, a, rounds = SESSION
    est_s = estimate_saving(b - a)
    say("## 2. Por sessão longa (16 rodadas, OpenRouter ao vivo, medido)")
    say("")
    say(f"- Tokens economizados/sessão: **{b - a:,}** ({b:,} → {a:,})")
    say(f"- Energia evitada/sessão: **{f3(est_s['wh'], 'Wh')}**")
    say(f"- Emissões evitadas/sessão: **{f3(est_s['gco2e'], 'gCO2e')}**")
    say("")

    # ---- deployment scenario ------------------------------------------------ #
    per_dispatch = (b - a) / rounds
    daily_tokens = per_dispatch * DEPLOY_DISPATCHES_PER_DAY
    yearly = estimate_saving(int(daily_tokens * 365))
    hit, cost = CACHE_SCENARIO
    yearly_cached = estimate_saving(int(daily_tokens * 365), cache_hit=hit, cache_cost=cost)
    say(f"## 3. Por deployment (cenário: {DEPLOY_DISPATCHES_PER_DAY:,} dispatches/dia, "
        "carga de sessão longa)")
    say("")
    say(f"- Tokens economizados/dia: {daily_tokens/1e6:,.1f}M (medido: "
        f"{per_dispatch:,.0f} tok/dispatch)")
    say("")
    say("| Baseline contrafactual | Energia evitada/ano | Emissões evitadas/ano (mundial) |")
    say("| :--- | ---: | ---: |")
    say(f"| Sem caching | {f3(yearly['wh'], 'MWh', 1e-6)} | {f3(yearly['gco2e'], 'tCO2e', 1e-6)} |")
    say(f"| Com caching agressivo ({hit:.0%} hit a {cost:.0%} do custo) "
        f"| {f3(yearly_cached['wh'], 'MWh', 1e-6)} | {f3(yearly_cached['gco2e'], 'tCO2e', 1e-6)} |")
    say("")
    say("Por grid (variante central, sem caching): "
        + " · ".join(f"{g.upper()} {yearly['wh'][1]/1e6*v/1000:,.1f} tCO2e"
                     for g, v in GRID_GCO2_PER_KWH.items()))
    say("")

    # ---- cross-check vs our own hardware measurement ------------------------ #
    wh, tok = LOCAL_WH_MEASURED
    local_kwh_mtok = wh / tok * 1e3
    say("## 4. Sanidade: nossa medição própria vs o coeficiente da literatura")
    say("")
    say(f"- Medido em CPU de notebook (`reports/BIOMA_ENERGY_LOCAL.md`): {wh} Wh / "
        f"{tok:,} tok ≈ **{local_kwh_mtok:.2f} kWh/Mtok** (energia MARGINAL — idle e PUE")
    say("  excluídos, modelo de 1B parâmetros, carga de prefill).")
    say(f"- Fica ~{KWH_PER_MTOK['low']/local_kwh_mtok:.0f}× abaixo do piso da literatura — coerente: "
        "o intervalo 0,5–1,3 kWh/Mtok")
    say("  descreve inferência de modelos de fronteira em produção (10–100× mais parâmetros,")
    say("  sistema completo + PUE). Nossa medição delimita o caso de modelo pequeno; a redução")
    say("  percentual do KPI independe do coeficiente (ele cancela na razão).")
    say("")
    say("## Alegação oficial (escopo honesto)")
    say("")
    say("> O B.I.O.M.A. é uma **camada Frugal AI client-side** que reduz de forma")
    say("> **auditável** o custo energético de inferência **por deployment** — tokens")
    say("> medidos por dispatch, convertidos por coeficientes declarados. Não é uma")
    say("> alegação de impacto global; escala com adoção e com o grid de quem opera.")
    say("")
    say("Fontes dos coeficientes: Epoch AI (~0,3 Wh/query GPT-4o), literatura de")
    say("inferência 2024–2025 (0,5–1,3 kWh/Mtok); grids: IEA (mundo), EEA (UE),")
    say("EPA eGRID (EUA), EPE/ONS (BR). Substitua pelo fator do seu grid/provedor.")

    text = "\n".join(lines)
    print(text)
    if args.report:
        path = os.path.join(_ROOT, "reports", "BIOMA_ESG_BENCHMARK.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"\n📄 relatório salvo em {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
