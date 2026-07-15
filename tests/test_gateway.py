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

from bioma.gateway import create_app, dehydrate_messages  # noqa: E402


# ---- a mock upstream that echoes back the forwarded messages -------------- #
def _mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        sent = json.loads(request.content.decode())
        return httpx.Response(200, json={
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
