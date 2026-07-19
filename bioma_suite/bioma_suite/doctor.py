"""
`bioma_suite/doctor.py` — `bioma-doctor`: verify the whole stack in one command.

Stdlib-only on purpose: it must run and report even on a broken or partial
install (if it needed rich or httpx it could fail exactly when you need it).
For every component it answers two questions honestly:

  1. does the import actually work? (not just "is the dist present")
  2. which version is installed? (dist metadata, falling back to `__version__`)

plus a REAL kernel smoke test (a `dehydrate()` round-trip with measured
reduction and latency — the same call the gateway makes on every request).

Exit code: 0 when the core (kernel + framework) is healthy; 1 otherwise.
Optional tiers (vision, clients, monitor, langchain) report as missing without
failing the checkup — they are opt-in extras of `bioma-framework`, and a
missing one just means that tier was not installed.
"""
from __future__ import annotations

import importlib
import sys
from typing import Optional

try:  # 3.8+: stdlib importlib.metadata
    from importlib.metadata import PackageNotFoundError, version as _dist_version
except ImportError:  # pragma: no cover
    _dist_version = None  # type: ignore[assignment]

    class PackageNotFoundError(Exception):  # type: ignore[no-redef]
        pass

# component → (dist name for version lookup, import names that must ALL work)
COMPONENTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "kernel (bioma_micro)":      ("bioma_micro", ("bioma_micro",)),
    "framework (import bioma)":  ("bioma-framework", ("bioma",)),
    "gateway":                   ("fastapi", ("fastapi", "uvicorn", "httpx")),
    "client (openai)":           ("openai", ("openai",)),
    "client (anthropic)":        ("anthropic", ("anthropic",)),
    "vision":                    ("rapidocr-onnxruntime", ("PIL", "imagehash", "rapidocr_onnxruntime", "cv2", "numpy")),
    "monitor":                   ("rich", ("rich",)),
    "carbon ledger":             ("cryptography", ("cryptography", "bioma.carbon_ledger")),
    "langchain integration":     ("bioma-langchain", ("bioma_langchain", "langchain_core")),
}
CORE = ("kernel (bioma_micro)", "framework (import bioma)")


def probe(dist: str, imports: tuple[str, ...]) -> Optional[str]:
    """Version string when every import works, else None. Import is the ground
    truth; the dist metadata (then `__version__`) only labels the version."""
    modules = []
    for name in imports:
        try:
            modules.append(importlib.import_module(name))
        except Exception:
            return None
    if _dist_version is not None:
        try:
            return _dist_version(dist)
        except PackageNotFoundError:
            pass
    return str(getattr(modules[0], "__version__", "installed"))


def kernel_smoke() -> Optional[dict]:
    """A real dehydrate() round-trip — the same call the gateway makes per
    request. Returns the audit dict, or None when the kernel is unusable."""
    try:
        kernel = importlib.import_module("bioma_micro")
        audit = kernel.dehydrate(
            [("keep me", kernel.SYSTEM), ("disposable noise " * 50, kernel.TOOL)],
            half_life=6.0, safe_threshold=0.35)
        return {"reduction": float(audit["reduction"]),
                "kernel_latency_us": float(audit["kernel_latency_us"])}
    except Exception:
        return None


def report() -> dict:
    """{component: version | None} for every component, plus the smoke test."""
    out: dict = {name: probe(dist, imports)
                 for name, (dist, imports) in COMPONENTS.items()}
    out["_smoke"] = kernel_smoke()
    return out


def _main() -> int:
    try:  # legacy Windows consoles/pipes default to cp1252 → force utf-8
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    rep = report()
    smoke = rep.pop("_smoke")
    width = max(len(n) for n in rep)
    print("B.I.O.M.A. suite — install checkup\n")
    for name, ver in rep.items():
        mark = "✓" if ver else "—"
        if ver:
            note = ver
        elif name in CORE:
            note = "MISSING — core component"
        else:
            note = "not installed (optional tier)"
        print(f"  {mark} {name.ljust(width)}  {note}")
    if smoke:
        print(f"\n  kernel smoke: dehydrate −{smoke['reduction'] * 100:.1f}% "
              f"in {smoke['kernel_latency_us']:.1f}μs — OK")
    else:
        print("\n  kernel smoke: FAILED — the Rust kernel did not answer")
    core_ok = all(rep.get(n) for n in CORE) and smoke is not None
    print("\n  verdict:", "core healthy" if core_ok else "core BROKEN — reinstall: pip install bioma-suite")
    return 0 if core_ok else 1


if __name__ == "__main__":
    raise SystemExit(_main())
