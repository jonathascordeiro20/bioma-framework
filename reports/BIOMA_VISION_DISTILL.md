# B.I.O.M.A. — Destilação de Imagens Complexas (fase local + LLMs reais)

> Gerado por `tests/test_vision_distill.py`. Fase A: análise local client-side
> (pHash + RapidOCR/ONNX, CPU) sobre 6 formas complexas. Fase B: dispatch real,
> braços baseline / purga (v1) / destilação (v2).

## Fase A — velocidade e recall por forma

| Forma | pHash | OCR (warm) | Recall | Tokens img→texto |
| :--- | ---: | ---: | :---: | ---: |
| dashboard denso | 3 ms | 3,414 ms | 3/3 | 1.600 → 50 |
| tabela/planilha | 3 ms | 4,261 ms | 2/2 | 1.600 → 86 |
| gráfico de barras | 6 ms | 2,885 ms | 2/2 | 1.600 → 28 |
| terminal escuro | 3 ms | 4,072 ms | 2/2 | 1.600 → 59 |
| documento | 3 ms | 3,979 ms | 2/2 | 1.600 → 73 |
| diagrama de formas | 4 ms | 3,764 ms | 3/3 | 1.600 → 25 |

## Fase B — LLMs reais (probes nas imagens antigas da sessão)

| Modelo | Braço | Probes | in_tok (usage) | Custo |
| :--- | :--- | :---: | ---: | ---: |
| GPT-5.5 | baseline | 100% | 11,016 | $0.0570 |
| GPT-5.5 | purge | 0% | 3,985 | $0.0282 |
| GPT-5.5 | distill | 100% | 2,816 | $0.0161 |
| Claude Sonnet 5 | baseline | 100% | 12,369 | $0.0250 |
| Claude Sonnet 5 | purge | 0% | 4,479 | $0.0100 |
| Claude Sonnet 5 | distill | 100% | 3,316 | $0.0069 |
| Gemini 3.1 Pro | baseline | 100% | 15,540 | $0.0393 |
| Gemini 3.1 Pro | purge | 0% | 5,602 | $0.0232 |
| Gemini 3.1 Pro | distill | 100% | 3,842 | $0.0161 |

Limites: OCR roda fora do hot path (lazy, uma vez por imagem); recall
depende da forma (medido acima); destilação é lossy para conteúdo
não-textual — caption por VLM local é o próximo tier.

## Achados (v2 — tier de estrutura determinística + dedup keep-latest)

1. **Paridade total recuperada: 100% nos 3 modelos** (antes: 66,7% em GPT-5.5 e
   Sonnet 5). A probe espacial (`NODE-A7` dentro do círculo) passou a ser
   respondida corretamente a partir do bloco destilado
   `estrutura do diagrama: círculo contém 'NODE-A7'; ...`.
2. **O tier de estrutura é determinístico** (OpenCV: contornos → fecho convexo →
   contagem fina de vértices; rótulos associados por continência das caixas do
   OCR) — ~3,5s/imagem, sem alucinação. O VLM local (Moondream 1.8B) foi testado
   e **rejeitado para rótulos exatos**: confabulou "NODE-7"/"NODE-8"
   (inexistentes) na descrição do diagrama — medido, não presumido.
3. **Dedup keep-latest** implementado (`VisionDistiller.dedup_keep_latest`):
   clusters por pHash mantêm o membro MAIS RECENTE (o estado novo de uma tela de
   monitoramento é o que vale), corrigindo a política keep-first da v1.
4. **Braço destilado: −74/75% de tokens vs baseline com 100% das probes** —
   e ainda abaixo do braço de purga, que perde as respostas (0%).
