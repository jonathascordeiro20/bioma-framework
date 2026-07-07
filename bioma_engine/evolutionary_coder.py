"""
`evolutionary_coder.py` — Evolutionary Code Mutation Sandbox (plan Fase 10).

Refactoring is **discrete, non-differentiable search** over the space of
programs.  This module manipulates **source text only** — no tensors, no neural
math, no differentiation — which is auditable statically (the coder audit test
asserts the module contains none of those tokens).  It ingests a Python source
that defines a target function, spawns variants by applying **named AST
transforms from a deterministic catalog**, executes each variant in an
**isolated subprocess** with a hard timeout, scores them by a **lexicographic**
fitness, and apoptoses (kills + purges) hanging/failing variants.

Fitness is **lexicographic** (plan Fase 10 — not a naive weighted sum of
incommensurable units):

    correctness (hard gate)  →  latency (median of R runs)  →  memory (RSS Δ)

Every variant is **labelled by origin** (which catalog transform produced it), so
a gain is *measured, not narrated*: random mutation does not "discover" an
algorithm — the speed-up comes from a known transform (e.g. inserting
``functools.lru_cache`` to memoise a recursive function, or shrinking a loop
bound).  The winning transform is **promoted to a reusable catalog**; this is the
honest replacement for the earlier "neural knowledge-transfer into the stem cell"
idea (which was a category error — no network learns a "concept of clean code").
"""

from __future__ import annotations

import ast
import asyncio
import functools
import gc
import json
import os
import random
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Optional

from .config import BiomaConfig, DEFAULT_CONFIG

_RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_eval_runner.py")


# --------------------------------------------------------------------------- #
#  Fitness report — lexicographic
# --------------------------------------------------------------------------- #
@dataclass
class FitnessReport:
    """Result of evaluating one code variant. Selection uses :attr:`sort_key`."""

    tests_passed: int = 0
    tests_total: int = 0
    latency_ms: float = 0.0
    mem_delta_kb: float = 0.0
    error: Optional[str] = None
    alive: bool = True            # False => apoptosed (timeout/kill)
    source: str = ""
    origin: str = "seed"          # which catalog transform produced this variant

    @property
    def correct(self) -> bool:
        return self.tests_total > 0 and self.tests_passed == self.tests_total

    @property
    def sort_key(self) -> tuple:
        """Lexicographic key (higher is fitter): correctness gate first, then
        lower latency, then lower memory.  A correct program ALWAYS outranks an
        incorrect one no matter how fast — correctness is a hard gate."""
        gate = 1 if (self.alive and self.correct) else 0
        return (gate, -self.latency_ms, -self.mem_delta_kb)

    def as_dict(self) -> dict:
        return {
            "tests_passed": self.tests_passed,
            "tests_total": self.tests_total,
            "latency_ms": round(self.latency_ms, 4),
            "mem_delta_kb": round(self.mem_delta_kb, 4),
            "error": self.error,
            "alive": self.alive,
            "correct": self.correct,
            "origin": self.origin,
        }


# --------------------------------------------------------------------------- #
#  AST transform catalog (deterministic, named, origin-labelled)
# --------------------------------------------------------------------------- #
_ARITH = (ast.Add, ast.Sub, ast.Mult)
_CMP = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)


class _SinglePointMutator(ast.NodeTransformer):
    """Applies exactly one random node-level edit and records which kind."""

    def __init__(self, rng: random.Random, target: int):
        self.rng = rng
        self.target = target
        self._i = 0
        self.applied = False
        self.origin = "none"

    def _hit(self) -> bool:
        hit = self._i == self.target
        self._i += 1
        return hit

    def visit_Constant(self, node: ast.Constant):  # noqa: N802
        if isinstance(node.value, bool):
            return node
        if isinstance(node.value, int) and self._hit():
            if node.value > 8 and self.rng.random() < 0.6:
                new = max(1, int(node.value * self.rng.choice([0.25, 0.5, 0.5, 0.75])))
            else:
                new = max(1, node.value + self.rng.choice([-4, -2, -1, 1, 2]))
            self.applied, self.origin = True, "perturb_int"
            return ast.copy_location(ast.Constant(value=new), node)
        if isinstance(node.value, float) and self._hit():
            self.applied, self.origin = True, "perturb_float"
            return ast.copy_location(
                ast.Constant(value=node.value * self.rng.choice([0.5, 0.75, 0.9, 1.1, 1.25])), node
            )
        return node

    def visit_BinOp(self, node: ast.BinOp):  # noqa: N802
        self.generic_visit(node)
        if isinstance(node.op, _ARITH) and self._hit():
            node.op = self.rng.choice([o for o in _ARITH if not isinstance(node.op, o)])()
            self.applied, self.origin = True, "swap_binop"
        return node

    def visit_Compare(self, node: ast.Compare):  # noqa: N802
        self.generic_visit(node)
        if len(node.ops) == 1 and isinstance(node.ops[0], _CMP) and self._hit():
            node.ops = [self.rng.choice([o for o in _CMP if not isinstance(node.ops[0], o)])()]
            self.applied, self.origin = True, "swap_compare"
        return node


def _count_sites(tree: ast.AST) -> int:
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            n += 1
        elif isinstance(node, ast.BinOp) and isinstance(node.op, _ARITH):
            n += 1
        elif isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], _CMP):
            n += 1
    return n


def apply_lru_cache(source: str, entrypoint: str) -> Optional[str]:
    """Catalog transform: memoise ``entrypoint`` with ``functools.lru_cache``.

    A genuine algorithmic transform (turns naive-recursive into memoised), the
    canonical example the plan cites. Returns the new source, or None if the
    function already has the decorator.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    changed = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == entrypoint:
            already = any(
                (isinstance(d, ast.Call) and getattr(d.func, "attr", getattr(d.func, "id", "")) == "lru_cache")
                or (getattr(d, "attr", getattr(d, "id", "")) == "lru_cache")
                for d in node.decorator_list
            )
            if already:
                return None
            deco = ast.parse("functools.lru_cache(maxsize=None)").body[0].value
            node.decorator_list.insert(0, deco)
            changed = True
    if not changed:
        return None
    ast.fix_missing_locations(tree)
    new_body = "import functools\n" + ast.unparse(tree)
    try:
        compile(new_body, "<mutant>", "exec")
    except (SyntaxError, ValueError):
        return None
    return new_body


# --------------------------------------------------------------------------- #
#  Evolutionary Coder
# --------------------------------------------------------------------------- #
class EvolutionaryCoder:
    """Mutate (named transforms) → execute-in-parallel → lexicographic score →
    apoptose failures → return the fittest correct program + promote its transform."""

    def __init__(
        self,
        config: BiomaConfig = DEFAULT_CONFIG,
        *,
        timeout_s: float = 5.0,
        tolerance: float = 1e-3,
        compare: str = "approx",
        repeats: int = 5,
        warmup: int = 1,
        max_workers: int = 6,
        seed: Optional[int] = None,
    ) -> None:
        self.config = config
        self.timeout_s = timeout_s
        self.tolerance = tolerance
        self.compare = compare
        self.repeats = repeats
        self.warmup = warmup
        self.rng = random.Random(seed if seed is not None else config.seed)
        from concurrent.futures import ThreadPoolExecutor

        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="bioma-evo")
        self.apoptosis_count = 0
        # Promoted winning transforms (honest catalog growth; pattern harvesting).
        self.catalog: list[dict] = []

    # ------------------------------------------------------------------ #
    #  Mutation via the named catalog
    # ------------------------------------------------------------------ #
    def apply_transform(self, source: str, entrypoint: str, name: str) -> Optional[str]:
        """Apply one named catalog transform deterministically (for tests/tools)."""
        if name == "insert_lru_cache":
            return apply_lru_cache(source, entrypoint)
        # single-point family: search for a site of the requested kind
        try:
            base = ast.parse(source)
        except SyntaxError:
            return None
        sites = _count_sites(base)
        for target in range(sites):
            mut = _SinglePointMutator(self.rng, target)
            tree = mut.visit(ast.parse(source))
            if mut.applied and mut.origin == name:
                ast.fix_missing_locations(tree)
                cand = ast.unparse(tree)
                try:
                    compile(cand, "<mutant>", "exec")
                    return cand
                except (SyntaxError, ValueError):
                    continue
        return None

    def mutate(self, source: str, entrypoint: str, n: int) -> list[tuple[str, str]]:
        """Return up to ``n`` distinct ``(variant_source, origin)`` pairs."""
        variants: list[tuple[str, str]] = []
        seen: set[str] = {source}

        # Always try the algorithmic memoisation transform once (if applicable).
        memo = apply_lru_cache(source, entrypoint)
        if memo and memo not in seen:
            seen.add(memo)
            variants.append((memo, "ast:insert_lru_cache"))

        try:
            sites = _count_sites(ast.parse(source))
        except SyntaxError:
            sites = 0

        attempts = 0
        while len(variants) < n and sites > 0 and attempts < n * 8:
            attempts += 1
            mut = _SinglePointMutator(self.rng, self.rng.randrange(sites))
            tree = mut.visit(ast.parse(source))
            if not mut.applied:
                continue
            ast.fix_missing_locations(tree)
            try:
                cand = ast.unparse(tree)
                compile(cand, "<mutant>", "exec")
            except (SyntaxError, ValueError):
                continue
            if cand not in seen:
                seen.add(cand)
                variants.append((cand, f"ast:{mut.origin}"))
        return variants[:n]

    # ------------------------------------------------------------------ #
    #  Evaluation (isolated subprocess + hard timeout = apoptosis)
    # ------------------------------------------------------------------ #
    def _evaluate_blocking(self, source: str, entrypoint: str, test_cases: list, origin: str) -> FitnessReport:
        spec = {
            "source": source, "entrypoint": entrypoint, "test_cases": test_cases,
            "tolerance": self.tolerance, "compare": self.compare,
            "repeats": self.repeats, "warmup": self.warmup,
        }
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        try:
            json.dump(spec, tmp)
            tmp.close()
            proc = subprocess.run(
                [sys.executable, _RUNNER, tmp.name],
                capture_output=True, text=True, timeout=self.timeout_s,
            )
            out = (proc.stdout or "").strip().splitlines()
            data = json.loads(out[-1]) if out else {}
            return FitnessReport(
                tests_passed=int(data.get("tests_passed", 0)),
                tests_total=int(data.get("tests_total", len(test_cases))),
                latency_ms=float(data.get("latency_ms", 0.0)),
                mem_delta_kb=float(data.get("mem_delta_kb", 0.0)),
                error=data.get("error") or ((proc.stderr or "").strip() or None if proc.returncode else None),
                alive=True, source=source, origin=origin,
            )
        except subprocess.TimeoutExpired:
            # The variant hung: subprocess.run killed it. Apoptosis.
            return FitnessReport(tests_passed=0, tests_total=len(test_cases),
                                 error="timeout -> apoptosis", alive=False, source=source, origin=origin)
        except Exception as exc:  # pragma: no cover - defensive
            return FitnessReport(tests_passed=0, tests_total=len(test_cases),
                                 error=f"runner: {type(exc).__name__}: {exc}", alive=False,
                                 source=source, origin=origin)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    async def evaluate(self, source: str, entrypoint: str, test_cases: list, origin: str = "seed") -> FitnessReport:
        """Async wrapper: run one variant in the pool so many run in parallel."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._pool, functools.partial(self._evaluate_blocking, source, entrypoint, test_cases, origin)
        )

    # ------------------------------------------------------------------ #
    #  Evolution loop
    # ------------------------------------------------------------------ #
    async def evolve(
        self, source: str, entrypoint: str, test_cases: list, *,
        generations: int = 4, population: int = 6,
    ) -> dict:
        """Evolve ``source`` toward the lexicographic optimum. Elitism guarantees
        the returned program is at least as fit (and as correct) as the input."""
        self.apoptosis_count = 0
        baseline = await self.evaluate(source, entrypoint, test_cases, origin="seed")
        best = baseline
        history = [{"generation": 0, "best_latency_ms": round(best.latency_ms, 4),
                    "best_correct": best.correct, "population": 1, "apoptosis": 0}]

        for gen in range(1, generations + 1):
            mutants = self.mutate(best.source, entrypoint, population)
            if not mutants:
                history.append({"generation": gen, "best_latency_ms": round(best.latency_ms, 4),
                                "population": 0, "apoptosis": 0, "note": "no mutable sites"})
                break

            reports = await asyncio.gather(*[
                self.evaluate(src, entrypoint, test_cases, origin=org) for src, org in mutants
            ])

            gen_apoptosis = 0
            for rep in reports:
                # Apoptosis: a dead (timeout) or incorrect variant is purged.
                if not rep.alive or not rep.correct:
                    gen_apoptosis += 1
                    continue
                if rep.sort_key > best.sort_key:   # lexicographic improvement
                    best = rep

            self.apoptosis_count += gen_apoptosis
            gc.collect()  # host-side reclaim (variants live in their own processes)
            history.append({"generation": gen, "best_latency_ms": round(best.latency_ms, 4),
                            "best_correct": best.correct, "best_origin": best.origin,
                            "population": len(mutants), "apoptosis": gen_apoptosis})

        improved = bool(best.correct and baseline.correct and best.latency_ms < baseline.latency_ms)
        promoted = None
        if improved and best.origin != "seed":
            promoted = self.promote(best, baseline)

        return {
            "best_source": best.source,
            "best_report": best.as_dict(),
            "baseline_report": baseline.as_dict(),
            "improved": improved,
            "winning_transform": best.origin,
            "latency_gain_pct": round(
                100.0 * (1.0 - best.latency_ms / baseline.latency_ms), 2
            ) if baseline.latency_ms > 0 else 0.0,
            "generations": generations,
            "apoptosis_count": self.apoptosis_count,
            "promoted": promoted,
            "catalog_size": len(self.catalog),
            "history": history,
        }

    # ------------------------------------------------------------------ #
    #  Catalog promotion (honest replacement for the neural-transfer idea)
    # ------------------------------------------------------------------ #
    def promote(self, winner: FitnessReport, baseline: FitnessReport) -> dict:
        """Record a winning transform in the reusable catalog. This is *pattern
        harvesting* (N2) — a library update — NOT a neural knowledge-transfer step."""
        entry = {
            "transform": winner.origin,
            "latency_before_ms": round(baseline.latency_ms, 4),
            "latency_after_ms": round(winner.latency_ms, 4),
            "gain_pct": round(100.0 * (1.0 - winner.latency_ms / baseline.latency_ms), 2)
            if baseline.latency_ms > 0 else 0.0,
        }
        self.catalog.append(entry)
        return entry

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True, cancel_futures=True)


# --------------------------------------------------------------------------- #
#  Ready-made benchmark targets (origin-labelled catalog transforms optimise them)
# --------------------------------------------------------------------------- #
# (a) An over-iterated Newton sqrt — optimised by the ``perturb_int`` transform
#     (shrinking the loop bound while staying correct).
DEMO_SLOW_SQRT = '''
def solve(x):
    guess = x if x > 1 else 1.0
    for _ in range(2000):
        guess = (guess + x / guess) / 2.0
    return round(guess, 4)
'''
DEMO_SQRT_TESTS = [
    [[4.0], 2.0], [[9.0], 3.0], [[16.0], 4.0], [[144.0], 12.0], [[2.0], 1.4142],
]

# (b) A naive-recursive Fibonacci — optimised by the ``insert_lru_cache``
#     transform (memoisation), the plan's canonical algorithmic example.
DEMO_SLOW_FIB = '''
def solve(n):
    if n < 2:
        return n
    return solve(n - 1) + solve(n - 2)
'''
DEMO_FIB_TESTS = [[[20], 6765], [[24], 46368], [[26], 121393]]
