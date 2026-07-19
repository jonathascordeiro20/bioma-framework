#!/usr/bin/env python3
"""Paired A/B benchmark: full session history vs. BIOMA-shielded history.

For every (task, model, rep) the SAME task runs twice:

  arm A (baseline) : the full simulated session history is sent verbatim.
  arm B (bioma)    : the history is passed through
                     `CognitiveFirewall.shield(history, final_prompt, system)`
                     and the hardened `h.prompt` / `h.system` are sent instead.

Both arms hit the same model with the same final request, so every pair is
directly comparable (tokens, latency, task success).

Usage:
  python run_benchmark.py --tier budget --reps 3
  python run_benchmark.py --models deepseek-chat --tasks 1 --reps 1
  python run_benchmark.py --models claude-haiku --tasks 1 --reps 1 --mock

Results are appended to results/results.jsonl (one JSON object per arm-run).
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time

import yaml

from bioma.firewall_client import CognitiveFirewall

ROOT = pathlib.Path(__file__).resolve().parent
RESULTS = ROOT / "results" / "results.jsonl"
MAX_TOKENS = 1024


# --------------------------------------------------------------------------- #
# token approximation (tiktoken when available, 4 chars/token fallback)
# --------------------------------------------------------------------------- #
def approx_tokens(text: str) -> int:
    try:
        import tiktoken

        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return max(1, len(text) // 4)


# --------------------------------------------------------------------------- #
# model roster
# --------------------------------------------------------------------------- #
def load_roster() -> dict:
    with open(ROOT / "models.yaml") as f:
        cfg = yaml.safe_load(f)
    roster = {}
    for tier, models in cfg["tiers"].items():
        for name, m in models.items():
            roster[name] = {**m, "tier": tier, "name": name}
    return roster


def usable(model: dict) -> bool:
    return bool(os.environ.get(model["key_env"]))


# --------------------------------------------------------------------------- #
# providers
# --------------------------------------------------------------------------- #
def call_anthropic(model: dict, system: str | None, messages: list[dict]) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ[model["key_env"]])
    kwargs = dict(model=model["id"], max_tokens=MAX_TOKENS, messages=messages)
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    text = "".join(b.text for b in resp.content if b.type == "text")
    return {
        "text": text,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
    }


def call_openai_compatible(model: dict, system: str | None, messages: list[dict]) -> dict:
    from openai import OpenAI

    client = OpenAI(base_url=model.get("base_url"), api_key=os.environ[model["key_env"]])
    msgs = ([{"role": "system", "content": system}] if system else []) + messages
    resp = client.chat.completions.create(
        model=model["id"], messages=msgs, max_tokens=MAX_TOKENS, temperature=0.2
    )
    text = resp.choices[0].message.content or ""
    usage = resp.usage
    return {
        "text": text,
        "input_tokens": usage.prompt_tokens if usage else approx_tokens(str(msgs)),
        "output_tokens": usage.completion_tokens if usage else approx_tokens(text),
    }


def call_mock(model: dict, system: str | None, messages: list[dict]) -> dict:
    """Offline stand-in: exercises payload construction + evaluation plumbing.

    Returns a canned non-answer, so mock runs validate INTEGRATION only —
    success rates from mock runs are meaningless by design.
    """
    payload = (system or "") + "\n".join(m["content"] for m in messages)
    return {
        "text": "```python\n# mock response — no model was called\n```\nmock answer",
        "input_tokens": approx_tokens(payload),
        "output_tokens": 16,
    }


PROVIDERS = {"anthropic": call_anthropic, "openai_compatible": call_openai_compatible}


# --------------------------------------------------------------------------- #
# success gate
# --------------------------------------------------------------------------- #
PY_BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)


def _keyword_gate(task: dict, text: str, gate_name: str = "keywords") -> dict:
    hits = {k: (k in text) for k in task["success_keywords"]}
    return {"success": all(hits.values()), "gate": gate_name, "keyword_hits": hits}


def evaluate_success(task: dict, text: str) -> dict:
    """Executable gate when the task has test_code, keyword gate otherwise.

    The solution is the FIRST ```python block of the model response; it is
    written to solution.py next to the task's pytest file and executed in a
    subprocess with a 30s timeout. Responses without a python block fall back
    to the keyword gate (marked keywords_fallback).
    """
    test_code = task.get("test_code")
    if not test_code:
        return _keyword_gate(task, text)

    match = PY_BLOCK.search(text)
    if not match:
        return _keyword_gate(task, text, "keywords_fallback")

    with tempfile.TemporaryDirectory(prefix="ab-gate-") as tmp:
        pathlib.Path(tmp, "solution.py").write_text(match.group(1))
        pathlib.Path(tmp, "test_solution.py").write_text(test_code)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-x", "-q", "--no-header", "-p", "no:cacheprovider"],
                cwd=tmp, capture_output=True, text=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            return {"success": False, "gate": "pytest", "pytest_timeout": True}
    tail = (proc.stdout + proc.stderr)[-400:]
    return {"success": proc.returncode == 0, "gate": "pytest",
            "pytest_returncode": proc.returncode, "pytest_tail": tail}


# --------------------------------------------------------------------------- #
# arms
# --------------------------------------------------------------------------- #
def run_arm(arm: str, task: dict, model: dict, fw: CognitiveFirewall, mock: bool) -> dict:
    system = task.get("system")
    telemetry = None
    if arm == "baseline":
        messages = list(task["session_turns"]) + [
            {"role": "user", "content": task["final_prompt"]}
        ]
    else:  # bioma
        h = fw.shield(task["session_turns"], task["final_prompt"], system=system)
        messages = [{"role": "user", "content": h.prompt}]
        system = h.system
        telemetry = h.telemetry

    call = call_mock if mock else PROVIDERS[model["provider"]]
    t0 = time.perf_counter()
    out = call(model, system, messages)
    latency = time.perf_counter() - t0

    row = {
        "task": task["id"],
        "lang": task.get("lang"),
        "stale_ratio": task.get("stale_ratio"),
        "model": model["name"],
        "model_id": model["id"],
        "tier": model["tier"],
        "arm": arm,
        "mock": mock,
        "input_tokens": out["input_tokens"],
        "output_tokens": out["output_tokens"],
        "latency_s": round(latency, 3),
        "response_preview": out["text"][:200],
    }
    row.update(evaluate_success(task, out["text"]))
    if telemetry:
        row["bioma_telemetry"] = telemetry
    return row


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tier", choices=["frontier", "budget"], help="run every model in a tier")
    ap.add_argument("--models", help="comma-separated model names from models.yaml")
    ap.add_argument("--tasks", type=int, default=0, help="run only the first N tasks (0 = all)")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--mock", action="store_true", help="no network: canned responses")
    ap.add_argument("--out", default=str(RESULTS))
    args = ap.parse_args()

    roster = load_roster()
    if args.models:
        names = [n.strip() for n in args.models.split(",")]
        unknown = [n for n in names if n not in roster]
        if unknown:
            print(f"unknown models {unknown}; available: {sorted(roster)}", file=sys.stderr)
            return 2
        selected = [roster[n] for n in names]
    elif args.tier:
        selected = [m for m in roster.values() if m["tier"] == args.tier]
    else:
        selected = list(roster.values())

    if not args.mock:
        skipped = [m["name"] for m in selected if not usable(m)]
        selected = [m for m in selected if usable(m)]
        if skipped:
            print(f"skipping models without API key: {skipped}", file=sys.stderr)
    if not selected:
        print("no usable models selected (set API keys or use --mock)", file=sys.stderr)
        return 2

    with open(ROOT / "tasks.json") as f:
        tasks = json.load(f)
    if args.tasks:
        tasks = tasks[: args.tasks]

    fw = CognitiveFirewall()
    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_runs = 0
    with open(out_path, "a") as out:
        for model in selected:
            for task in tasks:
                for rep in range(args.reps):
                    for arm in ("baseline", "bioma"):
                        try:
                            row = run_arm(arm, task, model, fw, args.mock)
                        except Exception as exc:  # keep the run going, record the failure
                            row = {
                                "task": task["id"],
                                "model": model["name"],
                                "tier": model["tier"],
                                "arm": arm,
                                "rep": rep,
                                "error": f"{type(exc).__name__}: {exc}",
                            }
                            print(f"  ERROR {model['name']}/{task['id']}/{arm}: {exc}",
                                  file=sys.stderr)
                        else:
                            row["rep"] = rep
                            tok = row["input_tokens"]
                            print(f"  {model['name']:>13} {task['id']:>22} rep{rep} "
                                  f"{arm:>8}: in={tok} ok={row.get('success')}")
                        out.write(json.dumps(row) + "\n")
                        n_runs += 1

    print(f"\n{n_runs} arm-runs appended to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
