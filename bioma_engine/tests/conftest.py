"""Pytest bootstrap.

conftest is imported before any test module, so this is the earliest place to
pin the OpenMP/MKL threading env — it MUST be set before ``import torch`` runs
anywhere (the test modules import torch at top level).  Pinning to 1 thread and
allowing a duplicate OpenMP runtime avoids the Windows interpreter-teardown fault
(STATUS_STACK_BUFFER_OVERRUN / 0xC0000409) that the linalg-heavy harness tests
otherwise trigger at process exit.
"""

import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

_WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _WORKSPACE not in sys.path:
    sys.path.insert(0, _WORKSPACE)

import pytest  # noqa: E402


_EXIT_STATUS = {"code": 0}


def pytest_sessionfinish(session, exitstatus):
    _EXIT_STATUS["code"] = (
        int(exitstatus) if isinstance(exitstatus, int) else (1 if session.testsfailed else 0)
    )


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    """Hard-exit with the real pytest status AFTER the summary prints but BEFORE
    Py_Finalize.  All tests have run and our leak/gauge tests prove clean resource
    handling; the only thing left is torch's native OpenMP/MKL teardown, which
    faults on Windows (0xC0000409) after a linalg-heavy session.  ``os._exit``
    returns the correct code and skips that buggy native teardown.
    """
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(_EXIT_STATUS["code"])
