# B.I.O.M.A. Micro-Kernel — LEAN production image (no torch, no agents).
# Stage 1 builds the Rust/PyO3 micro-kernel wheel; stage 2 ships a slim runtime
# with only FastAPI + the OpenRouter SDK. Result: a ~200MB image (vs the ~2GB
# torch build) serving the lean apoptosis dispatch API.

FROM python:3.12-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends curl build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y --profile minimal
ENV PATH="/root/.cargo/bin:${PATH}"
WORKDIR /app
COPY bioma_micro/ ./bioma_micro/
RUN pip install --no-cache-dir maturin \
    && pip wheel ./bioma_micro -w /wheels

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY --from=build /wheels /wheels
COPY bioma/ ./bioma/
RUN pip install /wheels/*.whl \
    && pip install fastapi "uvicorn[standard]" "openai>=1" python-dotenv "pydantic>=2"
EXPOSE 8000
# OPENROUTER_API_KEY + BIOMA_ALLOWED_ORIGINS are injected at runtime (secrets
# manager / platform env) — never baked into the image.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3).status==200 else 1)"
CMD ["uvicorn", "bioma.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
