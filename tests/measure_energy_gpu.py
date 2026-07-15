#!/usr/bin/env python3
"""
tests/measure_energy_gpu.py — datacenter-GPU energy bench (READY TO RUN).

The honest counterpart to tests/test_energy_local.py: that one measured joules on
a laptop CPU; this one measures them on an NVIDIA GPU, where production inference
actually runs. It is written to run UNCHANGED on a GPU box — it just needs the
hardware. On a machine without an NVIDIA GPU it detects that and exits cleanly
(no fabricated numbers).

Method (identical shape to the CPU bench, so results are comparable):
  * a real local model served on the GPU (Ollama with CUDA, or any OpenAI-compatible
    local endpoint), baseline (full context) vs BIOMA (dehydrated), interleaved;
  * per-dispatch marginal energy = ∫(power - idle) dt, sampled from the GPU's own
    power sensor via pynvml (NVML) or `nvidia-smi --query-gpu=power.draw`;
  * quality re-checked with the same objective probes.

    python tests/measure_energy_gpu.py                       # auto-detect GPU + endpoint
    python tests/measure_energy_gpu.py --endpoint http://localhost:11434 --model llama3.3:70b
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
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
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

import bioma_micro as kernel  # noqa: E402

SYSTEM_MSG = "You are a precise operations copilot. Answer with the exact requested values."
PROBES = ["2026-07-18", "350", "INC-7743"]
QUERY = ("From the pinned facts only: (1) deploy-freeze end date? (2) API rate limit "
         "per minute? (3) open incident code? Reply with the three exact values.")
_ROLE_SIG = {"system": kernel.SYSTEM, "user": kernel.USER, "assistant": kernel.ASSISTANT,
             "tool": kernel.TOOL, "fact": kernel.FACT}


# --------------------------------------------------------------------------- #
#  GPU power sampling — NVML (pynvml) preferred, nvidia-smi fallback
# --------------------------------------------------------------------------- #
def detect_gpu() -> tuple[str, object]:
    """Returns (backend, handle-or-None). backend in {'nvml','smi','none'}."""
    try:
        import pynvml
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        return "nvml", h
    except Exception:
        pass
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=power.draw",
                                  "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=10)
            if out.returncode == 0 and out.stdout.strip():
                return "smi", None
        except Exception:
            pass
    return "none", None


class GpuSampler:
    def __init__(self, backend: str, handle) -> None:
        self.backend, self.handle = backend, handle
        self.samples: list[tuple[float, float]] = []  # (t, watts)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _read_w(self) -> float:
        if self.backend == "nvml":
            import pynvml
            return pynvml.nvmlDeviceGetPowerUsage(self.handle) / 1000.0  # mW → W
        out = subprocess.run(["nvidia-smi", "--query-gpu=power.draw",
                              "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5)
        return float(out.stdout.strip().splitlines()[0])

    def start(self) -> None:
        def loop():
            while not self._stop.is_set():
                try:
                    self.samples.append((time.perf_counter(), self._read_w()))
                except Exception:
                    pass
                time.sleep(0.05)  # 20 Hz — GPU sensors update fast
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def energy_j(self, t0: float, t1: float, idle_w: float) -> tuple[float, float]:
        pts = [(t, w) for (t, w) in self.samples if t0 <= t <= t1]
        if len(pts) < 2:
            return 0.0, 0.0
        j = sum(((wa + wb) / 2.0) * (tb - ta)
                for (ta, wa), (tb, wb) in zip(pts, pts[1:]))
        dur = pts[-1][0] - pts[0][0]
        return max(0.0, j - idle_w * dur), (j / dur if dur else 0.0)


# --------------------------------------------------------------------------- #
def build_history(rounds: int = 15) -> list[dict]:
    h = [{"role": "system", "content": SYSTEM_MSG},
         {"role": "fact", "content": "FACT: the deploy freeze ends on 2026-07-18."},
         {"role": "fact", "content": "FACT: the API rate limit is 350 requests per minute."},
         {"role": "fact", "content": "FACT: the open incident code is INC-7743."}]
    for i in range(1, rounds + 1):
        noise = (f"conn=ok src=10.0.{i % 254}.{(i * 7) % 254} dst=443 bytes=1240 flags=ACK,PSH "
                 "seq=... ttl=64 proto=TCP verdict=allow rule=default ... ") * 10
        h += [{"role": "tool", "content": f"[audit burst {i}] {noise}"},
              {"role": "user", "content": f"Round {i}: any anomaly?"},
              {"role": "assistant", "content": f"Round {i}: nothing above baseline."}]
    return h


def dehydrate(history: list[dict]) -> str:
    msgs = [(str(m.get("content", "")), _ROLE_SIG.get(m.get("role", "user"), kernel.USER))
            for m in history]
    return "\n".join(kernel.dehydrate(msgs, half_life=6.0, safe_threshold=0.35)["kept"])


def ollama_gen(endpoint: str, model: str, prompt: str) -> dict:
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"num_ctx": 16384, "num_predict": 256,
                                   "temperature": 0.0, "seed": 7}}).encode()
    req = urllib.request.Request(f"{endpoint}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(r.read().decode())


def probe_score(text: str) -> float:
    low = (text or "").lower()
    return sum(1 for p in PROBES if p.lower() in low) / len(PROBES)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default=os.environ.get("BIOMA_LOCAL_ENDPOINT", "http://localhost:11434"))
    ap.add_argument("--model", default="llama3.3:70b")
    ap.add_argument("--trials", type=int, default=3)
    args = ap.parse_args()

    print("=" * 96)
    print("  B.I.O.M.A. — Datacenter-GPU Energy Bench (ready to run)")
    print("=" * 96)
    backend, handle = detect_gpu()
    if backend == "none":
        print("\n  ⚠️  NENHUMA GPU NVIDIA detectada nesta máquina.")
        print("     Esta bancada está PRONTA para rodar — execute-a numa caixa com GPU")
        print("     (nvidia-smi disponível ou `pip install nvidia-ml-py`) servindo um modelo")
        print("     local com CUDA. Nenhum número de GPU é fabricado sem o hardware.")
        print("     Referência de CPU já medida: reports/BIOMA_ENERGY_LOCAL.md (−97,4% J).")
        return 0
    print(f"  GPU detectada · backend {backend}\n")

    history = build_history()
    full = "\n".join(str(m.get("content", "")) for m in history)
    lean = dehydrate(history)
    prompts = {"baseline": f"Context:\n{full}\n\n{QUERY}",
               "bioma": f"Context:\n{lean}\n\n{QUERY}"}

    sampler = GpuSampler(backend, handle)
    sampler.start()
    time.sleep(1.0)
    print("  medindo idle da GPU por 10s...")
    t0 = time.perf_counter()
    time.sleep(10.0)
    _, idle_w = sampler.energy_j(t0, time.perf_counter(), 0.0)
    print(f"  idle GPU: {idle_w:.1f} W\n")

    try:
        ollama_gen(args.endpoint, args.model, "warmup")
    except Exception as exc:
        print(f"  endpoint local não respondeu ({exc}). Sirva o modelo e rode de novo.")
        sampler.stop()
        return 3

    rows: dict[str, list[dict]] = {"baseline": [], "bioma": []}
    for trial in range(1, args.trials + 1):
        for arm in ("baseline", "bioma"):
            t0 = time.perf_counter()
            r = ollama_gen(args.endpoint, args.model, prompts[arm])
            t1 = time.perf_counter()
            j, avg_w = sampler.energy_j(t0, t1, idle_w)
            rows[arm].append({"j": j, "avg_w": avg_w, "s": t1 - t0,
                              "q": probe_score(r.get("response", "")),
                              "ptok": r.get("prompt_eval_count", 0)})
            print(f"  t{trial} {arm:8s} | {rows[arm][-1]['ptok']:6} prefill tok | "
                  f"{j:8.1f} J (avg {avg_w:5.1f} W) | probes {rows[arm][-1]['q']*100:.0f}%")
    sampler.stop()

    def med(a, k): return statistics.median(x[k] for x in rows[a])
    jb, jo = med("baseline", "j"), med("bioma", "j")
    print("\n## Energia por dispatch na GPU (medianas)")
    print(f"  baseline {jb:.1f} J → BIOMA {jo:.1f} J  (−{(1-jo/jb)*100:.1f}%)" if jb else "  sem dados")
    print(f"  qualidade: baseline {med('baseline','q')*100:.0f}% → BIOMA {med('bioma','q')*100:.0f}%")
    out = os.path.join(_ROOT, "reports", "energy_gpu_runs.jsonl")
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps({"backend": backend, "model": args.model, "idle_w": idle_w,
                            "rows": rows}) + "\n")
    print(f"\n📄 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
