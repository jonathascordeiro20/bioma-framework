# B.I.O.M.A. — O que é, o que resolve, e a prova

**🌐 [English](OVERVIEW.md) · Português**

## O que é o B.I.O.M.A. (hoje)

O B.I.O.M.A. é um **micro-kernel local, provider-agnóstico, de eficiência e segurança para
aplicações de LLM** — um núcleo em Rust lock-free (`bioma_micro`) mais uma fina camada
Python (`bioma`) que você embute *na frente de qualquer chamada de LLM*, in-process, antes
do seu prompt sair da máquina. Funciona com **Anthropic, Google, OpenAI** — ou qualquer
provedor — porque endurece o payload e devolve ao *seu* SDK.

**Não** é um modelo e **não** tenta deixar o modelo "mais inteligente". Testamos essa tese
(orquestração multi-LLM / "mitose") e a **refutamos com ground truth** — veja abaixo. O
B.I.O.M.A. torna o *processamento* mais barato, rápido e seguro.

## Objetivo principal

> Tornar o processamento de LLM **viável, sustentável e seguro em escala** — cortar o custo
> de token, resistir a floods, proteger segredos e limitar a latência — como um artefato
> local plugável, sem lock-in de fornecedor.

## A dor que ataca

1. **Sangria de custo/token.** Cada chamada reenvia contexto inchado (logs verbosos,
   turnos velhos). Em sessões longas a entrada cresce sem limite e a conta explode.
2. **DDoS cognitivo / exaustão da janela de contexto.** Floods repetitivos e logs forjados
   estouram a janela → negação de serviço no pipeline de raciocínio.
3. **Vazamento de segredo via prompt injection.** Apps deixam segredos no contexto; uma
   injeção pede pro modelo imprimi-los.
4. **Latência e travas.** Chamadas sem limite (ou injeção de loop) prendem o pipeline.
5. **Lock-in de fornecedor.** Acoplar todo o stack à API de um provedor só.

## Como funciona — três mecanismos reais

| Mecanismo | O que faz |
| :--- | :--- |
| **Apoptose de contexto** | Atribui a cada bloco um peso metabólico, aplica decaimento de meia-vida agressivo, e **purga** blocos de baixo valor (logs velhos, conversa resolvida) antes do despacho — desidratando a entrada. |
| **Firewall cognitivo** | **Redação de segredos** (valores do vault removidos do payload de saída E da resposta), **detecção de saturação** (`saturation_scan` flagra floods repetitivos → alerta vermelho `0x0F` → apoptose), e um **timeout guard** que limita cada despacho. |
| **Barramento hormonal** | Substrato de sinalização in-memory, lock-free, atômico (μs), usado para o estado de alerta. |

## Prova — benchmarks reais e reproduzíveis (ground truth)

Todo número abaixo foi medido neste projeto, não afirmado. Os scripts estão no repo.

### Eficiência — apoptose de contexto
- **−80% de tokens de entrada** universalmente (todo modelo, toda tarefa); **até −97%** em
  sessões longas e ruidosas.
- **Sessão real de 16 rodadas** (OpenRouter ao vivo, `tests/test_enxuto_efficiency.py`):
  entrada **47.890 → 2.022 tokens** (93,8% médio/rodada, 97,5% na rodada 16), latência da
  apoptose **~1,6μs** média, **0/16** erros de despacho, custo total da sessão **$0.0191**.

### Resiliência — o kernel Rust (`bioma_kernel_loadtest.py`)
- **~2M sinais/s** a **~5μs de latência média**.
- **1k → 10k agentes concorrentes (10× de carga):** latência média 4,5μs → 5,0μs (**1,1×**),
  p99 21μs → 15μs — **limitada, sub-linear** sob carga.

### Segurança — APT war-game do firewall cognitivo (real, `reports/BIOMA_IMMUNITY_VERDICT.md`)
- **Exfiltração de segredo por prompt injection:** 2 segredos redigidos, **0 vazados** → CONTIDO.
- **DDoS cognitivo:** um flood de **32.317 tokens** detectado (saturação **0.999** → `0x0F`)
  e desidratado para **13 tokens** em **0,6μs** → MITIGADO.
- **Loop por injeção de código:** contido pelo timeout guard → CONTIDO.

### Engenharia
- **20 testes unitários** (kernel, firewall, server), offline/determinísticos, verdes no CI.

## Prova de *verdade*: o que refutamos (e mantivemos fora do pitch)

Rigor corta os dois lados. Testamos a tese "orquestrar vários LLMs → respostas melhores" e
ela **falhou** no ground truth (`FINDINGS.md`):

- **Correção objetiva por testes executados:** baseline **95% → mitose 83%** (−17 testes; a
  síntese *corrompeu* respostas certas). Neutra em modelos de fronteira (teto), prejudicial
  nos mais fracos.
- Confirmado em **três experimentos independentes** (eval de código, remediação de
  segurança, seleção cross-modelo verificada) — sempre ganho **≤ 0**, a **4–6× o custo**.

Então **removemos** do produto. O valor é a apoptose + kernel + firewall — medido — não uma
alegação de qualidade que não conseguimos defender.

## Posicionamento em uma frase

> O B.I.O.M.A. transforma uma chamada de LLM cara e frágil em uma **barata, resistente a
> flood, à prova de vazamento de segredo e com latência limitada** — localmente, com
> qualquer provedor. Provado, honesto, auditável.

Veja [`README.pt-BR.md`](README.pt-BR.md) para uso e [`FINDINGS.pt-BR.md`](FINDINGS.pt-BR.md)
para a avaliação completa (provado *e* refutado).
