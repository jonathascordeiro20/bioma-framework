"""
setup.py — Production installer for the sovereign B.I.O.M.A. engine.

Registers the global ``bioma`` terminal command and pins the local, CPU-optimized
runtime dependencies.  The package is **fully autarkic**: no external model
provider or cloud inference API.  The optional ``local-llm`` extra adds on-device
GGUF inference (``llama-cpp-python``) for users who supply their own local weights
— it is intentionally NOT a hard requirement, because the shipped runtime needs
no weights at all.

Install (fully independent tool)::

    cd c:\\Users\\jonat\\A.N.I.M.A\\workspace\\bioma_engine
    pip install -e .                 # registers the global `bioma` command
    pip install -e ".[local-llm]"    # + optional on-device GGUF inference
    pip install -e ".[dev]"          # + test tooling (pytest/hypothesis/httpx)

Run globally::

    bioma "optimize my recursive fibonacci for a production service"
    bioma -i          # interactive REPL
    bioma --status    # show the local backend
"""

import os

from setuptools import setup

HERE = os.path.abspath(os.path.dirname(__file__))


def _read(name: str) -> str:
    path = os.path.join(HERE, name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    return ""


setup(
    name="bioma-engine",
    version="1.0.0",
    description=(
        "B.I.O.M.A. — sovereign, fully-local, autarkic agent runtime & code "
        "optimizer (no external model / API / cloud)."
    ),
    long_description=_read("README.md"),
    long_description_content_type="text/markdown",
    author="B.I.O.M.A.",
    license="MIT",
    python_requires=">=3.10",

    # setup.py lives *inside* the package dir; treat the parent as the source
    # root so the package installs (and imports) as ``bioma_engine``.
    package_dir={"": ".."},
    packages=["bioma_engine"],
    include_package_data=True,
    package_data={"bioma_engine": ["models/README.md", "*.md"]},

    # Local, CPU-optimized runtime.  torch is the CPU wheel on this host; install
    # it from the CPU index if absent:  pip install torch --index-url \
    #   https://download.pytorch.org/whl/cpu
    install_requires=[
        "torch>=2.2,<3",
        "numpy>=1.26",
        "scipy>=1.11",
        "networkx>=3.0",
        "psutil>=5.9",
        "fastapi>=0.110",
        "uvicorn[standard]>=0.29",
        "pydantic>=2.6",
    ],
    extras_require={
        # Optional on-device GGUF inference (compiles llama.cpp; local-only, no
        # network).  Bring your own quantized weights in ./models/.
        "local-llm": ["llama-cpp-python>=0.2.0"],
        "dev": ["pytest>=8", "hypothesis>=6", "httpx>=0.27"],
    },

    entry_points={
        "console_scripts": [
            "bioma = bioma_engine.bioma_cli_launcher:main",
        ],
    },

    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Operating System :: Microsoft :: Windows",
        "License :: OSI Approved :: MIT License",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Intended Audience :: Developers",
    ],
    keywords="autonomous agents offline sovereign ast-optimizer neuroevolution cpu-inference",
)
