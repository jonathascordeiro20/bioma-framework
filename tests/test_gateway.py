"""Unit tests for bioma.gateway — offline, deterministic (mock upstream).

Verifies the drop-in gateway's design guarantees without any network:
apoptosis fires, the current query is preserved, the cache-safe prefix is
byte-identical across calls, and tool_call/tool pairs never orphan.
"""
from __future__ import annotations

import json
import os
import sys

import httpx
import pytest
from fastapi.testclient import TestClient

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bioma.gateway import (create_app, dehydrate_anthropic,  # noqa: E402
                           dehydrate_messages, redact_image_secrets)


# ---- a mock upstream that echoes back the forwarded messages -------------- #
def _mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        sent = json.loads(request.content.decode())
        if request.url.path.endswith("/messages"):   # Anthropic surface
            return httpx.Response(200, json={
                "id": "msg-mock", "type": "message", "role": "assistant",
                "model": sent.get("model", "?"),
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 2},
                "_forwarded_messages": sent["messages"],
                "_forwarded_system": sent.get("system")})
        return httpx.Response(200, json={   # OpenAI surface
            "id": "cmpl-mock", "object": "chat.completion",
            "model": sent.get("model", "?"),
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            "_forwarded_messages": sent["messages"]})
    return httpx.MockTransport(handler)


@pytest.fixture()
def client():
    app = create_app(upstream="http://mock/v1", transport=_mock_transport())
    with TestClient(app) as c:
        yield c


def _long_session(rounds: int = 15) -> list[dict]:
    msgs = [{"role": "system", "content": "You are a copilot."},
            {"role": "user", "content": "FACT: the release tag is v9.2.1"}]
    for i in range(rounds):
        msgs += [{"role": "assistant", "content": f"verbose log line {i} " * 40},
                 {"role": "user", "content": f"step {i}: continue"},
                 {"role": "assistant", "content": f"step {i} done"}]
    msgs.append({"role": "user", "content": "What is the release tag?"})
    return msgs


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_apoptosis_reduces_and_reports(client):
    r = client.post("/v1/chat/completions",
                    json={"model": "m", "messages": _long_session()})
    assert r.status_code == 200
    b = r.json()["bioma"]
    assert b["reduction"] > 0.5
    assert b["tokens_after"] < b["tokens_before"]
    assert b["kernel_latency_us"] >= 0


def test_current_query_is_preserved(client):
    r = client.post("/v1/chat/completions",
                    json={"model": "m", "messages": _long_session()})
    fwd = r.json()["_forwarded_messages"]
    assert fwd[-1]["role"] == "user"
    assert fwd[-1]["content"] == "What is the release tag?"


def test_fact_and_system_survive(client):
    r = client.post("/v1/chat/completions",
                    json={"model": "m", "messages": _long_session()})
    fwd = r.json()["_forwarded_messages"]
    contents = [m.get("content", "") for m in fwd]
    assert any(c == "You are a copilot." for c in contents)          # SYSTEM kept
    assert any("FACT: the release tag is v9.2.1" in c for c in contents)  # FACT kept


def test_cache_safe_prefix_is_identical_across_calls(client):
    # a longer session and a shorter one share the same durable prefix; the
    # surviving system+FACT prefix must be byte-identical (prompt-cache-safe)
    r1 = client.post("/v1/chat/completions",
                     json={"model": "m", "messages": _long_session(15)})
    r2 = client.post("/v1/chat/completions",
                     json={"model": "m", "messages": _long_session(25)})
    p1 = [m["content"] for m in r1.json()["_forwarded_messages"][:2]]
    p2 = [m["content"] for m in r2.json()["_forwarded_messages"][:2]]
    assert p1 == p2  # deletion-only + order-preserving ⇒ stable prefix


def test_tool_pairs_never_orphan(client):
    msgs = [{"role": "system", "content": "sys"}]
    for i in range(12):
        msgs += [
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": f"c{i}", "type": "function",
                             "function": {"name": "grep", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": f"c{i}", "content": f"result {i} " * 30},
        ]
    msgs.append({"role": "user", "content": "summarize"})
    r = client.post("/v1/chat/completions", json={"model": "m", "messages": msgs})
    fwd = r.json()["_forwarded_messages"]
    # every tool message must be immediately preceded by an assistant tool_call
    for i, m in enumerate(fwd):
        if m.get("role") == "tool":
            assert i > 0 and fwd[i - 1].get("tool_calls"), "orphaned tool result"
    # every assistant tool_call must be followed by its tool result(s)
    for i, m in enumerate(fwd):
        if m.get("role") == "assistant" and m.get("tool_calls"):
            assert i + 1 < len(fwd) and fwd[i + 1].get("role") == "tool"


def test_audit_jsonl_written(tmp_path, monkeypatch):
    log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("BIOMA_AUDIT_LOG", str(log))
    app = create_app(upstream="http://mock/v1", transport=_mock_transport())
    with TestClient(app) as c:
        c.post("/v1/chat/completions",
               json={"model": "m", "messages": _long_session()})
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["model"] == "m" and rec["reduction"] > 0.5


def test_no_history_passthrough():
    # only a current query, no history → nothing to dehydrate, no crash
    msgs = [{"role": "user", "content": "hi"}]
    survivors, audit = dehydrate_messages(msgs, half_life=6.0, safe_threshold=0.35)
    assert survivors == msgs and audit["reduction"] == 0.0


def test_fact_in_list_content_survives():
    # regression: a durable block carrying cache_control (list content) must be
    # recognized as FACT and survive, not fall through to USER and get purged.
    durable = {"role": "user", "content": [
        {"type": "text", "text": "FACT: the release tag is v9.2.1",
         "cache_control": {"type": "ephemeral"}}]}
    msgs = [{"role": "system", "content": "sys"}, durable]
    for i in range(20):
        msgs += [{"role": "assistant", "content": f"noise {i} " * 40},
                 {"role": "user", "content": f"step {i}"}]
    msgs.append({"role": "user", "content": "What is the release tag?"})
    survivors, _ = dehydrate_messages(msgs, half_life=6.0, safe_threshold=0.35)
    assert durable in survivors  # the cache_control block survived apoptosis


def test_cache_control_block_treated_as_durable():
    block = {"role": "user", "content": [
        {"type": "text", "text": "big stable prefix",
         "cache_control": {"type": "ephemeral"}}]}
    from bioma.gateway import _unit_signal
    import bioma_micro as k
    assert _unit_signal([block]) == k.FACT


# ---- Anthropic /v1/messages surface --------------------------------------- #
def _anthropic_session(rounds: int = 15) -> list[dict]:
    msgs = [{"role": "user", "content": [
        {"type": "text", "text": "FACT: the release tag is v9.2.1",
         "cache_control": {"type": "ephemeral"}}]}]
    for i in range(rounds):
        msgs += [
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": f"t{i}", "name": "grep", "input": {}}]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": f"t{i}",
                 "content": f"verbose result {i} " * 40}]},
        ]
    msgs.append({"role": "user", "content": "What is the release tag?"})
    return msgs


def test_anthropic_apoptosis_and_system_passthrough(client):
    r = client.post("/v1/messages", json={
        "model": "anthropic/claude-sonnet-5", "max_tokens": 50,
        "system": "You are terse.", "messages": _anthropic_session()})
    assert r.status_code == 200
    body = r.json()
    assert body["_forwarded_system"] == "You are terse."          # system untouched
    fwd = body["_forwarded_messages"]
    assert len(fwd) < len(_anthropic_session())                   # apoptosis fired
    assert fwd[-1]["content"] == "What is the release tag?"       # current query kept


def test_anthropic_fact_survives(client):
    r = client.post("/v1/messages", json={
        "model": "m", "max_tokens": 50, "messages": _anthropic_session()})
    fwd = r.json()["_forwarded_messages"]
    txt = json.dumps(fwd)
    assert "v9.2.1" in txt                                        # FACT block survived


def test_anthropic_tool_pairs_never_orphan(client):
    r = client.post("/v1/messages", json={
        "model": "m", "max_tokens": 50, "messages": _anthropic_session()})
    fwd = r.json()["_forwarded_messages"]
    for i, m in enumerate(fwd):
        # a tool_result must be immediately preceded by an assistant tool_use
        if any(b.get("type") == "tool_result" for b in m.get("content", [])
               if isinstance(b, dict)):
            prev = fwd[i - 1]
            assert i > 0 and any(b.get("type") == "tool_use"
                                 for b in prev.get("content", []) if isinstance(b, dict))


def test_anthropic_tool_units_signal_as_tool():
    # regression: an Anthropic tool_use/tool_result exchange must be classified
    # TOOL (disposable), not ASSISTANT — else verbose tool output never purges.
    from bioma.gateway import _unit_signal
    import bioma_micro as k
    tool_use = {"role": "assistant", "content": [
        {"type": "tool_use", "id": "t0", "name": "grep", "input": {}}]}
    tool_res = {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t0", "content": "big output"}]}
    assert _unit_signal([tool_use, tool_res]) == k.TOOL


def test_anthropic_verbose_tool_history_purges():
    # a long session of verbose tool exchanges should now dehydrate substantially
    msgs = [{"role": "user", "content": "start the task"}]
    for i in range(20):
        msgs += [{"role": "assistant", "content": [
                    {"type": "tool_use", "id": f"t{i}", "name": "run", "input": {}}]},
                 {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": f"t{i}",
                     "content": f"verbose output {i} " * 60}]}]
    msgs.append({"role": "user", "content": "summarize"})
    survivors, audit = dehydrate_anthropic(msgs, half_life=6.0, safe_threshold=0.35)
    assert audit["reduction"] > 0.4  # verbose tool history dehydrated


def test_redact_image_secrets_walks_both_formats():
    # fake redactor: pretends every data-URL had 1 secret, returns a marker
    def fake(url):
        return "data:image/png;base64,REDACTED", 1
    msgs = [
        {"role": "user", "content": [                    # OpenAI image part
            {"type": "text", "text": "look"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]},
        {"role": "user", "content": [                    # Anthropic image block
            {"type": "image", "source": {"type": "base64",
             "media_type": "image/png", "data": "BBBB"}}]},
        {"role": "user", "content": "no images here"},   # str content untouched
    ]
    n = redact_image_secrets(msgs, fake)
    assert n == 2
    assert msgs[0]["content"][1]["image_url"]["url"] == "data:image/png;base64,REDACTED"
    assert msgs[1]["content"][0]["source"]["data"] == "REDACTED"
    assert msgs[2]["content"] == "no images here"


def test_redact_image_secrets_noop_when_clean():
    def clean(url):
        return url, 0   # nothing found
    msgs = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,ZZ"}}]}]
    assert redact_image_secrets(msgs, clean) == 0
    assert msgs[0]["content"][0]["image_url"]["url"] == "data:image/png;base64,ZZ"


def test_anthropic_tool_result_tail_keeps_its_tool_use():
    # if the session ends on a tool_result (user), its paired tool_use must survive
    msgs = [{"role": "user", "content": "start"}]
    for i in range(12):
        msgs += [{"role": "assistant", "content": [
                    {"type": "tool_use", "id": f"t{i}", "name": "x", "input": {}}]},
                 {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": f"t{i}",
                     "content": f"r{i} " * 30}]}]
    survivors, _ = dehydrate_anthropic(msgs, half_life=6.0, safe_threshold=0.35)
    assert survivors[-1]["content"][0]["type"] == "tool_result"
    assert survivors[-2]["content"][0]["type"] == "tool_use"
    assert survivors[-2]["content"][0]["id"] == survivors[-1]["content"][0]["tool_use_id"]


def test_stable_prefix_keeps_leading_units_verbatim():
    # cache-aware zone: with stable_prefix=N, the first N history units survive
    # even when they would otherwise be purged — the cached prefix stays intact.
    msgs = _long_session()
    base, _ = dehydrate_messages(msgs, half_life=6.0, safe_threshold=0.35)
    kept, audit = dehydrate_messages(msgs, half_life=6.0, safe_threshold=0.35,
                                     stable_prefix=8)
    # the stable zone is a superset of the baseline survivors at the head
    assert kept[:8] == msgs[:8]
    assert len(kept) >= len(base)
    assert audit.get("stable_prefix_tokens", 0) > 0
    # order preserved and tail (current query) untouched
    assert kept[-1] == msgs[-1]


# ---- auto effort (BIOMA_AUTO_EFFORT) -------------------------------------- #
from bioma.gateway import apply_auto_effort  # noqa: E402

_HARD = ("Projete e implemente a arquitetura do módulo de cache do kernel. "
         "Deve garantir invariantes de consistência entre gerações, nunca "
         "perder dados durante a poda, e otimize o throughput no hot path. "
         "Analise os trade-offs de memória versus latência, compare as "
         "estratégias LRU e ARC sob carga adversarial, derive o custo esperado "
         "em tokens por chamada e prove os limites superiores. Requisito "
         "obrigatório: latência abaixo de 5ms no percentil 99; restrição dura: "
         "sem alocação dinâmica no caminho quente; sempre preservar blocos "
         "SYSTEM e FACT.")


def test_auto_effort_openai_fills_absent_only():
    body = {"messages": [{"role": "user", "content": "sim, continue"}]}
    fx = apply_auto_effort(body, surface="openai")
    assert fx["tier"] == "off" and body["reasoning"] == {"enabled": False}

    body = {"messages": [{"role": "user", "content": _HARD}]}
    fx = apply_auto_effort(body, surface="openai")
    assert fx["tier"] in ("medium", "high")
    assert body["reasoning"] == {"effort": fx["tier"]}

    # explicit client setting is untouched
    body = {"messages": [{"role": "user", "content": "sim"}],
            "reasoning": {"effort": "high"}}
    fx = apply_auto_effort(body, surface="openai")
    assert fx["action"] == "client_set" and body["reasoning"] == {"effort": "high"}


def test_auto_effort_anthropic_downgrades_trivial_never_upgrades():
    # trivial turn with a fat explicit budget → clamped to the 1024 minimum
    body = {"messages": [{"role": "user", "content": "ok, prossiga"}],
            "thinking": {"type": "enabled", "budget_tokens": 16000}}
    fx = apply_auto_effort(body, surface="anthropic")
    assert body["thinking"]["budget_tokens"] == 1024 and "downgraded" in fx["action"]

    # non-trivial turn: explicit budget respected verbatim
    body = {"messages": [{"role": "user", "content": _HARD}],
            "thinking": {"type": "enabled", "budget_tokens": 2048}}
    fx = apply_auto_effort(body, surface="anthropic")
    assert body["thinking"]["budget_tokens"] == 2048 and fx["action"] == "client_set"


def test_auto_effort_anthropic_adds_only_when_compatible():
    # hard task, no thinking, room under max_tokens, no temperature → added
    body = {"messages": [{"role": "user", "content": _HARD}], "max_tokens": 32000}
    fx = apply_auto_effort(body, surface="anthropic")
    assert body.get("thinking", {}).get("type") == "enabled"
    assert body["thinking"]["budget_tokens"] == int(fx["action"].split()[-1])

    # incompatible (temperature=0) → never added
    body = {"messages": [{"role": "user", "content": _HARD}],
            "max_tokens": 32000, "temperature": 0.0}
    fx = apply_auto_effort(body, surface="anthropic")
    assert "thinking" not in body and fx["action"] == "none"

    # trivial turn, no thinking field → stays off
    body = {"messages": [{"role": "user", "content": "valeu"}], "max_tokens": 32000}
    apply_auto_effort(body, surface="anthropic")
    assert "thinking" not in body


def test_auto_effort_disabled_by_default(client):
    # without BIOMA_AUTO_EFFORT the gateway must not touch reasoning params
    r = client.post("/v1/chat/completions",
                    json={"model": "m", "messages": _long_session()})
    assert r.status_code == 200
    fwd = r.json()["_forwarded_messages"]
    assert all("reasoning" not in m for m in fwd)
