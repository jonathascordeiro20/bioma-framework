#!/usr/bin/env python3
"""
tests/test_evolutions.py — as três evoluções de 2026-07-21:

  A. `BIOMA_STABLE_PREFIX=auto` — zona estável derivada do primeiro breakpoint
     de `cache_control` do cliente.
  B. Auto-FACT — heurística conservadora que promove constraints duráveis de
     USER a FACT (fecha a lacuna S3 sem disciplina do usuário), com corpus de
     precisão: nenhum falso positivo tolerado no conjunto negativo.
  C. Rehydration on-demand — store local content-addressed dos blocos podados
     + endpoint `GET /v1/rehydrate/{hash}`.

Offline, determinísticos, sem upstream.
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bioma.gateway import (  # noqa: E402
    create_app,
    dehydrate_anthropic,
    looks_durable,
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


# --------------------------------------------------------------------------- #
#  A — stable_prefix automático pelo breakpoint de cache
# --------------------------------------------------------------------------- #
def _session_with_breakpoint(rounds: int) -> list[dict]:
    msgs = [
        {"role": "user", "content": "kickoff"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": [
            {"type": "text", "text": "Project brief v2.",
             "cache_control": {"type": "ephemeral"}}]},
        {"role": "assistant", "content": "brief acknowledged"},
    ]
    for i in range(rounds):
        msgs += _tool_round(i)
    msgs.append({"role": "user", "content": "final ask"})
    return msgs


def test_auto_stable_prefix_freezes_up_to_first_breakpoint():
    msgs = _session_with_breakpoint(rounds=20)
    survivors, audit = dehydrate_anthropic(
        msgs, half_life=HL, safe_threshold=THR, stable_prefix=-1)
    assert audit["blocks_purged"] > 0
    # tudo até o breakpoint (inclusive) fica byte-idêntico, na ordem original
    assert survivors[:3] == msgs[:3]


def test_auto_stable_prefix_without_breakpoint_still_keeps_anchor():
    msgs = [{"role": "user", "content": "kickoff"},
            {"role": "assistant", "content": "hello"}]
    for i in range(15):
        msgs += _tool_round(i)
    msgs.append({"role": "user", "content": "final ask"})
    survivors, _ = dehydrate_anthropic(
        msgs, half_life=HL, safe_threshold=THR, stable_prefix=-1)
    assert survivors[0] == msgs[0]


# --------------------------------------------------------------------------- #
#  B — Auto-FACT: corpus de precisão
# --------------------------------------------------------------------------- #
DURABLE = [
    "All new modules must live under utils/ with type hints.",
    "Never call the payments API from the frontend.",
    "Reminder: the release train departs every Tuesday.",
    "We agreed the retry budget is 3 attempts max.",
    "Important: staging credentials rotate on day 1.",
    "Don't forget the audit flag defaults to on.",
    "O parser deve retornar int de segundos totais.",
    "Nunca exponha o token no log.",
    "Lembrete: a janela de manutenção é sábado 02:00 UTC.",
    "Ficou definido que o threshold de produção é 0.2.",
]

CHATTER = [
    "ok",
    "thanks, looks good to me",
    "hmm let me think about that",
    "run the tests again please",
    "what does this function return?",
    "haha nice catch",
    "sobe o servidor de novo",
    "qual o status do build?",
    "interesting, go on",
    "x = 1\n" * 300,  # tool-log gigante: nunca promover (limite de tamanho)
]


def test_auto_fact_promotes_all_durable_constraints():
    misses = [t for t in DURABLE if not looks_durable(t)]
    assert not misses, f"constraints não detectadas: {misses}"


def test_auto_fact_zero_false_positives_on_chatter():
    hits = [t[:40] for t in CHATTER if looks_durable(t)]
    assert not hits, f"falsos positivos: {hits}"


def test_auto_fact_saves_untagged_old_constraint():
    """A lacuna S3 real: constraint antiga, SEM tag FACT, enterrada sob ruído.
    Sem auto_fact ela morre; com auto_fact sobrevive."""
    msgs = [{"role": "user", "content": "kickoff"},
            {"role": "assistant", "content": "hello"},
            {"role": "user",
             "content": "Never deploy on Fridays, the pipeline must stay frozen."},
            {"role": "assistant", "content": "got it"}]
    for i in range(20):
        msgs += _tool_round(i)
    msgs.append({"role": "user", "content": "When can I deploy?"})

    def alive(auto: bool) -> bool:
        out, _ = dehydrate_anthropic(msgs, half_life=HL, safe_threshold=THR,
                                     auto_fact=auto)
        return any("Never deploy on Fridays" in str(m.get("content"))
                   for m in out)

    assert not alive(False), "sem auto_fact a constraint antiga deve decair (S3)"
    assert alive(True), "com auto_fact a constraint durável deve sobreviver"


def test_auto_fact_never_rescues_tool_output():
    msgs = [{"role": "user", "content": "kickoff"},
            {"role": "assistant", "content": "hello"}]
    for i in range(20):
        msgs += _tool_round(i)
    msgs.append({"role": "user", "content": "final"})
    _, a_off = dehydrate_anthropic(msgs, half_life=HL, safe_threshold=THR)
    _, a_on = dehydrate_anthropic(msgs, half_life=HL, safe_threshold=THR,
                                  auto_fact=True)
    assert a_on["blocks_purged"] == a_off["blocks_purged"], \
        "auto_fact não pode reduzir a poda de tool output"


# --------------------------------------------------------------------------- #
#  C — rehydration on-demand
# --------------------------------------------------------------------------- #
def test_rehydrate_store_roundtrip(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    store = str(tmp_path / "hibernation")
    monkeypatch.setenv("BIOMA_REHYDRATE_STORE", store)
    monkeypatch.setenv("BIOMA_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    app = create_app()
    client = TestClient(app)

    # poda direta via a função de produção, depois simula o armazenamento
    msgs = [{"role": "user", "content": "kickoff"},
            {"role": "assistant", "content": "hello"}]
    for i in range(15):
        msgs += _tool_round(i)
    msgs.append({"role": "user", "content": "final"})
    _, audit = dehydrate_anthropic(msgs, half_life=HL, safe_threshold=THR)
    purged = audit.get("_purged_units")
    assert purged, "sessão longa deve podar unidades"

    # grava como o gateway gravaria (mesmo formato content-addressed)
    import hashlib
    os.makedirs(store, exist_ok=True)
    unit = purged[0]
    blob = json.dumps(unit, ensure_ascii=False, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(blob).hexdigest()
    with open(os.path.join(store, f"{digest}.json"), "wb") as f:
        f.write(blob)

    r = client.get(f"/v1/rehydrate/{digest}")
    assert r.status_code == 200
    assert r.json()["unit"] == unit, "o bloco volta byte-idêntico"

    assert client.get(f"/v1/rehydrate/{'0' * 64}").status_code == 404
    assert client.get("/v1/rehydrate/not-a-hash").status_code == 400


def test_rehydrate_disabled_returns_404(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.delenv("BIOMA_REHYDRATE_STORE", raising=False)
    client = TestClient(create_app())
    r = client.get(f"/v1/rehydrate/{'a' * 64}")
    assert r.status_code == 404
    assert "disabled" in r.json()["error"]


def test_health_reports_new_knobs(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("BIOMA_STABLE_PREFIX", "auto")
    monkeypatch.setenv("BIOMA_PURGE_QUANTUM", "8")
    monkeypatch.setenv("BIOMA_AUTO_FACT", "1")
    h = TestClient(create_app()).get("/health").json()
    assert h["stable_prefix"] == "auto"
    assert h["purge_quantum"] == 8
    assert h["auto_fact"] is True
