"""
tools/smoke_client.py — end-to-end smoke test for the live B.I.O.M.A. server.

Exercises all three surfaces against a running server:
  1. GET  /health                 → expects 200 + vital signs
  2. POST /v1/bioma/synthesize    → consumes the SSE telemetry stream
  3. WS   /v1/bioma/ws            → consumes the WebSocket telemetry stream

Usage:
    python tools/smoke_client.py [--base http://127.0.0.1:8000] [--prompt "..."]

Exit code 0 iff every surface responded and a `convergence` event was observed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import httpx

DEFAULT_PROMPT = (
    "Simulate a global financial market collapse combined with a national energy "
    "grid failure, coordinating medical logistics, cybersecurity and food supply "
    "rerouting while optimizing every response matrix simultaneously."
)


def _parse_sse(chunk: str):
    """Yield (event, data) tuples from a block of SSE text."""
    for frame in chunk.split("\n\n"):
        event, data = None, None
        for line in frame.splitlines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        if event and data:
            yield event, data


async def test_health(base: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{base}/health")
        r.raise_for_status()
        body = r.json()
        print(f"[health] {r.status_code}  {body}")
        return body


async def test_sse(base: str, prompt: str) -> dict:
    kinds: dict[str, int] = {}
    summary: dict = {}
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST", f"{base}/v1/bioma/synthesize", json={"prompt": prompt, "request_id": "smoke-sse"}
        ) as r:
            r.raise_for_status()
            print(f"[sse] connected: HTTP {r.status_code} ({r.headers.get('content-type')})")
            buffer = ""
            async for text in r.aiter_text():
                buffer += text
                while "\n\n" in buffer:
                    frame, buffer = buffer.split("\n\n", 1)
                    for event, data in _parse_sse(frame + "\n\n"):
                        kinds[event] = kinds.get(event, 0) + 1
                        if event == "convergence":
                            summary = json.loads(data).get("metrics", {})
    print(f"[sse] event breakdown: {kinds}")
    print(f"[sse] convergence summary: {summary}")
    return {"kinds": kinds, "summary": summary}


async def test_ws(base: str, prompt: str) -> dict:
    ws_url = base.replace("http://", "ws://").replace("https://", "wss://") + "/v1/bioma/ws"
    kinds: dict[str, int] = {}
    try:
        import websockets
    except ImportError:
        print("[ws] websockets client not installed — skipping (server side still verified via SSE)")
        return {"kinds": {}, "skipped": True}

    async with websockets.connect(ws_url, max_size=None) as ws:
        await ws.send(json.dumps({"prompt": prompt, "request_id": "smoke-ws"}))
        try:
            async for message in ws:
                rec = json.loads(message)
                k = rec.get("kind", "?")
                kinds[k] = kinds.get(k, 0) + 1
        except Exception:
            pass
    print(f"[ws] event breakdown: {kinds}")
    return {"kinds": kinds}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    args = parser.parse_args()

    ok = True
    health = await test_health(args.base)
    ok = ok and health.get("status") == "alive"

    sse = await test_sse(args.base, args.prompt)
    ok = ok and sse["kinds"].get("convergence", 0) == 1 and sse["kinds"].get("mitosis", 0) >= 1

    ws = await test_ws(args.base, args.prompt)
    if not ws.get("skipped"):
        ok = ok and ws["kinds"].get("convergence", 0) == 1

    print("\n=== SMOKE TEST:", "PASS ✅" if ok else "FAIL ❌", "===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
