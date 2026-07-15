#!/usr/bin/env python3
"""
tests/simula_economia_mercado.py — simulação de economia ($ e energia) com BIOMA.

REGRA DE INTEGRIDADE: as entradas por chamada são MEDIDAS (medianas do DevBench,
resultados/execucoes.csv — usage real da API, preços reais); os volumes/mix/adoção
são PREMISSAS DECLARADAS de cenário; a energia usa os coeficientes declarados da
literatura em bioma.esg (0,5–1,3 kWh/Mtok) com limites baixo/central/alto.
Nenhum número é apresentado sem sua origem.

    python tests/simula_economia_mercado.py          # imprime e grava o relatório
"""
from __future__ import annotations

import csv
import os
import statistics
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from bioma.esg import GRID_GCO2_PER_KWH, KWH_PER_MTOK, estimate_saving  # noqa: E402

RES = os.path.join(_ROOT, "resultados")

# ---- entradas MEDIDAS: medianas por modelo do DevBench ---------------------- #
def measured() -> dict[str, dict]:
    with open(os.path.join(RES, "execucoes.csv"), encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if not r["observacoes"]]
    out: dict[str, dict] = {}
    for m in sorted({r["modelo"] for r in rows}):
        a = [r for r in rows if r["modelo"] == m and r["braco"] == "A"]
        b = [r for r in rows if r["modelo"] == m and r["braco"] == "B"]
        if not a or not b:
            continue
        out[m] = {
            "tok_saved": statistics.median(int(x["input_tokens"]) for x in a)
                         - statistics.median(int(x["input_tokens"]) for x in b),
            "usd_saved": statistics.median(float(x["custo_usd"]) for x in a)
                         - statistics.median(float(x["custo_usd"]) for x in b),
        }
    return out


# ---- cenários: PREMISSAS DECLARADAS ----------------------------------------- #
# mix = {modelo: fração das chamadas}
SCENARIOS = [
    ("S1 · Equipe dev (startup)", 5_000,
     {"Claude Sonnet 5": 1.0},
     "5k chamadas/dia, um modelo mid-tier — perfil de time pequeno com agente de código"),
    ("S2 · Produto SaaS com agentes", 100_000,
     {"GLM-5.2": 0.4, "Gemini 3.5 Flash": 0.3, "Claude Sonnet 5": 0.2, "Claude Opus 4.8": 0.1},
     "100k chamadas/dia, mix custo-consciente (70% modelos baratos)"),
    ("S3 · Enterprise frontier", 1_000_000,
     {"Claude Fable 5": 0.1, "Claude Opus 4.8": 0.2, "Claude Sonnet 5": 0.3,
      "GPT-5.6 Sol": 0.2, "GLM-5.2": 0.1, "Grok 4.5": 0.05, "Gemini 3.5 Flash": 0.05},
     "1M chamadas/dia, mix pesado em fronteira — perfil de plataforma corporativa"),
]

EV_KM_PER_KWH = 6.0          # ~6 km/kWh (VE médio)
HOUSE_KWH_MONTH = 160.0      # residência média BR (EPE, ordem de grandeza)


def fmt3(t, unit, k=1.0):
    return f"{t[0]*k:,.1f} / {t[1]*k:,.1f} / {t[2]*k:,.1f} {unit}"


def main() -> int:
    m = measured()
    L: list[str] = []
    say = L.append
    say("# Simulação de economia com B.I.O.M.A. — mercado e sustentabilidade")
    say("")
    say("> Entradas por chamada = MEDIDAS (medianas do DevBench, usage real da API,")
    say("> 126 execuções, commit 625d6b4). Volumes, mix e adoção = PREMISSAS de")
    say(f"> cenário, declaradas. Energia = coeficientes da literatura "
        f"({KWH_PER_MTOK['low']}–{KWH_PER_MTOK['high']} kWh/Mtok), grid mundial "
        f"{GRID_GCO2_PER_KWH['world']:.0f} gCO2e/kWh; limites baixo/central/alto sempre.")
    say("")
    say("## Entradas medidas (mediana por chamada, braço A − braço B)")
    say("")
    say("| Modelo | tokens evitados/chamada | $ evitados/chamada |")
    say("| :--- | ---: | ---: |")
    for name, d in m.items():
        say(f"| {name} | {d['tok_saved']:,.0f} | ${d['usd_saved']:.4f} |")
    say("")

    say("## Cenários de deployment (por ano)")
    say("")
    say("| Cenário | Chamadas/dia | 💰 economia/ano | ⚡ energia evitada/ano | 🌍 CO2e evitado/ano |")
    say("| :--- | ---: | ---: | ---: | ---: |")
    for name, calls, mix, note in SCENARIOS:
        usd_day = sum(m[mod]["usd_saved"] * frac for mod, frac in mix.items()) * calls
        tok_day = sum(m[mod]["tok_saved"] * frac for mod, frac in mix.items()) * calls
        est = estimate_saving(int(tok_day * 365))
        say(f"| {name} | {calls:,} | **${usd_day*365:,.0f}** "
            f"| {fmt3(est['wh'], 'MWh', 1e-6)} | {fmt3(est['gco2e'], 'tCO2e', 1e-6)} |")
    say("")
    for name, calls, mix, note in SCENARIOS:
        say(f"- **{name}**: {note}. Mix: "
            + ", ".join(f"{f*100:.0f}% {mo}" for mo, f in mix.items()) + ".")
    say("")

    # equivalências do cenário S3 (central)
    _, calls, mix, _ = SCENARIOS[2]
    tok_day = sum(m[mod]["tok_saved"] * frac for mod, frac in mix.items()) * calls
    est3 = estimate_saving(int(tok_day * 365))
    kwh_mid = est3["wh"][1] / 1000.0
    say("## O que significa (equivalências do S3, variante central)")
    say("")
    say(f"- **{kwh_mid/1000:,.1f} MWh/ano** ≈ consumo de **{kwh_mid/ (HOUSE_KWH_MONTH*12):,.0f} "
        f"residências brasileiras** por um ano (~{HOUSE_KWH_MONTH:.0f} kWh/mês) "
        f"≈ **{kwh_mid*EV_KM_PER_KWH:,.0f} km** rodados em veículo elétrico.")
    say(f"- CO2e por grid: " + " · ".join(
        f"{g.upper()} {est3['wh'][1]/1e9*v:,.1f} t" for g, v in GRID_GCO2_PER_KWH.items()) + ".")
    say("")

    # contexto de mercado (rótulo explícito: projeção de terceiros + adoção hipotética)
    say("## Contexto de mercado (NÃO é alegação de produto — adoção é hipótese)")
    say("")
    say("Projeção de mercado (Goldman Sachs): consumo de tokens ×24 entre 2026 e 2030,")
    say("para ~120 quatrilhões de tokens/mês. Premissas desta camada: 50% do volume é")
    say("agêntico/entrada; 50% desse payload é peso morto removível (medimos 80–97% em")
    say("sessões longas — 50% é o desconto conservador para tráfego misto).")
    say("")
    say("| Adoção de higiene de payload | Tokens evitados/ano | ⚡ energia/ano | 🌍 CO2e/ano |")
    say("| :--- | ---: | ---: | ---: |")
    base_year_tokens = 120e15 * 12 * 0.5 * 0.5   # tokens/ano evitáveis no teto do cenário
    for adoption in (0.01, 0.05, 0.10):
        tok = base_year_tokens * adoption
        est = estimate_saving(int(tok))
        say(f"| {adoption*100:.0f}% do mercado 2030 | {tok/1e15:,.1f} quatrilhões "
            f"| {fmt3(est['wh'], 'TWh', 1e-12)} | {fmt3(est['gco2e'], 'MtCO2e', 1e-12)} |")
    say("")
    say("Leitura honesta: a 5% de adoção, a higiene de payload evitaria da ordem de")
    say("**unidades de TWh/ano** — comparável ao consumo de um país pequeno — mas isso")
    say("é potencial condicionado à adoção, não impacto do BIOMA hoje. A alegação de")
    say("produto permanece a do whitepaper: redução auditável POR DEPLOYMENT (cenários")
    say("S1–S3, ancorados em medição).")
    say("")
    say("## Origem de cada número")
    say("")
    say("- $/chamada e tokens/chamada: `resultados/execucoes.csv` (usage real, 126 exec).")
    say("- Coeficientes de energia e grids: `bioma/esg.py` (literatura declarada).")
    say("- Projeção de tokens 2030: Goldman Sachs (pesquisa de mercado, jul/2026).")
    say("- Volumes/mix/adoção dos cenários: premissas declaradas neste arquivo.")

    text = "\n".join(L)
    print(text)
    path = os.path.join(RES, "SIMULACAO_MERCADO.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(f"\n📄 gravado em {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
