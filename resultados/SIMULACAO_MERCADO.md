# Simulação de economia com B.I.O.M.A. — mercado e sustentabilidade

> Entradas por chamada = MEDIDAS (medianas do DevBench, usage real da API,
> 126 execuções, commit 625d6b4). Volumes, mix e adoção = PREMISSAS de
> cenário, declaradas. Energia = coeficientes da literatura (0.5–1.3 kWh/Mtok), grid mundial 445 gCO2e/kWh; limites baixo/central/alto sempre.

## Entradas medidas (mediana por chamada, braço A − braço B)

| Modelo | tokens evitados/chamada | $ evitados/chamada |
| :--- | ---: | ---: |
| Claude Fable 5 | 6,319 | $0.0636 |
| Claude Opus 4.8 | 6,304 | $0.0308 |
| Claude Sonnet 5 | 6,304 | $0.0131 |
| GLM-5.2 | 4,267 | $0.0056 |
| GPT-5.6 Sol | 4,175 | $0.0043 |
| Gemini 3.5 Flash | 4,900 | $0.0059 |
| Grok 4.5 | 4,149 | $0.0049 |

## Cenários de deployment (por ano)

| Cenário | Chamadas/dia | 💰 economia/ano | ⚡ energia evitada/ano | 🌍 CO2e evitado/ano |
| :--- | ---: | ---: | ---: | ---: |
| S1 · Equipe dev (startup) | 5,000 | **$23,995** | 5.8 / 10.4 / 15.0 MWh | 2.6 / 4.6 / 6.7 tCO2e |
| S2 · Produto SaaS com agentes | 100,000 | **$354,685** | 92.5 / 166.5 / 240.5 MWh | 41.2 / 74.1 / 107.0 tCO2e |
| S3 · Enterprise frontier | 1,000,000 | **$6,727,826** | 1,003.4 / 1,806.1 / 2,608.8 MWh | 446.5 / 803.7 / 1,160.9 tCO2e |

- **S1 · Equipe dev (startup)**: 5k chamadas/dia, um modelo mid-tier — perfil de time pequeno com agente de código. Mix: 100% Claude Sonnet 5.
- **S2 · Produto SaaS com agentes**: 100k chamadas/dia, mix custo-consciente (70% modelos baratos). Mix: 40% GLM-5.2, 30% Gemini 3.5 Flash, 20% Claude Sonnet 5, 10% Claude Opus 4.8.
- **S3 · Enterprise frontier**: 1M chamadas/dia, mix pesado em fronteira — perfil de plataforma corporativa. Mix: 10% Claude Fable 5, 20% Claude Opus 4.8, 30% Claude Sonnet 5, 20% GPT-5.6 Sol, 10% GLM-5.2, 5% Grok 4.5, 5% Gemini 3.5 Flash.

## O que significa (equivalências do S3, variante central)

- **1,806.1 MWh/ano** ≈ consumo de **941 residências brasileiras** por um ano (~160 kWh/mês) ≈ **10,836,657 km** rodados em veículo elétrico.
- CO2e por grid: WORLD 803.7 t · EU 415.4 t · US 695.4 t · BR 180.6 t.

## Contexto de mercado (NÃO é alegação de produto — adoção é hipótese)

Projeção de mercado (Goldman Sachs): consumo de tokens ×24 entre 2026 e 2030,
para ~120 quatrilhões de tokens/mês. Premissas desta camada: 50% do volume é
agêntico/entrada; 50% desse payload é peso morto removível (medimos 80–97% em
sessões longas — 50% é o desconto conservador para tráfego misto).

| Adoção de higiene de payload | Tokens evitados/ano | ⚡ energia/ano | 🌍 CO2e/ano |
| :--- | ---: | ---: | ---: |
| 1% do mercado 2030 | 3.6 quatrilhões | 1.8 / 3.2 / 4.7 TWh | 0.8 / 1.4 / 2.1 MtCO2e |
| 5% do mercado 2030 | 18.0 quatrilhões | 9.0 / 16.2 / 23.4 TWh | 4.0 / 7.2 / 10.4 MtCO2e |
| 10% do mercado 2030 | 36.0 quatrilhões | 18.0 / 32.4 / 46.8 TWh | 8.0 / 14.4 / 20.8 MtCO2e |

Leitura honesta: a 5% de adoção, a higiene de payload evitaria da ordem de
**unidades de TWh/ano** — comparável ao consumo de um país pequeno — mas isso
é potencial condicionado à adoção, não impacto do BIOMA hoje. A alegação de
produto permanece a do whitepaper: redução auditável POR DEPLOYMENT (cenários
S1–S3, ancorados em medição).

## Origem de cada número

- $/chamada e tokens/chamada: `resultados/execucoes.csv` (usage real, 126 exec).
- Coeficientes de energia e grids: `bioma/esg.py` (literatura declarada).
- Projeção de tokens 2030: Goldman Sachs (pesquisa de mercado, jul/2026).
- Volumes/mix/adoção dos cenários: premissas declaradas neste arquivo.
