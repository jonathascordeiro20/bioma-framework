# syntax=docker/dockerfile:1
###############################################################################
# B.I.O.M.A. — multi-stage image (CPU by default, GPU-capable).
#
#   CPU  :  docker build -t bioma .
#   CUDA :  docker build -t bioma-gpu --build-arg TORCH_CHANNEL=cu121 .
#
# Stage 1 (builder) resolves all wheels into an isolated venv; stage 2 (runtime)
# copies only that venv + the source, yielding a slim, non-root runtime image.
###############################################################################
ARG PYTHON_VERSION=3.12

# ----------------------------------------------------------------------------- #
#  Stage 1 — builder: install dependencies into /opt/venv
# ----------------------------------------------------------------------------- #
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

# Which PyTorch channel to pull: cpu | cu121 | cu124 ...
ARG TORCH_CHANNEL=cpu

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install torch first from its dedicated index so the channel is deterministic,
# then the lighter web stack from PyPI.
RUN pip install --upgrade pip && \
    pip install "torch>=2.2,<3" --index-url "https://download.pytorch.org/whl/${TORCH_CHANNEL}" && \
    pip install \
        "fastapi>=0.110" \
        "uvicorn[standard]>=0.29" \
        "networkx>=3.0" \
        "psutil>=5.9" \
        "pydantic>=2.6"

# ----------------------------------------------------------------------------- #
#  Stage 2 — runtime: slim, non-root, healthchecked
# ----------------------------------------------------------------------------- #
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BIOMA_HOST=0.0.0.0 \
    BIOMA_PORT=8000

# Non-root runtime user.
RUN useradd --create-home --uid 10001 bioma

# Bring over the fully-populated virtual environment.
COPY --from=builder /opt/venv /opt/venv

# Source lives at /workspace/bioma_engine so `import bioma_engine` resolves with
# /workspace on sys.path (uvicorn adds the working directory).
WORKDIR /workspace
COPY . /workspace/bioma_engine

USER bioma
EXPOSE 8000

# Liveness probe hits the biological /health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; \
u=urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4); \
sys.exit(0 if u.status==200 else 1)" || exit 1

# One worker: the orchestrator, thread pool and live-cell gauge are in-process
# shared state.  Scale out with replicas behind a load-balancer, not workers.
CMD ["uvicorn", "bioma_engine.server:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "75"]
