# B.I.O.M.A. — production image (multi-stage).
# Stage 1 builds the Rust/PyO3 kernel wheel; stage 2 ships a slim runtime.
# Both stages use the SAME Python (3.12) so the compiled wheel's ABI matches.

FROM python:3.12-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends curl build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y --profile minimal
ENV PATH="/root/.cargo/bin:${PATH}"
WORKDIR /app
COPY bioma_kernel/ ./bioma_kernel/
RUN pip install --no-cache-dir maturin \
    && pip wheel ./bioma_kernel -w /wheels

FROM python:3.12-slim AS runtime
ENV OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 KMP_DUPLICATE_LIB_OK=TRUE \
    PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY --from=build /wheels /wheels
COPY . .
RUN pip install /wheels/*.whl \
    && pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r bioma_engine/requirements.txt httpx "openai>=1" python-dotenv gunicorn
EXPOSE 8000
# OPENROUTER_API_KEY + BIOMA_ALLOWED_ORIGINS are injected at runtime (secrets
# manager / platform env) — never baked into the image.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3).status==200 else 1)"
CMD ["gunicorn","bioma_engine.server:app","-k","uvicorn.workers.UvicornWorker", \
     "-w","4","-b","0.0.0.0:8000","--timeout","120","--graceful-timeout","30"]
