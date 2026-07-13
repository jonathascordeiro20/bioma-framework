# B.I.O.M.A.

**A local, provider-agnostic efficiency & security micro-kernel for LLM applications.**

B.I.O.M.A. is a drop-in artifact — a lock-free Rust kernel (`bioma_micro`) plus a
thin Python layer — that you embed in *any* project or architecture that talks to an
LLM. It does not try to make the model "smarter". It makes the *processing* cheaper,
faster and safer, in-process, before your prompt ever leaves the machine:

- **Context apoptosis** — dehydrates wasted/stale context (−80% input tokens; up to
  −97% on long sessions).
- **Cognitive firewall** — secret redaction, cognitive-DDoS/flood detection, and a
  dispatch timeout guard.
- **Hormonal bus** — lock-free μs signalling substrate (~2M signals/s).

100% local. Provider-agnostic: harden the payload here, then send it to **Anthropic,
Google, OpenAI** — or anything — with *your* SDK.

> **New here?** [`OVERVIEW.md`](OVERVIEW.md) explains what B.I.O.M.A. is, the pain it
> attacks, and the real benchmarks as proof. Every claim is measured and audited in
> [`FINDINGS.md`](FINDINGS.md), including what we tested and **refuted** (multi-LLM
> "mitosis" does not improve quality — it is not part of the product).

## Use it as a library (any provider)

```python
from bioma.firewall_client import CognitiveFirewall

fw = CognitiveFirewall(vault={"db_password": DB_PW})   # secrets to protect

# (a) PURE artifact — harden, then call YOUR provider with YOUR SDK:
h = fw.shield(history, "refactor this function")
#   h.prompt / h.system  → clean, dehydrated, secret-free payload
#   h.telemetry          → saturation, red_alert, apoptosis_reduction, kernel_latency_us

import anthropic                                        # or google.genai, or openai
msg = anthropic.Anthropic().messages.create(
    model="claude-sonnet-5", max_tokens=1024,
    system=h.system or "", messages=[{"role": "user", "content": h.prompt}])

# (b) Bring your own async dispatcher (Anthropic/Google/OpenAI), keep the guards:
shield = await fw.harden(history, "refactor", dispatch_fn=my_async_provider_call)
#   → timeout guard + response-side secret redaction applied automatically
```

The Rust kernel is usable directly too:

```python
import bioma_micro as k
k.dehydrate([("system rules", k.SYSTEM), ("verbose log " * 200, k.TOOL)])  # → -80% tokens
k.saturation_scan(payload)     # cognitive-DDoS score 0..1 (flood ≈ 1.0)
```

## Proven results (ground truth)

| Capability | Result | Source |
|---|---|---|
| Context apoptosis | **−80% input tokens** (up to −97% long sessions) | `tests/test_enxuto_efficiency.py` |
| Hormonal bus | **~2M signals/s @ ~5μs**, bounded under 10× load | `bioma_kernel_loadtest.py` |
| Cognitive-DDoS mitigation | 15k-token flood → dehydrated pre-dispatch | `tests/test_sovereign_defense.py` |
| Secret redaction | vault values never reach the model | `reports/BIOMA_IMMUNITY_VERDICT.md` |

## Quickstart (local)

```bash
# Build & install the Rust micro-kernel (PyO3 extension)
python -m pip install maturin
cd bioma_micro && maturin build --release && \
  pip install --force-reinstall target/wheels/bioma_micro-*.whl && cd ..

# Run the test suite (offline, deterministic)
pip install pytest fastapi "openai>=1"
python -m pytest tests/test_kernel.py tests/test_firewall.py tests/test_server.py -q
```

Optional: a local FastAPI runner (`bioma.server`, `GET /health` + `POST /v1/dispatch`)
and a local container image (`deploy/Dockerfile.lean`) are included — no hosted
service required.

## Layout

```
bioma_micro/   Rust/PyO3 micro-kernel — hormonal bus + apoptosis + saturation_scan
bioma/         Python: CognitiveFirewall, LeanOpenRouterClient, local server
tests/         unit suite (kernel, firewall, server) + real end-to-end validations
FINDINGS.md    ground-truth evaluation (proven / refuted), reproducible
reports/       immunity verdict (APT war-game)
```

> Legacy layers (`bioma_orchestrator/`, `bioma_kernel/`) remain only to reproduce
> `FINDINGS.md`; `bioma_micro` + `bioma` are the product.

## License

MIT.
