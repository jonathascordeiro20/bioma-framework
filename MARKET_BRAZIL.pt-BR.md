# B.I.O.M.A. — Mapa Competitivo (Brasil)

**🌐 [English](MARKET_BRAZIL.md) · Português**

> Leitura competitiva de uma página para o mercado brasileiro. Reflete pesquisa pública de
> **julho de 2026**. Fontes no rodapé; cada afirmação é linkada, não apenas asseverada.

## Tese

**Nenhuma empresa brasileira entrega a solução exata do B.I.O.M.A.** — um **micro-kernel local e
embutível** que junta **redução de tokens/contexto + firewall cognitivo de LLM + soberania
provider-agnóstica**, rodando dentro do perímetro do cliente. O que o Brasil tem hoje são
*revendas* de ferramentas estrangeiras, *consultorias*, e players de *modelo/infra soberana* uma
camada ao lado. A **demanda e a regulação já chegaram; o produto local, não.**

## Panorama

| Categoria | Players brasileiros | É o mesmo que B.I.O.M.A.? | Ameaça competitiva |
| :--- | :--- | :--- | :---: |
| Firewall de LLM estrangeiro revendido aqui | **Brasec** (distribuidora exclusiva da **AccuKnox**) | ❌ Só segurança; tecnologia estrangeira, orientada a nuvem — não é kernel local embutível | **Média–Alta** (camada de segurança) |
| Guardrails nativos do provedor | **AWS Bedrock Guardrails** (muito usado no BR) | ❌ Só segurança; preso à AWS/nuvem, não soberano/air-gapped | **Alta** para quem é AWS |
| Economia de custo/tokens | Prompt caching (Claude/OpenAI, −90%), roteamento multi-LLM; agências (X-Apps, EPIC, SegredoTech) | ❌ Só eficiência; não local, sem segurança — e em parte grátis/nativo | **Média** (comoditiza "tokens" isolado) |
| Modelo / infra soberana (BR) | **WideLabs** (Amazônia IA — GPU cloud soberana), **Maritaca AI** (modelos Sabiá) | ⚠️ Camada diferente — eles *hospedam modelos*; o B.I.O.M.A. roda *na frente de* qualquer modelo | **Baixa como rival · alta como parceiro** |
| Consultorias de segurança | Autenticare, Inteligência Brasil, B2E Group | ❌ Serviço/educação, não produto | Baixa |

## O espaço em branco que o B.I.O.M.A. ocupa

A **combinação** que ninguém no Brasil entrega como um único artefato local:
**eficiência (−80–97% de tokens) + firewall cognitivo (redação de segredos, defesa contra flood de
prompts) + provider-agnóstico + air-gapped**, embutível na frente de *qualquer* modelo — inclusive
os nacionais (Sabiá, Amazônia IA). Os estrangeiros cobrem a parte de segurança mas vivem na nuvem;
os nacionais hospedam modelos mas não blindam o payload.

## Vento de demanda & regulação 🔥

- **Primeiro precedente judicial documentado:** juíza do trabalho em Parauapebas/PA **multou
  advogados** por comandos ocultos de prompt injection plantados numa petição para manipular um
  sistema de IA. Prompt injection é o **#1 risco OWASP LLM**.
- **LGPD "segurança/privacidade por design":** mandar payloads para OpenAI/Google/Anthropic faz o
  provedor virar **"operador"** de dados sob a LGPD → pressão estrutural por processamento
  **local/soberano**. É exatamente o pitch do B.I.O.M.A.
- **A ANPD** virou **Agência Nacional** pela **Lei 15.352/2026** — fiscalização subindo.

## Posicionamento (recomendado)

> *"A camada de eficiência e defesa que roda **100% local e soberana** — dentro do seu perímetro,
> na frente de qualquer modelo (inclusive Sabiá / Amazônia IA), **em conformidade com a LGPD por
> design**."*

Venda a **combinação + soberania**, nunca economia de tokens isolada (isso está sendo comoditizado
pelo prompt caching nativo).

## Ir ao mercado (GTM)

- **Parceiros, não rivais:** Maritaca / WideLabs — o B.I.O.M.A. blinda e enxuga o payload *antes* de
  ele chegar aos modelos deles.
- **Canal:** MSSPs / distribuidores de segurança (tipo Brasec) já vendendo para o enterprise regulado.
- **Setores de entrada:** Judiciário / jurídico (dor documentada), finanças reguladas, saúde, governo.
- **Ressalvas honestas:** o AWS Bedrock Guardrails é nativo e fácil para quem é AWS; o caching nativo
  já entrega economia "boa o suficiente"; o ciclo de venda soberano/governo é longo.

## Fontes

- [Brasec — Firewall de Prompts (revenda AccuKnox)](https://brasec.com.br/firewall-prompts-seguranca-ia/) · [Parceria AccuKnox × Brasec](https://accuknox.com/press-release/brasec-partnership-portuguese)
- [WideLabs (Amazônia IA)](https://widelabs.com.br/) · [Maritaca AI](https://www.maritaca.ai/en/) · [O Brasil precisa de um LLM próprio? — Radar Neural](https://www.radarneural.com/artigo/maritaca-ai-llm-brasileiro)
- [Prompt injection no Judiciário — precedente Parauapebas/PA (Jusbrasil)](https://www.jusbrasil.com.br/artigos/prompt-injection-em-documentos-juridicos-e-sistemas-de-ia-no-poder-judiciario-analise-tecnica-regulatoria-processual-e-probatoria/6105847115) · [Agentes de IA e LGPD (Instituto Privacidade)](https://iprivacidade.org.br/blog/agentes-de-ia-e-lgpd-a-governanca-de-dados-deve-vir-antes-da-automacao)
- [IA Local & LGPD 2026 (PromptQuorum)](https://www.promptquorum.com/local-llms/local-llm-lgpd-compliance-brazil-2026) · [Protegendo agentes LLM com Bedrock Guardrails (M. Mesquita)](https://michelleamesquita.medium.com/protegendo-agentes-llm-contra-ataques-implementando-amazon-bedrock-guardrails-com-fastapi-0d44d763b630)
- [Reduzir custo de IA generativa (X-Apps)](https://x-apps.com.br/reduzir-custo-ia-generativa-caching-roteamento-limites/) · [Estratégia Multi-LLM 2026 (SegredoTech)](https://segredotech.com.br/estrategia-multi-llm-2026-rate-limits-custos/)
