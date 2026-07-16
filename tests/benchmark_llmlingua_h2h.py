#!/usr/bin/env python3
"""
tests/benchmark_llmlingua_h2h.py — BIOMA vs LLMLingua-2, head-to-head honesto.

MESMO dataset (os cenários S1/S2/S3 com probes objetivas de
`test_quality_preservation.py`), MESMAS métricas (acurácia de probes, tokens de
entrada reportados pelo provider, redução vs baseline, latência de compressão,
custo), MESMO template de prompt e temperatura 0.0 em todos os braços:

  * baseline  — histórico completo (controle);
  * bioma     — `bioma_micro.dehydrate` via `LeanOpenRouterClient` (caminho de produção);
  * llmlingua — LLMLingua-2 comprimindo o MESMO histórico com o MESMO orçamento
                de tokens que a apoptose atingiu (`target_token` pareado) —
                apples-to-apples no nível de compressão, não só no dataset.

A compressão roda UMA vez por cenário (ambos os filtros são determinísticos e
independentes do modelo); o resultado é despachado a cada modelo online.

    python tests/benchmark_llmlingua_h2h.py                    # 2 modelos default
    python tests/benchmark_llmlingua_h2h.py --compress-only    # só compressão local, $0
    python tests/benchmark_llmlingua_h2h.py --report           # escreve reports/ + resultados/
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
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
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

from bioma.openrouter_client import LeanOpenRouterClient  # noqa: E402
from tests.test_quality_preservation import (  # noqa: E402 — o MESMO dataset e scoring
    BaselineClient, Scenario, build_scenarios, probe_score,
)

DEFAULT_MODELS = ["openai/gpt-5.5", "anthropic/claude-sonnet-5"]
NAMES = {"openai/gpt-5.5": "GPT-5.5", "anthropic/claude-sonnet-5": "Claude Sonnet 5",
         "google/gemini-3.1-pro-preview": "Gemini 3.1 Pro"}
LLMLINGUA_MODEL = "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank"


# --------------------------------------------------------------------------- #
#  Compression arms — both deterministic, run once per scenario
# --------------------------------------------------------------------------- #
@dataclass
class Compression:
    arm: str
    text: str                 # o contexto comprimido, pronto para o template
    est_tokens_before: int
    est_tokens_after: int
    latency_ms: float         # wall-clock da decisão/compressão
    detail: dict


def bioma_compress(lean: LeanOpenRouterClient, history: list[dict]) -> Compression:
    t0 = time.perf_counter()
    audit = lean.apoptosis(history)
    wall_ms = (time.perf_counter() - t0) * 1000.0
    return Compression(
        arm="bioma",
        text="\n".join(audit["kept"]),
        est_tokens_before=int(audit["tokens_before"]),
        est_tokens_after=int(audit["tokens_after"]),
        latency_ms=wall_ms,
        detail={"kernel_latency_us": float(audit["kernel_latency_us"]),
                "blocks_purged": int(audit["blocks_purged"]),
                "half_life": lean.half_life, "safe_threshold": lean.safe_threshold},
    )


def llmlingua_compress(compressor, history: list[dict], target_token: int) -> Compression:
    docs = [str(m.get("content", "")) for m in history]
    t0 = time.perf_counter()
    res = compressor.compress_prompt(
        docs, target_token=max(target_token, 1), force_tokens=["\n", ":", "?", "."],
    )
    wall_ms = (time.perf_counter() - t0) * 1000.0
    return Compression(
        arm="llmlingua",
        text=res["compressed_prompt"],
        est_tokens_before=int(res.get("origin_tokens", 0)),
        est_tokens_after=int(res.get("compressed_tokens", 0)),
        latency_ms=wall_ms,
        detail={k: res[k] for k in ("origin_tokens", "compressed_tokens", "rate", "saving")
                if k in res},
    )


# --------------------------------------------------------------------------- #
@dataclass
class Cell:
    scenario: str
    model: str
    arm: str                  # baseline | bioma | llmlingua
    score: float              # fração de probes acertadas (mesma métrica p/ todos)
    in_tokens: int            # prompt_tokens reportado pelo provider (canônico)
    reduction_vs_baseline: float
    compress_ms: float
    cost_usd: float
    error: Optional[str] = None
    expected_degradation: bool = False


async def dispatch_text(base: BaselineClient, context_text: str, query: str,
                        model: str) -> tuple[str, int, float, Optional[str]]:
    """Mesmo template/caminho do baseline: history de 1 bloco = contexto comprimido."""
    return await base.dispatch([{"content": context_text}], query, model=model)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=DEFAULT_MODELS)
    ap.add_argument("--rounds", type=int, default=15)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--llmlingua-model", default=LLMLINGUA_MODEL)
    ap.add_argument("--compress-only", action="store_true",
                    help="só a fase local de compressão (sem dispatch, custo $0)")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    scenarios = build_scenarios(args.rounds)
    lean = LeanOpenRouterClient()

    print("=" * 96)
    print("  B.I.O.M.A. vs LLMLingua-2 — head-to-head (mesmo dataset, mesmas métricas)")
    print("=" * 96)

    print(f"  carregando LLMLingua-2 ({args.llmlingua_model}) em {args.device} ...")
    t0 = time.perf_counter()
    from llmlingua import PromptCompressor
    compressor = PromptCompressor(model_name=args.llmlingua_model,
                                  use_llmlingua2=True, device_map=args.device)
    print(f"  modelo carregado em {time.perf_counter() - t0:.1f}s\n")

    # ---- fase 1: compressão local (determinística, 1x por cenário) --------- #
    comps: dict[str, dict[str, Compression]] = {}
    for sc in scenarios:
        cb = bioma_compress(lean, sc.history)
        cl = llmlingua_compress(compressor, sc.history, target_token=cb.est_tokens_after)
        comps[sc.key] = {"bioma": cb, "llmlingua": cl}
        print(f"— {sc.key}: {sc.title}")
        print(f"    bioma     {cb.est_tokens_before:6,} → {cb.est_tokens_after:5,} tok (est) "
              f"| decisão {cb.detail['kernel_latency_us']:8.1f} µs (kernel) · {cb.latency_ms:8.2f} ms (wall)")
        print(f"    llmlingua {cl.est_tokens_before:6,} → {cl.est_tokens_after:5,} tok (próprio tokenizer) "
              f"| compressão {cl.latency_ms:11.0f} ms  (budget pareado = {cb.est_tokens_after})")

    if args.compress_only:
        await lean.close()
        print("\n(--compress-only: sem dispatch online)")
        return 0

    # ---- fase 2: dispatch online — mesmos modelos, mesma métrica ----------- #
    base = BaselineClient()
    cells: list[Cell] = []
    total_cost = 0.0
    t0 = time.perf_counter()
    try:
        for sc in scenarios:
            print(f"\n— dispatch {sc.key} ...")
            for slug in args.models:
                label = NAMES.get(slug, slug)
                # baseline (controle)
                b_text, b_in, b_cost, b_err = await base.dispatch(sc.history, sc.query, model=slug)
                bs = probe_score(b_text, sc.probes)
                cells.append(Cell(sc.key, label, "baseline", bs, b_in, 0.0, 0.0, b_cost, b_err,
                                  sc.expected_degradation))
                total_cost += b_cost
                # braços comprimidos — mesmo template, mesmo caminho de dispatch
                row = {"baseline": (bs, b_in)}
                for arm in ("bioma", "llmlingua"):
                    c = comps[sc.key][arm]
                    text, in_tok, cost, err = await dispatch_text(base, c.text, sc.query, slug)
                    if err is None and not text.strip():
                        err = f"empty response ({arm})"
                    s = probe_score(text, sc.probes)
                    red = 1.0 - (in_tok / b_in) if b_in else 0.0
                    cells.append(Cell(sc.key, label, arm, s, in_tok, red, c.latency_ms, cost,
                                      err, sc.expected_degradation))
                    total_cost += cost
                    row[arm] = (s, in_tok)
                (bs_, bi), (os_, oi), (ls_, li) = row["baseline"], row["bioma"], row["llmlingua"]
                print(f"    {label:16s} baseline {bs_*100:5.1f}% ({bi:6,} tok) | "
                      f"bioma {os_*100:5.1f}% ({oi:5,} tok) | llmlingua {ls_*100:5.1f}% ({li:5,} tok)")
    finally:
        await lean.close()
        await base.close()
    elapsed = time.perf_counter() - t0

    # ---- veredito ----------------------------------------------------------- #
    ok = [c for c in cells if not c.error]
    core = [c for c in ok if not c.expected_degradation]
    by = lambda arm: [c for c in core if c.arm == arm]  # noqa: E731
    print("\n" + "=" * 96)
    print("## Veredito head-to-head (S1+S2 = contrato de uso; S3 reportado à parte)\n")
    print("| Métrica (S1+S2) | baseline | BIOMA | LLMLingua-2 |")
    print("| :--- | ---: | ---: | ---: |")
    for name, f in [("Acurácia média de probes", lambda cs: f"{sum(c.score for c in cs)/len(cs)*100:.1f}%" if cs else "—"),
                    ("Tokens de entrada médios (provider)", lambda cs: f"{sum(c.in_tokens for c in cs)/len(cs):,.0f}" if cs else "—"),
                    ("Redução média vs baseline", lambda cs: f"−{sum(c.reduction_vs_baseline for c in cs)/len(cs)*100:.1f}%" if cs else "—"),
                    ("Latência de compressão (mediana)", lambda cs: f"{sorted(c.compress_ms for c in cs)[len(cs)//2]:,.2f} ms" if cs else "—")]:
        print(f"| {name} | {f(by('baseline'))} | {f(by('bioma'))} | {f(by('llmlingua'))} |")
    s3 = [c for c in ok if c.expected_degradation]
    if s3:
        arm_s3 = lambda a: [c for c in s3 if c.arm == a]  # noqa: E731
        fmt = lambda cs: f"{sum(c.score for c in cs)/len(cs)*100:.0f}%" if cs else "—"  # noqa: E731
        print(f"\nS3 (fato antigo NÃO marcado — limite declarado do BIOMA): baseline {fmt(arm_s3('baseline'))} · "
              f"BIOMA {fmt(arm_s3('bioma'))} · LLMLingua {fmt(arm_s3('llmlingua'))}")
    print(f"\nCusto total: ${total_cost:.4f} · dispatch {elapsed:.0f}s · células com erro: "
          f"{len(cells) - len(ok)}/{len(cells)}")

    if args.report:
        _write(cells, comps, scenarios, args, total_cost)
    return 0


def _write(cells: list[Cell], comps, scenarios: list[Scenario], args, cost: float) -> None:
    raw = os.path.join(_ROOT, "resultados", "llmlingua_h2h.json")
    with open(raw, "w", encoding="utf-8") as f:
        json.dump({
            "dataset": f"tests/test_quality_preservation.build_scenarios({args.rounds})",
            "llmlingua_model": args.llmlingua_model, "device": args.device,
            "budget_pairing": "llmlingua target_token = bioma est_tokens_after",
            "compressions": {k: {a: asdict(c) | {"text": c.text[:400] + "..."}
                                 for a, c in v.items()} for k, v in comps.items()},
            "cells": [asdict(c) for c in cells], "total_cost_usd": cost,
        }, f, ensure_ascii=False, indent=2)

    path = os.path.join(_ROOT, "reports", "BIOMA_VS_LLMLINGUA.md")
    ok = [c for c in cells if not c.error]
    lines = [
        "# B.I.O.M.A. vs LLMLingua-2 — head-to-head auditável",
        "",
        "> Mesmo dataset (probes objetivas de `test_quality_preservation.py`), mesmas métricas,",
        "> mesmo template de prompt, temperatura 0.0, orçamento de compressão PAREADO",
        f"> (LLMLingua `target_token` = tokens pós-apoptose). LLMLingua-2: `{args.llmlingua_model}`",
        f"> em `{args.device}`. Dados brutos: `resultados/llmlingua_h2h.json`.",
        "",
        "| Cenário | Modelo | Braço | Probes | in_tok | vs baseline | compressão |",
        "| :--- | :--- | :--- | ---: | ---: | ---: | ---: |",
    ]
    for c in cells:
        v = f"⚠ {c.error[:36]}" if c.error else f"{c.score*100:.0f}%"
        red = "—" if c.arm == "baseline" else f"−{c.reduction_vs_baseline*100:.1f}%"
        comp = "—" if c.arm == "baseline" else (
            f"{c.compress_ms:,.2f} ms" if c.arm == "llmlingua" else f"{c.compress_ms:.2f} ms")
        lines.append(f"| {c.scenario} | {c.model} | {c.arm} | {v} | {c.in_tokens:,} | {red} | {comp} |")
    kb = comps["S1"]["bioma"].detail["kernel_latency_us"]
    lines += [
        "",
        f"Custo total dos dispatches: ${cost:.4f}. Latência de decisão do kernel BIOMA: "
        f"~{kb:.0f} µs (Rust puro) vs compressão LLMLingua-2 em ordem de segundos (CPU).",
        "",
        "Leitura honesta: LLMLingua comprime token a token (preserva conteúdo diluído em",
        "qualquer posição); BIOMA purga blocos inteiros por classe+recência (µs, zero modelo).",
        "S3 mede exatamente essa diferença de design — reporte-a, não a esconda.",
        "",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n📄 relatório: {path}\n📄 dados brutos: {raw}")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
