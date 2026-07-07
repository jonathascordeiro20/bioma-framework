"""
stress_benchmark.py — market-grade stress report for the B.I.O.M.A. kernel.

Spins up 5,000 concurrent Rust micro-agents flooding the Hormonal Bus for 30s,
forcing Memory Apoptosis under load, and prints the benchmark report we'd ship to
market: average communication latency (µs) and the volume of context saved by
apoptosis.  A separate Python thread polls `obter_estado_sistema_nervoso()` live
during the run (possible because `run()` releases the GIL) — the same feed a
React/D3 dashboard would consume.

Run:  python stress_benchmark.py
"""

import threading
import time

import bioma_kernel as bk

AGENTS = 5_000
DURATION_S = 30.0
SIGNALS = 16


def live_feed(tester: "bk.StressTester", stop: threading.Event) -> None:
    """Poll the nervous-system snapshot ~every 3s while the flood runs."""
    while not stop.is_set():
        st = tester.obter_estado_sistema_nervoso()
        print(f"   · agentes={st['agentes_ativos']:>5}  "
              f"sinais={int(st['sinais_processados']):>12,}  "
              f"lat={st['latencia_comunicacao_us']:.3f}µs  "
              f"densidade={st['densidade_hormonal']:.1f}  "
              f"tokens_salvos={int(st['tokens_salvos_apoptose']):>10,}")
        stop.wait(3.0)


def main() -> None:
    tester = bk.StressTester(num_signals=SIGNALS, max_agents=AGENTS)

    print("=" * 72)
    print(f" B.I.O.M.A. STRESS BENCHMARK · {AGENTS:,} agentes × {DURATION_S:.0f}s ".center(72, "="))
    print("=" * 72)
    print("  telemetria ao vivo (feed do dashboard):")

    stop = threading.Event()
    monitor = threading.Thread(target=live_feed, args=(tester, stop), daemon=True)
    monitor.start()

    t0 = time.perf_counter()
    m = tester.run(num_agents=AGENTS, duration_secs=DURATION_S)   # releases the GIL
    wall = time.perf_counter() - t0
    stop.set()
    monitor.join(timeout=1.0)

    st = tester.obter_estado_sistema_nervoso()
    sinais = m["sinais_processados"]

    print("\n" + "=" * 72)
    print(" RELATÓRIO DE BENCHMARK (mercado) ".center(72, "="))
    print("=" * 72)
    print(f"  Agentes concorrentes ............ {int(m['agentes_ativos']):,}")
    print(f"  Duração real .................... {wall:.1f} s")
    print(f"  Sinais hormonais processados .... {int(sinais):,}")
    print(f"  Throughput ...................... {sinais / wall / 1e6:.2f} M sinais/s")
    print(f"  LATÊNCIA média de comunicação ... {m['latencia_comunicacao_us']:.3f} µs")
    print(f"     p99 / máx .................... {m['latencia_p99_us']:.3f} / {m['latencia_max_us']:.3f} µs")
    print(f"  Eventos de apoptose ............. {int(m['apoptosis_events']):,}")
    print(f"  TOKENS salvos por apoptose ...... {int(m['tokens_salvos_apoptose']):,}")
    print(f"  Densidade hormonal final ........ {m['densidade_hormonal']:.2f}")
    print("=" * 72)
    print(f"  amostra do grafo (nó, brilho) ... "
          f"{[(n['id'], round(n['brilho'], 2)) for n in st['nos'][:6]]}")
    print(f"  canais hormonais (concentração) . "
          f"{[round(c, 1) for c in st['concentracao_por_sinal'][:8]]} ...")
    print("=" * 72)


if __name__ == "__main__":
    main()
