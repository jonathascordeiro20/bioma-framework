# B.I.O.M.A. — Achados Empíricos (avaliação ground-truth)

**🌐 [English](FINDINGS.md) · Português**

> Avaliação honesta e reproduzível de cada mecanismo do B.I.O.M.A. contra dados reais.
> Escrita para sobreviver a uma due diligence técnica: declara o que é **provado**, o que é
> **refutado**, e o que ainda é uma **meta de design**. Os números abaixo são medidos, não
> afirmados. Onde uma alegação não se sustentou, está marcada como tal.

## Resumo

- 🟢 **A apoptose de contexto (−78–80% de tokens de entrada) é o ganho real, universal e vendável.** Todo modelo, toda tarefa.
- 🟢 **O kernel em Rust é genuinamente rápido e resiliente**: ~2M sinais/s a ~5μs de latência média, latência **limitada sob 10× de carga**.
- 🔴 **A mitose+síntese multi-LLM NÃO melhora qualidade de resposta nem remediação de segurança.** Em testes executados de ground truth foi **neutra em modelos de fronteira (teto) e prejudicial nos mais fracos** (a síntese corrompe respostas certas). Até o **desenho best-case corrigido** (seleção cross-modelo verificada, baseline no pool) entregou **+0** em tarefas difíceis de segurança. Essa tese está **refutada** pelos nossos próprios dados em três experimentos independentes e **não** faz parte do pitch.
- ✅ **Posicionamento:** o B.I.O.M.A. torna o processamento de IA *viável, sustentável e resiliente* — uma **camada de eficiência/infraestrutura**, não um sistema que deixa a IA "mais inteligente".

---

## Ledger de evidências

| Alegação | Status | Base |
| :--- | :--- | :--- |
| Apoptose de contexto corta ~80% dos tokens de entrada | 🟢 **Provado** | Medido em toda rodada (`ContextPruner`, kernel) |
| Kernel sustenta 10k agentes concorrentes a latência de μs | 🟢 **Provado** | `bioma_kernel_loadtest.py` |
| Latência do kernel limitada sob 10× de carga | 🟢 **Provado** | média 4,5μs→5,0μs (1,1×), p99 21μs→15μs |
| Mitose+síntese melhora qualidade | 🔴 **Refutado** | Eval objetiva de código: 95%→83% (−17 testes) |
| Mitose melhora remediação de segurança | 🔴 **Refutado** | Eval de defesa: baseline 98% ≥ síntese 90% = seleção 90% |
| Seleção cross-modelo verificada melhora segurança (best-case corrigido) | 🔴 **Refutado** | +0 vs melhor single-shot; todos os modelos 100% nas tarefas difíceis (sem headroom) |
| "Seleção-por-execução é provadamente ≥ baseline" | 🟢 **Corrigido & validado** | Com o baseline **no pool** valeu exato (30/30 = 30/30, monotônico) — mas entregou +0 |
| Resiliente "em nível industrial" (sistema ponta-a-ponta) | 🟡 **Meta** | Primitiva do kernel provada; sistema completo não load-testado |

---

## Experimentos & resultados

Todas as chamadas de LLM passam pelo OpenRouter (`bioma_orchestrator/openrouter_async.py`)
com backoff exponencial. "Real" = uma chave `sk-or` válida; senão, um mock determinístico
claramente rotulado. Qualidade foi medida de duas formas: um juiz LLM ruidoso (rodadas
iniciais) e — decisivamente — **execução objetiva contra suítes de teste** (sem juiz).

### 1. Apoptose de contexto — 🟢 o ganho universal
O `ContextPruner` (oxigênio/decay do `StateContext` em Rust, fallback Python) poda um
contexto de agente inchado antes da chamada. Redução medida: **−78% a −80%** dos tokens de
entrada, consistente em GPT-4o, Fable-5, Opus 4.8, Grok-4.3, Llama-3.3-70B e em toda tarefa.
É o único mecanismo que ajuda incondicionalmente (custo + foco), inclusive nos frontier.

### 2. Resiliência do kernel — 🟢 provado (`bioma_kernel_loadtest.py`)
1k → 10k micro-agentes Tokio concorrentes floodando o barramento hormonal lock-free, com
apoptose ao vivo num core de telemetria pinado (host de 12 cores):

| Agentes concorrentes | Throughput | Latência média | Latência p99 |
| ---: | ---: | ---: | ---: |
| 1.000 | 2,31 M sig/s | 4,54 μs | 21 μs |
| 2.500 | 1,75 M sig/s | 6,04 μs | 20 μs |
| 5.000 | 1,84 M sig/s | 5,76 μs | 27 μs |
| 10.000 | 2,12 M sig/s | 4,99 μs | 15 μs |

Sob **10× de carga**, a latência média moveu só 4,5→5,0μs (1,1×) e o p99 *melhorou*.
**Alegação defensável:** *"o kernel soberano sustenta 10.000 agentes concorrentes a ~2M
sinais/s com latência de ~5μs limitada."* Ressalva: `max` mostra picos de 10–37ms = scheduler
do SO (não-realtime); média/p99 são as métricas limitadas que valem. Escopo = a primitiva do
kernel, não um sistema LLM ponta-a-ponta.

### 3. Correção objetiva de código — 🔴 mitose refutada (`bioma_objective_eval.py`)
5 tarefas algorítmicas cheias de edge cases, **144 testes ocultos**, código executado em
subprocess isolado (sem juiz). Baseline (1 chamada) vs mitose forçada:

| Modelo | Baseline | Mitose B.I.O.M.A. | Δ |
| :--- | :---: | :---: | :---: |
| GPT-4o | 48/48 (100%) | 48/48 (100%) | 0 (teto) |
| Grok-4.3 | 48/48 (100%) | 48/48 (100%) | 0 (teto) |
| Llama-3.3-70B | 41/48 (85%) | 24/48 (50%) | **−17** |
| **Agregado** | **137/144 (95%)** | **120/144 (83%)** | **−17** |

**Tiro cirúrgico:** o `is_valid_number` do Llama foi **17/17 → 0/17** — o modelo acertou
sozinho, e a **síntese de 3 hipóteses corrompeu a resposta certa.** É o mecanismo do dano: a
síntese cega não tem verdade de referência e pode fundir uma hipótese errada por cima da certa.

### 4. Eficiência multi-modelo (juiz LLM) — mitose neutra-a-negativa (`bioma_efficiency_simulation.py`)
Tarefa algorítmica neutra, 5 modelos, juiz = gpt-4o-mini (ruidoso ±5):

| Modelo | Qualidade Base→BIOMA | Custo | Latência |
| :--- | :---: | :---: | :---: |
| GPT-4o | 90→85 | $0.006→$0.024 | 7→10s |
| Fable-5 | 95→100 | $0.045→$0.302 | 12→45s |
| Opus 4.8 | 95→95 | $0.031→$0.152 | 19→44s |
| Grok-4.3 | 95→95 | $0.003→$0.010 | 9→17s |
| Llama-3.3-70B | 95→90 | $0.0003→$0.001 | 15→114s |

Agregado: **−1,0 pt de qualidade, 5,7× de custo.** A maioria dos deltas está dentro do ruído
do juiz. Em tarefas que os frontier já resolvem, não há headroom pra mitose ajudar.

### 5. Remediação de segurança — 🔴 mitose sem ganho (`bioma_defense_eval.py`)
3 vulnerabilidades (eval inseguro, SQL injection, command injection), **17 checks executados**,
benignos por construção. Baseline vs síntese vs **seleção-por-execução**:

| Modelo | Baseline | Síntese | Seleção |
| :--- | :---: | :---: | :---: |
| GPT-4o | 17/17 | 17/17 | 17/17 |
| Grok-4.3 | 17/17 | 17/17 | 17/17 |
| Llama-3.3-70B | 16/17 (94%) | 12/17 | 12/17 |
| **Agregado** | **98%** | **90%** | **90%** |

Frontier: teto (todos empatam). Modelo fraco: **os dois braços de mitose ficaram abaixo do
baseline.** Os candidatos do `build_query` do Llama pontuaram **[0,0,0]** — os prompts de
papel foram piores que o prompt simples, e o baseline **não** estava no pool.

### 6. Mitose adaptativa — economia funciona, sinal de confiança é fraco (`live_pipeline.py`)
Uma célula scout sonda a dificuldade; só baixa autoconfiança escala pra mitose completa.
- ✅ Tarefa fácil → **1 chamada em vez de 4** (corte de custo real).
- ⚠️ Tarefa difícil → GPT-4o se auto-avaliou **95** numa prova de concorrência lock-free → não
  escalou. **A autoconfiança do LLM é superestimada**, então é um gatilho fraco. Um gate
  robusto precisa de sinal de consistência/crítico, não auto-relato.

### 7. Mitose corrigida: seleção cross-modelo verificada — 🔴 ainda +0 (`bioma_verified_selection_eval.py`)
O desenho best-case que a análise apontou: **baseline no pool** + diversidade **cross-modelo**
(GPT-4o + Grok-4.3 + Llama-3.3-70B) + **verificação objetiva** (rodar os checks) como seletor —
nunca síntese-LLM. Testado em 3 tarefas de segurança mais difíceis (30 checks):

| Referência | Score |
| :--- | :---: |
| GPT-4o single-shot | 30/30 (100%) |
| Grok-4.3 single-shot | 30/30 (100%) |
| Llama-3.3-70B single-shot | 30/30 (100%) |
| Melhor modelo único | 30/30 (100%) |
| **Seleção cross-modelo verificada** | **30/30 (100%)** |

**Δ = +0.** Duas coisas verdadeiras e ambas importam: (1) o desenho corrigido *funcionou como
projetado* — a seleção ficou exata no baseline (monotônica, **nunca pior**); (2) entregou
**zero ganho**, porque todos os modelos bateram no **teto** mesmo nas tarefas difíceis. Três
experimentos independentes (§3, §5, §7) convergem no mesmo veredito: em tarefas verificáveis, o
single-shot moderno já está no teto — a mitose, mesmo no best-case, não tem onde agregar, a 6×
o custo.

---

## Correções honestas às nossas próprias alegações

1. **"Mitose/orquestração melhora qualidade."** Refutado por ground truth.
2. **"Seleção-por-execução é provadamente ≥ baseline."** Exagerado. É ≥ o melhor *candidato*;
   para ser ≥ baseline, o baseline precisa estar no pool. E mesmo assim, empata (sem headroom).
3. **"Resiliente em nível industrial / pronto para os problemas mais difíceis do planeta."** A
   primitiva do kernel é resiliente; o sistema ponta-a-ponta não foi load-testado, e a
   simulação de segurança é inerte. Declare como meta, não resultado.

---

## Recomendação de produto

1. **Shipar:** apoptose de contexto (sempre ligada) + o kernel μs em Rust. Provado, auditável.
2. **Mitose:** OFF por padrão. Se oferecida, só como escalonamento opcional com o desenho de
   **seleção baseline-no-pool** (garante "nunca pior") — e **sem** alegação de qualidade.
3. **Posicionar** em eficiência/infraestrutura e resiliência, não inteligência — o único
   enquadramento que a evidência sustenta.

## Reprodutibilidade

| Script | O que mede | Custo |
| :--- | :--- | :--- |
| `bioma_kernel_loadtest.py` | throughput/latência do kernel sob 1k–10k agentes | grátis |
| `bioma_objective_eval.py` | correção de código, testes executados | ~$0.4 |
| `bioma_defense_eval.py` | remediação de segurança, checks executados | ~$0.3 |
| `bioma_efficiency_simulation.py` | eficiência por modelo (juiz) | ~$0.7 |
| `tests/test_universal_integration.py` | ganhos universais em 6 modelos frontier | ~$0.4 |

Todos os scripts rodam offline em modo **mock** rotulado, sem chave. O modo real precisa de uma
`OPENROUTER_API_KEY` válida (no `.env`, git-ignored — nunca commite uma chave).
