# 🧬 B.I.O.M.A. — Biologically Inspired Orchestration of Mutating Agents

A **PyTorch** framework that treats autonomous agents not as static software
wrappers but as **living neural organisms**. A single *stem cell* perceives an
incoming prompt, measures its **semantic divergence**, and — if the scenario is
multi-domain — undergoes **mitosis**, spawning specialised mini-agents into a
dynamic computational DAG. Cells maintain **homeostasis** (entropy balance),
consume synthetic **energy** tied to real FLOPs, collaborate through **vectorial
hormone exudation** on a shared latent manifold (no text/serialization), and
finally **apoptose** — transferring their learned representation to the parent and
releasing their VRAM/RAM.

Everything here runs **offline, deterministically, on CPU or GPU**, with zero
placeholders and zero external model downloads.

---

## The biological tensor lifecycle

```
                          ┌──────────────────────────────────────────────┐
                          │              MANIFOLD STREAM                  │
                          │   shared latent matrix  [slots × embed_dim]   │
                          │   + endocrine fields (cortisol/dopamine/…)    │
                          └──────────────────────────────────────────────┘
                                 ▲ secrete        │ sense (soft-attention)
                                 │ (write hormone)▼
   prompt ──► [ 🌱 STEM CELL ] ──divergence?──► k-means clusters
                    │  measures semantic spread of token embeddings
                    │
          divergence ≥ threshold │ (multi-domain)          │ divergence < threshold
                    ▼                                       ▼
        🧬 MITOSIS: divide()                          (solo path: stem
   deepcopy state_dict → mutate weights                 solves alone)
   split energy → specialise to a centroid
                    │
                    ▼
        ┌───────────┴────────────┐  ... one per cluster ...
        ▼                        ▼
  [ mini-agent i ]         [ mini-agent j ]        each cell:
   assess sub-domain load     ...                    sense → metabolise
        │                                             → homeostasis (entropy→setpoint)
   above-avg spread? ──yes──► 🧬 SUB-MITOSIS          → secrete → (converge?)
        │ no                    k-means its own
        ▼                       members → daughters
  🌿 DIFFERENTIATED LEAF                                 gradient adapt() to
   full metabolic loop + adapt()                         sub-domain target
        │                                                (isolated autograd)
        ▼
  transfer learned latent ──► parent.absorb()   (inherited_memory)
        │
        ▼
  ☠️ APOPTOSIS: detach params → drop refs
     → gc.collect() + torch.cuda.empty_cache()
     → release manifold slot → gauge −1
        │
        ▼
  🧠 SYNTHESIS: stem fuses inherited_memory + manifold
     → convergence metric → final answer
```

**Lifecycle stages, and where each lives in code:**

| Stage | Biology | Implementation |
|-------|---------|----------------|
| Genesis | Stem cell is born | `NeuralOrganism("stem")` — [organism_core.py](organism_core.py) |
| Perception | Sense the scenario | `PromptEmbedder.embed` (hash-based, offline) — [mitosis_engine.py](mitosis_engine.py) |
| Divergence | Cognitive-load estimate | `semantic_divergence` (centroid cosine spread) |
| Mitosis | Fission into specialists | `NeuralOrganism.divide` — deepcopy+mutate `state_dict`, split energy, specialise to k-means centroids |
| Homeostasis | Entropy balance | `NeuralOrganism.homeostasis` — proportional temperature controller |
| Metabolism | Energy from FLOPs | `metabolic_step` + `FlopMeter` (hooks on real `nn.Linear` shapes) |
| Hormones | Wire-free collaboration | `HormonalBus.secrete/sense` — attention over a shared latent matrix — [hormonal_bus.py](hormonal_bus.py) |
| Adaptation | Local learning | `NeuralOrganism.adapt` — one gradient step on a **per-cell, isolated** optimizer |
| Transfer | Inherit the child's knowledge | `parent.absorb(child_latent)` into `inherited_memory` |
| Apoptosis | Programmed death + reclaim | `NeuralOrganism.apoptose` — detach, `gc.collect()`, `empty_cache()` |
| Synthesis | Fuse into an answer | `MitosisEngine._synthesize` + convergence metric |

---

## Repository layout

```
bioma_engine/
├── config.py            # frozen biophysical constants + device policy (CUDA→CPU)
├── organism_core.py     # NeuralOrganism(nn.Module): energy, mitosis, adapt, distill, apoptosis
├── hormonal_bus.py      # HormonalBus: shared latent manifold + endocrine fields
├── mitosis_engine.py    # Stem-Cell Orchestrator: silhouette/entropy fission → async life → synthesis
├── simulation_harness.py# Fase 6 SSG + oracle: analytical ground-truth S*=(I−γC)⁻¹P, confusion matrix, 2×2
├── observability.py     # Fase 7 BioEvent JSONL + operational CSR (Wilson bound + gc cross-check) + leak/race probes
├── repair.py            # Fase 8 OODA self-correction loop: finite patch catalog (8 symptom classes), honest stopping
├── validation.py        # Fase 9 causal 2×2 factorial + statistics (Welch/MWU, Cohen d/Cliff δ, bootstrap CI, Holm-Bonferroni)
├── evolutionary_coder.py# Evolutionary Code Mutation Sandbox (lexicographic fitness + AST catalog + apoptosis)
├── _eval_runner.py      # isolated subprocess evaluator (timeout = variant apoptosis)
├── HONESTY.md           # canonical Metaphor↔Mechanism dictionary (N1/N2/N3) + epistemic bounds
├── telemetry.py         # TelemetryEvent schema + colourised biological dashboard
├── run_local.py         # PHASE 1 entry point — inject a scenario, stream telemetry
├── server.py            # PHASE 2 FastAPI: SSE + WebSocket streaming, /health
├── requirements.txt
├── Dockerfile           # multi-stage, CPU by default, GPU via --build-arg TORCH_CHANNEL=cu121
├── run_server.sh        # uvicorn boot script
├── tests/test_bioma_complete.py  # 14 duress tests: fission, bus races, apoptosis, evo, distill
└── tools/
    └── smoke_client.py  # end-to-end health + SSE + WS smoke test
```

### Evolutionary Code Sandbox (Pillar 3) + Reverse Distillation (Pillar 4)

```python
import asyncio
from bioma_engine import EvolutionaryCoder, NeuralOrganism, DEMO_SLOW_SQRT, DEMO_SQRT_TESTS

coder = EvolutionaryCoder(timeout_s=5, seed=7)
# Fitness = tests_passed*1000 − latency_ms − mem_delta_kb
result = asyncio.run(coder.evolve(DEMO_SLOW_SQRT, "solve", DEMO_SQRT_TESTS,
                                  generations=5, population=6))
print(result["improved"], result["best_report"]["latency_ms"])  # ~95% faster, still correct

# Distil the winning agent's weights into a Core Stem Cell, then demolish it:
stem = NeuralOrganism("stem")
asyncio.run(coder.evolve_and_distill(stem, DEMO_SLOW_SQRT, "solve", DEMO_SQRT_TESTS))
```

Each mutated variant runs in an **isolated subprocess with a hard timeout** — a
hanging/failing variant is killed (apoptosis) without endangering the
orchestrator. ⚠️ The sandbox `exec`s the code you give it; it is for optimising
*your own* scripts (process isolation + timeout bound the blast radius, but it is
not a security sandbox against hostile code).

### Test suite

```bash
python -m pytest -v bioma_engine/tests/     # 14 tests, all green
```

---

## Phase 1 — local prototype

```bash
python run_local.py
python run_local.py --prompt "your own multi-domain scenario" --no-color
```

Streams a live cell-culture dashboard: genesis → divergence → mitosis →
metabolism → homeostasis → hormone secretion → apoptosis → synthesis, ending
with a synthesis report (peak cells, mitosis/apoptosis counts, GFLOPs, energy
burned, convergence) and the cell-lineage DAG.

## Phase 2 — production server

```bash
# dev
python server.py
# prod
bash run_server.sh                    # uvicorn on 0.0.0.0:8000
# container
docker build -t bioma .               # CPU
docker run -p 8000:8000 bioma
```

### Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/health` | liveness + VRAM/RAM + count of living mini-agents |
| `POST` | `/v1/bioma/synthesize` | **Server-Sent Events** stream of telemetry |
| `WS`   | `/v1/bioma/ws` | WebSocket stream (JSON lines) |
| `GET`  | `/` | landing page with an in-browser live demo |

### Call it

```bash
curl -N -X POST http://localhost:8000/v1/bioma/synthesize \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Simulate a global market collapse combined with an energy grid failure, optimizing response matrices simultaneously."}'
```

```python
import httpx
with httpx.stream("POST", "http://localhost:8000/v1/bioma/synthesize",
                  json={"prompt": "..."}) as r:
    for line in r.iter_lines():
        print(line)
```

Full end-to-end check (health + SSE + WebSocket):

```bash
python tools/smoke_client.py --base http://127.0.0.1:8000
```

---

## Design guarantees

- **Gradient safety.** Mitosis copies *detached* tensor data into freshly-built
  leaf parameters; every cell's optimizer only touches its own parameters, so no
  autograd graph is ever shared between parent and child.
- **Concurrency isolation.** Every request builds its own `Colony` (bus + DAG +
  cell registry). Concurrent requests operate on disjoint sub-graphs — verified
  with 6 parallel requests (32 co-living agents at peak) returning the global
  live-cell gauge to exactly 0.
- **Deterministic memory reclaim.** `apoptose()` detaches parameters, removes
  forward hooks, drops the optimizer, moves storage to CPU, then runs
  `gc.collect()` + `torch.cuda.empty_cache()`.
- **No oversubscription / clean shutdown.** Intra-op torch threads are pinned to
  1 (we fan out across *cells*), avoiding CPU oversubscription and a Windows
  OpenMP teardown fault; the thread pool is drained at exit.
- **Offline & deterministic.** A seeded hash-embedding table is the shared
  "sensory cortex"; no network, no downloads.

## Configuration

Tune the physics in one place — `BiomaConfig` in [config.py](config.py):
`divergence_threshold`, `max_children`, `max_depth`, `cell_budget`,
`initial_energy`, `entropy_setpoint`, `metabolic_cycles`, `mutation_rate`, …

Environment overrides: `BIOMA_DEVICE` (`cpu`/`cuda`), `BIOMA_HOST`, `BIOMA_PORT`,
`BIOMA_WORKERS` (keep at 1 — see `run_server.sh`).
```
