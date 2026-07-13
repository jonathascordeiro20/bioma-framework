# B.I.O.M.A.

**🌐 [English](README.md) · Português**

[![CI](https://github.com/jonathascordeiro20/bioma-framework/actions/workflows/ci.yml/badge.svg)](https://github.com/jonathascordeiro20/bioma-framework/actions/workflows/ci.yml)
[![Licença: FSL-1.1-MIT](https://img.shields.io/badge/licen%C3%A7a-FSL--1.1--MIT-blue.svg)](LICENSE)
![Feito com Rust + Python](https://img.shields.io/badge/feito%20com-Rust%20%2B%20Python-orange.svg)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Tokens economizados: até 97%](https://img.shields.io/badge/tokens%20economizados-at%C3%A9%2097%25-success.svg)

**Um micro-kernel local, provider-agnóstico, de eficiência e segurança para aplicações de LLM.**

O B.I.O.M.A. é um artefato plugável — um kernel em Rust lock-free (`bioma_micro`) mais uma
fina camada Python — que você embute em *qualquer* projeto ou arquitetura que fale com um
LLM. Ele não tenta deixar o modelo "mais inteligente". Ele torna o *processamento* mais
barato, rápido e seguro, in-process, antes do seu prompt sair da máquina:

- **Apoptose de contexto** — desidrata contexto desperdiçado/obsoleto (−80% de tokens de
  entrada; até −97% em sessões longas).
- **Firewall cognitivo** — redação de segredos, detecção de DDoS cognitivo/flood, e um
  timeout guard no despacho.
- **Barramento hormonal** — substrato de sinalização lock-free em μs (~2M sinais/s).

100% local. Provider-agnóstico: endureça o payload aqui e mande pra **Anthropic, Google,
OpenAI** — ou qualquer coisa — com o *seu* SDK.

> **Novo por aqui?** [`OVERVIEW.pt-BR.md`](OVERVIEW.pt-BR.md) explica o que é o B.I.O.M.A., a
> dor que ele ataca, e os benchmarks reais como prova. Para posicionamento corporativo e
> governamental, veja [`ESCOPO_COMERCIAL.md`](ESCOPO_COMERCIAL.md); mapa competitivo Brasil em
> [`MARKET_BRAZIL.pt-BR.md`](MARKET_BRAZIL.pt-BR.md); ROI e modelo de custo em
> [`BUSINESS_CASE.pt-BR.md`](BUSINESS_CASE.pt-BR.md); implantação passo a passo (modelos locais
> e online) em [`IMPLEMENTATION.pt-BR.md`](IMPLEMENTATION.pt-BR.md). Toda alegação é medida e auditada em
> [`FINDINGS.pt-BR.md`](FINDINGS.pt-BR.md), inclusive o que testamos e **refutamos** (a
> "mitose" multi-LLM não melhora qualidade — não faz parte do produto).

## Use como biblioteca (qualquer provedor)

```python
from bioma.firewall_client import CognitiveFirewall

fw = CognitiveFirewall(vault={"db_password": DB_PW})   # segredos a proteger

# (a) artefato PURO — endureça e chame SEU provedor com SEU SDK:
h = fw.shield(history, "refatore esta função")
#   h.prompt / h.system  → payload limpo, desidratado, sem segredo
#   h.telemetry          → saturação, red_alert, apoptosis_reduction, kernel_latency_us

import anthropic                                        # ou google.genai, ou openai
msg = anthropic.Anthropic().messages.create(
    model="claude-sonnet-5", max_tokens=1024,
    system=h.system or "", messages=[{"role": "user", "content": h.prompt}])

# (b) traga seu dispatcher async (Anthropic/Google/OpenAI), mantendo os guards:
shield = await fw.harden(history, "refatore", dispatch_fn=meu_provedor_async)
#   → timeout guard + redação de segredo na resposta, automáticos
```

O kernel Rust também é usável direto:

```python
import bioma_micro as k
k.dehydrate([("regras de sistema", k.SYSTEM), ("log verboso " * 200, k.TOOL)])  # → -80% tokens
k.saturation_scan(payload)     # score de DDoS cognitivo 0..1 (flood ≈ 1.0)
```

## Resultados provados (ground truth)

| Capacidade | Resultado | Fonte |
|---|---|---|
| Apoptose de contexto | **−80% tokens de entrada** (até −97% em sessão longa) | `tests/test_enxuto_efficiency.py` |
| Barramento hormonal | **~2M sinais/s @ ~5μs**, limitado sob 10× de carga | `bioma_kernel_loadtest.py` |
| Mitigação de DDoS cognitivo | flood de 15k tokens → desidratado antes do despacho | `tests/test_sovereign_defense.py` |
| Redação de segredos | valores do vault nunca chegam ao modelo | `reports/BIOMA_IMMUNITY_VERDICT.md` |

## Início rápido (local)

```bash
# Compile e instale o micro-kernel Rust (extensão PyO3)
python -m pip install maturin
cd bioma_micro && maturin build --release && \
  pip install --force-reinstall target/wheels/bioma_micro-*.whl && cd ..

# Rode a suíte de testes (offline, determinística)
pip install pytest fastapi "openai>=1"
python -m pytest tests/test_kernel.py tests/test_firewall.py tests/test_server.py -q
```

Opcional: um runner FastAPI local (`bioma.server`, `GET /health` + `POST /v1/dispatch`) e
uma imagem de container local (`deploy/Dockerfile.lean`) estão inclusos — sem serviço
hospedado.

## Estrutura

```
bioma_micro/   micro-kernel Rust/PyO3 — barramento hormonal + apoptose + saturation_scan
bioma/         Python: CognitiveFirewall, LeanOpenRouterClient, servidor local
tests/         suíte unitária (kernel, firewall, server) + validações reais end-to-end
FINDINGS.md    avaliação ground-truth (provado / refutado), reproduzível
reports/       veredito de imunidade (APT war-game)
```

> Camadas legadas (`bioma_orchestrator/`, `bioma_kernel/`) permanecem só para reproduzir o
> `FINDINGS.md`; `bioma_micro` + `bioma` são o produto.

## Licença & edições

Fair-source. A **edição Community** (este repo — kernel, firewall, tudo que os benchmarks
provam) é source-available sob a **Functional Source License (FSL-1.1-MIT)**
([`LICENSE`](LICENSE)) — leia, execute, construa em cima; o único limite é reempacotá-la como
produto concorrente, e cada release vira MIT após dois anos. Uma **edição Enterprise** separada
(ferramentas soberanas/air-gapped, conformidade, admin, SLA) está disponível sob licença
comercial — veja [`EDITIONS.pt-BR.md`](EDITIONS.pt-BR.md).
