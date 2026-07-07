# B.I.O.M.A. — Plano de Arquitetura e Engenharia
### *Biologically Inspired Orchestration of Mutating Agents*
**Documento de Arquitetura-Chefe · Plano Final Consolidado · Português do Brasil**
**Versão 1.0 · Alvo de referência: Windows 11 / Python 3.12 / PyTorch CPU-only**

---

## 1. Sumário Executivo

### 1.1 O que é o B.I.O.M.A.

O B.I.O.M.A. (*Biologically Inspired Orchestration of Mutating Agents*) é um framework de orquestração dinâmica de agentes neurais construído sobre PyTorch, no qual mini-agentes (módulos `nn.Module`) são organizados num grafo acíclico dirigido (DAG) computacional que se **expande** e **contrai** em tempo de execução. O sistema modela, sob vocabulário biológico, quatro capacidades de engenharia bem definidas: (i) **mitose** — expansão dinâmica de rede preservando função, combinada com roteamento condicional; (ii) **homeostase/energia** — contabilidade de orçamento computacional com regularização por incerteza; (iii) **apoptose** — poda estrutural com consolidação de conhecimento e liberação determinística de memória; e (iv) **barramento hormonal** — comunicação inter-agente por estado latente compartilhado (blackboard tensorial) com leitura por atenção.

O ponto de partida **não é um projeto do zero**. Existe um esqueleto funcional em `C:/Users/jonat/A.N.I.M.A/workspace/bioma_engine/` contendo os quatro módulos-alvo — `organism_core.py`, `mitosis_engine.py`, `hormonal_bus.py` — mais `config.py`, `telemetry.py`, `server.py`, `run_local.py` e um `smoke_client`. Este plano é, portanto, um roteiro de **estabilização e endurecimento** (*brownfield*) de código existente, seguido da adição das capacidades ausentes descritas nos pilares. Ele corrige defeitos já verificados no código-fonte e depois eleva o sistema a um artefato cientificamente defensável.

### 1.2 O que o plano entrega

O plano entrega, ao longo de dez fases (Fase 0 a Fase 9), mais uma **trilha de extensão opcional (Fase 10 — Coder Evolutivo)**, um sistema no qual: os quatro módulos existentes são auditados e corrigidos; o ciclo de vida completo (nascimento → trabalho → morte → fusão) opera sem vazamento de memória e sem corrupção de gradiente; um harness de simulação com *ground-truth* analítico julga a convergência objetivamente sem depender de um LLM-juiz; a telemetria estruturada e a definição operacional de sobrevivência computacional existem e são confiáveis **antes** de qualquer conclusão experimental; e uma metodologia fatorial 2×2 com validação estatística prova (ou refuta) causalmente que os mecanismos biológicos agregam valor.

### 1.3 Postura honesta sobre metáfora versus mecanismo

Este documento adota uma **tese de honestidade epistêmica inegociável**. Toda entidade do sistema carrega simultaneamente um nome biológico e um nome de engenharia, e cada componente declara seu **nível de honestidade** em três categorias: **(N1) mecanismo concreto verificável**, **(N2) analogia funcional defensável** e **(N3) licença criativa/narrativa**. O framework não faz afirmações não-qualificadas de "vida", "consciência", "emergência autônoma" ou "termodinâmica real".

Em resposta direta às críticas recebidas, o plano corrige aqui os *overclaims* residuais mais graves e declara-os explicitamente onde a metáfora não corresponde ao mecanismo:

- **A "energia" não se conserva no sentido físico.** O modelo de energia possui fontes (regeneração por progresso), sumidouros (decaimento basal) e *clamp* em faixa fixa; qualquer um destes viola conservação. O que antes se chamava "conservação energética" passa a ser chamado, honestamente, de **auditoria de contabilidade**: verifica-se ausência de dupla-contagem e ausência de *drift* de ponto flutuante, não uma lei de conservação. Energia é um **orçamento com saldo**, análogo a uma conta bancária, não um sistema fechado.
- **A "mitose" não é preservadora de função no sentido de Net2Net.** O mecanismo real — roteamento por *clusters* + especialização — pertence à família Mixture-of-Experts (MoE), não a Net2Net. A propriedade verificada no instante da divisão (comportamento idêntico ao do pai antes de qualquer adaptação) é uma **verificação de sanidade do *deep-copy***, não a garantia algébrica de identidade que Net2Net oferece sob expansão de largura. A citação à literatura é corrigida para refletir isto.
- **A comunicação hormonal não é "em tempo real" nem "sem overhead".** É um blackboard latente *in-process* que elimina o custo de **serialização de texto/JSON** entre agentes, ao preço de sincronização por *lock* e latência de *tick*. A semântica é de **consistência eventual**: uma leitura enxerga o estado do último *tick* consolidado, não o instante de escrita de um par.
- **A "entropia" que drena energia é uma medida de incerteza (Shannon), não entropia termodinâmica.** O termo de drenagem é um **regularizador escolhido**, cuja direção (penalizar incerteza) é uma decisão de design a ser justificada empiricamente por ablação, não uma lei derivada.
- **O modelo de concorrência é predominantemente cooperativo *single-thread*.** A coordenação do barramento roda no *event loop*; o único paralelismo real é o cômputo por-célula no *executor* sobre tensores disjuntos. Vários mecanismos de defesa contra corridas de *threads* são, portanto, dimensionados com honestidade a esse modelo real (ver Seção 7).

Estas correções não enfraquecem o projeto; elevam-no de "demonstração com verniz biológico" a um estudo defensável de orquestração dinâmica de agentes.

---

## 2. Enquadramento Científico e Estado da Arte

### 2.1 Posicionamento na literatura

O B.I.O.M.A. situa-se na interseção de várias famílias técnicas estabelecidas, das quais herda mecanismos concretos e às quais deve atribuir crédito explícito, sem reivindicar invenção dos mecanismos-base. Sua contribuição real é a **integração orquestrada** dessas famílias sob um framework *in-process* unificado, não a criação de qualquer um dos componentes.

O sistema herda de **redes dinâmicas e crescentes** (transformações preservadoras de função no estilo Net2Net; redes progressivas; redes dinamicamente expansíveis) a ideia de alterar a topologia de uma rede em execução. Herda de **computação condicional e Mixture-of-Experts** (roteamento esparso *top-k*, *Switch Transformer*, balanceamento de carga por perda auxiliar) o mecanismo de ativar sub-redes especializadas por decisão de um roteador. Herda de **Neural Architecture Search** a noção de crescimento orientado por decisão. Herda de **hypernetworks** a geração/edição de parâmetros. Herda de **arquiteturas blackboard e estigmergia digital** o modelo de comunicação por estado compartilhado. E herda de **memória externa diferenciável e atenção sobre *key-value store*** a leitura ponderada do meio latente.

Onde o B.I.O.M.A. **diverge** e o admite honestamente: o crescimento é dirigido por **decisão de um roteador central** (paradigma MoE/NAS), e **não** por auto-organização emergente de regra local homogênea (paradigma dos Neural Cellular Automata). Os NCA são a referência de ALife mais honesta para "crescimento", mas são um paradigma **distinto**; o plano cita-os como **contraste**, não como equivalente, e reserva os termos "morfogênese" e "emergência" para trabalho futuro explicitamente rotulado como especulativo.

### 2.2 Dicionário canônico Metáfora → Mecanismo

A tabela a seguir é a fonte de verdade de nomenclatura para todo o código, logs e telemetria. Cada termo declara seu mecanismo de engenharia, a família técnica correspondente e seu nível de honestidade (N1 concreto / N2 analogia / N3 licença).

| Termo biológico | Mecanismo de engenharia | Família técnica | Nível |
|---|---|---|---|
| **Mitose** | Instanciação de *k* filhos por *clustering* de embeddings + *deep-copy* de `state_dict` + roteamento condicional | MoE / redes crescentes | **N1** |
| **Stem cell** | Roteador/*gating* que mede dispersão/entropia de *clusters* de embedding e decide expandir | MoE *top-k gating* / NAS online | **N1** |
| **Divergência Semântica** | Escalar estatístico sobre a geometria de embeddings | Teoria da informação / *clustering* | **N1** |
| **Homeostase** | Regulação de variável interna em faixa viável por *clamp* e realimentação | Controle proporcional / *resource accounting* | **N2** |
| **Energia** | Contador escalar de orçamento (proxy de FLOPs/tokens) + penalidade de incerteza | Computação condicional / *ponder cost* | **N2** |
| **Entropia (drenagem)** | Regularizador por incerteza de Shannon da saída | Regularização por entropia (RL, *early-exit*) | **N2** |
| **Apoptose** | Poda estrutural + consolidação (*merge*/destilação) + liberação de memória | *Pruning* + *knowledge distillation* + GC | **N1** |
| **Hormônio / exsudação** | Escrita/leitura EMA em tensor compartilhado; leitura por atenção de cosseno | Blackboard / estigmergia / atenção sobre KV | **N1** |
| **Organismo** | DAG dinâmico de `nn.Module` editável em runtime | Grafo dinâmico *define-by-run* | **N1** |
| **Simbiose** | Orquestração hierárquica com agregação em espaço latente | Sistemas multiagente / *ensembling* | **N2** |
| **Fissão/mutação de código** | Geração de variantes por *transforms* AST determinísticos (catálogo) e/ou propostas de LLM em quarentena | Programação genética / síntese de programas | **N1 (AST) / N3 ("evolução descobre")** |
| **Fitness** | Escalar multiobjetivo lexicográfico: correção (portão) → latência → memória | Otimização multiobjetivo / GP | **N1** |
| **Destilação reversa (Coder→Stem Cell)** | Promoção do *transform* vencedor ao catálogo reutilizável + ajuste de *prior* de preferência | *Pattern mining* / atualização de biblioteca | **N2 (não é "aprender código limpo")** |
| **"Vida" / "consciência"** | — (sem referente mecânico) | — | **N3 — proibido sem qualificação** |

### 2.3 Glossário de Fronteiras Epistêmicas (o que o B.I.O.M.A. NÃO é)

O B.I.O.M.A. **não é** termodinâmica: sua "energia" é um contador de recursos calibrável, não uma grandeza física, e não obedece conservação. **Não é** emergência morfogenética: seu crescimento é decisão programada de roteador por limiar, não auto-organização de regra local. **Não é** vida artificial no sentido forte: os rótulos celulares são andaimes narrativos sobre operações tensoriais determinísticas. E **não inventa** os mecanismos-base: mitose é Net2Net/MoE, apoptose é *pruning*+destilação, hormônio é blackboard/estigmergia — todos anteriores a este projeto.

---

## 3. Ciclo de Vida do Tensor Biológico

O fluxo canônico de uma unidade viva atravessa quatro estados, permeado continuamente pelo barramento hormonal e pela telemetria. A descrição a seguir é textual e conceitual; os contratos formais de cada operação estão na Seção 4.

Uma requisição chega ao sistema como um cenário multi-domínio. A **Stem Cell** (célula-raiz, um `NeuralOrganism`) recebe o estímulo, projeta-o em embeddings no espaço latente compartilhado e mede a **Divergência Semântica** — um escalar que quantifica quão heterogêneo é o cenário. Enquanto essa análise ocorre de forma assíncrona e sem *lock*, a telemetria já emite eventos de nascimento e a célula começa a **secretar** vetores no barramento hormonal, marcando sua presença no meio latente.

Quando a divergência ultrapassa o limiar superior de histerese e há orçamento energético disponível, dispara-se a **Mitose**. O motor de fissão decide o número *k* de filhos por *clustering* estável dos embeddings, faz *deep-copy* do `state_dict` do pai (via CPU-pivô), injeta em cada filho um viés de especialização em direção ao centroide do seu *cluster*, e insere os filhos como folhas no DAG. A mutação estrutural ocorre numa **seção crítica síncrona e atômica**, jamais concorrente com um *backward*, garantindo que o grafo de autograd permaneça válido. Cada filho nasce **destacado** (`detach`) do grafo do pai, com grafo de autograd disjunto.

Cada **Leaf Agent** (agente-folha) então executa seu trabalho: lê o contexto hormonal por **atenção de cosseno** sobre o barramento, processa seu sub-domínio, **secreta** de volta seu estado atual, e adapta seus parâmetros. Durante todo o trabalho, o barramento **dissipa** temporalmente os sinais antigos a cada *tick* (com meia-vida separada da fusão de escrita), envelhecendo os slots inativos e permitindo que a atenção descarte sinais obsoletos. A cada passo, a **contabilidade de energia** debita o custo de trabalho (proxy de FLOPs) e a penalidade de incerteza, e regenera saldo **apenas quando há progresso mensurável** (queda de perda no sub-domínio) — nunca por mera atividade. A telemetria registra a taxa de queima por agente.

Quando um agente satisfaz um dos quatro gatilhos — tarefa resolvida, energia esgotada, contribuição marginal baixa, ou senescência — entra em **Apoptose**. A máquina de estados transita `ALIVE → DYING → TRANSFERRING → DEAD`. Antes de qualquer liberação, o agente **transfere sua representação** ao pai por *merge* ponderado (LERP/SLERP) ou destilação de embeddings, com *snapshot* pré-*merge* do pai para *rollback* caso a perda global suba. Só então executa-se a **ordem canônica de limpeza**: soltar referências → *detach* → mover para CPU → `gc.collect()` → `empty_cache()` condicional a CUDA. O verificador anti-vazamento confirma o retorno da memória e a contagem zero de tensores vivos do agente morto.

Finalmente, o **escalonador topológico** garante que o pai só execute sua fase de redução (absorção/síntese) depois que todos os seus filhos apoptosaram e transferiram. A raiz produz a síntese final, cuja convergência é medida pelo harness contra o *ground-truth* analítico. O barramento permeia todo o fluxo como meio de coordenação; a telemetria permeia-o como camada de observabilidade que alimenta o *loop* de auto-correção.

---

## 4. Arquitetura em Camadas e os Quatro Módulos

A arquitetura organiza-se em oito camadas lógicas (Camada 0 a Camada 7) que envolvem os quatro módulos-alvo. Esta seção descreve responsabilidades e contratos; nenhuma linha de código é incluída.

### 4.1 Camadas lógicas

**Camada 0 — Configuração e Contratos Globais.** Fonte única de verdade para constantes, política de dispositivo, propagação de *seed* e o dicionário canônico Metáfora↔Mecanismo. Define os contratos de interface — *shapes* de tensor, dimensão latente `d` compartilhada, esquema de telemetria, e o **contrato do encoder Φ** (dimensão, normalização L2, quem o instancia). Em resposta às críticas, a definição de Φ é **promovida da Fase 2 para a Fase 0**, para que Núcleo e Barramento possam ser desenvolvidos em paralelo consumindo um contrato congelado. Separa as três escalas de tempo hoje colapsadas na constante única `hormone_decay`.

**Camada 1 — Núcleo do Organismo.** O módulo `organism_core.py`, unidade viva passiva.

**Camada 2 — Barramento Hormonal.** O módulo `hormonal_bus.py`, meio latente concorrente-seguro.

**Camada 3 — Motor de Mitose.** O módulo `mitosis_engine.py`, controlador de fissão.

**Camada 4 — Homeostase, Energia e Apoptose.** Contabilidade de recursos e ciclo de vida celular, integrada ao núcleo e ao motor.

**Camada 5 — Orquestração Assíncrona e Escalonador do DAG.** Decide quando e onde cada célula executa sob concorrência.

**Camada 6 — Harness de Simulação.** O módulo `simulation_harness.py`, biorreator e juiz.

**Camada 7 — Verificação, Telemetria e Metodologia Experimental.** Observabilidade estruturada, definição de sobrevivência computacional e ciência.

### 4.2 Os quatro módulos: responsabilidades e contratos

#### `organism_core.py` — NeuralOrganism (Núcleo)

**Responsabilidade.** Encapsula a unidade viva: um `nn.Module` com identidade/genoma (`state_dict` + metadados de linhagem), operadores de mutação reprodutíveis, contabilidade de energia acoplada ao *forward*, invariantes de *shape* com falha-rápida, replicação sem *aliasing* e liberação limpa. O núcleo é **passivo**: expõe primitivas e sinais, mas não decide dividir nem morrer.

**Contrato.** As primitivas públicas são `clone(mutate, seed_override)`, `mutate(mutation_rate, generator)`, `forward(x, hormonal_context)`, `extract_representation()`, `release()`, `to(device)` e `genome_signature()`. O genoma carrega `{id (UUID), generation, parent_id, specialization, mutation_seed, birth_step, device, arch_signature}`, com derivação determinística do *seed* do filho a partir do pai (hash SHA→int). A energia é um *buffer* `float64` (não `Parameter`), atualizada sob `no_grad`. A `arch_signature` (hash canônico de topologia+*shapes*+*dtypes*) é pré-condição de replicação e de conexão no DAG. Ordem contratual de apoptose no lado do núcleo: soltar refs → (externo) `gc.collect()` → (externo) `empty_cache()` guardado por `is_available()`.

**Nota de correção.** A crítica de engenharia verificou que o `clone` atual **já produz réplicas independentes** (`data_ptr` distintos; mutar o filho não afeta o pai), pois usa `deepcopy` de `state_dict` + `load_state_dict`. A narrativa de "CPU-pivô para evitar *aliasing*" é, portanto, **removida como correção de bug inexistente**; o CPU-pivô é mantido apenas como política device-safe, e o teste de independência (`data_ptr` distintos) permanece como regressão barata que protege contra futuras regressões (ex.: troca por `copy.copy` raso).

#### `hormonal_bus.py` — HormonalBus (Barramento)

**Responsabilidade.** Meio latente contínuo e concorrente-seguro para comunicação por exsudação vetorial (escrita EMA *in-place*) e sensoriamento por atenção de cosseno. Blackboard tensorial `[slots, embed_dim]`, um slot por célula viva, com dissipação temporal real, *snapshot-isolation* versionado e política de diferenciabilidade explícita.

**Contrato.** A API pública é preservada (`register/release`, `secrete/sense`, `emit_hormone/hormone/hormone_panel`, `tick`, `snapshot`, `active_field`, `occupancy`), pois `mitosis_engine` e `organism_core` dependem dela. As correções internas endereçam cinco defeitos verificados no código: (1) leitura por **cosseno verdadeiro** (normalizar *query* E *keys*), substituindo o score assimétrico atual `keys @ q / (‖q‖+ε)`; (2) **dissipação temporal real** no `tick()` sobre todos os slots ocupados, com envelhecimento (`_age`) agora efetivamente consumido pela atenção; (3) **snapshot-isolation versionado** que só recopia quando há escrita desde a última leitura, eliminando o `clone` incondicional sob *lock*; (4) **separação de três constantes de tempo** (`write_blend`, `decay_vec`, `decay_scalar`), hoje colapsadas em `hormone_decay=0.92`; (5) **política de diferenciabilidade explícita** — não-diferenciável por padrão (`detach`/`no_grad`), com modo diferenciável opt-in e *stop-gradient* nas *keys*. Blindagem numérica: *clamp* de norma `c_max` e sanitização de não-finitos na escrita.

#### `mitosis_engine.py` — MitosisEngine + Colony (Motor)

**Responsabilidade.** Transforma um cenário multi-camada em plano de fissão: embutimento e decomposição em unidades semânticas, medição escalar de Divergência Semântica `D`, decisão com histerese, seleção de *k* filhos por *clustering* estável, herança por *warm-start* + viés de especialização, e inserção no DAG com política de gradiente por-ramo. Separa rigidamente a **fase de análise** (assíncrona, sem *lock*) da **fase de mutação** (síncrona, atômica, sob barreira). A `Colony` é *share-nothing* por requisição.

**Contrato.** O encoder Φ é **compartilhado com o Barramento** (contrato fixado na Camada 0). A decisão de fissão consulta o `asyncio.Semaphore` de orçamento (ver Seção 7), substituindo a checagem TOCTOU verificada nas linhas 455–460 do código atual. A herança é por *deep-copy* device-safe + injeção de viés via contexto-condicionante de dimensão fixa (`= d`), preferida sobre mutar pesos herdados (reversível, não-destrutiva). A telemetria por evento de mitose emite `D`, `k`, tamanhos de *cluster*, silhueta, energia consumida, profundidade e estado do *latch*.

#### `simulation_harness.py` — Structured Scenario Generator (Harness)

**Responsabilidade.** Biorreator e juiz. Fabrica um problema multi-domínio sinteticamente controlado com *ground-truth* analítico, injeta-o como lote de vetores-alvo honrando o contrato do Barramento, mede convergência, impõe determinismo assíncrono e emite o veredicto de sobrevivência computacional. Inclui baselines de controle (monolítico; enxame-sem-hormônio) e, por exigência das críticas, **cenários de controle onde dividir é errado**.

**Contrato.** A entrada é um tensor `[K·M, d]` com rótulos de domínio ocultos (só para avaliação). O `d` é parâmetro compartilhado único, lido no *boot* com falha-rápida se divergir. O *ground-truth* global `S* = (I − γC)⁻¹ P` é mantido *detached*, fora do grafo, nunca visto pelo organismo. O oráculo composto pontua cobertura, resíduo de cascata, coerência e custo energético.

#### `evolutionary_coder.py` — Evolutionary Coder (Auto-Refatoração) · *módulo de extensão, Fase 10*

**Responsabilidade.** Aplica busca evolutiva (programação genética / síntese de programas) para refatorar código Python-alvo, **reutilizando** a maquinaria de orquestração, ciclo de vida e telemetria do B.I.O.M.A. (fan-out, orçamento, apoptose, `BioEvent`), porém operando sobre **programas, não tensores**. Não introduz novas afirmações biológicas nem toca no grafo de autograd: refatoração é busca **discreta não-diferenciável**, sem gradiente envolvido. Os "micro-agentes" aqui são *workers* de mutação — reaproveitam o padrão de DAG/apoptose, mas não executam *forward* neural.

**Contrato.** `EvolutionaryCoder` expõe `generate_population(alvo, testes, N, budget)`, `evaluate_fitness()` e `converge_and_distill()`. As variantes são executadas **exclusivamente em `subprocess` isolado** (limites de recurso via `setrlimit`/*job object* do Windows, *timeout* duro, sem rede) — **nunca `exec()` in-process**, que não isola memória/tempo e pode derrubar o *host*. A fitness é **lexicográfica**: correção como portão duro (qualquer teste `pytest` falho → 0), depois latência (mediana de R repetições, não amostra única), depois delta de RSS. A "destilação reversa" é, honestamente, **promoção do *transform* vencedor ao catálogo determinista da Fase 8** — não a atualização de um "conceito de código limpo" numa rede. Cada variante é **rotulada por origem** (AST-determinística vs. LLM-quarentena); apenas o caminho AST entra na validação reproduzível (ver Fase 10 e a reconciliação com a Fase 8).

---

## 5. Roteiro Faseado

Cada fase declara objetivo, passos, entregáveis, critérios de aceitação testáveis, dependências e duração. As três lacunas de severidade alta identificadas pelas críticas (definição estatística de CSR, atuador do *loop* de auto-correção, reprodutibilidade sob concorrência) são **pré-condições de entrada da Fase 8** e estão incorporadas abaixo.

### Fase 0 — Estabilização de Base, Auditoria e Andaimes de Verificação

**Objetivo.** Estabelecer o chão firme: ambiente reprodutível, auditoria completa do esqueleto existente contra os pilares, o documento canônico Metáfora vs. Mecanismo, e os andaimes mínimos de teste/telemetria/CI. Congelar os **contratos globais**, incluindo o encoder Φ e um **registro de limiares versionado**.

**Passos.** Criar ambiente virtual isolado fixando `torch` CPU, `numpy`, `psutil`, `pytest`, `hypothesis`; congelar `requirements.txt`. Rodar `run_local.py` e `smoke_client` e capturar a linha de base (exit code, tempo, RSS, contagem de células). Auditar linha-a-linha os quatro módulos, produzindo inventário de defeitos rastreado a pilar. Escrever o documento canônico Metáfora vs. Mecanismo (8 termos × 3 níveis), o Glossário de Fronteiras Epistêmicas e o Contrato de Invariantes de Segurança. Fixar o contrato do encoder Φ (dimensão `d`, normalização L2, instanciação). Criar o registro de limiares versionado. Instalar `pytest` com marcadores (unit/integration/property/stress), o utilitário de medição de memória (RSS + `gc.get_objects`) e o CI local. Estender `seed_everything` para `torch`+`numpy`+`random` e escrever o teste de reprodutibilidade lógica.

**Entregáveis.** Ambiente reprodutível; relatório de auditoria com inventário de defeitos (arquivo:linha, severidade, pilar); documento canônico; glossário e contrato de invariantes; contrato de Φ; registro de limiares; andaime de testes; utilitário de memória; linha de base do estado de partida.

**Critérios de aceitação.** Todos os módulos importam sem erro em Python 3.12 CPU-only. `run_local.py` termina com exit code 0 no Windows. Inventário com ≥ 6 defeitos, cada um com arquivo:linha e pilar. Tabela Metáfora vs. Mecanismo com 100% dos 8 termos qualificados; contagem de afirmações não-qualificadas de vida/consciência = 0. `pytest` coleta e roda verde. Teste de reprodutibilidade lógica produz relatório de divergência mensurado.

**Dependências.** Nenhuma. **Duração.** 1,5–2 semanas (revisado de 1 semana, atendendo à crítica de subdimensionamento; o utilitário anti-vazamento completo de 3 modos pode ser diferido para o início da Fase 4).

### Fase 1 — Núcleo do Organismo Endurecido

**Objetivo.** Elevar o núcleo ao contrato do pilar: replicação sem *aliasing*, mutação reprodutível e numericamente estável, contabilidade de energia sob `no_grad`, invariantes de *shape* com falha-rápida, apoptose sem vazamento com `weakref` nos links do DAG. O núcleo permanece passivo.

**Passos.** Formalizar o esquema do genoma e a derivação determinística de *seed*. Consolidar `clone()` (mantendo a independência já existente; adicionar teste de regressão de `data_ptr`). Implementar `mutate()` com perturbação gaussiana de escala relativa por camada (`σ_layer = mutation_rate·(std(θ_layer)+ε)`), máscara de mutabilidade congelando normalizações, `torch.Generator` dedicado e verificação de finitude com rejeição. Integrar contabilidade de energia no *forward* via `register_forward_hook` sob `no_grad`. Adicionar validação de *shape* na fronteira do *forward*. Implementar `extract_representation()` e `release()` (com `handle.remove()` e `weakref`). Padronizar a ordem contratual de apoptose.

**Entregáveis.** `organism_core.py` refatorado com contratos pré/pós-condição; esquema do genoma; formulação da mutação e do modelo de energia; suíte de testes *property-based* do núcleo.

**Critérios de aceitação.** Independência de replicação: 100% dos clones com `data_ptr` distintos; mutar filho não altera o pai (assert bit-a-bit). Reprodutibilidade de mutação: mesmo `(genoma, seed, device, dtype)` → tensores idênticos no caminho CPU. Integridade de gradiente: perda/grad COM contabilidade == SEM contabilidade dentro de tolerância. Falha-rápida de *shape*: 100% dos *mismatches* detectados. Estabilidade numérica: fração de genomas finitos = 100% ao longo de N gerações. Coletabilidade: após `release()`+`gc.collect()`, instâncias coletadas; *overhead* do *hook* de energia < 10%.

**Dependências.** Fase 0. **Duração.** 2 semanas. *(Pode rodar em paralelo à Fase 2, pois ambas dependem só da Fase 0 e do contrato de Φ congelado.)*

### Fase 2 — Barramento Hormonal Concorrente-Seguro

**Objetivo.** Corrigir os cinco defeitos verificados do barramento preservando a API pública: cosseno verdadeiro, dissipação temporal com *gating* por *staleness*, *snapshot-isolation* versionado, constantes de tempo separadas, diferenciabilidade explícita e blindagem numérica.

**Passos.** Separar `write_blend`, `decay_vec`, `decay_scalar` em `config.py`, documentando meias-vidas. Reescrever `secrete_sync` com fusão EMA, *clamp* de norma `c_max`, sanitização de não-finitos e zero de `_age`. Reescrever `sense_sync` com cosseno verdadeiro, máscara de self/não-ocupados/*stale*, e *gating* por frescor. Mover a dissipação para `tick()` sobre todos os slots ocupados. Implementar *snapshot-isolation* versionado (`version`/`view_version`, cópia-sob-*lock* + cômputo-fora-do-*lock*). Tornar a diferenciabilidade explícita (`differentiable=False` por padrão; *stop-gradient* nas *keys* no modo opt-in). Escrever a suíte de estresse.

**Entregáveis.** `hormonal_bus.py` refatorado; `config.py` com constantes de tempo documentadas; contrato de concorrência como comentário e teste; modo de diferenciabilidade explícito; suíte de estresse (concorrência, dissipação, *staleness*, numérica, eficiência de *snapshot*).

**Critérios de aceitação.** Concorrência: N escritores + M leitores por T iterações sem erro *in-place*, *deadlock* ou *timeout*. Zero NaN/Inf no *manifold* e em qualquer contexto retornado; norma de slot ≤ `c_max` em todos os *ticks*. Dissipação: após K *ticks* sem secreção, `‖M[slot_inativo]‖ ≤ ε`. Atenção por cosseno: pesos somam 1 sem NaN inclusive no caso todas-keys-zero; invariância à escala das *keys* demonstrada. Eficiência de leitura: fração de `sense` que reaproveitam *snapshot* acima do limiar-alvo declarado no registro. No modo diferenciável, gradiente da leitura de uma célula não altera parâmetros de outra.

**Dependências.** Fase 0. **Duração.** 2 semanas. *(Paralela à Fase 1.)* **Mini-portão de integração ao fim:** núcleo lê/escreve o barramento sem NaN em 1 ciclo.

### Fase 3 — Motor de Mitose: Divergência, Histerese e Herança

**Objetivo.** Formalizar o controlador de fissão com métrica `D` **bem-condicionada** (endereçando a crítica de mal-condicionamento), decisão com histerese de banda dupla + EMA + *cooldown*, seleção de *k* por *clustering* penalizado, herança não-destrutiva, e separação análise-assíncrona vs. mutação-síncrona.

**Passos.** Implementar o embutimento via encoder Φ compartilhado, com normalização L2. **Especificar cada sinal de `D` com domínio, escala e comportamento em casos-limite** (`k=1`, `n<k`, *cluster* singleton), respondendo à crítica: a silhueta é computada **sobre a partição candidata do seletor de `k`, não antes** (removendo a circularidade), ou é usada apenas na seleção de `k`; cada sinal é normalizado explicitamente para [0,1] antes da soma convexa; a "entropia de tópicos" é **substituída pela entropia da distribuição de massa entre *clusters*** do próprio seletor de `k`, quantidade computável sem modelo de tópicos latente. Implementar a histerese (`τ_up > τ_down`, EMA, *cooldown*, escalonamento com profundidade). Implementar o seletor de `k` (varredura 2..k_max, critério `Qualidade(k) − λ·k`, `min_cluster_size`, restrição energética; se nenhum `k>1` supera `k=1`, não há mitose). Reescrever a herança (deep-copy + contexto-condicionante). Formalizar a inserção no DAG e a política de gradiente por-ramo. Separar rigidamente análise (async) de mutação (sync atômica).

**Entregáveis.** `mitosis_engine.py` com `D` de quatro componentes bem-especificados; módulo de embutimento; rotina de herança+especialização; protocolo de inserção no DAG; matriz de hiperparâmetros com *defaults* e faixas; esquema de telemetria por evento de mitose; **ablação dos pesos `w1..w4`** demonstrando robustez da decisão.

**Critérios de aceitação.** Fidelidade da decisão: em cenários rotulados uni- vs. multi-domínio, o motor dispara nos multi-domínio e **suprime nos uni-domínio** — a **matriz de confusão da decisão de mitose é elevada a métrica primária** (precisão/recall acima de piso declarado no registro de limiares). Estabilidade anti-oscilação: *cooldown* respeitado em 100% dos casos; ausência de ciclo fissão→apoptose→fissão dentro de janela N. Reprodutibilidade do *clustering*: mesma *seed* → `k*` idêntico. **Verificação de sanidade do *deep-copy*** na divisão: `‖f_após − f_antes‖ < 1e−5` **antes** de qualquer especialização (declarado honestamente como sanidade de cópia, **não** propriedade Net2Net). **Diferenciação efetiva** (novo critério): após K passos de *adapt*, a distância inter-filho e a queda de perda por sub-domínio excedem um piso, e a especialização correlaciona com os centroides — provando que a mitose não é teatro caro. Robustez a `w1..w4`: a decisão de mitose não muda sob perturbação dos pesos (senão são *ad hoc*). Contenção: número de células ≤ `branching_max^prof_max`; nenhuma mutação concorrente com *backward*.

**Dependências.** Fases 1 e 2. **Duração.** 2,5 semanas.

### Fase 4 — Homeostase, Energia e Apoptose

**Objetivo.** Fechar o *loop* nascimento↔morte com contabilidade honesta: equação de estado de energia, FSM de apoptose com 4 gatilhos e histerese, transferência de representação com *rollback*, limpeza determinística verificada anti-vazamento e regulador homeostático global.

**Passos.** Formalizar a equação de estado `E(t+1) = clamp(E − λ_basal·E − ΔE_trabalho − ΔE_entropia + η·max(0, Δutil), E_min, E_max)`, com `Δutil` = queda de perda (regeneração por **progresso**). Implementar o módulo de incerteza device-agnóstico (Shannon + *proxy* de variância, normalização por `log(K)`, EMA) — nomeado **`output_uncertainty`** para não colidir com a `cluster_mass_entropy` da Fase 3. Implementar a FSM `ALIVE→DYING→TRANSFERRING→DEAD` com 4 gatilhos (tarefa resolvida, energia esgotada, contribuição marginal, senescência), logando o gatilho de cada morte. Implementar a transferência (LERP/SLERP por utilidade + destilação + *snapshot*/*rollback*). Padronizar a limpeza em `try/finally`. Implementar o verificador anti-vazamento de 3 modos e o regulador homeostático global. **Endereçar o bug verificado em `absorb()`** (`normalize(v)·‖v‖` é *no-op*, memória herdada cresce sem limite): incluí-lo no inventário como 7º defeito e unificar o caminho de *merge* com disciplina LERP/SLERP de α limitado. Fazer **ablação de `κ`** (incluindo `κ=0` e `κ<0`) para provar que o termo de incerteza tem efeito útil.

**Entregáveis.** Módulo de energia integrado ao núcleo; equação de estado + módulo de incerteza; FSM com logging de gatilho; rotina de transferência com *rollback*; rotina de limpeza em `try/finally`; verificador anti-vazamento; regulador homeostático; painel de telemetria (burn_rate, energia residual, incerteza por agente, mortes por gatilho, status anti-vazamento).

**Critérios de aceitação.** **Auditoria de contabilidade** (renomeada de "conservação energética"): a soma debitada iguala a soma dos componentes computados dentro do erro de ponto flutuante — declarado explicitamente como ausência de dupla-contagem, **não** conservação física; `E_i` nunca negativa; `output_uncertainty` bem-normalizada. Invariante anti-vazamento: após N ciclos, `mem_final ≤ mem_baseline + ε`; contagem de `torch.Tensor` vivos do agente morto == 0; população-viva == objetos `NeuralOrganism` vivos em `gc`. Preservação de conhecimento: perda global não aumenta após transferências (na maioria); taxa de *rollback* < limiar. Estabilidade homeostática: população em `[N_min, N_max]` sem extinção nem explosão. Utilidade da apoptose: mortes por "tarefa resolvida" + "marginal" dominam sobre "energia esgotada" + "senescência". Sobrevivência parcial: fração de terminações que são apoptose ordenada com limpeza verificada = 100%; zero necrose; *overhead* de contabilidade < 10%.

**Dependências.** Fases 1 e 3. **Duração.** 2,5 semanas. **Mini-portão de integração ao fim:** nascimento→trabalho→apoptose→fusão ponta-a-ponta em 2 células, com verificação anti-vazamento.

### Fase 5 — Orquestração Assíncrona e Escalonador do DAG

**Objetivo.** Endurecer o plano de execução concorrente **com o modelo de concorrência correto** (cooperativo *single-thread* + *executor* de dados). Substituir a recursão implícita por escalonador topológico explícito, converter `cell_budget` em teto de admissão via `Semaphore` (elimina o TOCTOU verificado), adicionar *backpressure* de telemetria e forçar a invariante de isolamento de autograd.

**Passos.** Implementar o `dag_scheduler` explícito (ready-set + join-counter): a redução do pai só dispara quando `pending[p]==0` (todos os filhos apoptosaram). Substituir a checagem não-atômica `live_count()+2 <= cell_budget` por `asyncio.Semaphore(cell_budget)` com **reserva-antes-de-dividir** de N *permits* e *rollback* — a crítica de engenharia esclarece que isto é uma **corrida cooperativa/reentrância de corotina no `gather`**, não TOCTOU de *threads*, e o Semaphore a resolve mesmo assim. Converter `colony.queue` em `asyncio.Queue(maxsize=Q)` com modos *strict*/*lossy* e não-descarte da sentinela. Codificar a invariante de isolamento de autograd como *assert* de *ownership* pré-*backward*, com *fallback* `adapt_executor(max_workers=1)`. Impor a regra **no-await-under-lock** e ordem total de *locks* (bus *lock* sempre o mais interno, único por bus). Documentar a estratégia honesta de paralelismo CPU-only (`torch.set_num_threads(1)`, `_MAX_WORKERS=clamp(2,8,cpu−2)`, teto de Amdahl, *batching* de irmãs preferido a mais *workers*; `atexit shutdown(wait=True, cancel_futures=True)`).

**Nota de calibração de esforço (crítica de engenharia).** Como o barramento é single-thread no *event loop*, o `threading.Lock` é majoritariamente decorativo e o *snapshot-isolation* versionado só se torna estritamente necessário **se** `secrete`/`sense` migrarem para dentro do *executor*. O plano mantém o Semaphore (a corrida cooperativa é real) mas **rebaixa** o restante das defesas de *thread* a "guarda de robustez para evolução futura", documentando-as como tal em vez de tratá-las como correção de um *race* ativo.

**Entregáveis.** `dag_scheduler`; `Semaphore` com reserva+*rollback*; `asyncio.Queue` *strict*/*lossy* com `dropped_events`; guia de disciplina de autograd; regras no-await-under-lock e ordem total de *locks*; modelo de custo/honestidade de Amdahl com instrumentação tempo-em-executor vs. tempo-de-loop.

**Critérios de aceitação.** Invariante de orçamento nunca violada: `live_count() ≤ cell_budget` sempre; zero `RuntimeError 'manifold saturated'` sob *fuzz* de *fan-out* máximo. Correção de autograd: gradientes de `adapt()` concorrente idênticos (até tolerância) aos seriais; zero *ownership* cruzada. Ausência de *deadlock*: *timeout* global nunca atingido; auditoria estática confirma zero `await` sob *lock* e grafo de espera acíclico. *Backpressure* efetivo: sob consumidor lento, memória da fila limitada a O(maxsize); `dropped_events` reportado em modo *lossy*. Saída limpa no Windows: exit code 0 em execuções repetidas. Ordem topológica sempre respeitada; *overhead* do escalonador < limite-alvo declarado.

**Dependências.** Fases 2, 3, 4. **Duração.** 2 semanas. **Mini-portão de integração ao fim:** DAG concorrente sem *deadlock* em *fan-out* máximo.

### Fase 6 — Harness de Simulação e Cenário de Referência

**Objetivo.** Construir o biorreator e juiz com *ground-truth* analítico, **quebrando a circularidade do benchmark** apontada pelas críticas: além dos cenários multi-domínio, incluir cenários onde dividir é errado.

**Passos.** Implementar o SSG: dado *seed* e config, gerar protótipos ortogonalizados `P = QR(G)[:K]`, nuvens `x = p_k + σ·ε`, matriz de cascata `C` normalizada (`raio_espectral(γC) < 1`) e *ground-truth* `S* = (I − γC)⁻¹ P`. Implementar o injetor de estímulo (contrato do Barramento; `d` compartilhado com falha-rápida). Implementar o oráculo composto (`Score = w1·Cobertura + w2·(1−ResíduoCascata) + w3·Coerência + w4·(1−CustoEnergNorm)`), com `S*` sempre *detached*, fora do grafo. Implementar a camada de determinismo assíncrono (redução sobre sequência ordenada por id de domínio). Implementar a sonda de sobrevivência computacional. Implementar os baselines (monolítico; sem-hormônio). **Adicionar o eixo experimental de estrutura de domínio (crítica de rigor):** cenários genuinamente **uni-domínio** (`K=1`), cenários com `K` desconhecido, e cenários **adversariais** onde a divisão prejudica (domínios acoplados que exigem representação conjunta). **Adicionar análise de identificabilidade:** reportar `cos(síntese, P_médio)` como *baseline* trivial ao lado de `cos(síntese, S*)`; varrer `γ` de 0 ao limite espectral e mostrar que a margem sobre o monolítico **cresce com `γ`** — se ambos os cossenos forem altos, o cenário é trivial e é reportado como tal. Criar a suíte-currículo (*smoke*/*severe*).

**Entregáveis.** `simulation_harness.py` completo; documento de Contrato de Interface; especificação matemática do cenário; suíte-currículo; baselines de controle; **cenários de controle onde dividir é errado**; análise de identificabilidade; teste de reprodutibilidade; protocolo de sobrevivência computacional.

**Critérios de aceitação.** Taxa de disparo de mitose: em 100% das execuções *severe* multi-domínio, `D > τ` e o DAG ramifica em ≥ K sub-agentes; **e em 100% dos cenários uni-domínio a mitose é suprimida**. Cobertura de domínio ≥ 0,9 no *severe*. Resíduo de cascata normalizado < 0,1. Coerência: `cos(síntese, S*) ≥ 0,95` com estabilidade. **Identificabilidade:** a margem sobre o monolítico cresce monotonicamente com `γ`; `cos(síntese, P_médio)` é significativamente menor que `cos(síntese, S*)` no regime de `γ` alto (prova que coordenação é necessária). Margem sobre baselines > 2 desvios-padrão sobre R *seeds*; *ground-truth* confirmadamente *detached*.

**Dependências.** Fases 1–5. **Duração.** 2,5 semanas.

### Fase 7 — Telemetria Estruturada e Definição Operacional de CSR

**Objetivo.** Consolidar a observabilidade como cidadã de primeira classe e definir a **Taxa de Sobrevivência Computacional (CSR)** de forma falsificável, **estatística** (não igualdade exata sobre processo estocástico), com tolerâncias calibradas empiricamente.

**Passos.** Formalizar o esquema `BioEvent` versionado (JSONL append-only, `seq` monotônico, correlação de linhagem). Plantar *hooks* não-invasivos nos pontos de vida celular. Implementar o dashboard de telemetria biológica. Escrever a definição operacional de CSR: `survive(c) = healthy_forward ∧ no_nan_inf ∧ transfer_ok ∧ clean_apoptosis ∧ no_leak ∧ no_race`. **Endereçar a crítica de alvo estatisticamente frágil:** o critério primário passa a ser **`CSR ≥ 1−ε` com limite inferior de Wilson ≥ limiar sobre N nascimentos declarados**, OU `CSR = 1,0` condicionado a que toda terminação `< 1,0` seja classificada como necrose genuína por um segundo oráculo independente-de-tolerância (o cruzamento `gc.get_objects`). **Endereçar a crítica de vazamento por ruído de alocador (CPU-only):** o critério primário de vazamento **abandona "retorno a baseline ±1%"** e adota **"ausência de tendência de crescimento no *soak*"** (inclinação `b ≤ b_max`, `p ≥ 0,05`) **mais** "contagem `gc` de `NeuralOrganism` vivos == 0" (independente de tolerância de RSS). Implementar os probes de vazamento por regressão e de *race* (invariante *read-after-write*). Adicionar amostragem seletiva de eventos de alta frequência e redação de tensores. Medir o *overhead* de telemetria.

**Entregáveis.** Especificação `BioEvent`; *hooks* + *sink* JSONL; dashboard device-agnóstico; documento de definição operacional de CSR com protocolo de calibração e denominador N declarado; probes de vazamento e de *race*; relatório de *overhead* de telemetria.

**Critérios de aceitação.** Alinhamento telemetria↔realidade: cada sinal mapeia 1:1 a grandeza mensurável; reconstrução do DAG a partir do JSONL válida. Igualdade população-viva `A(t)` vs. contagem `gc`. Zero eventos NAN_INF. **CSR bem-definido:** tolerâncias calibradas da distribuição de resíduo de *baseline*; CSR falsificável e automatizável; denominador N explícito. *Overhead* de telemetria abaixo do limite; ligar/desligar instrumentação não muda CSR. Reprodutibilidade da telemetria: mesma *seed* → `BioEvents` idênticos módulo *timestamps*.

**Dependências.** Fases 1–6. **Duração.** 2 semanas. *(O esquema `BioEvent` pode ser rascunhado cedo, na Fase 0–1, sem custo de caminho crítico.)*

### Fase 8 — Loop de Auto-Correção Dirigido por Sintomas

**Objetivo.** Construir o controlador de reparo em malha fechada que persegue a meta de sobrevivência computacional **sem mascarar bugs**. **Pré-condições de entrada (as três lacunas altas devem estar congeladas):** (i) CSR como critério estatístico com N declarado (Fase 7); (ii) reprodutibilidade lógica garantida via execução serial nos *runs* de validação (Fase 6/9); (iii) **atuador definido**.

**Definição do atuador (crítica de completude).** O *loop* é um **controlador de seleção-de-patch sobre um catálogo FINITO e determinista de transformações escritas por humanos** (biblioteca de *refactors* auditáveis parametrizados), **não** um gerador de código por LLM. Cada patch tem pré/pós-condição verificável. Se auto-modificação por LLM for desejada no futuro, ela é isolada num modo separado marcado como **não-reproduzível** e **excluída** do caminho da Fase 9. Esta escolha é obrigatória porque geração por LLM quebraria a exigência de reprodutibilidade da validação científica.

**Passos.** Definir o catálogo sintoma→detector→diagnóstico→patch para as 8 classes (SHAPE_MISMATCH, CUDA_OOM, CPU_LEAK, VRAM_LEAK, ASYNC_RACE, NAN_INF, GRAD_BREAK, DEADLOCK); cada patch é correção estrutural auditável (**nunca** supressão cega de exceção ou *cast* forçado de *shape*). Implementar os detectores. Implementar o controlador OODA (run → se CSR-estatístico satisfeito e `conv_ok` então FIXPOINT; senão classificar, localizar, aplicar patch de maior prioridade, re-verificar). Implementar a guarda de regressão (re-rodar a suíte S completa após cada patch; verificar `conv_score` em paralelo ao CSR — célula que "sobrevive" mas não contribui é sinalizada). Implementar o critério de parada honesto (FIXPOINT OU `iter ≥ max_repair_iter` → relatório de falha com menor contraexemplo via *shrinking* do Hypothesis). Integrar a suíte *property-based*. Executar *end-to-end* sobre *smoke* e *severe*.

**Entregáveis.** Catálogo de reparos (8 classes) com política de parada e formato do relatório honesto; controlador OODA com guarda de regressão; suíte *property-based* com *shrinking*; registro auditável de REPAIR_ACTIONs; relatório de falha honesto.

**Critérios de aceitação.** Iterações até FIXPOINT registradas; taxa de sucesso do *loop* medida. Nenhum patch é supressão cega (revisão auditável); guarda de regressão re-roda S sem regressão. Cobertura *property-based* (energia não-negativa, *deep-copy* sem *storage* compartilhado, apoptose libera memória, gradiente não quebrado) sem contraexemplo após *shrinking*. Sobrevivência espúria prevenida. Honestidade de parada: em cenário deliberadamente irreparável (bug injetado), o *loop* reporta falha, não sucesso falso. CSR-estatístico atingido nos perfis *smoke* e *severe* com zero ANOMALY não-recuperado.

**Dependências.** Fases 6 e 7. **Duração.** 2,5 semanas.

### Fase 9 — Validação Experimental e Consolidação Final

**Objetivo.** Provar causalmente que os mecanismos agregam valor via desenho fatorial 2×2 com **reprodutibilidade lógica** (não bit-a-bit sob concorrência), atingir e certificar a sobrevivência computacional estável em *soak* prolongado, e consolidar a documentação de honestidade.

**Passos.** Executar o fatorial 2×2 (mitose {on,off} × barramento {on,off}) com K réplicas, *seed_grid*, dados/hiperparâmetros fixos. **Para os *runs* de validação, forçar `max_workers=1` (execução serial determinista)** e documentar que o paralelismo é apenas de desempenho — medindo correção e desempenho separadamente (crítica de reprodutibilidade). Aplicar análise estatística (Welch t / Mann-Whitney conforme normalidade; Cohen d / Cliff δ; IC 95% *bootstrap*; correção Holm-Bonferroni/BH). Fazer análise de poder a priori para dimensionar K. Executar o *soak*/*stress* prolongado certificando o critério de vazamento (tendência `b ≤ b_max`, `p ≥ 0,05`; biomassa fantasma zerada; `_LIVE_CELLS → 0`). Consolidar o Mapa de Posicionamento na Literatura e revisar a documentação anti-*overclaiming*. Auditar os invariantes finais.

**Reprodutibilidade — política honesta (crítica).** Separar explicitamente: **(a) determinismo lógico** — mesmas decisões de mitose/apoptose, mesma topologia de DAG, mesmo veredicto de CSR — **exigido como critério de aceitação**; e **(b) determinismo numérico bit-a-bit** — documentado como *best-effort*, atingível apenas sob execução serial. A validade científica das ablações **não** é acoplada a reprodutibilidade bit-a-bit; a tolerância de métricas é derivada empiricamente do *jitter* de ponto flutuante em CPU (tipicamente 1e−4 a 1e−3, não 1e−5).

**Entregáveis.** Relatório fatorial 2×2 com efeito causal (IC 95% *bootstrap*, correção múltipla, tamanho de efeito); certificado de *soak* (critério de vazamento atendido, zero biomassa fantasma); Mapa de Posicionamento + revisão anti-*overclaiming*; auditoria final de invariantes; relatório consolidado + certificado de aceitação.

**Critérios de aceitação.** Efeito causal significativo após correção múltipla, com tamanho de efeito e IC. CSR-estatístico satisfeito na suíte canônica S, replicado em R execuções, com zero ANOMALY não-recuperado. Critério de vazamento atendido no *soak*; `_LIVE_CELLS → 0` ao fim de toda *run*. Reprodutibilidade **lógica** confirmada; reprodutibilidade numérica documentada honestamente. Verificação de sanidade da divisão em 100% das divisões; auditoria de contabilidade com erro de ponto flutuante apenas. Rastreabilidade: cada mecanismo central cita ≥ 1 família técnica (sem papers inventados); 0 afirmações não-qualificadas.

**Dependências.** Todas (0–8). **Duração.** 2,5 semanas.

### Fase 10 — Trilha de Extensão: Desenvolvimento Evolutivo de Software (Auto-Refatoração)

**Natureza.** Capacidade **opcional** construída sobre o framework já validado (pós-M8 / *code-freeze*). O módulo `evolutionary_coder.py` aplica busca evolutiva (programação genética / síntese de programas) para refatorar código Python-alvo, **reutilizando** — não duplicando — a maquinaria de orquestração (Fase 5), ciclo de vida/apoptose (Fase 4), catálogo de *transforms* (Fase 8) e telemetria (Fase 7), porém operando sobre **programas, não tensores**. O projeto-base conclui-se sem esta fase; ela é uma extensão de capacidade.

**Reenquadramento honesto (obrigatório antes de qualquer passo — mesma disciplina das Fases 3, 4 e 8).** O pedido original contém quatro afirmações que a tese de honestidade do plano exige corrigir explicitamente:

- **Não há gradiente a preservar.** Refatoração é **busca discreta não-diferenciável** sobre o espaço de programas. A expressão "a execução dinâmica derruba gradientes" é um **erro de categoria**: não existe grafo de autograd neste módulo. A integridade de gradiente do restante do framework é **ortogonal** e permanece intacta justamente porque o Coder não toca em tensores. Qualquer telemetria ou log de "gradiente" aqui é proibido (auditável estaticamente).
- **"Evolução" não descobre classe de complexidade sozinha.** Transformar bubble-sort O(N²) em O(N log N), ou Fibonacci iterativo em memoizado/fechado, **não emerge de mutação aleatória** em nenhum horizonte prático. O ganho vem de uma de duas fontes, e cada variante é **rotulada por origem**: (a) *transform* AST **determinístico já presente no catálogo** (ex.: "trocar laço de ordenação por `sorted()`", "inserir `functools.lru_cache`", "içar invariante de laço"), ou (b) **proposta de um LLM** (que aplica *conhecimento*, não seleção natural). Apresentar o resultado como "o organismo evoluiu e descobriu quicksort" seria N3 travestido de N1 — vetado. O alvo lento do teste é válido como *benchmark*; o que se mede é redução de latência sob origem declarada, não emergência.
- **`exec()` não isola nada.** Executar variante mutada com `exec()` no processo hospedeiro compartilha o interpretador, vaza estado global, não impõe limite de memória/tempo e pode derrubar o *host* com um laço infinito. O isolamento real exige **`subprocess`** com limites de recurso (`resource.setrlimit` no POSIX; *Job Objects* no Windows), *timeout* duro, ambiente restrito e sem rede. `exec()`/`eval()` in-process de código não-confiável fica **proibido** — é simultaneamente um risco de segurança e de estabilidade.
- **"Destilação reversa para a Stem Cell" é colheita de padrão, não aprendizado de conceito.** Uma rede não "atualiza sua representação conceitual de código limpo" ao observar um vencedor. O mecanismo honesto: **promover o *transform* vencedor ao catálogo reutilizável da Fase 8** e, opcionalmente, ajustar um *prior* de preferência sobre estratégias. "Destilação reversa" é rótulo narrativo (N2/N3), não uma operação de destilação de conhecimento neural.

**Reconciliação com a Fase 8 (reprodutibilidade).** A Fase 8 decidiu que o *loop* de auto-correção usa um catálogo **finito e determinista**, e **não** geração por LLM, para preservar a reprodutibilidade exigida pela validação científica. A Fase 10 honra isso com **dois caminhos separados** que compartilham o mesmo motor de fitness e a mesma apoptose, diferindo **apenas na fonte das variantes**: o **caminho reproduzível** (somente *transforms* AST determinísticos — entra na validação estatística da Fase 9) e o **caminho exploratório** (propostas de LLM — quarentena marcada como **não-reproduzível**, fora do caminho de validação). Isto evita reabrir o conflito já resolvido na Fase 8.

**Passos.**

1. Definir a interface `EvolutionaryCoder`: entrada = função/módulo-alvo + suíte `pytest` estrita + orçamento (N variantes, tempo, memória); saída = script refatorado vencedor + relatório de métricas com origem rotulada.
2. `generate_population(N)` — instanciar N *workers* via o padrão de fan-out do orquestrador (Fase 5), cada um aplicando **uma** estratégia distinta: caminho A = *transform* AST do catálogo (parametrizado, reversível, com pré/pós-condição); caminho B (opcional, quarentenado) = proposta de LLM. Registrar origem e *seed* de cada variante.
3. `evaluate_fitness()` — executar cada variante em **`subprocess` isolado** (rlimit CPU+RSS, *timeout*, sem rede); rodar a suíte `pytest`; medir **fitness lexicográfica**: (i) correção como **portão duro** (qualquer teste falho → fitness 0), (ii) latência = **mediana de R repetições** com *warm-up* descartado, (iii) delta de RSS de pico medido no *subprocess*. Variantes com *syntax error* / exceção / *timeout* são **contidas** e pontuadas 0 sem afetar o *host* nem a busca.
4. `converge_and_distill()` — apoptose de toda variante abaixo do limiar (encerrar processo, remover do escopo, `gc.collect()` + `torch.cuda.empty_cache()` condicional a CUDA, verificar liberação e ausência de processo zumbi); promover o *transform* vencedor ao catálogo da Fase 8; emitir `BioEvent`s de nascimento/fitness/morte por variante; retornar o script vencedor e o relatório latência-original-vs-evoluída.
5. Suíte `tests/test_evolutionary.py` — alvo deliberadamente lento (bubble-sort O(N²) ou Fibonacci iterativo pesado) + assertivas de correção de saída. **Pré-condição declarada:** o catálogo AST contém o *transform* capaz de otimizar o alvo (caso contrário, o teste passa a ser um teste do proponente-LLM, o que deve ser explicitamente rotulado, não mascarado). Asserção: a variante vencedora passa 100% dos testes e reduz a latência mediana em ≥ δ, com origem registrada.

**Entregáveis.** Contrato de `EvolutionaryCoder`; *sandbox* de execução em *subprocess* com limites de recurso (POSIX + Windows *Job Objects*); motor de fitness lexicográfica com repetições e *warm-up*; catálogo mínimo de *transforms* AST (stdlib-sort, memoização, hoisting de invariante de laço, *comprehension*); ponte de promoção ao catálogo da Fase 8; `tests/test_evolutionary.py` com alvo lento; relatório de métricas (latência/memória original vs. evoluída, origem das variantes, taxa de sucesso operacional).

**Critérios de aceitação (testáveis).**

- **Isolamento:** 100% das variantes executam em *subprocess*; variante com *syntax error* ou laço infinito é contida por *timeout*/rlimit sem derrubar o *host* nem deixar processo zumbi.
- **Portão de correção:** variante que falha ≥ 1 teste recebe fitness 0 e é podada; **nenhuma** variante incorreta é promovida ao catálogo ou retornada.
- **Ganho medido, não narrado:** a variante retornada reduz a latência mediana do alvo em ≥ δ (limiar declarado) sobre R repetições; o relatório mostra latência original vs. evoluída com intervalo de confiança.
- **Origem rotulada:** cada variante declara AST-determinística vs. LLM-quarentena; o caminho reproduzível **não** contém variantes de LLM.
- **Apoptose sem vazamento:** após a busca, a contagem de processos-filho vivos = 0 e o RSS do orquestrador retorna ao *baseline* sem tendência de crescimento (mesmo critério estatístico da Fase 7).
- **Sem erro de categoria:** auditoria estática confirma ausência de qualquer referência a "gradiente"/autograd no módulo do Coder.
- **Reprodutibilidade:** no caminho só-AST, mesma *seed* + mesmo alvo → mesma população de variantes e mesmo vencedor.

**Dependências.** Fases 3 (fan-out), 4 (apoptose/energia), 5 (orquestração), 7 (telemetria) e 8 (catálogo de *transforms*). Inicia após o *code-freeze* / M8. **Duração.** ~3 semanas.

### Marco intermediário: MVSV (crítica de cronograma)

Para proteger a integridade estatística sob pressão de prazo, define-se um **Subconjunto Mínimo Cientificamente Válido**: um único cenário seedado, um único fatorial 2×2 com R réplicas suficientes para poder ≥ 0,8 num tamanho de efeito pré-declarado, e CSR sobre o perfil *smoke*. As hipóteses e critérios são **congelados (pré-registro interno) antes de rodar**, para evitar HARKing. *Severe*, *soak* prolongado e posicionamento exaustivo são trabalho incremental pós-MVSV.

---

## 6. Modelo de Energia/Homeostase e Política de Apoptose (Conceitual)

O modelo de energia é um **sistema de contabilidade de orçamento com fontes e sumidouros** — explicitamente **não** um sistema físico conservativo. Cada agente carrega um escalar de estado `E_i` em *buffer* `float64`, atualizado sob `no_grad`, que evolui pela equação de estado discreta:

`E_i(t+1) = clamp( E_i(t) − λ_basal·E_i(t) − ΔE_trabalho − ΔE_incerteza + η·max(0, Δutil), E_min, E_max )`

O termo `ΔE_trabalho` é o custo computacional debitado por passo (proxy de FLOPs analíticos derivados da topologia + tokens). O termo `ΔE_incerteza = κ·H_norm` penaliza a incerteza da saída (`output_uncertainty`, entropia de Shannon normalizada por `log(K)`), sendo `κ` um coeficiente de regularização cuja direção e magnitude são **decisões de design justificadas por ablação**, não leis derivadas. A regeneração `η·max(0, Δutil)` premia **progresso** (queda de perda no sub-domínio), nunca mera atividade, evitando agentes que queimam recursos sem convergir. O `clamp` mantém `E_i` em faixa fixa — e é precisamente este `clamp`, junto com fontes e sumidouros, que torna o sistema **não-conservativo por design**.

A propriedade auditável não é "conservação", mas **auditoria de contabilidade**: a soma debitada iguala a soma dos componentes computados dentro do erro de ponto flutuante (sem dupla-contagem, sem *drift*), e a energia nunca fica negativa. A correlação entre energia consumida e recurso real (tempo/RSS) é tratada como **monotonicidade fraca**, não como Pearson > 0,8 contra tempo de parede — pois, para MLPs pequenos em CPU, o tempo é dominado por *overhead* de despacho Python, não por FLOPs.

A **política de apoptose** é uma máquina de estados `ALIVE → DYING → TRANSFERRING → DEAD` governada por quatro gatilhos combinados por OR, com histerese (`N_estab` *ticks* consecutivos) exceto para energia esgotada (imediata): **(1) tarefa resolvida** (perda < `τ_loss` por `N_estab`), **(2) energia esgotada** (`E_i ≤ E_death`), **(3) contribuição marginal baixa** (`MC_i < τ_marginal` por `N_estab`), **(4) senescência** (idade > `T_max`). Cada morte loga qual gatilho disparou. O regulador homeostático global mantém `sum(E_i)` e a população sob o teto de recurso via uma variável de `pressão = clamp(sum(E_i)/E_global_budget, 0, 1)` que aperta `λ_eff`, eleva o limiar de mitose e prioriza apoptose marginal sob pressão — fechando o *loop* nascimento↔morte e impondo `N_max_hard` como salvaguarda anti-explosão. A apoptose é **saudável e esperada**; sua ausência não é meta.

---

## 7. Estratégia de Concorrência e Segurança de Gradiente

O modelo de concorrência real do B.I.O.M.A. é **cooperativo *single-thread***, e o plano o declara honestamente em resposta à crítica de engenharia. A coordenação — `sense`, `secrete`, `tick`, `divide`, `register` — executa toda no *event loop* `asyncio` (corotinas sem `await` interno nas seções críticas). O **único paralelismo real** é o cômputo por-célula (`metabolic_step`, `adapt`) despachado a um `ThreadPoolExecutor` *bounded*, operando sobre tensores de células **disjuntas**, e apenas na fração de tempo em que os *kernels* ATen liberam o GIL. Consequentemente, o `threading.Lock` do barramento é majoritariamente decorativo sob o modelo atual, e as defesas contra corridas de *threads* são calibradas como **guardas de robustez para evolução futura**, não como correção de um *race* ativo — exceto o `Semaphore` de orçamento, que resolve uma **corrida cooperativa real** (a reentrância de corotinas irmãs entre a checagem de orçamento e o `divide` subsequente no `gather`).

O **escalonamento** usa um `dag_scheduler` explícito (ready-set + join-counter): a fase de redução de um pai só dispara quando `pending[p]==0`. O teto de biomassa é um `asyncio.Semaphore(cell_budget)` com **reserva-antes-de-dividir** e *rollback*, substituindo a checagem não-atômica `live_count()+2 <= cell_budget` verificada nas linhas 455–460. A fila de telemetria é *bounded* (`asyncio.Queue(maxsize=Q)`) com *backpressure*, em modos *strict* (sem perda) e *lossy* (drop-oldest contabilizado), e a sentinela de fim jamais é descartada.

A **segurança de gradiente** é um requisito de engenharia de primeira classe, **não** uma propriedade biológica — nenhuma metáfora ajuda a diagnosticá-la. As regras invioláveis são: toda mutação estrutural ocorre **entre** passos de otimização, jamais durante um *backward*, sempre numa seção crítica síncrona **sem `await` interno**; os grafos de autograd são **disjuntos por célula** (parâmetros *leaf* próprios + alvos *detached*), invariante forçada por um *assert* de *ownership* pré-*backward* (todo tensor no grafo pertence a esta célula), com *fallback* para `adapt_executor(max_workers=1)` se *ownership* cruzada surgir; `retain_graph` permanece `False` no caso normal; e o *deep-copy* de dados *detached* na mitose corta a fita do autograd entre pai e filho. A disciplina de *locks* impõe **no-await-under-lock** e ordem total (bus *lock* sempre o mais interno, único por bus), tornando o grafo de espera acíclico por construção e o *deadlock* impossível.

Sobre paralelismo em CPU-only, o plano é honesto quanto ao teto de Amdahl: `speedup ≤ 1/((1−f) + f/p)`, com `f` = fração em *kernels* que soltam o GIL e `p` = *workers*. Para MLPs pequenos, `f` é baixo e o *speedup* é sublinear; a alavanca correta é **aumentar `f`** por *batching* de células irmãs, não aumentar `p`. Usa-se `torch.set_num_threads(1)` (evita *oversubscription* e o *crash* de *teardown* OpenMP no Windows), `_MAX_WORKERS = clamp(2, 8, cpu−2)` e `atexit shutdown(wait=True, cancel_futures=True)`.

---

## 8. Verificação, Telemetria, Auto-Correção e Definição de "100% de Sobrevivência Computacional"

A observabilidade precede a validação: a telemetria e a definição de sobrevivência devem existir e ser confiáveis **antes** de qualquer conclusão experimental. O núcleo é o esquema **`BioEvent`** (JSONL append-only, `seq` monotônico global via contador atômico, `t_mono`, `event_type`, `cell_id`/`parent_id`/`root_id`, `dag_depth`, `device`, `payload`, `energy_level`, `entropy`), emitido por *hooks* não-invasivos nos pontos de vida celular (`CELL_SPAWN`, `MITOSIS_TRIGGER`, `ENERGY_TICK`, `HORMONE_WRITE/READ`, `REPRESENTATION_TRANSFER`, `APOPTOSIS`, `ANOMALY`, `REPAIR_ACTION`). O *sink* JSONL é a fonte única de verdade; o dashboard é um consumidor derivado que reconstrói o DAG como *trace* e agrega células ativas `A(t)`, gatilhos de mitose, `burn_rate` por sub-agente, profundidade/largura do DAG e `conv_score`.

### 8.1 Definição operacional de "100% de sobrevivência computacional" (CSR)

A **Taxa de Sobrevivência Computacional** é definida de forma falsificável como a fração de células que atravessam o ciclo de vida completo satisfazendo a conjunção de invariantes:

`survive(c) = healthy_forward(c) ∧ no_nan_inf(c) ∧ transfer_ok(c) ∧ clean_apoptosis(c) ∧ no_leak(c) ∧ no_race(c)`

Crucialmente, "sobrevivência" significa **ausência de necrose** (nenhum *crash*/OOM não-programado) e **ausência de vazamento acima de tolerância calibrada** — **NÃO** ausência de apoptose, que é saudável e esperada. Em resposta às críticas de fragilidade estatística e de ruído de alocador, o critério terminal **não é igualdade exata sobre processo estocástico**. Adota-se:

- **Critério primário estatístico:** `CSR ≥ 1−ε` com limite inferior do intervalo de Wilson ≥ um limiar declarado, sobre um denominador **N de nascimentos explicitamente declarado** na suíte S; ou, equivalentemente, `CSR = 1,0` condicionado a que **toda** terminação `< 1,0` seja classificada como necrose genuína por um segundo oráculo **independente-de-tolerância** — o cruzamento `gc.get_objects` (contagem de `NeuralOrganism` vivos == 0).
- **Critério de vazamento:** substitui-se "retorno a *baseline* ±1%" (inatingível em CPU por ruído do alocador) por **ausência de tendência de crescimento no *soak*** (inclinação `b ≤ b_max` com `p ≥ 0,05` sobre N ciclos) **mais** o cruzamento `gc` independente de tolerância. As tolerâncias `τ_mem`/`τ_vram`/`τ_rss` são calibradas empiricamente da distribuição de resíduo de *baseline*, não fixadas como números mágicos.

### 8.2 Loop de auto-correção

O *loop* é um controlador OODA de **seleção-de-patch sobre um catálogo finito e determinista** (nunca geração de código por LLM no caminho de validação): executa o harness, classifica o sintoma entre as 8 classes, localiza módulo e causa via *trace*, aplica o patch de maior prioridade (correção estrutural auditável, **jamais** supressão cega de exceção ou *cast* forçado de *shape*), e re-verifica. Cada `REPAIR_ACTION` é logada como `BioEvent`. A guarda de regressão re-roda a suíte S completa após cada patch e verifica `conv_score` em paralelo ao CSR — uma célula que "sobrevive" mas não contribui para a convergência é sinalizada, prevenindo sobrevivência espúria. O critério de parada é honesto: FIXPOINT ou esgotamento de `max_repair_iter`, caso em que se emite um **relatório de falha com o menor contraexemplo** (via *shrinking* do Hypothesis), jamais declarando "100%" falso.

---

## 9. Metodologia Experimental

A metodologia atribui causalmente qualquer ganho aos mecanismos biológicos, evitando *p-hacking* estrutural. O desenho é **fatorial 2×2** cruzando mitose {on, off} × barramento {on, off}, com K réplicas por condição dimensionadas por **análise de poder a priori** (poder ≥ 0,8 para um tamanho de efeito pré-declarado), *seed_grid* para robustez, e dados/hiperparâmetros fixos. Computam-se o efeito da mitose, o efeito do barramento e o termo de interação sobre as métricas primárias (`conv_score`, CSR) e secundárias (energia total, latência, profundidade do DAG).

Os **baselines** de controle são o agente monolítico (sem mitose) e o enxame-sem-hormônio (mitose sem barramento). Em resposta à crítica de **circularidade do benchmark**, a metodologia inclui obrigatoriamente cenários onde a estrutura de domínio varia de forma cega ao sistema: **uni-domínio** (`K=1`, onde dividir é errado e a supressão de mitose é o sucesso), `K` desconhecido, e **adversariais** (domínios acoplados que exigem representação conjunta). A **matriz de confusão da decisão de mitose** é métrica primária de honestidade — sem cenários onde dividir é errado, não há como falsificar a utilidade da mitose. A **análise de identificabilidade** reporta `cos(síntese, P_médio)` (baseline trivial) ao lado de `cos(síntese, S*)` e varre `γ` para demonstrar que a margem sobre o monolítico cresce com o acoplamento — caso contrário, "convergência" seria artefato de `γ` pequeno.

A **análise estatística** usa o teste apropriado à normalidade (Welch t / Mann-Whitney), reporta tamanho de efeito (Cohen d / Cliff δ) e IC 95% por *bootstrap*, e aplica correção para múltiplas comparações (Holm-Bonferroni / Benjamini-Hochberg). As **ablações** internas incluem os pesos `w1..w4` de `D` (robustez da decisão de mitose), o coeficiente `κ` de incerteza (incluindo `κ=0` e `κ<0`, provando que o termo não é decorativo) e o acoplamento `γ`. A **reprodutibilidade** exigida é **lógica** (mesmas decisões, mesma topologia, mesmo veredicto); a numérica bit-a-bit é *best-effort*, atingível apenas sob execução serial (`max_workers=1`) nos *runs* de validação, com tolerância de métricas derivada empiricamente do *jitter* de ponto flutuante. As hipóteses são **pré-registradas internamente** antes de rodar, para evitar HARKing.

---

## 10. Registro de Riscos

| Risco | Severidade | Mitigação |
|---|---|---|
| *Overclaiming* científico (apresentar como "vida"/"organismo autônomo" o que é MoE + *pruning*) | Alta | Vocabulário duplo obrigatório; documento canônico Metáfora↔Mecanismo (Fase 0); Glossário de Fronteiras; revisão anti-*overclaim* na Fase 9 com contagem-alvo 0; declarar crescimento como decisão de roteador, não emergência. |
| Instabilidade de gradiente na edição topológica dinâmica | Alta | Mutação só entre passos, nunca durante *backward*; grafos disjuntos por célula forçados por *assert* de *ownership*; `retain_graph=False`; *deep-copy* *detached*; testes gradiente paralelo vs. serial. |
| Vazamento de memória por referências residuais (*hooks*, ciclos pai↔filho, ativações presas ao autograd) | Alta | Ordem canônica de apoptose em `try/finally`; `weakref` nos links do DAG; `handle.remove()` em todos os *hooks*; verificador anti-vazamento de 3 modos + cruzamento `gc`; *soak* com regressão de tendência; `N_max_hard`. |
| *Race conditions* e não-determinismo do pipeline assíncrono | Média | Modelo de concorrência declarado honestamente (cooperativo *single-thread*); `Semaphore` para a corrida cooperativa de orçamento; no-await-under-lock; determinismo assíncrono por ordenação canônica; probe de *race* *read-after-write*; validação serial na Fase 9. |
| Metáfora energética mal calibrada (apoptose prematura ou proliferação descontrolada) | Alta | Energia ancorada em proxy mensurável (FLOPs+tokens); histerese (`τ_up/τ_down`, `N_estab`); teto de FLOPs e `N_max_hard`; regeneração por progresso; **renomear "conservação" para auditoria de contabilidade**; declarar energia como orçamento não-conservativo. |
| Alvo "100% de CSR" mal definido | Alta | Definição operacional falsificável (Fase 7); "sobrevivência" ≠ ausência de apoptose; **critério estatístico** (`CSR ≥ 1−ε`, Wilson, N declarado); tolerâncias calibradas; cruzamento `gc` independente de tolerância; tendência no *soak*. |
| *Loop* de auto-correção mascarando bugs | Alta | Catálogo restrito a correções estruturais auditáveis; **atuador finito e determinista, não LLM**; guarda de regressão re-rodando S; `conv_score` verificado em paralelo ao CSR; `REPAIR_ACTION` logada; relatório de falha honesto com menor contraexemplo. |
| Benchmark circular/trivial (monolítico resolve tudo; *ground-truth* vaza) | Alta | **Cenários uni-domínio e adversariais onde dividir é errado**; matriz de confusão da mitose como métrica primária; análise de identificabilidade (`P_médio` vs. `S*`; varredura de `γ`); baselines com margem > 2σ; `S*` *detached*, fora do grafo. |
| Métrica `D` mal-condicionada (silhueta circular, escalas incompatíveis, "entropia de tópicos" sem modelo) | Média | Silhueta computada sobre a partição candidata (não antes); normalização explícita [0,1] por sinal; "entropia de tópicos" substituída por `cluster_mass_entropy`; ablação de `w1..w4` provando robustez. |
| Mitose citada como Net2Net mas mecanismo é MoE | Média | Corrigir a citação (roteamento por *clusters* = MoE, não Net2Net); declarar `‖f_após−f_antes‖<1e−5` como **sanidade de *deep-copy***, não propriedade de identidade; adicionar critério de **diferenciação efetiva** pós-*adapt*. |
| Reprodutibilidade bit-a-bit sob concorrência (frágil) | Média | Rebaixar bit-a-bit a *best-effort*; exigir determinismo **lógico**; validação serial (`max_workers=1`); tolerância empírica (1e−4 a 1e−3); *generators* dedicados em *kmeans* e mutação; `seed_everything` estendido a `numpy`/`random`. |
| Bug em `absorb()` (`normalize(v)·‖v‖` é *no-op*; memória herdada cresce sem limite) | Média | Incluir como 7º defeito no inventário (Fase 0); unificar o caminho de *merge* com LERP/SLERP de α limitado; testar norma de `inherited_memory` limitada ao longo de N absorções. |
| Explosão de custo em CPU-only (*deep-copy* de *state_dicts*, muitas células) | Média | Tetos de população (`cell_budget=24`, `N_max_hard`) e profundidade (`max_depth=2`); apoptose por exaustão como controle de população; `set_num_threads(1)`; *batching* de irmãs; perfis *smoke*/*severe* escalonáveis; telemetria de custo para abortar antes de *swap*. |
| Cronograma otimista para 1–2 engenheiros; rigor sacrificado sob prazo | Baixa | Marco **MVSV** com pré-registro de hipóteses; *loop* de auto-correção rebaixado a *playbook* de patches manuais + re-verificação automatizada; *buffer* de 20–30%; *code freeze* antes da Fase 9. |
| *Observer effect* / *overhead* de telemetria | Média | Amostragem configurável de eventos de alta frequência; *flush* em lote; redação de tensores; medir *overhead* como métrica de primeira classe; validar que ligar/desligar não muda CSR. |
| **[Fase 10] `exec()` de código mutado no processo hospedeiro (segurança + isolamento)** | Alta | **Nunca `exec()`/`eval()` in-process** para variantes; execução em *subprocess* com `setrlimit`/*Job Objects*, *timeout* duro, ambiente restrito e sem rede; tratar toda variante como não-confiável. |
| **[Fase 10] *Overclaim* "a evolução descobriu O(N log N)"** | Alta | Declarar que mutação aleatória não descobre classe de complexidade; o ganho vem de *transform* AST do catálogo **ou** de proposta de LLM (conhecimento, não emergência); **rotular a origem** de cada variante; medir sucesso contra baseline de latência, não contra narrativa. |
| **[Fase 10] Erro de categoria: "queda de gradiente" em refatoração** | Média | Refatoração é busca discreta **não-diferenciável**, sem gradiente; remover toda linguagem de gradiente/autograd do módulo; auditoria estática como critério de aceitação. |
| **[Fase 10] Fitness com unidades incomensuráveis / gameável** | Média | Substituir soma ponderada ingênua por **objetivo lexicográfico** (correção como portão → latência normalizada → memória normalizada); latência = mediana de R repetições com *warm-up* descartado. |
| **[Fase 10] Reprodutibilidade vs. propostas de LLM (conflito com Fase 8)** | Alta | Propostas de LLM ficam em **modo não-reproduzível quarentenado**, fora do caminho de validação da Fase 9; o caminho reproduzível usa apenas *transforms* AST determinísticos do catálogo. |

---

## 11. Cronograma Consolidado e Marcos

O cronograma é sequenciado por dependências técnicas: núcleo antes de mitose; barramento antes de orquestração; energia/apoptose antes de *stress*; telemetria e *loop* de auto-correção antes da validação. A duração serial total é de aproximadamente **22–23 semanas**; com paralelização (Fases 1 e 2 concorrentes; rascunho do `BioEvent` antecipado), o caminho crítico comprime para **~19–20 semanas**. Recomenda-se *buffer* de 20–30% e um *checkpoint* de revisão ao fim de cada fase contra seus critérios de aceitação testáveis.

| Fase | Janela (semana) | Duração | Depende de |
|---|---|---|---|
| 0 — Estabilização, auditoria, andaimes | 1–2 | 1,5–2 sem | — |
| 1 — Núcleo NeuralOrganism | 2,5–4,5 | 2 sem | 0 |
| 2 — Barramento Hormonal *(paralela à 1)* | 2,5–4,5 | 2 sem | 0 |
| 3 — Motor de Mitose | 4,5–7 | 2,5 sem | 1, 2 |
| 4 — Homeostase/Energia/Apoptose | 7–9,5 | 2,5 sem | 1, 3 |
| 5 — Orquestração/Escalonador | 9,5–11,5 | 2 sem | 2, 3, 4 |
| 6 — Harness/SSG | 11,5–14 | 2,5 sem | 1–5 |
| 7 — Telemetria/CSR | 14–16 | 2 sem | 1–6 |
| 8 — Loop de Auto-Correção | 16–18,5 | 2,5 sem | 6, 7 (+ 3 lacunas altas congeladas) |
| 9 — Validação Experimental/Consolidação | 18,5–21 | 2,5 sem | 0–8 |
| **10 — Trilha de Extensão: Coder Evolutivo** *(opcional, pós-M8)* | 21–24 | ~3 sem | 3, 4, 5, 7, 8 + *code-freeze* |

> A Fase 10 é uma **extensão opcional**: o projeto-base conclui-se em M8 / Fase 9. Se ativada, adiciona ~3 semanas ao caminho crítico (janela 21–24), preservando o *code-freeze* da validação estatística.

**Marcos:**

- **M1 (fim Sem. 2):** Base estável, esqueleto auditado, contratos de honestidade e de Φ escritos, registro de limiares criado.
- **M2 (fim Sem. 4,5):** Núcleo e barramento endurecidos e testados isoladamente; cinco defeitos verificados corrigidos; mini-portão de integração núcleo↔barramento verde.
- **M3 (fim Sem. 9,5):** Ciclo de vida completo funcional (mitose→trabalho→apoptose→fusão) com auditoria de contabilidade e apoptose sem vazamento; matriz de confusão da mitose e diferenciação efetiva verificadas.
- **M4 (fim Sem. 11,5):** Orquestração concorrente sem *deadlock*/corrida-cooperativa, saída limpa no Windows.
- **M5 (fim Sem. 14):** Harness com *ground-truth* analítico, baselines e **cenários de controle onde dividir é errado**; análise de identificabilidade operante.
- **M6 (fim Sem. 16):** Telemetria estruturada + CSR operacionalmente definido, estatístico e calibrado.
- **M7 (fim Sem. 18,5):** *Loop* de auto-correção atinge o CSR-estatístico nos perfis *smoke* e *severe*; MVSV alcançado.
- **M8 (fim Sem. 21):** Validação fatorial 2×2 com efeito causal significativo; certificado de aceitação (CSR-estatístico replicado, critério de vazamento atendido, reprodutibilidade lógica confirmada, 0 *overclaiming*).
- **M9 (fim Sem. 24, opcional — Fase 10):** módulo `evolutionary_coder` operante — refatora um alvo lento em *subprocess* isolado, poda variantes por apoptose sem vazamento, promove o *transform* vencedor ao catálogo, e reporta latência original vs. evoluída, com a origem de cada variante rotulada e sucesso definido operacionalmente (não narrativamente).

Um **congelamento de código** (*code freeze*) precede a Fase 9, para que a validação estatística opere sobre uma versão estável e reproduzível.

---

## 12. Critérios de Conclusão / Definição de Pronto

O projeto é considerado **concluído** quando todas as condições abaixo são satisfeitas simultaneamente e certificadas por evidência auditável.

**Sobrevivência computacional.** O critério estatístico de CSR (`CSR ≥ 1−ε` com limite inferior de Wilson ≥ limiar, sobre N nascimentos declarados) é satisfeito na suíte canônica S, replicado em R execuções independentes, com zero ANOMALY não-recuperado e zero necrose (nenhum *crash*/OOM não-programado).

**Ausência de vazamento.** No *soak* prolongado, a inclinação de crescimento de RSS é não-significativa (`b ≤ b_max`, `p ≥ 0,05`); a contagem de `NeuralOrganism` vivos em `gc` retorna a zero (`_LIVE_CELLS → 0`) ao fim de toda *run*; e a população-viva do dashboard iguala a contagem `gc` (divergência zero → sem referência pendurada).

**Integridade de gradiente e contabilidade.** A contabilidade de energia/incerteza não altera gradientes (perda/grad COM == SEM dentro de tolerância); os grafos de autograd são disjuntos por célula; os gradientes de `adapt()` concorrente igualam os seriais; a **verificação de sanidade da divisão** (`‖f_após−f_antes‖<1e−5` antes de especialização) passa em 100% das divisões; e a **auditoria de contabilidade** de energia fecha com erro de ponto flutuante apenas.

**Utilidade demonstrada dos mecanismos.** O fatorial 2×2 mostra efeito causal significativo da mitose e do barramento após correção múltipla, com tamanho de efeito e IC 95% *bootstrap* reportados; a **matriz de confusão da decisão de mitose** demonstra disparo correto em multi-domínio e supressão correta em uni-domínio; e a análise de identificabilidade confirma que a margem sobre o monolítico cresce com o acoplamento `γ`.

**Reprodutibilidade.** A reprodutibilidade **lógica** (mesmas decisões, mesma topologia, mesmo veredicto) é confirmada; a reprodutibilidade numérica é documentada honestamente como *best-effort* sob execução serial.

**Honestidade epistêmica.** Os 8 termos biológicos possuem mecanismo de engenharia, família técnica e nível de honestidade declarados; a contagem de afirmações não-qualificadas de vida/consciência/emergência/termodinâmica é 0; cada mecanismo central cita ≥ 1 família da literatura sem papers inventados; e as correções de nomenclatura desta versão (auditoria de contabilidade, mitose=MoE, comunicação por consistência eventual, incerteza≠entropia física) estão refletidas em código, logs, telemetria e documentação.

**Agnosticismo de dispositivo e saída limpa.** A suíte inteira passa em CPU-only Windows/Python 3.12 sem dependência CUDA obrigatória; `empty_cache` é condicional a `is_available()`; o *overhead* de telemetria e de contabilidade fica abaixo do limite acordado; e o harness sai com exit code 0 em execuções consecutivas repetidas, sem *crash* de *teardown* OpenMP.

**Extensão — Coder Evolutivo (Fase 10, se ativada).** O módulo `evolutionary_coder` é considerado pronto quando: gera N variantes **rotuladas por origem** (AST-determinística vs. LLM-quarentena); executa cada variante em *subprocess* isolado com *timeout* e limites de recurso, **jamais** via `exec()` in-process; avalia fitness **lexicográfica** (correção como portão duro → latência mediana de R repetições → delta de RSS); poda variantes sub-limiar por apoptose com liberação verificada e zero processo zumbi; promove o *transform* vencedor ao catálogo determinista da Fase 8 (não "aprende o conceito de código limpo"); e reporta latência original vs. evoluída com sucesso definido operacionalmente (variante correta com latência ≤ (1−δ)·original em ≥ X% dos alvos do *benchmark*), **sem** afirmar que a evolução "descobriu" uma classe de complexidade. O caminho reproduzível (só AST) satisfaz a reprodutibilidade lógica; o caminho de LLM permanece fora da validação estatística.

Satisfeitas todas estas condições sobre uma base congelada e reproduzível, o B.I.O.M.A. deixa de ser uma demonstração com verniz biológico e passa a constituir um estudo defensável de orquestração dinâmica de agentes com honestidade epistêmica exemplar.