# B.I.O.M.A. — Benchmark Comparativo Auditável (2026-07-16)

> Um único documento, duas comparações, todas as ressalvas na mesa.
> Reprodução: `tests/e2e_claude_code.py` e `tests/benchmark_llmlingua_h2h.py`.
> Dados brutos: `resultados/e2e_claude_code.json`, `resultados/llmlingua_h2h.json`,
> `bioma_gateway_audit.jsonl`.

## TL;DR honesto

1. **vs Claude Code (A/B real e2e, Sonnet 5, threshold 0.2):** os dois braços
   resolvem a tarefa em turnos comparáveis (6 vs 7); a apoptose purga **−22%**
   do histórico respeitando a janela de trabalho, e o custo estimado pelo cliente
   sai **−19%** para o gateway. A redução chega ao billing do provider (prova:
   payload idêntico custou 4.604 tokens direto vs 32 via gateway). O tuning
   importa: com o default 0.35 a purga cega o agente aos próprios tool_results
   e o efeito líquido vira NEGATIVO (13 vs 5 turnos) — medido e documentado.
2. **vs LLMLingua-2 (mesmo dataset, mesmo budget, mesmas métricas):** no orçamento
   extremo em que a apoptose opera (−97,6%), o BIOMA mantém 100% de acurácia e o
   LLMLingua-2 colapsa para 0% — decidindo em 0,04 ms contra ~26 s de CPU.
   Reproduzido 3× (2 rodadas free + 1 paga com GPT-5.5 e Sonnet 5, 0/18 células
   com erro). Em compensação, o LLMLingua não exige rótulos de classe e funciona
   em texto arbitrário em taxas moderadas (2–5×), onde é o estado da arte.

---

## Parte 1 — A/B auditável contra o Claude Code REAL

**Setup:** Claude Code CLI headless, mesma tarefa (bug off-by-one num repo real,
critério = pytest verde), mesmo modelo, só a `ANTHROPIC_BASE_URL` muda:
braço A direto no OpenRouter, braço B via gateway BIOMA (apoptose ON).

**Desbloqueio histórico:** o 401 que travava o braço direto desde o primeiro
benchmark era o Claude Code headless silenciosamente não enviando
`ANTHROPIC_API_KEY` (exige aprovação de keychain). Fix: `ANTHROPIC_AUTH_TOKEN`
→ `Authorization: Bearer`.

### Rodada definitiva — Sonnet 5 real, `BIOMA_SAFE_THRESHOLD=0.2`

| Métrica | A direto | B gateway (BIOMA) |
| :--- | ---: | ---: |
| Bug resolvido (pytest verde) | ✅ | ✅ |
| Turnos | 6 | 7 |
| Custo estimado pelo cliente | $1.11 | **$0.90 (−19%)** |
| Modelo | `anthropic/claude-sonnet-5` | `anthropic/claude-sonnet-5` |

Curva do audit (7 requests): reqs 1–4 → **0% purgado** (janela de trabalho jovem,
tool_results frescos preservados); reqs 5–7 → 23% → 31% → 47% conforme os blocos
envelhecem. Total: **144.066 → 112.054 tokens (−22%)**, tarefa resolvida, sem
retrabalho do agente. Gasto real da rodada (billing OpenRouter): ~$1,34 nos dois
braços.

### Rodada com o tuning default (0.35) — a lição de tuning, medida

| Métrica | A direto | B gateway (BIOMA) |
| :--- | ---: | ---: |
| Bug resolvido (pytest verde) | ✅ | ✅ |
| Turnos | 5 | **13** |
| Modelo | `tencent/hy3:free` | `tencent/hy3:free` |

Purga acumulada −74% (497.248 → 127.302; histórico crescendo 11,7K → 75,9K com
payload flat ~11,5K) — mas com 0.35 até o tool_result mais recente é purgado
(0,25 × 2^(−1/6) = 0,223 < 0,35), o agente refaz trabalho e o efeito líquido
fica negativo. É exatamente por isso que a recomendação agêntica é 0.2.

**Prova de billing (o teste que fecha a questão):** o mesmo payload sintético
(12 rounds de tool_result no formato Anthropic + pergunta final), mesmo modelo:

| Rota | input_tokens cobrados pelo provider |
| :--- | ---: |
| Direto | 4.604 |
| Via gateway | **32** |

**As ressalvas que um vendedor esconderia:**

1. **O tuning define o sinal do resultado.** Com 0.35 o efeito líquido é negativo
   (13 vs 15 turnos, retrabalho); com 0.2, positivo (−22% histórico, −19% custo
   estimado, turnos comparáveis). O default do gateway deveria ser 0.2 para
   clientes agênticos.
2. **N=1 tarefa por rodada.** Uma tarefa de bug-fix por braço; o delta de custo
   (−19%) carrega variância de agente (6 vs 7 turnos). A direção é consistente
   com o audit determinístico, mas a barra de erro é real — mais tarefas dariam
   um intervalo.
3. **O custo "$" do Claude Code é contabilidade do cliente** (ele não sabe que o
   gateway podou — na rodada 0.35 reportou 528K ≈ soma pré-apoptose). A métrica
   limpa é o audit do gateway + o billing do provider, ambos registrados.

**Onde o BIOMA entrega (consistente com todas as rodadas):** Claude Code em
sessão curta → −0% (no-op seguro); Claude Code em sessão longa → −22% líquido
com tuning certo (−74% bruto com tuning errado e efeito colateral); agente
tool-calling ingênuo → −84%; sessão longa genérica → −95,8% com paridade de
qualidade.

---

## Parte 2 — Head-to-head vs LLMLingua-2

**Setup (apples-to-apples de verdade):** mesmo dataset (cenários S1/S2/S3 de
`test_quality_preservation.py`, probes objetivas plantadas — sem juiz LLM),
mesmo template de prompt, temperatura 0.0, e **orçamento de compressão pareado**:
o `target_token` do LLMLingua-2 = tokens pós-apoptose do BIOMA. Compressão roda
uma vez por cenário (ambos determinísticos); dispatch nos mesmos modelos.
LLMLingua-2: `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank`
(o modelo oficial small), CPU. Reproduzido em **3 rodadas independentes**
(2 com modelos free, 1 paga com GPT-5.5 + Claude Sonnet 5) com o mesmo veredito;
a rodada paga fechou **0/18 células com erro**.

| Métrica (S1+S2, rodada paga) | baseline | BIOMA | LLMLingua-2 |
| :--- | ---: | ---: | ---: |
| Acurácia de probes | 100% | **100%** | **0%** |
| Tokens de entrada (provider) | 9.320 | 222 | 70 |
| Redução vs baseline | — | −97,6% | −99,3% |
| Latência de compressão | — | **0,04 ms** (kernel ~1 µs) | **~25.800 ms** (CPU) |

S3 (fato antigo não taggeado — limite declarado do BIOMA): baseline 100% ·
BIOMA 0% (purga by design) · LLMLingua-2 0%. Nenhum dos dois preserva o fato
antigo no budget extremo; o contrato do BIOMA é explícito: informação durável
deve ser marcada `FACT`.

**Por que o LLMLingua-2 colapsa aqui (leitura honesta, não triunfalista):**
ele foi projetado para taxas de 2–5× em texto genérico, sem metadados. No budget
extremo (~50×) que a apoptose atinge, o filtro token-a-token não tem como saber
que "INC-7743" importa mais que o log de auditoria — ele mantém fragmentos
diluídos de tudo. O BIOMA usa a estrutura que o cliente JÁ tem (classes
SYSTEM/FACT/TOOL + recência) e por isso escolhe os 184 tokens certos. É uma
vantagem de informação, não de algoritmo — e é exatamente a tese do produto:
**poda estrutural µs-grátis onde há estrutura; compressão neural onde não há.**

**Ressalvas:** (a) nas rodadas free, só `hy3:free` foi estável (9/9 células, 2×);
gemma/qwen-next falharam células (marcadas, não descartadas em silêncio) — a
rodada paga eliminou o problema (0/18 erros); (b) LLMLingua em GPU cairia para
~0,5–2 s — ainda 4–6 ordens de magnitude acima do kernel; (c) em taxas moderadas
(2–5×) o LLMLingua preservaria mais — esse regime não foi medido aqui porque não
é o ponto de operação do BIOMA.

---

## Reprodução

```bash
# A/B Claude Code (precisa do gateway em modo ponte + OPENROUTER_API_KEY)
BIOMA_FORCE_KEY=1 BIOMA_SAFE_THRESHOLD=0.2 python -m uvicorn bioma.gateway:app --port 8790 &
python tests/e2e_claude_code.py --max-turns 15 --model anthropic/claude-sonnet-5

# Head-to-head LLMLingua (baixa ~700MB do HF na primeira vez)
python tests/benchmark_llmlingua_h2h.py --models openai/gpt-5.5 anthropic/claude-sonnet-5 --report
```

Custo real total da bateria definitiva (billing OpenRouter): **$1,55**
(A/B Sonnet 5 nos dois braços ~$1,34 + H2H pago $0,21); rodadas exploratórias
em modelos free: $0. Kernel: `bioma_micro 1.0.0` (wheel abi3, pronto para
PyPI — ver `bioma_micro/PUBLISH.md`).
