# B.I.O.M.A. — Mapeamento de Frameworks de Segurança & Conformidade

**🌐 [English](COMPLIANCE_MAPPING.md) · Português**

> Como os controles de runtime do B.I.O.M.A. mapeiam para os frameworks que o comprador avalia:
> **OWASP LLM Top 10 (2025)**, **NIST AI RMF 1.0** (+ GenAI Profile), **MITRE ATLAS** (v5.1.0) e
> **ISO/IEC 42001:2023**. Escrito para ser *auditado*, não admirado.

## Escopo — leia primeiro (honestidade acima de cobertura)

O B.I.O.M.A. é uma **camada de controle de runtime** — um kernel local e in-process que blinda o
payload *antes* de ele chegar a qualquer LLM. Ele **não** é um programa completo de governança ou
segurança de IA, e não finge ser:

- ✅ Ele **implementa controles específicos e verificáveis** que você cita como evidência no seu programa.
- ❌ Ele **não** cobre supply-chain/SBOM de modelo, poisoning em treinamento, segurança de RAG/vetores,
  alucinação/factualidade, nem governança de permissão de agentes. Isso exige outras ferramentas.
- 🔁 Ele **complementa — não substitui** — um programa ISO 42001 / NIST AI RMF.

**Legenda de cobertura:** ✅ Forte · ◐ Parcial · ○ Habilitador (apoia; o resultado é da sua organização) · — Não coberto.
Tudo marcado ✅/◐ tem lastro em testes reproduzíveis no [`FINDINGS.md`](FINDINGS.md) e na
[suíte de testes](tests/).

---

## OWASP LLM Top 10 (2025)

| # | Risco | B.I.O.M.A. | Como |
| :-- | :-- | :--: | :-- |
| LLM01 | Prompt Injection | ◐ | Reduz o raio de dano, não é classificador semântico: segredos são redigidos (a injeção não os exfiltra); contexto é minimizado (apoptose); flood/repetição é pontuado (`saturation_scan`). Combine com um modelo de detecção para cobertura total. |
| LLM02 | Divulgação de Informação Sensível | ✅ | **Redação de segredos** via vault — valores configurados nunca chegam ao modelo; redação **na volta** (resposta); apoptose encolhe o contexto exposto. |
| LLM03 | Supply Chain | — | Fora de escopo (sem scanning de modelo / SBOM). |
| LLM04 | Poisoning de Dados & Modelo | — | Fora de escopo (treinamento; o B.I.O.M.A. é inferência). |
| LLM05 | Tratamento Impróprio de Saída | ◐ | Redação na resposta + **timeout guard**; não faz validação completa da saída a jusante. |
| LLM06 | Agência Excessiva | ○ | O core não governa permissão de agente; o `policies` do Enterprise adiciona regras centrais. |
| LLM07 | Vazamento de System Prompt | ◐ | A redação mantém credenciais fora do system prompt; apoptose + separação de papéis limitam o que vaza. |
| LLM08 | Fraquezas de Vetores & Embeddings | — | Fora de escopo (sem camada RAG/vetorial). |
| LLM09 | Desinformação | — | Fora de escopo (não é ferramenta de factualidade). |
| LLM10 | **Consumo Ilimitado** | ✅ | Encaixe principal. **Apoptose limita o consumo de tokens (−80–97%)**; `saturation_scan` sinaliza DDoS cognitivo/flood; timeout guard limita chamadas descontroladas — mitiga *Denial of Wallet* / exaustão de recursos. |

**Saldo:** forte de verdade em **LLM02** e **LLM10**; parcial em **LLM01/05/07**; explicitamente
fora de escopo no resto.

---

## NIST AI RMF 1.0 (+ GenAI Profile, NIST-AI-600-1)

O B.I.O.M.A. é um **controle técnico que operacionaliza** as duas funções voltadas ao runtime — ele
não escreve a sua governança.

| Função | B.I.O.M.A. | Como |
| :-- | :--: | :-- |
| **GOVERN** | ○ | Fornece um ponto de controle local, auditável e provider-agnóstico; a política é da sua organização. Trilha de auditoria à prova de adulteração é Enterprise (`compliance`). |
| **MAP** | — | Mapeamento de contexto/impacto é responsabilidade da sua organização. |
| **MEASURE** | ✅ | Emite telemetria de risco por requisição: % de redução de tokens, **score de saturação**, **red-alert `0x0F`**, `secrets_redacted`, latência do kernel — indicadores mensuráveis para a sua evidência de MEASURE. |
| **MANAGE** | ✅ | Implementa o **tratamento de risco** em runtime: redação, mitigação de flood, minimização de contexto, timeout — resposta técnica real, não só documentação. |

---

## MITRE ATLAS (técnicas adversariais)

Mapeado pelo **nome** da técnica (estável); valide os IDs exatos contra a matriz atual do ATLAS (v5.1.0, nov/2025).

| Tática → Técnica | B.I.O.M.A. | Como |
| :-- | :--: | :-- |
| Impact → **Denial of ML Service** | ✅ | `saturation_scan` detecta flood/repetição pré-dispatch; timeout guard limita chamadas. |
| Impact → **Cost Harvesting** (Denial of Wallet) | ✅ | Apoptose limita tokens; detecção de flood barra abuso de exaustão. |
| Exfiltration → **LLM Data Leakage** | ✅ | Redação de segredos (entrada + saída) barra a exfiltração de valores no vault. |
| Initial Access → **LLM Prompt Injection** | ◐ | Redução de raio de dano (redação + minimização de contexto); não é classificador de detecção. |
| Collection → **Extração de Meta/System Prompt** | ◐ | A redação mantém segredos fora da superfície extraível. |

---

## ISO/IEC 42001:2023 (Sistema de Gestão de IA)

A ISO 42001 certifica um **sistema de gestão**, não uma ferramenta. O B.I.O.M.A. fornece **evidência
de controle implementado** para áreas específicas do Anexo A — apoia, mas não confere, a certificação.

| Área de controle (Anexo A) | B.I.O.M.A. | Como |
| :-- | :--: | :-- |
| Gestão & minimização de dados | ✅ | Apoptose minimiza o dado enviado ao modelo; redação remove segredos do caminho do dado. |
| Controles de segurança operacional / runtime | ✅ | Firewall in-process, mitigação de flood, timeout, egresso provider-agnóstico. |
| Terceiros & proveniência de dados | ◐ | Provider-agnóstico + blindagem local reduzem a exposição a terceiros (o provedor vê menos). |
| Monitoramento & tratamento de eventos | ◐ | Emite telemetria + red-alert `0x0F`; log à prova de adulteração é Enterprise (`compliance`). |
| Governança, papéis, avaliação de impacto | — | Responsabilidade do seu sistema de gestão. |

---

## Community vs Enterprise (o que mapeia onde)

- **Community (este repo, FSL):** redação de segredos, apoptose de contexto, `saturation_scan` /
  mitigação de flood, timeout guard, operação provider-agnóstica + air-gapped, telemetria por requisição.
- **Enterprise (`bioma-enterprise`):** **logs de auditoria** à prova de adulteração e pacotes de
  evidência de conformidade, **packs de detecção** de PII/PHI, gestão central de **política/vault** e o
  **dashboard de frota** — as peças que auditores pedem sob ISO 42001 / NIST GOVERN.

## Como o comprador usa isto

Cite o B.I.O.M.A. como o **controle técnico implementado** para: OWASP **LLM02** & **LLM10**; NIST AI
RMF **MEASURE** & **MANAGE**; ATLAS **Denial of ML Service / Cost Harvesting / Data Leakage**; e as
áreas de **minimização de dados / controle operacional** da ISO 42001 — com evidência reproduzível no
[`FINDINGS.md`](FINDINGS.md). Para implantações air-gapped / soberanas, ele roda inteiramente dentro do
seu perímetro, sem egresso externo.

---

> **Não é aconselhamento jurídico, de auditoria ou de certificação.** As versões dos frameworks
> evoluem — valide IDs de controle e cobertura contra as versões publicadas atuais (OWASP LLM Top 10
> 2025 · NIST AI RMF 1.0 + NIST-AI-600-1 · MITRE ATLAS v5.1.0 · ISO/IEC 42001:2023) com o seu
> avaliador. Reflete o projeto em julho de 2026.
