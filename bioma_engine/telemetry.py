"""
`telemetry.py` — Biological telemetry dashboard.

The engine emits a stream of :class:`TelemetryEvent` objects describing every
biological transition (mitosis, secretion, homeostatic correction, apoptosis,
synthesis).  This module defines the event schema plus a colourised terminal
renderer that makes a run read like a live cell-culture monitor.

The same event objects are:
  * pretty-printed to the terminal by :func:`render` (used by ``run_local.py``),
  * serialised to JSON by :meth:`TelemetryEvent.as_sse` for the FastAPI server.

Keeping one schema for both surfaces guarantees the local prototype and the
production server describe the organism identically.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any


# Event kinds — the "vocabulary" of the cellular lifecycle.
KIND_GENESIS = "genesis"          # the stem cell is born
KIND_DIVERGENCE = "divergence"    # semantic-divergence measurement
KIND_MITOSIS = "mitosis"          # a cell divides into children
KIND_FORWARD = "forward"          # a cell performs a compute (metabolic) step
KIND_SECRETE = "secrete"          # a cell writes hormones to the manifold
KIND_SENSE = "sense"              # a cell reads the manifold
KIND_HOMEOSTASIS = "homeostasis"  # entropy is corrected toward the setpoint
KIND_ADAPT = "adapt"              # a cell performs a local gradient adaptation
KIND_APOPTOSIS = "apoptosis"      # programmed cell death + resource reclaim
KIND_SYNTHESIS = "synthesis"      # parent fuses children into a solution
KIND_CONVERGENCE = "convergence"  # the colony reaches a stable answer
KIND_ERROR = "error"              # a recoverable fault (surfaced, never hidden)


# ANSI colours keyed by event kind for the terminal dashboard.
_COLOURS = {
    KIND_GENESIS: "\033[1;96m",
    KIND_DIVERGENCE: "\033[0;96m",
    KIND_MITOSIS: "\033[1;95m",
    KIND_FORWARD: "\033[0;37m",
    KIND_SECRETE: "\033[0;93m",
    KIND_SENSE: "\033[0;94m",
    KIND_HOMEOSTASIS: "\033[0;92m",
    KIND_ADAPT: "\033[0;36m",
    KIND_APOPTOSIS: "\033[1;91m",
    KIND_SYNTHESIS: "\033[1;92m",
    KIND_CONVERGENCE: "\033[1;97;42m",
    KIND_ERROR: "\033[1;97;41m",
}
_RESET = "\033[0m"

_GLYPHS = {
    KIND_GENESIS: "🌱",
    KIND_DIVERGENCE: "🧭",
    KIND_MITOSIS: "🧬",
    KIND_FORWARD: "⚙️",
    KIND_SECRETE: "🧪",
    KIND_SENSE: "👁️",
    KIND_HOMEOSTASIS: "🌡️",
    KIND_ADAPT: "📈",
    KIND_APOPTOSIS: "☠️",
    KIND_SYNTHESIS: "🧠",
    KIND_CONVERGENCE: "✅",
    KIND_ERROR: "🔥",
}


@dataclass
class TelemetryEvent:
    """A single, timestamped biological event in the life of the colony."""

    kind: str
    message: str
    cell_id: str = "-"
    generation: int = 0
    # Free-form biological metrics (energy, entropy, shapes, counts, …).
    metrics: dict[str, Any] = field(default_factory=dict)
    t: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def as_sse(self) -> str:
        """Encode as a Server-Sent-Events frame (``event:`` + ``data:``)."""
        payload = json.dumps(self.as_dict(), default=_json_default)
        return f"event: {self.kind}\ndata: {payload}\n\n"

    def as_json_line(self) -> str:
        """Encode as a single newline-delimited JSON record (for logs/WS)."""
        return json.dumps(self.as_dict(), default=_json_default)


def _json_default(obj: Any) -> Any:
    """Best-effort JSON coercion for stray numpy/torch scalars."""
    if hasattr(obj, "item"):
        try:
            return obj.item()
        except Exception:
            return str(obj)
    return str(obj)


def _fmt_metrics(metrics: dict[str, Any]) -> str:
    parts = []
    for key, value in metrics.items():
        if isinstance(value, float):
            parts.append(f"{key}={value:.4g}")
        else:
            parts.append(f"{key}={value}")
    return "  ".join(parts)


def render(event: TelemetryEvent, use_colour: bool = True, t0: float | None = None) -> str:
    """Render one event as a single dashboard line."""
    glyph = _GLYPHS.get(event.kind, "•")
    elapsed = event.t - t0 if t0 is not None else 0.0
    header = f"[{elapsed:8.3f}s] {glyph} {event.kind.upper():<11}"
    body = f"cell={event.cell_id:<14} gen={event.generation}  {event.message}"
    metrics = _fmt_metrics(event.metrics)
    line = f"{header} | {body}"
    if metrics:
        line += f"   « {metrics} »"
    if use_colour:
        colour = _COLOURS.get(event.kind, "")
        line = f"{colour}{line}{_RESET}"
    return line


def banner(title: str, width: int = 78) -> str:
    """A centred banner for section headers in the terminal dashboard."""
    title = f" {title} "
    pad = max(0, width - len(title))
    left = pad // 2
    right = pad - left
    return "\033[1;97;44m" + "═" * left + title + "═" * right + _RESET
