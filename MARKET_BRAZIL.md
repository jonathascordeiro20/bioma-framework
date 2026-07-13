# B.I.O.M.A. — Competitive Map (Brazil)

**🌐 English · [Português](MARKET_BRAZIL.pt-BR.md)**

> One-page competitive read for the Brazilian market. Reflects public research as of
> **July 2026**. Sources at the bottom; every claim is linked, not asserted.

## Thesis

**No Brazilian company ships B.I.O.M.A.'s exact solution** — a **local, embeddable micro-kernel**
that combines **token/context reduction + an LLM cognitive firewall + provider-agnostic
sovereignty**, running inside the customer's perimeter. What Brazil has today is *resellers* of
foreign tools, *consultancies*, and *sovereign model/infra* players one layer away. The **demand
and the regulation are already here; the local product is not.**

## Landscape

| Category | Brazilian players | Same as B.I.O.M.A.? | Competitive threat |
| :--- | :--- | :--- | :---: |
| Foreign LLM-firewall resold locally | **Brasec** (exclusive **AccuKnox** distributor) | ❌ Security only; foreign tech, cloud-oriented — not an embeddable local kernel | **Medium–High** (security layer) |
| Native provider guardrails | **AWS Bedrock Guardrails** (widely used in BR) | ❌ Security only; AWS-/cloud-bound, not sovereign/air-gapped | **High** for AWS shops |
| LLM cost/token savings | Prompt caching (Claude/OpenAI, −90%), multi-LLM routing; agencies (X-Apps, EPIC, SegredoTech) | ❌ Efficiency only; not local, no security — and partly free/native | **Medium** (commoditizes tokens-alone) |
| Sovereign model / infra (BR) | **WideLabs** (Amazônia IA — sovereign GPU cloud), **Maritaca AI** (Sabiá models) | ⚠️ Different layer — they *host models*; B.I.O.M.A. runs *in front of* any model | **Low as rival · high as partner** |
| Security consultancies | Autenticare, Inteligência Brasil, B2E Group | ❌ Services/education, not a product | Low |

## The white space B.I.O.M.A. owns

The **combination** nobody in Brazil ships as one local artifact:
**efficiency (−80–97% tokens) + cognitive firewall (secret redaction, prompt-flood defense) +
provider-agnostic + air-gapped**, embeddable in front of *any* model — including national ones
(Sabiá, Amazônia IA). Foreign products cover the security piece but live in the cloud; national
players host models but don't harden the payload.

## Demand & regulatory tailwind 🔥

- **First documented court precedent:** a labor judge in Parauapebas/PA **fined lawyers** for
  hidden prompt-injection commands planted in a petition to manipulate an AI system. Prompt
  injection is the **#1 OWASP LLM risk**.
- **LGPD "security/privacy by design":** sending payloads to OpenAI/Google/Anthropic makes the
  provider a data **"operator"** under LGPD → structural pressure toward **local/sovereign**
  processing. This is exactly B.I.O.M.A.'s pitch.
- **ANPD** was upgraded into a **National Agency** by **Law 15.352/2026** — enforcement is rising.

## Positioning (recommended)

> *"The efficiency and defense layer that runs **100% locally and sovereign** — inside your
> perimeter, in front of any model (including Sabiá / Amazônia IA), **LGPD-compliant by
> design**."*

Sell the **combination + sovereignty**, never token-savings alone (that is being commoditized by
native prompt caching).

## Go-to-market

- **Partners, not rivals:** Maritaca / WideLabs — B.I.O.M.A. hardens and slims the payload *before*
  it reaches their models.
- **Channel:** security MSSPs / distributors (Brasec-type) already selling to regulated enterprise.
- **Beachhead sectors:** Judiciary / legal (documented pain), regulated finance, health, government.
- **Honest caveats:** AWS Bedrock Guardrails is native and easy for AWS shops; native caching
  already delivers "good-enough" savings; sovereign/gov sales cycles are long.

## Sources

- [Brasec — Prompt Firewall (AccuKnox reseller)](https://brasec.com.br/firewall-prompts-seguranca-ia/) · [AccuKnox × Brasec partnership](https://accuknox.com/press-release/brasec-partnership-portuguese)
- [WideLabs (Amazônia IA)](https://widelabs.com.br/) · [Maritaca AI](https://www.maritaca.ai/en/) · [Does Brazil need its own LLM? — Radar Neural](https://www.radarneural.com/artigo/maritaca-ai-llm-brasileiro)
- [Prompt injection in the Judiciary — Parauapebas/PA precedent (Jusbrasil)](https://www.jusbrasil.com.br/artigos/prompt-injection-em-documentos-juridicos-e-sistemas-de-ia-no-poder-judiciario-analise-tecnica-regulatoria-processual-e-probatoria/6105847115) · [AI agents & LGPD (Instituto Privacidade)](https://iprivacidade.org.br/blog/agentes-de-ia-e-lgpd-a-governanca-de-dados-deve-vir-antes-da-automacao)
- [Local AI & LGPD 2026 (PromptQuorum)](https://www.promptquorum.com/local-llms/local-llm-lgpd-compliance-brazil-2026) · [Protecting LLM agents with Bedrock Guardrails (M. Mesquita)](https://michelleamesquita.medium.com/protegendo-agentes-llm-contra-ataques-implementando-amazon-bedrock-guardrails-com-fastapi-0d44d763b630)
- [Cutting GenAI cost (X-Apps)](https://x-apps.com.br/reduzir-custo-ia-generativa-caching-roteamento-limites/) · [Multi-LLM strategy 2026 (SegredoTech)](https://segredotech.com.br/estrategia-multi-llm-2026-rate-limits-custos/)
