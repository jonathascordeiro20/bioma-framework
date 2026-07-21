"""
`bioma/gateway.py` — the drop-in gateway: point your OpenAI-compatible client's
`base_url` here and every request gets context apoptosis, transparently.

    uvicorn bioma.gateway:app --port 8790
    client = OpenAI(base_url="http://localhost:8790/v1", api_key=...)  # nothing else changes

Surfaces: `POST /v1/chat/completions` (OpenAI format) and `POST /v1/messages`
(Anthropic Messages format — point Claude Code's `ANTHROPIC_BASE_URL` here),
both streaming and non-streaming, + `GET /health`. Upstream OpenRouter accepts
both formats natively, so either surface works with an OpenRouter key.

Design guarantees (each one is unit-tested):

1. **The current query is sacred** — the last `user` message never enters the
   filter; the first `system` message maps to the kernel's SYSTEM class
   (never purged). Content starting with ``FACT:`` maps to FACT (never purged).
2. **Cache-aware by construction** — dehydration is deletion-only and order-
   preserving: the surviving prefix (system + early FACTs) stays byte-identical
   across calls, so provider prompt-caching can still hit on it.
3. **Tool-pair integrity** — an assistant message carrying `tool_calls` and its
   following `tool` result messages form ONE unit that survives or is purged
   together; the gateway never emits an orphaned tool call/result.
4. **Auditable** — every request appends a JSONL line (tokens before/after,
   reduction, kernel μs) to `BIOMA_AUDIT_LOG` (default: bioma_gateway_audit.jsonl);
   non-streaming responses also carry a top-level ``bioma`` audit object
   (extra fields are ignored by SDKs).

Upstream: `BIOMA_UPSTREAM` (default https://openrouter.ai/api/v1). Auth: the
client's Authorization / x-api-key is forwarded; if absent, `OPENROUTER_API_KEY`.
Bridge mode (`BIOMA_FORCE_KEY` set) ignores the client's key and always uses
`OPENROUTER_API_KEY` — needed to point an Anthropic client such as Claude Code
(`ANTHROPIC_BASE_URL=http://localhost:8790`) at an OpenRouter upstream.
Pixel secret redaction (`BIOMA_REDACT_IMAGE_SECRETS` set): OCR every image part
and mask secrets visible in the pixels before dispatch — opt-in, since OCR is
off the hot path only when enabled (see `reports/BIOMA_PIXEL_SECRETS.md`).
Tuning: `BIOMA_HALF_LIFE` (6.0), `BIOMA_SAFE_THRESHOLD` (0.35) and
`BIOMA_STABLE_PREFIX` (0 — leading history units kept verbatim, cache-aware zone;
the Anthropic surface enforces a minimum of 1 so `messages[0]` is never purged —
strict upstreams 400 on a pruned conversation anchor).
`BIOMA_CACHE_HYSTERESIS` (0.0 = off): only apply a purge when the potential
reduction reaches this fraction — below it the history is forwarded untouched so
the provider prompt-cache prefix stays byte-identical. Purges then happen in
batches: one cache invalidation buys a large reduction, instead of many small
purges each breaking the cache for single-digit savings.
`BIOMA_PURGE_QUANTUM` (0 = off): quantized purge boundary — with K, only units
below `B = (n_units // K) * K` are eligible for purging; the rest is frozen
verbatim. B advances once every K new units, so the pruned output stays
byte-identical for K consecutive turns and the provider cache hits on the
PRUNED context; the invalidation is paid once per batch. Recommended for
agent traffic (e.g. Claude Code): K=8 with hysteresis 0.30.
`BIOMA_STABLE_PREFIX=auto`: derives the stable zone per request from the
client's FIRST `cache_control` breakpoint — everything before it (system,
tools, project brief) is the prefix the provider already cached and stays
byte-identical; no manual tuning.
`BIOMA_AUTO_FACT` (off): conservative heuristic that promotes short USER turns
that read like durable constraints ("must/never/sempre/lembre/we agreed…") to
the FACT class, closing the untagged-requirement gap without user discipline.
Never promotes tool output or texts >600 chars (no context inflation).
`BIOMA_REHYDRATE_STORE=<dir>` (off): every purged unit is persisted locally,
content-addressed by SHA-256 (`purged_hashes` in the audit line), and can be
brought back via `GET /v1/rehydrate/{hash}` — apoptosis becomes hibernation,
nothing is lost. Local-only, same trust domain as the gateway.
Auto effort (`BIOMA_AUTO_EFFORT` set): per-request dynamic thinking budgets via
the kernel's `effort_gauge` — fills absent reasoning params by task complexity,
downgrades an explicit Anthropic budget only on confidently-trivial turns, and
never raises effort beyond what the client asked for.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

# Load .env so the standalone server (uvicorn) finds OPENROUTER_API_KEY without
# it having to be exported into the shell — matches how the tests load it.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import bioma_micro as kernel

IMAGE_NOMINAL_TOKENS = 1600   # multimodal content parts priced like the vision adapter


# --------------------------------------------------------------------------- #
#  Dehydration over OpenAI-format messages
# --------------------------------------------------------------------------- #
def _unit_text(msgs: list[dict]) -> str:
    """Text used for the kernel's token sizing of a unit (marker added later)."""
    parts: list[str] = []
    for m in msgs:
        c = m.get("content")
        if isinstance(c, str):
            parts.append(c)
        elif isinstance(c, list):  # multimodal content parts
            for p in c:
                if p.get("type") == "text":
                    parts.append(p.get("text", ""))
                else:                       # image/audio part → nominal cost
                    parts.append(" " * (IMAGE_NOMINAL_TOKENS * 4))
        for tc in m.get("tool_calls") or []:
            parts.append(json.dumps(tc.get("function", {}), ensure_ascii=False))
    return "\n".join(parts)


def _first_text(content: Any) -> str:
    """The leading text of a message, whether content is a str or a list of parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                return p.get("text", "")
    return ""


def _has_cache_control(content: Any) -> bool:
    return isinstance(content, list) and any(
        isinstance(p, dict) and p.get("cache_control") for p in content)


def _has_block_type(msg: dict, block_type: str) -> bool:
    return any(isinstance(b, dict) and b.get("type") == block_type
               for b in _blocks(msg.get("content")))


def _is_tool_unit(msgs: list[dict]) -> bool:
    """A purge unit is 'tool' (verbose, disposable) if any of its messages is a
    tool exchange — OpenAI (`tool` role / `tool_calls`) OR Anthropic
    (`tool_use` / `tool_result` content blocks)."""
    for m in msgs:
        if m.get("role") == "tool" or m.get("tool_calls"):
            return True
        if _has_block_type(m, "tool_use") or _has_block_type(m, "tool_result"):
            return True
    return False


# Auto-FACT — CONSERVATIVE heuristic for durable constraints. Only promotes
# short USER turns that read like a requirement/decision/reminder; never
# promotes tool output (the purge target) or long texts (context inflation).
_DURABLE_RE = re.compile(
    r"(?:\b(?:must|never|always|shall|required|remember|reminder|important)\b"
    r"|\bdon'?t forget\b|\bnote this\b|\b(?:we|as) agreed\b|\bdecision:"
    r"|\b(?:deve[mr]?|nunca|sempre|obrigat[óo]ri[oa]|lembre(?:te)?|anote"
    r"|importante|decidimos|combinamos|ficou definido)\b"
    r"|\bn[ãa]o (?:pode|esque[çc]a)\b)",
    re.IGNORECASE)
_AUTO_FACT_MAX_CHARS = 600


def looks_durable(text: str) -> bool:
    """True when the text reads like a durable constraint worthy of FACT."""
    t = (text or "").strip()
    return bool(t) and len(t) <= _AUTO_FACT_MAX_CHARS and bool(_DURABLE_RE.search(t))


def _unit_signal(msgs: list[dict], auto_fact: bool = False) -> int:
    first = msgs[0]
    role = first.get("role", "user")
    content = first.get("content")
    # durable if explicitly FACT-tagged OR marked for provider caching (a
    # cache_control breakpoint means the caller declared this block stable)
    if _first_text(content).lstrip().startswith("FACT:") or _has_cache_control(content):
        return kernel.FACT
    if role == "system":
        return kernel.SYSTEM
    # tool exchanges are disposable in BOTH protocol shapes
    if _is_tool_unit(msgs):
        return kernel.TOOL
    if role == "assistant":
        return kernel.ASSISTANT
    if auto_fact and looks_durable(_first_text(content)):
        return kernel.FACT
    return kernel.USER


def _auto_stable_prefix(units: list[list[dict]]) -> int:
    """`BIOMA_STABLE_PREFIX=auto`: the stable zone ends at the client's FIRST
    `cache_control` breakpoint — everything before it is the prefix the
    provider already cached (system/tools/brief) and must stay byte-identical."""
    for i, unit in enumerate(units):
        if any(_has_cache_control(m.get("content")) for m in unit):
            return i + 1
    return 0


def _group_units(messages: list[dict]) -> list[list[dict]]:
    """Group messages into purge units, keeping tool pairs together."""
    units: list[list[dict]] = []
    i = 0
    while i < len(messages):
        m = messages[i]
        if m.get("role") == "assistant" and m.get("tool_calls"):
            unit = [m]
            i += 1
            while i < len(messages) and messages[i].get("role") == "tool":
                unit.append(messages[i])
                i += 1
            units.append(unit)
        else:
            units.append([m])
            i += 1
    return units


_EMPTY_AUDIT = {"tokens_before": 0, "tokens_after": 0, "reduction": 0.0,
                "kernel_latency_us": 0.0, "blocks_purged": 0}


def apply_cache_hysteresis(messages: list[dict], survivors: list[dict],
                           audit: dict, hysteresis: float) -> tuple[list[dict], dict]:
    """Cache-aware purge batching. Dehydration is its own dry-run (~1µs): when
    the potential reduction is below `hysteresis`, HOLD — forward the original
    messages untouched so the provider prompt-cache prefix stays byte-identical.
    Junk keeps accumulating until one batched purge buys a big reduction, paying
    the cache invalidation once instead of on every small purge. Stateless by
    construction: the decision derives only from the current request."""
    if hysteresis <= 0 or float(audit.get("reduction", 0.0)) >= hysteresis:
        return survivors, audit
    held = dict(audit, held=True,
                potential_reduction=round(float(audit.get("reduction", 0.0)), 4),
                tokens_after=audit["tokens_before"], reduction=0.0,
                blocks_purged=0)
    return messages, held


def _apoptose_units(units: list[list[dict]], tail: list[dict], *,
                    half_life: float, safe_threshold: float,
                    stable_prefix: int = 0,
                    auto_fact: bool = False) -> tuple[list[dict], dict]:
    """Run the kernel over pre-grouped history units and reassemble survivors + tail.
    `stable_prefix` = number of leading UNITS kept verbatim (cache-aware zone);
    passed through when the installed kernel supports it (≥1.1.0). The purged
    units ride along in `audit["_purged_units"]` (transient, never serialized)
    so the caller can feed the rehydration store."""
    msgs = [(f"[U{idx}]" + _unit_text(unit), _unit_signal(unit, auto_fact))
            for idx, unit in enumerate(units)]
    try:
        audit = kernel.dehydrate(msgs, half_life=half_life,
                                 safe_threshold=safe_threshold,
                                 stable_prefix=stable_prefix)
    except TypeError:  # kernel < 1.1.0 — no cache-aware zone
        audit = kernel.dehydrate(msgs, half_life=half_life,
                                 safe_threshold=safe_threshold)
    kept_idx = {int(k[2:k.index("]")]) for k in audit["kept"]}
    survivors = [m for idx, unit in enumerate(units) if idx in kept_idx for m in unit]
    purged = [unit for idx, unit in enumerate(units) if idx not in kept_idx]
    return survivors + tail, dict(audit, kept=None, _purged_units=purged)


def _split_quantum(units: list[list[dict]],
                   quantum: int) -> tuple[list[list[dict]], list[list[dict]]]:
    """Quantized purge boundary. With `quantum=K`, only units below the boundary
    `B = (n // K) * K` enter the kernel; units in [B, n) are frozen verbatim.
    B is a pure function of the unit count, so it only advances once every K new
    units — and the kernel sees the SAME mobile list for K consecutive turns,
    making the pruned output byte-identical between advances. Result: provider
    prompt-cache hits on the PRUNED context, and one batched invalidation per
    quantum instead of one per turn."""
    if quantum <= 0:
        return units, []
    boundary = (len(units) // quantum) * quantum
    return units[:boundary], units[boundary:]


def _merge_frozen_audit(audit: dict, frozen: list[list[dict]]) -> dict:
    """Fold the frozen (verbatim) zone back into the audit so the reported
    reduction is over the WHOLE history, not just the mobile zone."""
    if not frozen:
        return audit
    frozen_tok = sum(len(_unit_text(u)) // 4 for u in frozen)
    before = int(audit["tokens_before"]) + frozen_tok
    after = int(audit["tokens_after"]) + frozen_tok
    return dict(audit, tokens_before=before, tokens_after=after,
                reduction=(1 - after / before) if before else 0.0,
                quantum_frozen_units=len(frozen))


def dehydrate_messages(messages: list[dict], *, half_life: float,
                       safe_threshold: float, stable_prefix: int = 0,
                       quantum: int = 0,
                       auto_fact: bool = False) -> tuple[list[dict], dict]:
    """Deletion-only, order-preserving apoptosis over an OpenAI message list.
    Returns (surviving messages, audit dict). The LAST user message (and
    everything after it) is the current query — it never enters the filter.
    `stable_prefix=-1` = auto: derived from the client's first cache_control
    breakpoint (see `_auto_stable_prefix`)."""
    last_user = max((i for i, m in enumerate(messages) if m.get("role") == "user"),
                    default=-1)
    if last_user < 0:
        return messages, dict(_EMPTY_AUDIT)
    history, tail = messages[:last_user], messages[last_user:]
    units = _group_units(history)
    if stable_prefix < 0:
        stable_prefix = _auto_stable_prefix(units)
    mobile, frozen = _split_quantum(units, quantum)
    survivors, audit = _apoptose_units(
        mobile, [m for u in frozen for m in u] + tail,
        half_life=half_life, safe_threshold=safe_threshold,
        stable_prefix=min(stable_prefix, len(mobile)), auto_fact=auto_fact)
    return survivors, _merge_frozen_audit(audit, frozen)


# --------------------------------------------------------------------------- #
#  Anthropic Messages format
# --------------------------------------------------------------------------- #
def _blocks(content: Any) -> list[dict]:
    return content if isinstance(content, list) else []


def _has_block(msg: dict, block_type: str) -> bool:
    return any(isinstance(b, dict) and b.get("type") == block_type
               for b in _blocks(msg.get("content")))


def _group_units_anthropic(history: list[dict]) -> list[list[dict]]:
    """Group Anthropic messages into purge units, keeping tool pairs together:
    an assistant message with `tool_use` blocks pairs with the FOLLOWING user
    message carrying the matching `tool_result` blocks."""
    units: list[list[dict]] = []
    i = 0
    while i < len(history):
        m = history[i]
        if (m.get("role") == "assistant" and _has_block(m, "tool_use")
                and i + 1 < len(history) and _has_block(history[i + 1], "tool_result")):
            units.append([m, history[i + 1]])
            i += 2
        else:
            units.append([m])
            i += 1
    return units


def redact_image_secrets(messages: list[dict], redactor) -> int:
    """Walk image content parts (OpenAI `image_url` data-URLs and Anthropic
    `image`/base64 blocks) and mask any secret visible in the pixels, in place.
    `redactor(data_url) -> (clean_data_url, n_secrets)`. Returns total masked.
    Opt-in (OCR is off the hot path only when `BIOMA_REDACT_IMAGE_SECRETS` is set)."""
    total = 0
    for m in messages:
        content = m.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "image_url":                    # OpenAI
                url = (part.get("image_url") or {}).get("url", "")
                if url.startswith("data:image"):
                    clean, n = redactor(url)
                    if n:
                        part["image_url"]["url"] = clean
                        total += n
            elif part.get("type") == "image":                      # Anthropic
                src = part.get("source") or {}
                if src.get("type") == "base64" and src.get("data"):
                    data_url = f"data:{src.get('media_type','image/png')};base64,{src['data']}"
                    clean, n = redactor(data_url)
                    if n:
                        src["data"] = clean.split(",", 1)[1]
                        total += n
    return total


def _tool_use_ids(msg: dict) -> set:
    return {b.get("id") for b in _blocks(msg.get("content"))
            if isinstance(b, dict) and b.get("type") == "tool_use"}


def _tool_result_ids(msg: dict) -> set:
    return {b.get("tool_use_id") for b in _blocks(msg.get("content"))
            if isinstance(b, dict) and b.get("type") == "tool_result"}


def repair_anthropic(survivors: list[dict]) -> list[dict]:
    """Deletion-only repair pass: whatever apoptosis leaves behind must still be
    a protocol-valid Anthropic Messages list. Strict upstreams (api.anthropic.com)
    400 on violations that permissive routers tolerate. Invariants enforced:

      1. the conversation starts with a real `user` turn (no pruned anchor);
      2. no orphan `tool_result` (its `tool_use` must be the previous message);
      3. no dangling `tool_use` (its `tool_result` must be the next message).

    Unit grouping already keeps pairs together, so this is a backstop — it only
    ever DELETES messages, preserving the deletion-only apoptosis contract."""
    out: list[dict] = []
    for m in survivors:
        if not out and m.get("role") != "user":
            continue                      # (1) leading non-user turns fall
        if _has_block(m, "tool_result"):
            prev = out[-1] if out else None
            paired = (prev is not None and prev.get("role") == "assistant"
                      and _tool_result_ids(m) <= _tool_use_ids(prev))
            if not paired:
                continue                  # (2) orphan tool_result falls
        out.append(m)
    # (3) walk backwards: an assistant tool_use not answered by the NEXT message
    # (e.g. its paired result was dropped above) falls too
    repaired: list[dict] = []
    for i, m in enumerate(out):
        if m.get("role") == "assistant" and _tool_use_ids(m):
            nxt = out[i + 1] if i + 1 < len(out) else None
            if nxt is None or not (_tool_use_ids(m) & _tool_result_ids(nxt)):
                continue
        repaired.append(m)
    return repaired


def dehydrate_anthropic(messages: list[dict], *, half_life: float,
                        safe_threshold: float, stable_prefix: int = 0,
                        quantum: int = 0,
                        auto_fact: bool = False) -> tuple[list[dict], dict]:
    """Apoptosis over Anthropic Messages. `system` is a separate top-level field
    (always forwarded untouched, never purged) so it is not in `messages`. The
    last user turn is the current query and is never filtered; if it carries a
    `tool_result`, its matching assistant `tool_use` is kept with it (no orphan).

    The first unit is ALWAYS in the stable zone (`stable_prefix` floors at 1):
    strict Messages endpoints reject a conversation whose opening user turn was
    pruned, and keeping the anchor also protects the provider cache prefix."""
    last_user = max((i for i, m in enumerate(messages) if m.get("role") == "user"),
                    default=-1)
    if last_user < 0:
        return messages, dict(_EMPTY_AUDIT)
    split = last_user
    # if the sacred tail begins with a tool_result, keep its paired tool_use too
    if (_has_block(messages[last_user], "tool_result") and last_user > 0
            and messages[last_user - 1].get("role") == "assistant"
            and _has_block(messages[last_user - 1], "tool_use")):
        split = last_user - 1
    history, tail = messages[:split], messages[split:]
    units = _group_units_anthropic(history)
    if stable_prefix < 0:
        stable_prefix = _auto_stable_prefix(units)
    mobile, frozen = _split_quantum(units, quantum)
    survivors, audit = _apoptose_units(
        mobile, [m for u in frozen for m in u] + tail,
        half_life=half_life, safe_threshold=safe_threshold,
        stable_prefix=min(max(1, stable_prefix), len(mobile)) if mobile else 0,
        auto_fact=auto_fact)
    return repair_anthropic(survivors), _merge_frozen_audit(audit, frozen)


# --------------------------------------------------------------------------- #
#  Auto effort — dynamic thinking budgets from the kernel's effort_gauge
# --------------------------------------------------------------------------- #
_EFFORT_TIERS = {"low": "low", "medium": "medium", "high": "high"}
_MIN_THINKING_BUDGET = 1024  # Anthropic minimum for thinking.budget_tokens


def _last_user_text(messages: list[dict]) -> str:
    for m in reversed(messages or []):
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                return " ".join(b.get("text", "") for b in c
                                if isinstance(b, dict) and b.get("type") == "text")
    return ""


def apply_auto_effort(body: dict, *, surface: str) -> Optional[dict]:
    """Set the request's reasoning budget from the kernel's `effort_gauge`
    (kernel ≥ 1.1.0). Conservative contract:

    - NEVER raises effort beyond what the client explicitly asked for;
    - OpenAI surface: only fills in when `reasoning`/`reasoning_effort` are
      absent (tier off → reasoning disabled; otherwise effort by tier);
    - Anthropic surface: an explicit thinking budget is only DOWNGRADED (to the
      1024 minimum) when the gauge is confident the turn is trivial (tier off);
      thinking is only ADDED for medium/high when the request is compatible
      (temperature absent or 1, and room left under max_tokens).

    Returns an audit fragment {tier, score, action} or None when inactive."""
    gauge = getattr(kernel, "effort_gauge", None)
    if gauge is None:
        return None
    text = _last_user_text(body.get("messages") or [])
    if not text:
        return None
    g = gauge(text)
    tier, score, budget = g["tier"], round(float(g["score"]), 3), int(g["budget_tokens"])
    action = "none"

    if surface == "openai":
        if "reasoning" in body or "reasoning_effort" in body:
            action = "client_set"
        elif tier == "off":
            body["reasoning"] = {"enabled": False}
            action = "disabled"
        else:
            body["reasoning"] = {"effort": _EFFORT_TIERS[tier]}
            action = f"effort={tier}"
    else:  # anthropic
        thinking = body.get("thinking")
        if isinstance(thinking, dict) and thinking.get("type") == "enabled":
            cur = int(thinking.get("budget_tokens") or 0)
            if tier == "off" and cur > _MIN_THINKING_BUDGET:
                thinking["budget_tokens"] = _MIN_THINKING_BUDGET
                action = f"downgraded {cur}->{_MIN_THINKING_BUDGET}"
            else:
                action = "client_set"
        elif thinking is None and tier in ("medium", "high"):
            temp = body.get("temperature")
            max_tokens = body.get("max_tokens")
            if (temp in (None, 1, 1.0) and isinstance(max_tokens, int)
                    and max_tokens > budget + 256):
                body["thinking"] = {"type": "enabled", "budget_tokens": budget}
                action = f"added {budget}"
        # tier off/low with no thinking field: already not thinking — no-op
    return {"tier": tier, "score": score, "action": action}


# --------------------------------------------------------------------------- #
#  The gateway app
# --------------------------------------------------------------------------- #
def create_app(*, upstream: Optional[str] = None,
               transport: Optional[httpx.AsyncBaseTransport] = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await app.state.client.aclose()

    app = FastAPI(title="B.I.O.M.A. Gateway", version="0.1.0", lifespan=lifespan)
    app.state.upstream = (upstream or os.environ.get(
        "BIOMA_UPSTREAM", "https://openrouter.ai/api/v1")).rstrip("/")
    app.state.half_life = float(os.environ.get("BIOMA_HALF_LIFE", "6.0"))
    app.state.threshold = float(os.environ.get("BIOMA_SAFE_THRESHOLD", "0.35"))
    # cache-aware zone: leading history UNITS kept verbatim so a provider
    # prompt-cache prefix stays byte-identical (kernel ≥ 1.1.0)
    _sp = os.environ.get("BIOMA_STABLE_PREFIX", "0").strip().lower()
    app.state.stable_prefix = -1 if _sp == "auto" else int(_sp)
    app.state.cache_hysteresis = float(os.environ.get("BIOMA_CACHE_HYSTERESIS", "0.0"))
    app.state.purge_quantum = int(os.environ.get("BIOMA_PURGE_QUANTUM", "0"))
    app.state.auto_fact = bool(os.environ.get("BIOMA_AUTO_FACT", ""))
    app.state.rehydrate_dir = os.environ.get("BIOMA_REHYDRATE_STORE", "")
    # opt-in dynamic thinking budgets via the kernel's effort_gauge (≥ 1.1.0)
    app.state.auto_effort = os.environ.get("BIOMA_AUTO_EFFORT", "") != ""
    app.state.audit_path = os.environ.get("BIOMA_AUDIT_LOG", "bioma_gateway_audit.jsonl")
    app.state.client = httpx.AsyncClient(transport=transport, timeout=600.0)
    # opt-in pixel secret redaction (OCR is slow → off by default). A lazily-built
    # VisionDistiller masks secrets visible in image content parts before dispatch.
    app.state.redact_images = os.environ.get("BIOMA_REDACT_IMAGE_SECRETS", "") != ""
    app.state.redactor = None

    def _image_redactor():
        if app.state.redactor is None:
            from bioma.vision import VisionDistiller
            d = VisionDistiller()
            app.state.redactor = lambda url: (lambda c, s: (c, len(s.findings)))(
                *d.redact_secrets(url))
        return app.state.redactor

    def _auth_headers(request: Request) -> dict[str, str]:
        """Forward the caller's auth (Bearer OR Anthropic x-api-key); fall back
        to OPENROUTER_API_KEY. In BRIDGE MODE (`BIOMA_FORCE_KEY` set) the client's
        own key is ignored and OPENROUTER_API_KEY is always used — needed when
        bridging an Anthropic client (e.g. Claude Code) to the OpenRouter upstream,
        since the client sends its own Anthropic-style key."""
        force = os.environ.get("BIOMA_FORCE_KEY", "")
        if force:
            key = os.environ.get("OPENROUTER_API_KEY", "") or force
            return {"Authorization": f"Bearer {key}"}
        out: dict[str, str] = {}
        if request.headers.get("authorization"):
            out["Authorization"] = request.headers["authorization"]
        if request.headers.get("x-api-key"):
            out["x-api-key"] = request.headers["x-api-key"]
        if request.headers.get("anthropic-version"):
            out["anthropic-version"] = request.headers["anthropic-version"]
        # subscription OAuth (Claude Code login) requires the matching beta
        # header; OpenRouter-style upstreams simply ignore it.
        if request.headers.get("anthropic-beta"):
            out["anthropic-beta"] = request.headers["anthropic-beta"]
        if not out:
            key = os.environ.get("OPENROUTER_API_KEY", "")
            if key:
                out["Authorization"] = f"Bearer {key}"
        return out

    async def _forward(request: Request, path: str, body: dict, stream: bool,
                       inject: Optional[dict] = None):
        url = f"{app.state.upstream}{path}"
        headers = {"Content-Type": "application/json", **_auth_headers(request)}
        for h in ("http-referer", "x-title"):
            if request.headers.get(h):
                headers[h] = request.headers[h]
        if stream:
            req = app.state.client.build_request("POST", url, headers=headers, json=body)
            upstream_resp = await app.state.client.send(req, stream=True)

            async def pump():
                try:
                    async for chunk in upstream_resp.aiter_bytes():
                        yield chunk
                finally:
                    await upstream_resp.aclose()

            return StreamingResponse(
                pump(), status_code=upstream_resp.status_code,
                media_type=upstream_resp.headers.get("content-type", "text/event-stream"))

        r = await app.state.client.post(url, headers=headers, json=body)
        try:
            payload = r.json()
        except ValueError:
            return JSONResponse({"error": "upstream returned non-JSON"}, status_code=502)
        if inject is not None and isinstance(payload, dict):
            payload["bioma"] = inject
        return JSONResponse(payload, status_code=r.status_code)

    def _store_purged(audit: dict) -> None:
        """Rehydration store (opt-in): persist each purged unit content-addressed
        by SHA-256 under `BIOMA_REHYDRATE_STORE`; the hashes go to the audit line
        so `GET /v1/rehydrate/{hash}` can bring any pruned block back. Local-only,
        same trust domain as the gateway (nothing leaves the machine)."""
        purged = audit.pop("_purged_units", None) or []
        # on a hysteresis HOLD nothing left the wire — nothing to rehydrate later
        if audit.get("held") or not app.state.rehydrate_dir or not purged:
            return
        os.makedirs(app.state.rehydrate_dir, exist_ok=True)
        hashes = []
        for unit in purged:
            blob = json.dumps(unit, ensure_ascii=False,
                              sort_keys=True).encode("utf-8")
            digest = hashlib.sha256(blob).hexdigest()
            path = os.path.join(app.state.rehydrate_dir, f"{digest}.json")
            if not os.path.exists(path):
                try:
                    with open(path, "wb") as f:
                        f.write(blob)
                except OSError:
                    continue
            hashes.append(digest)
        if hashes:
            audit["purged_hashes"] = hashes

    def _audit_line(model: str, audit: dict, stream: bool) -> None:
        line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": model,
                "stream": stream, "tokens_before": int(audit["tokens_before"]),
                "tokens_after": int(audit["tokens_after"]),
                "reduction": round(float(audit["reduction"]), 4),
                "kernel_latency_us": round(float(audit["kernel_latency_us"]), 2),
                "blocks_purged": int(audit["blocks_purged"])}
        if audit.get("effort"):
            line["effort"] = audit["effort"]
        if audit.get("held"):
            line["held"] = True
            line["potential_reduction"] = audit.get("potential_reduction", 0.0)
        if audit.get("purged_hashes"):
            line["purged_hashes"] = audit["purged_hashes"]
        try:
            with open(app.state.audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(line) + "\n")
        except OSError:
            pass

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "kernel": getattr(kernel, "__version__", "?"),
                "upstream": app.state.upstream,
                "half_life": app.state.half_life, "threshold": app.state.threshold,
                "stable_prefix": ("auto" if app.state.stable_prefix < 0
                                  else app.state.stable_prefix),
                "cache_hysteresis": app.state.cache_hysteresis,
                "purge_quantum": app.state.purge_quantum,
                "auto_fact": app.state.auto_fact,
                "rehydrate_store": bool(app.state.rehydrate_dir)}

    def _audit_fields(audit: dict) -> dict:
        return {k: audit[k] for k in ("tokens_before", "tokens_after",
                "reduction", "kernel_latency_us", "blocks_purged")}

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        body = await request.json()
        survivors, audit = dehydrate_messages(
            body.get("messages") or [], half_life=app.state.half_life,
            safe_threshold=app.state.threshold,
            stable_prefix=app.state.stable_prefix,
            quantum=app.state.purge_quantum,
            auto_fact=app.state.auto_fact)
        survivors, audit = apply_cache_hysteresis(
            body.get("messages") or [], survivors, audit,
            app.state.cache_hysteresis)
        _store_purged(audit)
        if app.state.redact_images:
            redact_image_secrets(survivors, _image_redactor())
        body["messages"] = survivors
        if app.state.auto_effort:
            audit["effort"] = apply_auto_effort(body, surface="openai")
        stream = bool(body.get("stream", False))
        _audit_line(str(body.get("model", "?")), audit, stream)
        # OpenAI SDKs ignore unknown top-level fields → safe to inject the audit
        return await _forward(request, "/chat/completions", body, stream,
                              inject=None if stream else _audit_fields(audit))

    @app.post("/v1/messages")
    async def messages(request: Request):
        """Anthropic Messages surface — point Claude Code's ANTHROPIC_BASE_URL here.
        `system` is a top-level field, forwarded untouched (never purged)."""
        body = await request.json()
        survivors, audit = dehydrate_anthropic(
            body.get("messages") or [], half_life=app.state.half_life,
            safe_threshold=app.state.threshold,
            stable_prefix=app.state.stable_prefix,
            quantum=app.state.purge_quantum,
            auto_fact=app.state.auto_fact)
        survivors, audit = apply_cache_hysteresis(
            body.get("messages") or [], survivors, audit,
            app.state.cache_hysteresis)
        _store_purged(audit)
        if app.state.redact_images:
            redact_image_secrets(survivors, _image_redactor())
        body["messages"] = survivors
        if app.state.auto_effort:
            audit["effort"] = apply_auto_effort(body, surface="anthropic")
        stream = bool(body.get("stream", False))
        _audit_line(str(body.get("model", "?")), audit, stream)
        # the Anthropic response schema is strict; keep it clean (JSONL audit only)
        return await _forward(request, "/messages", body, stream, inject=None)

    @app.get("/v1/rehydrate/{digest}")
    async def rehydrate(digest: str):
        """Return a purged block by its SHA-256 (see `purged_hashes` in the
        audit line). Nothing is lost to apoptosis — it hibernates locally."""
        if not app.state.rehydrate_dir:
            return JSONResponse({"error": "rehydration store disabled "
                                          "(set BIOMA_REHYDRATE_STORE)"},
                                status_code=404)
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            return JSONResponse({"error": "invalid digest"}, status_code=400)
        path = os.path.join(app.state.rehydrate_dir, f"{digest}.json")
        if not os.path.exists(path):
            return JSONResponse({"error": "unknown digest"}, status_code=404)
        with open(path, "rb") as f:
            unit = json.loads(f.read().decode("utf-8"))
        return JSONResponse({"digest": digest, "unit": unit})

    @app.post("/v1/messages/count_tokens")
    async def count_tokens(request: Request):
        """Auxiliary endpoint some Anthropic clients (Claude Code) call. Passthrough
        WITHOUT apoptosis: it must count the tokens the client actually holds, so
        the client's own context bookkeeping stays consistent."""
        body = await request.json()
        return await _forward(request, "/messages/count_tokens", body,
                              stream=False, inject=None)

    return app


app = create_app()


def _main() -> None:
    """Console entry point: `bioma-gateway` → runs the gateway with uvicorn.
    Config via env: BIOMA_PORT (8790), BIOMA_HOST (127.0.0.1), plus the tuning /
    upstream / audit vars documented in this module."""
    import uvicorn
    uvicorn.run("bioma.gateway:app",
                host=os.environ.get("BIOMA_HOST", "127.0.0.1"),
                port=int(os.environ.get("BIOMA_PORT", "8790")),
                log_level=os.environ.get("BIOMA_LOG_LEVEL", "info"))


if __name__ == "__main__":
    _main()
