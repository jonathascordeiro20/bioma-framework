#!/usr/bin/env python3
"""
tests/test_vision_distill.py — complex images: local analysis SPEED before the
LLM, and REAL-model proof of the distillation tier.

Phase A (offline, hardware ground truth): six COMPLEX image types — dense
dashboard, spreadsheet grid, bar chart, terminal log, document page, and a
geometric-shapes diagram — measured for perceptual-hash latency, OCR latency,
OCR probe recall, and token footprint (image ~1,600 tok → distilled text).

Phase B (real vision LLMs): an agent session where the probe values live ONLY
in three stale complex images. Three arms per model:
  * baseline — every image is sent;
  * purge    — apoptosis v1 (stale images dropped; the honest 0% of V3);
  * distill  — apoptosis v2 (stale images replaced by their OCR text via
               `bioma.vision.VisionDistiller`; near-duplicate frames deduped).

If distill recovers the probes at purge-level token cost, the trade-off
"purge or pay 1,600 tokens" becomes "pay ~15-100 tokens".

    python tests/test_vision_distill.py --local-only        # phase A only
    python tests/test_vision_distill.py --report            # A + B (3 models)
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import io
import os
import sys
import time

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

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from bioma.vision import VisionDistiller, distill_block_text  # noqa: E402
from test_vision_quality_preservation import (  # noqa: E402
    Block, IMAGE_NOMINAL_TOKENS, VISION_MODELS, _noise_step, dispatch,
    kernel_filter, make_screenshot, probe_score, to_content_parts)


# --------------------------------------------------------------------------- #
#  Six complex image forms, probes rendered into the pixels
# --------------------------------------------------------------------------- #
def _fonts():
    try:
        return (ImageFont.load_default(size=34), ImageFont.load_default(size=22),
                ImageFont.load_default(size=26))
    except TypeError:
        f = ImageFont.load_default()
        return f, f, f


def _encode(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def img_dashboard() -> tuple[str, list[str]]:
    """Dense 3×4 metric grid, small fonts — the hard screenshot case."""
    img = Image.new("RGB", (1024, 640), "#eef1f4")
    d = ImageDraw.Draw(img)
    big, small, med = _fonts()
    d.rectangle([0, 0, 1024, 64], fill="#1f2937")
    d.text((24, 14), "Ops Dashboard — prod-east", fill="white", font=big)
    cells = [("CPU", "91%"), ("MEM", "68%"), ("DISK", "54%"), ("NET", "1.2Gb/s"),
             ("p50", "120ms"), ("p95", "410ms"), ("p99", "842ms"), ("RPS", "3.4k"),
             ("errors", "ERR-2210"), ("retries", "312"), ("pods", "48/50"), ("SLO", "99.2%")]
    for i, (k, v) in enumerate(cells):
        x, y = 24 + (i % 4) * 248, 92 + (i // 4) * 172
        d.rectangle([x, y, x + 224, y + 148], fill="white", outline="#c5ccd4", width=2)
        d.text((x + 14, y + 12), k, fill="#6b7280", font=small)
        d.text((x + 14, y + 56), v, fill="#111827", font=med)
    return _encode(img), ["91", "842", "ERR-2210"]


def img_table() -> tuple[str, list[str]]:
    """Spreadsheet grid with 8 rows of orders."""
    img = Image.new("RGB", (1024, 640), "white")
    d = ImageDraw.Draw(img)
    big, small, med = _fonts()
    d.text((24, 16), "Pedidos — julho/2026", fill="#111827", font=big)
    headers = ["pedido", "valor", "status", "canal"]
    rows = [("ORD-5510", "R$ 88,00", "pago", "web"), ("ORD-5512", "R$ 240,10", "pago", "app"),
            ("ORD-5514", "R$ 55,90", "envio", "web"), ("ORD-5519", "R$ 1.204,77", "pendente", "b2b"),
            ("ORD-5521", "R$ 310,00", "pago", "app"), ("ORD-5523", "R$ 99,90", "pago", "web"),
            ("ORD-5527", "R$ 178,30", "envio", "app"), ("ORD-5530", "R$ 64,25", "pago", "web")]
    for c, h in enumerate(headers):
        d.rectangle([24 + c * 244, 80, 24 + (c + 1) * 244, 128], fill="#e5e7eb", outline="#9ca3af")
        d.text((36 + c * 244, 92), h, fill="#374151", font=small)
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            y = 128 + r * 56
            d.rectangle([24 + c * 244, y, 24 + (c + 1) * 244, y + 56], outline="#d1d5db")
            d.text((36 + c * 244, y + 14), val, fill="#111827", font=small)
    return _encode(img), ["ORD-5519", "1.204,77"]


def img_chart() -> tuple[str, list[str]]:
    """Bar chart with value labels on the caps."""
    img = Image.new("RGB", (1024, 640), "white")
    d = ImageDraw.Draw(img)
    big, small, med = _fonts()
    d.text((24, 16), "Vendas por SKU — 2026-Q3", fill="#111827", font=big)
    data = [("SKU-81", 240), ("SKU-83", 385), ("SKU-85", 172), ("SKU-88", 610),
            ("SKU-90", 455), ("SKU-92", 298)]
    for i, (k, v) in enumerate(data):
        x = 80 + i * 155
        h = int(v * 0.7)
        d.rectangle([x, 560 - h, x + 96, 560], fill="#2f6f4f")
        d.text((x + 10, 560 - h - 36), str(v), fill="#111827", font=med)
        d.text((x, 576), k, fill="#374151", font=small)
    d.line([60, 560, 1000, 560], fill="#9ca3af", width=3)
    return _encode(img), ["SKU-88", "610"]


def img_terminal() -> tuple[str, list[str]]:
    """Dark terminal with log lines — low contrast, mono-ish."""
    img = Image.new("RGB", (1024, 640), "#0d1117")
    d = ImageDraw.Draw(img)
    big, small, med = _fonts()
    lines = ["$ kubectl get pods -n prod", "worker-1   Running   14d",
             "worker-2   Running   14d", "worker-3   CrashLoopBackOff   2m",
             "$ kubectl logs worker-3 --tail=3", "level=warn msg=backpressure queue=full",
             "level=error msg=oom killed", "FATAL worker-3 exit=137"]
    y = 40
    for ln in lines:
        color = "#e6edf3" if not ln.startswith("$") else "#7ee787"
        if "FATAL" in ln or "error" in ln:
            color = "#ff7b72"
        d.text((36, y), ln, fill=color, font=med)
        y += 68
    return _encode(img), ["worker-3", "137"]


def img_document() -> tuple[str, list[str]]:
    """Document page with paragraph text."""
    img = Image.new("RGB", (1024, 640), "#fbfaf7")
    d = ImageDraw.Draw(img)
    big, small, med = _fonts()
    d.text((60, 40), "ADITIVO CONTRATUAL", fill="#111827", font=big)
    para = ["Pelo presente instrumento, as partes resolvem aditar o",
            "contrato nº CT-2044-B, firmado em 12/03/2026, para",
            "prorrogar sua vigência até 31/12/2027, mantidas as",
            "demais cláusulas. O valor mensal passa a ser de",
            "R$ 14.500,00 (quatorze mil e quinhentos reais),",
            "com reajuste anual pelo IPCA."]
    y = 130
    for ln in para:
        d.text((60, y), ln, fill="#1f2937", font=med)
        y += 62
    return _encode(img), ["CT-2044-B", "14.500,00"]


def img_shapes() -> tuple[str, list[str]]:
    """Geometric-shapes diagram with labels — the 'formas' case."""
    img = Image.new("RGB", (1024, 640), "white")
    d = ImageDraw.Draw(img)
    big, small, med = _fonts()
    d.text((24, 16), "Fluxo de aprovação", fill="#111827", font=big)
    d.ellipse([80, 140, 300, 300], outline="#2f6f4f", width=5)
    d.text((128, 196), "NODE-A7", fill="#111827", font=med)
    d.polygon([(470, 140), (620, 300), (320, 300)], outline="#8a4f2f", width=5)
    d.text((420, 236), "GATE-3", fill="#111827", font=med)
    d.rectangle([720, 160, 960, 290], outline="#2f4f8a", width=5)
    d.text((766, 204), "SINK-11", fill="#111827", font=med)
    d.line([300, 220, 380, 220], fill="#374151", width=4)
    d.line([620, 220, 720, 220], fill="#374151", width=4)
    d.text((80, 420), "regra: aprovações acima de R$ 5.000 passam por GATE-3", fill="#374151", font=med)
    return _encode(img), ["NODE-A7", "GATE-3", "SINK-11"]


FORMS = [("dashboard denso", img_dashboard), ("tabela/planilha", img_table),
         ("gráfico de barras", img_chart), ("terminal escuro", img_terminal),
         ("documento", img_document), ("diagrama de formas", img_shapes)]


# --------------------------------------------------------------------------- #
#  Phase A — local speed & recall per form
# --------------------------------------------------------------------------- #
def phase_a() -> list[dict]:
    print("## Fase A — análise local ANTES do LLM (velocidade e recall por forma)\n")
    dist = VisionDistiller()
    warm = make_screenshot("warmup", ["warmup"])
    dist.distill(warm)  # load OCR model off the record
    dist.is_duplicate(warm)
    out = []
    print("| Forma | pHash | OCR (warm) | Recall OCR | Tokens img→texto |")
    print("| :--- | ---: | ---: | :---: | ---: |")
    for name, builder in FORMS:
        url, probes = builder()
        _, hash_ms = dist.is_duplicate(url)
        d = dist.distill(url)
        hits = [p for p in probes if p.lower() in d.text.lower()]
        out.append({"forma": name, "hash_ms": hash_ms, "ocr_ms": d.ocr_ms,
                    "recall": f"{len(hits)}/{len(probes)}", "hits": hits,
                    "probes": probes, "tokens": d.est_tokens, "url": url})
        print(f"| {name} | {hash_ms:.0f} ms | {d.ocr_ms:,.0f} ms | {len(hits)}/{len(probes)} "
              f"| {IMAGE_NOMINAL_TOKENS:,} → {d.est_tokens} (−{(1-d.est_tokens/IMAGE_NOMINAL_TOKENS)*100:.0f}%) |")
    for r in out:
        missing = [p for p in r["probes"] if p not in r["hits"]]
        if missing:
            print(f"  ⚠ {r['forma']}: OCR não leu {missing}")
    print()
    return out


# --------------------------------------------------------------------------- #
#  Phase B — real vision LLMs: baseline vs purge vs distill
# --------------------------------------------------------------------------- #
QUERY = ("From earlier screens in this session: (1) which error code was on the ops "
         "dashboard? (2) which order id had value R$ 1.204,77? (3) which label is inside "
         "the circle of the approval-flow diagram? Reply with the three exact values.")
PROBES = ["ERR-2210", "ORD-5519", "NODE-A7"]


def build_session(steps: int = 12) -> list[Block]:
    blocks = [Block("system", "text",
                    "You are a precise operations copilot. Answer with the exact requested values.")]
    dash, _ = img_dashboard()
    table, _ = img_table()
    shapes, _ = img_shapes()
    blocks += _noise_step(1)
    blocks += [Block("user", "image", dash),
               Block("assistant", "text", "Step 2: dashboard reviewed.")]
    blocks += [Block("user", "image", table),
               Block("assistant", "text", "Step 3: orders table reviewed.")]
    blocks += [Block("user", "image", shapes),
               Block("assistant", "text", "Step 4: approval diagram reviewed.")]
    for i in range(5, steps + 1):
        blocks += _noise_step(i)
    # a near-duplicate pair for the dedup stage (same idle screen twice)
    dup = make_screenshot("Monitor — idle", ["status: idle", "throughput nominal", "no alerts"])
    blocks += [Block("user", "image", dup), Block("assistant", "text", "idle."),
               Block("user", "image", dup), Block("assistant", "text", "still idle.")]
    return blocks


def build_arms(blocks: list[Block]) -> dict[str, tuple[list[Block], dict]]:
    # v1 purge — the unchanged kernel adapter
    survivors, audit = kernel_filter(blocks)
    kept_ids = {id(b) for b in survivors}

    # v2 distill — batch dedup with the KEEP-LATEST policy, then distill purged
    # images (OCR + local-VLM caption for structure-bearing ones) instead of dropping
    dist = VisionDistiller()
    img_idx = [i for i, b in enumerate(blocks) if b.kind == "image"]
    keep_rel = dist.dedup_keep_latest([blocks[i].content for i in img_idx])
    keep_img_ids = {id(blocks[img_idx[r]]) for r in keep_rel}

    stats = {"distilled": 0, "distill_ms": 0.0, "distill_tokens": 0,
             "captioned": 0, "dedup_dropped": len(img_idx) - len(keep_rel)}
    v2: list[Block] = []
    for b in blocks:
        if b.kind == "image" and id(b) not in keep_img_ids:
            continue  # near-duplicate; a newer member of its cluster survives
        if id(b) in kept_ids:
            v2.append(b)
        elif b.kind == "image":
            d = dist.distill_rich(b.content)
            stats["distilled"] += 1
            stats["distill_ms"] += d.ocr_ms
            stats["distill_tokens"] += d.est_tokens
            if "descrição visual:" in d.text:
                stats["captioned"] += 1
            v2.append(Block("user", "text", distill_block_text("tela anterior da sessão", d)))
    return {"baseline": (blocks, {}), "purge": (survivors, audit), "distill": (v2, stats)}


async def phase_b(models: list[str], report_rows: list) -> tuple[int, float]:
    from openai import AsyncOpenAI
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key.startswith("sk-or"):
        print("OPENROUTER_API_KEY ausente — fase B pulada.")
        return 2, 0.0
    from bioma.openrouter_client import OPENROUTER_BASE_URL
    client = AsyncOpenAI(base_url=OPENROUTER_BASE_URL, api_key=key,
                         default_headers={"HTTP-Referer": "https://bioma.ai",
                                          "X-Title": "B.I.O.M.A. Vision Distill"})
    names = dict(VISION_MODELS)
    blocks = build_session()
    arms = build_arms(blocks)
    n_img = {k: sum(1 for b in v[0] if b.kind == "image") for k, v in arms.items()}
    st = arms["distill"][1]
    print("## Fase B — LLMs reais: baseline vs purga (v1) vs destilação (v2)\n")
    print(f"  sessão: {len(blocks)} blocos · imagens por braço: baseline {n_img['baseline']} · "
          f"purga {n_img['purge']} · destilação {n_img['distill']} "
          f"(+{st['distilled']} destiladas ≈ {st['distill_tokens']} tok, "
          f"{st['captioned']} com caption VLM, {st['distill_ms']/1000:.1f}s em background, "
          f"{st['dedup_dropped']} dedup keep-latest)\n")

    total_cost, fails = 0.0, 0
    try:
        for slug in models:
            label = names.get(slug, slug)
            scores = {}
            for arm, (arm_blocks, _) in arms.items():
                parts = to_content_parts(arm_blocks, QUERY)
                text, in_tok, cost, err = await dispatch(client, slug, parts)
                total_cost += cost
                s = probe_score(text, PROBES)
                scores[arm] = s
                report_rows.append((label, arm, s, in_tok, cost, err))
                err_s = f" ERR {err}" if err else ""
                print(f"    {label:16s} {arm:9s} | probes {s*100:5.1f}% | in_tok {in_tok:6,} "
                      f"| ${cost:.4f}{err_s}")
            if scores.get("distill", 0) < scores.get("baseline", 0):
                fails += 1
            print()
    finally:
        await client.close()
    return fails, total_cost


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=[m for m, _ in VISION_MODELS])
    ap.add_argument("--local-only", action="store_true")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    print("=" * 100)
    print("  B.I.O.M.A. — Destilação de Imagens Complexas (velocidade local + prova em LLMs reais)")
    print("=" * 100 + "\n")

    a_rows = phase_a()
    rows_b: list = []
    if not args.local_only:
        fails, cost = await phase_b(args.models, rows_b)
        print(f"  custo fase B: ${cost:.4f}")
        verdict = 0 if fails == 0 else 1
    else:
        verdict = 0

    if args.report:
        path = os.path.join(_ROOT, "reports", "BIOMA_VISION_DISTILL.md")
        lines = ["# B.I.O.M.A. — Destilação de Imagens Complexas (fase local + LLMs reais)", "",
                 "> Gerado por `tests/test_vision_distill.py`. Fase A: análise local client-side",
                 "> (pHash + RapidOCR/ONNX, CPU) sobre 6 formas complexas. Fase B: dispatch real,",
                 "> braços baseline / purga (v1) / destilação (v2).", "",
                 "## Fase A — velocidade e recall por forma", "",
                 "| Forma | pHash | OCR (warm) | Recall | Tokens img→texto |",
                 "| :--- | ---: | ---: | :---: | ---: |"]
        for r in a_rows:
            lines.append(f"| {r['forma']} | {r['hash_ms']:.0f} ms | {r['ocr_ms']:,.0f} ms "
                         f"| {r['recall']} | 1.600 → {r['tokens']} |")
        if rows_b:
            lines += ["", "## Fase B — LLMs reais (probes nas imagens antigas da sessão)", "",
                      "| Modelo | Braço | Probes | in_tok (usage) | Custo |",
                      "| :--- | :--- | :---: | ---: | ---: |"]
            for (m, arm, s, tok, c, err) in rows_b:
                e = f" ⚠ {err[:30]}" if err else ""
                lines.append(f"| {m} | {arm} | {s*100:.0f}%{e} | {tok:,} | ${c:.4f} |")
        lines += ["", "Limites: OCR roda fora do hot path (lazy, uma vez por imagem); recall",
                  "depende da forma (medido acima); destilação é lossy para conteúdo",
                  "não-textual — caption por VLM local é o próximo tier.", ""]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"\n📄 relatório salvo em {path}")
    return verdict


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
