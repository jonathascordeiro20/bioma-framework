"""
`bioma/openrouter_client.py` — the resilient async OpenRouter abstraction.

Every request is intercepted and passed through the Rust **context apoptosis
filter** (`bioma_micro.dehydrate`) before dispatch: stale, low-value history is
dehydrated away, so only the lean, high-oxygen context reaches the model — cutting
input tokens (and therefore cost) on every call. Network failures and 429 rate
limits are absorbed with exponential backoff + jitter.

    client = LeanOpenRouterClient()                 # needs OPENROUTER_API_KEY
    d = await client.dispatch(history, "fix the bug", model="openai/gpt-4o")
    print(d.reduction, d.kernel_latency_us, d.text)
"""
from __future__ import annotations

import asyncio
import os
import random
import time
from dataclasses import dataclass
from typing import Optional

import bioma_micro as _kernel

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Map chat roles → metabolic signal classes understood by the kernel.
_ROLE_SIGNAL = {
    "system": _kernel.SYSTEM,
    "user": _kernel.USER,
    "assistant": _kernel.ASSISTANT,
    "tool": _kernel.TOOL,
    "fact": _kernel.FACT,
}

# Illustrative per-model prices (USD / 1M tokens) — used only if OpenRouter does
# not return the real usage.cost.
_PRICES = {
    "anthropic/claude-fable-5": (5.0, 15.0),
    "openai/gpt-4o": (2.5, 10.0),
}


@dataclass
class Dispatch:
    """The result of one dispatch: the model output + a full apoptosis audit."""
    text: str
    model: str
    in_tokens: int
    out_tokens: int
    cost_usd: float
    rtt_ms: float
    # apoptosis audit (all measured)
    tokens_before: int
    tokens_after: int
    reduction: float            # fraction of input tokens dehydrated away (0..1)
    kernel_latency_us: float    # pure Rust apoptosis latency
    blocks_purged: int
    error: Optional[str] = None


class LeanOpenRouterClient:
    """Async, resilient OpenRouter client with kernel-side context apoptosis."""

    def __init__(self, api_key: Optional[str] = None, *,
                 referer: str = "https://bioma.ai", title: str = "B.I.O.M.A. Micro-Kernel",
                 max_retries: int = 5, base_delay: float = 1.0, max_delay: float = 30.0,
                 half_life: float = 6.0, safe_threshold: float = 0.35):
        from openai import AsyncOpenAI
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY not set — cannot reach the online gateway.")
        self._client = AsyncOpenAI(
            base_url=OPENROUTER_BASE_URL, api_key=key,
            default_headers={"HTTP-Referer": referer, "X-Title": title},
        )
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.half_life = half_life
        self.safe_threshold = safe_threshold

    # ----- kernel-side apoptosis (pure Rust) ------------------------------- #
    def apoptosis(self, history: list[dict]) -> dict:
        """Run the Rust dehydration filter over a chat history; returns the audit
        dict (kept blocks + token savings + kernel latency in μs)."""
        msgs = [(str(m.get("content", "")), _ROLE_SIGNAL.get(m.get("role", "user"), _kernel.USER))
                for m in history]
        return _kernel.dehydrate(msgs, half_life=self.half_life, safe_threshold=self.safe_threshold)

    @staticmethod
    def _usage_cost(usage, model: str, in_tok: int, out_tok: int) -> float:
        c = getattr(usage, "cost", None)
        if isinstance(c, (int, float)):
            return float(c)
        pin, pout = _PRICES.get(model, (1.0, 3.0))
        return in_tok / 1e6 * pin + out_tok / 1e6 * pout

    # ----- resilient dispatch --------------------------------------------- #
    async def dispatch(self, history: list[dict], query: str, *,
                       model: str = "openai/gpt-4o", system: Optional[str] = None,
                       max_tokens: int = 1024, temperature: float = 0.3) -> Dispatch:
        """Dehydrate `history` through the kernel, then dispatch the lean prompt to
        `model` with exponential-backoff resilience against 429/5xx/network errors."""
        from openai import (APIConnectionError, APIStatusError, APITimeoutError, RateLimitError)

        audit = self.apoptosis(history)
        dehydrated = "\n".join(audit["kept"])
        prompt = f"Context:\n{dehydrated}\n\nCurrent request:\n{query}" if dehydrated else query
        messages = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": prompt}]

        delay = self.base_delay
        last_err = "unknown"
        for attempt in range(self.max_retries + 1):
            t0 = time.perf_counter()
            try:
                resp = await self._client.chat.completions.create(
                    model=model, messages=messages, max_tokens=max_tokens,
                    temperature=temperature, extra_body={"usage": {"include": True}},
                )
                rtt_ms = (time.perf_counter() - t0) * 1000.0
                usage = resp.usage
                in_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
                out_tok = int(getattr(usage, "completion_tokens", 0) or 0)
                cost = self._usage_cost(usage, model, in_tok, out_tok)
                text = resp.choices[0].message.content or ""
                return Dispatch(
                    text, model, in_tok, out_tok, round(cost, 6), round(rtt_ms, 2),
                    tokens_before=int(audit["tokens_before"]), tokens_after=int(audit["tokens_after"]),
                    reduction=float(audit["reduction"]), kernel_latency_us=float(audit["kernel_latency_us"]),
                    blocks_purged=int(audit["blocks_purged"]),
                )
            except RateLimitError as exc:                     # 429 → back off + retry
                last_err = f"429 {exc}"
            except APIStatusError as exc:                     # retry 5xx, surface 4xx
                code = getattr(exc, "status_code", 0)
                if 500 <= code < 600:
                    last_err = f"{code} {exc}"
                else:
                    return self._error(audit, f"{code}: {exc}", model)
            except (APIConnectionError, APITimeoutError) as exc:
                last_err = f"conn {exc}"

            if attempt < self.max_retries:
                sleep = min(self.max_delay, delay) + random.uniform(0, 0.3 * delay)
                await asyncio.sleep(sleep)
                delay *= 2
        return self._error(audit, f"exhausted retries: {last_err}", model)

    @staticmethod
    def _error(audit: dict, msg: str, model: str) -> Dispatch:
        return Dispatch("", model, 0, 0, 0.0, 0.0,
                        tokens_before=int(audit["tokens_before"]), tokens_after=int(audit["tokens_after"]),
                        reduction=float(audit["reduction"]), kernel_latency_us=float(audit["kernel_latency_us"]),
                        blocks_purged=int(audit["blocks_purged"]), error=msg)

    async def close(self) -> None:
        await self._client.close()
