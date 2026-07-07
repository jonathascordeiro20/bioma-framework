"""
context.py — kernel-backed context pruning (apoptosis) for the orchestrator.

Trims an agent's context window BEFORE each LLM call by evicting low-relevance
data (verbose tool logs, stale scratchpad, old turns) via the Rust kernel's
oxygen/apoptosis mechanism — cutting **input tokens** and therefore **cost** on
every request.

Uses the compiled `bioma_kernel.StateContext` when available; otherwise falls
back to an identical pure-Python apoptosis so the layer works without the Rust
build.  Each datum is tagged with a relevance `signal` and seeded with `oxygen`
proportional to its importance; a few decay cycles apoptose whatever falls below
`epsilon`, and `render()` returns the surviving (pruned) context.
"""

from __future__ import annotations

from typing import List

try:
    import bioma_kernel as _bk  # the compiled Rust kernel
    _HAS_KERNEL = True
except Exception:  # pragma: no cover - kernel optional
    _HAS_KERNEL = False

# Relevance channels (bitwise signal flags shared with the kernel).
SYSTEM = 1 << 0     # durable instructions — never prune
USER = 1 << 1       # user turns
ASSISTANT = 1 << 2  # model turns
FACT = 1 << 3       # retrieved facts / decisions to keep
TOOL = 1 << 4       # verbose tool logs / scratchpad — prime apoptosis target


def est_tokens(s: str) -> int:
    """~4 chars/token — identical to the Rust kernel's ``(len/4)+1`` so the
    Python-side 'full' count and the kernel-side 'pruned' count are consistent."""
    return len(s) // 4 + 1


class ContextPruner:
    """A self-pruning context window (kernel-backed, with a Python fallback)."""

    def __init__(self, epsilon: float = 0.05):
        self.backend = "rust" if _HAS_KERNEL else "python"
        self._eps = epsilon
        self._full_tokens = 0                      # cumulative if never pruned
        if _HAS_KERNEL:
            self._ctx = _bk.StateContext(epsilon)
        else:
            self._items: List[list] = []           # [content, oxygen, signal, tokens]

    def add(self, content: str, *, oxygen: float = 1.0, signal: int = 0) -> None:
        self._full_tokens += est_tokens(content)
        if _HAS_KERNEL:
            self._ctx.insert(content, oxygen, signal)
        else:
            self._items.append([content, oxygen, signal, est_tokens(content)])

    def prune(self, *, rate: float = 0.34, reinforce_mask: int = SYSTEM,
              reinforce_amount: float = 0.5) -> int:
        """One decay cycle → returns the number of apoptosed items."""
        if _HAS_KERNEL:
            return self._ctx.decay(rate, reinforce_mask, reinforce_amount)
        purged = 0
        kept: List[list] = []
        for it in self._items:
            if reinforce_mask and (it[2] & reinforce_mask):
                it[1] += reinforce_amount
            it[1] -= rate
            if it[1] > self._eps:
                kept.append(it)
            else:
                purged += 1
        self._items = kept
        return purged

    def prune_cycles(self, cycles: int = 3, **kw) -> int:
        """Run several decay cycles; returns total apoptosed."""
        return sum(self.prune(**kw) for _ in range(max(1, cycles)))

    def active_context(self) -> List[str]:
        return self._ctx.active_context() if _HAS_KERNEL else [it[0] for it in self._items]

    def active_tokens(self) -> int:
        return int(self._ctx.active_tokens()) if _HAS_KERNEL else sum(it[3] for it in self._items)

    def full_tokens(self) -> int:
        """Tokens the context would carry if nothing were ever pruned."""
        return self._full_tokens

    def render(self) -> str:
        """The pruned context, ready to send to the LLM."""
        return "\n".join(self.active_context())

    def reduction(self) -> float:
        f = self._full_tokens
        return 0.0 if f == 0 else 1.0 - self.active_tokens() / f
