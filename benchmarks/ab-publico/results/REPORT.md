# B.I.O.M.A. — Benchmark A/B pareado (contexto completo vs. shield BIOMA)

**Data da execução:** 2026-07-19
**Roteador:** OpenRouter (`--via-openrouter`), uma única `OPENROUTER_API_KEY` para os 8 modelos.
**Desenho:** para cada `(tarefa, modelo, rep)`, a MESMA tarefa roda duas vezes — braço **A (baseline)** manda o histórico de sessão inteiro; braço **B (bioma)** manda `CognitiveFirewall.shield(history, final_prompt, system)`. Pares diretamente comparáveis.
**Escala real:** 8 modelos × 30 tarefas × 3 reps × 2 braços = **1.440 chamadas reais**, todas gravadas em `results/results.jsonl`.

> **Regra desta execução:** todo número abaixo vem de `results/results.jsonl`, gerado por chamadas reais à API. Nenhum `--mock`. Nenhuma tarefa/shield/keyword foi ajustada para "passar" — recusas e perdas de qualidade são **resultados** do benchmark.

---

## 1. Setup real e integridade dos dados

- **1.440/1.440 linhas** gravadas, **0 erros**, **0 duplicatas** após validação de unicidade por `(model, task, rep, arm)`.
- Cada modelo: exatamente 180 linhas (30 tarefas × 3 reps × 2 braços), reps `[0,1,2]`, 90 baseline + 90 bioma.
- **Custo real total (campo `cost_usd` reportado pelo OpenRouter, presente em 100% das linhas): US$ 22,32.**

### Chamadas completadas vs. "falhas" por modelo

Nenhuma linha de `error` técnico. As únicas "não-respostas" foram **recusas do classificador de segurança da Anthropic no fable-5** (detalhe na §5). Todos os demais modelos responderam em 180/180.

| Modelo | Tier | Linhas | Respostas efetivas | Recusas duras |
| :--- | :--- | ---: | ---: | ---: |
| claude-haiku | budget | 180 | 180 | 0 |
| gpt-mini | budget | 180 | 180 | 0 |
| deepseek-chat | budget | 180 | 180 | 0 |
| claude-opus | frontier | 180 | 180 | 0 |
| gpt-5.6-sol | frontier | 180 | 180 | 0 |
| gpt-5.5 | frontier | 180 | 180 | 0 |
| gemini-pro | frontier | 180 | 180 | 0 |
| **fable-5** | frontier | 180 | **82** | **98** |

### Custo real por modelo (US$, do OpenRouter)

| Modelo | baseline | bioma | economia | economia % |
| :--- | ---: | ---: | ---: | ---: |
| claude-opus | 4,3665 | 1,5578 | 2,8087 | 64% |
| fable-5 | 3,2331 | 1,9565 | 1,2766 | 39% |
| gpt-5.6-sol | 2,0030 | 1,1557 | 0,8472 | 42% |
| gpt-5.5 | 2,1520 | 1,6037 | 0,5483 | 25% |
| gemini-pro | 1,8357 | 1,1479 | 0,6879 | 37% |
| claude-haiku | 0,6369 | 0,2715 | 0,3653 | 57% |
| gpt-mini | 0,1981 | 0,1351 | 0,0629 | 32% |
| deepseek-chat | 0,0481 | 0,0187 | 0,0294 | 61% |
| **Total** | **14,47** | **7,85** | **6,63** | **46%** |

O braço bioma custou **46% menos** que o baseline no agregado (US$ 7,85 vs 14,47; total faturado US$ 22,32), medido em dólares reais. A economia % em dólar varia por modelo porque cada um também gera nº distinto de tokens de saída (que o shield não corta) — por isso a economia em dólar (46%) é menor que a redução de tokens de entrada (84,7%).

---

## 2. Saída completa de `analyze.py`

```
== claude-haiku (budget) — 90 pairs ==
  input-token reduction : 84.9% (95% CI [84.2, 85.5])
  Wilcoxon signed-rank  : W=0.0 p=1.69e-16
  success A -> B        : 97% -> 97%
  tokens saved          : 415,895
  dollars saved         : $0.3653
  energy saved (mid)    : 374.31 Wh / 166.57 gCO2e

== claude-opus (frontier) — 90 pairs ==
  input-token reduction : 84.5% (95% CI [83.8, 85.2])
  Wilcoxon signed-rank  : W=0.0 p=1.69e-16
  success A -> B        : 97% -> 96%
  tokens saved          : 560,552
  dollars saved         : $2.8087
  energy saved (mid)    : 504.50 Wh / 224.50 gCO2e

== deepseek-chat (budget) — 90 pairs ==
  input-token reduction : 84.5% (95% CI [83.9, 85.2])
  Wilcoxon signed-rank  : W=0.0 p=1.71e-16
  success A -> B        : 87% -> 83%
  tokens saved          : 368,898
  dollars saved         : $0.0521
  energy saved (mid)    : 332.01 Wh / 147.74 gCO2e

== fable-5 (frontier) — 90 pairs ==
  input-token reduction : 84.5% (95% CI [83.8, 85.2])
  Wilcoxon signed-rank  : W=0.0 p=1.69e-16
  success A -> B        : 33% -> 47%
  tokens saved          : 547,866
  dollars saved         : $4.9831
  energy saved (mid)    : 493.08 Wh / 219.42 gCO2e

== gemini-pro (frontier) — 90 pairs ==
  input-token reduction : 84.8% (95% CI [84.2, 85.5])
  Wilcoxon signed-rank  : W=0.0 p=1.71e-16
  success A -> B        : 63% -> 60%
  tokens saved          : 399,103
  dollars saved         : $0.7732
  energy saved (mid)    : 359.19 Wh / 159.84 gCO2e

== gpt-5.5 (frontier) — 90 pairs ==
  input-token reduction : 84.8% (95% CI [84.2, 85.5])
  Wilcoxon signed-rank  : W=0.0 p=1.69e-16
  success A -> B        : 86% -> 86%
  tokens saved          : 356,246
  dollars saved         : $1.7349
  energy saved (mid)    : 320.62 Wh / 142.68 gCO2e

== gpt-5.6-sol (frontier) — 90 pairs ==
  input-token reduction : 84.8% (95% CI [84.2, 85.5])
  Wilcoxon signed-rank  : W=0.0 p=1.69e-16
  success A -> B        : 91% -> 89%
  tokens saved          : 362,386
  dollars saved         : $1.9191
  energy saved (mid)    : 326.15 Wh / 145.14 gCO2e

== gpt-mini (budget) — 90 pairs ==
  input-token reduction : 84.8% (95% CI [84.2, 85.5])
  Wilcoxon signed-rank  : W=0.0 p=1.69e-16
  success A -> B        : 97% -> 99%
  tokens saved          : 357,253
  dollars saved         : $0.2648
  energy saved (mid)    : 321.53 Wh / 143.08 gCO2e

== by stale_ratio (all models pooled) ==
  stale pairs tok red %             ci95 succ A succ B
------------------------------------------------------
   high   240     83.4% [  83.2,  83.5]    75%    80%
 medium   240     83.0% [  82.8,  83.2]    84%    80%
    low   240     87.7% [  87.2,  88.1]    85%    86%

== cross-tier summary ==
         model      tier pairs tok red % succ A succ B   $ saved
----------------------------------------------------------------
  claude-haiku    budget    90     84.9%    97%    97% $  0.3653
      gpt-mini    budget    90     84.8%    97%    99% $  0.2648
 deepseek-chat    budget    90     84.5%    87%    83% $  0.0521
       gpt-5.5  frontier    90     84.8%    86%    86% $  1.7349
   gpt-5.6-sol  frontier    90     84.8%    91%    89% $  1.9191
    gemini-pro  frontier    90     84.8%    63%    60% $  0.7732
   claude-opus  frontier    90     84.5%    97%    96% $  2.8087
       fable-5  frontier    90     84.5%    33%    47% $  4.9831
```

> `dollars saved` aqui usa os preços de tabela do `models.yaml` (API direta). Ver §6 para a diferença vs. o custo real faturado do OpenRouter.

---

## 3. Leitura em uma frase

Em **720 pares**, o shield BIOMA cortou **84,7% dos tokens de entrada em média** (IC 95% ~[84, 85], Wilcoxon p≈1,7e-16 para todos os 8 modelos), com **qualidade agregada praticamente neutra** (sucesso pooled 81,2% → 81,9%; excluindo o fable-5, 88,1% → 87,0%, uma queda de ~1 ponto) e **custo real faturado 46% menor** (US$ 14,47 → 7,85). A redução de tokens é uniforme entre modelos e tiers; o que varia é como cada modelo tolera a poda.

---

## 4. Comparação frontier interna: fable-5 vs gpt-5.6-sol vs claude-opus

Números reais por braço (90 pares/modelo), incluindo **custo por tarefa resolvida** (custo real do braço ÷ nº de sucessos):

| Modelo | Braço | Resolvidas/90 | Sucesso | in tok/chamada | out tok/chamada | Custo real | **US$/resolvida** |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| **claude-opus** | baseline | 87 | 97% | 7.325 | 476 | 4,3665 | 0,0502 |
| **claude-opus** | **bioma** | 86 | 96% | 1.100 | 472 | 1,5578 | **0,0181** |
| **gpt-5.6-sol** | baseline | 82 | 91% | 4.668 | 364 | 2,0030 | 0,0244 |
| **gpt-5.6-sol** | **bioma** | 80 | 89% | 689 | 316 | 1,1557 | **0,0144** |
| **fable-5** | baseline | 30 | 33% | 7.325 | 187 | 3,2331 | 0,1078 |
| **fable-5** | **bioma** | 42 | 47% | 1.100 | 324 | 1,9565 | **0,0466** |

**Ranking custo-por-tarefa-resolvida (US$, menor = melhor):**

- **Braço bioma:** gpt-5.6-sol **0,0144** < claude-opus **0,0181** < fable-5 **0,0466**.
- **Braço baseline:** gpt-5.6-sol 0,0244 < claude-opus 0,0502 < fable-5 0,1078.

Leitura:
- **claude-opus** é o mais forte em qualidade absoluta (97%→96%), e o bioma o torna **2,8× mais barato por tarefa resolvida** perdendo só 1 ponto.
- **gpt-5.6-sol** é o **mais eficiente em custo** nos dois braços; com bioma resolve 80/90 a US$ 0,0144/tarefa (1,7× mais barato que seu baseline).
- **fable-5** é o outlier: a poda BIOMA **melhora** o resultado (33%→47%) porque a carga menor dispara **menos recusas** de segurança (§5) — efeito colateral inesperado e favorável ao shield.

---

## 5. Recusas do fable-5 (resultado real, não corrigido)

O fable-5 (via OpenRouter → classificadores de segurança da Anthropic) recusou tarefas de código benignas com `finish_reason=content_filter`, mensagem literal:

> *"This request triggered restrictions on violative cyber content and was blocked under Anthropic's Usage Policy."*

Diagnóstico isolado (sondas controladas): o gatilho é o **system prompt** que enquadra o modelo como *"coding assistant working inside the orders-api repository… Answer with working code"* — a superfície agêntica dual-use que o Fable 5 vigia. A tarefa em si (ex.: implementar `LRUCache`) é benigna; com system prompt neutro, não há recusa (0/6). É **falso positivo**, determinístico para o enquadramento agêntico e ausente em todos os outros 7 modelos (nenhum content_filter).

Duas formas do sinal:
- **Recusa dura:** conteúdo vazio, ~3 tokens, bloqueio real.
- **Soft-flag:** o modelo devolve uma solução completa e válida E ainda é marcado `content_filter`; essas passam no gate normalmente.

| Braço fable-5 | Recusa dura | Soft-flag (respondeu) | Respostas úteis |
| :--- | ---: | ---: | ---: |
| baseline | 59/90 | 6 | 31 |
| **bioma** | **39/90** | 15 | 51 |

**Achado central:** o braço bioma teve **39 recusas duras contra 59 do baseline** (−34%). Como o shield preserva o system prompt (classe SYSTEM, nunca purgada), ele não elimina o gatilho — mas ao remover o histórico volumoso reduz a "superfície de conteúdo" que o classificador pontua, derrubando a taxa de falso positivo. É por isso que o único caso em que o bioma **sobe** a qualidade é justamente o modelo com o filtro mais agressivo.

---

## 6. Leitura honesta: onde o bioma perdeu qualidade

**Agregado:** neutro. Pooled 81,2%→81,9%; sem o fable-5, 88,1%→87,0% (−1,1 ponto). Custo real cai à metade e a redução de tokens é 84,7%.

**Por stale_ratio (a suspeita prévia):** a hipótese era que a apoptose padrão cortaria ~84% do contexto **mesmo quando quase tudo é relevante** (low-stale), machucando a qualidade ali. Os dados **confirmam a poda agressiva mas refutam a consequência temida**:

| stale | pares | redução tok | sucesso A→B |
| :--- | ---: | ---: | :--- |
| high | 240 | 83,4% | 75% → **80%** |
| medium | 240 | 83,0% | 84% → **80%** |
| low | 240 | **87,7%** | 85% → **86%** |

- Em **low-stale** (quase tudo relevante) a poda é a **mais agressiva** (87,7%) — a suspeita de "corta ~84% mesmo quando é relevante" está **correta**.
- Mas o sucesso em low-stale **não caiu** (85%→86%). A perda concentra-se em **medium-stale** (84%→80%, −4 pontos) — não em low.
- Em **high-stale** o bioma até **sobe** (75%→80%): purgar histórico obsoleto ajuda o modelo.

**As 5 tarefas onde o braço bioma mais perdeu qualidade** (Δ = sucesso_bioma − sucesso_baseline sobre 3 reps):

| Δ | Modelo | Tarefa | stale | A→B |
| ---: | :--- | :--- | :--- | :--- |
| −3 | fable-5 | py-flatten-dict | low | 3/3 → 0/3 |
| −3 | fable-5 | rs-parse-config | medium | 3/3 → 0/3 |
| −3 | fable-5 | sql-upsert-inventory | medium | 3/3 → 0/3 |
| −2 | deepseek-chat | ts-deep-clone | high | 3/3 → 1/3 |
| −2 | gemini-pro | ts-debounce | high | 2/3 → 0/3 |

Ressalva importante: **3 das 5 maiores perdas são do fable-5** e estão **entrelaçadas com o comportamento de recusa** — nessas tarefas específicas o payload shieldado foi bloqueado enquanto o baseline respondeu, o inverso do padrão agregado. Apenas **uma** perda de topo é low-stale (fable-5/py-flatten-dict), e é justamente uma das entrelaçadas com recusa. Não há, no conjunto, evidência de que o low-stale seja o ponto fraco do shield: nos modelos sem filtro de segurança, as perdas de topo são medium/high-stale e de magnitude 1–2 reps.

---

## 7. Limitações

- **Taxa OpenRouter vs. preços de tabela.** O `analyze.py` calcula `dollars saved` com os preços do `models.yaml` (API direta). O custo **real faturado** vem do campo `cost_usd` do OpenRouter (§1), que reflete o preço praticado no roteador. Os catálogos batem para quase todos; a exceção registrada é o **deepseek** (tabela 0,14/0,28 vs OpenRouter **0,10/0,20 por 1M tok**). Preços reais confirmados no catálogo OpenRouter (2026-07-19): fable-5 10/50, gpt-5.6-sol 5/30, claude-opus 5/25, gpt-5.5 5/30, gemini-pro 2/12, claude-haiku 1/5, gpt-mini 0,75/4,50, deepseek 0,10/0,20 (in/out por 1M tok).
- **Aproximação de tokens.** O `estimate_cost.py` e o fallback usam tiktoken/4-chars-por-token; mas os `input_tokens`/`output_tokens` do dataset e o `cost_usd` vêm do **usage real** de cada resposta, então as métricas do relatório não dependem da aproximação.
- **Correções de slug (passo 2).** **Nenhuma necessária** — os 8 `openrouter_id` do `models.yaml` existem no catálogo real do OpenRouter, incluindo `google/gemini-3.1-pro-preview`.
- **Energia (Wh/gCO2e).** Estimativa via coeficientes de literatura declarados em `bioma.esg` (0,5–1,3 kWh/Mtok); os tokens são medidos, a conversão é estimada com limites — nunca inventada.
- **Ajustes de harness feitos nesta execução** (dentro de `benchmarks/ab-publico/`, sem tocar tarefa/shield/keywords):
  1. **Fix de encoding no gate** — `evaluate_success` gravava `solution.py` em cp1252 (default do Windows) e crashava quando o código do modelo continha caracteres não-Latin-1 (ex.: `→`), virando falha espúria. Corrigido para `encoding="utf-8"`.
  2. **Captura de recusa** — o runner agora grava `refusal` + `finish_reason` verbatim (antes a recusa virava resposta vazia inexplicada).
  3. **Captura de custo real** — grava o `cost_usd` reportado pelo OpenRouter por chamada (base da §1).
  4. **Durabilidade** — `flush + fsync` por linha, para que um SIGKILL não perca chamadas pagas.
- **Reprodutibilidade/limpeza do dataset.** Dois processos de background morreram por terminação externa (job object do Windows) durante o tier budget; o deepseek foi re-executado limpo (processo destacado via `Start-Process`). Duplicatas de chave geradas por escritores sobrepostos foram removidas mantendo a 1ª ocorrência: **8 linhas** no deepseek e reconstrução final do dataset como `540 budget (backup validado) + 900 frontier`, resultando em 1.440 linhas únicas, 0 duplicatas, 0 erros.

---

## 8. Arquivos

- `results/results.jsonl` — 1.440 linhas, dado bruto de cada braço-chamada.
- `results/ANALYSIS.txt` — saída íntegra do `analyze.py`.
- `results/REPORT.md` — este relatório.
