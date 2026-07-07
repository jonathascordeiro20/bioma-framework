"""
tests/test_local_production_stress.py — local production-simulation stress suite.

Chaos / performance validation of ``bioma_cloud_server.py`` + the integration hook
against an async client, before any cloud deployment.  The suite boots the cloud
server in a **separate subprocess**, drives it with ``httpx`` (async), and asserts:

  1. **High concurrency** — 5 simultaneous IDE-style POSTs all return HTTP 200
     with valid code, no dropped connections.
  2. **Chaos apoptosis** — a rogue ``while True: pass`` variant is apoptosed by the
     execution deadline, its child subprocess is killed, and the server stays live.
  3. **Offline autarky gate** — an ``OFFLINE_ONLY`` cached request returns in < 1s.

Run:  pytest -sv bioma_engine/tests/test_local_production_stress.py
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time

import httpx
import psutil
import pytest

_WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_METRICS: dict = {"peak_rss_delta_mb": 0.0}


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def server():
    """Boot bioma_cloud_server in a subprocess on a free port; kill it on teardown."""
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    log_path = os.path.join(
        os.environ.get("TEMP", "/tmp"), f"bioma_stress_server_{port}.log"
    )
    env = dict(os.environ)
    env.update({
        "PYTHONIOENCODING": "utf-8", "PYTHONPATH": _WORKSPACE,
        "BIOMA_HOST": "127.0.0.1", "BIOMA_PORT": str(port),
        "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "KMP_DUPLICATE_LIB_OK": "TRUE",
    })
    log = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "bioma_engine.bioma_cloud_server:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=_WORKSPACE, env=env, stdout=log, stderr=log,
    )
    # Wait for readiness (or a clean, explained failure).
    deadline = time.time() + 45
    ready = False
    with httpx.Client(timeout=2.0) as c:
        while time.time() < deadline:
            if proc.poll() is not None:
                log.flush()
                raise RuntimeError(f"server exited during boot (see {log_path})")
            try:
                if c.get(f"{base}/health").status_code == 200:
                    ready = True
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.4)
    if not ready:
        proc.terminate()
        raise RuntimeError(f"server did not become ready on {base} (see {log_path})")

    ps = psutil.Process(proc.pid)
    baseline_rss = ps.memory_info().rss
    try:
        yield {"base": base, "proc": proc, "ps": ps, "port": port, "baseline_rss": baseline_rss}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


def _sample_peak_rss(server) -> float:
    delta_mb = (server["ps"].memory_info().rss - server["baseline_rss"]) / 1e6
    _METRICS["peak_rss_delta_mb"] = max(_METRICS["peak_rss_delta_mb"], delta_mb)
    return delta_mb


# ============================================================================ #
#  1. High-concurrency execution
# ============================================================================ #
def _slow_newton(bound: int) -> str:
    return (
        "def solve(x):\n"
        "    guess = x if x > 1 else 1.0\n"
        f"    for _ in range({bound}):\n"
        "        guess = (guess + x / guess) / 2.0\n"
        "    return round(guess, 4)\n"
    )


def test_simultaneous_ide_requests(server):
    """5 concurrent IDE-style pipelines each get HTTP 200 + valid, compilable code."""
    base = server["base"]
    tests = [[[4.0], 2.0], [[9.0], 3.0], [[16.0], 4.0]]
    # Distinct sources ⇒ distinct cache keys ⇒ genuinely 5-way concurrent evolution.
    payloads = [
        {
            "prompt": f"Enterprise service #{i}: optimize this hot numeric routine for production",
            "source": _slow_newton(1500 + i * 137), "entrypoint": "solve",
            "test_cases": tests, "generations": 2, "population": 3,
        }
        for i in range(5)
    ]

    async def fire():
        async with httpx.AsyncClient(timeout=180.0) as client:
            async def one(payload):
                t0 = time.perf_counter()
                r = await client.post(f"{base}/v1/bioma/integrate", json=payload)
                return r, time.perf_counter() - t0
            return await asyncio.gather(*[one(p) for p in payloads])

    results = asyncio.run(fire())
    latencies = []
    for r, dt in results:
        assert r.status_code == 200, r.text            # no dropped connections
        data = r.json()
        assert "def solve" in data["code"]
        compile(data["code"], "<concurrent>", "exec")  # valid code output
        latencies.append(dt)

    assert len(latencies) == 5
    _METRICS["avg_latency_s"] = sum(latencies) / len(latencies)
    _METRICS["clients"] = len(latencies)
    _METRICS["logical_threads"] = (os.cpu_count() or 0)
    _sample_peak_rss(server)


# ============================================================================ #
#  2. Chaos subprocess apoptosis guard
# ============================================================================ #
def test_infinite_loop_apoptosis(server):
    """A structural infinite loop is apoptosed at the deadline; the rogue child is
    killed, no zombie lingers, and the server stays alive and ready."""
    base = server["base"]
    ps = server["ps"]
    children_before = len(ps.children(recursive=True))

    payload = {
        "prompt": "chaos: rogue infinite loop",
        "source": "def solve(x):\n    while True:\n        pass\n    return x\n",
        "entrypoint": "solve", "test_cases": [[[1], 1]],
        "generations": 2, "population": 3, "timeout_s": 1.5,
    }
    with httpx.Client(timeout=60.0) as client:
        r = client.post(f"{base}/v1/bioma/integrate", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    # The resource guard tripped the deadline and apoptosed the rogue variant(s).
    assert data["apoptosis_cleans"] >= 1, data

    time.sleep(1.2)  # allow any killed child to be reaped
    children_after = len(ps.children(recursive=True))
    assert children_after <= children_before, (children_before, children_after)  # no zombie

    # The main server remains alive, stable, and ready for new requests.
    with httpx.Client(timeout=30.0) as client:
        assert client.get(f"{base}/health").status_code == 200
        r2 = client.post(f"{base}/v1/bioma/integrate",
                         json={"prompt": "optimize fibonacci", "generations": 2, "population": 3})
        assert r2.status_code == 200

    _METRICS["apoptosis_cleans"] = data["apoptosis_cleans"]
    _sample_peak_rss(server)


# ============================================================================ #
#  3. Offline autarky latency profile (sub-second cache gate)
# ============================================================================ #
def test_sub_second_cache_gate(server):
    """OFFLINE_ONLY cached request skips the sandboxes and returns in < 1.0 second."""
    base = server["base"]
    payload = {
        "prompt": "offline autarky: optimize recursive fibonacci",
        "execution_mode": "OFFLINE_ONLY", "generations": 3, "population": 5,
    }
    with httpx.Client(timeout=60.0) as client:
        prime = client.post(f"{base}/v1/bioma/integrate", json=payload)  # populate cache
        assert prime.status_code == 200
        t0 = time.perf_counter()
        r = client.post(f"{base}/v1/bioma/integrate", json=payload)      # cache hit
        gate = time.perf_counter() - t0

    assert r.status_code == 200
    data = r.json()
    assert data["cached"] is True, data
    assert data["execution_mode"] == "OFFLINE_ONLY"
    assert gate < 1.0, f"offline cache gate took {gate:.3f}s (expected < 1.0s)"
    compile(data["code"], "<offline>", "exec")

    _METRICS["cache_gate_s"] = gate
    _sample_peak_rss(server)


# ============================================================================ #
#  Metrics report
# ============================================================================ #
@pytest.fixture(scope="module", autouse=True)
def _report(server):
    yield
    print("\n" + "=" * 60)
    print(" B.I.O.M.A. — LOCAL PRODUCTION STRESS · PERFORMANCE METRICS ".center(60, "="))
    print("=" * 60)
    print(f"  Clients (concurrent)    : {_METRICS.get('clients', '?')}"
          f"  · logical threads: {_METRICS.get('logical_threads', '?')}")
    print(f"  Avg latency / client    : {_METRICS.get('avg_latency_s', 0.0):.3f} s")
    print(f"  Peak RAM RSS delta      : {_METRICS.get('peak_rss_delta_mb', 0.0):.2f} MB")
    print(f"  Successful apoptosis     : {_METRICS.get('apoptosis_cleans', '?')}")
    print(f"  Offline cache gate       : {_METRICS.get('cache_gate_s', 0.0):.3f} s (< 1.0 s)")
    print("=" * 60)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-sv"]))
