"""
B.I.O.M.A. — a lean efficiency & resilience micro-kernel for LLM infrastructure.

Two proven primitives, exposed from the Rust kernel (`bioma_micro`) plus a
resilient OpenRouter abstraction:

  * `kernel.HormonalBus`       — lock-free in-memory signal injection (~2M sig/s, ~5μs)
  * `kernel.dehydrate` / `kernel.ContextApoptosis` — autonomous context apoptosis
  * `LeanOpenRouterClient`     — resilient async dispatch with kernel-side apoptosis
"""
import bioma_micro as kernel  # the compiled Rust micro-kernel

from bioma.openrouter_client import Dispatch, LeanOpenRouterClient

__all__ = ["kernel", "LeanOpenRouterClient", "Dispatch"]
__version__ = "1.0.0"
