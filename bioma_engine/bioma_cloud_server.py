"""
`bioma_cloud_server.py` — Cloud / production entry point for the B.I.O.M.A. API.

Re-exports the FastAPI application (from :mod:`bioma_engine.server`) under a
deployment-oriented name and provides a bootable ``main()`` with cloud-friendly
defaults (binds ``0.0.0.0``).  Boot it with either:

    python -m bioma_engine.bioma_cloud_server
    uvicorn bioma_engine.bioma_cloud_server:app --host 0.0.0.0 --port 8000

The application is fully autonomous — no external model, API or network model
dependency (see ``AUTONOMY.md``).  Endpoints:
    GET  /health                 · liveness + vitals
    POST /v1/bioma/synthesize    · SSE cellular telemetry stream
    WS   /v1/bioma/ws            · WebSocket telemetry stream
    POST /v1/bioma/integrate     · middleware broker → optimized code + telemetry
"""

from __future__ import annotations

import os

from .server import app  # the FastAPI application (single source of truth)

__all__ = ["app", "main"]


def main() -> int:  # pragma: no cover - process entry point
    import uvicorn

    # Single process by design: the engine, daemon cache and thread pools are
    # in-process shared state.  Scale out with replicas behind a load balancer.
    host = os.environ.get("BIOMA_HOST", "0.0.0.0")
    port = int(os.environ.get("BIOMA_PORT", "8000"))
    uvicorn.run(app, host=host, port=port,
                log_level=os.environ.get("BIOMA_LOG_LEVEL", "info"), timeout_keep_alive=75)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
