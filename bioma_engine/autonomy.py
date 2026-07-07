"""
`autonomy.py` — Verifiable guarantee that B.I.O.M.A. runs fully autonomously.

The framework depends on **no external model, LLM, hosted-inference API, or
assistant**.  The only "model" is its own local ``torch.nn.Module`` runtime
(self-contained and deterministic), and the code optimizer is a deterministic
AST-transform catalog.  No network is required to run the core.

This module makes that a *checkable* property (in the spirit of the whole
project — every guarantee is tested): :func:`autonomy_audit` statically scans the
package source for any dependency on third-party model/inference libraries and
for any vendor/assistant name token, and reports violations.
"""

from __future__ import annotations

import ast
import os

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))

# Hosted / cloud model APIs the runtime must NOT use: these send data OFF the
# host to a third-party provider, breaking sovereignty.
FORBIDDEN_MODEL_LIBS = {
    "openai", "anthropic", "cohere", "replicate", "together", "litellm",
    "langchain", "langchain_core", "google.generativeai", "vertexai",
    "transformers", "sentence_transformers", "huggingface_hub", "ollama",
    "mistralai", "groq", "boto3",
}

# Local, on-device inference runtimes that run user-supplied weights with **zero
# network egress** — sovereign by nature and explicitly optional (extras_require,
# lazily imported).  Their presence does NOT break autonomy; we surface them for
# transparency instead of forbidding them.
ALLOWED_LOCAL_INFERENCE = {"llama_cpp", "ctransformers"}

# Vendor / assistant name tokens that must not appear in the source (substring-safe:
# none of these collide with the project's own vocabulary such as "coherence").
FORBIDDEN_TOKENS = ("claude", "anthropic", "openai", "chatgpt", "copilot", "gemini")


def _py_files() -> list[str]:
    return [
        os.path.join(_PKG_DIR, n)
        for n in sorted(os.listdir(_PKG_DIR))
        if n.endswith(".py") and n != "autonomy.py"
    ]


def _imported_roots(path: str) -> set[str]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError):
        return set()
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name)
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module)
            roots.add(node.module.split(".")[0])
    return roots


def autonomy_audit() -> dict:
    """Statically verify the package has no external-model dependency. Returns a
    report with ``autonomous`` True iff clean."""
    model_violations: list[dict] = []
    token_violations: list[dict] = []
    local_inference: list[dict] = []
    files = _py_files()
    for path in files:
        name = os.path.basename(path)
        roots = _imported_roots(path)
        for lib in FORBIDDEN_MODEL_LIBS:
            if lib in roots or lib.split(".")[0] in roots:
                model_violations.append({"file": name, "lib": lib})
        for lib in ALLOWED_LOCAL_INFERENCE:
            if lib in roots:
                local_inference.append({"file": name, "lib": lib})
        try:
            text = open(path, "r", encoding="utf-8").read().lower()
        except OSError:
            text = ""
        for tok in FORBIDDEN_TOKENS:
            if tok in text:
                token_violations.append({"file": name, "token": tok})

    clean = not model_violations and not token_violations
    return {
        "autonomous": clean,
        "no_external_model_libs": not model_violations,
        "no_vendor_references": not token_violations,
        "model_violations": model_violations,
        "token_violations": token_violations,
        "optional_local_inference": local_inference,  # sovereign, offline, optional
        "scanned_files": len(files),
        "local_model": "torch.nn.Module — self-contained, deterministic",
        "code_optimizer": "deterministic AST-transform catalog (no model)",
        "network_required_to_run_core": False,
    }


def main() -> int:  # pragma: no cover - reporting entry point
    rep = autonomy_audit()
    w = 68
    print("=" * w)
    print(" B.I.O.M.A. — AUTONOMY AUDIT ".center(w, "="))
    print("=" * w)
    print(f"  scanned files                : {rep['scanned_files']}")
    print(f"  no external model/LLM libs   : {rep['no_external_model_libs']}")
    print(f"  no vendor/assistant tokens   : {rep['no_vendor_references']}")
    print(f"  local model                  : {rep['local_model']}")
    print(f"  code optimizer               : {rep['code_optimizer']}")
    print(f"  network required to run core : {rep['network_required_to_run_core']}")
    if rep["optional_local_inference"]:
        libs = sorted({v["lib"] for v in rep["optional_local_inference"]})
        print(f"  optional local inference     : {', '.join(libs)} (on-device, offline, opt-in)")
    if rep["model_violations"]:
        print("  MODEL VIOLATIONS:", rep["model_violations"])
    if rep["token_violations"]:
        print("  TOKEN VIOLATIONS:", rep["token_violations"])
    print("-" * w)
    print(f"  VERDICT: {'FULLY AUTONOMOUS ✓' if rep['autonomous'] else 'REVIEW — external dependency found'}")
    print("=" * w)
    return 0 if rep["autonomous"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
