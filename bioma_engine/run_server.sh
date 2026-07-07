#!/usr/bin/env bash
#
# run_server.sh — boot the B.I.O.M.A. API with Uvicorn.
#
# Environment overrides:
#   BIOMA_HOST      bind address        (default 0.0.0.0)
#   BIOMA_PORT      bind port           (default 8000)
#   BIOMA_WORKERS   uvicorn workers     (default 1 — see note below)
#   BIOMA_DEVICE    cpu | cuda          (default: auto-detect)
#
# NOTE: keep workers at 1 unless you have sharded the colony state.  The engine,
# its bounded thread pool and the process-wide live-cell gauge are in-process
# shared state; multiple workers would fragment that gauge and multiply the
# thread pools.  For horizontal scale, run multiple replicas behind a load
# balancer instead.
set -euo pipefail

HOST="${BIOMA_HOST:-0.0.0.0}"
PORT="${BIOMA_PORT:-8000}"
WORKERS="${BIOMA_WORKERS:-1}"

# cd to the workspace root (parent of this package dir) so `bioma_engine` is
# importable as a top-level package.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."

echo "🧬 Booting B.I.O.M.A. on ${HOST}:${PORT} (workers=${WORKERS}, device=${BIOMA_DEVICE:-auto})"
exec uvicorn bioma_engine.server:app \
    --host "${HOST}" \
    --port "${PORT}" \
    --workers "${WORKERS}" \
    --timeout-keep-alive 75 \
    --log-level info
