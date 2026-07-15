"""
`bioma/gateway.py` — the drop-in gateway: point your OpenAI-compatible client's
`base_url` here and every request gets context apoptosis, transparently.

    uvicorn bioma.gateway:app --port 8790
    client = OpenAI(base_url="http://localhost:8790/v1", api_key=...)  # nothing else changes

Surface (MVP): `POST /v1/chat/completions` (OpenAI format, streaming and
non-streaming) + `GET /health`. The Anthropic `/v1/messages` surface (for
Claude Code E2E) is the declared next iteration.

Design guarantees (each one is unit-tested):

1. **The current query is sacred** — the last `user` message never enters the
   filter; the first `system` message maps to the kernel's SYSTEM class
   (never purged). Content starting with ``FACT:`` maps to FACT (never purged).
2. **Cache-aware by construction** — dehydration is deletion-only and order-
   preserving: the surviving prefix (system + early FACTs) stays byte-identical
   across calls, so provider prompt-caching can still hit on it.
3. **Tool-pair integrity** — an assistant message carrying `tool_calls` and its
   following `tool` result messages form ONE unit that survives or is purged
   together; the gateway never emits an orphaned tool call/result.
4. **Auditable** — every request appends a JSONL line (tokens before/after,
   reduction, kernel μs) to `BIOMA_AUDIT_LOG` (default: bioma_gateway_audit.jsonl);
   non-streaming responses also carry a top-level ``bioma`` audit object
   (extra fields are ignored by SDKs).

Upstream: `BIOMA_UPSTREAM` (default https://openrouter.ai/api/v1). Auth: the
client's Authorization header is forwarded; if absent, `OPENROUTER_API_KEY`.
Tuning: `BIOMA_HALF_LIFE` (6.0) and `BIOMA_SAFE_THRESHOLD` (0.35).
"""
from __future__ import annotations

import json
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

import bioma_micro as kernel

IMAGE_NOMINAL_TOKENS = 1600   # multimodal content parts priced like the vision adapter


# --------------------------------------------------------------------------- #
#  Dehydration over OpenAI-format messages
# --------------------------------------------------------------------------- #
def _unit_text(msgs: list[dict]) -> str:
    """Text used for the kernel's token sizing of a unit (marker added later)."""
    parts: list[str] = []
    for m in msgs:
        c = m.get("content")
        if isinstance(c, str):
            parts.append(c)
        elif isinstance(c, list):  # multimodal content parts
            for p in c:
                if p.get("type") == "text":
                    parts.append(p.get("text", ""))
                else:                       # image/audio part → nominal cost
                    parts.append(" " * (IMAGE_NOMINAL_TOKENS * 4))
        for tc in m.get("tool_calls") or []:
            parts.append(json.dumps(tc.get("function", {}), ensure_ascii=False))
    return "\n".join(parts)


def _unit_signal(msgs: list[dict]) -> int:
    first = msgs[0]
    role = first.get("role", "user")
    content = first.get("content")
    if isinstance(content, str) and content.lstrip().startswith("FACT:"):
        return kernel.FACT
    if role == "system":
        return kernel.SYSTEM
    if role == "tool" or first.get("tool_calls"):
        return kernel.TOOL
    if role == "assistant":
        return kernel.ASSISTANT
    return kernel.USER


def _group_units(messages: list[dict]) -> list[list[dict]]:
    """Group messages into purge units, keeping tool pairs together."""
    units: list[list[dict]] = []
    i = 0
    while i < len(messages):
        m = messages[i]
        if m.get("role") == "assistant" and m.get("tool_calls"):
            unit = [m]
            i += 1
            while i < len(messages) and messages[i].get("role") == "tool":
                unit.append(messages[i])
                i += 1
            units.append(unit)
        else:
            units.append([m])
            i += 1
    return units


def dehydrate_messages(messages: list[dict], *, half_life: float,
                       safe_threshold: float) -> tuple[list[dict], dict]:
    """Deletion-only, order-preserving apoptosis over an OpenAI message list.
    Returns (surviving messages, audit dict). The LAST user message (and
    everything after it) is the current query — it never enters the filter."""
    # split off the sacred tail: last user message onwards
    last_user = max((i for i, m in enumerate(messages) if m.get("role") == "user"),
                    default=-1)
    if last_user < 0:
        return messages, {"tokens_before": 0, "tokens_after": 0, "reduction": 0.0,
                          "kernel_latency_us": 0.0, "blocks_purged": 0}
    history, tail = messages[:last_user], messages[last_user:]

    units = _group_units(history)
    msgs = []
    for idx, unit in enumerate(units):
        marker = f"[U{idx}]"
        msgs.append((marker + _unit_text(unit), _unit_signal(unit)))
    audit = kernel.dehydrate(msgs, half_life=half_life, safe_threshold=safe_threshold)
    kept_idx = {int(k[2:k.index("]")]) for k in audit["kept"]}
    survivors = [m for idx, unit in enumerate(units) if idx in kept_idx for m in unit]
    return survivors + tail, dict(audit, kept=None)


# --------------------------------------------------------------------------- #
#  The gateway app
# --------------------------------------------------------------------------- #
def create_app(*, upstream: Optional[str] = None,
               transport: Optional[httpx.AsyncBaseTransport] = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await app.state.client.aclose()

    app = FastAPI(title="B.I.O.M.A. Gateway", version="0.1.0", lifespan=lifespan)
    app.state.upstream = (upstream or os.environ.get(
        "BIOMA_UPSTREAM", "https://openrouter.ai/api/v1")).rstrip("/")
    app.state.half_life = float(os.environ.get("BIOMA_HALF_LIFE", "6.0"))
    app.state.threshold = float(os.environ.get("BIOMA_SAFE_THRESHOLD", "0.35"))
    app.state.audit_path = os.environ.get("BIOMA_AUDIT_LOG", "bioma_gateway_audit.jsonl")
    app.state.client = httpx.AsyncClient(transport=transport, timeout=600.0)

    def _auth_header(request: Request) -> dict[str, str]:
        auth = request.headers.get("authorization")
        if not auth:
            key = os.environ.get("OPENROUTER_API_KEY", "")
            auth = f"Bearer {key}" if key else ""
        return {"Authorization": auth} if auth else {}

    def _audit_line(model: str, audit: dict, stream: bool) -> None:
        line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": model,
                "stream": stream, "tokens_before": int(audit["tokens_before"]),
                "tokens_after": int(audit["tokens_after"]),
                "reduction": round(float(audit["reduction"]), 4),
                "kernel_latency_us": round(float(audit["kernel_latency_us"]), 2),
                "blocks_purged": int(audit["blocks_purged"])}
        try:
            with open(app.state.audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(line) + "\n")
        except OSError:
            pass

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "kernel": getattr(kernel, "__version__", "?"),
                "upstream": app.state.upstream,
                "half_life": app.state.half_life, "threshold": app.state.threshold}

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        body = await request.json()
        messages = body.get("messages") or []
        survivors, audit = dehydrate_messages(
            messages, half_life=app.state.half_life,
            safe_threshold=app.state.threshold)
        body["messages"] = survivors
        model = str(body.get("model", "?"))
        stream = bool(body.get("stream", False))
        _audit_line(model, audit, stream)

        url = f"{app.state.upstream}/chat/completions"
        headers = {"Content-Type": "application/json", **_auth_header(request)}
        for h in ("http-referer", "x-title"):
            if request.headers.get(h):
                headers[h] = request.headers[h]

        if stream:
            req = app.state.client.build_request("POST", url, headers=headers,
                                                 json=body)
            upstream_resp = await app.state.client.send(req, stream=True)

            async def pump():
                try:
                    async for chunk in upstream_resp.aiter_bytes():
                        yield chunk
                finally:
                    await upstream_resp.aclose()

            return StreamingResponse(
                pump(), status_code=upstream_resp.status_code,
                media_type=upstream_resp.headers.get("content-type",
                                                     "text/event-stream"))

        r = await app.state.client.post(url, headers=headers, json=body)
        try:
            payload = r.json()
        except ValueError:
            return JSONResponse({"error": "upstream returned non-JSON"},
                                status_code=502)
        if isinstance(payload, dict):
            payload["bioma"] = {k: audit[k] for k in
                                ("tokens_before", "tokens_after", "reduction",
                                 "kernel_latency_us", "blocks_purged")}
        return JSONResponse(payload, status_code=r.status_code)

    return app


app = create_app()
