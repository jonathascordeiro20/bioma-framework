# B.I.O.M.A. — Ganhos de Integração Universal (qualquer LLM · online & offline)

**🌐 [English](BIOMA_UNIVERSAL_GAINS.md) · Português**

> Tradução do relatório gerado por `tests/test_universal_integration.py`. Ground truth.
> O B.I.O.M.A. endurece o **payload**, não o modelo — então os ganhos são **model-agnósticos**
> e idênticos, esteja o LLM online (API) ou offline (on-prem).

**Eficiência model-agnóstica (medida no payload):** contexto de entrada **1.069 → 63 tokens
(−94%)** · kernel 0,8μs · segredo redigido da saída.

## Online — dispatch real (baseline vs B.I.O.M.A.)

| Modelo (online) | in_tok base→BIOMA | redução | custo base→BIOMA | segredo → provedor |
| :--- | :---: | :---: | :---: | :---: |
| GPT-5.5 | 1605→78 | −95% | $0.0113→$0.0029 | baseline **True** → BIOMA **False** |
| Claude Sonnet 5 | 2489→123 | −95% | $0.0058→$0.0007 | baseline **True** → BIOMA **False** |
| Claude Fable 5 | 2489→123 | −95% | $0.0000→$0.0000 | baseline **True** → BIOMA **False** |
| Gemini 3.1 Pro | 1835→81 | −96% | $0.0052→$0.0016 | baseline **True** → BIOMA **False** |
| Grok 4.5 | 1806→280 | −84% | $0.0026→$0.0026 | baseline **True** → BIOMA **False** |
| GLM-5.2 | 1610→83 | −95% | $0.0026→$0.0007 | baseline **True** → BIOMA **False** |

## Offline — modelo local / on-prem (sem rede)

| Modelo (offline) | in tok base→BIOMA | redução | custo | segredo vazou |
| :--- | :---: | :---: | :---: | :---: |
| Llama-3.3-70B (on-prem) | 1.069→63 | −94% | $0 (local) | **False** |

## Defesa em profundidade — idêntica na frente de qualquer modelo

| Vetor | Resultado |
| :--- | :--- |
| Exfiltração de segredo por prompt injection | ✅ CONTIDO — o segredo nunca chega ao modelo |
| DDoS cognitivo | ✅ MITIGADO — flood 8.403→2 (saturação 0.9988) |
| Loop por injeção de código | ✅ CONTIDO — timeout guard |

> **Veredito.** Adicionar o B.I.O.M.A. a qualquer LLM — online ou offline — dá a **mesma**
> eficiência (−94% de tokens de entrada) e a **mesma** postura de segurança, porque ele opera
> no payload. Só o **$ absoluto economizado escala com o preço do modelo**. É uma camada
> model-agnóstica de defesa em profundidade.
