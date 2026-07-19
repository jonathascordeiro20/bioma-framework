"""
B.I.O.M.A. — a lean efficiency & resilience micro-kernel for LLM infrastructure.

Two proven primitives, exposed from the Rust kernel (`bioma_micro`) plus a
resilient OpenRouter abstraction and a drop-in gateway:

  * `kernel.HormonalBus`       — lock-free in-memory signal injection (~2M sig/s, ~5μs)
  * `kernel.dehydrate` / `kernel.ContextApoptosis` — autonomous context apoptosis
  * `LeanOpenRouterClient`     — resilient async dispatch with kernel-side apoptosis
  * `bioma.gateway`            — OpenAI/Anthropic drop-in gateway (`pip install bioma[gateway]`)

The optional integrations (`LeanOpenRouterClient` needs `openai`) are imported
lazily, so `import bioma` stays light for kernel-only use.
"""
import bioma_micro as kernel  # the compiled Rust micro-kernel

__all__ = ["kernel", "LeanOpenRouterClient", "Dispatch"]
__version__ = "1.2.0"


def __getattr__(name: str):
    # PEP 562 lazy import — pull the openai-backed client only when actually used
    if name in ("LeanOpenRouterClient", "Dispatch"):
        from bioma.openrouter_client import Dispatch, LeanOpenRouterClient
        return {"LeanOpenRouterClient": LeanOpenRouterClient, "Dispatch": Dispatch}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
