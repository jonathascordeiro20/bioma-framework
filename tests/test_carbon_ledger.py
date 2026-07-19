"""Unit tests for bioma.carbon_ledger — hash chain, bounded ledger, Ed25519."""
from __future__ import annotations

import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bioma.carbon_ledger import (build_ledger, chain_audit, keygen, read_audit,
                                 sign_ledger, verify_chain, verify_ledger)


def _audit():
    return [
        {"ts": "2026-07-19T10:00:00", "model": "m", "tokens_before": 5000, "tokens_after": 200},
        {"ts": "2026-07-19T10:00:01", "model": "m", "tokens_before": 3000, "tokens_after": 150},
    ]


# --------------------------------------------------------------------------- #
# hash chain
# --------------------------------------------------------------------------- #
def test_chain_is_linked_and_verifies():
    chained = chain_audit(_audit())
    assert chained[0]["prev_hash"] == "GENESIS"
    assert chained[1]["prev_hash"] == chained[0]["hash"]
    ok, broken = verify_chain(chained)
    assert ok and broken is None


def test_tamper_breaks_chain():
    chained = chain_audit(_audit())
    chained[0]["tokens_before"] = 999999      # inflate savings after the fact
    ok, broken = verify_chain(chained)
    assert not ok and broken == 0


def test_dropped_row_breaks_chain():
    chained = chain_audit(_audit() + [{"ts": "t", "model": "m",
                                       "tokens_before": 1000, "tokens_after": 100}])
    del chained[1]                            # remove a row
    ok, broken = verify_chain(chained)
    assert not ok


# --------------------------------------------------------------------------- #
# ledger math (exact reduction, bounded energy)
# --------------------------------------------------------------------------- #
def test_ledger_aggregates_measured_tokens():
    L = build_ledger(_audit(), grid="br", price_in_per_mtok=2.0)
    assert L["tokens"] == {"before": 8000, "after": 350, "saved": 7650}
    assert abs(L["input_reduction_pct"] - 100 * (1 - 350 / 8000)) < 1e-6
    lo, mid, hi = L["wh_avoided"]
    assert lo < mid < hi                      # bounds ordered, never a single number
    assert abs(L["usd_input_avoided"] - 7650 / 1e6 * 2.0) < 1e-9
    assert "counterfactual" in L["accounting_note"].lower()


def test_ledger_refuses_broken_chain():
    chained = chain_audit(_audit())
    chained[1]["tokens_after"] = 0            # tamper
    with pytest.raises(ValueError, match="chain broken"):
        build_ledger(chained, grid="world")


def test_empty_savings_is_zero_not_fabricated():
    L = build_ledger([{"ts": "t", "model": "m", "tokens_before": 100, "tokens_after": 100}])
    assert L["tokens"]["saved"] == 0 and L["wh_avoided"] == [0.0, 0.0, 0.0]


# --------------------------------------------------------------------------- #
# signing / verification (Ed25519)
# --------------------------------------------------------------------------- #
def test_sign_and_verify_roundtrip(tmp_path):
    pytest.importorskip("cryptography")
    stem = str(tmp_path / "issuer")
    keyfile, pubfile = keygen(stem)
    L = build_ledger(_audit(), grid="eu")
    env = sign_ledger(L, open(keyfile, "rb").read())
    assert verify_ledger(env, open(pubfile, "rb").read()) is True


def test_verify_fails_on_altered_ledger(tmp_path):
    pytest.importorskip("cryptography")
    stem = str(tmp_path / "issuer")
    keyfile, pubfile = keygen(stem)
    env = sign_ledger(build_ledger(_audit()), open(keyfile, "rb").read())
    env["ledger"]["tokens"]["saved"] = 999999   # forge the headline number
    assert verify_ledger(env, open(pubfile, "rb").read()) is False


def test_verify_fails_with_wrong_key(tmp_path):
    pytest.importorskip("cryptography")
    env = sign_ledger(build_ledger(_audit()),
                      open(keygen(str(tmp_path / "a"))[0], "rb").read())
    _, other_pub = keygen(str(tmp_path / "b"))
    assert verify_ledger(env, open(other_pub, "rb").read()) is False


def test_read_audit_skips_garbage(tmp_path):
    p = tmp_path / "a.jsonl"
    p.write_text(json.dumps(_audit()[0]) + "\n\nnot-json\n", encoding="utf-8")
    assert len(read_audit(str(p))) == 1
