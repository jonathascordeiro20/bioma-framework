"""
`_eval_runner.py` — isolated candidate evaluator for the Evolutionary Coder.

Executed as a **separate process** (``python _eval_runner.py <spec.json>``) so
every mutated code variant runs in its own memory space with a hard wall-clock
timeout enforced by the parent.  A variant that hangs or blows up is killed by
the parent (the "apoptosis" of a bad mutation) without endangering the
orchestrator.  Dependency-free (no torch / no bioma imports) for fast startup.

Security note: the candidate source is executed with ``exec``.  It is for the
user's *own* scripts being optimised — process isolation + timeout bound the
blast radius, but this is not a sandbox against hostile code. Do not feed it
untrusted input.

Spec JSON (written by the parent):
    {source, entrypoint, test_cases, tolerance, compare, repeats, warmup}

Emits one JSON line: {tests_passed, tests_total, latency_ms, mem_delta_kb, error}
where ``latency_ms`` is the **median over ``repeats`` timed passes** with the
first ``warmup`` passes discarded (plan Fase 10 — stable latency, not a sample).
"""

from __future__ import annotations

import json
import statistics
import sys
import time
import tracemalloc


def _compare(got, expected, mode: str, tol: float) -> bool:
    if mode == "exact":
        return got == expected
    try:
        if isinstance(expected, (list, tuple)):
            if len(got) != len(expected):
                return False
            return all(abs(float(g) - float(e)) <= tol for g, e in zip(got, expected))
        return abs(float(got) - float(expected)) <= tol
    except (TypeError, ValueError):
        return got == expected


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"tests_passed": 0, "tests_total": 0, "latency_ms": 0.0,
                          "mem_delta_kb": 0.0, "error": "no spec file"}))
        return 2

    with open(sys.argv[1], "r", encoding="utf-8") as fh:
        spec = json.load(fh)

    source = spec["source"]
    entrypoint = spec["entrypoint"]
    cases = spec.get("test_cases", [])
    tol = float(spec.get("tolerance", 1e-3))
    mode = spec.get("compare", "approx")
    repeats = max(1, int(spec.get("repeats", 5)))
    warmup = max(0, int(spec.get("warmup", 1)))

    namespace: dict = {}
    try:
        code = compile(source, "<candidate>", "exec")
        exec(code, namespace)  # noqa: S102 - deliberate: evaluating the candidate
        fn = namespace.get(entrypoint)
        if not callable(fn):
            raise ValueError(f"entrypoint '{entrypoint}' is not callable")
    except Exception as exc:  # compile/exec failure -> a non-viable mutation
        print(json.dumps({"tests_passed": 0, "tests_total": len(cases), "latency_ms": 0.0,
                          "mem_delta_kb": 0.0, "error": f"load: {type(exc).__name__}: {exc}"}))
        return 0

    # --- Correctness pass (single) + peak-memory measurement ---------------- #
    passed = 0
    error = None
    tracemalloc.start()
    try:
        for args, expected in cases:
            got = fn(*args)
            if _compare(got, expected, mode, tol):
                passed += 1
    except Exception as exc:
        error = f"runtime: {type(exc).__name__}: {exc}"
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # --- Latency: median of R timed passes, warm-up discarded --------------- #
    latency_ms = 0.0
    if error is None and cases:
        def _one_pass():
            for args, _expected in cases:
                fn(*args)

        try:
            for _ in range(warmup):
                _one_pass()
            samples = []
            for _ in range(repeats):
                t0 = time.perf_counter()
                _one_pass()
                samples.append((time.perf_counter() - t0) * 1000.0)
            latency_ms = float(statistics.median(samples))
        except Exception as exc:
            error = f"latency: {type(exc).__name__}: {exc}"

    print(json.dumps({
        "tests_passed": passed,
        "tests_total": len(cases),
        "latency_ms": round(latency_ms, 4),
        "mem_delta_kb": round(peak / 1024.0, 4),
        "error": error,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
