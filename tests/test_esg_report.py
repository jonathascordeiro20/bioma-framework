"""Unit tests for bioma.esg_report — deployment ESG report from an audit log."""
from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bioma.esg_report import build_report, read_audit


def _rows():
    return [
        {"tokens_before": 5000, "tokens_after": 200, "reduction": 0.96},
        {"tokens_before": 3000, "tokens_after": 150, "reduction": 0.95},
    ]


def test_report_aggregates_measured_tokens():
    rep = build_report(_rows(), grid="world")
    assert rep["requests"] == 2
    assert rep["tokens_before"] == 8000 and rep["tokens_after"] == 350
    assert rep["tokens_saved"] == 7650
    assert abs(rep["reduction"] - (1 - 350 / 8000)) < 1e-9


def test_report_energy_bounds_ordered():
    rep = build_report(_rows())
    lo, mid, hi = rep["wh_avoided"]
    assert lo < mid < hi                     # declared low/mid/high bounds
    assert all(g >= 0 for g in rep["gco2e_avoided"])


def test_report_usd_when_price_given():
    rep = build_report(_rows(), price_in_per_mtok=10.0)
    assert abs(rep["usd_avoided"] - 7650 / 1e6 * 10.0) < 1e-9


def test_report_no_usd_without_price():
    assert build_report(_rows())["usd_avoided"] is None


def test_empty_log_is_zero_not_fabricated():
    rep = build_report([], grid="eu")
    assert rep["tokens_saved"] == 0 and rep["wh_avoided"] == (0.0, 0.0, 0.0)


def test_read_audit_skips_bad_lines(tmp_path):
    p = tmp_path / "a.jsonl"
    p.write_text(json.dumps({"tokens_before": 1, "tokens_after": 0}) + "\n\nnot-json\n",
                 encoding="utf-8")
    assert len(read_audit(str(p))) == 1
