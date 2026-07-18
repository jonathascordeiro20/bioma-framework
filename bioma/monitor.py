"""
`bioma/monitor.py` — the terminal cockpit: a real-time view of everything the
deployment measures.

Reads the SAME ground truth as the ESG report — the gateway's per-request audit
JSONL (`BIOMA_AUDIT_LOG`) — and follows it live (`tail -f` semantics, safe
against truncation/rotation and partial writes), so every number on screen is
exactly a number in the log: tokens before/after, reduction, kernel μs, blocks
purged, per model. Nothing displayed is invented; the energy/cost panel reuses
the declared-coefficient estimator from `bioma.esg` (bounded low/mid/high,
always labeled as an estimate).

    pip install "bioma-framework[monitor]"
    bioma-monitor                                  # follows bioma_gateway_audit.jsonl
    bioma-monitor --audit run.jsonl --grid br --price-in 2.0

Panels: session totals, live reduction sparkline, kernel latency, per-model
table, ESG/cost estimate, request feed, and gateway `/health` status (polled by
a stdlib-only daemon thread — the monitor itself needs nothing but `rich`).

Flags: `--tail` starts at the end of the log (live traffic only, ignore
history); `--once` renders a single frame and exits (CI/screenshot-friendly).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.request
from collections import deque
from typing import Any, Optional

from bioma.esg import GRID_GCO2_PER_KWH, estimate_saving

try:  # display layer is opt-in: `pip install "bioma-framework[monitor]"`
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    _HAS_RICH = True
except ImportError:  # aggregation (AuditFollower/MonitorState) still importable
    _HAS_RICH = False

SPARK_BLOCKS = "▁▂▃▄▅▆▇█"


def spark(values, width: int = 72) -> str:
    """Unicode sparkline of the last `width` values, each clamped to [0, 1]."""
    out = []
    for v in list(values)[-width:]:
        v = min(max(float(v), 0.0), 1.0)
        out.append(SPARK_BLOCKS[min(int(v * len(SPARK_BLOCKS)), len(SPARK_BLOCKS) - 1)])
    return "".join(out)


# --------------------------------------------------------------------------- #
#  Data plane — pure, testable without a terminal
# --------------------------------------------------------------------------- #
class AuditFollower:
    """`tail -f` over the gateway audit JSONL.

    Byte-offset based: survives the file not existing yet (waits), truncation /
    rotation (size shrank → re-read from 0), and partial writes (only complete
    ``\\n``-terminated lines are consumed; the remainder stays buffered)."""

    def __init__(self, path: str):
        self.path = path
        self._pos = 0
        self._buf = b""

    def poll(self) -> list[dict]:
        try:
            size = os.path.getsize(self.path)
        except OSError:                       # not created yet (or vanished)
            self._pos, self._buf = 0, b""
            return []
        if size < self._pos:                  # truncated/rotated → start over
            self._pos, self._buf = 0, b""
        if size == self._pos:
            return []
        with open(self.path, "rb") as f:
            f.seek(self._pos)
            chunk = f.read()
        self._pos += len(chunk)
        self._buf += chunk
        *complete, self._buf = self._buf.split(b"\n")
        rows: list[dict] = []
        for raw in complete:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows


class MonitorState:
    """Aggregation of audit rows — everything the dashboard shows.

    `ingest(row, live=False)` marks history replayed at startup: it counts in
    the session totals but not in the requests-per-minute rate."""

    def __init__(self, window: int = 240, clock=time.monotonic):
        self._clock = clock
        self.started = clock()
        self.requests = 0
        self.tokens_before = 0
        self.tokens_after = 0
        self.blocks_purged = 0
        self.peak_reduction = 0.0
        self.reductions: deque[float] = deque(maxlen=window)
        self.latencies: deque[float] = deque(maxlen=window)
        self.models: dict[str, dict] = {}
        self.feed: deque[dict] = deque(maxlen=10)
        self._live_arrivals: deque[float] = deque()

    @property
    def tokens_saved(self) -> int:
        return self.tokens_before - self.tokens_after

    @property
    def avg_reduction(self) -> float:
        return (1 - self.tokens_after / self.tokens_before) if self.tokens_before else 0.0

    def req_per_min(self) -> int:
        now = self._clock()
        while self._live_arrivals and now - self._live_arrivals[0] > 60.0:
            self._live_arrivals.popleft()
        return len(self._live_arrivals)

    def latency_stats(self) -> tuple[float, float]:
        """(p50, max) of the kernel latency window, in μs."""
        vals = sorted(self.latencies)
        if not vals:
            return (0.0, 0.0)
        return (vals[len(vals) // 2], vals[-1])

    def ingest(self, row: dict, *, live: bool = True) -> None:
        try:
            before = int(row.get("tokens_before", 0))
            after = int(row.get("tokens_after", 0))
        except (TypeError, ValueError):
            return
        red = float(row.get("reduction") or 0.0)
        lat = float(row.get("kernel_latency_us") or 0.0)
        self.requests += 1
        self.tokens_before += before
        self.tokens_after += after
        self.blocks_purged += int(row.get("blocks_purged") or 0)
        self.peak_reduction = max(self.peak_reduction, red)
        self.reductions.append(red)
        self.latencies.append(lat)
        m = self.models.setdefault(str(row.get("model", "?")),
                                   {"requests": 0, "before": 0, "after": 0})
        m["requests"] += 1
        m["before"] += before
        m["after"] += after
        self.feed.appendleft(row)
        if live:
            self._live_arrivals.append(self._clock())


class HealthPoller(threading.Thread):
    """Polls the gateway's `GET /health` in a daemon thread (stdlib urllib —
    no extra dependency). `latest` is the parsed dict or None when offline."""

    def __init__(self, gateway_url: str, interval: float = 2.0):
        super().__init__(daemon=True)
        self.url = gateway_url.rstrip("/") + "/health"
        self.interval = interval
        self.latest: Optional[dict] = None
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            self.latest = fetch_health(self.url)
            self._stop.wait(self.interval)

    def stop(self) -> None:
        self._stop.set()


def fetch_health(health_url: str, timeout: float = 1.5) -> Optional[dict]:
    try:
        with urllib.request.urlopen(health_url, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


# --------------------------------------------------------------------------- #
#  Display plane — rich renderables
# --------------------------------------------------------------------------- #
def _pct(v: float) -> str:
    # truncate (not round) so 0.9998 shows −99.9%, never an overstated −100.0%
    return f"−{int(v * 1000) / 10:.1f}%"


def _red_style(v: float) -> str:
    return "bold green" if v >= 0.5 else ("yellow" if v >= 0.2 else "red")


def _header(state: MonitorState, health: Optional[dict], audit_path: str) -> Any:
    left = Text("B.I.O.M.A. ", style="bold cyan")
    left.append("live monitor", style="bold")
    if health:
        left.append("   ● gateway online", style="bold green")
        left.append(f" · kernel {health.get('kernel', '?')}"
                    f" · upstream {str(health.get('upstream', '?')).split('//')[-1]}"
                    f" · t½ {health.get('half_life', '?')}"
                    f" · threshold {health.get('threshold', '?')}", style="dim")
    else:
        left.append("   ○ gateway offline", style="bold red")
        left.append(" (start it: bioma-gateway)", style="dim")
    up = int(state._clock() - state.started)
    left.append(f"   audit: {audit_path} · up {up // 60:02d}:{up % 60:02d}", style="dim")
    return Panel(left, border_style="cyan")


def _totals(state: MonitorState) -> Any:
    p50, pmax = state.latency_stats()
    grid = Table.grid(expand=True)
    cells = [
        ("Requests", f"{state.requests:,}", "bold"),
        ("Tokens in → out", f"{state.tokens_before:,} → {state.tokens_after:,}", "bold"),
        ("Saved", f"{state.tokens_saved:,}", "bold green"),
        ("Avg reduction", _pct(state.avg_reduction), _red_style(state.avg_reduction)),
        ("Peak", _pct(state.peak_reduction), "bold green"),
        ("Kernel μs p50/max", f"{p50:.1f} / {pmax:.1f}", "bold"),
        ("Req/min", f"{state.req_per_min()}", "bold"),
        ("Blocks purged", f"{state.blocks_purged:,}", "bold"),
    ]
    for _ in cells:
        grid.add_column(justify="center", ratio=1)
    grid.add_row(*(Text(label, style="dim") for label, _, _ in cells))
    grid.add_row(*(Text(value, style=style) for _, value, style in cells))
    return Panel(grid, title="session — measured from the audit log",
                 title_align="left", border_style="white")


def _sparkline(state: MonitorState) -> Any:
    if state.reductions:
        line = Text(spark(state.reductions), style="green")
    else:
        line = Text("waiting for the first request through the gateway…", style="dim")
    return Panel(line, title=f"reduction per request (last {len(state.reductions)})",
                 title_align="left", border_style="green")


def _model_table(state: MonitorState) -> Any:
    t = Table(expand=True, border_style="dim", pad_edge=False)
    t.add_column("model", overflow="ellipsis", max_width=30)
    t.add_column("req", justify="right")
    t.add_column("in → out", justify="right")
    t.add_column("saved", justify="right", style="green")
    t.add_column("avg", justify="right")
    ranked = sorted(state.models.items(),
                    key=lambda kv: kv[1]["before"] - kv[1]["after"], reverse=True)
    for name, m in ranked[:8]:
        red = (1 - m["after"] / m["before"]) if m["before"] else 0.0
        t.add_row(name, f"{m['requests']:,}", f"{m['before']:,} → {m['after']:,}",
                  f"{m['before'] - m['after']:,}", Text(_pct(red), style=_red_style(red)))
    return Panel(t, title="per model", title_align="left", border_style="white")


def _feed(state: MonitorState) -> Any:
    t = Table(expand=True, border_style="dim", pad_edge=False, show_header=False)
    t.add_column("ts", style="dim", no_wrap=True)
    t.add_column("model", overflow="ellipsis", max_width=26)
    t.add_column("tokens", justify="right")
    t.add_column("red", justify="right")
    t.add_column("μs", justify="right", style="dim")
    for row in state.feed:
        red = float(row.get("reduction") or 0.0)
        ts = str(row.get("ts", ""))
        t.add_row(ts[-8:], str(row.get("model", "?")),
                  f"{int(row.get('tokens_before', 0)):,}→{int(row.get('tokens_after', 0)):,}",
                  Text(_pct(red), style=_red_style(red)),
                  f"{float(row.get('kernel_latency_us') or 0.0):.1f}")
    return Panel(t, title="request feed", title_align="left", border_style="white")


def _esg(state: MonitorState, grid: str, price_in: Optional[float]) -> Any:
    saved = state.tokens_saved
    body = Text()
    if saved > 0:
        est = estimate_saving(saved, grid=grid)
        wl, wm, wh = est["wh"]
        _, gm, _ = est["gco2e"]
        body.append(f"Energy avoided: {wl:,.1f} / ", style="dim")
        body.append(f"{wm:,.1f}", style="bold green")
        body.append(f" / {wh:,.1f} Wh (low/mid/high) · CO₂e avoided: ", style="dim")
        body.append(f"{gm:,.1f} g", style="bold green")
        body.append(f" (grid {grid})", style="dim")
        if price_in is not None:
            body.append(f" · input cost avoided: ", style="dim")
            body.append(f"${saved / 1e6 * price_in:,.4f}", style="bold green")
            body.append(f" (at ${price_in:,.2f}/Mtok — estimate)", style="dim")
    else:
        body.append("no measured savings yet", style="dim")
    body.append("\ntokens are measured ground truth; energy/cost use the declared "
                "coefficients in bioma.esg (estimates with bounds)", style="dim")
    return Panel(body, title="ESG / cost", title_align="left", border_style="green")


def build_dashboard(state: MonitorState, health: Optional[dict], *, audit_path: str,
                    grid: str = "world", price_in: Optional[float] = None) -> Any:
    layout = Layout()
    layout.split_column(
        Layout(_header(state, health, audit_path), name="header", size=3),
        Layout(_totals(state), name="totals", size=5),
        Layout(_sparkline(state), name="spark", size=3),
        Layout(name="middle"),
        Layout(_esg(state, grid, price_in), name="esg", size=4),
    )
    layout["middle"].split_row(Layout(_model_table(state), name="models"),
                               Layout(_feed(state), name="feed"))
    return layout


# --------------------------------------------------------------------------- #
#  Entry point
# --------------------------------------------------------------------------- #
def _main(argv: Optional[list] = None) -> int:
    try:  # legacy Windows consoles/pipes default to cp1252 → force utf-8
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="B.I.O.M.A. live terminal monitor — follows the gateway audit log.")
    ap.add_argument("--audit",
                    default=os.environ.get("BIOMA_AUDIT_LOG", "bioma_gateway_audit.jsonl"),
                    help="audit JSONL written by the gateway (BIOMA_AUDIT_LOG)")
    ap.add_argument("--gateway",
                    default=os.environ.get("BIOMA_GATEWAY_URL", "http://127.0.0.1:8790"),
                    help="gateway base URL for /health polling")
    ap.add_argument("--grid", default=os.environ.get("BIOMA_MONITOR_GRID", "world"),
                    choices=sorted(GRID_GCO2_PER_KWH))
    ap.add_argument("--price-in", type=float, default=None,
                    help="input price $/M tokens (optional → $ avoided, labeled estimate)")
    ap.add_argument("--refresh", type=float, default=4.0, help="frames per second")
    ap.add_argument("--tail", action="store_true",
                    help="start at the END of the log (live traffic only)")
    ap.add_argument("--once", action="store_true",
                    help="render one frame and exit (CI/screenshot-friendly)")
    args = ap.parse_args(argv)

    if not _HAS_RICH:
        print('the monitor needs rich — install with: pip install "bioma-framework[monitor]"')
        return 2

    follower = AuditFollower(args.audit)
    state = MonitorState()
    if args.tail:
        follower.poll()                      # consume history without ingesting
    else:
        for row in follower.poll():
            state.ingest(row, live=False)    # history counts in totals, not in req/min

    if args.once:
        health = fetch_health(args.gateway.rstrip("/") + "/health", timeout=0.8)
        Console().print(build_dashboard(state, health, audit_path=args.audit,
                                        grid=args.grid, price_in=args.price_in))
        return 0

    poller = HealthPoller(args.gateway)
    poller.start()
    interval = 1.0 / max(args.refresh, 0.5)
    try:
        with Live(build_dashboard(state, poller.latest, audit_path=args.audit,
                                  grid=args.grid, price_in=args.price_in),
                  refresh_per_second=args.refresh, screen=True) as live:
            while True:
                for row in follower.poll():
                    state.ingest(row)
                live.update(build_dashboard(state, poller.latest, audit_path=args.audit,
                                            grid=args.grid, price_in=args.price_in))
                time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        poller.stop()
    Console().print(
        f"session: {state.requests:,} requests · {state.tokens_before:,} → "
        f"{state.tokens_after:,} tokens · saved {state.tokens_saved:,} "
        f"({_pct(state.avg_reduction)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
