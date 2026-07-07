"""
`bioma_cli_launcher.py` — Sovereign B.I.O.M.A. CLI (fully local, offline).

The ``bioma`` terminal command.  Parses a prompt (parameterized) or runs an
interactive loop, routes it to the local :class:`LocalInferenceEngine`, spins up
parallel multi-variant AST mutations across the CPU cores (with strict apoptosis
on slow/unstable variants), and streams the optimized code + local hardware
telemetry to stdout.  **No byte leaves the host machine over the network.**

Usage::

    bioma "optimize my recursive fibonacci for production"   # one-shot
    bioma -i                                                  # interactive loop
    bioma --status                                            # show local backend
"""

from __future__ import annotations

import argparse
import sys

from .local_inference_engine import LocalInferenceEngine
from .bioma_integration_hook import IntegrationResult


# --------------------------------------------------------------------------- #
#  Core one-shot entry (importable for tests / embedding)
# --------------------------------------------------------------------------- #
def run_once(prompt: str, *, engine: LocalInferenceEngine | None = None, **kwargs) -> IntegrationResult:
    """Generate an optimized code payload for ``prompt``, fully locally/offline."""
    engine = engine or LocalInferenceEngine()
    return engine.generate(prompt, **kwargs)


def _telemetry_line(result: IntegrationResult) -> str:
    """Local hardware telemetry (autarkic engine) — RSS delta measured on-host."""
    return (
        f"[B.I.O.M.A. Telemetry | Autarkic Local Engine | "
        f"RAM RSS Delta: {result.rss_delta_mb} MB | "
        f"Lineages: {result.lineages_mutated} | Apoptosis: {result.apoptosis_cleans} | "
        f"Transform: {result.winning_transform} | Cached: {result.cached}]"
    )


def _emit(result: IntegrationResult, stream=None) -> None:
    stream = stream or sys.stdout
    stream.write(result.code.rstrip() + "\n")
    stream.write(_telemetry_line(result) + "\n")
    stream.flush()


# --------------------------------------------------------------------------- #
#  Interactive REPL
# --------------------------------------------------------------------------- #
def interactive_loop(engine: LocalInferenceEngine | None = None, *, _inputs=None) -> int:
    """Read prompts from stdin and stream optimized code until 'exit'.

    ``_inputs`` (an iterable of strings) drives the loop non-interactively for
    tests without touching a real TTY."""
    engine = engine or LocalInferenceEngine()
    st = engine.status()
    print(
        f"B.I.O.M.A. sovereign CLI — backend={st.backend} · threads={st.threads} · "
        f"network_required={st.network_required}  (offline, autarkic)"
    )
    print("Enter a code request (or 'exit'/'quit'):")

    feed = iter(_inputs) if _inputs is not None else None
    while True:
        try:
            line = next(feed).strip() if feed is not None else input("bioma> ").strip()
        except (EOFError, StopIteration):
            break
        if not line:
            continue
        if line.lower() in ("exit", "quit"):
            break
        _emit(engine.generate(line))
    return 0


# --------------------------------------------------------------------------- #
#  Argument parsing / dispatch  (the `bioma` console entry point)
# --------------------------------------------------------------------------- #
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bioma",
        description="Sovereign, fully-local B.I.O.M.A. code engine (offline / autarkic).",
    )
    p.add_argument("prompt", nargs="*", help="code request; omit (or use -i) for interactive mode")
    p.add_argument("-i", "--interactive", action="store_true", help="run the interactive REPL")
    p.add_argument("--status", action="store_true", help="print the local backend status and exit")
    p.add_argument("-g", "--generations", type=int, default=4, help="evolutionary generations (default 4)")
    p.add_argument("-n", "--population", type=int, default=6, help="mutants per generation (default 6)")
    p.add_argument("-t", "--timeout", type=float, default=None, help="per-sandbox apoptosis deadline (s)")
    p.add_argument("--models-dir", default=None, help="local weights directory (optional GGUF backend)")
    return p


def main(argv=None) -> int:
    args = _build_parser().parse_args(sys.argv[1:] if argv is None else list(argv))
    engine = LocalInferenceEngine(models_dir=args.models_dir)

    if args.status:
        st = engine.status()
        print(
            f"backend           : {st.backend}\n"
            f"models_dir        : {st.models_dir}\n"
            f"weights_found     : {st.weights_found or '(none — sovereign deterministic optimizer)'}\n"
            f"logical threads   : {st.threads}\n"
            f"network_required  : {st.network_required}"
        )
        return 0

    prompt = " ".join(args.prompt).strip()
    if args.interactive or not prompt:
        return interactive_loop(engine)

    _emit(engine.generate(
        prompt, generations=args.generations, population=args.population, timeout_s=args.timeout,
    ))
    return 0


if __name__ == "__main__":
    # os._exit avoids the Windows OpenMP atexit teardown crash (0xC0000409).
    import os as _os
    _rc = main()
    sys.stdout.flush()
    sys.stderr.flush()
    _os._exit(_rc)
