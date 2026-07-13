# B.I.O.M.A. — Edições (Núcleo Fair-Source)

**🌐 [English](EDITIONS.md) · Português**

O B.I.O.M.A. segue um modelo **fair-source**: o núcleo é source-available sob a
**Functional Source License (FSL-1.1-MIT)** — livre para ler, executar, auditar e construir em
cima para qualquer finalidade não-concorrente, e converte para MIT dois anos após cada release.
Uma edição **Enterprise** separada, sob licença comercial, adiciona a camada de soberania,
conformidade e suporte que organizações reguladas precisam.

## Edição Community — este repositório, FSL-1.1-MIT

Source-available. Leia, audite, execute, embuta no seu produto — sem custo, para qualquer
**Finalidade Permitida** sob a [`LICENSE`](LICENSE). A única coisa que você **não** pode fazer é
um **Uso Concorrente** — reempacotar o próprio B.I.O.M.A. como produto ou serviço rival. Dois
anos após cada release, aquela versão vira MIT automaticamente.

- `bioma_micro` — o micro-kernel Rust: barramento hormonal, apoptose de contexto, `saturation_scan`.
- `bioma` — `CognitiveFirewall` (redação de segredos, mitigação de DDoS cognitivo, timeout guard),
  cliente provider-agnóstico, servidor local.
- Suíte de testes completa, benchmarks e documentação.

**Tudo que os benchmarks ground-truth provam (−80–97% de tokens, redação de segredos, mitigação
de DDoS cognitivo, kernel μs) está na edição Community, grátis.**

## Edição Enterprise — repo privado `bioma-enterprise`, licença comercial

Add-ons de código fechado para implantações **soberanas / air-gapped / reguladas**. Construída
sobre o núcleo source-available; requer licença comercial.

| Capacidade | Community (FSL) | Enterprise (comercial) |
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

## Por que fair-source

Source-available gera **adoção, confiança e credibilidade** — qualquer um pode ler e auditar o
código — enquanto a cláusula de não-concorrência da FSL impede um rival de pegar e revender
contra você. A edição Enterprise **financia o desenvolvimento**. Usar o núcleo grátis nunca
obriga a Enterprise — a Enterprise existe para organizações que precisam da camada de
soberania/conformidade/suporte por cima.

> **Contato para Enterprise / licenciamento comercial:** jonathas.cordeiro2023@gmail.com
