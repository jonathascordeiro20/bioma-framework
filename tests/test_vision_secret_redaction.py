#!/usr/bin/env python3
"""
tests/test_vision_secret_redaction.py — fechar a lacuna que nós mesmos declaramos:
segredos visíveis em PIXELS passavam pelo firewall (que só vê texto).

Fase A (offline, determinística): renderiza um screenshot com chaves reais-shaped
(AWS AKIA…, OpenAI sk-…) nos pixels, roda `redact_secrets`, faz OCR do resultado
e confirma que as chaves SUMIRAM da imagem redigida.

Fase B (modelo de visão REAL): manda a imagem ORIGINAL a um modelo com visão
perguntando a chave → o modelo LÊ (a lacuna é real); manda a REDIGIDA → o modelo
NÃO consegue ler (a lacuna está fechada). Medido, não presumido.

    python tests/test_vision_secret_redaction.py            # A + B (1 modelo)
    python tests/test_vision_secret_redaction.py --local-only
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import io
import os
import sys

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

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from bioma.vision import VisionDistiller  # noqa: E402

AWS_KEY = "AKIA9F3XQ2M7ZP1TDLC8"
OAI_KEY = "sk-proj-9x2Kd7Qa1mZv8Lp3Rt6Wy0Bn4Hc5Jf2Es"


def make_secret_screenshot() -> str:
    img = Image.new("RGB", (1024, 480), "#0d1117")
    d = ImageDraw.Draw(img)
    try:
        big = ImageFont.load_default(size=30)
        med = ImageFont.load_default(size=26)
    except TypeError:
        big = med = ImageFont.load_default()
    d.rectangle([0, 0, 1024, 70], fill="#161b22")
    d.text((28, 20), "~/.aws/credentials  ·  deploy console", fill="#e6edf3", font=big)
    rows = [("region", "us-east-1"),
            ("aws_access_key_id", AWS_KEY),
            ("OPENAI_API_KEY", OAI_KEY),
            ("status", "authenticated ✓")]
    y = 110
    for k, v in rows:
        d.text((40, y), f"{k} =", fill="#8b949e", font=med)
        d.text((430, y), v, fill="#79c0ff", font=med)
        y += 80
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def phase_a() -> str:
    print("## Fase A — redação de segredos em pixels (offline)\n")
    dist = VisionDistiller()
    original = make_secret_screenshot()
    scan = dist.scan_secrets(original)
    print(f"  segredos detectados na imagem: {len(scan.findings)} "
          f"({', '.join(f.kind for f in scan.findings)}) em {scan.ocr_ms:.0f}ms")
    redacted, _ = dist.redact_secrets(original)
    # OCR do resultado: as chaves não podem mais aparecer
    after = dist.scan_secrets(redacted)
    ocr_text = " ".join(f.text for f in after.findings)
    aws_gone = AWS_KEY not in ocr_text
    oai_gone = OAI_KEY not in ocr_text
    # verificação direta: OCR completo da imagem redigida não contém as chaves
    full = dist.distill(redacted).text
    aws_gone = aws_gone and AWS_KEY not in full
    oai_gone = oai_gone and OAI_KEY not in full
    print(f"  após redação · AWS key sumiu: {'SIM' if aws_gone else 'NÃO'} · "
          f"OpenAI key sumiu: {'SIM' if oai_gone else 'NÃO'}")
    print(f"  {'✅' if (aws_gone and oai_gone) else '❌'} chaves mascaradas nos pixels\n")
    return redacted


async def phase_b(redacted: str, model: str) -> None:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key.startswith("sk-or"):
        print("  (fase B pulada — OPENROUTER_API_KEY ausente)")
        return
    from openai import AsyncOpenAI
    from bioma.openrouter_client import OPENROUTER_BASE_URL
    client = AsyncOpenAI(base_url=OPENROUTER_BASE_URL, api_key=key)
    original = make_secret_screenshot()
    # A benign TRANSCRIPTION request (not "give me the secret") — this measures
    # whether the model can READ the pixels, without tripping models' own refusal
    # to reveal credentials. If the key shows up in a plain transcript, the model
    # read it from the image; after redaction it cannot.
    q = ("Transcribe every line of text visible in this screenshot, exactly as "
         "shown, one line per row. Output only the transcription.")

    async def ask(img: str) -> str:
        r = await client.chat.completions.create(
            model=model, max_tokens=120, temperature=0.0,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": q},
                {"type": "image_url", "image_url": {"url": img}}]}])
        return (r.choices[0].message.content or "")

    print("## Fase B — modelo de visão real (a lacuna é real? está fechada?)\n")
    orig_ans = await ask(original)
    red_ans = await ask(redacted)
    await client.close()
    # partial-match tolerant: models may transcribe with minor spacing, so check
    # a distinctive substring of each key too
    def read(ans: str) -> bool:
        return (AWS_KEY in ans or OAI_KEY in ans
                or AWS_KEY[:12] in ans or OAI_KEY[:14] in ans)
    leaked_orig = read(orig_ans)
    leaked_red = read(red_ans)
    print(f"  imagem ORIGINAL → modelo transcreveu a chave: {'SIM (lacuna real)' if leaked_orig else 'não'}")
    print(f"    transcrição: {orig_ans[:120]!r}")
    print(f"  imagem REDIGIDA → modelo transcreveu a chave: {'SIM ❌' if leaked_red else 'NÃO ✅'}")
    print(f"    transcrição: {red_ans[:120]!r}")
    print()
    if leaked_orig and not leaked_red:
        print("  ✅ VEREDITO: a lacuna era real (o modelo lê pixels) e foi FECHADA — o")
        print("     segredo mascarado não chega ao modelo. Firewall agora enxerga pixels.")
    elif not leaked_orig:
        print("  ⚠ o modelo não leu nem a original (OCR do modelo falhou) — inconclusivo.")
    else:
        print("  ❌ o segredo vazou mesmo na redigida — investigar.")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="openai/gpt-5.5")
    ap.add_argument("--local-only", action="store_true")
    args = ap.parse_args()
    print("=" * 92)
    print("  B.I.O.M.A. — Redação de Segredos em Pixels (fechando a lacuna declarada)")
    print("=" * 92 + "\n")
    redacted = phase_a()
    if not args.local_only:
        await phase_b(redacted, args.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
