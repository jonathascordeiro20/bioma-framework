"""
`bioma/gateway.py` — the drop-in gateway: point your OpenAI-compatible client's
`base_url` here and every request gets context apoptosis, transparently.

    uvicorn bioma.gateway:app --port 8790
    client = OpenAI(base_url="http://localhost:8790/v1", api_key=...)  # nothing else changes

Surfaces: `POST /v1/chat/completions` (OpenAI format) and `POST /v1/messages`
(Anthropic Messages format — point Claude Code's `ANTHROPIC_BASE_URL` here),
both streaming and non-streaming, + `GET /health`. Upstream OpenRouter accepts
both formats natively, so either surface works with an OpenRouter key.

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
client's Authorization / x-api-key is forwarded; if absent, `OPENROUTER_API_KEY`.
Bridge mode (`BIOMA_FORCE_KEY` set) ignores the client's key and always uses
`OPENROUTER_API_KEY` — needed to point an Anthropic client such as Claude Code
(`ANTHROPIC_BASE_URL=http://localhost:8790`) at an OpenRouter upstream.
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

# Load .env so the standalone server (uvicorn) finds OPENROUTER_API_KEY without
# it having to be exported into the shell — matches how the tests load it.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

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


def _first_text(content: Any) -> str:
    """The leading text of a message, whether content is a str or a list of parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                return p.get("text", "")
    return ""


def _has_cache_control(content: Any) -> bool:
    return isinstance(content, list) and any(
        isinstance(p, dict) and p.get("cache_control") for p in content)


def _has_block_type(msg: dict, block_type: str) -> bool:
    return any(isinstance(b, dict) and b.get("type") == block_type
               for b in _blocks(msg.get("content")))


def _is_tool_unit(msgs: list[dict]) -> bool:
    """A purge unit is 'tool' (verbose, disposable) if any of its messages is a
    tool exchange — OpenAI (`tool` role / `tool_calls`) OR Anthropic
    (`tool_use` / `tool_result` content blocks)."""
    for m in msgs:
        if m.get("role") == "tool" or m.get("tool_calls"):
            return True
        if _has_block_type(m, "tool_use") or _has_block_type(m, "tool_result"):
            return True
    return False


def _unit_signal(msgs: list[dict]) -> int:
    first = msgs[0]
    role = first.get("role", "user")
    content = first.get("content")
    # durable if explicitly FACT-tagged OR marked for provider caching (a
    # cache_control breakpoint means the caller declared this block stable)
    if _first_text(content).lstrip().startswith("FACT:") or _has_cache_control(content):
        return kernel.FACT
    if role == "system":
        return kernel.SYSTEM
    # tool exchanges are disposable in BOTH protocol shapes
    if _is_tool_unit(msgs):
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


_EMPTY_AUDIT = {"tokens_before": 0, "tokens_after": 0, "reduction": 0.0,
                "kernel_latency_us": 0.0, "blocks_purged": 0}


def _apoptose_units(units: list[list[dict]], tail: list[dict], *,
                    half_life: float, safe_threshold: float) -> tuple[list[dict], dict]:
    """Run the kernel over pre-grouped history units and reassemble survivors + tail."""
    msgs = [(f"[U{idx}]" + _unit_text(unit), _unit_signal(unit))
            for idx, unit in enumerate(units)]
    audit = kernel.dehydrate(msgs, half_life=half_life, safe_threshold=safe_threshold)
    kept_idx = {int(k[2:k.index("]")]) for k in audit["kept"]}
    survivors = [m for idx, unit in enumerate(units) if idx in kept_idx for m in unit]
    return survivors + tail, dict(audit, kept=None)


def dehydrate_messages(messages: list[dict], *, half_life: float,
                       safe_threshold: float) -> tuple[list[dict], dict]:
    """Deletion-only, order-preserving apoptosis over an OpenAI message list.
    Returns (surviving messages, audit dict). The LAST user message (and
    everything after it) is the current query — it never enters the filter."""
    last_user = max((i for i, m in enumerate(messages) if m.get("role") == "user"),
                    default=-1)
    if last_user < 0:
        return messages, dict(_EMPTY_AUDIT)
    history, tail = messages[:last_user], messages[last_user:]
    return _apoptose_units(_group_units(history), tail,
                           half_life=half_life, safe_threshold=safe_threshold)


# --------------------------------------------------------------------------- #
#  Anthropic Messages format
# --------------------------------------------------------------------------- #
def _blocks(content: Any) -> list[dict]:
    return content if isinstance(content, list) else []


def _has_block(msg: dict, block_type: str) -> bool:
    return any(isinstance(b, dict) and b.get("type") == block_type
               for b in _blocks(msg.get("content")))


def _group_units_anthropic(history: list[dict]) -> list[list[dict]]:
    """Group Anthropic messages into purge units, keeping tool pairs together:
    an assistant message with `tool_use` blocks pairs with the FOLLOWING user
    message carrying the matching `tool_result` blocks."""
    units: list[list[dict]] = []
    i = 0
    while i < len(history):
        m = history[i]
        if (m.get("role") == "assistant" and _has_block(m, "tool_use")
                and i + 1 < len(history) and _has_block(history[i + 1], "tool_result")):
            units.append([m, history[i + 1]])
            i += 2
        else:
            units.append([m])
            i += 1
    return units


def dehydrate_anthropic(messages: list[dict], *, half_life: float,
                        safe_threshold: float) -> tuple[list[dict], dict]:
    """Apoptosis over Anthropic Messages. `system` is a separate top-level field
    (always forwarded untouched, never purged) so it is not in `messages`. The
    last user turn is the current query and is never filtered; if it carries a
    `tool_result`, its matching assistant `tool_use` is kept with it (no orphan)."""
    last_user = max((i for i, m in enumerate(messages) if m.get("role") == "user"),
                    default=-1)
    if last_user < 0:
        return messages, dict(_EMPTY_AUDIT)
    split = last_user
    # if the sacred tail begins with a tool_result, keep its paired tool_use too
    if (_has_block(messages[last_user], "tool_result") and last_user > 0
            and messages[last_user - 1].get("role") == "assistant"
            and _has_block(messages[last_user - 1], "tool_use")):
        split = last_user - 1
    history, tail = messages[:split], messages[split:]
    return _apoptose_units(_group_units_anthropic(history), tail,
                           half_life=half_life, safe_threshold=safe_threshold)


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

    def _auth_headers(request: Request) -> dict[str, str]:
        """Forward the caller's auth (Bearer OR Anthropic x-api-key); fall back
        to OPENROUTER_API_KEY. In BRIDGE MODE (`BIOMA_FORCE_KEY` set) the client's
        own key is ignored and OPENROUTER_API_KEY is always used — needed when
        bridging an Anthropic client (e.g. Claude Code) to the OpenRouter upstream,
        since the client sends its own Anthropic-style key."""
        force = os.environ.get("BIOMA_FORCE_KEY", "")
        if force:
            key = os.environ.get("OPENROUTER_API_KEY", "") or force
            return {"Authorization": f"Bearer {key}"}
        out: dict[str, str] = {}
        if request.headers.get("authorization"):
            out["Authorization"] = request.headers["authorization"]
        if request.headers.get("x-api-key"):
            out["x-api-key"] = request.headers["x-api-key"]
        if request.headers.get("anthropic-version"):
            out["anthropic-version"] = request.headers["anthropic-version"]
        if not out:
            key = os.environ.get("OPENROUTER_API_KEY", "")
            if key:
                out["Authorization"] = f"Bearer {key}"
        return out

    async def _forward(request: Request, path: str, body: dict, stream: bool,
                       inject: Optional[dict] = None):
        url = f"{app.state.upstream}{path}"
        headers = {"Content-Type": "application/json", **_auth_headers(request)}
        for h in ("http-referer", "x-title"):
            if request.headers.get(h):
                headers[h] = request.headers[h]
        if stream:
            req = app.state.client.build_request("POST", url, headers=headers, json=body)
            upstream_resp = await app.state.client.send(req, stream=True)

            async def pump():
                try:
                    async for chunk in upstream_resp.aiter_bytes():
                        yield chunk
                finally:
                    await upstream_resp.aclose()

            return StreamingResponse(
                pump(), status_code=upstream_resp.status_code,
                media_type=upstream_resp.headers.get("content-type", "text/event-stream"))

        r = await app.state.client.post(url, headers=headers, json=body)
        try:
            payload = r.json()
        except ValueError:
            return JSONResponse({"error": "upstream returned non-JSON"}, status_code=502)
        if inject is not None and isinstance(payload, dict):
            payload["bioma"] = inject
        return JSONResponse(payload, status_code=r.status_code)

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

    def _audit_fields(audit: dict) -> dict:
        return {k: audit[k] for k in ("tokens_before", "tokens_after",
                "reduction", "kernel_latency_us", "blocks_purged")}

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        body = await request.json()
        survivors, audit = dehydrate_messages(
            body.get("messages") or [], half_life=app.state.half_life,
            safe_threshold=app.state.threshold)
        body["messages"] = survivors
        stream = bool(body.get("stream", False))
        _audit_line(str(body.get("model", "?")), audit, stream)
        # OpenAI SDKs ignore unknown top-level fields → safe to inject the audit
        return await _forward(request, "/chat/completions", body, stream,
                              inject=None if stream else _audit_fields(audit))

    @app.post("/v1/messages")
    async def messages(request: Request):
        """Anthropic Messages surface — point Claude Code's ANTHROPIC_BASE_URL here.
        `system` is a top-level field, forwarded untouched (never purged)."""
        body = await request.json()
        survivors, audit = dehydrate_anthropic(
            body.get("messages") or [], half_life=app.state.half_life,
            safe_threshold=app.state.threshold)
        body["messages"] = survivors
        stream = bool(body.get("stream", False))
        _audit_line(str(body.get("model", "?")), audit, stream)
        # the Anthropic response schema is strict; keep it clean (JSONL audit only)
        return await _forward(request, "/messages", body, stream, inject=None)

    @app.post("/v1/messages/count_tokens")
    async def count_tokens(request: Request):
        """Auxiliary endpoint some Anthropic clients (Claude Code) call. Passthrough
        WITHOUT apoptosis: it must count the tokens the client actually holds, so
        the client's own context bookkeeping stays consistent."""
        body = await request.json()
        return await _forward(request, "/messages/count_tokens", body,
                              stream=False, inject=None)

    return app


app = create_app()
