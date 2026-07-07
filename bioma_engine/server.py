"""
`server.py` — Phase 2 production API surface for B.I.O.M.A.

Wraps the Stem-Cell Orchestrator in an asynchronous FastAPI service that streams
live cellular telemetry to clients as the colony mitoses, metabolises and
apoptoses in real time.

Endpoints
---------
* ``GET  /``                     — HTML landing page + usage.
* ``GET  /health``               — liveness + VRAM/RAM usage + living-agent count.
* ``POST /v1/bioma/synthesize``  — Server-Sent-Events stream of telemetry events.
* ``WS   /v1/bioma/ws``          — WebSocket stream of the same events (JSON lines).

Concurrency isolation
---------------------
A single :class:`MitosisEngine` is created at startup.  Its embedder is
stateless/read-only; **every** request handled by :meth:`MitosisEngine.run`
builds its own :class:`Colony` (bus + DAG + cell registry), so two concurrent
requests operate on completely disjoint dynamic sub-graphs — no memory bleed,
no cross-request races.  The shared bounded thread pool caps total CPU pressure
regardless of how many organisms spawn across all in-flight requests.

Run directly:  ``python server.py``      (dev)
Or via script: ``bash run_server.sh``     (prod, uvicorn)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from typing import Optional

# --- Make the package importable no matter the working directory ----------- #
_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_PKG_DIR)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse  # noqa: E402
from pydantic import BaseModel, Field, ValidationError  # noqa: E402

from bioma_engine import MitosisEngine, DEVICE, __version__  # noqa: E402
from bioma_engine.mitosis_engine import resource_snapshot, live_cells_global  # noqa: E402
from bioma_engine.telemetry import TelemetryEvent, KIND_ERROR  # noqa: E402
from bioma_engine.bioma_integration_hook import process_external_prompt  # noqa: E402
from bioma_engine.bioma_vigil_daemon import shutdown_daemon  # noqa: E402


# --------------------------------------------------------------------------- #
#  Application lifespan: build the shared orchestrator once.
# --------------------------------------------------------------------------- #
_STATE: dict[str, object] = {"engine": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the sensory cortex (embedding table) a single time at boot.
    _STATE["engine"] = MitosisEngine()
    try:
        yield
    finally:
        _STATE["engine"] = None
        shutdown_daemon()  # clear the integration daemon's cache


app = FastAPI(
    title="B.I.O.M.A. — Biologically Inspired Orchestration of Mutating Agents",
    version=__version__,
    description="Self-replicating neural organisms that solve prompts by mitosis, "
                "homeostasis and apoptosis. Streams live cellular telemetry.",
    lifespan=lifespan,
)

# Allow the local file:// test terminal (bioma_chat_test.html) — which sends an
# ``Origin: null`` header — plus any localhost tool to call the API from a browser.
# No credentials are used, so a wildcard origin is safe here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _engine() -> MitosisEngine:
    engine = _STATE["engine"]
    if engine is None:  # pragma: no cover - only during shutdown window
        raise RuntimeError("Engine not initialised")
    return engine


# --------------------------------------------------------------------------- #
#  Schemas
# --------------------------------------------------------------------------- #
class SynthesizeRequest(BaseModel):
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=8000,
        description="The complex, multi-domain scenario to inject into the colony.",
        examples=["Simulate a global market collapse combined with an energy grid failure, "
                  "optimizing response matrices simultaneously."],
    )
    request_id: Optional[str] = Field(
        default=None, description="Optional client-supplied id echoed in telemetry."
    )


class IntegrateRequest(BaseModel):
    """A code-optimization request piped in from an external chat / workflow."""

    prompt: str = Field(
        ..., min_length=1, max_length=8000,
        description="The code request; keyword-routed to an optimization target.",
        examples=["Optimize my slow recursive fibonacci function for production."],
    )
    source: Optional[str] = Field(
        default=None, max_length=100_000,
        description="Optional Python source to optimize directly (with test_cases).",
    )
    entrypoint: Optional[str] = Field(default=None, max_length=128,
                                      description="Function name in `source` to optimize.")
    test_cases: Optional[list] = Field(
        default=None, description="[[args...], expected] pairs used to gate correctness.",
    )
    generations: int = Field(default=4, ge=1, le=12)
    population: int = Field(default=6, ge=1, le=16)
    execution_mode: str = Field(default="OFFLINE_ONLY",
                                description="Only OFFLINE_ONLY is supported (offline by design).")
    timeout_s: Optional[float] = Field(default=None, ge=0.2, le=30.0,
                                       description="Per-sandbox execution deadline (apoptosis trigger).")


# --------------------------------------------------------------------------- #
#  Routes
# --------------------------------------------------------------------------- #
@app.get("/health")
async def health() -> JSONResponse:
    """Liveness + biological vital signs (never raises; degrades gracefully)."""
    engine = _STATE["engine"]
    body = {
        "status": "alive" if engine is not None else "initialising",
        "version": __version__,
        "device": str(DEVICE),
        "living_mini_agents": live_cells_global(),
        "resources": resource_snapshot(),
    }
    return JSONResponse(body, status_code=200 if engine is not None else 503)


@app.post("/v1/bioma/integrate")
async def integrate(req: IntegrateRequest) -> JSONResponse:
    """Pipe a code request into the B.I.O.M.A. evolutionary runtime and return the
    optimized code payload + telemetry tail (the middleware/broker surface).

    Concurrency-safe: each call runs an isolated, fresh optimizer (no shared
    mutable daemon state), so simultaneous IDE pipelines never race.  Optimization
    is the framework's own deterministic AST-transform catalog run in isolated
    subprocess sandboxes — fully autonomous, no external model, API or network.
    """
    try:
        result = await process_external_prompt(
            req.prompt, source=req.source, entrypoint=req.entrypoint,
            test_cases=req.test_cases, generations=req.generations, population=req.population,
            execution_mode=req.execution_mode, timeout_s=req.timeout_s,
        )
        return JSONResponse(result.as_dict())
    except ValueError as exc:  # bad execution_mode / malformed custom source spec
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=422)


@app.post("/v1/evolve")
async def evolve(req: IntegrateRequest) -> JSONResponse:
    """Spec-compatible alias of :func:`integrate` — the evolutionary chat/optimize
    surface consumed by the visual test terminal (``bioma_chat_test.html``).
    Identical request/response contract; enforces the same OFFLINE_ONLY autarky."""
    return await integrate(req)


@app.post("/v1/bioma/synthesize")
async def synthesize(req: SynthesizeRequest, request: Request) -> StreamingResponse:
    """Stream the colony's telemetry as Server-Sent Events.

    Each SSE frame is ``event: <kind>`` + ``data: <json>`` (see
    :meth:`TelemetryEvent.as_sse`).  The stream ends after the ``convergence``
    event.  If the client disconnects mid-run the generator stops promptly.
    """
    engine = _engine()
    rid = req.request_id or f"req-{abs(hash((req.prompt, id(request)))) & 0xffffff:06x}"

    async def event_stream():
        # Opening comment flushes headers immediately on proxies/browsers.
        yield ": bioma-stream-open\n\n"
        try:
            async for event in engine.run(req.prompt, request_id=rid):
                if await request.is_disconnected():
                    break
                yield event.as_sse()
        except asyncio.CancelledError:  # client went away
            raise
        except Exception as exc:  # surface, never swallow
            yield TelemetryEvent(
                KIND_ERROR, f"{type(exc).__name__}: {exc}", cell_id="server",
                metrics={"fatal": True},
            ).as_sse()

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # disable nginx buffering for true streaming
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


@app.websocket("/v1/bioma/ws")
async def synthesize_ws(websocket: WebSocket) -> None:
    """WebSocket variant: send ``{"prompt": "...", "request_id": "..."}`` once,
    then receive newline-delimited JSON telemetry records until the stream ends."""
    await websocket.accept()
    try:
        raw = await websocket.receive_text()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"prompt": raw}
        # A non-object JSON body (list/number/string) is treated as a bare prompt.
        if not isinstance(payload, dict):
            payload = {"prompt": raw}

        # Enforce the *same* validation bounds as the SSE path (length/type) by
        # reusing the pydantic model — the WS surface must not be a bypass.
        try:
            req = SynthesizeRequest(
                prompt=payload.get("prompt") or "",
                request_id=payload.get("request_id"),
            )
        except ValidationError as ve:
            await websocket.send_text(
                TelemetryEvent(KIND_ERROR, f"invalid payload: {ve.errors()[:1]}",
                               cell_id="server").as_json_line()
            )
            await websocket.close(code=1003)
            return

        rid = req.request_id or "ws"
        engine = _engine()
        async for event in engine.run(req.prompt, request_id=rid):
            await websocket.send_text(event.as_json_line())
        await websocket.close(code=1000)
    except WebSocketDisconnect:
        return
    except Exception as exc:  # pragma: no cover - defensive
        try:
            await websocket.send_text(
                TelemetryEvent(KIND_ERROR, f"{type(exc).__name__}: {exc}", cell_id="server").as_json_line()
            )
            await websocket.close(code=1011)
        except Exception:
            pass


_INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>B.I.O.M.A.</title>
<style>
 body{font-family:ui-monospace,Menlo,Consolas,monospace;background:#0b0f14;color:#cfe;max-width:820px;margin:2rem auto;padding:0 1rem;line-height:1.5}
 h1{color:#6fe;letter-spacing:.05em} code,pre{background:#111a22;color:#9fe;border-radius:6px}
 pre{padding:1rem;overflow:auto} a{color:#6fe} .k{color:#f9a}
 #out{white-space:pre-wrap;background:#111a22;padding:1rem;border-radius:6px;min-height:6rem;font-size:.8rem}
 button{background:#6fe;border:0;color:#012;padding:.5rem 1rem;border-radius:6px;cursor:pointer;font-weight:700}
 input{width:100%;padding:.5rem;background:#0b0f14;color:#cfe;border:1px solid #244;border-radius:6px}
</style></head><body>
<h1>🧬 B.I.O.M.A.</h1>
<p>Biologically Inspired Orchestration of Mutating Agents — self-replicating neural
organisms that solve a prompt by <span class="k">mitosis</span>, <span class="k">homeostasis</span>
and <span class="k">apoptosis</span>, streaming live cellular telemetry.</p>
<h3>Endpoints</h3>
<pre>GET  /health
POST /v1/bioma/synthesize   (Server-Sent Events)
WS   /v1/bioma/ws           (WebSocket, JSON lines)
POST /v1/bioma/integrate    (middleware broker → optimized code + telemetry)</pre>
<h3>curl</h3>
<pre>curl -N -X POST http://localhost:8000/v1/bioma/synthesize \\
  -H "Content-Type: application/json" \\
  -d '{"prompt":"Simulate a global market collapse combined with an energy grid failure."}'</pre>
<h3>Live demo</h3>
<input id="p" value="Simulate a global market collapse combined with an energy grid failure, optimizing response matrices simultaneously."/>
<p><button onclick="go()">inject scenario →</button></p>
<div id="out">telemetry will stream here…</div>
<script>
async function go(){
  const out=document.getElementById('out'); out.textContent='';
  const resp=await fetch('/v1/bioma/synthesize',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({prompt:document.getElementById('p').value})});
  const reader=resp.body.getReader(); const dec=new TextDecoder();
  while(true){const {value,done}=await reader.read(); if(done)break;
    out.textContent+=dec.decode(value,{stream:true}); out.scrollTop=out.scrollHeight;}
}
</script>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(_INDEX_HTML)


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("BIOMA_HOST", "127.0.0.1")
    port = int(os.environ.get("BIOMA_PORT", "8000"))
    # Single worker: the engine + thread pool live in-process and share the
    # live-cell gauge.  Scale horizontally with multiple containers behind a LB
    # rather than multiple workers that would fragment that in-process state.
    uvicorn.run(app, host=host, port=port, log_level="info")
