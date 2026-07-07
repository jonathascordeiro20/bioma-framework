"""
`local_inference_engine.py` — Sovereign, fully-local inference controller.

B.I.O.M.A. runs **100% locally** with **no external model provider, hosted API,
or cloud**.  Its own runtime is a local ``torch.nn.Module`` plus a
**deterministic AST-transform optimizer** that needs **no downloaded weights** —
sovereign by construction.  No byte leaves the host.

Optional local weights
-----------------------
If you drop quantized weights (``.gguf`` or ``.safetensors``) into ``./models/``
**and** install the optional ``local-llm`` extra (``llama-cpp-python``), the
engine detects them and can load them for **local-only** free-form inference over
the CPU cores.  This is entirely offline (llama.cpp runs the weights on-device).
By default — the shipped configuration, with no weights present — the engine uses
the sovereign deterministic optimizer.  Either way, nothing contacts the network.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from typing import Optional

from .config import BiomaConfig, DEFAULT_CONFIG
from .bioma_integration_hook import process_external_prompt_sync, IntegrationResult

_DEFAULT_MODELS_DIR = os.environ.get("BIOMA_MODELS_DIR") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "models"
)


@dataclass
class EngineStatus:
    backend: str            # "deterministic_ast" (default) | "local_gguf" (optional)
    models_dir: str
    weights_found: list
    threads: int
    network_required: bool  # always False — sovereign / offline


class LocalInferenceEngine:
    """Routes prompts to the local, offline B.I.O.M.A. runtime.

    The default backend is the sovereign deterministic AST optimizer.  A local
    GGUF backend is selected only if weights are present AND ``llama-cpp-python``
    is installed — and even then it runs the weights **on-device** (no network).
    """

    def __init__(self, models_dir: Optional[str] = None, config: BiomaConfig = DEFAULT_CONFIG):
        self.config = config
        self.models_dir = models_dir or _DEFAULT_MODELS_DIR
        self.threads = max(2, min(12, os.cpu_count() or 4))  # all logical cores
        self.weights = self._discover_weights()
        self.backend = self._select_backend()
        self._llm = None  # lazily-loaded llama.cpp handle (optional path)

    # -- Local weight discovery / backend selection ------------------------ #
    def _discover_weights(self) -> list:
        if not os.path.isdir(self.models_dir):
            return []
        return sorted(
            f for f in os.listdir(self.models_dir)
            if f.lower().endswith((".gguf", ".safetensors"))
        )

    @staticmethod
    def _has_llama_cpp() -> bool:
        return importlib.util.find_spec("llama_cpp") is not None

    def _select_backend(self) -> str:
        has_gguf = any(w.lower().endswith(".gguf") for w in self.weights)
        if has_gguf and self._has_llama_cpp():
            return "local_gguf"
        return "deterministic_ast"

    def status(self) -> EngineStatus:
        return EngineStatus(
            backend=self.backend, models_dir=self.models_dir,
            weights_found=list(self.weights), threads=self.threads,
            network_required=False,
        )

    # -- Generation (the sovereign, tested path) --------------------------- #
    def generate(
        self, prompt: str, *,
        source: Optional[str] = None, entrypoint: Optional[str] = None,
        test_cases: Optional[list] = None, generations: int = 4, population: int = 6,
        timeout_s: Optional[float] = None, use_cache: bool = True,
    ) -> IntegrationResult:
        """Produce an optimized code payload fully locally and offline.

        Uses the deterministic AST optimizer (evolutionary_coder) in isolated
        subprocess sandboxes with strict timeouts + apoptosis.  Nothing contacts
        the network (``execution_mode="OFFLINE_ONLY"``)."""
        return process_external_prompt_sync(
            prompt, source=source, entrypoint=entrypoint, test_cases=test_cases,
            generations=generations, population=population,
            execution_mode="OFFLINE_ONLY", timeout_s=timeout_s, use_cache=use_cache,
        )

    # -- Optional local GGUF inference (bring-your-own weights, offline) ---- #
    def load_gguf(self, *, n_ctx: int = 2048):
        """Load local GGUF weights via llama-cpp-python (local-only inference).

        Raises if no ``.gguf`` weights are present or the optional extra is not
        installed — the sovereign deterministic optimizer is used instead."""
        if self.backend != "local_gguf":
            raise RuntimeError(
                "No local GGUF weights + llama-cpp-python detected; the sovereign "
                "deterministic optimizer is the active backend. Place a .gguf file "
                f"in {self.models_dir} and `pip install 'bioma-engine[local-llm]'` to enable."
            )
        from llama_cpp import Llama  # type: ignore[import-not-found]  # optional on-device extra

        if self._llm is None:
            gguf = next(w for w in self.weights if w.lower().endswith(".gguf"))
            self._llm = Llama(
                model_path=os.path.join(self.models_dir, gguf),
                n_ctx=n_ctx, n_threads=self.threads, verbose=False,
            )
        return self._llm
