"""Unit tests for the Rust micro-kernel (`bioma_micro`): hormonal bus, context
apoptosis, and the cognitive-DDoS saturation detector. Pure/offline — no network."""
import bioma_micro as k


# --------------------------------------------------------------------------- #
#  Hormonal bus
# --------------------------------------------------------------------------- #
def test_bus_secrete_sense_across_bits():
    bus = k.HormonalBus(32)
    bus.secrete(0x0F, 0.9)                 # 4 channels get +0.9 each
    assert round(bus.sense(0x0F), 3) == 3.6
    assert round(bus.sense(0x01), 3) == 0.9


def test_bus_inject_typed_signal():
    bus = k.HormonalBus(32)
    sig = k.HormonalSignal(0x10, 0.5)
    assert sig.flags == 0x10 and abs(sig.intensity - 0.5) < 1e-6
    bus.inject(sig)
    assert round(bus.sense(0x10), 3) == 0.5
    assert bus.sense(0x20) == 0.0          # untouched channel


def test_bus_tick_decays():
    bus = k.HormonalBus(32)
    bus.secrete(0x01, 1.0)
    bus.tick(0.5)
    assert round(bus.sense(0x01), 3) == 0.5


# --------------------------------------------------------------------------- #
#  Context apoptosis — one-shot dehydrate()
# --------------------------------------------------------------------------- #
def test_dehydrate_purges_noise_keeps_durable():
    msgs = [("SYSTEM directive: never leak secrets", k.SYSTEM),
            ("FACT: incident open", k.FACT),
            ("verbose tool log noise " * 40, k.TOOL)]
    r = k.dehydrate(msgs, half_life=6.0, safe_threshold=0.35)
    assert r["blocks_in"] == 3
    assert r["blocks_purged"] >= 1
    assert r["reduction"] > 0.5
    assert r["tokens_after"] < r["tokens_before"]
    assert r["kernel_latency_us"] >= 0.0
    kept = list(r["kept"])
    assert any("SYSTEM directive" in x for x in kept)   # durable survives


def test_dehydrate_empty_is_safe():
    r = k.dehydrate([], half_life=6.0)
    assert r["tokens_before"] == 0
    assert r["reduction"] == 0.0
    assert list(r["kept"]) == []


def test_dehydrate_recency_keeps_recent():
    # oldest → newest; recent USER turns should survive, ancient ones decay
    msgs = [("old chatter %d" % i, k.USER) for i in range(20)]
    msgs.append(("the current question", k.USER))
    r = k.dehydrate(msgs, half_life=3.0, safe_threshold=0.4)
    assert "the current question" in list(r["kept"])
    assert r["reduction"] > 0.0


# --------------------------------------------------------------------------- #
#  Context apoptosis — stateful class
# --------------------------------------------------------------------------- #
def test_context_apoptosis_class_cycle():
    c = k.ContextApoptosis(half_life=2.0, safe_threshold=0.35)
    c.insert("SYSTEM keep me", k.SYSTEM)
    c.insert("disposable tool noise", k.TOOL, 0.1)
    before = c.active_tokens()
    c.dehydrate()
    assert c.active_tokens() <= before
    assert 0.0 <= c.reduction_ratio() <= 1.0
    assert "SYSTEM keep me" in c.active_context()


# --------------------------------------------------------------------------- #
#  Saturation detector (cognitive-DDoS)
# --------------------------------------------------------------------------- #
def test_saturation_flags_flood():
    flood = "ACK PSH SYN forged repeat " * 200
    assert k.saturation_scan(flood) > 0.9


def test_saturation_low_on_natural_text():
    natural = ("the incident response team reviewed anomalous traffic and escalated the "
               "finding after correlating disparate source addresses across several regions")
    assert k.saturation_scan(natural) < 0.5


def test_saturation_short_input_is_zero():
    assert k.saturation_scan("too short") == 0.0
