"""
`bioma/firewall_client.py` — the Cognitive Firewall: a local, provider-agnostic
defensive shim you drop in front of ANY LLM call (Anthropic, Google, OpenAI, …).

It is NOT a magic injection blocker. It is a stack of *real, measurable* controls:

  1. **Secret redaction** — vault values are scrubbed from the outbound payload AND
     the model response. An injection cannot exfiltrate a secret the model never got.
  2. **Saturation detection + apoptosis** — cognitive-DDoS / floods are detected
     (`saturation_scan`) → RED ALERT (`0x0F`) → dehydrated by apoptosis before dispatch.
  3. **Timeout guard** — dispatch is bounded, so a loop/hang cannot stall the pipeline.
  4. **Exponential backoff** — 429/5xx absorbed (built-in OpenRouter path).

Two ways to use it — 100% local, no hosted service:

    fw = CognitiveFirewall(vault={"db": DB_PW})

    # (a) PURE artifact — harden the payload, then call YOUR provider yourself:
    h = fw.shield(history, "fix the bug")
    #   → send h.prompt / h.system to anthropic / google-genai / openai directly
    #   → h.telemetry has saturation, red_alert, apoptosis reduction, μs latency

    # (b) Bring-your-own dispatcher (any async provider):
    s = await fw.harden(history, "fix the bug", dispatch_fn=my_anthropic_call)

    # (c) Convenience: built-in OpenRouter dispatch (needs OPENROUTER_API_KEY).
    s = await fw.harden(history, "fix the bug", model="openai/gpt-4o")
"""
from __future__ import annotations

import asyncio
import os
import random
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

import bioma_micro as _kernel

RED_ALERT = 0x0F  # invasion bit-flag broadcast on the hormonal bus
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_ROLE_SIGNAL = {"system": _kernel.SYSTEM, "user": _kernel.USER, "assistant": _kernel.ASSISTANT,
                "tool": _kernel.TOOL, "fact": _kernel.FACT}

# A bring-your-own dispatcher: takes the hardened (prompt, system) and returns text.
Dispatcher = Callable[[str, Optional[str]], Awaitable[str]]


@dataclass
class Hardened:
    """The pure output of `shield()`: a clean payload ready for ANY provider."""
    prompt: str                   # dehydrated + redacted user payload
    system: Optional[str]         # redacted system prompt
    saturation: float
    red_alert: bool
    secrets_redacted: int
    outbound_clean: bool          # no vault secret survived into the outbound
    apoptosis_reduction: float
    tokens_before: int
    tokens_after: int
    kernel_latency_us: float

    @property
    def telemetry(self) -> dict:
        return {"saturation": self.saturation, "red_alert": self.red_alert,
                "secrets_redacted": self.secrets_redacted, "outbound_clean": self.outbound_clean,
                "apoptosis_reduction": self.apoptosis_reduction, "tokens_before": self.tokens_before,
                "tokens_after": self.tokens_after, "kernel_latency_us": self.kernel_latency_us}


@dataclass
class Shield:
    """The outcome of one hardened *dispatch* + full defensive telemetry."""
    answer: str
    model: str
    saturation: float
    red_alert: bool
    secrets_redacted: int
    outbound_clean: bool
    apoptosis_reduction: float
    tokens_before: int
    tokens_after: int
    kernel_latency_us: float
    dispatched: bool
    timed_out: bool
    error: Optional[str] = None


class CognitiveFirewall:
    """Local, provider-agnostic defensive shim. Thread-safe: kernel calls are pure."""

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

    # ----- the PURE hardening primitive (provider-agnostic) ---------------- #
    def shield(self, history: list[dict], query: str, system: Optional[str] = None) -> Hardened:
        """Harden a payload — scan → RED ALERT → apoptosis → secret redaction — and
        return the clean prompt/system + telemetry. No network, no provider. Send the
        result to Anthropic / Google / OpenAI (or anything) yourself."""
        payload = "\n".join(str(m.get("content", "")) for m in history) + "\n" + query
        saturation = _kernel.saturation_scan(payload)
        red = saturation >= self.saturation_threshold
        if red:
            self._bus.secrete(RED_ALERT, min(1.0, saturation))

        msgs = [(str(m.get("content", "")), _ROLE_SIGNAL.get(m.get("role", "user"), _kernel.USER))
                for m in history]
        audit = _kernel.dehydrate(msgs, half_life=self.half_life, safe_threshold=self.safe_threshold)
        dehydrated = "\n".join(audit["kept"])

        clean_ctx, h1 = self._redact(dehydrated)
        clean_query, h2 = self._redact(query)
        clean_system, h3 = self._redact(system) if system else ("", 0)
        prompt = f"Context:\n{clean_ctx}\n\nRequest:\n{clean_query}" if clean_ctx else clean_query
        outbound_clean = not (self._leaks(prompt) or self._leaks(clean_system))
        return Hardened(prompt=prompt, system=(clean_system or None), saturation=round(saturation, 4),
                        red_alert=red, secrets_redacted=h1 + h2 + h3, outbound_clean=outbound_clean,
                        apoptosis_reduction=float(audit["reduction"]), tokens_before=int(audit["tokens_before"]),
                        tokens_after=int(audit["tokens_after"]), kernel_latency_us=float(audit["kernel_latency_us"]))

    # ----- hardened dispatch (built-in OpenRouter OR your own provider) ---- #
    async def harden(self, history: list[dict], query: str, *, model: str = "openai/gpt-4o",
                     system: Optional[str] = None, max_tokens: int = 256,
                     timeout: Optional[float] = None,
                     dispatch_fn: Optional[Dispatcher] = None) -> Shield:
        hp = self.shield(history, query, system)
        base = dict(saturation=hp.saturation, red_alert=hp.red_alert, secrets_redacted=hp.secrets_redacted,
                    outbound_clean=hp.outbound_clean, apoptosis_reduction=hp.apoptosis_reduction,
                    tokens_before=hp.tokens_before, tokens_after=hp.tokens_after,
                    kernel_latency_us=hp.kernel_latency_us)
        bound = timeout if timeout is not None else self.dispatch_timeout

        # No dispatcher available → hardening ran, dispatch skipped.
        if dispatch_fn is None and not self.online:
            return Shield(answer="", model=model, dispatched=False, timed_out=False,
                          error="offline (no key, no dispatch_fn) — defenses ran; dispatch skipped", **base)

        try:
            if dispatch_fn is not None:  # bring-your-own provider (Anthropic/Google/OpenAI)
                text = await asyncio.wait_for(dispatch_fn(hp.prompt, hp.system), timeout=bound)
                err = None
                model = "custom"
            else:                        # built-in OpenRouter convenience
                messages = ([{"role": "system", "content": hp.system}] if hp.system else []) + \
                           [{"role": "user", "content": hp.prompt}]
                text, err = await asyncio.wait_for(self._dispatch(model, messages, max_tokens), timeout=bound)
        except asyncio.TimeoutError:
            return Shield(answer="", model=model, dispatched=False, timed_out=True,
                          error=f"dispatch exceeded {bound}s — contained by timeout guard", **base)

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
