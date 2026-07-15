# Frugal pelo Payload — B.I.O.M.A. como Camada Frugal-AI Client-Side

**🌐 [English](FRUGAL_AI_WHITEPAPER.md) · Português**

> Whitepaper alinhado ao referencial de IA frugal AFNOR SPEC 2314. Todo número
> medido abaixo tem script reproduzível e relatório versionado neste repositório;
> todo número estimado carrega coeficientes declarados e limites explícitos.

## Alegação oficial (escopo declarado)

O B.I.O.M.A. é uma **camada Frugal-AI client-side que reduz de forma auditável o
custo energético de inferência de LLM por deployment**. Não é uma alegação de
impacto global: o efeito escala com adoção e com o grid de quem opera. O KPI
oficial é **energia por token**; sua redução percentual é exata e independente
de coeficiente, porque deriva da própria auditoria de tokens do kernel por dispatch.

## 1. Problema

Inferência — não treinamento — domina a energia do ciclo de vida de modelos em
produção (~80–90% do compute), e cargas agênticas multiplicam os tokens por
tarefa em até três ordens de grandeza, principalmente **reenviando contexto a
cada passo**. O componente que mais cresce na conta energética da IA é, portanto,
payload de entrada redundante — peso morto que a camada de aplicação controla e
o provedor não consegue remover.

## 2. Método

**Apoptose de contexto** (micro-kernel Rust, 0,8–1,6 μs por dispatch, in-process):
cada bloco do histórico recebe um peso metabólico por classe; uma meia-vida por
recência o decai; blocos abaixo do threshold seguro são purgados antes do
despacho. Classes duráveis (`SYSTEM`, `FACT`) nunca são purgadas; a query atual
nunca entra no filtro. O mesmo passe alimenta o firewall cognitivo (redação de
segredos, detecção de flood, timeout guard). A camada é model-agnóstica:
endurece o payload, não o modelo.

**Contrato de uso** (verificado no §4): informação durável deve ser marcada
`FACT` ou estar em turnos recentes; turnos antigos não marcados são purgados
por design.

## 3. Metodologia de medição

- **Baseline = mesmo prompt, mesmo modelo, sem desidratar** — a única variável
  é o filtro de apoptose.
- **Qualidade por probes objetivas**: valores exatos plantados no histórico e
  verificados na resposta (sem juiz LLM), temperatura 0.
- **Tokens e custo do usage real do provedor** (OpenRouter), não de tabela de preços.
- **Energia medida em hardware**: modelo local (Ollama, Llama 3.2 1B), fuel
  gauge da bateria a 2 Hz, baseline de idle subtraída, braços intercalados.
- **Conversão para Wh/gCO2e é estimativa, separada das medições**, com
  coeficientes declarados da literatura e limites baixo/central/alto (`bioma/esg.py`).

## 4. Resultados medidos (ground truth)

| Camada | Sem B.I.O.M.A. | Com B.I.O.M.A. | Redução | Fonte |
|---|---|---|---|---|
| Tokens de entrada / dispatch (6 modelos online) | 1.605–2.489 | 63–280 | −84 a −96% | `reports/BIOMA_UNIVERSAL_GAINS.md` |
| Sessão de 16 rodadas, entrada acumulada | 47.890 | 2.022 | −95,8% | `tests/test_enxuto_efficiency.py` |
| Qualidade da resposta (probes, 5 modelos, S1+S2) | 100% | 100% | paridade 10/10 | `reports/BIOMA_QUALITY_PRESERVATION.md` |
| Compute de prefill (hardware local) | 411,1 s | 1,8 s | −99,6% | `reports/BIOMA_ENERGY_LOCAL.md` |
| **Energia marginal / dispatch (medida)** | **2.714,7 J** | **69,5 J** | **−97,4%** | `reports/BIOMA_ENERGY_LOCAL.md` |
| Segredos vazados ao provedor | 6/6 | 0/6 | contido | `reports/BIOMA_IMMUNITY_VERDICT.md` |

A redução de energia medida (−97,4%) acompanha a redução de tokens (−97,2%)
quase 1:1 — validando, por medição direta, a proporcionalidade tokens↔energia
que a camada de estimativa assume.

## 5. Camada de estimativa (coeficientes declarados)

`tests/test_esg_benchmark.py` → `reports/BIOMA_ESG_BENCHMARK.md` converte as
economias medidas usando 0,5–1,3 kWh/M tokens (central 0,9; consistente com
~0,3 Wh/query da Epoch AI), presets de grid (mundo 445, UE 230, EUA 385,
BR 100 gCO2e/kWh) e um contrafactual honesto ajustado por caching (cache hit
não é economia que reivindicamos). Deployment ilustrativo (100k dispatches/dia,
carga de sessão longa): **52–136 MWh/ano evitados (central 94)** ≈ 42 tCO2e no
grid mundial — caindo para ~31 MWh sob caching agressivo. Nosso ponto de
hardware próprio (0,10 kWh/Mtok, marginal, modelo de 1B) fica abaixo do
intervalo de fronteira, como esperado; delimita o caso de modelo pequeno e não
infla a alegação.

## 6. Alinhamento com a AFNOR SPEC 2314 (referencial de IA frugal)

| Princípio frugal | Prática no B.I.O.M.A. | Evidência |
|---|---|---|
| Eficiência de recurso com desempenho mantido | −80–97% tokens de entrada com 100% de paridade nas probes | §4 |
| Medir antes de alegar | auditoria por dispatch do kernel; bancada de energia em hardware | §3–4 |
| Metodologia de estimativa declarada | coeficientes com limites, contrafactual de caching | §5 |
| Transparência e comunicabilidade | relatórios versionados, CI, dados brutos (`reports/energy_local_runs.jsonl`) | repo |
| Acessibilidade / baixa barreira | client-side, model-agnóstico, sem lock-in, roda offline | §2 |

## 7. Limites declarados

Turnos antigos não marcados são purgados por design (o contrato: marque
informação durável como `FACT`). Um endpoint (Claude Fable 5 via OpenRouter)
foi excluído da suíte de qualidade (`content_filter` nos dois braços). O Grok
4.5 mostrou −84% de tokens com custo de API inalterado. A camada não toca
treinamento, geração de imagem/vídeo, tokens de saída, nem carbono embutido do
hardware. Eficiência pode induzir mais uso (Jevons); a auditoria por dispatch
existe justamente para o operador reportar os dois lados. Valores de energia de
CPU de notebook não transferem para GPUs de data center — a razão transfere.

## 8. Reprodutibilidade

Todos os scripts estão em `tests/`; todos os relatórios em `reports/`; os
testes unitários (incluindo a conversão ESG) rodam no CI a cada push. Commits
chave: suíte de qualidade `43927a0`, bancada de energia `7ac8d57`, KPI ESG
`9bfda63`.
