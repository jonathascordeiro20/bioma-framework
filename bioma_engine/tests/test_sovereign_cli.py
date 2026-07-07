"""
tests/test_sovereign_cli.py — sovereign / zero-network regression suite.

Validates that the ``bioma`` CLI + local inference engine execute the full
prompt → AST-mutation → apoptosis → optimized-code pipeline **under 100% internet
darkness**, and that repeated local generations keep host RAM flat-lined.
"""

from __future__ import annotations

import gc
import socket

import psutil
import pytest

from bioma_engine.bioma_cli_launcher import run_once, main, interactive_loop, _telemetry_line
from bioma_engine.local_inference_engine import LocalInferenceEngine
from bioma_engine.bioma_vigil_daemon import shutdown_daemon


@pytest.fixture(scope="module", autouse=True)
def _teardown():
    yield
    shutdown_daemon()


def _is_loopback(address) -> bool:
    """True for host-local endpoints that never leave the machine."""
    host = address[0] if isinstance(address, (tuple, list)) and address else address
    h = str(host)
    return h in ("127.0.0.1", "::1", "localhost", "0.0.0.0", "") or h.startswith("127.")


@pytest.fixture()
def net_blackout(monkeypatch):
    """100% internet darkness: any **external** (non-loopback) egress raises.

    Loopback (``127.0.0.1``) is allowed because asyncio's Windows event loop uses
    a localhost self-pipe internally — that never leaves the host.  A byte can
    only leave the machine via a non-loopback connect/DNS, and every such path is
    trapped, proving the pipeline runs with zero external network access."""
    real_socket = socket.socket
    real_getaddrinfo = socket.getaddrinfo
    real_create_connection = socket.create_connection

    class _NoEgressSocket(real_socket):
        def connect(self, address, *a, **k):
            if not _is_loopback(address):
                raise AssertionError(f"external egress attempted under autarky: {address!r}")
            return super().connect(address, *a, **k)

        def connect_ex(self, address, *a, **k):
            if not _is_loopback(address):
                raise AssertionError(f"external egress attempted under autarky: {address!r}")
            return super().connect_ex(address, *a, **k)

    def _guarded_getaddrinfo(host, *a, **k):
        if not _is_loopback(host):
            raise AssertionError(f"external DNS lookup attempted under autarky: {host!r}")
        return real_getaddrinfo(host, *a, **k)

    def _guarded_create_connection(address, *a, **k):
        if not _is_loopback(address):
            raise AssertionError(f"external create_connection attempted under autarky: {address!r}")
        return real_create_connection(address, *a, **k)

    monkeypatch.setattr(socket, "socket", _NoEgressSocket)
    monkeypatch.setattr(socket, "getaddrinfo", _guarded_getaddrinfo)
    monkeypatch.setattr(socket, "create_connection", _guarded_create_connection)
    return monkeypatch


# ============================================================================ #
#  Test 1 — Zero-Network Isolation Ingestion Gate
# ============================================================================ #
def test_zero_network_isolation_ingestion_gate(net_blackout):
    """Under a strict network block, the CLI accesses the local model cache, runs
    the mutation sandbox, and produces a valid enterprise code payload."""
    engine = LocalInferenceEngine()
    assert engine.status().network_required is False  # sovereign backend

    result = run_once(
        "Optimize this recursive fibonacci for a high-throughput enterprise service",
        engine=engine, generations=3, population=5,
    )

    # A valid, non-truncated code payload was produced under internet darkness.
    assert "def solve" in result.code
    compile(result.code, "<sovereign>", "exec")
    assert result.execution_mode == "OFFLINE_ONLY"
    # The evolutionary layers actually ran locally (mutation sandbox executed).
    assert result.lineages_mutated > 0
    assert result.winning_transform.startswith("ast:")
    # Telemetry is the autarkic-local-engine form.
    assert "Autarkic Local Engine" in _telemetry_line(result)


def test_bioma_command_entrypoint_offline(net_blackout, capsys):
    """The exact `bioma "<prompt>"` console entry streams code + telemetry to
    stdout with no network access."""
    rc = main(["optimize my recursive fibonacci", "-g", "3", "-n", "5"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "def solve" in out
    assert "[B.I.O.M.A. Telemetry | Autarkic Local Engine |" in out
    compile(out.split("[B.I.O.M.A. Telemetry")[0], "<cli-stdout>", "exec")


def test_interactive_loop_offline(net_blackout, capsys):
    """The interactive REPL processes fed prompts and exits cleanly, offline."""
    rc = interactive_loop(_inputs=["optimize fibonacci", "exit"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "backend=deterministic_ast" in out
    assert "Autarkic Local Engine" in out


# ============================================================================ #
#  Test 2 — Memory Leak Control during Local Inference
# ============================================================================ #
def test_memory_leak_control_local_inference():
    """Five back-to-back local generations keep host RSS flat (≤ 1%): every
    sandbox is apoptosed and no tensor/host state accumulates."""
    engine = LocalInferenceEngine()
    proc = psutil.Process()

    # use_cache=False so every loop genuinely spawns + apoptoses sandboxes.
    for _ in range(2):  # warm code paths first
        run_once("optimize fibonacci", engine=engine, generations=2, population=4, use_cache=False)
    gc.collect()
    baseline = proc.memory_info().rss

    for _ in range(5):
        run_once("optimize fibonacci", engine=engine, generations=2, population=4, use_cache=False)
    gc.collect()
    final = proc.memory_info().rss

    delta_pct = (final - baseline) / baseline * 100.0
    assert delta_pct <= 1.0, f"host RSS grew {delta_pct:.3f}% over 5 local generations (leak?)"


def test_engine_reports_sovereign_offline_backend():
    """The engine advertises a local backend and never requires the network."""
    st = LocalInferenceEngine().status()
    assert st.backend in ("deterministic_ast", "local_gguf")
    assert st.network_required is False
    assert st.threads >= 2


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
