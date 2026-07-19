"""
`bioma-suite` — the one-shot install for the whole B.I.O.M.A. stack.

    pip install bioma-suite     # kernel + framework[all] + langchain, one command
    bioma-doctor                # verify every component of the install

This package ships no runtime of its own: it pins the full dependency set
(`bioma_micro`, `bioma-framework[all]`, `bioma-langchain`) so one install pulls
everything, and provides `bioma-doctor` — a stdlib-only checkup that reports
which components are importable, their versions, and a real kernel smoke test.
"""
__version__ = "1.0.1"

__all__ = ["__version__"]
