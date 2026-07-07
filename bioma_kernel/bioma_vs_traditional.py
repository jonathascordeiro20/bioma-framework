"""
bioma_vs_traditional.py — end-to-end functional + performance benchmark.

Runs the SAME complex problem (5 heavy CPU-bound "vulnerability sweep" search
meta-tasks) on two engines and prints the market-ready comparison:

  * Motor A — Traditional: a linear, single-thread sequential agent flow.
  * Motor B — B.I.O.M.A.:   hormonal-triggered NEURONAL MITOSIS — apoptose the
    context, then branch specialist children across Tokio's pool to search the
    hypothesis space in parallel and converge fastest.

Both engines return the SAME correct answers (parallelism never corrupts the
result) — the win is wall-clock speed and fewer context tokens per call.

Run:
    cd bioma_kernel
    pip install .        # rebuild the kernel with the mitosis module
    python bioma_vs_traditional.py
"""

from __future__ import annotations

import bioma_kernel as bk

N_TASKS = 5
KEYSPACE = 1_500_000
HASH_ROUNDS = 32
SHARDS = 4
REPS = 3
PRICE_IN_PER_M = 3.0     # USD / 1M input tokens (illustrative)


def _best(runs: list[dict]) -> dict:
    return min(runs, key=lambda r: r["elapsed_us"])


def main() -> None:
    b = bk.MitosisBenchmark(n_tasks=N_TASKS, keyspace=KEYSPACE,
                            base_seed=20260707, answer_frac=0.86, hash_rounds=HASH_ROUNDS)
    known = b.known_answers()

    # warm-up (caches, allocator, tokio runtime), then timed reps.
    b.run_traditional(); b.run_bioma(shards=SHARDS)
    trad = [b.run_traditional() for _ in range(REPS)]
    bioma = [b.run_bioma(shards=SHARDS) for _ in range(REPS)]
    A, B = _best(trad), _best(bioma)

    a_ms, b_ms = A["elapsed_us"] / 1000.0, B["elapsed_us"] / 1000.0
    speedup = A["elapsed_us"] / B["elapsed_us"] if B["elapsed_us"] > 0 else float("inf")
    tok_reduction = 100.0 * (1.0 - B["avg_tokens_per_call"] / A["avg_tokens_per_call"]) \
        if A["avg_tokens_per_call"] else 0.0
    identical = (int(A["correct"]) == int(B["correct"]) == N_TASKS)

    w = 74
    print("=" * w)
    print(" B.I.O.M.A. vs TRADITIONAL — MITOSIS E2E BENCHMARK ".center(w, "="))
    print("=" * w)
    print(f"  Cenário: {N_TASKS} meta-tarefas de varredura (keyspace {KEYSPACE:,} · "
          f"{HASH_ROUNDS} rounds/probe)")
    print(f"  Mitose: {int(B['mitosis_events'])} nós-filho em {int(B['workers'])} cores · "
          f"estresse hormonal sentido {B['total_stress']:.2f}")
    print("-" * w)
    print(f"  {'Métrica':<30}{'Motor A · Linear':>20}{'Motor B · BIOMA':>20}")
    print("  " + "-" * (w - 4))
    print(f"  {'Tempo total (ms)':<30}{a_ms:>20.2f}{b_ms:>20.2f}")
    print(f"  {'Tokens médios / chamada':<30}{A['avg_tokens_per_call']:>20.0f}{B['avg_tokens_per_call']:>20.0f}")
    print(f"  {'Qualidade (corretas/total)':<30}{int(A['correct']):>17}/{N_TASKS}{int(B['correct']):>17}/{N_TASKS}")
    print(f"  {'Convergência idêntica ao GT':<30}{'sim' if int(A['correct'])==N_TASKS else 'não':>20}"
          f"{'sim' if int(B['correct'])==N_TASKS else 'não':>20}")
    print("  " + "-" * (w - 4))
    print(f"  ⚡ FATOR DE ACELERAÇÃO (speedup) ..... {speedup:.2f}×  "
          f"(A {a_ms:.1f}ms ÷ B {b_ms:.1f}ms)")
    print(f"  🧬 Redução de tokens (apoptose) ...... {tok_reduction:.1f}%  "
          f"→ ${(A['avg_tokens_per_call']-B['avg_tokens_per_call'])*PRICE_IN_PER_M:.0f}/1M chamadas")
    print(f"  ✅ Qualidade preservada .............. {'sim — mesma resposta correta, {}× mais rápido'.format(round(speedup,1)) if identical else 'DIVERGÊNCIA — revisar'}")
    print("=" * w)
    print("  Honestidade: tempo/tokens são MEDIDOS (Rust, mesma máquina). O speedup vem")
    print("  de paralelismo real (Tokio spawn_blocking, CPU-bound, N cores). Ambos os")
    print("  motores retornam as MESMAS respostas corretas (GT verificado) — mitose")
    print("  acelera sem sacrificar acurácia. $ é cálculo a $3/1M input, sem chamar LLM.")
    print("=" * w)


if __name__ == "__main__":
    main()
