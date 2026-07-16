# B.I.O.M.A. — E2E com o Claude Code REAL (o círculo que o benchmark original pedia)

> O Claude Code (CLI real, headless) apontado via `ANTHROPIC_BASE_URL` para o
> gateway BIOMA, corrigindo tarefas reais num repositório real. Dados brutos:
> `resultados/e2e_claude_code.json`, audit em `bioma_gateway_audit.jsonl`.

## ✅ Marco: a integração funciona de ponta a ponta

O caminho que ficou **bloqueado desde o primeiro pedido de benchmark** está aberto:

- **Smoke test** (`claude -p "PONG"` via gateway): resposta correta, sem erro.
- **Tarefa 1** (corrigir bug off-by-one): Claude Code real **RESOLVEU** (pytest verde, 8 turnos).
- **Tarefa 2** (corrigir bug + adicionar `quarter_window` + testes): **RESOLVEU**
  (pytest verde, 9 turnos, $1.08).

A superfície Anthropic `/v1/messages` + o modo ponte (`BIOMA_FORCE_KEY`, forwarding
de `x-api-key`, passthrough de `count_tokens`, carregamento de `.env`) fazem o
Claude Code rodar sobre o gateway **sem qualquer alteração no agente** — só a
`ANTHROPIC_BASE_URL`. O modelo real por trás foi servido via OpenRouter.

## O achado honesto: contra o Claude Code, a apoptose acha pouco para purgar (−0%)

Medição pelo audit (o `tokens_before` é exatamente o que uma chamada direta enviaria):

| Request ao modelo | tokens_before | tokens_after | purgados |
| ---: | ---: | ---: | ---: |
| 1 | 0 | 0 | 0 |
| 2–3 | 11.799 | 11.799 | 0 |
| 4–5 | 1.985 | 1.985 | 0 |
| 6–7 | 2.898 | 2.898 | 0 |
| 8 | 3.270 | 3.270 | 0 |

**Os payloads por request NÃO acumulam** (11.799 → 1.985 → 2.898 → 3.270, não
monotônico). Se o Claude Code mandasse um histórico crescente e inchado, veríamos
11K → 13K → 18K… Em vez disso, cada chamada carrega um histórico pequeno e recente.

**Interpretação:** o Claude Code **já gerencia o próprio contexto de forma
eficiente** — ele cura/compacta o histórico antes de enviar. A apoptose então,
corretamente, **não encontra peso morto** e é um no-op. O −0% não é falha; é o
comportamento certo diante de um agente que já é enxuto. E, crucialmente, **nunca
prejudica**: a tarefa foi resolvida em ambos os casos.

## Onde o BIOMA entrega valor (e onde não)

| Cliente | Comportamento de contexto | Ganho do BIOMA |
| :--- | :--- | :--- |
| Claude Code | **auto-gerencia** (compacta histórico) | ~0% — nada a purgar (medido aqui) |
| Agente tool-calling ingênuo (histórico acumulado) | envia o blob crescente | **−84%** (medido em `resultados/e2e_agent.json`) |
| Sessão longa genérica (16 rodadas) | reenvia tudo | **−95,8%** (medido em `test_enxuto_efficiency.py`) |

O BIOMA é uma **rede de segurança para agentes que NÃO gerenciam contexto** —
a maioria dos agentes custom/LangChain no mundo real. Contra um agente que já é
eficiente, ele é um no-op seguro (não ajuda, não atrapalha). Vender "−X% universal"
seria desonesto; a alegação correta é: **redução auditável onde há peso morto,
neutro onde não há, e nunca prejudicial**.

## Bug encontrado e corrigido no processo

A rodada 1 revelou que turnos com `tool_result` no formato Anthropic estavam
classificados como `ASSISTANT` (peso 1.0, "conversa valiosa") em vez de `TOOL`
(peso 0.25, "log descartável"). Corrigido em `bioma/gateway.py` (`_is_tool_unit`
detecta blocos `tool_use`/`tool_result`) com 2 testes de regressão. Ainda assim o
−0% persistiu — porque a causa real é o auto-gerenciamento do Claude Code, não a
classificação. Duas hipóteses testadas, uma descartada: rigor nos dois lados.

## Limite declarado (rodada 1)

Não obtivemos o comparativo head-to-head de custo (o braço "direto" bateu 401 —
quirk de auth do Claude Code → OpenRouter sem o gateway forçar a chave). A
medição de redução veio do audit do gateway, que é suficiente e mais direta.

---

## Rodada 2 (2026-07-16) — o círculo FECHOU: A/B completo, os dois braços resolveram

**Fix do 401:** o Claude Code headless não envia `ANTHROPIC_API_KEY` sem aprovação
prévia do keychain (o request sai SEM header de auth → 401 "Missing Authentication
header"). A correção é `ANTHROPIC_AUTH_TOKEN` (→ `Authorization: Bearer`,
incondicional), aplicada em `tests/e2e_claude_code.py`.

**Contexto do run:** saldo OpenRouter esgotado no meio da rodada paga (402 com
Sonnet 5 após $1,84) → A/B executado com `tencent/hy3:free` (262K ctx, tools).
Free tier = indicativo; repetir com Sonnet 5 após recarga.

| Métrica | A direto | B gateway |
| :--- | ---: | ---: |
| Bug resolvido (pytest verde) | ✅ | ✅ |
| Turnos | 5 | 13 |
| Custo estimado pelo cliente | $0.83 | $3.06 |

**Apoptose real em sessão longa (audit, 12 requests):** o histórico do braço B
cresce monotônico 11.663 → 75.866 tokens (est) e o payload dehidratado fica flat
~11,3–11,7K → purga acumulada **−74%** (497.248 → 127.302). Diferente da rodada 1
(4 requests, payloads pequenos, −0%): em sessões curtas o Claude Code é enxuto;
em sessões longas o histórico incha SIM, e a apoptose encontra peso morto.

**Prova de billing (payload idêntico, sintético, mesmo modelo):** direto →
provider cobrou **4.604** input tokens; via gateway → **32**. A redução chega ao
faturamento de verdade. (O `in_tok` que o Claude Code reporta é a contabilidade
LOCAL do cliente sobre o contexto que ele mantém — ele não sabe que o gateway
podou — por isso 528K ≈ soma dos "before".)

**Achado honesto novo — o default machuca agentes tool-calling:** com
`safe_threshold=0.35`, até o tool_result MAIS RECENTE é purgado
(peso 0,25 × 2^(−1/6) = 0,223 < 0,35). O agente fica cego ao resultado da própria
ferramenta, refaz trabalho (13 vs 5 turnos) e reenvia o system prompt gigante a
cada request extra → **para o Claude Code o efeito líquido pode ser negativo**.
Medido localmente: `safe_threshold=0.2` preserva o tool_result fresco mantendo
−91% de redução no sintético. Recomendação: `BIOMA_SAFE_THRESHOLD=0.2` para
clientes agênticos; 0,35 só para chat/sessões sem tool-calling denso.

## Rodada 3 (definitiva) — Sonnet 5 real, threshold 0.2

| Métrica | A direto | B gateway |
| :--- | ---: | ---: |
| Bug resolvido (pytest verde) | ✅ | ✅ |
| Turnos | 6 | 7 |
| Custo estimado pelo cliente | $1.11 | **$0.90 (−19%)** |

Audit (7 requests): reqs 1–4 sem purga (janela de trabalho preservada),
reqs 5–7 purgando 23% → 47% conforme os blocos envelhecem; total
**144.066 → 112.054 (−22%)**. O tuning 0.2 elimina o retrabalho observado na
rodada 2 e vira o sinal do custo. Gasto real (billing OpenRouter): ~$1,34.
Consolidado em `reports/BIOMA_BENCHMARK_COMPARATIVO.md`.
