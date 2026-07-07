"""
bioma_vs_claude.py — Monolithic-Pure vs. B.I.O.M.A.-Orchestrated benchmark (CLI).

A self-contained, deterministic benchmark that runs the SAME complex multi-domain
workload under two execution regimes and prints a comparative FinOps panel:

  * **Monolithic Pure**  — one large agent processes every domain in a single
    context (the classic single-LLM baseline).
  * **B.I.O.M.A. Orchestrated** — semantic divergence triggers mitosis into `k`
    domain-specialist sub-agents on a shared hormonal bus (true-cosine attention),
    which cooperate asynchronously and then undergo deterministic apoptosis,
    consolidating into the parent and physically freeing memory (try/finally +
    weakref + gc).

HONESTY (stated up front, not buried):
  • This is a **simulation with local mock agents** — NO external model/API is
    called (the framework is offline/autarkic and holds no key).  The "LLM" is a
    small local ``nn.Module``.
  • **Wall-time, RSS delta (psutil), and orphan-tensor count (gc) are REAL
    measurements.**  Token volume and cost are a **FinOps MODEL** whose knobs are
    all CLI-tunable (see ``--help``) — a monolith re-reads coupled context (the
    ``--cross-domain-tax``); specialists read only their slice plus a small bus
    summary.  Treat the $ as illustrative, the memory as measured.

Examples:
    python bioma_vs_claude.py
    python bioma_vs_claude.py --domains 12 --cross-domain-tax 0.6
    python bioma_vs_claude.py --price-in 5 --price-out 20 --json out.json --md out.md
"""

from __future__ import annotations

import os

# Pin threading before torch import (Windows OpenMP teardown safety).
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import argparse
import asyncio
import copy
import gc
import json
import math
import sys
import time
import warnings
import weakref
from dataclasses import dataclass, asdict

import torch
import torch.nn as nn
import torch.nn.functional as F

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

torch.set_num_threads(1)


# --------------------------------------------------------------------------- #
#  Configuration (all CLI-tunable) — workload + FinOps token/cost MODEL
# --------------------------------------------------------------------------- #
@dataclass
class BenchConfig:
    # workload
    domains: int = 6                 # multi-domain complexity of the prompt
    points: int = 24                 # vectors per domain
    embed_dim: int = 128
    seed: int = 1337
    # token model (per-domain volumes)
    tokens_per_domain: int = 1000    # input tokens carried by one domain's content
    output_per_domain: int = 350     # output tokens to answer one domain
    sys_overhead: int = 400          # system/instruction tokens
    bus_ctx: int = 80                # shared-bus summary a specialist also reads
    cross_domain_tax: float = 0.45   # monolith re-reads coupled context (long-context tax)
    # FinOps prices (USD / 1M tokens) — illustrative frontier tier
    price_in_per_m: float = 3.0
    price_out_per_m: float = 15.0
    # bus numerics
    c_max: float = 8.0
    blend: float = 0.2


# --------------------------------------------------------------------------- #
#  1. MockHormonalBus — blackboard [slots, embed_dim], EMA write + cosine read
# --------------------------------------------------------------------------- #
class MockHormonalBus:
    """Shared tensorial blackboard.  Writes fuse via EMA with a norm clamp for
    numerical safety; reads use TRUE cosine attention (query AND keys L2-
    normalised) over the mask of occupied slots."""

    def __init__(self, slots: int, embed_dim: int, *, c_max: float = 8.0, blend: float = 0.2):
        self.M = torch.zeros(slots, embed_dim)
        self.occupied = torch.zeros(slots, dtype=torch.bool)
        self.c_max = float(c_max)
        self.blend = float(blend)

    def register(self, idx: int) -> None:
        self.occupied[idx] = True

    def release(self, idx: int) -> None:
        self.occupied[idx] = False
        self.M[idx].zero_()

    def secrete(self, idx: int, vec: torch.Tensor, blend: float | None = None) -> None:
        b = self.blend if blend is None else float(blend)
        vec = torch.nan_to_num(vec.detach(), nan=0.0, posinf=0.0, neginf=0.0)
        fused = (1.0 - b) * self.M[idx] + b * vec
        n = float(fused.norm().item())
        if n > self.c_max:                       # clamp norm — numerical protection
            fused = fused * (self.c_max / (n + 1e-8))
        self.M[idx] = fused

    def sense(self, query: torch.Tensor) -> torch.Tensor:
        if not bool(self.occupied.any()):
            return torch.zeros_like(query)
        q = F.normalize(query.detach(), dim=0)
        keys = F.normalize(self.M, dim=1)        # true cosine: keys normalised too
        sims = keys @ q                          # [slots]
        sims = sims.masked_fill(~self.occupied, float("-inf"))
        w = torch.softmax(sims, dim=0)           # attention over occupied slots
        return (w.unsqueeze(1) * self.M).sum(dim=0)

    def occupancy(self) -> int:
        return int(self.occupied.sum().item())


# --------------------------------------------------------------------------- #
#  2. MockAgentCell — passive organism: genome, float64 energy, state equation
# --------------------------------------------------------------------------- #
class MockAgentCell(nn.Module):
    """A passive mini-agent.  Carries genome metadata and a float64 energy buffer
    updated by a discrete state equation that debits a processing cost and an
    uncertainty penalty (normalised Shannon entropy of the output distribution)."""

    def __init__(self, cell_id: str, embed_dim: int, *, generation: int = 0,
                 parent_id: str | None = None, specialization: int = -1):
        super().__init__()
        self.genome = {"id": cell_id, "generation": generation,
                       "parent_id": parent_id, "specialization": specialization}
        self.proj = nn.Linear(embed_dim, embed_dim)
        self.head = nn.Linear(embed_dim, 64)     # "vocabulary" logits for uncertainty
        self.register_buffer("energy", torch.tensor(100.0, dtype=torch.float64))
        self.last_output: torch.Tensor | None = None

    def forward(self, x: torch.Tensor, context: torch.Tensor) -> tuple[torch.Tensor, float]:
        with torch.no_grad():
            h = torch.tanh(self.proj(x) + context.unsqueeze(0))   # [n, d]
            pooled = h.mean(dim=0)                                 # [d]
            logits = self.head(pooled)                            # [64]
            p = torch.softmax(logits, dim=-1)
            shannon = float(-(p * (p + 1e-9).log()).sum().item())
            h_norm = shannon / math.log(p.numel())                # normalise to [0,1]
            self._state_equation(work=float(x.shape[0]) * 0.02, uncertainty=h_norm)
            self.last_output = pooled.clone()
        return pooled, h_norm

    def _state_equation(self, *, work: float, uncertainty: float,
                        basal: float = 0.001, kappa: float = 2.0, regen: float = 0.5,
                        e_min: float = 0.0, e_max: float = 200.0) -> None:
        """E(t+1) = clamp(E − basal·E − work − κ·H + regen, E_min, E_max)."""
        with torch.no_grad():
            e = float(self.energy.item())
            e = e - basal * e - work - kappa * uncertainty + regen
            self.energy.fill_(max(e_min, min(e_max, e)))


def semantic_divergence(x: torch.Tensor) -> float:
    """Spread of an embedding cloud around its centroid, in [0, 1]."""
    centroid = x.mean(dim=0, keepdim=True)
    sims = F.cosine_similarity(x, centroid.expand_as(x), dim=1)
    return float((1.0 - sims).clamp(0.0, 1.0).mean().item())


# --------------------------------------------------------------------------- #
#  3. BiomaBenchmarkHarness — real psutil/gc metrics around each regime
# --------------------------------------------------------------------------- #
class BiomaBenchmarkHarness:
    def __init__(self, cfg: BenchConfig):
        self.cfg = cfg
        self.d = cfg.embed_dim
        self.D = cfg.domains
        g = torch.Generator().manual_seed(cfg.seed)
        self.protos = F.normalize(torch.randn(cfg.domains, cfg.embed_dim, generator=g), dim=1)
        clouds, labels = [], []
        for k in range(cfg.domains):
            cloud = self.protos[k].unsqueeze(0) + 0.05 * torch.randn(cfg.points, cfg.embed_dim, generator=g)
            clouds.append(cloud)
            labels += [k] * cfg.points
        self.X = torch.cat(clouds, dim=0)
        self.labels = torch.tensor(labels)

    # -- real system probes ------------------------------------------------- #
    @staticmethod
    def _rss_mb() -> float:
        return round(psutil.Process().memory_info().rss / 1e6, 3) if psutil else 0.0

    @staticmethod
    def _tensor_count() -> int:
        # Scanning every live object trips a deprecated torch descriptor → mute it.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return sum(1 for o in gc.get_objects() if isinstance(o, torch.Tensor))

    def _finops(self, in_tok: int, out_tok: int) -> dict:
        cost = in_tok / 1e6 * self.cfg.price_in_per_m + out_tok / 1e6 * self.cfg.price_out_per_m
        return {"input_tokens": int(in_tok), "output_tokens": int(out_tok),
                "total_tokens": int(in_tok + out_tok), "cost_usd": round(cost, 6)}

    def _profile(self, name: str, run) -> dict:
        """Measure REAL wall-time, RSS delta and orphan-tensor delta around ``run``.
        ``run`` returns (token_dict, disposable) — the disposable is dropped before
        the post-run measurement so leaked tensors show up as orphans."""
        gc.collect()
        t_before = self._tensor_count()
        rss_before = self._rss_mb()
        t0 = time.perf_counter()
        tokens, disposable = run()
        wall = time.perf_counter() - t0
        del disposable                       # release the regime's returned handle
        gc.collect()
        rss_after = self._rss_mb()
        t_after = self._tensor_count()
        fin = self._finops(tokens["in"], tokens["out"])
        return {
            "regime": name,
            "wall_time_s": round(wall, 4),
            **fin,
            "rss_delta_mb": round(rss_after - rss_before, 3),
            "orphan_tensors": max(0, t_after - t_before),
            "agents": tokens.get("agents", 1),
            "extra": tokens.get("extra", {}),
        }

    # -- Regime A: monolithic pure ----------------------------------------- #
    def _monolithic(self):
        c = self.cfg
        agent = MockAgentCell("monolith", self.d)
        bus = MockHormonalBus(1, self.d, c_max=c.c_max, blend=c.blend)
        bus.register(0)
        held = []
        try:
            ctx = bus.sense(self.X.mean(dim=0))
            out, _h = agent(self.X, ctx)          # ONE pass over ALL domains
            bus.secrete(0, out)
            held.append(out)                      # a monolith keeps its full context resident
        except Exception as exc:                  # strict: surface, do not mask
            raise RuntimeError(f"monolithic run failed: {exc}") from exc
        in_tok = int((c.sys_overhead + self.D * c.tokens_per_domain) * (1.0 + c.cross_domain_tax))
        out_tok = self.D * c.output_per_domain
        return {"in": in_tok, "out": out_tok, "agents": 1}, (agent, bus, held)

    # -- Regime B: B.I.O.M.A. orchestrated (mitosis → bus → apoptosis) ------ #
    def _orchestrated(self):
        c = self.cfg
        parent = MockAgentCell("stem", self.d)
        bus = MockHormonalBus(self.D + 1, self.d, c_max=c.c_max, blend=c.blend)
        bus.register(0)
        divergence = semantic_divergence(self.X)  # complexity gauge → triggers mitosis

        consolidated = torch.zeros(self.d)
        in_tok = out_tok = 0
        child_refs: list[weakref.ref] = []

        async def live_and_die(k: int):
            """One specialist: mitosis (deep-copy), work on its slice via the bus,
            then DETERMINISTIC apoptosis with physical cleanup in try/finally."""
            nonlocal consolidated, in_tok, out_tok
            idx = k + 1
            child = MockAgentCell(f"cell{k}", self.d, generation=1,
                                  parent_id="stem", specialization=k)
            child.load_state_dict(copy.deepcopy(parent.state_dict()))   # deep-copy state_dict
            with torch.no_grad():                                       # specialisation bias
                child.proj.bias.add_(0.1 * self.protos[k])
            bus.register(idx)
            try:
                slice_x = self.X[self.labels == k]
                ctx = bus.sense(slice_x.mean(dim=0))
                await asyncio.sleep(0)                                  # cooperative yield
                out, _h = child(slice_x, ctx)
                bus.secrete(idx, out)
                consolidated = consolidated + out                      # transfer to parent
                in_tok += c.tokens_per_domain + c.bus_ctx              # reads only its slice
                out_tok += c.output_per_domain
            finally:
                # APOPTOSIS — release bus slot, drop refs, verify collection.
                bus.release(idx)
                child_refs.append(weakref.ref(child))
                child.last_output = None
                del child

        async def orchestrate():
            # Sibling specialists cooperate on the single-thread event loop.
            await asyncio.gather(*[live_and_die(k) for k in range(self.D)])

        try:
            asyncio.run(orchestrate())
        except Exception as exc:
            raise RuntimeError(f"orchestrated run failed: {exc}") from exc
        finally:
            gc.collect()                          # deterministic reclaim after apoptosis

        consolidated = consolidated / max(1, self.D)
        in_tok += c.sys_overhead                  # parent merge/consolidation
        out_tok += c.output_per_domain
        alive = sum(1 for r in child_refs if r() is not None)
        extra = {"divergence": round(divergence, 4), "k_children": self.D,
                 "children_still_alive_after_apoptosis": alive}
        return {"in": in_tok, "out": out_tok, "agents": 1 + self.D, "extra": extra}, (parent, bus, consolidated)

    def compare(self) -> list[dict]:
        # Sequential (logical determinism): monolithic first, then orchestrated.
        return [self._profile("Monolithic Pure", self._monolithic),
                self._profile("B.I.O.M.A. Orchestrated", self._orchestrated)]


# --------------------------------------------------------------------------- #
#  Reporting
# --------------------------------------------------------------------------- #
def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:,.4f}" if abs(v) < 1000 else f"{v:,.2f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


_ROWS = [
    ("Wall time (s)          [REAL]", "wall_time_s", True),
    ("Input tokens           [model]", "input_tokens", True),
    ("Output tokens          [model]", "output_tokens", True),
    ("Total tokens           [model]", "total_tokens", True),
    ("Session cost (USD)     [model]", "cost_usd", True),
    ("RSS delta (MB)         [REAL]", "rss_delta_mb", True),
    ("Orphan tensors (gc)    [REAL]", "orphan_tensors", True),
    ("Agents spawned                ", "agents", False),
]


def summarize(cfg: BenchConfig, mono: dict, bioma: dict) -> dict:
    tok_save = 100.0 * (mono["total_tokens"] - bioma["total_tokens"]) / mono["total_tokens"] if mono["total_tokens"] else 0.0
    cost_save = 100.0 * (mono["cost_usd"] - bioma["cost_usd"]) / mono["cost_usd"] if mono["cost_usd"] else 0.0
    rss_save = 100.0 * (mono["rss_delta_mb"] - bioma["rss_delta_mb"]) / mono["rss_delta_mb"] if mono["rss_delta_mb"] else 0.0
    return {
        "config": asdict(cfg),
        "monolithic": mono,
        "bioma": bioma,
        "savings": {
            "token_savings_pct": round(tok_save, 2),
            "cost_savings_pct": round(cost_save, 2),
            "rss_savings_pct": round(rss_save, 2),
            "wall_time_overhead_x": round(bioma["wall_time_s"] / mono["wall_time_s"], 2) if mono["wall_time_s"] else None,
            "zero_leak": bioma.get("extra", {}).get("children_still_alive_after_apoptosis") == 0
                         and bioma["orphan_tensors"] == 0,
        },
        "assumptions": {
            "note": "Simulation with local mock agents — no external model/API called.",
            "real_metrics": ["wall_time_s", "rss_delta_mb", "orphan_tensors"],
            "modeled_metrics": ["input_tokens", "output_tokens", "cost_usd"],
            "cross_domain_tax": cfg.cross_domain_tax,
            "price_usd_per_1M": {"input": cfg.price_in_per_m, "output": cfg.price_out_per_m},
        },
    }


def print_panel(cfg: BenchConfig, mono: dict, bioma: dict) -> None:
    W = 78
    print("=" * W)
    print(" B.I.O.M.A. vs. MONOLITHIC — FinOps & MEMORY BENCHMARK ".center(W, "="))
    print("=" * W)
    print(f"  Workload: {cfg.domains} coupled domains × {cfg.points} vectors "
          f"(embed_dim={cfg.embed_dim})   |   two sequential rounds")
    print("-" * W)
    print(f"  {'Metric':<32}{'Monolithic':>16}{'B.I.O.M.A.':>16}{'Δ / win':>12}")
    print("  " + "-" * (W - 4))
    for label, key, comparable in _ROWS:
        mv, bv = mono[key], bioma[key]
        if not comparable:
            delta = ""
        else:
            d = bv - mv
            if isinstance(mv, (int, float)) and mv:
                pct = 100.0 * (bv - mv) / abs(mv)
                win = "BIOMA" if d < 0 else ("MONO" if d > 0 else "tie")
                delta = f"{pct:+.0f}% {win}"
            else:
                delta = f"{d:+g}"
        print(f"  {label:<32}{_fmt(mv):>16}{_fmt(bv):>16}{delta:>12}")
    print("  " + "-" * (W - 4))

    s = summarize(cfg, mono, bioma)["savings"]
    ex = bioma.get("extra", {})
    print(f"  Token savings (model): {s['token_savings_pct']:+.1f}%   ·   "
          f"cost savings: {s['cost_savings_pct']:+.1f}%   ·   RSS savings (REAL): {s['rss_savings_pct']:+.1f}%")
    print(f"  Wall-time overhead: {s['wall_time_overhead_x']}×   ·   zero-leak: {s['zero_leak']}")
    print(f"  Divergence that triggered mitosis: {ex.get('divergence')}  "
          f"→ {ex.get('k_children')} specialists  (alive after apoptosis: "
          f"{ex.get('children_still_alive_after_apoptosis')})")
    print("=" * W)
    print("  Notes: wall-time / RSS / orphan-tensors are REAL (psutil + gc). Tokens &")
    print(f"  cost are a FinOps MODEL (monolith cross-domain re-read tax "
          f"{int(cfg.cross_domain_tax*100)}%; specialists read only their slice + a "
          f"{cfg.bus_ctx}-token")
    print(f"  bus summary; price ${cfg.price_in_per_m}/${cfg.price_out_per_m} per-M in/out).")
    print("  No external model/API was called — the 'LLM' is a local mock nn.Module.")
    print("=" * W)


def _write_md(rep: dict, path: str) -> None:
    m, b, s, cfg = rep["monolithic"], rep["bioma"], rep["savings"], rep["config"]
    L = ["# B.I.O.M.A. vs. Monolithic — FinOps & Memory Benchmark", "",
         f"Workload: **{cfg['domains']} domains × {cfg['points']} vectors** "
         f"(embed_dim={cfg['embed_dim']}, seed={cfg['seed']}).", "",
         "| Metric | Monolithic | B.I.O.M.A. |", "|---|---|---|"]
    for label, key, _c in _ROWS:
        L.append(f"| {label.strip()} | {_fmt(m[key])} | {_fmt(b[key])} |")
    L += ["",
          f"- **Token savings (model):** {s['token_savings_pct']:+.1f}% · "
          f"**cost:** {s['cost_savings_pct']:+.1f}% · **RSS (REAL):** {s['rss_savings_pct']:+.1f}%",
          f"- **Wall-time overhead:** {s['wall_time_overhead_x']}× · **zero-leak:** {s['zero_leak']}",
          "",
          "> Simulation — no external model called. Wall/RSS/orphans are REAL; "
          "tokens/cost are a FinOps model "
          f"(cross-domain tax {int(cfg['cross_domain_tax']*100)}%, "
          f"price ${cfg['price_in_per_m']}/${cfg['price_out_per_m']} per-M)."]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def _parse_args(argv=None) -> tuple[BenchConfig, argparse.Namespace]:
    p = argparse.ArgumentParser(
        prog="bioma_vs_claude",
        description="Monolithic-Pure vs. B.I.O.M.A.-Orchestrated FinOps/memory benchmark "
                    "(local mock simulation — no external model called).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    d = BenchConfig()
    g_w = p.add_argument_group("workload")
    g_w.add_argument("--domains", type=int, default=d.domains, help="coupled domains in the prompt")
    g_w.add_argument("--points", type=int, default=d.points, help="vectors per domain")
    g_w.add_argument("--embed-dim", type=int, default=d.embed_dim, dest="embed_dim")
    g_w.add_argument("--seed", type=int, default=d.seed)
    g_t = p.add_argument_group("FinOps token model")
    g_t.add_argument("--tokens-per-domain", type=int, default=d.tokens_per_domain, dest="tokens_per_domain")
    g_t.add_argument("--output-per-domain", type=int, default=d.output_per_domain, dest="output_per_domain")
    g_t.add_argument("--sys-overhead", type=int, default=d.sys_overhead, dest="sys_overhead")
    g_t.add_argument("--bus-ctx", type=int, default=d.bus_ctx, dest="bus_ctx")
    g_t.add_argument("--cross-domain-tax", type=float, default=d.cross_domain_tax, dest="cross_domain_tax",
                     help="monolith long-context re-read tax (0..1) — sensitivity knob")
    g_p = p.add_argument_group("prices (USD / 1M tokens)")
    g_p.add_argument("--price-in", type=float, default=d.price_in_per_m, dest="price_in_per_m")
    g_p.add_argument("--price-out", type=float, default=d.price_out_per_m, dest="price_out_per_m")
    g_o = p.add_argument_group("output")
    g_o.add_argument("--json", default=None, help="write the full report to this JSON path")
    g_o.add_argument("--md", default=None, help="write a Markdown summary to this path")
    g_o.add_argument("--quiet", action="store_true", help="suppress the terminal panel")
    a = p.parse_args(argv)
    cfg = BenchConfig(
        domains=a.domains, points=a.points, embed_dim=a.embed_dim, seed=a.seed,
        tokens_per_domain=a.tokens_per_domain, output_per_domain=a.output_per_domain,
        sys_overhead=a.sys_overhead, bus_ctx=a.bus_ctx, cross_domain_tax=a.cross_domain_tax,
        price_in_per_m=a.price_in_per_m, price_out_per_m=a.price_out_per_m,
    )
    if cfg.domains < 1 or cfg.points < 1 or cfg.embed_dim < 2:
        p.error("domains ≥ 1, points ≥ 1, embed-dim ≥ 2 required")
    if not (0.0 <= cfg.cross_domain_tax <= 5.0):
        p.error("--cross-domain-tax must be in [0, 5]")
    return cfg, a


def main(argv=None) -> int:
    cfg, args = _parse_args(argv)
    torch.manual_seed(cfg.seed)
    harness = BiomaBenchmarkHarness(cfg)
    try:
        mono, bioma = harness.compare()
    except Exception as exc:  # strict top-level handling
        print(f"[FATAL] benchmark failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    if not args.quiet:
        print_panel(cfg, mono, bioma)
    rep = summarize(cfg, mono, bioma)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, indent=2, ensure_ascii=False)
        if not args.quiet:
            print(f"  [written] {args.json}")
    if args.md:
        _write_md(rep, args.md)
        if not args.quiet:
            print(f"  [written] {args.md}")
    return 0


if __name__ == "__main__":
    _rc = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_rc)   # avoid the Windows OpenMP atexit teardown crash (0xC0000409)
