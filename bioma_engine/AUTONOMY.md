# B.I.O.M.A. — Garantia de Autonomia

**O B.I.O.M.A. opera de forma totalmente autônoma, sem intervenção nem
dependência de qualquer modelo externo, LLM, API de inferência hospedada ou
assistente.** O sistema é auto-contido e roda offline.

## O que isso significa (concretamente)

- **O único "modelo" é o próprio runtime local** — organismos `torch.nn.Module`
  determinísticos, instanciados e executados dentro do processo. B.I.O.M.A.
  **é** um modelo; ele não **chama** outro.
- **O otimizador de código é determinístico** — um catálogo de *transforms* AST
  (memoização, ajuste de constantes, …) executado em subprocessos isolados com
  timeout. **Não** há geração de código por LLM.
- **Nenhuma chamada de rede é necessária** para rodar o núcleo. Não há download
  de pesos, não há API externa, não há *harvesting* de internet. (O
  `DigitalForager` deriva um nutriente **offline** do próprio prompt.)
- **Zero referências a assistentes/fornecedores** (Claude, Anthropic, OpenAI,
  etc.) no código de runtime.

> A camada de rede existente é apenas **transporte** do próprio serviço:
> `server.py` (FastAPI) recebe requisições de entrada, e `tools/smoke_client.py`
> testa esse servidor local. Nenhuma delas contata um modelo externo.

## Como isso é verificado (garantia testável)

No espírito do projeto — toda garantia é testada — a autonomia é uma propriedade
**auditável**:

```bash
python -m bioma_engine.autonomy          # relatório de autonomia
python -m pytest -q bioma_engine/tests/test_integration_hook.py
```

`bioma_engine/autonomy.py` faz uma varredura estática de todo o pacote e falha se
encontrar:

- import de qualquer biblioteca de modelo/LLM/inferência de terceiros
  (`openai`, `anthropic`, `transformers`, `langchain`, `ollama`, …);
- qualquer token de fornecedor/assistente no código-fonte.

O próprio módulo de auditoria é o **único** lugar onde esses nomes aparecem — por
necessidade, como *denylist* — e ele se exclui da varredura.

**Veredito atual:** `FULLY AUTONOMOUS ✓` — 16 arquivos varridos, 0 violações,
`network_required_to_run_core = False`.

## Dependências (todas locais, nenhuma é um modelo externo)

| Pacote | Papel |
|---|---|
| `torch` | runtime neural **local** (o próprio organismo) |
| `numpy`, `scipy` | estatística da validação 2×2 |
| `networkx` | DAG de linhagem |
| `psutil` | telemetria de memória / apoptose |
| `fastapi`, `uvicorn`, `pydantic` | transporte HTTP do próprio serviço |
| `httpx`, `hypothesis`, `pytest` | testes (do próprio servidor local) |

Nenhuma delas é um serviço de modelo externo. O sistema roda de ponta a ponta em
CPU, offline, determinístico e reproduzível.
