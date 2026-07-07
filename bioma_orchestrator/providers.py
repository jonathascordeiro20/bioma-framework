"""
providers.py — LLM provider abstraction for the ONLINE orchestrator layer.

This package (`bioma_orchestrator`) is the **online commercial surface** — the
"dual-mode" counterpart to the sovereign offline `bioma_engine` core.  It is kept
OUTSIDE `bioma_engine/` on purpose, so the core keeps its ``FULLY AUTONOMOUS ✓``
guarantee: choosing the online orchestrator is an explicit, separate decision
(data leaves the host, vendor + cost apply).

  * ``LLMProvider``       — the vendor-agnostic interface.
  * ``MockProvider``      — deterministic, offline, no key/network.  Simulates
    models of differing skill so the evolution loop can be tested end-to-end.
  * ``OpenRouterProvider``— the real online gateway (one adapter → many vendors'
    models).  Requires ``OPENROUTER_API_KEY``.  Never invoked by the tests.
"""

from __future__ import annotations

import hashlib
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Completion:
    """One model response + its real FinOps footprint."""
    text: str
    model: str
    provider: str
    in_tokens: int
    out_tokens: int
    cost_usd: float
    latency_s: float
    meta: dict = field(default_factory=dict)


@dataclass
class ModelSpec:
    name: str
    price_in_per_m: float
    price_out_per_m: float
    tags: tuple = ()


def est_tokens(text: str) -> int:
    """~4 chars/token heuristic (used only when a provider omits usage)."""
    return max(1, len(text) // 4)


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def complete(self, prompt: str, model: str, *, system: Optional[str] = None,
                 max_tokens: int = 512, temperature: float = 0.2,
                 context: Optional[dict] = None) -> Completion:
        """Return a :class:`Completion`.  ``context`` carries orchestration
        metadata (e.g. task_type) that real providers ignore and the mock uses."""

    def price(self, model: str) -> ModelSpec:
        return ModelSpec(model, 0.0, 0.0, ())


class MockProvider(LLMProvider):
    """Deterministic offline provider that SIMULATES models of differing skill.

    ``skills`` maps ``{model: {task_type: skill01}}`` (hidden from the
    orchestrator); the emitted answer quality (``meta['quality']``) is a
    deterministic function of that skill + tiny reproducible noise, so the online
    fitness/bandit loop can be validated without any key or network — the same way
    the sovereign core uses an analytic ground-truth to validate.
    """
    name = "mock"

    def __init__(self, skills: dict, prices: dict):
        self.skills = skills                 # {model: {task_type: skill01}}
        self.prices = prices                 # {model: (price_in_per_m, price_out_per_m)}

    def price(self, model: str) -> ModelSpec:
        pin, pout = self.prices.get(model, (0.0, 0.0))
        return ModelSpec(model, pin, pout, ())

    def complete(self, prompt, model, *, system=None, max_tokens=512, temperature=0.2, context=None):
        task_type = (context or {}).get("task_type", "general")
        by_model = self.skills.get(model, {})
        skill = by_model.get(task_type, by_model.get("general", 0.5))
        seed = int.from_bytes(hashlib.sha256(f"{model}|{prompt}".encode("utf-8")).digest()[:4], "big")
        noise = ((seed % 1000) / 1000.0 - 0.5) * 0.08        # ±0.04, deterministic
        quality = max(0.0, min(1.0, skill + noise))
        in_tok = est_tokens((system or "") + prompt)
        out_tok = est_tokens(prompt) // 2 + 64
        pin, pout = self.prices.get(model, (0.0, 0.0))
        cost = in_tok / 1e6 * pin + out_tok / 1e6 * pout
        latency = 0.15 + (pin + pout) / 40.0                 # pricier ≈ slower (illustrative)
        text = f"[{model}] answer(q={quality:.2f}) :: {prompt[:48]}"
        return Completion(text, model, self.name, in_tok, out_tok, round(cost, 6), round(latency, 4),
                          meta={"quality": round(quality, 4), "task_type": task_type})


class OpenRouterProvider(LLMProvider):
    """Real online gateway (OpenAI-compatible) — one adapter → many vendors.

    Requires ``OPENROUTER_API_KEY``.  Uses only the stdlib (``urllib``), so no new
    dependency.  This is the byte that leaves the host in online mode — never
    exercised by the offline test-suite.
    """
    name = "openrouter"
    ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, prices: Optional[dict] = None, api_key: Optional[str] = None,
                 *, referer: str = "https://bioma.local", title: str = "B.I.O.M.A. Orchestrator"):
        self.prices = prices or {}
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.referer = referer
        self.title = title

    def price(self, model: str) -> ModelSpec:
        pin, pout = self.prices.get(model, (0.0, 0.0))
        return ModelSpec(model, pin, pout, ())

    def complete(self, prompt, model, *, system=None, max_tokens=512, temperature=0.2, context=None):
        if not self.api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set — the online gateway cannot be called. "
                "Set the key to enable online orchestration, or use MockProvider offline."
            )
        import json
        import urllib.request

        messages = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": prompt}]
        body = json.dumps({"model": model, "messages": messages,
                           "max_tokens": max_tokens, "temperature": temperature}).encode("utf-8")
        req = urllib.request.Request(self.ENDPOINT, data=body, headers={
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.referer, "X-Title": self.title,
        })
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=90) as resp:      # noqa: S310 (trusted endpoint)
            data = json.loads(resp.read())
        latency = time.perf_counter() - t0
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        in_tok = int(usage.get("prompt_tokens", est_tokens(prompt)))
        out_tok = int(usage.get("completion_tokens", est_tokens(text)))
        pin, pout = self.prices.get(model, (0.0, 0.0))
        cost = in_tok / 1e6 * pin + out_tok / 1e6 * pout
        return Completion(text, model, self.name, in_tok, out_tok, round(cost, 6), round(latency, 4),
                          meta={"finish_reason": data["choices"][0].get("finish_reason")})
