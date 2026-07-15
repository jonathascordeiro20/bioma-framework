#!/usr/bin/env python3
"""
tests/test_vision_quality_preservation.py — apoptosis over IMAGE context, proven
on real vision models.

The question: in agent/vision sessions (screenshots, documents, vision loops),
does context apoptosis preserve answer quality while purging stale images?

## The vision adapter (the architecture under test)

The Rust kernel is content-agnostic: it weighs BLOCKS by class and recency.
The thin adapter added here (pure Python, zero kernel changes) makes it
multimodal:

1. **Blocks carry a modality** — text blocks pass through unchanged; an image
   block enters the kernel as a MARKER string (`[IMG:n]` + padding) sized to
   the provider's nominal image cost (~1,600 tokens ≈ 6,400 chars), so the
   kernel's per-dispatch audit stays truthful for media.
2. **Role policy** — screenshots/observations are `USER` blocks (recency
   decides: the freshest ~4 steps survive the half-life; older ones decay
   below the threshold and are purged). Pinned reference images (diagrams,
   spec pages) are `FACT` — never purged. Verbose text logs remain `TOOL`.
3. **Purge is all-or-nothing per image (v1)** — no downscale/caption tiers
   yet; those are declared roadmap, not claimed capability.
4. Survivor markers are mapped back to real image parts when the API payload
   is assembled (interleaved text/image content parts, order preserved).

## The proof method (same rigor as the text suite)

Probes are EXACT strings rendered INTO the pixels of synthetic screenshots
(Pillow). If the model answers them, it read the image; no LLM judge.

  V1 pinned-image  — values only visible in an early FACT-tagged diagram
                     (must survive) → parity expected.
  V2 recent-screen — values only in the LAST screenshot (survives by recency)
                     → parity expected.
  V3 stale-screen  — values only in an OLD untagged screenshot → purged BY
                     DESIGN; expected degradation, documents the contract.

Baseline = ALL images + all text (only variable is the apoptosis filter).

    python tests/test_vision_quality_preservation.py                  # 3 vision models
    python tests/test_vision_quality_preservation.py --models openai/gpt-5.5 --report
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import io
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

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import bioma_micro as kernel  # noqa: E402
from bioma.openrouter_client import OPENROUTER_BASE_URL  # noqa: E402

VISION_MODELS = [
    ("openai/gpt-5.5", "GPT-5.5"),
    ("anthropic/claude-sonnet-5", "Claude Sonnet 5"),
    ("google/gemini-3.1-pro-preview", "Gemini 3.1 Pro"),
]

IMAGE_NOMINAL_TOKENS = 1600           # declared nominal cost per image block
_SIG = {"system": kernel.SYSTEM, "user": kernel.USER, "assistant": kernel.ASSISTANT,
        "tool": kernel.TOOL, "fact": kernel.FACT}


# --------------------------------------------------------------------------- #
#  Synthetic screenshots — probes rendered into the pixels
# --------------------------------------------------------------------------- #
def make_screenshot(title: str, lines: list[str], accent: str = "#334455") -> str:
    img = Image.new("RGB", (1024, 640), "#f4f6f8")
    d = ImageDraw.Draw(img)
    try:
        f_big = ImageFont.load_default(size=52)
        f_med = ImageFont.load_default(size=42)
    except TypeError:  # very old Pillow
        f_big = f_med = ImageFont.load_default()
    d.rectangle([0, 0, 1024, 90], fill=accent)
    d.text((32, 20), title, fill="white", font=f_big)
    y = 140
    for ln in lines:
        d.text((48, y), ln, fill="#111418", font=f_med)
        y += 74
    d.rectangle([700, 480, 980, 600], outline="#8899aa", width=4)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# --------------------------------------------------------------------------- #
#  Multimodal blocks + the vision adapter over the kernel
# --------------------------------------------------------------------------- #
@dataclass
class Block:
    role: str                  # system | fact | user | assistant | tool
    kind: str                  # text | image
    content: str               # text, or data-URL for images


def kernel_filter(blocks: list[Block]) -> tuple[list[Block], dict]:
    """Run the UNCHANGED Rust kernel over mixed text/image blocks.

    Images enter as padded markers so token accounting is media-aware; the
    survivors are mapped back to the original blocks by marker identity."""
    msgs: list[tuple[str, int]] = []
    for i, b in enumerate(blocks):
        if b.kind == "image":
            marker = f"[IMG:{i}]"
            msgs.append((marker + " " * (IMAGE_NOMINAL_TOKENS * 4 - len(marker)),
                         _SIG.get(b.role, kernel.USER)))
        else:
            msgs.append((b.content, _SIG.get(b.role, kernel.USER)))
    audit = kernel.dehydrate(msgs, half_life=6.0, safe_threshold=0.35)
    kept_set = set()
    for kept in audit["kept"]:
        if kept.startswith("[IMG:"):
            kept_set.add(int(kept[5:kept.index("]")]))
        else:
            for i, b in enumerate(blocks):
                if b.kind == "text" and b.content == kept:
                    kept_set.add(i)
    survivors = [b for i, b in enumerate(blocks) if i in kept_set]
    return survivors, audit


def to_content_parts(blocks: list[Block], query: str) -> list[dict]:
    parts: list[dict] = [{"type": "text", "text": "Context (session history):"}]
    for b in blocks:
        if b.kind == "image":
            parts.append({"type": "image_url", "image_url": {"url": b.content}})
        else:
            parts.append({"type": "text", "text": f"[{b.role}] {b.content}"})
    parts.append({"type": "text", "text": f"Current request:\n{query}"})
    return parts


# --------------------------------------------------------------------------- #
#  Scenarios — an agent vision loop with planted, pixel-borne probes
# --------------------------------------------------------------------------- #
@dataclass
class Scenario:
    key: str
    title: str
    blocks: list[Block]
    query: str
    probes: list[str]
    expected_degradation: bool = False


def _noise_step(i: int) -> list[Block]:
    shot = make_screenshot(f"Monitor — step {i}",
                           [f"status: idle · ticker XZ-{i:03d}", "throughput nominal",
                            f"uptime {40 + i}h · no alerts"], accent="#3a4a5a")
    return [
        Block("user", "image", shot),
        Block("assistant", "text", f"Step {i}: screen reviewed, nothing notable."),
    ]


def build_scenarios(steps: int = 12) -> list[Scenario]:
    sys_b = Block("system", "text",
                  "You are a precise operations copilot. Answer with the exact requested values.")

    # V1 — pinned FACT diagram, planted at the very start
    diagram = make_screenshot("Network Reference Diagram",
                              ["TOPOLOGY: MESH-7", "VLAN 42", "GATEWAY 10.7.0.1"],
                              accent="#225544")
    v1_blocks = [sys_b, Block("fact", "image", diagram)]
    for i in range(1, steps + 1):
        v1_blocks += _noise_step(i)
    v1 = Scenario(
        "V1", "imagem fixada como FACT (diagrama de referência)",
        v1_blocks,
        "From the pinned reference diagram only: (1) which topology is shown? "
        "(2) which VLAN number? (3) which gateway IP? Reply with the three exact values.",
        ["MESH-7", "42", "10.7.0.1"],
    )

    # V2 — the values live in the MOST RECENT screenshot
    v2_blocks = [sys_b]
    for i in range(1, steps):
        v2_blocks += _noise_step(i)
    alert = make_screenshot("Monitor — step 12 (ALERT)",
                            ["ALERT CODE RX-509", "QUEUE DEPTH 87", "severity: high"],
                            accent="#7a3030")
    v2_blocks += [Block("user", "image", alert),
                  Block("assistant", "text", "Step 12: alert visible on screen.")]
    v2 = Scenario(
        "V2", "informação no screenshot mais recente (recência)",
        v2_blocks,
        "From the latest screenshot: what is the alert code and the queue depth? "
        "Reply with the exact values.",
        ["RX-509", "87"],
    )

    # V3 — the value only exists in an OLD, untagged screenshot
    v3_blocks = [sys_b]
    ticket = make_screenshot("Helpdesk — step 2",
                             ["OPEN TICKET INC-3341", "assigned: platform team"],
                             accent="#555a2a")
    v3_blocks += _noise_step(1)
    v3_blocks += [Block("user", "image", ticket),
                  Block("assistant", "text", "Step 2: ticket screen reviewed.")]
    for i in range(3, steps + 1):
        v3_blocks += _noise_step(i)
    v3 = Scenario(
        "V3", "screenshot ANTIGO não marcado (purga por design)",
        v3_blocks,
        "Which ticket number was open on the helpdesk screen earlier in this session? "
        "Reply with the exact value.",
        ["INC-3341"],
        expected_degradation=True,
    )
    return [v1, v2, v3]


# --------------------------------------------------------------------------- #
def probe_score(text: str, probes: list[str]) -> float:
    low = (text or "").lower()
    return sum(1 for p in probes if p.lower() in low) / len(probes)


async def dispatch(client, model: str, parts: list[dict]) -> tuple[str, int, float, Optional[str]]:
    delay = 1.0
    last = "unknown"
    for _ in range(4):
        try:
            r = await client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": parts}],
                max_tokens=1000, temperature=0.0, extra_body={"usage": {"include": True}},
            )
            u = r.usage
            in_tok = int(getattr(u, "prompt_tokens", 0) or 0)
            cost = getattr(u, "cost", None)
            cost = float(cost) if isinstance(cost, (int, float)) else 0.0
            text = r.choices[0].message.content or ""
            if not text.strip():
                return ("", in_tok, cost, f"empty (finish={r.choices[0].finish_reason})")
            return (text, in_tok, cost, None)
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {str(exc)[:60]}"
            await asyncio.sleep(delay)
            delay *= 2
    return ("", 0, 0.0, last)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=[m for m, _ in VISION_MODELS])
    ap.add_argument("--steps", type=int, default=12)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key.startswith("sk-or"):
        print("OPENROUTER_API_KEY ausente — este teste exige dispatch real online.")
        return 2

    from openai import AsyncOpenAI
    client = AsyncOpenAI(base_url=OPENROUTER_BASE_URL, api_key=key,
                         default_headers={"HTTP-Referer": "https://bioma.ai",
                                          "X-Title": "B.I.O.M.A. Vision QA"})
    names = dict(VISION_MODELS)
    scenarios = build_scenarios(args.steps)

    print("=" * 100)
    print("  B.I.O.M.A. — Vision Quality Preservation (apoptose sobre IMAGENS, modelos reais)")
    print("=" * 100)
    print(f"  modelos: {len(args.models)} · cenários: {len(scenarios)} · "
          f"{args.steps} passos de agente · probes rendidas nos pixels · temp 0.0\n")

    rows = []
    total_cost = 0.0
    t0 = time.perf_counter()
    try:
        for sc in scenarios:
            survivors, audit = kernel_filter(sc.blocks)
            imgs_all = sum(1 for b in sc.blocks if b.kind == "image")
            imgs_kept = sum(1 for b in survivors if b.kind == "image")
            print(f"— {sc.key}: {sc.title}")
            print(f"    apoptose: {len(sc.blocks)} blocos → {len(survivors)} · imagens "
                  f"{imgs_all} → {imgs_kept} · tokens nominais −{audit['reduction']*100:.1f}% "
                  f"· kernel {audit['kernel_latency_us']:.1f}μs")
            base_parts = to_content_parts(sc.blocks, sc.query)
            bio_parts = to_content_parts(survivors, sc.query)
            for slug in args.models:
                label = names.get(slug, slug)
                b_text, b_in, b_cost, b_err = await dispatch(client, slug, base_parts)
                o_text, o_in, o_cost, o_err = await dispatch(client, slug, bio_parts)
                err = b_err or o_err
                bs, os_ = probe_score(b_text, sc.probes), probe_score(o_text, sc.probes)
                cost = b_cost + o_cost
                total_cost += cost
                rows.append((sc.key, label, bs, os_, b_in, o_in, imgs_all, imgs_kept,
                             cost, err, sc.expected_degradation))
                mark = "✅" if (os_ >= bs or (sc.expected_degradation and err is None)) else "❌"
                err_s = f" ERR {err}" if err else ""
                print(f"    {mark} {label:16s} baseline {bs*100:5.1f}%  →  bioma {os_*100:5.1f}%"
                      f" | in_tok {b_in:6,} → {o_in:5,} | ${cost:.4f}{err_s}")
            print()
    finally:
        await client.close()

    ok = [r for r in rows if not r[9]]
    core = [r for r in ok if not r[10]]
    parity = [r for r in core if r[3] >= r[2]]
    perfect = [r for r in core if r[3] == 1.0]
    limit = [r for r in ok if r[10]]
    elapsed = time.perf_counter() - t0

    print("=" * 100)
    print("## Veredito — apoptose sobre contexto de IMAGENS (ground truth)\n")
    print("| Métrica | Valor |")
    print("| :--- | ---: |")
    print(f"| Dispatches reais | {2 * len(rows)} |")
    print(f"| Células válidas | {len(ok)}/{len(rows)} |")
    print(f"| V1+V2 · paridade (bioma ≥ baseline) | **{len(parity)}/{len(core)}** |")
    print(f"| V1+V2 · resposta 100% correta com BIOMA | **{len(perfect)}/{len(core)}** |")
    if core:
        red = sum(1 - r[5] / r[4] for r in core if r[4]) / len(core)
        print(f"| Redução média de tokens de entrada (usage real) | **−{red*100:.1f}%** |")
    if limit:
        deg = [r for r in limit if r[3] < r[2]]
        print(f"| V3 · purga esperada observada (contrato) | {len(deg)}/{len(limit)} |")
    print(f"| Custo total | ${total_cost:.4f} |")
    print(f"| Duração | {elapsed:.0f}s |")

    fails = [r for r in core if r[3] < r[2]]
    if fails:
        print("\n❌ QUALIDADE PERDIDA em cenários projetados (V1/V2):")
        for r in fails:
            print(f"   - {r[0]} · {r[1]}: {r[2]*100:.0f}% → {r[3]*100:.0f}%")
        verdict = 1
    else:
        print("\n✅ VEREDITO: com imagens, o contrato se mantém — referência fixada (FACT) e")
        print("   observação recente sobrevivem à apoptose com resposta íntegra; screenshots")
        print("   antigos são purgados por design (V3). Mesmo contrato do texto, agora visual.")
        verdict = 0

    if args.report:
        _write_report(rows, total_cost, elapsed)
    return verdict


def _write_report(rows, cost, elapsed) -> None:
    path = os.path.join(_ROOT, "reports", "BIOMA_VISION_QUALITY.md")
    lines = [
        "# B.I.O.M.A. — Apoptose sobre Contexto de Imagens (dispatch real, modelos com visão)",
        "",
        "> Gerado por `tests/test_vision_quality_preservation.py`. Probes = strings exatas",
        "> RENDIDAS NOS PIXELS de screenshots sintéticos; baseline = todas as imagens;",
        "> BIOMA = kernel inalterado + adaptador de visão (marcadores com custo nominal de",
        "> 1.600 tok/imagem; screenshots como USER — recência decide; referência como FACT).",
        "",
        "| Cenário | Modelo | Baseline | BIOMA | in_tok (usage real) | imagens | veredito |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :--- |",
    ]
    for (k, m, bs, os_, bi, oi, ia, ik, _c, err, deg) in rows:
        if err:
            v = f"⚠ {err[:40]}"
        elif deg:
            v = "purga by design (fixe como FACT)" if os_ < bs else "sobreviveu"
        else:
            v = "✅ paridade" if os_ >= bs else "❌ degradou"
        lines.append(f"| {k} | {m} | {bs*100:.0f}% | {os_*100:.0f}% | {bi:,} → {oi:,} "
                     f"| {ia} → {ik} | {v} |")
    lines += ["", f"Custo total: ${cost:.4f} · duração {elapsed:.0f}s", "",
              "Limites: purga tudo-ou-nada por imagem (sem tiers downscale/caption);",
              "firewall não faz OCR (segredos em pixels não são redigidos); custo nominal",
              "por imagem declarado em 1.600 tokens — os tokens reais vêm do usage da API.", ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n📄 relatório salvo em {path}")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
