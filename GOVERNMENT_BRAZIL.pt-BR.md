# B.I.O.M.A. — Playbook de Venda ao Governo (Brasil)

**🌐 [English](GOVERNMENT_BRAZIL.md) · Português**

> Como oferecer o B.I.O.M.A. ao setor público brasileiro **dentro da lei**, como conseguir o
> primeiro contrato, e como mostrar valor na língua do gestor público. Inclui **modelo de proposta
> CPSI** e **checklist de conformidade (LGPD + CNJ 615)**.
>
> ⚠️ **Não é aconselhamento jurídico.** Valide o passo final com um especialista em **direito
> público / licitações**. Reflete a legislação vigente em **julho de 2026**.

## As três portas legais (ranqueadas pelo encaixe)

| Porta | Base legal | Quando usar | Teto / limite |
| :-- | :-- | :-- | :-- |
| 🥇 **CPSI** — Contrato Público p/ Solução Inovadora | **LC 182/2021** (Marco Legal das Startups) | O órgão tem um *problema* e você propõe a solução inovadora, com fase de teste | Contrato de fornecimento até **R$ 8 mi** (dispensa nova licitação se o teste aprovar) |
| 🥈 **Dispensa de licitação** | **Lei 14.133/2021** | Primeiro **piloto pago** rápido, sem processo completo | Até **R$ 54.020,41** (bens/serviços comuns, 2026) |
| 🥉 **Encomenda Tecnológica (ETEC)** | **Lei 10.973/2004**, art. 20 | Órgão grande quer **co-desenvolver** com risco tecnológico | Definido no contrato |

## 🥇 Porta principal — CPSI passo a passo

O CPSI **inverte a licitação tradicional**: o edital descreve o *problema*, não o produto pronto.

1. **Órgão publica o desafio** (ex.: *"reduzir custo de tokens e defender nossos sistemas de IA contra prompt injection, mantendo o dado no nosso perímetro"*).
2. **Você submete a proposta** (use o modelo abaixo).
3. **Banca multidisciplinar (mín. 3)** julga por: grau de inovação, aderência ao problema, impacto potencial e viabilidade.
4. **Fase de teste em ambiente real** com aplicação de P&D — o B.I.O.M.A. roda no ambiente do órgão.
5. **Se o teste comprovar a eficácia → contrato de fornecimento direto, com licitação dispensada** (até R$ 8 mi).

## Como se cadastrar e achar oportunidades

| Etapa | Ação |
| :-- | :-- |
| **Formalizar** | CNPJ ativo · **enquadramento como startup** (declaração LC 182) · regularidade fiscal (CND, FGTS, trabalhista) |
| **Cadastrar** | **SICAF** + **Compras.gov.br (Comprasnet)** |
| **Monitorar** | **PNCP** (Portal Nacional de Contratações Públicas), BLL e portais dos tribunais — diariamente |
| **Munição** | Atestado de capacidade técnica (o 1º piloto gera), pacote LGPD, alinhamento CNJ 615 |

## Mostrar valor na língua do governo

O gestor não compra "−97% de tokens" — compra **economia do erário, conformidade e redução de risco**.

| O B.I.O.M.A. faz | O governo lê |
| :-- | :-- |
| Apoptose −80–97% tokens | **Economia de recursos públicos**, mensurável e auditável |
| Firewall cognitivo (anti prompt-injection) | **Segurança da informação** contra o #1 risco OWASP — com **precedente judicial** |
| Roda 100% local / air-gapped | **Soberania de dados**: o provedor deixa de ser **"operador" sob a LGPD** |
| Logs + não decide nada | Atende à **CNJ 615**: auditabilidade e **supervisão humana efetiva** |
| Conformidade por design | Reduz risco sob **LGPD** e o vindouro **Marco Legal da IA (PL 2338)** |

## Onde bater primeiro: o Judiciário

Melhor alvo inicial — **dor documentada** (advogados multados por prompt injection numa petição) +
**mandato regulatório** (a **Resolução CNJ 615/2025** exige governança, auditoria e registro no
**Sinapses**, e **respeita a autonomia dos tribunais** para adotar soluções locais — o modelo
on-prem do B.I.O.M.A.). Também fortes: **Tribunais de Contas** (o TCU já usa CPSI), **saúde
pública** e **defesa**.

---

## 📄 Modelo de proposta CPSI (esqueleto para preencher)

```
1. IDENTIFICAÇÃO
   Razão social / CNPJ / enquadramento como startup (LC 182/2021)
   Responsável técnico e contato

2. PROBLEMA PÚBLICO ENDEREÇADO
   [Citar o desafio do edital, com as palavras do órgão]

3. SOLUÇÃO PROPOSTA — B.I.O.M.A.
   Micro-kernel local de eficiência + defesa que roda dentro do perímetro do órgão,
   na frente de qualquer modelo (inclusive nacionais). Apoptose de contexto +
   firewall cognitivo + operação air-gapped.

4. GRAU DE INOVAÇÃO
   Combinação inédita (eficiência + segurança + soberania) num artefato local;
   kernel em Rust, latência de microssegundos.

5. RESULTADOS ESPERADOS (KPIs)
   - Redução de custo de tokens: __% (meta −80%+)
   - Incidentes de prompt injection bloqueados / segredos redigidos
   - Conformidade: registro no Sinapses, evidências LGPD/CNJ 615

6. PLANO DE TESTE EM AMBIENTE REAL
   Fases, duração, critérios objetivos de sucesso, ambiente do órgão.

7. ARQUITETURA
   Implantação on-prem / air-gapped; nenhum dado sai do perímetro.

8. CONFORMIDADE
   LGPD (minimização, segurança por design), CNJ 615 (auditoria, supervisão humana),
   cadastro no Sinapses por categoria de risco.

9. EQUIPE, CRONOGRAMA E ORÇAMENTO

10. RISCOS E MITIGAÇÃO
```

## ✅ Checklist de conformidade (LGPD + CNJ 615)

**LGPD (Lei 13.709/2018)**
- [ ] Encarregado (DPO) designado
- [ ] Base legal do tratamento definida
- [ ] RIPD (Relatório de Impacto) quando aplicável
- [ ] **Minimização de dados** — a apoptose do B.I.O.M.A. reduz o dado enviado ao modelo
- [ ] **Dado não sai do perímetro** (air-gapped) → o provedor não vira operador
- [ ] Segurança por design (art. 46)

**Resolução CNJ 615/2025** (para o Judiciário)
- [ ] Solução **cadastrada no Sinapses** (por categoria de risco)
- [ ] **Supervisão humana efetiva** garantida (o B.I.O.M.A. não toma decisões)
- [ ] **Auditabilidade / logs** (tamper-evident via edição Enterprise)
- [ ] Transparência e explicabilidade
- [ ] Respeito à autonomia do tribunal
- [ ] Monitoramento contínuo

## Ressalvas honestas
- **Ciclo longo** (meses a anos); pagamento público atrasa (legal 30 dias, real 60–90).
- O **1º contrato é o mais difícil** — CPSI e dispensa existem justamente para começar sem histórico.
- O **Marco Legal da IA (PL 2338) ainda NÃO é lei** (aguarda a Câmara) — use como "está vindo".
- Considere **parceria com integrador** que já vende ao governo — encurta muito o caminho.

## Referências
- [CPSI — Portal TCU](https://portal.tcu.gov.br/transparencia-e-prestacao-de-contas/servico/contrato-publico-para-solucao-inovadora-cpsi) · [LC 182/2021 (Planalto)](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp182.htm)
- [Resolução CNJ 615/2025 (íntegra)](https://atos.cnj.jus.br/files/original1555302025031467d4517244566.pdf) · [CNJ regulamenta uso de IA](https://www.cnj.jus.br/cnj-aprova-resolucao-regulamentando-o-uso-da-ia-no-poder-judiciario/)
- [PL 2338 / Marco Legal da IA — status (Senado)](https://www25.senado.leg.br/web/atividade/materias/-/materia/157233)
- [Vender ao governo federal (Compras.gov.br)](https://www.gov.br/compras/pt-br/fornecedor) · [Dispensa 2026 — valores](https://licitagov.org/artigos/dispensa-de-licitacao-como-participar/)
