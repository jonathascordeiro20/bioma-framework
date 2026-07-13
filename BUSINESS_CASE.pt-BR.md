# B.I.O.M.A. — Business Case & ROI

**🌐 [English](BUSINESS_CASE.md) · Português**

> **A % de redução é medida (ground truth). Os preços são de lista, ilustrativos e
> claramente rotulados.** Então a *razão de economia* é real; o valor absoluto em $ escala
> com os seus preços e volumes reais.

## O que é o B.I.O.M.A., em uma linha

Um **micro-kernel local** que você coloca na frente de qualquer chamada de LLM. Ele
**desidrata o contexto de entrada** (apoptose) e o **endurece** (redação de segredo, DDoS
cognitivo, guard de latência) — cortando **~94% do custo de tokens de entrada** em cada
chamada, com qualquer modelo, online ou offline.

## A dor principal que ele mata

> Todo agente e copiloto reenvia contexto inchado a **cada** chamada. Em escala de empresa —
> milhares a milhões de chamadas por dia — esse desperdício é a maior e mais invisível linha
> de um orçamento de IA. O B.I.O.M.A. remove ~94% dela.

## Benchmark real — redução de tokens de entrada medida (6 modelos de fronteira)

| Empresa | Modelo | in_tok base→BIOMA | Redução |
| :--- | :--- | :---: | :---: |
| OpenAI | GPT-5.5 | 1.605→78 | **−95%** |
| Anthropic | Claude Sonnet 5 | 2.489→123 | **−95%** |
| Anthropic | Claude Fable 5 | 2.489→123 | **−95%** |
| Google | Gemini 3.1 Pro | 1.835→81 | **−96%** |
| xAI | Grok 4.5 | 1.806→280 | **−84%** |
| Zhipu | GLM-5.2 | 1.610→83 | **−95%** |

Fonte: `tests/test_universal_integration.py` (dispatch real, `prompt_tokens` reais).

## Modelo de custo (transparente)

```text
economia_por_chamada = tokens_entrada_médios × redução × preço_entrada_por_token
diária = economia_por_chamada × chamadas_por_dia
semanal = diária × 7   ·   mensal = diária × 30   ·   anual = diária × 365
```

Premissas (ajustáveis no dashboard interativo):

- `tokens_entrada_médios` = 2.000 (nosso workload medido; sessões longas de agente são bem maiores).
- `redução` = 0,94 (média medida combinada).
- `preço_entrada` ≈ preço de lista, USD / 1M tokens de entrada: GPT-5.5 $5 · Sonnet 5 $3 ·
  Fable 5 $5 · Gemini 3.1 Pro $2 · Grok 4.5 $3 · GLM-5.2 $0,6.

## Perfis de empresa (volumes ilustrativos)

| Perfil | Quem | chamadas de IA/dia |
| :--- | :--- | ---: |
| **PME** | startup/SaaS: agentes de código + um bot de suporte | 5.000 |
| **Grande empresa** | banco/varejo: 500 posições + agentes de produção | 250.000 |
| **Multinacional** | tech/telecom global: frotas de agentes | 5.000.000 |

## Economia calculada (Claude Sonnet 5, $3/1M in, 2.000 tok/chamada, −94%)

| Perfil | Custo hoje/dia | Com B.I.O.M.A./dia | Economia/dia | Economia/mês | **Economia/ano** |
| :--- | ---: | ---: | ---: | ---: | ---: |
| PME | $30 | $1,80 | $28,20 | $846 | **$10.293** |
| Grande empresa | $1.500 | $90 | $1.410 | $42.300 | **$514.650** |
| Multinacional | $30.000 | $1.800 | $28.200 | $846.000 | **$10.293.000** |

> Uma multinacional rodando agentes de fronteira economiza da ordem de **$10M/ano** só em
> tokens de entrada — de uma camada que também redige segredos e absorve DDoS cognitivo.

## De onde vêm as chamadas (uso real)

- **Agentes do dia a dia:** triagem de suporte, copilotos de ops, análise de documento, Q&A
  interno — contextos longos e crescentes (onde a apoptose economiza mais).
- **Desenvolvimento de software:** agentes de código, review de PR, geração de teste,
  agentes de refatoração — contexto grande de repo/arquivo reenviado a cada passo.

## Impacto da defesa em profundidade (medido, model-agnóstico)

| Sem B.I.O.M.A. | Com B.I.O.M.A. |
| :--- | :--- |
| Segredo no contexto **vaza pro provedor** (baseline `secret→provider = True` nos 6 modelos) | **Redigido** — `False` nos 6 (0 vazados) |
| DDoS cognitivo de 15k tokens **estoura a janela de contexto** | **Desidratado** 32.317→13 tokens (saturação 0.999) |
| Injeção de loop **trava o orquestrador** | **Contido** pelo timeout guard |

> O dashboard interativo de ROI (artefato) deixa você plugar seus próprios volumes e preços.
