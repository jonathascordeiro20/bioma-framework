# B.I.O.M.A. vs LLMLingua-2 — head-to-head auditável

> Mesmo dataset (probes objetivas de `test_quality_preservation.py`), mesmas métricas,
> mesmo template de prompt, temperatura 0.0, orçamento de compressão PAREADO
> (LLMLingua `target_token` = tokens pós-apoptose). LLMLingua-2: `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank`
> em `cpu`. Dados brutos: `resultados/llmlingua_h2h.json`.

| Cenário | Modelo | Braço | Probes | in_tok | vs baseline | compressão |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: |
| S1 | GPT-5.5 | baseline | 100% | 7,612 | — | — |
| S1 | GPT-5.5 | bioma | 100% | 193 | −97.5% | 0.04 ms |
| S1 | GPT-5.5 | llmlingua | 0% | 69 | −99.1% | 25,787.69 ms |
| S1 | Claude Sonnet 5 | baseline | 100% | 11,694 | — | — |
| S1 | Claude Sonnet 5 | bioma | 100% | 298 | −97.5% | 0.04 ms |
| S1 | Claude Sonnet 5 | llmlingua | 0% | 108 | −99.1% | 25,787.69 ms |
| S2 | GPT-5.5 | baseline | 100% | 7,083 | — | — |
| S2 | GPT-5.5 | bioma | 100% | 152 | −97.9% | 0.04 ms |
| S2 | GPT-5.5 | llmlingua | 0% | 37 | −99.5% | 24,092.57 ms |
| S2 | Claude Sonnet 5 | baseline | 100% | 10,893 | — | — |
| S2 | Claude Sonnet 5 | bioma | 100% | 244 | −97.8% | 0.04 ms |
| S2 | Claude Sonnet 5 | llmlingua | 0% | 64 | −99.4% | 24,092.57 ms |
| S3 | GPT-5.5 | baseline | 100% | 7,556 | — | — |
| S3 | GPT-5.5 | bioma | 0% | 119 | −98.4% | 0.05 ms |
| S3 | GPT-5.5 | llmlingua | 0% | 31 | −99.6% | 25,785.48 ms |
| S3 | Claude Sonnet 5 | baseline | 100% | 11,620 | — | — |
| S3 | Claude Sonnet 5 | bioma | 0% | 194 | −98.3% | 0.05 ms |
| S3 | Claude Sonnet 5 | llmlingua | 0% | 54 | −99.5% | 25,785.48 ms |

Custo total dos dispatches: $0.2066. Latência de decisão do kernel BIOMA: ~1 µs (Rust puro) vs compressão LLMLingua-2 em ordem de segundos (CPU).

Leitura honesta: LLMLingua comprime token a token (preserva conteúdo diluído em
qualquer posição); BIOMA purga blocos inteiros por classe+recência (µs, zero modelo).
S3 mede exatamente essa diferença de design — reporte-a, não a esconda.
