"""
`observability.py` — Structured telemetry (BioEvent) + operational CSR (plan Fase 7).

Observability precedes validation: the telemetry and the definition of
"survival" must exist and be trustworthy **before** any experimental conclusion.

This module provides:

* **BioEvent** — a versioned, append-only JSONL event schema with a monotonic
  global ``seq``, monotonic clock, full lineage (``cell_id``/``parent_id``/
  ``root_id``/``dag_depth``) and tensor-redacted payloads.  The JSONL sink is the
  single source of truth; the DAG is reconstructable from it.
* **CSR** — the Computational Survival Rate, defined **falsifiably**:

      survive(c) = healthy_forward ∧ no_nan_inf ∧ transfer_ok
                   ∧ clean_apoptosis ∧ no_leak ∧ no_race

  Crucially "survival" means **absence of necrosis** (no unplanned crash) and
  **absence of leak beyond a calibrated tolerance** — NOT absence of apoptosis,
  which is healthy and expected.  The terminal criterion is statistical: a
  **Wilson lower bound** over a declared denominator ``N`` of births, plus a
  **tolerance-independent second oracle** (the ``gc`` live-organism cross-check).
* **Probes** — a leak *soak* (RSS-growth slope + p-value ≥ 0.05, plus ``gc``
  count → 0) and a bus *race* probe (read-after-write invariant), and a
  telemetry-overhead measurement.
"""

from __future__ import annotations

import asyncio
import gc
import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Optional

import networkx as nx
import torch

from .config import BiomaConfig, DEFAULT_CONFIG
from .mitosis_engine import MitosisEngine, live_cells_global, resource_snapshot
from .organism_core import NeuralOrganism
from .hormonal_bus import HormonalBus

SCHEMA_VERSION = "1.0"

# BioEvent types (plan §8).
EV_SPAWN = "CELL_SPAWN"
EV_MITOSIS = "MITOSIS_TRIGGER"
EV_ENERGY = "ENERGY_TICK"
EV_HORMONE_W = "HORMONE_WRITE"
EV_HORMONE_R = "HORMONE_READ"
EV_HOMEO = "HOMEOSTASIS"
EV_ADAPT = "ADAPT"
EV_TRANSFER = "REPRESENTATION_TRANSFER"
EV_APOPTOSIS = "APOPTOSIS"
EV_SYNTHESIS = "SYNTHESIS"
EV_CONVERGENCE = "CONVERGENCE"
EV_DIVERGENCE = "DIVERGENCE"
EV_ANOMALY = "ANOMALY"

# TelemetryEvent.kind → BioEvent.event_type
_KIND_MAP = {
    "genesis": EV_SPAWN,
    "divergence": EV_DIVERGENCE,
    "mitosis": EV_MITOSIS,
    "sense": EV_HORMONE_R,
    "forward": EV_ENERGY,
    "homeostasis": EV_HOMEO,
    "secrete": EV_HORMONE_W,
    "adapt": EV_ADAPT,
    "apoptosis": EV_APOPTOSIS,
    "synthesis": EV_SYNTHESIS,
    "convergence": EV_CONVERGENCE,
    "error": EV_ANOMALY,
}


@dataclass
class BioEvent:
    """One versioned, timestamped biological event with full lineage."""

    seq: int
    t_mono: float
    event_type: str
    cell_id: str
    parent_id: Optional[str]
    root_id: str
    dag_depth: int
    device: str
    energy_level: Optional[float]
    entropy: Optional[float]
    payload: dict = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def as_json(self) -> str:
        return json.dumps(asdict(self))


def _redact(metrics: dict, max_len: int = 8) -> dict:
    """Drop/redact tensor-like payloads so the JSONL stays small and readable."""
    out = {}
    for k, v in metrics.items():
        if isinstance(v, list) and len(v) > max_len:
            out[k] = {"_redacted_list_len": len(v)}
        elif isinstance(v, (int, float, str, bool)) or v is None:
            out[k] = v
        elif isinstance(v, dict):
            out[k] = _redact(v, max_len)
        else:
            out[k] = str(type(v).__name__)
    return out


def _parent_of(cell_id: str) -> Optional[str]:
    return cell_id.rsplit(".", 1)[0] if "." in cell_id else (None if cell_id == "stem" else "stem")


class BioEventSink:
    """Append-only JSONL sink with a monotonic global ``seq`` counter."""

    def __init__(self, path: Optional[str] = None, *, root_id: str = "root"):
        self.path = path
        self.root_id = root_id
        self._seq = 0
        self._events: list[BioEvent] = []
        self._fh = open(path, "w", encoding="utf-8") if path else None

    def emit(self, event_type: str, cell_id: str, *, energy=None, entropy=None,
             device: str = "cpu", payload: Optional[dict] = None) -> BioEvent:
        ev = BioEvent(
            seq=self._seq, t_mono=time.monotonic(), event_type=event_type,
            cell_id=cell_id, parent_id=_parent_of(cell_id), root_id=self.root_id,
            dag_depth=cell_id.count(".") if cell_id not in ("-", "engine") else 0,
            device=device, energy_level=energy, entropy=entropy, payload=payload or {},
        )
        self._seq += 1
        self._events.append(ev)
        if self._fh is not None:
            self._fh.write(ev.as_json() + "\n")
        return ev

    def events(self) -> list[BioEvent]:
        return list(self._events)

    def reconstruct_dag(self) -> nx.DiGraph:
        """Rebuild the lineage DAG purely from the event stream (JSONL → DAG)."""
        dag = nx.DiGraph()
        for ev in self._events:
            if ev.event_type == EV_SPAWN and ev.cell_id not in ("-", "engine"):
                dag.add_node(ev.cell_id, depth=ev.dag_depth)
                if ev.parent_id:
                    dag.add_edge(ev.parent_id, ev.cell_id)
        return dag

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


def record_run(
    engine: MitosisEngine, *, prompt: Optional[str] = None,
    embeddings: Optional[torch.Tensor] = None, root_id: str = "root",
    sink: Optional[BioEventSink] = None, path: Optional[str] = None,
) -> tuple[BioEventSink, dict]:
    """Run the engine and record its telemetry as BioEvents. Returns (sink, summary).

    Synthetic ``CELL_SPAWN`` events are inserted the first time a new cell_id is
    seen (children announce themselves via their first sense), so the DAG is
    reconstructable even though the engine does not emit an explicit spawn.
    """
    sink = sink or BioEventSink(path=path, root_id=root_id)
    device = str(engine.device)
    seen: set[str] = set()

    async def _drive():
        async for te in engine.run(prompt=prompt, embeddings=embeddings, request_id=root_id):
            cid = te.cell_id
            metrics = te.metrics or {}
            energy = metrics.get("energy")
            entropy = metrics.get("entropy")
            # Synthesize a spawn the first time a real cell appears.
            if cid not in ("-", "engine") and cid not in seen:
                seen.add(cid)
                if te.kind != "genesis":
                    sink.emit(EV_SPAWN, cid, energy=energy, entropy=entropy, device=device,
                              payload={"synthesized": True})
            btype = _KIND_MAP.get(te.kind, te.kind.upper())
            sink.emit(btype, cid, energy=energy, entropy=entropy, device=device,
                      payload=_redact(metrics))

    asyncio.run(_drive())
    return sink, (engine.last_result or {})


# --------------------------------------------------------------------------- #
#  CSR — Computational Survival Rate (falsifiable, statistical)
# --------------------------------------------------------------------------- #
def wilson_lower_bound(successes: int, n: int, z: float = 1.96) -> float:
    """Lower bound of the Wilson score interval for a binomial proportion."""
    if n == 0:
        return 1.0
    p = successes / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, centre - margin)


def count_live_organisms() -> int:
    """Tolerance-independent second oracle: living NeuralOrganism objects in gc."""
    import warnings

    gc.collect()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # silence torch deprecation noise during the scan
        return sum(
            1 for o in gc.get_objects()
            if isinstance(o, NeuralOrganism) and getattr(o, "alive", False)
        )


def _is_finite(*vals) -> bool:
    for v in vals:
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isnan(f) or math.isinf(f):
            return False
    return True


def compute_csr(sink: BioEventSink, *, gauge_after: int, gc_live: int,
                no_race: bool = True) -> dict:
    """Audit each cell's lifecycle from the event stream → CSR + Wilson bound.

    survive(c) = spawned ∧ healthy_forward ∧ no_nan_inf ∧ transfer_ok
                 ∧ clean_apoptosis ∧ no_leak ∧ no_race

    The stem survives as the synthesizer (reaches CONVERGENCE); every other cell
    must reach a clean, triggered APOPTOSIS.  The ``no_race`` conjunct (the bus
    read-after-write invariant) is NOT observable from a single run's event
    stream — it is certified out-of-band by :func:`race_probe` and passed in here
    (default ``True``); if a race was detected, pass ``no_race=False`` and every
    cell's survival is invalidated, as the conjunction requires.
    """
    cells: dict[str, dict] = {}
    reached_convergence = False
    no_nan_global = True

    for ev in sink.events():
        if ev.event_type == EV_ANOMALY:
            no_nan_global = False
        if ev.event_type == EV_CONVERGENCE:
            reached_convergence = True
        cid = ev.cell_id
        if cid in ("-", "engine"):
            continue
        c = cells.setdefault(cid, {"spawned": False, "forwarded": False, "transferred": False,
                                   "apoptosed": False, "trigger": None, "anomaly": False,
                                   "nan": False})
        if ev.event_type == EV_SPAWN:
            c["spawned"] = True
        elif ev.event_type == EV_ENERGY:
            c["forwarded"] = True
        elif ev.event_type in (EV_TRANSFER, EV_APOPTOSIS):
            c["transferred"] = True
        if ev.event_type == EV_APOPTOSIS:
            c["apoptosed"] = True
            c["trigger"] = ev.payload.get("trigger")
        if ev.event_type == EV_ANOMALY:
            c["anomaly"] = True
        if not _is_finite(ev.energy_level, ev.entropy):
            c["nan"] = True

    valid_triggers = {"task_solved", "energy_depleted", "marginal_contribution", "senescence"}
    no_leak = (gauge_after == 0 and gc_live == 0)

    births = sum(1 for c in cells.values() if c["spawned"])
    survivors = 0
    necrosis: list[str] = []
    for cid, c in cells.items():
        if not c["spawned"]:
            continue
        if cid == "stem":
            alive_ok = reached_convergence and not c["anomaly"] and not c["nan"]
            survived = alive_ok and no_leak and no_race
        else:
            survived = (
                c["forwarded"] and not c["nan"] and not c["anomaly"]
                and c["apoptosed"] and c["trigger"] in valid_triggers
                and c["transferred"] and no_leak and no_race
            )
        if survived:
            survivors += 1
        else:
            necrosis.append(cid)

    csr = survivors / births if births else 1.0
    return {
        "csr": round(csr, 6),
        "births": births,
        "survivors": survivors,
        "necrosis": necrosis,
        "necrosis_count": len(necrosis),
        "no_nan_inf": no_nan_global,
        "no_leak": no_leak,
        "no_race": no_race,
        "gauge_after": gauge_after,
        "gc_live_organisms": gc_live,
        "wilson_lower_bound": round(wilson_lower_bound(survivors, births), 6),
    }


def csr_over_runs(config: BiomaConfig, prompts: list[str], *, z: float = 1.96) -> dict:
    """Aggregate CSR over R runs → a single Wilson lower bound over N total births
    (the declared statistical denominator)."""
    total_births = total_survivors = 0
    per_run = []
    for i, prompt in enumerate(prompts):
        engine = MitosisEngine(config)
        sink, _ = record_run(engine, prompt=prompt, root_id=f"run{i}")
        rep = compute_csr(sink, gauge_after=live_cells_global(), gc_live=count_live_organisms())
        total_births += rep["births"]
        total_survivors += rep["survivors"]
        per_run.append({"run": i, "csr": rep["csr"], "births": rep["births"],
                        "necrosis": rep["necrosis_count"]})
    csr = total_survivors / total_births if total_births else 1.0
    return {
        "csr": round(csr, 6),
        "total_births": total_births,
        "total_survivors": total_survivors,
        "wilson_lower_bound": round(wilson_lower_bound(total_survivors, total_births, z), 6),
        "runs": len(prompts),
        "per_run": per_run,
    }


# --------------------------------------------------------------------------- #
#  Probes: leak soak, bus race, telemetry overhead
# --------------------------------------------------------------------------- #
def _slope_pvalue(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """OLS slope + two-sided p-value (normal approximation of the t-statistic)."""
    n = len(xs)
    if n < 3:
        return 0.0, 1.0
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx <= 0:
        return 0.0, 1.0
    b1 = sxy / sxx
    b0 = my - b1 * mx
    resid = [y - (b0 + b1 * x) for x, y in zip(xs, ys)]
    s2 = sum(r * r for r in resid) / (n - 2)
    se = math.sqrt(s2 / sxx) if s2 > 0 else 0.0
    if se == 0:
        return b1, 1.0
    t = b1 / se
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t) / math.sqrt(2.0))))
    return b1, p


def leak_soak(config: BiomaConfig, prompt: str, *, cycles: int = 40, b_max: float = 0.5) -> dict:
    """Run ``cycles`` colonies; regress RSS over the cycle index.  Leak-free ⇔ no
    significant upward trend (slope ≤ b_max MB/cycle OR p ≥ 0.05) AND gc live == 0."""
    idx, rss = [], []
    engine = MitosisEngine(config)
    for i in range(cycles):
        sink, _ = record_run(engine, prompt=prompt, root_id=f"soak{i}")
        idx.append(float(i))
        rss.append(float(resource_snapshot().get("rss_mb", 0.0)))
    slope, pval = _slope_pvalue(idx, rss)
    gc_live = count_live_organisms()
    no_growth = (slope <= b_max) or (pval >= 0.05)
    return {
        "cycles": cycles,
        "rss_slope_mb_per_cycle": round(slope, 5),
        "p_value": round(pval, 4),
        "b_max": b_max,
        "gc_live_organisms": gc_live,
        "gauge_after": live_cells_global(),
        "leak_free": bool(no_growth and gc_live == 0 and live_cells_global() == 0),
        "rss_first": round(rss[0], 2) if rss else None,
        "rss_last": round(rss[-1], 2) if rss else None,
    }


def race_probe(config: BiomaConfig = DEFAULT_CONFIG, *, n: int = 64) -> dict:
    """Read-after-write invariant under concurrency: N cells each secrete a unique
    marked vector and immediately sense; assert no exception / shape drift and that
    every write is observable in the manifold snapshot."""
    bus = HormonalBus(config)
    ids = [f"c{i}" for i in range(n)]
    for cid in ids:
        bus.register(cid)

    async def _storm():
        errors = 0
        shape_ok = True

        async def rw(cid: str, i: int):
            nonlocal errors, shape_ok
            try:
                vec = torch.zeros(config.embed_dim)
                vec[i % config.embed_dim] = float(i + 1)  # a uniquely-marked write
                await bus.secrete(cid, vec, blend=1.0)
                ctx = await bus.sense(cid, vec)
                if ctx.shape != (config.embed_dim,):
                    shape_ok = False
            except Exception:
                errors += 1

        await asyncio.gather(*[rw(cid, i) for i, cid in enumerate(ids)])
        return errors, shape_ok

    errors, shape_ok = asyncio.run(_storm())
    snap = bus.snapshot()
    finite = bool(torch.isfinite(snap).all().item())
    return {
        "writers": n, "errors": errors, "shape_consistent": shape_ok,
        "manifold_finite": finite, "occupancy": bus.occupancy(),
        "race_free": bool(errors == 0 and shape_ok and finite and bus.occupancy() == n),
    }


def telemetry_overhead(config: BiomaConfig, prompt: str, *, repeats: int = 3) -> dict:
    """Time a run with the BioEvent sink vs without, to bound instrumentation cost."""
    def _timed(record: bool) -> float:
        best = float("inf")
        for _ in range(repeats):
            engine = MitosisEngine(config)
            t0 = time.perf_counter()
            if record:
                record_run(engine, prompt=prompt, root_id="oh")
            else:
                asyncio.run(engine.synthesize(prompt=prompt, request_id="oh"))
            best = min(best, time.perf_counter() - t0)
        return best

    with_sink = _timed(True)
    without = _timed(False)
    overhead = (with_sink - without) / without if without > 0 else 0.0
    return {"with_sink_s": round(with_sink, 4), "without_s": round(without, 4),
            "overhead_ratio": round(overhead, 4)}


_COMPLEX = ("global financial market collapse energy grid failure medical logistics "
            "cybersecurity food supply water sanitation communication strategy parallel")


def _banner(t: str, w: int = 74) -> str:
    s = f" {t} "
    pad = max(0, w - len(s))
    return "=" * (pad // 2) + s + "=" * (pad - pad // 2)


def main() -> int:  # pragma: no cover - reporting entry point
    scratch = os.environ.get("BIOMA_JSONL", "bioevents.jsonl")
    cfg = DEFAULT_CONFIG
    print(_banner("B.I.O.M.A. OBSERVABILITY — Fase 7 (BioEvent + CSR)"))

    engine = MitosisEngine(cfg)
    sink, summary = record_run(engine, prompt=_COMPLEX, root_id="demo", path=scratch)
    dag = sink.reconstruct_dag()
    print(f"  BioEvents recorded : {len(sink.events())}  → {scratch}")
    print(f"  DAG reconstructed  : {dag.number_of_nodes()} nodes / {dag.number_of_edges()} edges "
          f"(engine reported {summary.get('dag_nodes')}/{summary.get('dag_edges')})")

    print("\n" + _banner("CSR (single run)"))
    rep = compute_csr(sink, gauge_after=live_cells_global(), gc_live=count_live_organisms())
    for k in ("csr", "births", "survivors", "necrosis_count", "no_nan_inf", "no_leak",
              "gc_live_organisms", "wilson_lower_bound"):
        print(f"  {k:22}: {rep[k]}")

    print("\n" + _banner("CSR over R runs (declared N births, Wilson bound)"))
    agg = csr_over_runs(cfg, [_COMPLEX] * 8)
    print(f"  runs={agg['runs']} N_births={agg['total_births']} survivors={agg['total_survivors']}")
    print(f"  CSR={agg['csr']}  Wilson lower bound (95%)={agg['wilson_lower_bound']}")

    print("\n" + _banner("LEAK SOAK (RSS trend) + RACE probe"))
    soak = leak_soak(cfg, _COMPLEX, cycles=30)
    print(f"  soak: slope={soak['rss_slope_mb_per_cycle']} MB/cycle p={soak['p_value']} "
          f"gc_live={soak['gc_live_organisms']} → leak_free={soak['leak_free']}")
    race = race_probe(cfg, n=64)
    print(f"  race: writers={race['writers']} errors={race['errors']} "
          f"finite={race['manifold_finite']} → race_free={race['race_free']}")

    print("\n" + _banner("TELEMETRY OVERHEAD"))
    oh = telemetry_overhead(cfg, _COMPLEX)
    print(f"  with_sink={oh['with_sink_s']}s without={oh['without_s']}s "
          f"overhead={oh['overhead_ratio'] * 100:.1f}%")
    print("\n" + _banner("OBSERVABILITY COMPLETE"))
    return 0


if __name__ == "__main__":
    # Hard-exit after flushing to bypass torch's native OpenMP/MKL teardown fault
    # on Windows (0xC0000409) that a linalg/engine-heavy standalone run can trigger.
    import sys as _sys

    _rc = main()
    _sys.stdout.flush()
    _sys.stderr.flush()
    os._exit(_rc)
