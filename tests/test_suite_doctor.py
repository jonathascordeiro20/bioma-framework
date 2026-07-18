"""Unit tests for bioma_suite.doctor — the one-shot install checkup.

The suite package lives in `bioma_suite/` (its own distribution); tests import
it straight from the source tree, like the rest of the repo's tests do."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_SUITE = os.path.join(_ROOT, "bioma_suite")
if _SUITE not in sys.path:
    sys.path.insert(0, _SUITE)

from bioma_suite import doctor


def test_probe_reports_installed_component():
    assert doctor.probe("bioma_micro", ("bioma_micro",)) is not None


def test_probe_missing_import_is_none_not_exception():
    assert doctor.probe("whatever", ("module_that_does_not_exist_xyz",)) is None


def test_probe_import_is_ground_truth_over_metadata():
    # a real dist name with a broken import list must still report None
    assert doctor.probe("bioma_micro", ("bioma_micro", "nope_xyz")) is None


def test_kernel_smoke_measures_real_reduction():
    smoke = doctor.kernel_smoke()
    assert smoke is not None
    assert smoke["reduction"] > 0.5           # 50× "noise" vs one SYSTEM line
    assert smoke["kernel_latency_us"] >= 0.0


def test_report_covers_every_component_plus_smoke():
    rep = doctor.report()
    assert set(doctor.COMPONENTS) <= set(rep)
    assert "_smoke" in rep
    for name in doctor.CORE:                   # core is importable in this env
        assert rep[name] is not None


def test_main_exits_zero_when_core_healthy(capsys):
    assert doctor._main() == 0
    out = capsys.readouterr().out
    assert "install checkup" in out
    assert "kernel smoke" in out and "OK" in out
    assert "core healthy" in out


def test_main_exits_one_when_kernel_broken(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "kernel_smoke", lambda: None)
    assert doctor._main() == 1
    assert "core BROKEN" in capsys.readouterr().out
