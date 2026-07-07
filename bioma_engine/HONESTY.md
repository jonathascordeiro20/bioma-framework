# B.I.O.M.A. — Dicionário Canônico Metáfora ↔ Mecanismo

**Fonte única de verdade de nomenclatura** para código, logs e telemetria
(plano Fase 0). Cada termo biológico declara seu mecanismo de engenharia, a
família técnica correspondente e seu **nível de honestidade**:

- **N1** — mecanismo concreto verificável.
- **N2** — analogia funcional defensável.
- **N3** — licença criativa/narrativa (proibida sem qualificação).

| Termo biológico | Mecanismo de engenharia | Família técnica | Nível |
|---|---|---|---|
| **Mitose** | Instanciação de *k* filhos por *clustering* de embeddings + *deep-copy* de `state_dict` + roteamento condicional | MoE / redes crescentes | **N1** |
| **Stem cell** | Roteador/*gating* que mede dispersão/entropia de *clusters* e decide expandir | MoE *top-k* / NAS online | **N1** |
| **Divergência semântica / H(X)** | Escalar estatístico sobre a geometria de embeddings (dispersão + entropia espectral) | Teoria da informação / *clustering* | **N1** |
| **Homeostase** | Regulação de variável interna por *clamp* e realimentação proporcional | Controle proporcional | **N2** |
| **Energia** | Contador escalar de orçamento (proxy de FLOPs/tokens) + penalidade de incerteza | Computação condicional / *ponder cost* | **N2** |
| **Entropia (drenagem)** | Regularizador por incerteza de Shannon da saída | Regularização por entropia | **N2** |
| **Apoptose** | Poda estrutural + consolidação (*merge*) + liberação determinística de memória | *Pruning* + GC | **N1** |
| **Hormônio / exsudação** | Escrita/leitura EMA em tensor compartilhado; leitura por **atenção de cosseno verdadeiro** | Blackboard / estigmergia / atenção KV | **N1** |
| **Organismo** | DAG dinâmico de `nn.Module` editável em runtime | Grafo dinâmico *define-by-run* | **N1** |
| **Fissão/mutação de código** | *Transforms* AST determinísticos de um catálogo | Programação genética / síntese de programas | **N1 (AST)** |
| **Fitness** | Escalar **lexicográfico**: correção (portão) → latência → memória | Otimização multiobjetivo | **N1** |
| **Promoção ao catálogo** (ex-"destilação reversa") | Registro do *transform* vencedor num catálogo reutilizável | *Pattern mining* / atualização de biblioteca | **N2** |
| **Destilação (organismo→organismo)** | KD por gradiente entre `NeuralOrganism` (primitiva neural isolada) | *Knowledge distillation* | **N1** |
| **"Vida" / "consciência" / "emergência"** | — (sem referente mecânico) | — | **N3 — proibido sem qualificação** |

## Fronteiras epistêmicas (o que o B.I.O.M.A. NÃO é)

- **Não é termodinâmica.** A "energia" é um contador de recursos com fontes,
  sumidouros e *clamp* — **não obedece conservação**. O invariante auditável é
  *contabilidade* (ausência de dupla-contagem/*drift*), não conservação física.
- **Não é morfogênese emergente.** O crescimento é **decisão de um roteador por
  limiar** (paradigma MoE/NAS), não auto-organização de regra local (NCA).
- **Não é vida no sentido forte.** Os rótulos celulares são andaimes narrativos
  sobre operações tensoriais determinísticas.
- **A comunicação hormonal é *in-process* por consistência eventual** — elimina
  serialização texto/JSON, ao preço de *lock* + latência de *tick*; uma leitura
  enxerga o último *tick* consolidado, não o instante de escrita.
- **A "mitose" é MoE, não Net2Net.** A verificação `‖f_após−f_antes‖<1e−5` é
  **sanidade de *deep-copy***, não a garantia algébrica de identidade de Net2Net.

## Nota sobre o `evolutionary_coder`

Refatoração de código é **busca discreta não-diferenciável**: não há grafo de
autograd no módulo do Coder (auditável estaticamente). O ganho de latência vem
de *transforms* AST de um **catálogo determinístico** de origem rotulada — não de
"a evolução descobriu um algoritmo". A antiga "destilação reversa para a Stem
Cell" foi corrigida para **promoção do *transform* vencedor ao catálogo**
(N2), sem treinar rede alguma a partir do vencedor de código.
