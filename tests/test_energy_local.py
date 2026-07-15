#!/usr/bin/env python3
"""
tests/test_energy_local.py — DIRECT energy/compute measurement, baseline vs apoptosis.

Closes the honest gap in the sustainability analysis: the online tests measured
tokens and cost; energy was inferred. This bench measures, on a REAL local model
(Ollama), the compute that apoptosis removes — and, when the laptop runs on
battery, converts it into measured joules per dispatch.

Two measurement layers:
  1. ALWAYS (AC or battery): Ollama's native per-dispatch counters —
     `prompt_eval_count` (prefill tokens) and `prompt_eval_duration` (prefill
     wall time on this CPU). Hardware-level ground truth of the compute removed.
  2. ON BATTERY ONLY: whole-system power from the battery fuel gauge
     (ROOT\\wmi BatteryStatus.DischargeRate, mW, sampled at 2 Hz by a PowerShell
     child process). Reports marginal energy per dispatch = ∫(draw − idle) dt,
     with the idle baseline measured immediately before the trials.

Quality is re-checked with the same objective probes as the online test.

    python tests/test_energy_local.py                 # 3 interleaved trials
    python tests/test_energy_local.py --trials 5 --model llama3.2:1b
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import statistics
import subprocess
import sys
import threading
import time
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import bioma_micro as kernel  # noqa: E402

OLLAMA = "http://localhost:11434"
SYSTEM_MSG = "You are a precise operations copilot. Answer with the exact requested values."
PROBES = ["2026-07-18", "350", "INC-7743"]
QUERY = ("From the pinned facts only: (1) on which date does the deploy freeze end? "
         "(2) what is the API rate limit per minute? (3) which incident code is open? "
         "Reply with the three exact values.")

_ROLE_SIG = {"system": kernel.SYSTEM, "user": kernel.USER, "assistant": kernel.ASSISTANT,
             "tool": kernel.TOOL, "fact": kernel.FACT}


def build_history(rounds: int = 15) -> list[dict]:
    h = [
        {"role": "system", "content": SYSTEM_MSG},
        {"role": "fact", "content": "FACT: the deploy freeze ends on 2026-07-18."},
        {"role": "fact", "content": "FACT: the API rate limit is 350 requests per minute."},
        {"role": "fact", "content": "FACT: the open incident code is INC-7743."},
    ]
    for i in range(1, rounds + 1):
        noise = (f"conn=ok src=10.0.{i % 254}.{(i * 7) % 254} dst=443 bytes=1240 flags=ACK,PSH "
                 "seq=... ack=... win=... ttl=64 proto=TCP verdict=allow rule=default ... ") * 10
        h += [
            {"role": "tool", "content": f"[audit burst {i}] {noise}"},
            {"role": "user", "content": f"Round {i}: any anomaly in the last burst?"},
            {"role": "assistant", "content": f"Round {i}: nothing above baseline; continuing to monitor."},
        ]
    return h


def render(history: list[dict]) -> str:
    return "\n".join(str(m.get("content", "")) for m in history)


def dehydrate(history: list[dict]) -> tuple[str, dict]:
    msgs = [(str(m.get("content", "")), _ROLE_SIG.get(m.get("role", "user"), kernel.USER))
            for m in history]
    audit = kernel.dehydrate(msgs, half_life=6.0, safe_threshold=0.35)
    return "\n".join(audit["kept"]), audit


def ollama_generate(model: str, prompt: str, num_ctx: int = 16384) -> dict:
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "options": {"num_ctx": num_ctx, "num_predict": 256, "temperature": 0.0, "seed": 7},
    }).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(r.read().decode())


# --------------------------------------------------------------------------- #
#  Battery power sampler (whole-system, no admin required, battery mode only)
# --------------------------------------------------------------------------- #
_PS_SAMPLER = r"""
while ($true) {
  $b = Get-CimInstance -Namespace root\wmi -ClassName BatteryStatus -ErrorAction SilentlyContinue
  if ($b) { Write-Output ("{0},{1},{2}" -f [DateTimeOffset]::Now.ToUnixTimeMilliseconds(),
            [int]$b.DischargeRate, [bool]$b.PowerOnline) }
  Start-Sleep -Milliseconds 500
}
"""


class PowerSampler:
    """Streams (t_ms, mW, on_ac) samples from the battery fuel gauge."""

    def __init__(self) -> None:
        self.samples: list[tuple[float, float, bool]] = []
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", _PS_SAMPLER],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            try:
                t, mw, on_ac = line.strip().split(",")
                self.samples.append((float(t) / 1000.0, float(mw), on_ac == "True"))
            except ValueError:
                continue

    def stop(self) -> None:
        if self._proc:
            self._proc.kill()

    def energy_j(self, t0: float, t1: float, idle_w: float = 0.0) -> tuple[float, float, int]:
        """Trapezoidal ∫(draw − idle)dt over [t0, t1] → (marginal_J, avg_W, n_samples)."""
        pts = [(t, mw / 1000.0) for (t, mw, _ac) in self.samples if t0 <= t <= t1]
        if len(pts) < 2:
            return (0.0, 0.0, len(pts))
        j = 0.0
        for (ta, wa), (tb, wb) in zip(pts, pts[1:]):
            j += ((wa + wb) / 2.0) * (tb - ta)
        dur = pts[-1][0] - pts[0][0]
        avg_w = j / dur if dur > 0 else 0.0
        return (max(0.0, j - idle_w * dur), avg_w, len(pts))

    def on_battery(self) -> bool:
        recent = self.samples[-3:]
        return bool(recent) and all((not ac) and mw > 0 for (_t, mw, ac) in recent)


def probe_score(text: str) -> float:
    low = (text or "").lower()
    return sum(1 for p in PROBES if p.lower() in low) / len(PROBES)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="llama3.2:1b")
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--rounds", type=int, default=15)
    args = ap.parse_args()

    history = build_history(args.rounds)
    full = render(history)
    lean, audit = dehydrate(history)
    prompts = {
        "baseline": f"Context:\n{full}\n\nCurrent request:\n{QUERY}",
        "bioma": f"Context:\n{lean}\n\nCurrent request:\n{QUERY}",
    }

    print("=" * 96)
    print("  B.I.O.M.A. — Local Energy/Compute Bench (Ollama, hardware ground truth)")
    print("=" * 96)
    print(f"  model: {args.model} · trials: {args.trials}/arm (interleaved) · CPU: local")
    print(f"  apoptose: {audit['tokens_before']:,} → {audit['tokens_after']:,} tok estimados "
          f"(−{audit['reduction']*100:.1f}%) · kernel {audit['kernel_latency_us']:.1f}μs\n")

    sampler = PowerSampler()
    sampler.start()
    time.sleep(2.0)
    battery = sampler.on_battery()
    idle_w = 0.0
    if battery:
        print("  🔋 na bateria — medindo baseline de idle por 15s (não use a máquina)...")
        t0 = time.time()
        time.sleep(15.0)
        _, idle_w, n = sampler.energy_j(t0, time.time())
        print(f"  idle: {idle_w:.2f} W ({n} amostras)\n")
    else:
        print("  🔌 na tomada — fuel gauge lê 0 mW; medindo APENAS compute (prefill).")
        print("     Para a passada de energia: desconecte o carregador e rode de novo.\n")

    print("  aquecendo o modelo...")
    ollama_generate(args.model, "warmup: reply OK", num_ctx=2048)

    rows: dict[str, list[dict]] = {"baseline": [], "bioma": []}
    try:
        for trial in range(1, args.trials + 1):
            for arm in ("baseline", "bioma"):
                t0 = time.time()
                r = ollama_generate(args.model, prompts[arm])
                t1 = time.time()
                marginal_j, avg_w, _ = sampler.energy_j(t0, t1, idle_w) if battery else (0.0, 0.0, 0)
                row = {
                    "prefill_tok": r.get("prompt_eval_count", 0),
                    "prefill_s": r.get("prompt_eval_duration", 0) / 1e9,
                    "decode_tok": r.get("eval_count", 0),
                    "total_s": r.get("total_duration", 0) / 1e9,
                    "wall_s": t1 - t0,
                    "marginal_j": marginal_j,
                    "avg_w": avg_w,
                    "quality": probe_score(r.get("response", "")),
                }
                rows[arm].append(row)
                ej = f" | {marginal_j:7.1f} J (avg {avg_w:4.1f} W)" if battery else ""
                print(f"  t{trial} {arm:8s} | prefill {row['prefill_tok']:6,} tok "
                      f"em {row['prefill_s']:7.2f}s | total {row['total_s']:7.2f}s "
                      f"| probes {row['quality']*100:3.0f}%{ej}")
    finally:
        sampler.stop()

    # ---- report ----------------------------------------------------------- #
    def med(arm: str, k: str) -> float:
        return statistics.median(r[k] for r in rows[arm])

    pf_b, pf_o = med("baseline", "prefill_s"), med("bioma", "prefill_s")
    tk_b, tk_o = med("baseline", "prefill_tok"), med("bioma", "prefill_tok")
    tt_b, tt_o = med("baseline", "total_s"), med("bioma", "total_s")
    q_b, q_o = med("baseline", "quality"), med("bioma", "quality")

    print("\n" + "=" * 96)
    print("## Medição direta — baseline vs B.I.O.M.A. (medianas)\n")
    print("| Métrica (hardware real) | sem BIOMA | com BIOMA | redução |")
    print("| :--- | ---: | ---: | ---: |")
    print(f"| Tokens de prefill (tokenizer do modelo) | {tk_b:,.0f} | {tk_o:,.0f} | −{(1-tk_o/tk_b)*100:.1f}% |")
    print(f"| Tempo de prefill (compute medido) | {pf_b:.2f}s | {pf_o:.2f}s | −{(1-pf_o/pf_b)*100:.1f}% |")
    print(f"| Tempo total do dispatch | {tt_b:.2f}s | {tt_o:.2f}s | −{(1-tt_o/tt_b)*100:.1f}% |")
    if battery:
        ej_b, ej_o = med("baseline", "marginal_j"), med("bioma", "marginal_j")
        red = (1 - ej_o / ej_b) * 100 if ej_b > 0 else 0.0
        print(f"| **Energia marginal por dispatch (fuel gauge)** | **{ej_b:.1f} J** | **{ej_o:.1f} J** | **−{red:.1f}%** |")
    print(f"| Qualidade (probes objetivas) | {q_b*100:.0f}% | {q_o*100:.0f}% | paridade: {'✅' if q_o >= q_b else '❌'} |")
    print(f"\n> Método: Ollama `prompt_eval_*` por dispatch (contadores do runtime); "
          f"{'energia = ∫(draw−idle)dt do fuel gauge da bateria, idle medido antes dos trials' if battery else 'energia requer modo bateria (fuel gauge lê 0 na tomada)'}; "
          f"braços intercalados contra drift térmico; temperatura 0, seed fixa.")
    if not battery:
        print("> ⚠️ Passada de energia pendente: desconecte o carregador e rode novamente.")

    # ---- persist (results must never live only in a terminal) -------------- #
    run = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "model": args.model, "trials": args.trials, "battery": battery,
        "idle_w": round(idle_w, 2), "rows": rows,
        "medians": {
            "prefill_tok": [tk_b, tk_o], "prefill_s": [pf_b, pf_o],
            "total_s": [tt_b, tt_o], "quality": [q_b, q_o],
            **({"marginal_j": [med("baseline", "marginal_j"), med("bioma", "marginal_j")]}
               if battery else {}),
        },
    }
    out = os.path.join(_ROOT, "reports", "energy_local_runs.jsonl")
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(run) + "\n")
    print(f"\n📄 execução registrada em {out}")
    return 0 if q_o >= q_b else 1


if __name__ == "__main__":
    raise SystemExit(main())
