# B.I.O.M.A. — Benchmark Frugal AI: tokens medidos → Wh → gCO2e

> Gerado por `tests/test_esg_benchmark.py` (determinístico, offline).
> **Tokens = medição** (relatórios publicados neste repo). **Energia/CO2 =
> estimativa** com coeficientes declarados da literatura: 0.5–1.3 kWh/milhão de tokens (central 0.9), grid mundial 445 gCO2e/kWh (IEA).
> Todo número traz limites (baixo/central/alto) e variante ajustada por caching.

## KPI oficial do projeto: energia por token

A redução percentual é **exata e independente do coeficiente** (ele cancela):
a mesma auditoria do kernel que conta tokens antes/depois define o KPI.
A conversão para Wh/gCO2e herda a incerteza declarada do coeficiente.

## 1. Por dispatch (média dos 6 modelos online, medido)

- Tokens economizados/dispatch (média): **1,844**
- Energia evitada/dispatch: **0.9 / 1.7 / 2.4 Wh**
- Emissões evitadas/dispatch (grid mundial): **0.4 / 0.7 / 1.1 gCO2e**

## 2. Por sessão longa (16 rodadas, OpenRouter ao vivo, medido)

- Tokens economizados/sessão: **45,868** (47,890 → 2,022)
- Energia evitada/sessão: **22.9 / 41.3 / 59.6 Wh**
- Emissões evitadas/sessão: **10.2 / 18.4 / 26.5 gCO2e**

## 3. Por deployment (cenário: 100,000 dispatches/dia, carga de sessão longa)

- Tokens economizados/dia: 286.7M (medido: 2,867 tok/dispatch)

| Baseline contrafactual | Energia evitada/ano | Emissões evitadas/ano (mundial) |
| :--- | ---: | ---: |
| Sem caching | 52.3 / 94.2 / 136.0 MWh | 23.3 / 41.9 / 60.5 tCO2e |
| Com caching agressivo (75% hit a 10% do custo) | 17.0 / 30.6 / 44.2 MWh | 7.6 / 13.6 / 19.7 tCO2e |

Por grid (variante central, sem caching): WORLD 41.9 tCO2e · EU 21.7 tCO2e · US 36.3 tCO2e · BR 9.4 tCO2e

## 4. Sanidade: nossa medição própria vs o coeficiente da literatura

- Medido em CPU de notebook (`reports/BIOMA_ENERGY_LOCAL.md`): 0.754 Wh / 7,481 tok ≈ **0.10 kWh/Mtok** (energia MARGINAL — idle e PUE
  excluídos, modelo de 1B parâmetros, carga de prefill).
- Fica ~5× abaixo do piso da literatura — coerente: o intervalo 0,5–1,3 kWh/Mtok
  descreve inferência de modelos de fronteira em produção (10–100× mais parâmetros,
  sistema completo + PUE). Nossa medição delimita o caso de modelo pequeno; a redução
  percentual do KPI independe do coeficiente (ele cancela na razão).

## Alegação oficial (escopo honesto)

> O B.I.O.M.A. é uma **camada Frugal AI client-side** que reduz de forma
> **auditável** o custo energético de inferência **por deployment** — tokens
> medidos por dispatch, convertidos por coeficientes declarados. Não é uma
> alegação de impacto global; escala com adoção e com o grid de quem opera.

Fontes dos coeficientes: Epoch AI (~0,3 Wh/query GPT-4o), literatura de
inferência 2024–2025 (0,5–1,3 kWh/Mtok); grids: IEA (mundo), EEA (UE),
EPA eGRID (EUA), EPE/ONS (BR). Substitua pelo fator do seu grid/provedor.
