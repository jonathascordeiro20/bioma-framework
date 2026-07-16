"""bioma-langchain — context apoptosis for LangChain message histories.

Prunes stale, low-value messages with the B.I.O.M.A. Rust kernel (~1 µs
decision) before they reach the model. Class-aware: system messages and
messages marked as durable facts are never purged; verbose tool output
dehydrates first; everything else decays by recency half-life.

    from bioma_langchain import BiomaDehydrator

    dehydrator = BiomaDehydrator()          # tool-calling default: threshold 0.2
    chain = dehydrator | llm                # LCEL: lean messages reach the model
    lean = dehydrator.invoke(messages)      # or call it directly

Mark durable facts so they survive forever:

    HumanMessage("The rollback token is RBK-5521.",
                 additional_kwargs={"bioma": "fact"})
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

import bioma_micro as _kernel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    FunctionMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import Runnable, RunnableConfig

__all__ = ["BiomaDehydrator", "dehydrate_messages", "signal_for"]
__version__ = "0.1.0"

# Tool-calling agents: 0.2 keeps the freshest tool result alive (0.35, the raw
# kernel default, purges it — measured to cause agent rework; see the repo's
# BIOMA_BENCHMARK_COMPARATIVO.md).
DEFAULT_HALF_LIFE = 6.0
DEFAULT_SAFE_THRESHOLD = 0.2

_FACT_MARKS = {"fact", "durable", "pin"}


def signal_for(message: BaseMessage) -> int:
    """Map a LangChain message to a B.I.O.M.A. metabolic signal class."""
    mark = str(message.additional_kwargs.get("bioma", "")).lower()
    if mark in _FACT_MARKS:
        return _kernel.FACT
    if isinstance(message, SystemMessage):
        return _kernel.SYSTEM
    if isinstance(message, (ToolMessage, FunctionMessage)):
        return _kernel.TOOL
    if isinstance(message, AIMessage):
        # tool_calls without text are scratchpad plumbing, not conversation
        if getattr(message, "tool_calls", None) and not _text_of(message).strip():
            return _kernel.TOOL
        return _kernel.ASSISTANT
    if isinstance(message, HumanMessage):
        return _kernel.USER
    return _kernel.USER


def _text_of(message: BaseMessage) -> str:
    c = message.content
    if isinstance(c, str):
        return c
    # content blocks (multimodal / tool results): weigh their textual size
    return "\n".join(str(b.get("text", b)) if isinstance(b, dict) else str(b) for b in c)


def dehydrate_messages(
    messages: Sequence[BaseMessage],
    *,
    half_life: float = DEFAULT_HALF_LIFE,
    safe_threshold: float = DEFAULT_SAFE_THRESHOLD,
    return_audit: bool = False,
):
    """Run the kernel over a message list; return the surviving messages.

    The original message objects are returned untouched (same identity), in the
    original order. With ``return_audit=True`` returns ``(messages, audit)``
    where audit has tokens_before/tokens_after/reduction/kernel_latency_us.
    """
    pairs = [(_text_of(m), signal_for(m)) for m in messages]
    audit: dict[str, Any] = _kernel.dehydrate(
        pairs, half_life=half_life, safe_threshold=safe_threshold)

    # `kept` preserves order — two-pointer walk maps contents back to objects
    kept_texts = list(audit["kept"])
    survivors: list[BaseMessage] = []
    k = 0
    for msg, (text, _sig) in zip(messages, pairs):
        if k < len(kept_texts) and kept_texts[k] == text:
            survivors.append(msg)
            k += 1
    audit_out = {key: audit[key] for key in (
        "blocks_in", "blocks_kept", "blocks_purged",
        "tokens_before", "tokens_after", "reduction", "kernel_latency_us")}
    return (survivors, audit_out) if return_audit else survivors


class BiomaDehydrator(Runnable):
    """LCEL Runnable: ``list[BaseMessage] -> list[BaseMessage]``.

    Compose it right before the model: ``chain = dehydrator | llm``.
    The last audit is kept on ``.last_audit`` for logging/observability.
    """

    def __init__(self, *, half_life: float = DEFAULT_HALF_LIFE,
                 safe_threshold: float = DEFAULT_SAFE_THRESHOLD) -> None:
        self.half_life = half_life
        self.safe_threshold = safe_threshold
        self.last_audit: Optional[dict[str, Any]] = None

    def invoke(self, input: Sequence[BaseMessage],  # noqa: A002 — Runnable API
               config: Optional[RunnableConfig] = None, **kwargs: Any) -> list[BaseMessage]:
        survivors, audit = dehydrate_messages(
            input, half_life=self.half_life, safe_threshold=self.safe_threshold,
            return_audit=True)
        self.last_audit = audit
        return survivors
