# B.I.O.M.A. — Security & Compliance Framework Mapping

**🌐 English · [Português](COMPLIANCE_MAPPING.pt-BR.md)**

> How B.I.O.M.A.'s runtime controls map to the frameworks US buyers evaluate against:
> **OWASP LLM Top 10 (2025)**, **NIST AI RMF 1.0** (+ GenAI Profile), **MITRE ATLAS** (v5.1.0),
> and **ISO/IEC 42001:2023**. Written to be *audited*, not admired.

## Scope — read this first (honesty over coverage)

B.I.O.M.A. is a **runtime control layer** — a local, in-process kernel that hardens the payload
*before* it reaches any LLM. It is **not** a complete AI-governance or AI-security program, and it
does not pretend to be:

- ✅ It **implements specific, verifiable controls** you can cite as evidence in your program.
- ❌ It does **not** cover model supply-chain/SBOM, training-time poisoning, RAG/vector security,
  hallucination/factuality, or agent-permission governance. Those need other tools.
- 🔁 It **complements — does not replace** — an ISO 42001 / NIST AI RMF program.

**Coverage legend:** ✅ Strong · ◐ Partial · ○ Enabler (supports; your org owns the outcome) · — Not covered.
Everything marked ✅/◐ is backed by reproducible tests in [`FINDINGS.md`](FINDINGS.md) and the
[test suite](tests/).

---

## OWASP LLM Top 10 (2025)

| # | Risk | B.I.O.M.A. | How |
| :-- | :-- | :--: | :-- |
| LLM01 | Prompt Injection | ◐ | Reduces blast radius, not a semantic classifier: secrets are redacted so an injection can't exfiltrate them; context is minimized (apoptosis); prompt-flood/repetition is scored (`saturation_scan`). Pair with a detection model for full coverage. |
| LLM02 | Sensitive Information Disclosure | ✅ | Vault-based **secret redaction** — configured values never reach the model; **response-side** redaction on the way back; apoptosis shrinks exposed context. |
| LLM03 | Supply Chain | — | Out of scope (no model scanning / SBOM). |
| LLM04 | Data & Model Poisoning | — | Out of scope (training-time; B.I.O.M.A. is inference-time). |
| LLM05 | Improper Output Handling | ◐ | Response-side redaction + dispatch **timeout guard**; does not perform full downstream output validation. |
| LLM06 | Excessive Agency | ○ | Core doesn't govern agent permissions; Enterprise `policies` adds central rules. |
| LLM07 | System Prompt Leakage | ◐ | Secret redaction keeps credentials out of the system prompt; apoptosis + role separation limit what can leak. |
| LLM08 | Vector & Embedding Weaknesses | — | Out of scope (no RAG/vector layer). |
| LLM09 | Misinformation | — | Out of scope (not a factuality tool). |
| LLM10 | **Unbounded Consumption** | ✅ | Primary fit. **Apoptosis caps token consumption (−80–97%)**; `saturation_scan` flags cognitive-DDoS/flood; timeout guard bounds runaway calls — directly mitigating *Denial of Wallet* / resource exhaustion. |

**Net:** genuinely strong on **LLM02** and **LLM10**; partial on **LLM01/05/07**; explicitly out of
scope elsewhere.

---

## NIST AI RMF 1.0 (+ GenAI Profile, NIST-AI-600-1)

B.I.O.M.A. is a **technical control that operationalizes** the two runtime-facing functions — it
does not author your governance.

| Function | B.I.O.M.A. | How |
| :-- | :--: | :-- |
| **GOVERN** | ○ | Provides an auditable, local, provider-agnostic control point; your org owns policy. Tamper-evident audit trail is Enterprise (`compliance`). |
| **MAP** | — | Context/impact mapping is your org's responsibility. |
| **MEASURE** | ✅ | Emits per-request risk telemetry: token-reduction %, **saturation score**, **red-alert `0x0F`**, `secrets_redacted`, kernel latency — measurable indicators for your MEASURE evidence. |
| **MANAGE** | ✅ | Implements the runtime **risk treatment**: redaction, flood mitigation, context minimization, timeout — an actual technical response, not just documentation. |

---

## MITRE ATLAS (adversarial techniques)

Mapped by technique **name** (stable); validate exact IDs against the current ATLAS matrix (v5.1.0, Nov 2025).

| Tactic → Technique | B.I.O.M.A. | How |
| :-- | :--: | :-- |
| Impact → **Denial of ML Service** | ✅ | `saturation_scan` detects flood/repetition pre-dispatch; timeout guard bounds calls. |
| Impact → **Cost Harvesting** (Denial of Wallet) | ✅ | Apoptosis caps tokens; flood detection stops resource-exhaustion abuse. |
| Exfiltration → **LLM Data Leakage** | ✅ | Secret redaction (in + out) blocks exfiltration of vaulted values. |
| Initial Access → **LLM Prompt Injection** | ◐ | Blast-radius reduction (redaction + context minimization); not a detection classifier. |
| Collection → **Meta/System Prompt Extraction** | ◐ | Redaction keeps secrets out of the extractable surface. |

---

## ISO/IEC 42001:2023 (AI Management System)

ISO 42001 certifies a **management system**, not a tool. B.I.O.M.A. supplies **implemented-control
evidence** for specific Annex A control areas — it supports, but does not confer, certification.

| Annex A control area | B.I.O.M.A. | How |
| :-- | :--: | :-- |
| Data management & minimization | ✅ | Apoptosis minimizes data sent to the model; redaction removes secrets from the data path. |
| Operational / runtime security controls | ✅ | In-process firewall, flood mitigation, timeout, provider-agnostic egress. |
| Third-party & data-provenance | ◐ | Provider-agnostic + local hardening reduces third-party data exposure (the provider sees less). |
| Monitoring & event handling | ◐ | Emits telemetry + `0x0F` red-alert; tamper-evident logging is Enterprise (`compliance`). |
| Governance, roles, impact assessment | — | Your management system's responsibility. |

---

## Community vs Enterprise (what maps where)

- **Community (this repo, FSL):** secret redaction, context apoptosis, `saturation_scan` / flood
  mitigation, timeout guard, provider-agnostic + air-gapped operation, per-request telemetry.
- **Enterprise (`bioma-enterprise`):** tamper-evident **audit logs** and compliance evidence packs,
  PII/PHI **detection packs**, central **policy/vault** management, and the **fleet dashboard** —
  the pieces auditors ask for under ISO 42001 / NIST GOVERN.

## How a buyer uses this

Cite B.I.O.M.A. as the **implemented technical control** for: OWASP **LLM02** & **LLM10**; NIST AI RMF
**MEASURE** & **MANAGE**; ATLAS **Denial of ML Service / Cost Harvesting / Data Leakage**; and the
ISO 42001 **data-minimization / operational-control** areas — with reproducible evidence in
[`FINDINGS.md`](FINDINGS.md). For air-gapped / sovereign deployments, it runs entirely inside your
perimeter with no external egress.

---

> **Not legal, audit, or certification advice.** Framework versions evolve — validate control IDs
> and coverage against the current published versions (OWASP LLM Top 10 2025 · NIST AI RMF 1.0 +
> NIST-AI-600-1 · MITRE ATLAS v5.1.0 · ISO/IEC 42001:2023) with your assessor. Reflects the project
> as of July 2026.
