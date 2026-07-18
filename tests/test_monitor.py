"""Unit tests for bioma.monitor — live terminal monitor over the audit log.

The data plane (AuditFollower/MonitorState) is tested without a terminal; the
display plane tests skip cleanly when `rich` is not installed."""
from __future__ import annotations

import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bioma.monitor import AuditFollower, MonitorState, spark


def _line(before=1000, after=100, model="test/model", **kw):
    row = {"ts": "2026-07-18T12:00:00", "model": model, "stream": False,
           "tokens_before": before, "tokens_after": after,
           "reduction": round(1 - after / before, 4),
           "kernel_latency_us": 0.8, "blocks_purged": 2}
    row.update(kw)
    return json.dumps(row) + "\n"


# --------------------------------------------------------------------------- #
#  AuditFollower — tail -f semantics
# --------------------------------------------------------------------------- #
def test_follower_reads_incrementally(tmp_path):
    p = tmp_path / "audit.jsonl"
    p.write_text(_line() + _line(2000, 100), encoding="utf-8")
    f = AuditFollower(str(p))
    assert len(f.poll()) == 2
    assert f.poll() == []                       # nothing new
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(_line(3000, 60))
    rows = f.poll()
    assert len(rows) == 1 and rows[0]["tokens_before"] == 3000


def test_follower_waits_for_missing_file(tmp_path):
    p = tmp_path / "not_yet.jsonl"
    f = AuditFollower(str(p))
    assert f.poll() == []                       # file not created yet → no crash
    p.write_text(_line(), encoding="utf-8")
    assert len(f.poll()) == 1


def test_follower_survives_truncation(tmp_path):
    p = tmp_path / "audit.jsonl"
    p.write_text(_line() + _line() + _line(), encoding="utf-8")
    f = AuditFollower(str(p))
    assert len(f.poll()) == 3
    p.write_text(_line(500, 50), encoding="utf-8")   # rotated/truncated
    rows = f.poll()
    assert len(rows) == 1 and rows[0]["tokens_before"] == 500


def test_follower_buffers_partial_line(tmp_path):
    p = tmp_path / "audit.jsonl"
    full = _line(700, 70)
    p.write_text(full[:20], encoding="utf-8")   # mid-write: no newline yet
    f = AuditFollower(str(p))
    assert f.poll() == []
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(full[20:])
    rows = f.poll()
    assert len(rows) == 1 and rows[0]["tokens_before"] == 700


def test_follower_skips_garbage_lines(tmp_path):
    p = tmp_path / "audit.jsonl"
    p.write_text("not-json\n" + _line() + "\n[1,2]\n", encoding="utf-8")
    assert len(AuditFollower(str(p)).poll()) == 1   # only the dict line survives


# --------------------------------------------------------------------------- #
#  MonitorState — aggregation
# --------------------------------------------------------------------------- #
def test_state_aggregates_totals_and_models():
    s = MonitorState()
    s.ingest(json.loads(_line(5000, 200, model="a")))
    s.ingest(json.loads(_line(3000, 150, model="b")))
    s.ingest(json.loads(_line(1000, 500, model="a")))
    assert s.requests == 3
    assert s.tokens_before == 9000 and s.tokens_after == 850
    assert s.tokens_saved == 8150
    assert abs(s.avg_reduction - (1 - 850 / 9000)) < 1e-9
    assert s.peak_reduction == pytest.approx(0.96)
    assert s.models["a"]["requests"] == 2 and s.models["b"]["before"] == 3000
    assert s.blocks_purged == 6


def test_state_ignores_malformed_rows():
    s = MonitorState()
    s.ingest({"tokens_before": "garbage"})
    s.ingest({"tokens_before": None, "tokens_after": 3})
    assert s.requests == 0 and s.tokens_saved == 0


def test_req_per_min_counts_only_live_rows():
    now = [100.0]
    s = MonitorState(clock=lambda: now[0])
    s.ingest(json.loads(_line()), live=False)   # replayed history → rate excluded
    s.ingest(json.loads(_line()))
    s.ingest(json.loads(_line()))
    assert s.req_per_min() == 2
    now[0] += 61.0                              # window slides past both arrivals
    assert s.req_per_min() == 0
    assert s.requests == 3                      # totals keep the history


def test_latency_stats_p50_and_max():
    s = MonitorState()
    for lat in (1.0, 5.0, 2.0):
        s.ingest(json.loads(_line(kernel_latency_us=lat)))
    p50, pmax = s.latency_stats()
    assert p50 == 2.0 and pmax == 5.0
    assert MonitorState().latency_stats() == (0.0, 0.0)


def test_spark_clamps_and_maps_bounds():
    assert spark([]) == ""
    line = spark([0.0, 1.0, 2.0, -1.0])
    assert line[0] == "▁" and line[1] == "█"
    assert line[2] == "█" and line[3] == "▁"    # clamped to [0, 1]
    assert len(spark([0.5] * 500, width=72)) == 72


# --------------------------------------------------------------------------- #
#  Display plane — needs rich
# --------------------------------------------------------------------------- #
def test_dashboard_renders_measured_numbers(tmp_path):
    pytest.importorskip("rich")
    from rich.console import Console
    from bioma.monitor import build_dashboard
    s = MonitorState()
    s.ingest(json.loads(_line(4604, 32, model="anthropic/claude-sonnet-5")))
    console = Console(record=True, width=140, height=40,
                      force_terminal=True, color_system=None)
    console.print(build_dashboard(s, None, audit_path="x.jsonl",
                                  grid="br", price_in=10.0))
    text = console.export_text()
    assert "B.I.O.M.A." in text
    assert "4,604" in text and "4,572" in text          # before / saved, measured
    assert "gateway offline" in text                    # health=None
    assert "grid br" in text and "estimate" in text     # labeled estimate


def test_dashboard_renders_online_health():
    pytest.importorskip("rich")
    from rich.console import Console
    from bioma.monitor import build_dashboard
    health = {"status": "ok", "kernel": "1.0.1",
              "upstream": "https://openrouter.ai/api/v1",
              "half_life": 6.0, "threshold": 0.35}
    console = Console(record=True, width=140, height=40,
                      force_terminal=True, color_system=None)
    console.print(build_dashboard(MonitorState(), health, audit_path="x.jsonl"))
    text = console.export_text()
    assert "gateway online" in text and "1.0.1" in text
    assert "waiting for the first request" in text


def test_main_once_renders_and_exits(tmp_path, monkeypatch):
    pytest.importorskip("rich")
    from bioma import monitor
    p = tmp_path / "audit.jsonl"
    p.write_text(_line(), encoding="utf-8")
    monkeypatch.setattr(monitor, "fetch_health", lambda *a, **k: None)
    assert monitor._main(["--audit", str(p), "--once"]) == 0
