"""
`bioma/vision.py` — the semantic-dehydration tier for image context.

Extends context apoptosis to multimodal sessions with two client-side,
offline stages (no image ever leaves the machine to be "analyzed"):

1. **Perceptual dedup** (`imagehash` pHash, milliseconds): a screenshot that is
   a near-duplicate of a previous one carries no new signal — it is dropped
   before it ever costs context tokens. The multimodal `saturation_scan`.
2. **Lazy distillation** (RapidOCR, ONNX, CPU, ~1-3s/image): an image block
   that is AGING toward the purge threshold is distilled ONCE, off the hot
   path — its pixels are replaced by the extracted text (~15-100 tokens vs
   ~1,600 for the image). The distilled text then decays like any other text
   block. Instead of "purge or pay 1,600 tokens", the trade becomes "pay ~15".

Both stages are optional and degrade gracefully: without the extra deps the
adapter falls back to v1 behavior (keep-or-purge). Heavy imports are lazy so
`import bioma.vision` stays cheap.

Security note: distillation also closes the pixel-blindness gap — once text is
extracted, the cognitive firewall's secret redaction applies to image content.
"""
from __future__ import annotations

import base64
import io
import re
import time
from dataclasses import dataclass, field


@dataclass
class Distilled:
    text: str
    ocr_ms: float
    segments: int
    est_tokens: int


# Common secret shapes, so image redaction works even without a known vault.
SECRET_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("aws_secret", re.compile(r"(?i)aws_secret[^A-Za-z0-9]{0,3}[A-Za-z0-9/+=]{30,}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("google_api", re.compile(r"AIza[0-9A-Za-z_-]{30,}")),
    ("bearer", re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{16,}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]


@dataclass
class SecretFinding:
    text: str              # the OCR segment that matched
    kind: str              # pattern name, or "vault" for a known value
    box: list              # OCR polygon (4 points) — the region to mask


@dataclass
class ImageScan:
    findings: list[SecretFinding] = field(default_factory=list)
    ocr_ms: float = 0.0

    @property
    def has_secret(self) -> bool:
        return bool(self.findings)


class VisionDistiller:
    """Client-side image dedup + OCR distillation (lazy, offline)."""

    def __init__(self, dup_threshold: int = 5) -> None:
        self.dup_threshold = dup_threshold
        self._ocr = None
        self._hashes: list = []

    # ---- stage 0: secret redaction in PIXELS (closes the firewall's blind spot) #
    def scan_secrets(self, data_url: str, *, vault: tuple = (),
                     patterns: list = SECRET_PATTERNS) -> ImageScan:
        """OCR the image and flag any segment that is a known vault value OR matches
        a secret pattern — with its bounding box. This is what the text firewall
        cannot see: a secret rendered into pixels."""
        import numpy as np  # lazy
        if self._ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            self._ocr = RapidOCR()
        t0 = time.perf_counter()
        result, _ = self._ocr(np.array(self._to_pil(data_url)))
        ms = (time.perf_counter() - t0) * 1000.0
        vault_vals = [str(v) for v in vault if v]
        findings: list[SecretFinding] = []
        for box, text, *_ in (result or []):
            for v in vault_vals:
                if v and v in text:
                    findings.append(SecretFinding(text=text, kind="vault", box=box))
                    break
            else:
                for name, pat in patterns:
                    if pat.search(text):
                        findings.append(SecretFinding(text=text, kind=name, box=box))
                        break
        return ImageScan(findings=findings, ocr_ms=ms)

    def redact_secrets(self, data_url: str, *, vault: tuple = (),
                       patterns: list = SECRET_PATTERNS) -> tuple[str, ImageScan]:
        """Scan for secrets and MASK their regions with black boxes, returning a
        clean data-URL + the scan. The rest of the screenshot stays usable; only
        the secret is blacked out. If nothing is found, returns the input unchanged."""
        from PIL import ImageDraw  # lazy
        scan = self.scan_secrets(data_url, vault=vault, patterns=patterns)
        if not scan.has_secret:
            return data_url, scan
        img = self._to_pil(data_url)
        draw = ImageDraw.Draw(img)
        for f in scan.findings:
            xs = [p[0] for p in f.box]
            ys = [p[1] for p in f.box]
            draw.rectangle([min(xs), min(ys), max(xs), max(ys)], fill="black")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(), scan

    # ---- stage 1: perceptual dedup ---------------------------------------- #
    def is_duplicate(self, data_url: str) -> tuple[bool, float]:
        """pHash against every image seen this session → (dup?, elapsed_ms)."""
        import imagehash  # lazy
        img = self._to_pil(data_url)
        t0 = time.perf_counter()
        h = imagehash.phash(img)
        dup = any((h - prev) <= self.dup_threshold for prev in self._hashes)
        if not dup:
            self._hashes.append(h)
        return dup, (time.perf_counter() - t0) * 1000.0

    def dedup_keep_latest(self, data_urls: list[str]) -> set[int]:
        """Batch dedup with the KEEP-LATEST policy: near-duplicate images are
        clustered by pHash and only the MOST RECENT member of each cluster
        survives — a monitoring screen's newest state is the valuable one.
        Returns the set of indices to keep."""
        import imagehash  # lazy
        hashes = [imagehash.phash(self._to_pil(u)) for u in data_urls]
        cluster_of: list[int] = []
        reps: list = []
        for h in hashes:
            for ci, rep in enumerate(reps):
                if (h - rep) <= self.dup_threshold:
                    cluster_of.append(ci)
                    break
            else:
                cluster_of.append(len(reps))
                reps.append(h)
        latest: dict[int, int] = {}
        for i, ci in enumerate(cluster_of):
            latest[ci] = i  # later index overwrites → keeps the newest
        return set(latest.values())

    # ---- stage 2: lazy OCR distillation ------------------------------------ #
    def distill(self, data_url: str) -> Distilled:
        """Extract the text content of an image (RapidOCR, CPU). Call OFF the
        dispatch hot path — once per image, when it ages toward purge."""
        import numpy as np  # lazy
        if self._ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            self._ocr = RapidOCR()
        arr = np.array(self._to_pil(data_url))
        t0 = time.perf_counter()
        result, _ = self._ocr(arr)
        ms = (time.perf_counter() - t0) * 1000.0
        segs = [seg[1] for seg in (result or [])]
        text = " · ".join(segs)
        return Distilled(text=text, ocr_ms=ms, segments=len(segs),
                         est_tokens=len(text) // 4 + 1)

    # ---- stage 3: VLM caption for structure-bearing images ----------------- #
    CAPTION_PROMPT = ("Describe this image concisely. If it contains shapes or a "
                      "diagram, say which text label is inside or attached to each "
                      "shape (e.g. 'a circle labeled X, a triangle labeled Y').")

    def caption(self, data_url: str, *, model: str = "moondream",
                base_url: str = "http://localhost:11434",
                timeout: float = 300.0) -> tuple[str, float]:
        """Local VLM caption via Ollama → (text, elapsed_ms). Preserves the
        shape↔label semantics that a flat OCR dump loses. Returns ("", ms) on
        failure — the OCR tier still stands alone."""
        import json
        import urllib.request
        body = json.dumps({
            "model": model, "prompt": self.CAPTION_PROMPT, "stream": False,
            "images": [data_url.split(",", 1)[1]],
            "options": {"temperature": 0.0, "num_predict": 160},
        }).encode()
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(f"{base_url}/api/generate", data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                text = (json.loads(r.read().decode()).get("response") or "").strip()
        except Exception:
            text = ""
        return text, (time.perf_counter() - t0) * 1000.0

    # ---- stage 3b: DETERMINISTIC shape↔label structure (OpenCV + OCR boxes) - #
    def structure(self, data_url: str) -> tuple[str, float]:
        """Recover shape↔label relations geometrically: OpenCV finds the shape
        contours, RapidOCR provides text boxes, containment associates them.
        Deterministic and hallucination-free — unlike a tiny local VLM, which we
        measured confabulating exact labels. Returns ("", ms) when no clear
        shapes are found."""
        import cv2  # lazy
        import numpy as np
        if self._ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            self._ocr = RapidOCR()
        t0 = time.perf_counter()
        arr = np.array(self._to_pil(data_url))
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, 60, 160)
        edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        ocr_result, _ = self._ocr(arr)
        segs = [(seg[0], seg[1]) for seg in (ocr_result or [])]

        def center(box) -> tuple[float, float]:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            return sum(xs) / len(xs), sum(ys) / len(ys)

        found: list[str] = []
        for raw in contours:
            if cv2.contourArea(raw) < 4000:   # ignore glyphs/noise
                continue
            # classify on the convex hull: thin appendages (connector lines
            # merged into the contour by edge dilation) stop distorting the
            # circularity of the underlying shape
            c = cv2.convexHull(raw)
            peri = cv2.arcLength(c, True)
            v = len(cv2.approxPolyDP(c, 0.03 * peri, True))
            # fine-grained vertex count on the hull: a smooth curve keeps many
            # vertices at 1% tolerance (ellipse ≳ 10), a polygon keeps only its
            # corners (rect+connector-tail ≲ 8) — robust to merged thin lines,
            # unlike circularity (a square scores 0.785, inside the noise band)
            v_fine = len(cv2.approxPolyDP(c, 0.01 * peri, True))
            if v == 3:
                kind = "triângulo"
            elif v_fine >= 10:
                kind = "círculo"
            elif v >= 4:
                kind = "retângulo"
            else:
                continue
            inside = [t for box, t in segs
                      if cv2.pointPolygonTest(c, center(box), False) >= 0]
            if inside:
                found.append(f"{kind} contém '{' '.join(inside)}'")
        ms = (time.perf_counter() - t0) * 1000.0
        return ("; ".join(found), ms)

    def distill_rich(self, data_url: str, *, structure_max_segments: int = 8) -> Distilled:
        """OCR always; for structure-bearing images (few OCR segments → likely a
        diagram), ADD the deterministic shape↔label map. All client-side."""
        d = self.distill(data_url)
        if d.segments <= structure_max_segments:
            st, st_ms = self.structure(data_url)
            if st:
                text = f"{d.text} · estrutura do diagrama: {st}"
                return Distilled(text=text, ocr_ms=d.ocr_ms + st_ms,
                                 segments=d.segments, est_tokens=len(text) // 4 + 1)
        return d

    @staticmethod
    def _to_pil(data_url: str):
        from PIL import Image  # lazy
        raw = base64.b64decode(data_url.split(",", 1)[1])
        return Image.open(io.BytesIO(raw)).convert("RGB")


def distill_block_text(source_hint: str, d: Distilled) -> str:
    """The text block that replaces a distilled image in the context."""
    return f"[imagem destilada: {source_hint}] conteúdo lido (OCR): {d.text}"
