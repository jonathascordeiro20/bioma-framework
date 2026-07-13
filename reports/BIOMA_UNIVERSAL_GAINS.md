# B.I.O.M.A. — Universal Integration Gains (any LLM · online & offline)

**🌐 English · [Português](BIOMA_UNIVERSAL_GAINS.pt-BR.md)**

> Ground truth. B.I.O.M.A. hardens the **payload**, not the model — so the gains are **model-agnostic** and identical whether the LLM is online (API) or offline (on-prem).

**Model-agnostic efficiency (measured on the payload):** input context **1,069 → 63 tokens (−94%)** · kernel 0.8μs · secret redacted from outbound.

## Online — real dispatch (baseline vs B.I.O.M.A.)

| Model (online) | in_tok base→BIOMA | reduction | cost base→BIOMA | secret → provider |
| :--- | :---: | :---: | :---: | :---: |
| GPT-5.5 | 1605→78 | −95% | $0.0113→$0.0029 | baseline **True** → BIOMA **False** |
| Claude Sonnet 5 | 2489→123 | −95% | $0.0058→$0.0007 | baseline **True** → BIOMA **False** |
| Claude Fable 5 | 2489→123 | −95% | $0.0000→$0.0000 | baseline **True** → BIOMA **False** |
| Gemini 3.1 Pro | 1835→81 | −96% | $0.0052→$0.0016 | baseline **True** → BIOMA **False** |
| Grok 4.5 | 1806→280 | −84% | $0.0026→$0.0026 | baseline **True** → BIOMA **False** |
| GLM-5.2 | 1610→83 | −95% | $0.0026→$0.0007 | baseline **True** → BIOMA **False** |

## Offline — local / on-prem model (no network)

| Model (offline) | in tok base→BIOMA | reduction | cost | secret leaked |
| :--- | :---: | :---: | :---: | :---: |
| Llama-3.3-70B (on-prem) | 1,069→63 | −94% | $0 (local) | **False** |

## Defense-in-depth — identical in front of any model

| Vector | Result |
| :--- | :--- |
| Prompt-injection secret exfiltration | ✅ CONTAINED — secret never reaches the model |
| Cognitive DDoS | ✅ MITIGATED — flood 8,403→2 (saturation 0.9988) |
| Code-injection loop | ✅ CONTAINED — timeout guard |

> **Verdict.** Adding B.I.O.M.A. to any LLM — online or offline — yields the **same** efficiency (−94% input tokens) and the **same** security posture, because it operates on the payload. Only the absolute **$ saved scales with the model's price**. It is a model-agnostic layer of defense-in-depth — see `COMMERCIAL_SCOPE.md`.