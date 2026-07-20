# Estudo Técnico e de Viabilidade — "Propósito Contexto" (Evolução do Core BIOMA)

**Data:** 2026-07-20
**Escopo:** onde o custo de processamento de um LLM realmente está (entrada de contexto vs. pensamento profundo), e como o BIOMA deve evoluir para reduzir tokens nas duas fases.

---

## 1. Fundamentos: as duas fases de processamento de um LLM

Toda chamada a um LLM tem duas fases fisicamente distintas no hardware:

### 1.1 Prefill (entrada de contexto)

- Todos os N tokens de entrada são processados **em paralelo**, numa única passada.
- É **compute-bound**: o GPU atinge alta utilização de FLOPs (60–80% de MFU).
- Custo aproximado em FLOPs: `2 · P · N` (P = parâmetros do modelo) **+ atenção O(N²·d)** — o termo quadrático da atenção faz contextos muito longos (100k+) dominarem o custo computacional.
- É rápida em tempo de parede por token (paraleliza), mas cara em energia total quando N é grande.

### 1.2 Decode (geração / pensamento profundo)

- Gera **um token por vez**, autoregressivamente. Cada token exige reler todos os pesos do modelo + o KV-cache inteiro.
- É **memory-bandwidth-bound**: utilização de FLOPs tipicamente < 10% de MFU. O hardware fica ocioso esperando memória.
- Por token, o decode custa **10–100× mais tempo de parede e energia** que um token de prefill.
- "Pensamento profundo" (extended thinking / reasoning) é decode puro: milhares de tokens gerados sequencialmente antes da resposta final.

### 1.3 Resposta direta à pergunta do estudo

> *"O processamento do LLM é mais alto na entrada de contexto ou no pensamento profundo?"*

**Depende da métrica — e as duas respostas importam para o BIOMA:**

| Métrica | Quem domina | Por quê |
| :--- | :--- | :--- |
| **FLOPs totais por chamada** | Entrada (prefill), no caso típico de agente | Agentes reenviam 20k–100k tokens de histórico para gerar 1k–3k tokens. Volume de entrada ≫ saída, e a atenção cresce O(N²). |
| **Custo por token (energia, tempo, preço)** | Pensamento (decode) | Sequencial + memory-bound. Os provedores refletem isso no preço: output custa **4–5× o input** (ex.: Claude Sonnet $3/M input vs $15/M output; tokens de thinking são cobrados como output). |
| **Latência percebida** | Pensamento (decode) | Prefill de 50k tokens leva ~1–2 s; 5k tokens de thinking levam dezenas de segundos. |
| **Custo acumulado de uma sessão agêntica** | Entrada — e de forma **quadrática** | Ver §2. Este é o resultado central do estudo. |

---

## 2. O resultado central: em sessões agênticas, a entrada cresce quadraticamente

Modelo de custo de uma sessão com T turnos, contexto médio C_t no turno t, R_t tokens de raciocínio e O_t de resposta:

```
Custo_total = Σ_t [ c_in · C_t  +  c_out · (R_t + O_t) ]
```

- Sem poda, C_t cresce linearmente com t (cada turno acumula histórico + logs de ferramenta).
  → o termo de entrada soma uma **série quadrática em T**.
- R_t e O_t são aproximadamente constantes por turno → o termo de saída é **linear em T**.

**Conclusão:** mesmo com output custando 5× mais por token, em qualquer sessão longa o custo de **entrada ultrapassa e domina**. É exatamente o regime que o `bioma_micro` já ataca (−84% em agente naive, −95,8% em sessão longa de 16 rodadas — dados medidos do próprio framework). A tese do BIOMA está no lugar certo.

**Corolário:** reduzir thinking é a alavanca complementar — domina apenas em workloads de **sessão curta + tarefa difícil** (uma pergunta, muito raciocínio). Um core completo precisa das duas.

---

## 3. Restrição crítica descoberta: apoptose × prompt caching

O prompt caching dos provedores (cache read = **10× mais barato** que input normal; ~$0,30/M vs $3/M no Sonnet) funciona por **prefixo exato**. Qualquer alteração no início do histórico invalida o cache dali em diante.

**Risco real para o BIOMA hoje:** o `dehydrate()` reescreve o histórico a cada chamada. Contra um cliente que usa prompt caching, podar 30% do contexto pode **aumentar** o custo líquido — trocando 70k tokens cacheados ($0,021) por 49k tokens não-cacheados ($0,147), fora o cache-write ($3,75/M).

**Requisito da evolução (P0):** modo *cache-aware*:
1. Manter um **prefixo estável** (system + FACTs + histórico já consolidado) que nunca é reescrito entre chamadas.
2. Aplicar apoptose apenas no **sufixo móvel** (após o último cache breakpoint).
3. Consolidar podas em "gerações": reescrever o prefixo só quando a economia projetada superar o custo de re-cache (limiar calculável: poda vale a pena se `tokens_podados > ~0,9 · tokens_do_prefixo` no preço atual — senão, adiar).

Sem isso, o argumento de venda do BIOMA quebra contra qualquer stack moderna (Claude API, OpenAI, Bedrock — todos têm caching).

---

## 4. Viabilidade: reduzir tokens do "pensamento profundo"

Não é possível comprimir tokens que o modelo gera — mas é possível **controlar quantos ele gera** e **impedir que raciocínio antigo vire ballast de entrada**. Quatro mecanismos, em ordem de viabilidade:

### 4.1 Orçamento dinâmico de thinking (viável agora, alto impacto)

As APIs expõem controle direto: `budget_tokens` (Anthropic), `reasoning_effort` (OpenAI). O que falta nos frameworks é **decidir o orçamento por tarefa**. O BIOMA pode fazer isso com um classificador O(n) no espírito do `saturation_scan`:

- Sinais baratos (sem LLM): tamanho e entropia do pedido, presença de código/números, nº de restrições, se é continuação de tarefa já resolvida.
- Mapeamento: trivial → thinking off; médio → 1–2k; difícil → 8k+.
- Economia esperada: workloads reais têm maioria de turnos triviais ("continue", "sim", correções curtas) que hoje pagam thinking cheio. Redução plausível de 30–60% dos reasoning tokens sem perda de qualidade — verificável com as mesmas sondas objetivas usadas no benchmark do framework.

### 4.2 Contrato de Propósito (o "Propósito contexto" propriamente dito)

Injetar um bloco compacto e **estável** no topo do contexto:

```
PROPÓSITO: <objetivo da sessão em 1 frase>
RESTRIÇÕES: <3–5 invariantes>
ESTADO: <o que já foi decidido — substitui reler o histórico>
```

Efeito duplo, ambos mensuráveis:
- **Entrada:** o bloco ESTADO substitui turnos antigos (a apoptose pode ser mais agressiva porque a informação durável migrou para o contrato — é a generalização do flag `FACT` atual).
- **Pensamento:** objetivo cristalino reduz raciocínio errante (o modelo gasta menos tokens "redescobrindo" o que deve fazer). Hipótese testável: A/B com e sem contrato, mesmas tarefas, medir reasoning tokens e taxa de acerto.

Encaixe natural: é a evolução do `ContextApoptosis` stateful — o kernel passa a manter, além do histórico com pesos, um **sumário consolidado** que absorve o conteúdo dos itens apoptosados em vez de descartá-los às cegas.

### 4.3 Apoptose de blocos de thinking no loop agêntico

A API da Anthropic já descarta thinking de turnos anteriores automaticamente, mas frameworks que persistem o transcript completo (LangChain, logs de tool-calling caseiros) reenviam tudo. O kernel deve classificar blocos de thinking/scratchpad como classe `TOOL` (alvo primário) — custo de implementação ~zero, é só tagging.

### 4.4 Cascata de modelos (viável, mas fora do core)

Rotear para modelo pequeno primeiro e escalar só em baixa confiança. Alto ganho, mas é papel do orquestrador (`bioma_orchestrator`), não do micro-kernel — manter o core com "exatamente duas primitivas provadas" é a identidade do produto.

---

## 5. Veredito de viabilidade

| Frente | Viabilidade | Impacto | Prioridade |
| :--- | :--- | :--- | :--- |
| Modo cache-aware da apoptose | Alta (só Rust, sem API nova) | Evita regressão de custo real | **P0** |
| Orçamento dinâmico de thinking | Alta (classificador O(n) + params de API) | 30–60% dos reasoning tokens | **P1** |
| Contrato de Propósito + sumário consolidado | Média (muda o contrato do `ContextApoptosis`) | Poda mais agressiva sem perda + menos thinking errante | **P1** |
| Tagging de thinking antigo como `TOOL` | Trivial | Marginal, mas grátis | P2 |
| Cascata de modelos | Alta, mas no orquestrador | Grande, fora do escopo do core | P3 |

**Síntese:** a física do problema confirma a aposta atual do BIOMA — em sessões agênticas o custo é dominado pela **entrada**, que cresce quadraticamente com o número de turnos, enquanto o pensamento cresce linearmente. A evolução correta não é migrar o foco para o thinking, e sim (1) blindar a apoptose contra prompt caching, que hoje pode inverter o ganho, e (2) adicionar o controle de orçamento de raciocínio como segunda primitiva — barata, mensurável e complementar. O "Propósito contexto" (contrato + sumário consolidado) é a ponte entre as duas: melhora a poda de entrada e reduz o raciocínio ao mesmo tempo.

**Benchmark de aceitação sugerido:** repetir o protocolo existente (agente naive, 16 rodadas, sondas objetivas) em 3 condições — baseline, BIOMA atual, BIOMA + P0/P1 — medindo input tokens, reasoning tokens, custo em USD (com e sem prompt caching ativo) e taxa de acerto das sondas.
