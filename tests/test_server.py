"""Unit tests for the lean production server (`bioma.server`) via FastAPI's
TestClient. Forced offline (no key) so `/v1/dispatch` runs the apoptosis-only
path — deterministic, no network."""
import os

# Force the server offline before its lifespan reads the environment.
os.environ.pop("OPENROUTER_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from bioma.server import app  # noqa: E402


def test_health_reports_lean_topology():
    with TestClient(app) as client:
        body = client.get("/health").json()
    assert body["status"] == "alive"
    assert "lean" in body["topology"]
    assert body["online"] is False


def test_dispatch_apoptosis_only_without_key():
    payload = {"query": "summarize risk",
               "history": [{"role": "system", "content": "soc copilot"},
                           {"role": "tool", "content": "verbose audit noise " * 40}]}
    with TestClient(app) as client:
        resp = client.post("/v1/dispatch", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["dispatched"] is False
    assert body["apoptosis"]["reduction"] >= 0.0
    assert body["apoptosis"]["kernel_latency_us"] >= 0.0


def test_dispatch_rejects_empty_query():
    with TestClient(app) as client:
        resp = client.post("/v1/dispatch", json={"query": "", "history": []})
    assert resp.status_code == 422  # pydantic min_length
