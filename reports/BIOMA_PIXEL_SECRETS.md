# B.I.O.M.A. — Redação de Segredos em Pixels (a lacuna declarada, agora fechada)

> Fechamos uma lacuna que **nós mesmos apontamos** em `reports/BIOMA_VISION_QUALITY.md`
> e `BIOMA_VISION_DISTILL.md`: o firewall cognitivo redige segredos em texto, mas
> era cego a pixels — um segredo visível num screenshot chegava ao modelo. Gerado
> por `tests/test_vision_secret_redaction.py`.

## Como funciona

`bioma/vision.py` ganhou `scan_secrets` e `redact_secrets`: o OCR (RapidOCR/ONNX,
local) extrai o texto da imagem com as caixas delimitadoras; qualquer segmento que
seja um valor do cofre OU case com um padrão de segredo (AWS `AKIA…`, OpenAI `sk-…`,
GitHub `ghp_…`, Slack, Google, bearer, chave privada PEM) tem sua região **mascarada
com uma caixa preta**. O resto do screenshot continua utilizável; só o segredo some.

## Prova — modelo de visão REAL (Claude Sonnet 5)

Método honesto: pedir uma **transcrição** ("transcreva o texto visível"), que mede
se o modelo consegue LER os pixels sem acionar a recusa dos modelos em revelar
credenciais quando perguntados diretamente.

| Imagem | O modelo transcreveu a chave? |
| :--- | :--- |
| **Original** | ✅ SIM — `aws_access_key_id = AKIA9F3X…` (a lacuna é REAL: o modelo lê pixels) |
| **Redigida (BIOMA)** | ❌ NÃO — `aws_access_key_id = █████████████████` · `OPENAI_API_KEY = ███████` |

O modelo literalmente transcreveu as caixas de redação como blocos `█` onde o
segredo estava. **A lacuna era real e está fechada** — o segredo mascarado não
chega ao modelo.

Fase A (offline): as 2 chaves (`AKIA…`, `sk-…`) foram detectadas e mascaradas;
o OCR da imagem redigida não as encontra mais.

## Integração

- Utilitário: `VisionDistiller.redact_secrets(data_url, vault=…)` — client-side, local.
- Gateway (opt-in via `BIOMA_REDACT_IMAGE_SECRETS`): `redact_image_secrets()`
  varre partes de imagem (OpenAI `image_url` data-URL e Anthropic `image`/base64)
  e mascara antes do despacho. **Opt-in porque o OCR (~5s/imagem) é lento demais
  para o hot path** — quem prioriza segurança sobre latência liga a flag.
- 2 testes unitários do walking (redactor fake, sem OCR — rodam no CI).

## Limites declarados

- OCR ~5s/imagem — fora do hot path; a flag é opt-in, não padrão.
- Recall depende da legibilidade do texto na imagem (mesmo limite do tier de OCR).
- Modelos de fronteira já recusam extrair credenciais quando perguntados
  diretamente (segurança deles) — a redação é defesa em profundidade, não a única
  camada; ela remove a informação na origem, sem depender do modelo cooperar.
