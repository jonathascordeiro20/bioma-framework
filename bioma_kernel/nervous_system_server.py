"""
nervous_system_server.py — live feed for the "Sistema Nervoso Visível" dashboard.

Runs the Rust `StressTester` in a background thread (its `run()` releases the GIL,
so the async server stays responsive) and streams `obter_estado_sistema_nervoso()`
snapshots to the browser over a WebSocket at ~10 Hz.  Also serves the single-file
dashboard at `/`.

Run:
    cd bioma_kernel
    python nervous_system_server.py          # → http://127.0.0.1:8080
    #   BIOMA_AGENTS=5000 BIOMA_PORT=8080 python nervous_system_server.py
"""

from __future__ import annotations

import asyncio
import json
import os
import threading

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

import bioma_kernel as bk

_HERE = os.path.dirname(os.path.abspath(__file__))
AGENTS = int(os.environ.get("BIOMA_AGENTS", "3000"))
SIGNALS = int(os.environ.get("BIOMA_SIGNALS", "16"))
RUN_SECS = float(os.environ.get("BIOMA_RUN_SECS", "86400"))   # keep flooding ~all day

_tester = bk.StressTester(num_signals=SIGNALS, max_agents=AGENTS)


def _flood() -> None:
    # Releases the GIL inside Rust → the event loop keeps serving while this runs.
    _tester.run(num_agents=AGENTS, duration_secs=RUN_SECS)


app = FastAPI(title="B.I.O.M.A. — Sistema Nervoso Visível")


@app.get("/")
def index() -> HTMLResponse:
    with open(os.path.join(_HERE, "nervous_system_dashboard.html"), encoding="utf-8") as fh:
        return HTMLResponse(fh.read())


@app.get("/snapshot")
def snapshot() -> JSONResponse:
    return JSONResponse(_tester.obter_estado_sistema_nervoso())


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            await websocket.send_text(json.dumps(_tester.obter_estado_sistema_nervoso()))
            await asyncio.sleep(0.1)   # 10 Hz
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


def main() -> None:
    host = os.environ.get("BIOMA_HOST", "127.0.0.1")
    port = int(os.environ.get("BIOMA_PORT", "8080"))
    threading.Thread(target=_flood, daemon=True).start()   # start the swarm
    print(f"  Sistema Nervoso Visível → http://{host}:{port}   "
          f"({AGENTS} agentes · {SIGNALS} canais)")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
