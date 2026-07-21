#!/usr/bin/env python3
"""
tests/test_protocol_invariants.py — garantias novas nascidas do E2E longo real:

  A. `dehydrate_anthropic` NUNCA poda a âncora da conversa (`messages[0]`),
     mesmo com `stable_prefix=0` — upstreams estritos (api.anthropic.com)
     devolvem 400 quando o primeiro turno real some (observado em 2026-07-21).
  B. `repair_anthropic` remove órfãos de protocolo (tool_result sem tool_use
     anterior; tool_use sem tool_result seguinte) por DELEÇÃO apenas.
  C. `apply_cache_hysteresis` segura purgas pequenas (prefixo byte-idêntico →
     cache hit) e libera purgas em lote acima do limiar.

Rodam offline, determinísticos, sem rede.
"""
from __future__ import annotations

import os
import random
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bioma.gateway import (  # noqa: E402
    apply_cache_hysteresis,
    dehydrate_anthropic,
    repair_anthropic,
)

HL, THR = 6.0, 0.35


def _tool_round(i: int) -> list[dict]:
    return [
        {"role": "assistant", "content": [
            {"type": "text", "text": f"reading file {i}"},
            {"type": "tool_use", "id": f"tu_{i}", "name": "Read",
             "input": {"file_path": f"f{i}.py"}}]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": f"tu_{i}",
             "content": "x = 1\n" * 120}]},
        {"role": "assistant", "content": f"noted {i}"},
    ]


def _session(rounds: int) -> list[dict]:
    msgs = [{"role": "user", "content": "Project brief: fix the modules."},
            {"role": "assistant", "content": "Understood."}]
    for i in range(rounds):
        msgs += _tool_round(i)
    msgs.append({"role": "user", "content": "Now write the final module."})
    return msgs


# --------------------------------------------------------------------------- #
#  A — âncora da conversa nunca é podada
# --------------------------------------------------------------------------- #
def test_anchor_survives_even_with_stable_prefix_zero():
    msgs = _session(rounds=25)
    survivors, audit = dehydrate_anthropic(msgs, half_life=HL,
                                           safe_threshold=THR, stable_prefix=0)
    assert audit["blocks_purged"] > 0, "sessão longa deve podar algo"
    assert survivors[0] == msgs[0], "messages[0] deve ficar byte-idêntico"
    assert survivors[0]["role"] == "user"


def test_anchor_survives_across_sizes():
    for rounds in (5, 15, 40):
        msgs = _session(rounds)
        survivors, _ = dehydrate_anthropic(msgs, half_life=HL,
                                           safe_threshold=THR, stable_prefix=0)
        assert survivors[0] == msgs[0], f"âncora perdida com rounds={rounds}"


def _assert_protocol_valid(msgs: list[dict]) -> None:
    assert msgs and msgs[0].get("role") == "user"
    for i, m in enumerate(msgs):
        blocks = m.get("content") if isinstance(m.get("content"), list) else []
        res_ids = {b.get("tool_use_id") for b in blocks
                   if isinstance(b, dict) and b.get("type") == "tool_result"}
        use_ids = {b.get("id") for b in blocks
                   if isinstance(b, dict) and b.get("type") == "tool_use"}
        if res_ids:
            prev = msgs[i - 1] if i else {}
            prev_uses = {b.get("id") for b in (prev.get("content") or [])
                         if isinstance(b, dict) and b.get("type") == "tool_use"} \
                if isinstance(prev.get("content"), list) else set()
            assert res_ids <= prev_uses, f"tool_result órfão na posição {i}"
        if use_ids:
            nxt = msgs[i + 1] if i + 1 < len(msgs) else {}
            nxt_res = {b.get("tool_use_id") for b in (nxt.get("content") or [])
                       if isinstance(b, dict) and b.get("type") == "tool_result"} \
                if isinstance(nxt.get("content"), list) else set()
            assert use_ids & nxt_res, f"tool_use pendurado na posição {i}"


def test_dehydrated_output_is_always_protocol_valid():
    for rounds in (3, 10, 30):
        survivors, _ = dehydrate_anthropic(_session(rounds), half_life=HL,
                                           safe_threshold=THR, stable_prefix=0)
        _assert_protocol_valid(survivors)


# --------------------------------------------------------------------------- #
#  B — reparo de órfãos (backstop determinístico + fuzz semeado)
# --------------------------------------------------------------------------- #
def test_repair_drops_leading_assistant():
    broken = [{"role": "assistant", "content": "orphan opener"},
              {"role": "user", "content": "hi"},
              {"role": "assistant", "content": "hello"}]
    fixed = repair_anthropic(broken)
    assert fixed[0]["role"] == "user" and len(fixed) == 2


def test_repair_drops_orphan_tool_result():
    broken = [{"role": "user", "content": "hi"},
              {"role": "user", "content": [
                  {"type": "tool_result", "tool_use_id": "tu_ghost",
                   "content": "orphan"}]},
              {"role": "assistant", "content": "ok"}]
    fixed = repair_anthropic(broken)
    assert len(fixed) == 2
    assert all(not isinstance(m.get("content"), list) for m in fixed)


def test_repair_drops_dangling_tool_use():
    broken = [{"role": "user", "content": "hi"},
              {"role": "assistant", "content": [
                  {"type": "tool_use", "id": "tu_1", "name": "Read",
                   "input": {}}]},
              {"role": "assistant", "content": "moved on without result"}]
    fixed = repair_anthropic(broken)
    assert len(fixed) == 2
    assert fixed[1]["content"] == "moved on without result"


def test_repair_is_deletion_only_fuzz():
    rng = random.Random(42)
    base = _session(rounds=12)
    for _ in range(200):
        subset = [m for m in base if rng.random() > 0.35]
        fixed = repair_anthropic(subset)
        # deleção apenas: todo sobrevivente existe no input, na mesma ordem
        it = iter(subset)
        assert all(any(m is c for c in it) for m in fixed)
        if fixed:
            _assert_protocol_valid(fixed)


# --------------------------------------------------------------------------- #
#  C — histerese cache-aware
# --------------------------------------------------------------------------- #
def _audit(reduction: float, before: int = 10_000) -> dict:
    return {"tokens_before": before,
            "tokens_after": int(before * (1 - reduction)),
            "reduction": reduction, "kernel_latency_us": 1.0,
            "blocks_purged": 3}


def test_hysteresis_holds_small_purges():
    msgs, survivors = _session(10), _session(2)
    out, audit = apply_cache_hysteresis(msgs, survivors, _audit(0.12), 0.30)
    assert out is msgs, "abaixo do limiar → prefixo intacto (cache hit)"
    assert audit["held"] is True and audit["reduction"] == 0.0
    assert audit["potential_reduction"] == 0.12
    assert audit["tokens_after"] == audit["tokens_before"]


def test_hysteresis_releases_batched_purge():
    msgs, survivors = _session(10), _session(2)
    out, audit = apply_cache_hysteresis(msgs, survivors, _audit(0.45), 0.30)
    assert out is survivors, "acima do limiar → purga em lote aplicada"
    assert "held" not in audit and audit["reduction"] == 0.45


def test_hysteresis_disabled_by_default():
    msgs, survivors = _session(10), _session(2)
    out, audit = apply_cache_hysteresis(msgs, survivors, _audit(0.05), 0.0)
    assert out is survivors, "0.0 = desligada → comportamento atual preservado"
    assert "held" not in audit


# --------------------------------------------------------------------------- #
#  D — fronteira quantizada: saída podada byte-idêntica entre avanços
# --------------------------------------------------------------------------- #
def _growing_session(turns: int) -> list[dict]:
    """Sessão que cresce turno a turno, como o Claude Code reenvia o transcript."""
    msgs = [{"role": "user", "content": "Project brief: fix the modules."},
            {"role": "assistant", "content": "Understood."}]
    for i in range(turns):
        msgs += _tool_round(i)
    msgs.append({"role": "user", "content": f"Continue with step {turns}."})
    return msgs


def _prune(turns: int, quantum: int) -> list[dict]:
    out, _ = dehydrate_anthropic(_growing_session(turns), half_life=HL,
                                 safe_threshold=THR, stable_prefix=0,
                                 quantum=quantum)
    return out


def _is_prefix(shorter: list[dict], longer: list[dict]) -> bool:
    """out(t) sem a cauda sagrada (último user) precisa ser prefixo de out(t+1)
    para o prompt-cache do provedor acertar no contexto já podado."""
    body = shorter[:-1]
    return len(body) <= len(longer) and all(
        a == b for a, b in zip(body, longer))


def test_quantum_output_stable_between_boundary_advances():
    K = 8
    invalidations = sum(
        0 if _is_prefix(_prune(t, K), _prune(t + 1, K)) else 1
        for t in range(2, 30))
    # a fronteira só avança a cada K unidades novas (3 msgs/rodada ≈ 3 unidades
    # por turno) → poucas invalidações num intervalo de 28 turnos
    assert invalidations <= (28 * 3) // K + 1, f"invalidações demais: {invalidations}"


def test_no_quantum_invalidates_nearly_every_turn():
    invalidations = sum(
        0 if _is_prefix(_prune(t, 0), _prune(t + 1, 0)) else 1
        for t in range(2, 30))
    K = 8
    quantized = sum(
        0 if _is_prefix(_prune(t, K), _prune(t + 1, K)) else 1
        for t in range(2, 30))
    assert quantized < invalidations, (
        f"quantum deve reduzir invalidações: {quantized} vs {invalidations}")


def test_quantum_preserves_contract_probes():
    for turns in (5, 12, 25):
        out = _prune(turns, quantum=8)
        assert out[0] == _growing_session(turns)[0], "âncora intacta"
        assert out[-1]["content"] == f"Continue with step {turns}.", "cauda sagrada"
        _assert_protocol_valid(out)


def test_quantum_still_reduces_tokens():
    _, audit = dehydrate_anthropic(_growing_session(30), half_life=HL,
                                   safe_threshold=THR, stable_prefix=0,
                                   quantum=8)
    assert audit["reduction"] > 0.3, "quantização não pode anular a economia"
    assert audit.get("quantum_frozen_units", 0) > 0
