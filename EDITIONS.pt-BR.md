# B.I.O.M.A. — Edições (Open-Core)

**🌐 [English](EDITIONS.md) · Português**

O B.I.O.M.A. segue um modelo **open-core**: o núcleo é livre e aberto (MIT); uma edição
**Enterprise** separada, sob licença comercial, adiciona a camada de soberania, conformidade e
suporte que organizações reguladas precisam.

## Edição Community — este repositório, MIT

Livre e aberta. Use, forke, embuta, distribua — sem custo, sob a [`LICENSE`](LICENSE).

- `bioma_micro` — o micro-kernel Rust: barramento hormonal, apoptose de contexto, `saturation_scan`.
- `bioma` — `CognitiveFirewall` (redação de segredos, mitigação de DDoS cognitivo, timeout guard),
  cliente provider-agnóstico, servidor local.
- Suíte de testes completa, benchmarks e documentação.

**Tudo que os benchmarks ground-truth provam (−80–97% de tokens, redação de segredos, mitigação
de DDoS cognitivo, kernel μs) está na edição Community, grátis.**

## Edição Enterprise — repo privado `bioma-enterprise`, licença comercial

Add-ons de código fechado para implantações **soberanas / air-gapped / reguladas**. Construída
sobre o núcleo MIT; requer licença comercial.

| Capacidade | Community (MIT) | Enterprise (comercial) |
| :--- | :---: | :---: |
| Apoptose de contexto · firewall · kernel | ✅ | ✅ |
| Provider-agnóstico (Anthropic/Google/OpenAI/local) | ✅ | ✅ |
| Ferramentas de implantação soberana / air-gapped & hardening | — | ✅ |
| Gestão central de políticas & vault (packs de PII, segredos org-wide) | básico | ✅ |
| Dashboard admin & observabilidade de frota | só telemetria | ✅ |
| Evidência de conformidade (logs de auditoria, LGPD / SOC 2 / ISO 27001) | — | ✅ |
| Suporte prioritário & SLA | comunidade | ✅ |

A Enterprise é onde vive a diferenciação que a análise de mercado apontou — o **ângulo
soberano, on-prem** que os concorrentes SaaS não conseguem servir.

## Por que open-core

O núcleo MIT gera **adoção, confiança e credibilidade**; a edição Enterprise **financia o
desenvolvimento**. Usar o núcleo grátis nunca obriga a Enterprise — a Enterprise existe para
organizações que precisam da camada de soberania/conformidade/suporte por cima.

> **Contato para Enterprise / licenciamento comercial:** jonathas.cordeiro2023@gmail.com
