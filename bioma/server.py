"""
`bioma/server.py` — the lean production API for the B.I.O.M.A. Micro-Kernel.

Depends on nothing but the Rust kernel (`bioma_micro`) + the resilient client
(`bioma.openrouter_client`) + FastAPI — no torch, no agents, no mitosis. Every
request runs the real Rust context-apoptosis filter; if a valid OpenRouter key is
present it also dispatches the dehydrated prompt to the model.

Endpoints:
  * GET  /health        — liveness + kernel/topology info
  * POST /v1/dispatch   — apoptosis filter (+ resilient model dispatch when keyed)

Run:  uvicorn bioma.server:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

import bioma_micro as kernel

_ROLE_SIG = {"system": kernel.SYSTEM, "user": kernel.USER, "assistant": kernel.ASSISTANT,
             "tool": kernel.TOOL, "fact": kernel.FACT}
_STATE: dict[str, object] = {"client": None}


def _valid_key(k: Optional[str]) -> bool:
    return bool(k) and k.startswith("sk-or")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build the resilient client once — only if a real key is present. The apoptosis
    # filter works regardless (offline kernel), so the surface never hard-fails.
    if _valid_key(os.environ.get("OPENROUTER_API_KEY")):
        try:
            from bioma.openrouter_client import LeanOpenRouterClient
            _STATE["client"] = LeanOpenRouterClient()
        except Exception:
            _STATE["client"] = None
    try:
        yield
    finally:
        client = _STATE.get("client")
        if client is not None:
            await client.close()  # type: ignore[attr-defined]
        _STATE["client"] = None


app = FastAPI(
    title="B.I.O.M.A. Micro-Kernel",
    version=getattr(kernel, "__version__", "1.0.0"),
    description="Lean efficiency & resilience kernel: lock-free hormonal bus + context apoptosis.",
    lifespan=lifespan,
)

# CORS: dev defaults to "*"; in prod set BIOMA_ALLOWED_ORIGINS to your real origins.
_origins_env = os.environ.get("BIOMA_ALLOWED_ORIGINS", "*").strip()
_allowed = ["*"] if _origins_env == "*" else [o.strip() for o in _origins_env.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_allowed, allow_methods=["*"], allow_headers=["*"])


class DispatchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=32000,
                       description="The current request/prompt.")
    history: list[dict] = Field(default_factory=list,
                                description="Prior turns [{role, content}]; dehydrated by apoptosis.")
    model: str = Field(default="openai/gpt-4o", description="OpenRouter model id.")
    system: Optional[str] = Field(default=None, max_length=8000)
    max_tokens: int = Field(default=512, ge=1, le=4096)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({
        "status": "alive",
        "kernel": getattr(kernel, "__version__", "1.0.0"),
        "topology": "lean (hormonal_bus + context_apoptosis)",
        "online": _STATE["client"] is not None,
    })


@app.post("/v1/dispatch")
async def dispatch(req: DispatchRequest) -> JSONResponse:
    """Run the Rust apoptosis filter over `history`, then (if keyed) dispatch the
    dehydrated prompt to the model. Returns the answer + a full apoptosis audit."""
    # Apoptosis always runs (offline, real kernel μs).
    msgs = [(str(m.get("content", "")), _ROLE_SIG.get(m.get("role", "user"), kernel.USER))
            for m in req.history]
    audit = kernel.dehydrate(msgs, half_life=6.0, safe_threshold=0.35)
    apo = {
        "tokens_before": int(audit["tokens_before"]),
        "tokens_after": int(audit["tokens_after"]),
        "reduction": float(audit["reduction"]),
        "blocks_purged": int(audit["blocks_purged"]),
        "kernel_latency_us": float(audit["kernel_latency_us"]),
    }

    client = _STATE["client"]
    if client is None:
        return JSONResponse({
            "dispatched": False,
            "reason": "OPENROUTER_API_KEY not set — apoptosis ran; model dispatch skipped.",
            "apoptosis": apo,
        })

    try:
        d = await client.dispatch(req.history, req.query, model=req.model,  # type: ignore[attr-defined]
                                  system=req.system, max_tokens=req.max_tokens)
    except Exception as exc:  # never leak a stack trace
        return JSONResponse({"dispatched": False, "reason": f"{type(exc).__name__}: {exc}",
                             "apoptosis": apo}, status_code=502)

    return JSONResponse({
        "dispatched": not d.error,
        "answer": d.text,
        "model": d.model,
        "error": d.error,
        "usage": {"in_tokens": d.in_tokens, "out_tokens": d.out_tokens,
                  "cost_usd": d.cost_usd, "rtt_ms": d.rtt_ms},
        "apoptosis": {"tokens_before": d.tokens_before, "tokens_after": d.tokens_after,
                      "reduction": d.reduction, "blocks_purged": d.blocks_purged,
                      "kernel_latency_us": d.kernel_latency_us},
    }, status_code=200 if not d.error else 502)


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return ("<h1>B.I.O.M.A. Micro-Kernel</h1>"
            "<p>Lean efficiency &amp; resilience kernel for LLM infrastructure.</p>"
            "<p><code>GET /health</code> · <code>POST /v1/dispatch</code></p>")
