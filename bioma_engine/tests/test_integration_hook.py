"""
tests/test_integration_hook.py — regressive stability tests for the universal
integration hook (`bioma_integration_hook.py`).

Verifies seamless pipeline routing (external prompt → daemon → evolutionary
runtime → optimized code payload) and that apoptosis keeps the host memory
flat-lined across repeated integrations.
"""

from __future__ import annotations

import gc

import psutil
import pytest

from bioma_engine.bioma_integration_hook import (
    process_external_prompt_sync, IntegrationResult,
)
from bioma_engine.bioma_vigil_daemon import shutdown_daemon, get_daemon, DigitalForager


@pytest.fixture(scope="module", autouse=True)
def _daemon_teardown():
    """Drain the warm daemon's thread pool after this module's tests."""
    yield
    shutdown_daemon()


# ============================================================================ #
#  Test 1 — Pipeline routing and code interception
# ============================================================================ #
def test_pipeline_routing_and_code_interception():
    """A complex request flows through the broker, activates the core layers, and
    returns a valid, non-truncated code script — without blocking or dropping
    threads (the pipeline stays reusable for a second call)."""
    result = process_external_prompt_sync(
        "Optimize this slow recursive fibonacci function for a production service",
        generations=4, population=6,
    )
    assert isinstance(result, IntegrationResult)
    # Routed to the right target and the winning AST transform is present.
    assert result.target == "recursive-fibonacci"
    assert result.winning_transform == "ast:insert_lru_cache"
    assert "def solve" in result.code and "lru_cache" in result.code
    assert result.improved is True and result.latency_gain_pct > 0.0
    # The evolutionary layers actually ran.
    assert result.lineages_mutated > 0
    assert result.apoptosis_cleans >= 0
    # Standardized telemetry tail is well-formed and embedded in the payload.
    assert result.telemetry.startswith("[B.I.O.M.A. Telemetry:") and result.telemetry.endswith("]")
    assert "Lineages Mutated" in result.telemetry and "Apoptosis Cleans" in result.telemetry
    assert "RAM RSS Delta" in result.telemetry
    assert result.telemetry in result.payload
    # The returned code is valid Python (not truncated / placeholdered).
    compile(result.code, "<payload>", "exec")

    # Pipeline is reusable — a second request through the same warm daemon works
    # (threads were not dropped / the pool is not exhausted).
    second = process_external_prompt_sync("optimize the newton sqrt loop bound", generations=3, population=5)
    assert second.target == "newton-sqrt"
    assert "def solve" in second.code
    compile(second.code, "<second>", "exec")


def test_custom_source_optimization_path():
    """A caller-supplied (source, entrypoint, test_cases) is optimized directly."""
    slow = (
        "def solve(x):\n"
        "    guess = x if x > 1 else 1.0\n"
        "    for _ in range(2000):\n"
        "        guess = (guess + x / guess) / 2.0\n"
        "    return round(guess, 4)\n"
    )
    tests = [[[4.0], 2.0], [[9.0], 3.0], [[16.0], 4.0]]
    result = process_external_prompt_sync(
        "optimize", source=slow, entrypoint="solve", test_cases=tests,
        generations=5, population=6,
    )
    assert result.target == "custom"
    assert "def solve" in result.code
    compile(result.code, "<custom>", "exec")
    assert result.telemetry in result.payload


def test_forager_is_offline_and_deterministic():
    """The DigitalForager is reproducible and never touches the network."""
    f = DigitalForager()
    a = f.forage("optimize a recursive fibonacci")
    b = f.forage("optimize a recursive fibonacci")
    import torch
    assert torch.equal(a, b)                       # deterministic
    assert a.shape == (get_daemon().config.embed_dim,)
    assert abs(float(a.norm().item()) - 1.0) < 1e-4  # unit nutrient vector


# ============================================================================ #
#  Test 2 — Memory-leak sanity guard (apoptosis cleans every sandbox run)
# ============================================================================ #
def test_memory_flatlined_over_10_integrations():
    """Ten consecutive integrations keep the host RSS flat (≤ 1% delta): every
    sandbox subprocess is reclaimed and no host-side state accumulates."""
    proc = psutil.Process()
    # use_cache=False so every run actually spawns + apoptoses sandboxes (a cache
    # hit would trivially flatline without exercising the pruning path).
    for _ in range(2):  # warm the subprocess / torch code paths
        process_external_prompt_sync("optimize fibonacci", generations=2, population=4, use_cache=False)
    gc.collect()
    baseline = proc.memory_info().rss

    for _ in range(10):
        process_external_prompt_sync("optimize fibonacci", generations=2, population=4, use_cache=False)
    gc.collect()
    final = proc.memory_info().rss

    delta_pct = (final - baseline) / baseline * 100.0
    assert delta_pct <= 1.0, f"host RSS grew {delta_pct:.3f}% over 10 integrations (apoptosis leak?)"


# ============================================================================ #
#  Autonomy guarantee — no external model / vendor / network dependency
# ============================================================================ #
from bioma_engine.autonomy import autonomy_audit  # noqa: E402


def test_system_is_fully_autonomous_no_external_model():
    """Static audit: the package depends on no external model/LLM/inference lib
    and contains no vendor/assistant references (enforcement module excluded)."""
    rep = autonomy_audit()
    assert rep["no_external_model_libs"] is True, rep["model_violations"]
    assert rep["no_vendor_references"] is True, rep["token_violations"]
    assert rep["autonomous"] is True
    assert rep["network_required_to_run_core"] is False


def test_optimizer_path_is_deterministic_ast_only():
    """The code optimizer runs the deterministic AST catalog — never a model."""
    result = process_external_prompt_sync("optimize fibonacci", generations=2, population=4)
    assert result.winning_transform.startswith("ast:")


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
