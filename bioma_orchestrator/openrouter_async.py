"""
openrouter_async.py — the UNIFIED async model provider for B.I.O.M.A.

Every market model (proprietary + open) is reached through ONE endpoint —
OpenRouter — via the OpenAI-compatible SDK.  Switching "brains" is just switching
the `model` string in the payload.  Fully async / non-blocking, so the Rust
kernel's microsecond hormonal bus is never stalled by network I/O.

  * `AsyncOpenRouterProvider` — real calls (needs `OPENROUTER_API_KEY`).  Captures
    per-request RTT, real token usage + cost, and retries 429/5xx with
    exponential backoff + jitter.
  * `MockAsyncProvider` — deterministic, offline, no key/network — lets the whole
    pipeline (bus, apoptosis, mitosis, consolidation) be exercised end-to-end
    without spending a cent; swap in the real provider with a key.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Illustrative per-model prices (USD / 1M tokens).  When OpenRouter returns the
# real cost in `usage.cost` (usage.include=True) we use THAT instead.
PRICES = {
    "anthropic/claude-3.5-sonnet":       (3.00, 15.00),
    "openai/gpt-4o":                     (2.50, 10.00),
    "x-ai/grok-2":                       (2.00, 10.00),
    "meta-llama/llama-3-70b-instruct":   (0.59, 0.79),
}


@dataclass
class Completion:
    text: str
    model: str
    in_tokens: int
    out_tokens: int
    cost_usd: float
    rtt_ms: float               # network round-trip time (isolates AI time from local bus time)
    error: Optional[str] = None
    meta: dict = field(default_factory=dict)


def _price(model: str) -> tuple[float, float]:
    return PRICES.get(model, (1.0, 3.0))


class AsyncProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, model: str, *, system: Optional[str] = None,
                       max_tokens: int = 1024, temperature: float = 0.3) -> Completion: ...

    async def close(self) -> None:  # pragma: no cover
        pass


# --------------------------------------------------------------------------- #
#  Real provider — OpenAI-compatible SDK pointed at OpenRouter
# --------------------------------------------------------------------------- #
class AsyncOpenRouterProvider(AsyncProvider):
    def __init__(self, api_key: Optional[str] = None, *,
                 referer: str = "https://bioma.ai", title: str = "B.I.O.M.A. Framework",
                 max_retries: int = 5, base_delay: float = 1.0, max_delay: float = 30.0):
        from openai import AsyncOpenAI
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY not set — cannot reach the online gateway.")
        # The required OpenRouter attribution headers travel on every request.
        self._client = AsyncOpenAI(
            base_url=OPENROUTER_BASE_URL, api_key=key,
            default_headers={"HTTP-Referer": referer, "X-Title": title},
        )
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    @staticmethod
    def _usage_cost(usage) -> Optional[float]:
        """OpenRouter returns the real $ in `usage.cost` when usage.include=True."""
        if usage is None:
            return None
        c = getattr(usage, "cost", None)
        if isinstance(c, (int, float)):
            return float(c)
        try:
            c = usage.model_dump().get("cost")
            return float(c) if isinstance(c, (int, float)) else None
        except Exception:
            return None

    async def complete(self, prompt, model, *, system=None, max_tokens=1024, temperature=0.3):
        from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
        messages = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": prompt}]
        delay = self.base_delay
        last_err = "unknown"
        for attempt in range(self.max_retries + 1):
            t0 = time.perf_counter()
            try:
                resp = await self._client.chat.completions.create(
                    model=model, messages=messages,
                    max_tokens=max_tokens, temperature=temperature,
                    extra_body={"usage": {"include": True}},   # ask OpenRouter for real cost
                )
                rtt_ms = (time.perf_counter() - t0) * 1000.0
                usage = resp.usage
                in_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
                out_tok = int(getattr(usage, "completion_tokens", 0) or 0)
                pin, pout = _price(model)
                cost = self._usage_cost(usage)
                if cost is None:
                    cost = in_tok / 1e6 * pin + out_tok / 1e6 * pout
                text = resp.choices[0].message.content or ""
                return Completion(text, model, in_tok, out_tok, round(cost, 6), round(rtt_ms, 2))

            except RateLimitError as exc:              # 429 → back off + retry
                last_err = f"429 {exc}"
            except APIStatusError as exc:              # retry 5xx, surface 4xx
                if 500 <= getattr(exc, "status_code", 0) < 600:
                    last_err = f"{exc.status_code} {exc}"
                else:
                    return Completion("", model, 0, 0, 0.0, (time.perf_counter() - t0) * 1000.0,
                                      error=f"{getattr(exc,'status_code','?')}: {exc}")
            except (APIConnectionError, APITimeoutError) as exc:
                last_err = f"conn {exc}"

            if attempt < self.max_retries:
                sleep = min(self.max_delay, delay) + random.uniform(0, 0.3 * delay)  # exponential + jitter
                await asyncio.sleep(sleep)
                delay *= 2
        return Completion("", model, 0, 0, 0.0, 0.0, error=f"exhausted retries: {last_err}")

    async def close(self) -> None:
        await self._client.close()


# --------------------------------------------------------------------------- #
#  Mock provider — deterministic, offline (no key, no network, no cost)
# --------------------------------------------------------------------------- #
_MOCK_PROFILE = {
    "anthropic/claude-3.5-sonnet":     {"rtt": 0.48, "quality": 0.92},  # logic/refactor
    "openai/gpt-4o":                   {"rtt": 0.43, "quality": 0.88},  # agent consistency
    "x-ai/grok-2":                     {"rtt": 0.24, "quality": 0.82},  # low-latency predator
    "meta-llama/llama-3-70b-instruct": {"rtt": 0.62, "quality": 0.74},  # open-source giant
}


class MockAsyncProvider(AsyncProvider):
    """Simulates each model's latency/quality/cost profile so the full pipeline
    runs offline.  Latency is time-compressed (`speed`) for a fast demo but the
    REPORTED `rtt_ms` is the modelled network RTT."""

    def __init__(self, speed: float = 0.12):
        self.speed = speed

    async def complete(self, prompt, model, *, system=None, max_tokens=1024, temperature=0.3):
        prof = _MOCK_PROFILE.get(model, {"rtt": 0.5, "quality": 0.7})
        seed = abs(hash((model, prompt))) % 1000
        rtt_s = prof["rtt"] * (0.85 + (seed % 30) / 100.0)      # deterministic jitter
        await asyncio.sleep(rtt_s * self.speed)                 # non-blocking, time-compressed
        in_tok = max(1, len(((system or "") + prompt)) // 4)
        out_tok = 180 + (seed % 220)
        pin, pout = _price(model)
        cost = in_tok / 1e6 * pin + out_tok / 1e6 * pout
        text = (f"[{model}] Proposed remediation covering: parameterized queries, input "
                f"validation, least privilege, idempotency, atomic CAS, fencing token, "
                f"bounds check, safe allocation, fuzzing, sanitizer (q={prof['quality']:.2f}).")
        return Completion(text, model, in_tok, out_tok, round(cost, 6), round(rtt_s * 1000, 2),
                          meta={"quality": prof["quality"]})
