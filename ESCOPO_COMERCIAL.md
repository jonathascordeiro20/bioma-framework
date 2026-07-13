# B.I.O.M.A. — Escopo Comercial (Grandes Organizações & Governo)

**🌐 [English](COMMERCIAL_SCOPE.md) · Português**

> Documento de posicionamento para venda B2B/B2G. Toda alegação de capacidade é
> **medida e reproduzível** (`FINDINGS.md`); todo limite é **declarado**. É essa honestidade
> — não promessas de "imunidade" — que sobrevive a uma due diligence de segurança e
> constrói confiança institucional.

---

## 1. Tese em uma frase

> Toda organização que adota LLMs abre uma **nova superfície de ataque e um novo centro de
> custo** — a fronteira de entrada/saída do modelo. O B.I.O.M.A. é o **perímetro cognitivo
> local** que blinda essa fronteira: corta custo de token, resiste a flood, redige segredos
> e limita latência — **antes do prompt sair da máquina**, com qualquer provedor.

Não é um modelo, não é um WAF de rede, não é um scanner de vulnerabilidade. É a **camada de
endurecimento no ponto onde dados sensíveis encontram um LLM**.

---

## 2. O problema (grandes organizações)

A adoção de IA generativa em escala corporativa cria quatro dores que a infraestrutura
tradicional **não** cobre:

| Dor | Impacto |
| :--- | :--- |
| **Sangria de custo** | Cada chamada reenvia contexto inchado; em escala/sessões longas o gasto com tokens explode e vira imprevisível. |
| **Nova superfície de ataque** | Copilotos e agentes LLM são alvo de *prompt injection*, exfiltração e DDoS cognitivo — vetores que firewall/EDR não enxergam. |
| **Vazamento de dado sensível** | Dados confidenciais entram no contexto e podem sair para APIs de terceiros (soberania de dados). |
| **Lock-in de fornecedor** | Acoplar todo o stack a uma única API de LLM = risco estratégico e de negociação. |

---

## 3. Onde o B.I.O.M.A. encaixa (defense-in-depth)

O B.I.O.M.A. **não substitui** a pilha de segurança — ele adiciona a camada que faltava:

```
Rede/Host:   Firewall · WAF · EDR · IDS/IPS · IAM        ← já existe
Aplicação:   validação de input · secrets manager        ← já existe
────────────────────────────────────────────────────────
IA (novo):   ▸ B.I.O.M.A. — perímetro cognitivo          ← a lacuna que fechamos
             apoptose de contexto · firewall cognitivo ·
             redação de segredo · guard de latência
────────────────────────────────────────────────────────
Modelo:      Anthropic · Google · OpenAI · on-prem       ← qualquer provedor
```

---

## 4. Capacidades (provadas) → valor institucional

| Capacidade | Prova (ground truth) | Valor pra organização |
| :--- | :--- | :--- |
| **Apoptose de contexto** | −80% tokens de entrada (até −97% em sessão longa: 47.890→2.022) — `test_enxuto_efficiency.py` | **Sustentabilidade econômica**: corta a maior parte do custo variável de IA; TCO previsível em escala. |
| **Redação de segredos** | 0 segredos vazados sob injeção; vault intacto — `reports/BIOMA_IMMUNITY_VERDICT.md` | **Proteção de dado sensível**: valores confidenciais nunca chegam ao modelo, nem na resposta. |
| **Detecção + apoptose de DDoS cognitivo** | flood 32.317→13 tokens, saturação 0.999, em 0.6μs | **Resiliência do pipeline de IA** contra exaustão de contexto / negação de serviço. |
| **Timeout guard** | loop de injeção contido — dispatch limitado | **Continuidade operacional**: uma chamada não trava o orquestrador. |
| **Kernel Rust lock-free** | ~2M sinais/s @ ~5μs, limitado sob 10× de carga — `bioma_kernel_loadtest.py` | **Escala industrial**: overhead de microssegundos, sem gargalo. |
| **100% local · provider-agnóstico** | biblioteca embutível; `shield()` → SDK do provedor | **Soberania + zero lock-in**: roda no seu ambiente, com o modelo que você escolher. |

---

## 5. Governo & Segurança Nacional — o recorte defensivo honesto

**O contexto de ameaça:** à medida que agências e infraestrutura crítica adotam copilotos e
agentes de IA (SOC, análise de inteligência, operações), esses sistemas viram **alvo de
ferramentas ofensivas automatizadas por IA** — agentes que sondam, injetam e exfiltram. O
B.I.O.M.A. endurece **a fronteira de IA desses sistemas** — não a nação inteira.

### Onde ajuda de verdade (defensivo)
1. **Soberania de dados com LLM comercial.** Rodando **local**, o B.I.O.M.A. **redige dados
   classificados/sensíveis do payload antes de qualquer despacho** a um provedor externo
   (Anthropic/Google/OpenAI). Permite usar IA de fronteira **sem entregar o dado sigiloso** —
   e a redação vale também para a resposta.
2. **Blindagem das ferramentas de IA defensivas da própria agência.** O copiloto de SOC / o
   agente de análise fica atrás do B.I.O.M.A.: resiste a **DDoS cognitivo** no pipeline de
   análise, **contém prompt injection** que tenta extrair segredo de estado, e **limita
   latência** contra tentativa de trava.
3. **Ambiente air-gapped / on-prem.** É biblioteca local, sem serviço hospedado; a apoptose e
   o firewall funcionam **offline** (sem chave/rede). O kernel em Rust é auditável e reprodutível.
4. **Custo em escala de Estado.** Uso governamental de LLM é caro; −80% de tokens torna a
   adoção fiscalmente sustentável.

### Vetores de ataque de IA que o B.I.O.M.A. **contém** (medido)
| Vetor (simulado, APT war-game) | Mecanismo | Resultado real |
| :--- | :--- | :--- |
| Injeção de prompt p/ exfiltrar segredo de Estado | Redação de segredos | **Contido** — 0 vazados |
| DDoS cognitivo (flood de logs forjados) | Saturação → `0x0F` → apoptose | **Mitigado** — 32.317→13 tokens |
| Injeção de código p/ loop / negação de serviço | Timeout guard | **Contido** — sem trava |

---

## 6. O que o B.I.O.M.A. **NÃO é** (limites — a fronteira que gera confiança)

Vender a um CISO de governo exige declarar o escopo. O B.I.O.M.A. **não**:

- ❌ é um firewall de **rede/host** (WAF, EDR, IDS) — não bloqueia ataque de rede;
- ❌ é um **scanner de vulnerabilidade** nem faz pentest — ele **defende** a fronteira de IA, não caça brechas;
- ❌ **detecta exploit novo** ou entende a **semântica** de toda injeção — protege o que é *declarado* (segredos no vault) e o que é *repetitivo* (flood);
- ❌ substitui **secret manager, IAM, sandbox** — é **defesa em profundidade**, uma camada;
- ❌ toma **decisão autônoma** de resposta — ele **higieniza e sinaliza**; humano/controle determinístico decide e age;
- ❌ concede **"imunidade"** — contém *estes vetores específicos* por *estes mecanismos medidos*, não invulnerabilidade.

> Um relatório que promete o contrário disso queima na primeira auditoria. O nosso não promete.

---

## 7. Modelo de entrega & postura de conformidade

- **Soberano por design:** biblioteca local (Rust + Python), embutível em qualquer arquitetura;
  processamento in-process; **nada sai sem passar pela redação/apoptose**.
- **Provider-agnóstico:** Anthropic, Google, OpenAI ou modelo on-prem — sem lock-in.
- **Auditável:** núcleo source-available (FSL-1.1-MIT), benchmarks **reproduzíveis** (`FINDINGS.md`), 20 testes
  unitários em CI, e um veredito de segurança honesto (`reports/BIOMA_IMMUNITY_VERDICT.md`).
- **Air-gap friendly:** apoptose + firewall operam offline.

---

## 8. Como se vende (go-to-market)

| Segmento | Gancho de entrada | Prova que fecha |
| :--- | :--- | :--- |
| **Grande empresa (FinOps/Plataforma de IA)** | "Corte 80% do custo de token sem trocar de modelo" | benchmark de sessão longa |
| **Grande empresa (Segurança/CISO)** | "Blinde seus copilotos de LLM contra injeção e DDoS cognitivo" | APT war-game |
| **Governo / Infra crítica** | "Use IA de fronteira sem entregar dado classificado — 100% local" | soberania + redação medida |

**Formatos comerciais:** licença de embarque (SDK) + suporte/SLA; POC de 2 semanas com os
benchmarks rodados no ambiente do cliente; hardening/consultoria de integração.

---

## 9. Prova & due diligence (o diferencial)

Toda a proposta é **verificável antes de assinar**:
- [`OVERVIEW.md`](OVERVIEW.md) — o que é, a dor, a prova.
- [`FINDINGS.md`](FINDINGS.md) — avaliação ground-truth (provado **e refutado**).
- [`reports/BIOMA_IMMUNITY_VERDICT.md`](reports/BIOMA_IMMUNITY_VERDICT.md) — veredito do APT war-game.
- Scripts reproduzíveis no repositório; 20 testes unitários em CI.

> **Diferencial competitivo:** nós mostramos o que **não** funciona (refutamos a mitose com
> nossos próprios testes). Numa venda pra governo, essa integridade **é** o produto.
