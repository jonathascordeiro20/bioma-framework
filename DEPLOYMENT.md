# B.I.O.M.A. — Production Deployment Runbook

A practical, staged guide to take B.I.O.M.A. from repo → production. Two shippable
surfaces:

- **Sovereign mode** — the offline engine (`bioma_engine`) + Rust kernel. No
  network, no keys. For air-gapped / regulated deployments.
- **Online mode** — the orchestrator (`bioma_orchestrator`) + FastAPI server,
  calling market LLMs through OpenRouter. Needs a key + egress + cost controls.

> ⚠️ **Secrets rule #1.** Never put `OPENROUTER_API_KEY` in the repo (not even
> `.env.example`). Locally it lives in `.gitignore`d `.env`; in production it
> comes from your platform's **secrets manager** (below). If a key ever lands in
> a file or a log, **rotate it** at <https://openrouter.ai/keys>.

---

## 0 · Prerequisites
- Python 3.12, Rust 1.75+ (`rustup`), and a C toolchain (for PyO3/maturin).
- For online mode: an OpenRouter account + key, and outbound HTTPS to
  `openrouter.ai`.

## 1 · Build
```bash
# Python deps
python -m pip install -r bioma_engine/requirements.txt
python -m pip install httpx "openai>=1" python-dotenv       # online extras

# Rust kernel → native extension (release + LTO)
python -m pip install maturin
cd bioma_kernel && python -m pip install . && cd ..

# Sanity
python -m pytest bioma_engine/tests bioma_orchestrator/tests -q
python -c "import bioma_kernel, bioma_engine, bioma_orchestrator; print('ok')"
```

## 2 · Secrets (production)
Do **not** ship a `.env`. Inject the key as an environment variable from a
secrets manager:

| Platform | How |
|---|---|
| Docker / Compose | `--env-file` from a mounted secret, or `environment:` from a vault |
| Kubernetes | `Secret` → `env.valueFrom.secretKeyRef` |
| AWS | Secrets Manager / SSM Parameter Store → task env |
| Fly/Render/Railway | dashboard "Secrets" → `OPENROUTER_API_KEY` |

The code reads `os.environ.get("OPENROUTER_API_KEY")` — the `.env` auto-load is a
**local convenience only** and is inert when the var is already set.

## 3 · Run the API server
The FastAPI app (`bioma_engine/server.py`, re-exported by `bioma_cloud_server`)
serves `/health`, the SSE/WS telemetry, and `POST /v1/bioma/integrate|evolve`.

```bash
# dev
python -m bioma_engine.bioma_cloud_server        # binds 0.0.0.0:8000

# production (multiple workers behind a process manager)
gunicorn bioma_engine.server:app \
  -k uvicorn.workers.UvicornWorker \
  -w 4 -b 0.0.0.0:8000 --timeout 120 --graceful-timeout 30
```
> The engine holds in-process shared state (daemon cache, thread pools). Scale
> **out with replicas behind a load balancer**, not with threads inside one proc.
> Set `OMP_NUM_THREADS=1` and `KMP_DUPLICATE_LIB_OK=TRUE` in the environment.

## 4 · Container image
```dockerfile
# Dockerfile (multi-stage: build the Rust kernel, ship a slim runtime)
FROM rust:1-slim AS kernel
WORKDIR /app
RUN apt-get update && apt-get install -y python3 python3-pip python3-dev && rm -rf /var/lib/apt/lists/*
COPY bioma_kernel/ ./bioma_kernel/
RUN pip3 install --break-system-packages maturin && cd bioma_kernel && pip3 wheel . -w /wheels

FROM python:3.12-slim AS runtime
ENV OMP_NUM_THREADS=1 KMP_DUPLICATE_LIB_OK=TRUE PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=kernel /wheels /wheels
COPY . .
RUN pip install --no-cache-dir /wheels/*.whl \
 && pip install --no-cache-dir -r bioma_engine/requirements.txt httpx "openai>=1" python-dotenv gunicorn
EXPOSE 8000
# OPENROUTER_API_KEY comes from the orchestrator, injected at runtime — never baked in.
CMD ["gunicorn","bioma_engine.server:app","-k","uvicorn.workers.UvicornWorker","-w","4","-b","0.0.0.0:8000","--timeout","120"]
```
```bash
docker build -t bioma:latest .
docker run -p 8000:8000 --env OPENROUTER_API_KEY="$OPENROUTER_API_KEY" bioma:latest
```

## 5 · Edge: HTTPS + CORS
- Terminate TLS at a reverse proxy (nginx/Caddy/ALB) → `proxy_pass` to `:8000`.
- The server already ships permissive CORS for the local dashboard. **In
  production, restrict `allow_origins`** in `bioma_engine/server.py` to your real
  front-end origin(s) instead of `*`.

## 6 · Health, scaling, monitoring
- **Liveness/readiness**: `GET /health` (returns vitals + live-agent count).
- **Autoscale** on CPU + request latency; each replica is independent.
- **Telemetry**: the live nervous-system feed (`nervous_system_server.py`) exposes
  a WebSocket snapshot; scrape or stream it to your dashboards.
- **Cost controls (online mode)**: cap `max_tokens`, keep context apoptosis ON
  (`prune_context=True`), and set OpenRouter spend limits on the key. The
  exponential backoff already handles 429s.

## 7 · CI/CD
`.github/workflows/ci.yml` builds the Rust kernel and runs the test suites on
every push. Extend it with a build-and-publish step (GHCR) to ship the image:
```bash
gh workflow run ci.yml        # or push to main
```

## 8 · Go-live checklist
- [ ] `OPENROUTER_API_KEY` set via secrets manager (not in the image/repo).
- [ ] Key rotated after any exposure.
- [ ] CORS `allow_origins` restricted to real origins.
- [ ] `gunicorn -w N` sized to cores; replicas behind a LB.
- [ ] `/health` wired to the orchestrator's liveness probe.
- [ ] OpenRouter spend limit + alerts configured.
- [ ] `python -m pytest` green in CI; `python build_dossier.py` archived as the
      release evidence.
