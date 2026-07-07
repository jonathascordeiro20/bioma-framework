"""
`run_local.py` — Phase 1 local entry point.

Injects an extremely complex, multi-domain scenario into the B.I.O.M.A. engine
and renders the resulting cellular telemetry to the terminal as a live
biological dashboard: genesis → divergence → mitosis → metabolism → homeostasis
→ hormone secretion → apoptosis → synthesis.

Run it directly (no install needed — it puts the package's parent on ``sys.path``):

    python run_local.py
    python run_local.py --prompt "your own scenario" --no-color
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter

# --- Make the package importable no matter the working directory ----------- #
_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_PKG_DIR)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from bioma_engine import MitosisEngine, BiomaConfig, DEVICE  # noqa: E402
from bioma_engine.telemetry import render, banner  # noqa: E402


DEFAULT_PROMPT = (
    "Simulate a global financial market collapse cascading into a national "
    "energy grid failure, while simultaneously coordinating emergency medical "
    "logistics, cybersecurity defense of critical infrastructure, food supply "
    "chain rerouting, water sanitation, and public communication strategy — "
    "optimizing every response matrix in parallel under deep uncertainty."
)


def _enable_windows_ansi() -> None:
    """Turn on VT/ANSI escape processing on legacy Windows consoles."""
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # -11 = STD_OUTPUT_HANDLE ; 7 = ENABLE_PROCESSED_OUTPUT | ENABLE_WRAP |
        #                               ENABLE_VIRTUAL_TERMINAL_PROCESSING
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass


def _lineage_tree(cell_ids: set[str]) -> str:
    """Render the DAG lineage as an indented ASCII tree from dotted cell ids."""
    lines: list[str] = []
    for cid in sorted(cell_ids, key=lambda s: (s.count("."), s)):
        depth = cid.count(".")
        indent = "    " * depth
        connector = "└─ " if depth else ""
        lines.append(f"{indent}{connector}{cid}")
    return "\n".join(lines)


async def run(prompt: str, use_colour: bool) -> int:
    engine = MitosisEngine()
    cfg: BiomaConfig = engine.config

    print(banner("B.I.O.M.A.  —  CELLULAR NEURO-GENESIS  (PHASE 1 LOCAL)"))
    print(f"  device            : {DEVICE}")
    print(f"  embed_dim         : {cfg.embed_dim}   hidden_dim: {cfg.hidden_dim}")
    print(f"  divergence_thresh : {cfg.divergence_threshold}   max_children: {cfg.max_children}"
          f"   cell_budget: {cfg.cell_budget}")
    print(f"  initial_energy    : {cfg.initial_energy}   metabolic_cycles: {cfg.metabolic_cycles}")
    print(f"  scenario          : {prompt[:96]}{'…' if len(prompt) > 96 else ''}")
    print(banner("LIVE CELLULAR TELEMETRY"))

    counts: Counter[str] = Counter()
    cell_ids: set[str] = set()
    t0 = None
    async for ev in engine.run(prompt, request_id="local-001"):
        if t0 is None:
            t0 = ev.t
        print(render(ev, use_colour=use_colour, t0=t0))
        counts[ev.kind] += 1
        if ev.cell_id and ev.cell_id not in ("-", "engine"):
            cell_ids.add(ev.cell_id)

    result = engine.last_result or {}
    if "error" in result:
        print(banner("RUN FAILED"))
        print(f"  {result['error']}")
        return 1

    print(banner("CELL LINEAGE (DAG)"))
    print(_lineage_tree(cell_ids))

    print(banner("SYNTHESIS REPORT"))
    order = [
        ("convergence", "final synthesis convergence"),
        ("converged", "converged?"),
        ("peak_cells", "peak simultaneous cells"),
        ("total_mitosis", "mitosis events (fission)"),
        ("total_apoptosis", "apoptosis events (death)"),
        ("gflops", "total compute (GFLOPs)"),
        ("energy_burned", "total ATP burned"),
        ("stem_residual_energy", "stem residual energy"),
        ("live_cells_final", "cells still alive"),
        ("dag_nodes", "DAG nodes"),
        ("dag_edges", "DAG edges"),
        ("elapsed_s", "wall-clock seconds"),
    ]
    for key, label in order:
        if key in result:
            print(f"  {label:<32}: {result[key]}")
    print(f"  {'resources':<32}: {result.get('resources')}")
    print(f"  {'event breakdown':<32}: {dict(counts)}")
    print(f"  {'synthesis vector [:8]':<32}: {result.get('synthesis_vector')}")

    survival = 100.0 if result.get("live_cells_final", 1) >= 1 and result.get("convergence", 0) > 0 else 0.0
    print(banner(f"COMPUTATIONAL SURVIVAL RATE: {survival:.0f}%"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="B.I.O.M.A. local cellular simulation")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="scenario to inject")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colour")
    args = parser.parse_args()

    _enable_windows_ansi()
    use_colour = (not args.no_color) and sys.stdout.isatty()
    return asyncio.run(run(args.prompt, use_colour))


if __name__ == "__main__":
    raise SystemExit(main())
