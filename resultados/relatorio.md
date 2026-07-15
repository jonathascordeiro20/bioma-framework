# DevBench B.I.O.M.A. — Relatório Final (dados reais da API, nunca estimados)

> Protocolo adaptado para OpenRouter (adaptações registradas na seção 6). Matriz: 2 braços × 7 modelos × 3 tarefas × 3 réplicas = 126 execuções (+2 do piloto, incluídas e marcadas). BIOMA commit `625d6b4`, half_life 6.0, threshold 0.35, temperatura 0.0, ordem alternada A-B/B-A. Dados brutos: `execucoes.csv`, `usage_raw.jsonl`, `precos_openrouter.json`.

## 1. Tabela mestre — mediana (p90) por tarefa × modelo × braço

| Tarefa | Modelo | in_tok A | in_tok B | custo A | custo B | sucesso A | sucesso B |
| :--- | :--- | ---: | ---: | ---: | ---: | :---: | :---: |
| T1-bugfix | Claude Fable 5 | 5,299 | 393 | $0.0689 ($0.0696) | $0.0000 ($0.0000) | 67% | 0% |
| T1-bugfix | Claude Opus 4.8 | 5,299 | 393 | $0.0322 ($0.0327) | $0.0076 ($0.0078) | 100% | 100% |
| T1-bugfix | Claude Sonnet 5 | 5,299 | 393 | $0.0129 ($0.0136) | $0.0030 ($0.0031) | 100% | 100% |
| T1-bugfix | GPT-5.6 Sol | 3,518 | 245 | $0.0041 ($0.0243) | $0.0036 ($0.0036) | 100% | 100% |
| T1-bugfix | GLM-5.2 | 3,584 | 274 | $0.0055 ($0.0067) | $0.0013 ($0.0013) | 100% | 100% |
| T1-bugfix | Grok 4.5 | 3,665 | 466 | $0.0057 ($0.0100) | $0.0035 ($0.0043) | 100% | 100% |
| T1-bugfix | Gemini 3.5 Flash | 4,159 | 283 | $0.0074 ($0.0074) | $0.0015 ($0.0015) | 100% | 100% |
| T2-refactor | Claude Fable 5 | 6,641 | 337 | $0.0749 ($0.0750) | $0.0104 ($0.0105) | 100% | 100% |
| T2-refactor | Claude Opus 4.8 | 6,641 | 337 | $0.0359 ($0.0360) | $0.0052 ($0.0058) | 100% | 100% |
| T2-refactor | Claude Sonnet 5 | 6,641 | 337 | $0.0154 ($0.0159) | $0.0020 ($0.0021) | 100% | 100% |
| T2-refactor | GPT-5.6 Sol | 4,399 | 224 | $0.0040 ($0.0293) | $0.0029 ($0.0029) | 100% | 100% |
| T2-refactor | GLM-5.2 | 4,501 | 234 | $0.0066 ($0.0068) | $0.0014 ($0.0020) | 100% | 100% |
| T2-refactor | Grok 4.5 | 4,567 | 418 | $0.0037 ($0.0101) | $0.0017 ($0.0021) | 100% | 100% |
| T2-refactor | Gemini 3.5 Flash | 5,147 | 247 | $0.0087 ($0.0088) | $0.0013 ($0.0013) | 100% | 100% |
| T3-feature | Claude Fable 5 | 15,133 | 307 | $0.1694 ($0.1705) | $0.0123 ($0.0127) | 100% | 100% |
| T3-feature | Claude Opus 4.8 | 15,133 | 307 | $0.0818 ($0.0829) | $0.0050 ($0.0050) | 100% | 100% |
| T3-feature | Claude Sonnet 5 | 15,133 | 307 | $0.0328 ($0.0335) | $0.0020 ($0.0021) | 100% | 100% |
| T3-feature | GPT-5.6 Sol | 10,182 | 182 | $0.0077 ($0.0661) | $0.0033 ($0.0033) | 100% | 100% |
| T3-feature | GLM-5.2 | 10,220 | 194 | $0.0154 ($0.0156) | $0.0010 ($0.0011) | 100% | 100% |
| T3-feature | Grok 4.5 | 10,389 | 389 | $0.0071 ($0.0228) | $0.0018 ($0.0022) | 100% | 100% |
| T3-feature | Gemini 3.5 Flash | 12,447 | 215 | $0.0200 ($0.0200) | $0.0016 ($0.0016) | 100% | 100% |

Sucesso inclui execuções com erro (erro ⇒ sucesso=0). Tokens comparáveis apenas dentro do mesmo modelo (tokenizadores distintos — ex.: T3 tem 15.133 tok no tokenizador Claude e 10.182 no GPT para o MESMO texto).

## 2. Economia de custo por modelo (pares tarefa×réplica, braço B vs A)

| Modelo | economia mediana | economia absoluta mediana/chamada | pares |
| :--- | ---: | ---: | ---: |
| Claude Fable 5 | **−89%** | $0.1082 | 6 |
| Claude Opus 4.8 | **−86%** | $0.0308 | 9 |
| Claude Sonnet 5 | **−86%** | $0.0133 | 9 |
| GPT-5.6 Sol | **−57%** | $0.0043 | 9 |
| GLM-5.2 | **−80%** | $0.0052 | 9 |
| Grok 4.5 | **−57%** | $0.0052 | 9 |
| Gemini 3.5 Flash | **−80%** | $0.0059 | 9 |

**Hipótese do protocolo confirmada:** a economia ABSOLUTA é maior no Fable 5 (entrada $10/M): mediana de $0.1082 por chamada — no T3 chega a ~$0,157/chamada (−92%).

<details><summary>Diferenças pareadas (todas)</summary>

- Claude Fable 5 · T2-refactor · r1: $0.0749 → $0.0103 (−86%)
- Claude Fable 5 · T2-refactor · r2: $0.0750 → $0.0105 (−86%)
- Claude Fable 5 · T2-refactor · r3: $0.0737 → $0.0104 (−86%)
- Claude Fable 5 · T3-feature · r1: $0.1645 → $0.0127 (−92%)
- Claude Fable 5 · T3-feature · r2: $0.1694 → $0.0123 (−93%)
- Claude Fable 5 · T3-feature · r3: $0.1705 → $0.0121 (−93%)
- Claude Opus 4.8 · T1-bugfix · r1: $0.0322 → $0.0076 (−77%)
- Claude Opus 4.8 · T1-bugfix · r2: $0.0321 → $0.0078 (−76%)
- Claude Opus 4.8 · T1-bugfix · r3: $0.0327 → $0.0076 (−77%)
- Claude Opus 4.8 · T2-refactor · r1: $0.0359 → $0.0052 (−86%)
- Claude Opus 4.8 · T2-refactor · r2: $0.0359 → $0.0052 (−86%)
- Claude Opus 4.8 · T2-refactor · r3: $0.0360 → $0.0058 (−84%)
- Claude Opus 4.8 · T3-feature · r1: $0.0829 → $0.0049 (−94%)
- Claude Opus 4.8 · T3-feature · r2: $0.0818 → $0.0050 (−94%)
- Claude Opus 4.8 · T3-feature · r3: $0.0809 → $0.0050 (−94%)
- Claude Sonnet 5 · T1-bugfix · r1: $0.0134 → $0.0030 (−77%)
- Claude Sonnet 5 · T1-bugfix · r2: $0.0136 → $0.0031 (−77%)
- Claude Sonnet 5 · T1-bugfix · r3: $0.0125 → $0.0030 (−76%)
- Claude Sonnet 5 · T2-refactor · r1: $0.0154 → $0.0021 (−86%)
- Claude Sonnet 5 · T2-refactor · r2: $0.0159 → $0.0017 (−89%)
- Claude Sonnet 5 · T2-refactor · r3: $0.0151 → $0.0020 (−86%)
- Claude Sonnet 5 · T3-feature · r1: $0.0328 → $0.0021 (−94%)
- Claude Sonnet 5 · T3-feature · r2: $0.0335 → $0.0019 (−94%)
- Claude Sonnet 5 · T3-feature · r3: $0.0325 → $0.0020 (−94%)
- GPT-5.6 Sol · T1-bugfix · r1: $0.0243 → $0.0036 (−85%)
- GPT-5.6 Sol · T1-bugfix · r2: $0.0039 → $0.0034 (−15%)
- GPT-5.6 Sol · T1-bugfix · r3: $0.0041 → $0.0036 (−13%)
- GPT-5.6 Sol · T2-refactor · r1: $0.0293 → $0.0029 (−90%)
- GPT-5.6 Sol · T2-refactor · r2: $0.0040 → $0.0029 (−27%)
- GPT-5.6 Sol · T2-refactor · r3: $0.0040 → $0.0029 (−27%)
- GPT-5.6 Sol · T3-feature · r1: $0.0661 → $0.0033 (−95%)
- GPT-5.6 Sol · T3-feature · r2: $0.0077 → $0.0033 (−57%)
- GPT-5.6 Sol · T3-feature · r3: $0.0077 → $0.0032 (−59%)
- GLM-5.2 · T1-bugfix · r1: $0.0049 → $0.0013 (−72%)
- GLM-5.2 · T1-bugfix · r2: $0.0067 → $0.0013 (−80%)
- GLM-5.2 · T1-bugfix · r3: $0.0055 → $0.0006 (−88%)
- GLM-5.2 · T2-refactor · r1: $0.0066 → $0.0014 (−78%)
- GLM-5.2 · T2-refactor · r2: $0.0064 → $0.0020 (−69%)
- GLM-5.2 · T2-refactor · r3: $0.0068 → $0.0006 (−91%)
- GLM-5.2 · T3-feature · r1: $0.0156 → $0.0011 (−93%)
- GLM-5.2 · T3-feature · r2: $0.0154 → $0.0010 (−94%)
- GLM-5.2 · T3-feature · r3: $0.0039 → $0.0009 (−77%)
- Grok 4.5 · T1-bugfix · r1: $0.0100 → $0.0043 (−57%)
- Grok 4.5 · T1-bugfix · r2: $0.0051 → $0.0035 (−32%)
- Grok 4.5 · T1-bugfix · r3: $0.0057 → $0.0031 (−46%)
- Grok 4.5 · T2-refactor · r1: $0.0101 → $0.0021 (−80%)
- Grok 4.5 · T2-refactor · r2: $0.0037 → $0.0017 (−55%)
- Grok 4.5 · T2-refactor · r3: $0.0037 → $0.0017 (−55%)
- Grok 4.5 · T3-feature · r1: $0.0228 → $0.0022 (−90%)
- Grok 4.5 · T3-feature · r2: $0.0070 → $0.0018 (−75%)
- Grok 4.5 · T3-feature · r3: $0.0071 → $0.0018 (−74%)
- Gemini 3.5 Flash · T1-bugfix · r1: $0.0074 → $0.0015 (−80%)
- Gemini 3.5 Flash · T1-bugfix · r2: $0.0019 → $0.0015 (−23%)
- Gemini 3.5 Flash · T1-bugfix · r3: $0.0074 → $0.0015 (−80%)
- Gemini 3.5 Flash · T2-refactor · r1: $0.0087 → $0.0013 (−85%)
- Gemini 3.5 Flash · T2-refactor · r2: $0.0088 → $0.0013 (−85%)
- Gemini 3.5 Flash · T2-refactor · r3: $0.0033 → $0.0013 (−60%)
- Gemini 3.5 Flash · T3-feature · r1: $0.0200 → $0.0016 (−92%)
- Gemini 3.5 Flash · T3-feature · r2: $0.0200 → $0.0016 (−92%)
- Gemini 3.5 Flash · T3-feature · r3: $0.0035 → $0.0016 (−55%)

</details>

## 3. Efeito no cache

**NÃO MEDIDO.** Esta adaptação não exercita `cache_control`; o usage do OpenRouter não retornou campos de cache para estes dispatches. A interação apoptose×prompt-caching permanece pergunta aberta para a versão E2E com gateway compatível com a API Anthropic.

## 4. Qualidade — RESULTADO DE PRIMEIRA PÁGINA

**Claude Fable 5 × T1 × braço B falhou 3/3** (resposta vazia, 1–3 tokens de saída, custo $0.0000) onde o braço A passou. O braço A do mesmo modelo/tarefa também teve 1 réplica parcial (probes 33%). Nas demais tarefas (T2, T3) o Fable 5 no braço B respondeu 100%. Hipótese (não confirmada): filtro do endpoint sobre o prompt desidratado — consistente com o `content_filter` já documentado em `reports/BIOMA_QUALITY_PRESERVATION.md`. Fora essa célula: **60/60 execuções válidas do braço B com 100% de probes**, paridade total.

| Métrica global | Braço A | Braço B |
| :--- | :---: | :---: |
| Sucesso (incluindo erros) | 63/64 (98%) | 61/64 (95%) |

## 5. Verificação cruzada e achado de auditoria

- Custo total medido (usage da API): braço A **$1.9504** · braço B **$0.2209** · lote $2.1713.
- `/cost` e Console Anthropic: **NÃO APLICÁVEL** nesta adaptação (OpenRouter); auditoria equivalente = dashboard do OpenRouter por chave.
- **Achado de auditoria:** chamadas idênticas (mesmos tokens) tiveram custo até 6× diferente entre réplicas no MESMO braço (ex.: GPT-5.6 Sol T1-A: $0.0243 vs $0.0039 com 3.518 tokens iguais) — o OpenRouter roteia para provedores com preços distintos. O usage.cost reflete a rota real; a tabela `precos_openrouter.json` é o preço de lista. Medianas mitigam; declarado como variância de rota.

## 6. Limitações declaradas

1. Tarefas simuladas (sessões de dev-agente com probes objetivas), não execução E2E de agente em repositório real — a versão com Claude Code + gateway Anthropic-compatível permanece bloqueada (gateway inexistente no BIOMA; falha registrada no pre-flight).
2. N pequeno (3 tarefas × 3 réplicas), um único formato de prompt.
3. Prompt caching não exercitado (seção 3).
4. Tokenizadores distintos entre modelos — comparações apenas intra-modelo.
5. Variância de rota do OpenRouter (seção 5) afeta custos individuais; medianas e pares por réplica mitigam.
6. 'Gemini 3.5' substituído por `google/gemini-3.5-flash` (única variante 3.5 na API); piloto (2 linhas extras de T1×Sonnet) incluído no CSV.
