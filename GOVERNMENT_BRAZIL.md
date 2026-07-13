# B.I.O.M.A. — Government Sales Playbook (Brazil)

**🌐 English · [Português](GOVERNMENT_BRAZIL.pt-BR.md)**

> How to offer B.I.O.M.A. to the Brazilian public sector **within the law**, how to land the first
> contract, and how to show value in a public buyer's language. Includes a **CPSI proposal
> template** and a **compliance checklist (LGPD + CNJ 615)**.
>
> ⚠️ **Not legal advice.** Validate the final step with a **public-law / procurement** specialist.
> Reflects legislation in force as of **July 2026**.

## The three legal doors (ranked by fit)

| Door | Legal basis | When to use | Ceiling / limit |
| :-- | :-- | :-- | :-- |
| 🥇 **CPSI** — Public Contract for Innovative Solution | **LC 182/2021** (Startups Legal Framework) | The agency has a *problem* and you propose the innovative solution, with a testing phase | Supply contract up to **R$ 8M** (waives new bidding if the test passes) |
| 🥈 **Bid waiver (dispensa)** | **Law 14.133/2021** | A fast, **paid pilot** with no full procurement | Up to **R$ 54,020.41** (common goods/services, 2026) |
| 🥉 **Technological Order (ETEC)** | **Law 10.973/2004**, art. 20 | A large agency wants to **co-develop** with technological risk | Set in contract |

## 🥇 Main door — CPSI step by step

CPSI **inverts traditional procurement**: the notice describes the *problem*, not a finished product.

1. **Agency publishes the challenge** (e.g., *"cut token cost and defend our AI systems against prompt injection while keeping data inside our perimeter"*).
2. **You submit the proposal** (use the template below).
3. **Multidisciplinary panel (min. 3)** scores on: degree of innovation, fit to the problem, potential impact, feasibility.
4. **Real-environment testing phase** with R&D — B.I.O.M.A. runs inside the agency.
5. **If the test proves effectiveness → direct supply contract, bidding waived** (up to R$ 8M).

## How to register and find opportunities

| Step | Action |
| :-- | :-- |
| **Formalize** | Active CNPJ · **startup classification** (LC 182 declaration) · tax regularity (CND, FGTS, labor) |
| **Register** | **SICAF** + **Compras.gov.br (Comprasnet)** |
| **Monitor** | **PNCP** (National Public Procurement Portal), BLL and court portals — daily |
| **Ammunition** | Technical-capability attestation (the first pilot earns it), LGPD pack, CNJ 615 alignment |

## Show value in the government's language

Managers don't buy "−97% tokens" — they buy **public-money savings, compliance, and risk reduction**.

| What B.I.O.M.A. does | How government reads it |
| :-- | :-- |
| Apoptosis −80–97% tokens | **Savings of public resources**, measurable and auditable |
| Cognitive firewall (anti prompt-injection) | **Information security** against the #1 OWASP risk — with a **court precedent** |
| Runs 100% local / air-gapped | **Data sovereignty**: the provider stops being an **"operator" under the LGPD** |
| Logs + decides nothing | Meets **CNJ 615**: auditability and **effective human oversight** |
| Compliance by design | Cuts risk under **LGPD** and the coming **AI Legal Framework (PL 2338)** |

## Where to strike first: the Judiciary

Best initial target — **documented pain** (lawyers fined for prompt injection in a petition) +
**regulatory mandate** (**CNJ Resolution 615/2025** requires governance, auditing and registration
in **Sinapses**, and **respects tribunals' autonomy** to adopt local solutions — B.I.O.M.A.'s
on-prem model). Also strong: **Courts of Accounts** (TCU already uses CPSI), **public health**, and
**defense**.

---

## 📄 CPSI proposal template (skeleton to fill)

```
1. IDENTIFICATION
   Legal name / CNPJ / startup classification (LC 182/2021)
   Technical lead and contact

2. PUBLIC PROBLEM ADDRESSED
   [Quote the notice's challenge, in the agency's words]

3. PROPOSED SOLUTION — B.I.O.M.A.
   Local efficiency + defense micro-kernel running inside the agency's perimeter,
   in front of any model (including national ones). Context apoptosis +
   cognitive firewall + air-gapped operation.

4. DEGREE OF INNOVATION
   A novel combination (efficiency + security + sovereignty) in a local artifact;
   Rust kernel, microsecond latency.

5. EXPECTED RESULTS (KPIs)
   - Token cost reduction: __% (target −80%+)
   - Prompt-injection incidents blocked / secrets redacted
   - Compliance: Sinapses registration, LGPD/CNJ 615 evidence

6. REAL-ENVIRONMENT TEST PLAN
   Phases, duration, objective success criteria, agency environment.

7. ARCHITECTURE
   On-prem / air-gapped deployment; no data leaves the perimeter.

8. COMPLIANCE
   LGPD (minimization, security by design), CNJ 615 (audit, human oversight),
   Sinapses registration by risk category.

9. TEAM, TIMELINE AND BUDGET

10. RISKS AND MITIGATION
```

## ✅ Compliance checklist (LGPD + CNJ 615)

**LGPD (Law 13.709/2018)**
- [ ] Data Protection Officer (DPO) appointed
- [ ] Legal basis for processing defined
- [ ] DPIA (impact report) where applicable
- [ ] **Data minimization** — B.I.O.M.A.'s apoptosis shrinks data sent to the model
- [ ] **Data never leaves the perimeter** (air-gapped) → the provider is not an operator
- [ ] Security by design (art. 46)

**CNJ Resolution 615/2025** (for the Judiciary)
- [ ] Solution **registered in Sinapses** (by risk category)
- [ ] **Effective human oversight** guaranteed (B.I.O.M.A. makes no decisions)
- [ ] **Auditability / logs** (tamper-evident via the Enterprise edition)
- [ ] Transparency and explainability
- [ ] Respect for the tribunal's autonomy
- [ ] Continuous monitoring

## Honest caveats
- **Long cycle** (months to years); public payment lags (legal 30 days, real 60–90).
- The **first contract is hardest** — CPSI and dispensa exist precisely to start without a track record.
- The **AI Legal Framework (PL 2338) is NOT law yet** (pending the Chamber) — use it as "coming".
- Consider **partnering with an integrator** that already sells to government — it shortens the path.

## References
- [CPSI — TCU Portal](https://portal.tcu.gov.br/transparencia-e-prestacao-de-contas/servico/contrato-publico-para-solucao-inovadora-cpsi) · [LC 182/2021 (Planalto)](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp182.htm)
- [CNJ Resolution 615/2025 (full text)](https://atos.cnj.jus.br/files/original1555302025031467d4517244566.pdf) · [CNJ regulates AI use](https://www.cnj.jus.br/cnj-aprova-resolucao-regulamentando-o-uso-da-ia-no-poder-judiciario/)
- [PL 2338 / AI Legal Framework — status (Senate)](https://www25.senado.leg.br/web/atividade/materias/-/materia/157233)
- [Selling to the federal government (Compras.gov.br)](https://www.gov.br/compras/pt-br/fornecedor) · [Bid waiver 2026 — thresholds](https://licitagov.org/artigos/dispensa-de-licitacao-como-participar/)
