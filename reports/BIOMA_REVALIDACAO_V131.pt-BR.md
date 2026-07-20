# Revalidação A/B pós-atualização — kernel 1.1.0 + gateway 1.3.1

**Data:** 2026-07-20 · **Gasto real:** ~$0,67 (OpenRouter, custo via `usage.cost`)
**Objetivo:** repetir o benchmark A/B comparativo com as atualizações "Propósito
contexto" (apoptose cache-aware, `effort_gauge`, `BIOMA_AUTO_EFFORT`) e medir a
alavanca nova (orçamento dinâmico de thinking), que até então era só projetada.

## 1. Integridade (grátis, offline)

- Suítes locais: kernel + gateway + firewall + efficiency → **40/40 passed**.
- `run_benchmark.py --mock`: pipeline íntegro com o kernel 1.1.0 (redução ~85%
  visível na integração; sucesso de mock é sem significado por design).

## 2. Piloto A/B pareado (pago) — o benchmark comparativo repetido

4 modelos × 5 tasks × 1 rep × 2 braços = **40 chamadas reais** via OpenRouter
(`benchmarks/ab-publico/results/rerun_v131.jsonl`). Mesmo harness do dataset
público de 1.440 chamadas; braço B usa `CognitiveFirewall.shield` → kernel
**1.1.0**.

| Métrica | Piloto v1.3.1 (20 pares) | Referência publicada (720 pares) |
| :--- | ---: | ---: |
| Redução de input (mediana) | **−82,2%** | −83,8% |
| Redução de input (mín–máx) | −80,8% … −85,8% | — |
| Paridade de sucesso | **17 both-ok · 3 both-fail · 0 divergentes** | paridade agregada |
| Custo real faturado | **−65,0%** ($0,274 → $0,096) | — |
| Latência do kernel | mediana **1,1 µs** (máx 2,7 µs) | ~1 µs |

Leitura: o kernel 1.1.0 **reproduz** o resultado publicado dentro do ruído
esperado de um piloto (Δ 1,6 p.p. na mediana com N 36× menor). Nenhum par onde
o baseline resolveu e o BIOMA não — a única task que falhou (`py-token-bucket`)
falhou nos dois braços em 3 dos 4 modelos (dificuldade da task, não do
contexto podado; no claude-opus os dois braços resolveram).

Modelos: claude-haiku-4.5, deepseek-v4-flash, gpt-5.4-mini, claude-opus-4.8.

## 3. Auto-effort × thinking real (pago) — medição INÉDITA

A lacuna de evidência da release: o ganho de orçamento dinâmico de thinking era
projetado (30–60%), não medido. Experimento
(`tests/measure_auto_effort.py`, dados em `resultados/auto_effort.json`):

- Workload: 10 turnos, mistura realista da calibração (7 triviais / 3
  difíceis), claude-haiku-4.5, mesmo contexto e ordem nos dois braços.
- **Braço A (agente naive):** direto no OpenRouter, todo turno com
  `reasoning={"max_tokens": 4000}` (orçamento fixo — o padrão comum de agentes
  com thinking "ligado e esquecido").
- **Braço B (BIOMA):** via gateway `BIOMA_AUTO_EFFORT=1`, sem parâmetro de
  reasoning — o `effort_gauge` decide por turno.

| Total (10 turnos) | A (naive, budget fixo) | B (BIOMA auto-effort) |
| :--- | ---: | ---: |
| reasoning tokens | 6.174 | **670** |
| output tokens (total) | 31.447 | 27.501 |
| custo real | $0,1588 | **$0,1388** |

**Reasoning tokens: −89%. Custo total: −13% neste mix.**

Mecânica confirmada no audit JSONL: os 7 turnos triviais viraram
`{"enabled": false}` (0 tokens de thinking) e os 3 difíceis mantiveram
raciocínio com orçamento por tier. A decisão custou ~1 µs por request.

### Caveats honestos

1. O −13% de custo (vs −89% de reasoning) é porque neste workload as
   *respostas* dominam o output — o modelo respondeu longo mesmo em turno
   trivial. Em workloads onde thinking domina o output (agentes com orçamentos
   de 16k+), a fração economizada tende ao número de reasoning.
2. Qualidade não foi gateada NESTE experimento (é medição de mecânica de
   custo); os turnos difíceis atingiram o teto de `max_tokens` nos DOIS braços.
   ~~Gate de qualidade pareado fica para a suíte completa~~ → **fechado no
   §4.3**: mesmo desenho com gate pytest, 0 pares divergentes.
3. Piloto é piloto: N=20 pares no A/B e N=10 turnos no auto-effort. Os números
   batem com o dataset grande, mas a reexecução completa (1.440 chamadas,
   ~$30–60) é o próximo passo quando houver saldo.

## 4. Validação de QUALIDADE da saída (adendo 20/07, ~$0,20)

Três camadas, todas com gates objetivos (nunca juiz LLM):

**4.1 A/B do §2 re-analisado por par.** Os 40 runs usaram o gate EXECUTÁVEL
(pytest sobre o código gerado — o mais forte da suíte): **0/20 pares
divergentes**. Em nenhum caso o baseline entregou e o BIOMA não.

**4.2 Sondas de chat (`test_quality_preservation.py`, kernel 1.1.0).** Valores
exatos plantados numa sessão longa e ruidosa; a resposta final tem que contê-los.
3 modelos (Sonnet 5, Haiku 4.5, DeepSeek V4) × 3 cenários:

| Cenário | baseline | BIOMA | tokens |
| :--- | ---: | ---: | ---: |
| S1 fatos taggeados FACT (uso projetado) | 100% | **100%** | −97,2% |
| S2 info em turnos recentes | 100% | **100%** | −97,3% |
| S3 fato antigo NÃO taggeado (limite by design) | 100% | 0% | −97,9% |

Paridade **6/6** nos cenários do contrato; S3 é a degradação documentada e
esperada (informação durável deve ser taggeada `FACT` — é o contrato honesto do
produto, não um bug).

**4.3 Auto-effort com gate executável (`measure_auto_effort_quality.py`).**
Fecha o caveat do §3: 5 tasks reais com gate pytest, contexto IDÊNTICO nos dois
braços (apoptose desligada via `BIOMA_SAFE_THRESHOLD=0` para isolar a variável
de thinking), braço A com budget fixo 4000 vs braço B com auto-effort:

| Métrica | Resultado |
| :--- | :--- |
| Paridade (pytest) | **4 both-ok · 1 both-fail · 0 divergentes** |
| reasoning tokens | 2.352 → 844 (**−64%**) |
| custo real | $0,0453 → $0,0379 (−16%) |

O gauge desligou thinking em 3 das 5 tasks e **todas passaram no gate mesmo
assim** — thinking era desperdício nessas tasks. O único both-fail é o
`py-token-bucket`, que falha nos dois braços em todo o piloto (dificuldade da
task). Dados: `resultados/auto_effort_quality.json`.

**Conclusão de qualidade:** em todas as camadas com gate objetivo, o que foi
pedido via chat foi entregue com qualidade IGUAL com e sem BIOMA — 0 pares
divergentes em 25 comparações executáveis + 6/6 nas sondas do contrato. A única
degradação existente (S3) é o limite documentado do produto, reproduzida de
propósito para mantê-lo honesto.

## 5. Veredito

A atualização **não regrediu nada** (redução e paridade reproduzidas, kernel na
mesma classe de latência) e **adicionou uma alavanca medida**: −89% de
reasoning tokens em mix realista, com decisão auditável por request. As duas
fases de custo do LLM agora têm número medido: entrada −82% (piloto, coerente
com −84% publicado) e raciocínio −89% (novo).
