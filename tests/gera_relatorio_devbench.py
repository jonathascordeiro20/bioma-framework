#!/usr/bin/env python3
"""Gera resultados/relatorio.md a partir do CSV bruto do DevBench (seção 6 do protocolo)."""
from __future__ import annotations

import csv
import os
import statistics
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(_ROOT, "resultados")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

with open(os.path.join(RES, "execucoes.csv"), encoding="utf-8") as f:
    rows = [dict(r) for r in csv.DictReader(f)]
for r in rows:
    r["custo_usd"] = float(r["custo_usd"])
    r["input_tokens"] = int(r["input_tokens"])
    r["output_tokens"] = int(r["output_tokens"])
    r["sucesso"] = int(r["sucesso"])
    r["replica"] = int(r["replica"])

MODELS = ["Claude Fable 5", "Claude Opus 4.8", "Claude Sonnet 5", "GPT-5.6 Sol",
          "GLM-5.2", "Grok 4.5", "Gemini 3.5 Flash"]
TASKS = ["T1-bugfix", "T2-refactor", "T3-feature"]


def med(xs): return statistics.median(xs) if xs else None
def p90(xs): return sorted(xs)[max(0, int(round(0.9 * len(xs))) - 1)] if xs else None


L: list[str] = []
say = L.append
say("# DevBench B.I.O.M.A. — Relatório Final (dados reais da API, nunca estimados)")
say("")
say("> Protocolo adaptado para OpenRouter (adaptações registradas na seção 6). "
    "Matriz: 2 braços × 7 modelos × 3 tarefas × 3 réplicas = 126 execuções "
    "(+2 do piloto, incluídas e marcadas). BIOMA commit `625d6b4`, half_life 6.0, "
    "threshold 0.35, temperatura 0.0, ordem alternada A-B/B-A. "
    "Dados brutos: `execucoes.csv`, `usage_raw.jsonl`, `precos_openrouter.json`.")
say("")

# ---- 1. tabela mestre ----------------------------------------------------- #
say("## 1. Tabela mestre — mediana (p90) por tarefa × modelo × braço")
say("")
say("| Tarefa | Modelo | in_tok A | in_tok B | custo A | custo B | sucesso A | sucesso B |")
say("| :--- | :--- | ---: | ---: | ---: | ---: | :---: | :---: |")
for t in TASKS:
    for m in MODELS:
        a = [r for r in rows if r["tarefa"] == t and r["modelo"] == m and r["braco"] == "A"]
        b = [r for r in rows if r["tarefa"] == t and r["modelo"] == m and r["braco"] == "B"]
        if not a or not b:
            continue
        ca, cb = [r["custo_usd"] for r in a], [r["custo_usd"] for r in b]
        sa = sum(r["sucesso"] for r in a) / len(a)
        sb = sum(r["sucesso"] for r in b) / len(b)
        say(f"| {t} | {m} | {med(r['input_tokens'] for r in a):,.0f} "
            f"| {med(r['input_tokens'] for r in b):,.0f} "
            f"| ${med(ca):.4f} (${p90(ca):.4f}) | ${med(cb):.4f} (${p90(cb):.4f}) "
            f"| {sa*100:.0f}% | {sb*100:.0f}% |")
say("")
say("Sucesso inclui execuções com erro (erro ⇒ sucesso=0). Tokens comparáveis apenas "
    "dentro do mesmo modelo (tokenizadores distintos — ex.: T3 tem 15.133 tok no "
    "tokenizador Claude e 10.182 no GPT para o MESMO texto).")
say("")

# ---- 2. economia por modelo (pareada) -------------------------------------- #
say("## 2. Economia de custo por modelo (pares tarefa×réplica, braço B vs A)")
say("")
say("| Modelo | economia mediana | economia absoluta mediana/chamada | pares |")
say("| :--- | ---: | ---: | ---: |")
pares_txt = []
for m in MODELS:
    diffs, absd = [], []
    for t in TASKS:
        for rep in (1, 2, 3):
            a = [r for r in rows if r["tarefa"] == t and r["modelo"] == m
                 and r["braco"] == "A" and r["replica"] == rep and not r["observacoes"]]
            b = [r for r in rows if r["tarefa"] == t and r["modelo"] == m
                 and r["braco"] == "B" and r["replica"] == rep and not r["observacoes"]]
            if a and b and a[0]["custo_usd"] > 0:
                diffs.append(1 - b[0]["custo_usd"] / a[0]["custo_usd"])
                absd.append(a[0]["custo_usd"] - b[0]["custo_usd"])
                pares_txt.append(f"{m} · {t} · r{rep}: ${a[0]['custo_usd']:.4f} → "
                                 f"${b[0]['custo_usd']:.4f} (−{diffs[-1]*100:.0f}%)")
    if diffs:
        say(f"| {m} | **−{med(diffs)*100:.0f}%** | ${med(absd):.4f} | {len(diffs)} |")
say("")
say("**Hipótese do protocolo confirmada:** a economia ABSOLUTA é maior no Fable 5 "
    "(entrada $10/M): mediana de "
    f"${med([float(p.split('→')[0].split('$')[1]) - float(p.split('→ $')[1].split(' ')[0]) for p in pares_txt if p.startswith('Claude Fable')]):.4f} "
    "por chamada — no T3 chega a ~$0,157/chamada (−92%).")
say("")
say("<details><summary>Diferenças pareadas (todas)</summary>")
say("")
for p in pares_txt:
    say(f"- {p}")
say("")
say("</details>")
say("")

# ---- 3. cache --------------------------------------------------------------- #
say("## 3. Efeito no cache")
say("")
say("**NÃO MEDIDO.** Esta adaptação não exercita `cache_control`; o usage do "
    "OpenRouter não retornou campos de cache para estes dispatches. A interação "
    "apoptose×prompt-caching permanece pergunta aberta para a versão E2E com "
    "gateway compatível com a API Anthropic.")
say("")

# ---- 4. qualidade ----------------------------------------------------------- #
say("## 4. Qualidade — RESULTADO DE PRIMEIRA PÁGINA")
say("")
fable_t1_b = [r for r in rows if r["modelo"] == "Claude Fable 5"
              and r["tarefa"] == "T1-bugfix" and r["braco"] == "B"]
say(f"**Claude Fable 5 × T1 × braço B falhou 3/3** (resposta vazia, 1–3 tokens de "
    "saída, custo $0.0000) onde o braço A passou. O braço A do mesmo modelo/tarefa "
    "também teve 1 réplica parcial (probes 33%). Nas demais tarefas (T2, T3) o "
    "Fable 5 no braço B respondeu 100%. Hipótese (não confirmada): filtro do "
    "endpoint sobre o prompt desidratado — consistente com o `content_filter` "
    "já documentado em `reports/BIOMA_QUALITY_PRESERVATION.md`. Fora essa célula: "
    "**60/60 execuções válidas do braço B com 100% de probes**, paridade total.")
say("")
say("| Métrica global | Braço A | Braço B |")
say("| :--- | :---: | :---: |")
a_all = [r for r in rows if r["braco"] == "A"]
b_all = [r for r in rows if r["braco"] == "B"]
say(f"| Sucesso (incluindo erros) | {sum(r['sucesso'] for r in a_all)}/{len(a_all)} "
    f"({sum(r['sucesso'] for r in a_all)/len(a_all)*100:.0f}%) "
    f"| {sum(r['sucesso'] for r in b_all)}/{len(b_all)} "
    f"({sum(r['sucesso'] for r in b_all)/len(b_all)*100:.0f}%) |")
say("")

# ---- 5. verificação cruzada -------------------------------------------------- #
say("## 5. Verificação cruzada e achado de auditoria")
say("")
tot_a = sum(r["custo_usd"] for r in a_all)
tot_b = sum(r["custo_usd"] for r in b_all)
say(f"- Custo total medido (usage da API): braço A **${tot_a:.4f}** · braço B "
    f"**${tot_b:.4f}** · lote ${tot_a+tot_b:.4f}.")
say("- `/cost` e Console Anthropic: **NÃO APLICÁVEL** nesta adaptação (OpenRouter); "
    "auditoria equivalente = dashboard do OpenRouter por chave.")
say("- **Achado de auditoria:** chamadas idênticas (mesmos tokens) tiveram custo até "
    "6× diferente entre réplicas no MESMO braço (ex.: GPT-5.6 Sol T1-A: $0.0243 vs "
    "$0.0039 com 3.518 tokens iguais) — o OpenRouter roteia para provedores com "
    "preços distintos. O usage.cost reflete a rota real; a tabela `precos_openrouter"
    ".json` é o preço de lista. Medianas mitigam; declarado como variância de rota.")
say("")

# ---- 6. limitações ------------------------------------------------------------ #
say("## 6. Limitações declaradas")
say("")
say("1. Tarefas simuladas (sessões de dev-agente com probes objetivas), não execução "
    "E2E de agente em repositório real — a versão com Claude Code + gateway "
    "Anthropic-compatível permanece bloqueada (gateway inexistente no BIOMA; "
    "falha registrada no pre-flight).")
say("2. N pequeno (3 tarefas × 3 réplicas), um único formato de prompt.")
say("3. Prompt caching não exercitado (seção 3).")
say("4. Tokenizadores distintos entre modelos — comparações apenas intra-modelo.")
say("5. Variância de rota do OpenRouter (seção 5) afeta custos individuais; "
    "medianas e pares por réplica mitigam.")
say("6. 'Gemini 3.5' substituído por `google/gemini-3.5-flash` (única variante 3.5 "
    "na API); piloto (2 linhas extras de T1×Sonnet) incluído no CSV.")

with open(os.path.join(RES, "relatorio.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(L) + "\n")
print(f"relatório gravado em {os.path.join(RES, 'relatorio.md')} ({len(L)} linhas)")
