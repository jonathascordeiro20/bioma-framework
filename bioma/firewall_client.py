"""
`bioma/firewall_client.py` — the Cognitive Firewall: a low-latency defensive
shim in front of every outbound LLM call.

It is NOT a magic injection blocker. It is a stack of *real, measurable* controls,
each targeting one failure mode:

  1. **Secret redaction** — any value in the vault is scrubbed from the outbound
     payload AND the model response. An injection cannot exfiltrate a secret the
     model never received. (This, not "blocking injection", is the honest defense.)
  2. **Saturation detection + apoptosis** — cognitive-DDoS / forged-log floods are
     detected (Rust `saturation_scan`) → RED ALERT (hormonal `0x0F`) → the flood is
     dehydrated by apoptosis before it reaches the model (context-exhaustion defense).
  3. **Timeout guard** — every dispatch is bounded by `asyncio.wait_for`, so a
     loop/hang attempt cannot stall the pipeline.
  4. **Exponential backoff** — 429/5xx are absorbed with jittered backoff.

What it does NOT do: detect novel exploits, understand injection *semantics* that
don't touch a declared secret, or replace real network/host controls. See
`reports/BIOMA_IMMUNITY_VERDICT.md` for the honest scope.
"""
from __future__ import annotations

import asyncio
import os
import random
from dataclasses import dataclass
from typing import Optional

import bioma_micro as _kernel

RED_ALERT = 0x0F  # invasion bit-flag broadcast on the hormonal bus
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_ROLE_SIGNAL = {"system": _kernel.SYSTEM, "user": _kernel.USER, "assistant": _kernel.ASSISTANT,
                "tool": _kernel.TOOL, "fact": _kernel.FACT}


@dataclass
class Shield:
    """The outcome of one hardened dispatch + full defensive telemetry."""
    answer: str
    model: str
    # threat telemetry (all measured)
    saturation: float
    red_alert: bool
    secrets_redacted: int
    outbound_clean: bool          # no vault secret survived into the outbound/answer
    apoptosis_reduction: float
    tokens_before: int
    tokens_after: int
    kernel_latency_us: float
    dispatched: bool
    timed_out: bool
    error: Optional[str] = None


class CognitiveFirewall:
    """Low-latency defensive shim. Thread-safe: the Rust kernel calls are pure and
    the async client is per-instance."""

    def __init__(self, api_key: Optional[str] = None, *, vault: Optional[dict] = None,
                 saturation_threshold: float = 0.85, dispatch_timeout: float = 20.0,
                 max_retries: int = 5, base_delay: float = 1.0, max_delay: float = 30.0,
                 half_life: float = 6.0, safe_threshold: float = 0.35,
                 referer: str = "https://bioma.ai", title: str = "B.I.O.M.A. Cognitive Firewall"):
        self._vault = dict(vault or {})
        self._secrets = [str(v) for v in self._vault.values() if v]
        self.saturation_threshold = saturation_threshold
        self.dispatch_timeout = dispatch_timeout
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.half_life = half_life
        self.safe_threshold = safe_threshold
        self._bus = _kernel.HormonalBus(32)
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.online = bool(key and key.startswith("sk-or"))
        if self.online:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(base_url=OPENROUTER_BASE_URL, api_key=key,
                                       default_headers={"HTTP-Referer": referer, "X-Title": title})
        else:
            self._client = None

    # ----- primitives ------------------------------------------------------ #
    def _redact(self, text: str) -> tuple[str, int]:
        hits = 0
        for sv in self._secrets:
            if sv and sv in text:
                hits += text.count(sv)
                text = text.replace(sv, "[REDACTED]")
        return text, hits

    def _leaks(self, text: str) -> bool:
        return any(sv in text for sv in self._secrets if sv)

    def scan(self, text: str) -> float:
        """Cognitive-DDoS saturation score (0..1)."""
        return _kernel.saturation_scan(text)

    def alert_level(self) -> float:
        return self._bus.sense(RED_ALERT)

    # ----- the hardened pipeline ------------------------------------------- #
    async def harden(self, history: list[dict], query: str, *, model: str = "openai/gpt-4o",
                     system: Optional[str] = None, max_tokens: int = 256,
                     timeout: Optional[float] = None) -> Shield:
        # 1) saturation scan over the full incoming payload
        payload = "\n".join(str(m.get("content", "")) for m in history) + "\n" + query
        saturation = _kernel.saturation_scan(payload)
        red = saturation >= self.saturation_threshold
        if red:
            self._bus.secrete(RED_ALERT, min(1.0, saturation))  # broadcast 0x0F

        # 2) apoptosis — dehydrate the (possibly flooded) history
        msgs = [(str(m.get("content", "")), _ROLE_SIGNAL.get(m.get("role", "user"), _kernel.USER))
                for m in history]
        audit = _kernel.dehydrate(msgs, half_life=self.half_life, safe_threshold=self.safe_threshold)
        dehydrated = "\n".join(audit["kept"])

        # 3) redact vault secrets from the OUTBOUND payload
        clean_ctx, h1 = self._redact(dehydrated)
        clean_query, h2 = self._redact(query)
        clean_system, h3 = self._redact(system) if system else ("", 0)
        redacted = h1 + h2 + h3
        prompt = f"Context:\n{clean_ctx}\n\nRequest:\n{clean_query}" if clean_ctx else clean_query
        outbound_clean = not (self._leaks(prompt) or self._leaks(clean_system))

        base = dict(saturation=round(saturation, 4), red_alert=red, secrets_redacted=redacted,
                    outbound_clean=outbound_clean, apoptosis_reduction=float(audit["reduction"]),
                    tokens_before=int(audit["tokens_before"]), tokens_after=int(audit["tokens_after"]),
                    kernel_latency_us=float(audit["kernel_latency_us"]))

        if not self.online:
            return Shield(answer="", model=model, dispatched=False, timed_out=False,
                          error="offline (no key) — defenses ran; dispatch skipped", **base)

        # 4) dispatch under a timeout guard (bounds any loop/hang attempt)
        messages = ([{"role": "system", "content": clean_system}] if clean_system else []) + \
                   [{"role": "user", "content": prompt}]
        try:
            text, err = await asyncio.wait_for(
                self._dispatch(model, messages, max_tokens),
                timeout=timeout if timeout is not None else self.dispatch_timeout)
        except asyncio.TimeoutError:
            bound = timeout if timeout is not None else self.dispatch_timeout
            return Shield(answer="", model=model, dispatched=False, timed_out=True,
                          error=f"dispatch exceeded {bound}s — contained by timeout guard", **base)

        # 5) redact secrets from the RESPONSE (defense in depth)
        safe_answer, resp_hits = self._redact(text or "")
        base["secrets_redacted"] += resp_hits
        base["outbound_clean"] = base["outbound_clean"] and not self._leaks(safe_answer)
        return Shield(answer=safe_answer, model=model, dispatched=(err is None),
                      timed_out=False, error=err, **base)

    async def _dispatch(self, model: str, messages: list, max_tokens: int) -> tuple[str, Optional[str]]:
        from openai import (APIConnectionError, APIStatusError, APITimeoutError, RateLimitError)
        delay, last = self.base_delay, "unknown"
        for attempt in range(self.max_retries + 1):
            try:
                resp = await self._client.chat.completions.create(
                    model=model, messages=messages, max_tokens=max_tokens,
                    temperature=0.2, extra_body={"usage": {"include": True}})
                return resp.choices[0].message.content or "", None
            except RateLimitError as exc:
                last = f"429 {exc}"
            except APIStatusError as exc:
                code = getattr(exc, "status_code", 0)
                if 500 <= code < 600:
                    last = f"{code} {exc}"
                else:
                    return "", f"{code}: {exc}"
            except (APIConnectionError, APITimeoutError) as exc:
                last = f"conn {exc}"
            if attempt < self.max_retries:
                await asyncio.sleep(min(self.max_delay, delay) + random.uniform(0, 0.3 * delay))
                delay *= 2
        return "", f"exhausted retries: {last}"

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
