# B.I.O.M.A. Gateway — as duas medições antes bloqueadas (agora reais)

> Ambas exigiam o gateway drop-in (que não existia). Dados brutos:
> `resultados/cache_interaction.json`, `resultados/e2e_agent.json`.
> A rodada 1 do teste de cache **encontrou um bug real** no gateway (bloco FACT
> com `cache_control` em conteúdo-lista não era reconhecido como durável e era
> purgado, zerando a resposta) — corrigido em `bioma/gateway.py` e coberto por 2
> testes de regressão em `tests/test_gateway.py`. Os números abaixo são pós-fix.

## Medição 1 — Apoptose × Prompt Caching (Anthropic Sonnet 5, cache real)

Método: 2 chamadas idênticas por braço (a 1ª cria o cache, a 2ª acerta);
`cache_control: ephemeral` no fim do prefixo durável; campos de cache do usage
real da API.

| 2ª chamada (cache quente) | Baseline A | BIOMA B |
| :--- | ---: | ---: |
| tokens de entrada não-cacheados | 4.717 | 971 |
| cache_read (com desconto de −90%) | 1.222 | 1.222 |
| custo faturado | $0.01051 | $0.00369 |

**Economia líquida do BIOMA APÓS o desconto de cache: −65%.**

Resposta à objeção nº 1 (o cache "devolve" a economia?): **não.** O prefixo
durável (system + FACT) acerta o **mesmo** cache de 1.222 tokens nos dois braços
— a garantia de prefixo byte-idêntico (só-deleção, preserva ordem) se confirma
na prática. A economia do BIOMA vem de purgar o **miolo variável** (logs/turnos
antigos), que muda a cada chamada e por isso **nunca foi cacheável em nenhum dos
braços**. Cache e apoptose são complementares, não concorrentes.

Nota de qualidade: a resposta do braço B citou os valores corretos da spec
(350, 60, 429, Retry-After, ZCARD) a partir do contexto desidratado — as duas
config-keys finais faltaram por **truncamento em max_tokens=150** (resposta mais
verbosa), não por perda de informação. O bloco FACT sobreviveu e cacheou.

## Medição 2 — E2E com agente real de tool-calling

Agente real (loop com ferramentas read_file/write_file/run_pytest) corrigindo um
bug de off-by-one num repositório real, até `pytest` verde. O MESMO agente rodou
direto vs pela `base_url` do gateway. O histórico local do agente é sempre
íntegro; só o que sobe ao modelo é desidratado.

| Cenário | Braço | Tokens entrada acum. | Turnos | Resolveu? |
| :--- | :--- | ---: | ---: | :---: |
| **Sessão limpa** (sem histórico) | A direto | 2.855 | 3 | ✅ |
| | B gateway | 2.860 | 3 | ✅ |
| **12 turnos de histórico acumulado** | A direto | 19.574 | 3 | ✅ |
| | B gateway | **3.169** | 3 | ✅ |

**Dois resultados, ambos honestos:**

1. **Sessão curta (3 turnos): −0%, paridade.** Sem peso morto acumulado, a
   apoptose é corretamente um **no-op** — não ajuda e não atrapalha. Importante
   dizer: o BIOMA não penaliza tarefas curtas.
2. **Agente com histórico acumulado (o caso real de agente longo): −84% de
   tokens de entrada, mesma solução, mesmos 3 turnos.** É onde a apoptose importa
   — e os pares `tool_call`/`tool` foram preservados como unidade (nenhum órfão),
   com a tarefa resolvida (pytest verde) idêntica ao braço direto.

O cruzamento é a mensagem: **o ganho do BIOMA escala com o comprimento da sessão**
— zero numa tarefa trivial, −84% num agente que carrega contexto acumulado.

## O que estas medições destravaram (e o que ainda falta)

- ✅ Apoptose×cache: **medido** (−65% líquido; cache e apoptose complementares).
- ✅ E2E de agente real de tool-calling: **medido** (−84% em sessão longa, paridade).
- ⏳ Claude Code E2E: ainda exige a superfície Anthropic `/v1/messages` (o agente
  aqui fala protocolo OpenAI) — próxima iteração declarada.
- 🐛 Bug encontrado e corrigido no processo (FACT/cache_control em lista) —
  exemplo de que a medição honesta é o que endurece o produto.
