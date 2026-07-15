#!/usr/bin/env python3
"""
tests/test_quality_preservation.py — does apoptosis preserve ANSWER QUALITY?

The efficiency tests prove the token savings; this one proves the other half of
the contract: with REAL online models, what the user asks in chat is answered
correctly AFTER the history passes through context apoptosis — no loss of final
quality versus the full (bloated) baseline context.

Method (objective, no LLM judge): each scenario plants exact values (probes)
inside a long, noisy session, then asks a final question whose correct answer
must contain those values. The same prompt format is dispatched twice per model:

  * baseline — the FULL history (no apoptosis), joined exactly like the kernel
    renders it, so the ONLY variable is the apoptosis filter;
  * bioma    — the history dehydrated by `bioma_micro.dehydrate` via
    `LeanOpenRouterClient.dispatch` (the production path).

Scoring = fraction of probes present in the model's answer (case-insensitive).

Scenarios encode the usage contract honestly:
  S1 fact-tagged   — durable values tagged as FACT (designed usage) → parity.
  S2 recent-turns  — values given a few turns ago (survive by recency) → parity.
  S3 stale-untagged— value buried in an OLD, untagged user turn → apoptosis
                     purges it BY DESIGN; expected degradation, documents why
                     durable info must be tagged FACT. Never fails the verdict.

    python tests/test_quality_preservation.py                # all 6 online models
    python tests/test_quality_preservation.py --models openai/gpt-5.5
    python tests/test_quality_preservation.py --report       # also write reports/
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, ".env"))
except Exception:
    pass
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from bioma.openrouter_client import LeanOpenRouterClient, OPENROUTER_BASE_URL  # noqa: E402

ONLINE = [
    ("openai/gpt-5.5", "GPT-5.5"),
    ("anthropic/claude-sonnet-5", "Claude Sonnet 5"),
    ("anthropic/claude-fable-5", "Claude Fable 5"),
    ("google/gemini-3.1-pro-preview", "Gemini 3.1 Pro"),
    ("x-ai/grok-4.5", "Grok 4.5"),
    ("z-ai/glm-5.2", "GLM-5.2"),
]

SYSTEM_MSG = "You are a precise operations copilot. Answer with the exact requested values."


# --------------------------------------------------------------------------- #
#  Scenario construction — long noisy sessions with planted, checkable values
# --------------------------------------------------------------------------- #
def _noise_round(i: int) -> list[dict]:
    """One filler round: a verbose tool log (prime apoptosis target) + chatter."""
    log = (f"conn=ok src=10.0.{i % 254}.{(i * 7) % 254} dst=443 bytes=1240 flags=ACK,PSH "
           "seq=... ack=... win=... ttl=64 proto=TCP verdict=allow rule=default ... ") * 10
    return [
        {"role": "tool", "content": f"[audit burst {i}] {log}"},
        {"role": "user", "content": f"Round {i}: any anomaly in the last burst?"},
        {"role": "assistant", "content": f"Round {i}: nothing above baseline; continuing to monitor."},
    ]


@dataclass
class Scenario:
    key: str
    title: str
    history: list[dict]
    query: str
    probes: list[str]
    expected_degradation: bool = False  # S3: purge is BY DESIGN, not a failure
    note: str = ""


def build_scenarios(rounds: int = 15) -> list[Scenario]:
    scenarios: list[Scenario] = []

    # S1 — durable values tagged as FACT (the designed usage) ----------------- #
    h1: list[dict] = [
        {"role": "system", "content": SYSTEM_MSG},
        {"role": "fact", "content": "FACT: the deploy freeze ends on 2026-07-18."},
        {"role": "fact", "content": "FACT: the API rate limit is 350 requests per minute."},
        {"role": "fact", "content": "FACT: the open incident code is INC-7743."},
    ]
    for i in range(1, rounds + 1):
        h1 += _noise_round(i)
    scenarios.append(Scenario(
        key="S1", title="fatos marcados como FACT (uso projetado)",
        history=h1,
        query=("From the pinned facts only: (1) on which date does the deploy freeze end? "
               "(2) what is the API rate limit per minute? (3) which incident code is open? "
               "Reply with the three exact values."),
        probes=["2026-07-18", "350", "INC-7743"],
        note="FACT nunca é purgado — paridade esperada.",
    ))

    # S2 — values given by the user a FEW turns ago (survive by recency) ------ #
    h2: list[dict] = [{"role": "system", "content": SYSTEM_MSG}]
    for i in range(1, rounds - 1):
        h2 += _noise_round(i)
    h2 += [
        {"role": "user", "content": "Note this: my cluster name is atlas-prod-07 and the rollback token is RBK-5521."},
        {"role": "assistant", "content": "Noted: cluster atlas-prod-07, rollback token RBK-5521."},
    ]
    h2 += _noise_round(rounds)
    scenarios.append(Scenario(
        key="S2", title="informação em turnos recentes (sobrevive por recência)",
        history=h2,
        query="What cluster name and rollback token did I give you earlier? Reply with the exact values.",
        probes=["atlas-prod-07", "RBK-5521"],
        note="Turnos recentes têm oxigênio acima do threshold — paridade esperada.",
    ))

    # S3 — value buried in an OLD, UNTAGGED user turn (honest limit) ---------- #
    h3: list[dict] = [
        {"role": "system", "content": SYSTEM_MSG},
        {"role": "user", "content": "For later: the maintenance window is Saturday at 02:00 UTC."},
        {"role": "assistant", "content": "Understood."},
    ]
    for i in range(1, rounds + 1):
        h3 += _noise_round(i)
    scenarios.append(Scenario(
        key="S3", title="fato ANTIGO não marcado (limite honesto — purga por design)",
        history=h3,
        query="When is the maintenance window? Reply with day and time.",
        probes=["02:00"],
        expected_degradation=True,
        note="Bloco USER antigo decai abaixo do threshold — é o contrato: informação durável deve ser FACT.",
    ))
    return scenarios


# --------------------------------------------------------------------------- #
#  Baseline dispatch — identical prompt format, NO apoptosis (the control)
# --------------------------------------------------------------------------- #
class BaselineClient:
    def __init__(self) -> None:
        from openai import AsyncOpenAI
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        self._client = AsyncOpenAI(
            base_url=OPENROUTER_BASE_URL, api_key=key,
            default_headers={"HTTP-Referer": "https://bioma.ai", "X-Title": "B.I.O.M.A. QA"},
        )

    async def dispatch(self, history: list[dict], query: str, *, model: str,
                       max_tokens: int = 1000) -> tuple[str, int, float, Optional[str]]:
        """Full-context dispatch. Returns (text, in_tokens, cost_usd, error)."""
        full = "\n".join(str(m.get("content", "")) for m in history)
        prompt = f"Context:\n{full}\n\nCurrent request:\n{query}"
        delay = 1.0
        last_err = "unknown"
        for attempt in range(4):
            try:
                resp = await self._client.chat.completions.create(
                    model=model, messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens, temperature=0.0,
                    extra_body={"usage": {"include": True}},
                )
                usage = resp.usage
                in_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
                cost = getattr(usage, "cost", None)
                cost = float(cost) if isinstance(cost, (int, float)) else 0.0
                text = resp.choices[0].message.content or ""
                if not text.strip():
                    finish = resp.choices[0].finish_reason
                    return ("", in_tok, cost, f"empty response (finish={finish})")
                return (text, in_tok, cost, None)
            except Exception as exc:  # noqa: BLE001 — surface after retries
                last_err = f"{type(exc).__name__}: {exc}"
                await asyncio.sleep(delay)
                delay *= 2
        return ("", 0, 0.0, last_err)

    async def close(self) -> None:
        await self._client.close()


def probe_score(text: str, probes: list[str]) -> float:
    low = (text or "").lower()
    return sum(1 for p in probes if p.lower() in low) / len(probes)


@dataclass
class Row:
    scenario: str
    model: str
    base_score: float
    bio_score: float
    base_in: int
    bio_in: int
    reduction: float
    cost: float
    error: Optional[str] = None
    expected_degradation: bool = False


# --------------------------------------------------------------------------- #
async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=[m for m, _ in ONLINE],
                    help="OpenRouter slugs (default: the 6 online models from the universal report)")
    ap.add_argument("--rounds", type=int, default=15)
    ap.add_argument("--report", action="store_true", help="write reports/BIOMA_QUALITY_PRESERVATION.md")
    args = ap.parse_args()

    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key.startswith("sk-or"):
        print("OPENROUTER_API_KEY ausente — este teste exige dispatch real online.")
        return 2

    names = dict(ONLINE)
    scenarios = build_scenarios(args.rounds)
    lean = LeanOpenRouterClient()
    base = BaselineClient()

    print("=" * 96)
    print("  B.I.O.M.A. — Quality Preservation (baseline vs apoptose, modelos reais online)")
    print("=" * 96)
    print(f"  modelos: {len(args.models)} · cenários: {len(scenarios)} · temperatura 0.0 · probes objetivas\n")

    rows: list[Row] = []
    total_cost = 0.0
    t0 = time.perf_counter()
    try:
        for sc in scenarios:
            print(f"— {sc.key}: {sc.title}")
            for slug in args.models:
                label = names.get(slug, slug)
                b_text, b_in, b_cost, b_err = await base.dispatch(sc.history, sc.query, model=slug)
                d = await lean.dispatch(sc.history, sc.query, model=slug,
                                        system=None, max_tokens=1000, temperature=0.0)
                err = b_err or d.error
                # a provider-side refusal/empty answer measures nothing — flag the cell
                if err is None and not d.text.strip():
                    err = "empty response (bioma path)"
                bs = probe_score(b_text, sc.probes)
                os_ = probe_score(d.text, sc.probes)
                cost = b_cost + d.cost_usd
                total_cost += cost
                rows.append(Row(sc.key, label, bs, os_, b_in, d.in_tokens, d.reduction,
                                cost, err, sc.expected_degradation))
                mark = "✅" if (os_ >= bs or (sc.expected_degradation and err is None)) else "❌"
                err_s = f" ERR {err[:40]}" if err else ""
                print(f"    {mark} {label:16s} baseline {bs*100:5.1f}%  →  bioma {os_*100:5.1f}%"
                      f" | in_tok {b_in:5,} → {d.in_tokens:4,} (−{d.reduction*100:4.1f}%)"
                      f" | ${cost:.4f}{err_s}")
            print()
    finally:
        await lean.close()
        await base.close()

    # ---- aggregate verdict ------------------------------------------------- #
    ok_rows = [r for r in rows if not r.error]
    core = [r for r in ok_rows if not r.expected_degradation]          # S1 + S2
    limit = [r for r in ok_rows if r.expected_degradation]             # S3
    parity = [r for r in core if r.bio_score >= r.base_score]
    perfect = [r for r in core if r.bio_score == 1.0]
    elapsed = time.perf_counter() - t0

    print("=" * 96)
    print("## Veredito — preservação de qualidade sob apoptose (ground truth)\n")
    print("| Métrica | Valor |")
    print("| :--- | ---: |")
    print(f"| Dispatches reais (2 por célula) | {2 * len(rows)} |")
    print(f"| Células válidas (sem erro de API) | {len(ok_rows)}/{len(rows)} |")
    print(f"| S1+S2 · paridade (bioma ≥ baseline) | **{len(parity)}/{len(core)}** |")
    print(f"| S1+S2 · resposta 100% correta com BIOMA | **{len(perfect)}/{len(core)}** |")
    if core:
        avg_red = sum(r.reduction for r in core) / len(core)
        print(f"| Redução média de tokens de entrada (com paridade) | **−{avg_red*100:.1f}%** |")
    if limit:
        deg = [r for r in limit if r.bio_score < r.base_score]
        print(f"| S3 · degradação esperada observada (contrato) | {len(deg)}/{len(limit)} |")
    print(f"| Custo total da validação | ${total_cost:.4f} |")
    print(f"| Duração | {elapsed:.0f}s |")

    failures = [r for r in core if r.bio_score < r.base_score]
    if failures:
        print("\n❌ QUALIDADE PERDIDA em cenários projetados (S1/S2):")
        for r in failures:
            print(f"   - {r.scenario} · {r.model}: baseline {r.base_score*100:.0f}% → bioma {r.bio_score*100:.0f}%")
        verdict = 1
    else:
        print("\n✅ VEREDITO: nos cenários do contrato de uso (S1/S2), a resposta final com apoptose foi")
        print("   igual ou melhor que a baseline em todas as células válidas — qualidade preservada com")
        print("   a redução de tokens medida. S3 documenta o limite by design: informação durável → FACT.")
        verdict = 0

    if args.report:
        _write_report(rows, total_cost, elapsed, args.models, names)
    return verdict


def _write_report(rows: list[Row], cost: float, elapsed: float,
                  models: list[str], names: dict) -> None:
    path = os.path.join(_ROOT, "reports", "BIOMA_QUALITY_PRESERVATION.md")
    lines = [
        "# B.I.O.M.A. — Preservação de Qualidade sob Apoptose (dispatch real online)",
        "",
        "> Gerado por `tests/test_quality_preservation.py`. Ground truth: probes objetivas",
        "> (valores exatos plantados no histórico) verificadas na resposta do modelo.",
        "> Baseline = contexto completo; BIOMA = mesmo prompt após `bioma_micro.dehydrate`.",
        "",
        "| Cenário | Modelo | Baseline | BIOMA | in_tok base→BIOMA | redução | veredito |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :--- |",
    ]
    for r in rows:
        if r.error:
            v = f"⚠ erro de API: {r.error[:40]}"
        elif r.expected_degradation:
            v = "purga by design (use FACT)" if r.bio_score < r.base_score else "sobreviveu"
        else:
            v = "✅ paridade" if r.bio_score >= r.base_score else "❌ degradou"
        lines.append(f"| {r.scenario} | {r.model} | {r.base_score*100:.0f}% | {r.bio_score*100:.0f}% "
                     f"| {r.base_in:,} → {r.bio_in:,} | −{r.reduction*100:.0f}% | {v} |")
    lines += [
        "",
        f"Custo total: ${cost:.4f} · duração {elapsed:.0f}s · modelos: "
        + ", ".join(names.get(m, m) for m in models),
        "",
        "**Contrato de uso comprovado:** valores duráveis marcados como `FACT` e contexto recente",
        "sobrevivem à apoptose com resposta final íntegra; informação durável não marcada em turnos",
        "antigos é purgada por design (S3) — tague-a como `FACT`.",
        "",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n📄 relatório salvo em {path}")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
