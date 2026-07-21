#!/usr/bin/env python3
"""
tests/measure_kernel_latency.py — how much TIME does BIOMA add before the LLM?

Three layers, from surgical to real:

  1. PROCESSING PATH — wall-clock of the full production path
     (`dehydrate_anthropic`: grouping + kernel + repair) over synthetic
     Claude-Code-style sessions from ~1k to ~1M tokens, plus the pure-kernel
     microseconds from the audit. Median of N reps per size.

  2. GATEWAY HTTP OVERHEAD — same payloads POSTed to a local echo upstream
     directly vs through the gateway (echo replaces the LLM so provider
     variance cannot drown the signal). Overhead = median(gateway) − median(direct).

  3. REAL API SPOT CHECK (optional, needs OPENROUTER_API_KEY + credit) —
     direct OpenRouter vs gateway→OpenRouter, same prompt, max_tokens=32,
     cheap model, medians compared. Skipped gracefully on 402/no key.

    python tests/measure_kernel_latency.py            # layers 1 + 2
    python tests/measure_kernel_latency.py --real     # + layer 3
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, ".env"))
except Exception:
    pass
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

from fastapi import FastAPI, Request  # noqa: E402 — módulo-nível: com
# `from __future__ import annotations` o FastAPI só resolve o tipo Request
# se o nome existir nos globals do módulo.

from bioma.gateway import create_app, dehydrate_anthropic  # noqa: E402

ECHO_PORT, GW_PORT = 8791, 8790


# --------------------------------------------------------------------------- #
#  Session builder — Claude-Code-shaped traffic, ~500 tokens per round
# --------------------------------------------------------------------------- #
def _tool_round(i: int) -> list[dict]:
    body = (f"def handler_{i}(row):\n    return row.get('k{i}')\n" * 25)
    return [
        {"role": "assistant", "content": [
            {"type": "text", "text": f"reading services/mod_{i}.py"},
            {"type": "tool_use", "id": f"tu_{i}", "name": "Read",
             "input": {"file_path": f"services/mod_{i}.py"}}]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": f"tu_{i}", "content": body}]},
        {"role": "assistant", "content": f"noted {i}"},
    ]


def build(rounds: int) -> list[dict]:
    msgs = [{"role": "user", "content": "Project brief: keep the suite green."},
            {"role": "assistant", "content": "Understood."}]
    for i in range(rounds):
        msgs += _tool_round(i)
    msgs.append({"role": "user", "content": "Summarize the last change."})
    return msgs


SIZES = [  # (label, rounds) — ~500 tok/round
    ("~1k tok", 2),
    ("~5k tok", 10),
    ("~25k tok", 50),
    ("~100k tok", 200),
    ("~400k tok", 800),
    ("~1M tok", 2000),
]


def _reps_for(rounds: int) -> int:
    return 9 if rounds <= 50 else (5 if rounds <= 800 else 3)


# --------------------------------------------------------------------------- #
#  Layer 1 — processing path wall-clock
# --------------------------------------------------------------------------- #
def layer1(configs: list[tuple[str, dict]]) -> list[dict]:
    rows = []
    for label, rounds in SIZES:
        msgs = build(rounds)
        for cfg_name, kw in configs:
            times, kernel_us, audit = [], [], {}
            for _ in range(_reps_for(rounds)):
                t0 = time.perf_counter()
                _, audit = dehydrate_anthropic(msgs, half_life=6.0, **kw)
                times.append((time.perf_counter() - t0) * 1000)
                kernel_us.append(float(audit.get("kernel_latency_us", 0)))
            tb = int(audit.get("tokens_before", 0))
            med = statistics.median(times)
            rows.append({
                "size": label, "config": cfg_name, "tokens": tb,
                "path_ms": med, "path_p95_ms": max(times),
                "kernel_us": statistics.median(kernel_us),
                "tok_per_ms": tb / med if med else 0,
                "reduction": audit.get("reduction", 0.0),
            })
    return rows


# --------------------------------------------------------------------------- #
#  Layer 2 — gateway HTTP overhead vs local echo upstream
# --------------------------------------------------------------------------- #
def _start_uvicorn(app, port: int):
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                           log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    import httpx
    for _ in range(60):
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=1)
            return server
        except Exception:
            time.sleep(0.25)
    raise RuntimeError(f"server on :{port} did not come up")


def _echo_app():
    echo = FastAPI()

    @echo.get("/health")
    async def health():
        return {"ok": True}

    @echo.post("/v1/messages")
    async def messages(request: Request):
        await request.json()  # parse like a real upstream would
        return {"id": "msg_echo", "type": "message", "role": "assistant",
                "model": "echo", "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1}}
    return echo


def layer2() -> list[dict]:
    import httpx
    os.environ["BIOMA_SAFE_THRESHOLD"] = "0.2"
    os.environ["BIOMA_PURGE_QUANTUM"] = "8"
    os.environ["BIOMA_STABLE_PREFIX"] = "auto"
    os.environ["BIOMA_AUDIT_LOG"] = os.path.join(_ROOT, "bioma_gateway_audit.jsonl")
    _start_uvicorn(_echo_app(), ECHO_PORT)
    gw = create_app(upstream=f"http://127.0.0.1:{ECHO_PORT}/v1")
    _start_uvicorn(gw, GW_PORT)

    rows = []
    with httpx.Client(timeout=120) as client:
        for label, rounds in SIZES:
            body = {"model": "echo", "max_tokens": 32, "messages": build(rounds)}
            reps = _reps_for(rounds)
            direct, viagw = [], []
            for target, bucket in ((f"http://127.0.0.1:{ECHO_PORT}/v1/messages", direct),
                                   (f"http://127.0.0.1:{GW_PORT}/v1/messages", viagw)):
                client.post(target, json=body)  # warm-up (JIT, TCP, caches)
                for _ in range(reps):
                    t0 = time.perf_counter()
                    r = client.post(target, json=body)
                    r.raise_for_status()
                    bucket.append((time.perf_counter() - t0) * 1000)
            rows.append({"size": label,
                         "direct_ms": statistics.median(direct),
                         "gateway_ms": statistics.median(viagw),
                         "overhead_ms": statistics.median(viagw) - statistics.median(direct)})
    return rows


# --------------------------------------------------------------------------- #
#  Layer 3 — real API spot check (optional)
# --------------------------------------------------------------------------- #
def layer3(model: str) -> list[dict]:
    import httpx
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key.startswith("sk-or"):
        print("  (sem OPENROUTER_API_KEY — camada 3 pulada)")
        return []
    gw = create_app(upstream="https://openrouter.ai/api/v1")
    _start_uvicorn(gw, GW_PORT + 2)
    rows = []
    hdr = {"Authorization": f"Bearer {key}"}
    with httpx.Client(timeout=180) as client:
        for label, rounds in [("~1k tok", 2), ("~10k tok", 20), ("~40k tok", 80)]:
            body = {"model": model, "max_tokens": 32,
                    "messages": build(rounds)}
            direct, viagw = [], []
            try:
                for target, bucket in (
                        ("https://openrouter.ai/api/v1/messages", direct),
                        (f"http://127.0.0.1:{GW_PORT + 2}/v1/messages", viagw)):
                    for _ in range(2):
                        t0 = time.perf_counter()
                        r = client.post(target, headers=hdr, json=body)
                        if r.status_code == 402:
                            raise RuntimeError("402 — sem créditos")
                        r.raise_for_status()
                        bucket.append((time.perf_counter() - t0) * 1000)
            except Exception as exc:  # noqa: BLE001 — spot check é best-effort
                print(f"  {label}: pulado ({exc})")
                continue
            rows.append({"size": label,
                         "direct_ms": statistics.median(direct),
                         "gateway_ms": statistics.median(viagw)})
    return rows


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true", help="inclui a camada 3 (API real)")
    ap.add_argument("--model", default="z-ai/glm-5.2")
    args = ap.parse_args()

    print("=" * 96)
    print("  B.I.O.M.A. — latência de processamento do kernel/gateway por tamanho de contexto")
    print("=" * 96)

    configs = [
        ("default", dict(safe_threshold=0.35)),
        ("agent (0.2+q8+auto)", dict(safe_threshold=0.2, quantum=8, stable_prefix=-1)),
    ]
    print("\n## Camada 1 — caminho de produção completo (grouping + kernel + repair)\n")
    l1 = layer1(configs)
    print("| contexto | config | tokens | caminho (mediana) | pior rep | kernel puro | throughput |")
    print("| :--- | :--- | ---: | ---: | ---: | ---: | ---: |")
    for r in l1:
        print(f"| {r['size']} | {r['config']} | {r['tokens']:,} | {r['path_ms']:.2f} ms "
              f"| {r['path_p95_ms']:.2f} ms | {r['kernel_us']:.1f} µs "
              f"| {r['tok_per_ms']:,.0f} tok/ms |")

    print("\n## Camada 2 — overhead HTTP total do gateway (upstream de eco local)\n")
    l2 = layer2()
    print("| contexto | direto (eco) | via gateway | overhead BIOMA |")
    print("| :--- | ---: | ---: | ---: |")
    for r in l2:
        print(f"| {r['size']} | {r['direct_ms']:.1f} ms | {r['gateway_ms']:.1f} ms "
              f"| +{r['overhead_ms']:.1f} ms |")

    l3 = []
    if args.real:
        print(f"\n## Camada 3 — API real ({args.model}, 2 reps, max_tokens=32)\n")
        l3 = layer3(args.model)
        if l3:
            print("| contexto | direto OpenRouter | via gateway |")
            print("| :--- | ---: | ---: |")
            for r in l3:
                print(f"| {r['size']} | {r['direct_ms']:.0f} ms | {r['gateway_ms']:.0f} ms |")

    out = os.path.join(_ROOT, "results", "kernel_latency.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"layer1": l1, "layer2": l2, "layer3": l3}, f, indent=2)
    print(f"\n📄 dados: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
