"""
`bioma_integration_hook.py` — Universal middleware broker into B.I.O.M.A.

Pipe a prompt from any external chat / automated workflow into the active
B.I.O.M.A. evolutionary runtime and get back an optimized, self-contained code
payload plus a standardized telemetry tail.  This is a **wrapper/broker**, not a
new chat UI — call it from your existing environment.

Protocol layers
---------------
1. **Ingestion** — :func:`process_external_prompt` accepts a text string, parses
   it, and routes it to the orchestration workflow in
   :mod:`bioma_engine.bioma_vigil_daemon`.
2. **Downstream evolution** — the daemon forages an offline scientific-nutrient
   context into the hormonal bus, then runs the AST-transform catalog
   (:mod:`bioma_engine.evolutionary_coder`) generating variants **concurrently**
   across the host cores in **isolated subprocess sandboxes with hard timeouts**.
3. **Homeostatic pruning** — failing / hanging variants are apoptosed (killed +
   ``gc.collect``); the winning production-grade payload is returned with a tail
   like ``[B.I.O.M.A. Telemetry: X Lineages Mutated, Y Apoptosis Cleans, RAM RSS
   Delta: Z MB]``.

Autonomy (see ``AUTONOMY.md`` / ``HONESTY.md``)
----------------------------------------------
Fully self-contained: the optimizer is B.I.O.M.A.'s own **deterministic
AST-transform catalog** run in sandboxed subprocesses — **no external model, no
API, no network**.  The only "model" in the system is its local ``nn.Module``
runtime.  A free-text prompt is **routed by keyword** to a registered
optimization target; a custom ``(source, entrypoint, test_cases)`` may be
supplied to optimize arbitrary code.
"""

from __future__ import annotations

import asyncio
import gc
import time
from dataclasses import asdict, dataclass
from typing import Optional

# The system is offline & deterministic by design; OFFLINE_ONLY is the only mode.
VALID_EXECUTION_MODES = {"OFFLINE_ONLY"}

try:
    import psutil
except Exception:  # pragma: no cover - psutil is a hard dep; degrade gracefully
    psutil = None

from .config import BiomaConfig, DEFAULT_CONFIG
from .evolutionary_coder import (
    DEMO_SLOW_FIB, DEMO_FIB_TESTS, DEMO_SLOW_SQRT, DEMO_SQRT_TESTS,
)
from .bioma_vigil_daemon import get_daemon


# Registered optimization targets the AST catalog can genuinely optimize.
_TARGETS: dict[str, dict] = {
    "fibonacci": {
        "label": "recursive-fibonacci",
        "keywords": ["fib", "fibonacci", "recurs", "memo", "cache", "exponential"],
        "source": DEMO_SLOW_FIB, "entrypoint": "solve", "test_cases": DEMO_FIB_TESTS,
    },
    "sqrt": {
        "label": "newton-sqrt",
        "keywords": ["sqrt", "root", "newton", "iterat", "converg", "loop bound"],
        "source": DEMO_SLOW_SQRT, "entrypoint": "solve", "test_cases": DEMO_SQRT_TESTS,
    },
}
_DEFAULT_TARGET = "fibonacci"


def _route(prompt: str) -> str:
    """Keyword-route a free-text prompt to a registered optimization target."""
    p = (prompt or "").lower()
    best, best_score = _DEFAULT_TARGET, 0
    for name, spec in _TARGETS.items():
        score = sum(1 for kw in spec["keywords"] if kw in p)
        if score > best_score:
            best, best_score = name, score
    return best


@dataclass
class IntegrationResult:
    """The broker's response to the calling environment."""

    payload: str            # the string to hand back to the chat: code + telemetry tail
    code: str               # just the optimized source
    target: str             # which optimization target was engaged
    winning_transform: str  # the AST transform that won (labelled origin)
    improved: bool
    latency_gain_pct: float
    lineages_mutated: int
    apoptosis_cleans: int
    rss_delta_mb: float
    nutrient_norm: float
    telemetry: str
    execution_mode: str = "OFFLINE_ONLY"
    cached: bool = False    # served from the offline nutrient cache (sub-second gate)
    latency_s: float = 0.0  # wall-clock from ingestion to convergence

    def as_dict(self) -> dict:
        return asdict(self)


def _rss_mb() -> float:
    return round(psutil.Process().memory_info().rss / 1e6, 3) if psutil is not None else 0.0


async def process_external_prompt(
    prompt: str, *,
    source: Optional[str] = None,
    entrypoint: Optional[str] = None,
    test_cases: Optional[list] = None,
    generations: int = 4,
    population: int = 6,
    config: BiomaConfig = DEFAULT_CONFIG,
    execution_mode: str = "OFFLINE_ONLY",
    timeout_s: Optional[float] = None,
    use_cache: bool = True,
) -> IntegrationResult:
    """Ingest an external prompt, route it into the B.I.O.M.A. runtime, and return
    the optimized code payload + telemetry tail.

    Provide ``source`` + ``test_cases`` (and optional ``entrypoint``) to optimize
    an arbitrary target; otherwise the free-text ``prompt`` is keyword-routed to a
    registered target.  ``execution_mode`` must be ``OFFLINE_ONLY`` (the system is
    offline by design); ``timeout_s`` bounds each sandbox execution.
    """
    if execution_mode not in VALID_EXECUTION_MODES:
        raise ValueError(
            f"Unsupported execution_mode {execution_mode!r}; the system is offline by "
            f"design — only {sorted(VALID_EXECUTION_MODES)} is supported."
        )
    if not (prompt or source):
        raise ValueError("process_external_prompt requires a non-empty prompt or source")

    rss0 = _rss_mb()
    t0 = time.perf_counter()
    try:
        if source is not None and test_cases is not None:
            target_label, ep, src, tests = "custom", (entrypoint or "solve"), source, test_cases
        else:
            spec = _TARGETS[_route(prompt)]
            target_label, ep, src, tests = spec["label"], spec["entrypoint"], spec["source"], spec["test_cases"]

        daemon = get_daemon(config)
        res = await daemon.orchestrate(
            source=src, entrypoint=ep, test_cases=tests,
            generations=generations, population=population, nutrient_text=prompt or target_label,
            timeout_s=timeout_s, use_cache=use_cache,
        )
    finally:
        # Homeostatic pruning: reclaim any transient host memory after the run.
        gc.collect()

    latency_s = round(time.perf_counter() - t0, 4)
    rss_delta = round(_rss_mb() - rss0, 3)
    telemetry = (
        f"[B.I.O.M.A. Telemetry: {res.lineages_mutated} Lineages Mutated, "
        f"{res.apoptosis_cleans} Apoptosis Cleans, RAM RSS Delta: {rss_delta} MB]"
    )
    code = res.best_source.strip()
    payload = f"{code}\n\n# {telemetry}"
    return IntegrationResult(
        payload=payload, code=code, target=target_label,
        winning_transform=res.winning_transform, improved=res.improved,
        latency_gain_pct=res.latency_gain_pct, lineages_mutated=res.lineages_mutated,
        apoptosis_cleans=res.apoptosis_cleans, rss_delta_mb=rss_delta,
        nutrient_norm=res.nutrient_norm, telemetry=telemetry,
        execution_mode=execution_mode, cached=res.cached, latency_s=latency_s,
    )


def process_external_prompt_sync(prompt: str, **kwargs) -> IntegrationResult:
    """Blocking convenience wrapper — call from non-async chat/workflow code."""
    return asyncio.run(process_external_prompt(prompt, **kwargs))


def main() -> int:  # pragma: no cover - CLI entry point
    """CLI: feed a request as args or on stdin; prints the payload to stdout."""
    import sys

    prompt = " ".join(sys.argv[1:]).strip()
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    if not prompt:
        print("usage: python -m bioma_engine.bioma_integration_hook \"optimize my recursive fibonacci\"",
              file=sys.stderr)
        return 2
    result = process_external_prompt_sync(prompt)
    print(result.payload)
    return 0


if __name__ == "__main__":
    import os as _os
    import sys as _sys

    _rc = main()
    _sys.stdout.flush()
    _sys.stderr.flush()
    _os._exit(_rc)
