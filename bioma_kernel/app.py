"""
app.py — demonstration of the B.I.O.M.A. Rust kernel.

Shows (1) the lock-free Hormonal Bus (bitwise-flag hormones + f32 concentration,
subscription, temporal dissipation) with a real hot-path microbenchmark, and
(2) autonomous memory apoptosis shrinking a context window.

Build + run:
    cd bioma_kernel
    pip install .            # compiles the Rust extension via maturin
    python app.py
"""

import time

import bioma_kernel as bk

# ----- Hormone signal flags (bitwise) -------------------------------------- #
CORTISOL = 1 << 0     # stress
DOPAMINE = 1 << 1     # reward
ADRENALINE = 1 << 2   # urgency
GENERAL = 0           # untagged / noise


def hormonal_bus_demo() -> None:
    print("=" * 68)
    print(" HORMONAL BUS ".center(68, "="))
    print("=" * 68)
    bus = bk.HormonalBus(num_signals=32)

    # Inject signals: a stressful+urgent pulse, and a reward pulse.
    bus.secrete(CORTISOL | ADRENALINE, 0.8)
    bus.secrete(DOPAMINE, 0.5)
    print(f"  stress+urgency gradient  : {bus.sense(CORTISOL | ADRENALINE):.3f}")
    print(f"  dopamine concentration   : {bus.concentration(1):.3f}")

    # An agent subscribes to the cortisol gradient.
    sub = bus.subscribe(CORTISOL, threshold=0.5)
    print(f"  cortisol subscription    : fired at {bus.poll(sub)}")

    # Temporal dissipation (hormones decay each tick).
    for _ in range(5):
        bus.tick(0.9)
    print(f"  cortisol after 5 ticks   : {bus.concentration(0):.4f}")
    print(f"  buffered events (drain)  : {len(bus.drain_events(100))}")
    print(f"  stats                    : {bus.stats()}")

    # ---- hot-path microbenchmark (secrete + sense) ---- #
    N = 500_000
    t0 = time.perf_counter_ns()
    for _ in range(N):
        bus.secrete(DOPAMINE, 0.001)
        bus.sense(DOPAMINE)
    ns_per_op = (time.perf_counter_ns() - t0) / N
    print(f"  HOT-PATH LATENCY         : {ns_per_op:.1f} ns/op  "
          f"({ns_per_op/1000:.3f} µs) for secrete+sense over {N:,} ops")


def memory_apoptosis_demo() -> None:
    print("\n" + "=" * 68)
    print(" MEMORY APOPTOSIS ".center(68, "="))
    print("=" * 68)
    ctx = bk.StateContext(epsilon=0.05)

    # A durable, relevant system message (high oxygen, cortisol-tagged so it is
    # reinforced) + a pile of low-oxygen noise (old chit-chat, verbose logs).
    ctx.insert("SYSTEM: You are B.I.O.M.A., a precise engineering assistant.",
               oxygen=8.0, signal=CORTISOL)
    ctx.insert("user: (off-topic chit-chat from 20 turns ago)", oxygen=1.0, signal=GENERAL)
    for i in range(30):
        ctx.insert(f"verbose tool log line {i} with lots of low-value detail",
                   oxygen=0.7, signal=GENERAL)

    print(f"  before decay : {len(ctx)} items, {ctx.active_tokens()} tokens")
    for cycle in range(6):
        purged = ctx.decay(rate=0.25, reinforce_mask=CORTISOL, reinforce_amount=0.2)
        print(f"    cycle {cycle}: apoptosed {purged:>2}  → alive {len(ctx):>2}")

    print(f"  after decay  : {len(ctx)} items, {ctx.active_tokens()} tokens")
    print(f"  CONTEXT REDUCTION : {ctx.reduction_ratio() * 100:.1f}%  "
          f"(cognitive noise auto-purged from the LLM window)")
    print("  surviving context:")
    for line in ctx.active_context():
        print(f"     • {line}")
    print(f"  stats : {ctx.stats()}")


if __name__ == "__main__":
    hormonal_bus_demo()
    memory_apoptosis_demo()
