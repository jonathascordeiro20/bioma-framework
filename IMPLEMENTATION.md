# B.I.O.M.A. — Implementation & Deployment Manual

**🌐 English · [Português](IMPLEMENTATION.pt-BR.md)**

A step-by-step guide to deploy B.I.O.M.A. in an organization — in front of **local
models** and **online provider APIs** (Anthropic, Google, OpenAI and other big techs).

> **Golden rule.** B.I.O.M.A. runs **in-process, locally**. It hardens the *payload*
> (dehydrate + redact + guard) and hands the clean prompt to *your* model — online or
> local. The model never sees the waste or the secrets. Nothing leaves the machine
> un-hardened.

---

## 1. Architecture — where B.I.O.M.A. sits

```
        ┌─────────────────────────── YOUR APPLICATION / AGENT ───────────────────────────┐
        │  chat history + query + secrets in context                                     │
        └───────────────────────────────────┬────────────────────────────────────────────┘
                                             │  (1) raw payload
                                             ▼
        ┌──────────────────────── B.I.O.M.A. — COGNITIVE PERIMETER (local, μs) ───────────┐
        │  saturation_scan → 0x0F alert   ·   context apoptosis (−80%)   ·   secret redact │
        │  ── the payload is dehydrated, flood-checked and secret-free ──                  │
        └───────────────────────────────────┬────────────────────────────────────────────┘
                                             │  (2) clean prompt  (h.prompt / h.system)
                       ┌─────────────────────┼─────────────────────┐
                       ▼                     ▼                     ▼
             ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
             │ ONLINE PROVIDER  │  │ ONLINE PROVIDER  │  │  LOCAL / ON-PREM  │
             │ Anthropic API    │  │ OpenAI · Google  │  │ Llama · vLLM ·    │
             │ (Claude)         │  │ Azure · Bedrock  │  │ Ollama · llama.cpp│
             └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
                      └─────────────────────┼─────────────────────┘
                                            │  (3) response
                                            ▼
                          B.I.O.M.A. redacts secrets from the response too
                                            │
                                            ▼
                                    back to your application
```

**Defense-in-depth placement** — B.I.O.M.A. is the AI-layer that the classic stack lacks:

```
Network / Host   Firewall · WAF · EDR · IDS/IPS · IAM        (already deployed)
Application      input validation · secrets manager           (already deployed)
AI PERIMETER     ▸ B.I.O.M.A.  ← this layer                   (the gap you close)
Model            Anthropic · Google · OpenAI · on-prem
```

---

## 2. How it works — the request lifecycle

1. Your app assembles the usual payload (history + current query; secrets may be present).
2. `fw.shield(history, query)` runs **locally, in microseconds**:
   - **saturation_scan** measures repetition → if it looks like a cognitive-DDoS flood, it
     raises the `0x0F` red alert on the hormonal bus;
   - **context apoptosis** assigns metabolic weight, decays by half-life, and **purges**
     low-value blocks — dehydrating the input by ~80–97%;
   - **secret redaction** scrubs every vault value from the outbound payload.
3. You send `h.prompt` / `h.system` to **any** model (online API or local).
4. On the way back, B.I.O.M.A. redacts secrets from the **response** too (defense in depth).

`h.telemetry` gives you the audit: `saturation`, `red_alert`, `apoptosis_reduction`,
`tokens_before/after`, `secrets_redacted`, `kernel_latency_us`.

---

## 3. Prerequisites & install

```bash
# 1) Rust toolchain (for the kernel build) + maturin
python -m pip install maturin

# 2) Build & install the micro-kernel (PyO3 extension)
cd bioma_micro && maturin build --release
pip install --force-reinstall target/wheels/bioma_micro-*.whl && cd ..

# 3) The Python layer is the `bioma/` package (add the repo root to PYTHONPATH,
#    or `pip install -e .` once you add a pyproject for it)
```

No API key is required for the hardening itself — apoptosis, saturation and redaction run
fully offline. Keys are only your model provider's, used by *your* SDK.

---

## 4. Integration patterns

### A. Online provider — the pure `shield()` pattern (recommended)

Harden locally, then call the provider's SDK yourself. Works with **any** vendor.

```python
from bioma.firewall_client import CognitiveFirewall

fw = CognitiveFirewall(vault={"db_password": DB_PW, "api_key": INTERNAL_KEY})

h = fw.shield(history, "refactor this module")   # local, μs — dehydrated + redacted
# h.prompt, h.system are clean; h.telemetry has the audit
```

**OpenAI (or Azure OpenAI):**
```python
from openai import OpenAI
r = OpenAI().chat.completions.create(
    model="gpt-5.5",
    messages=([{"role":"system","content":h.system}] if h.system else []) +
             [{"role":"user","content":h.prompt}])
```

**Anthropic (Claude):**
```python
import anthropic
r = anthropic.Anthropic().messages.create(
    model="claude-sonnet-5", max_tokens=1024,
    system=h.system or "", messages=[{"role":"user","content":h.prompt}])
```

**Google (Gemini):**
```python
from google import genai
r = genai.Client().models.generate_content(
    model="gemini-3.1-pro", contents=(h.system+"\n\n" if h.system else "")+h.prompt)
```

**AWS Bedrock / Vertex / any OpenAI-compatible gateway:** same idea — send `h.prompt`.

> Redact the response too: `safe = fw._redact(r_text)[0]` (or use pattern **B**, which
> does it automatically).

### B. Bring-your-own async dispatcher — keep the guards automatically

Wrap *any* async provider call; you get the **timeout guard** and **response redaction**
for free.

```python
async def call_claude(prompt, system):
    msg = await anthropic.AsyncAnthropic().messages.create(
        model="claude-sonnet-5", max_tokens=1024, system=system or "",
        messages=[{"role":"user","content":prompt}])
    return msg.content[0].text

shield = await fw.harden(history, "refactor", dispatch_fn=call_claude)
# shield.answer (secret-redacted), shield.timed_out, shield.apoptosis_reduction, ...
```

### C. Local / on-prem model (air-gapped)

Same `shield()`; the dispatcher is your local runtime. No network at all.

```python
# Ollama
import ollama
h = fw.shield(history, query)
out = ollama.chat(model="llama3.3", messages=[{"role":"user","content":h.prompt}])

# vLLM / llama.cpp (OpenAI-compatible server)
from openai import OpenAI
local = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="local")
r = local.chat.completions.create(model="local-model",
        messages=[{"role":"user","content":h.prompt}])
```

The efficiency and security gains are **identical** to the online case — B.I.O.M.A. acts on
the payload, not the model.

### D. As a local sidecar service (language-agnostic)

Run the bundled FastAPI service so non-Python apps can call B.I.O.M.A. over localhost.

```bash
uvicorn bioma.server:app --host 127.0.0.1 --port 8900
#   GET  /health        → liveness + kernel version
#   POST /v1/dispatch   → {history, query, model} → hardened dispatch (+ apoptosis audit)
```

Any service (Node, Go, Java) posts its payload to `http://127.0.0.1:8900/v1/dispatch`.

---

## 5. Configuration

```python
CognitiveFirewall(
    vault={"name": "SECRET_VALUE", ...},   # values scrubbed from outbound + response
    saturation_threshold=0.85,             # ≥ this → 0x0F red alert (cognitive-DDoS)
    dispatch_timeout=20.0,                 # seconds; bounds any call (pattern B)
    half_life=6.0,                         # apoptosis aggressiveness (lower = more pruning)
    safe_threshold=0.35,                   # oxygen floor below which a block is purged
)
```

- **Durable classes never purge:** `SYSTEM` and `FACT` blocks are reinforced.
- Tag history items by role (`system`/`user`/`assistant`/`tool`/`fact`) so the kernel
  assigns the right metabolic weight (verbose `tool` logs are the prime apoptosis target).

---

## 6. Defense-in-depth — how it works and its measured impact

| Threat | Mechanism | How it protects | Measured impact |
| :--- | :--- | :--- | :--- |
| **Secret exfiltration** (prompt injection) | Secret redaction | Vault values are scrubbed from the outbound payload **and** the response → the model never receives them, so an injection has nothing to exfiltrate | **0 leaked** on all 6 frontier models (baseline leaks; B.I.O.M.A. does not) |
| **Cognitive DDoS** (flood / context exhaustion) | saturation_scan → `0x0F` → apoptosis | Repetitive floods are detected and dehydrated before dispatch, so the context window is never exhausted | flood **32,317 → 13 tokens**, saturation 0.999, in **0.6μs** |
| **Loop / hang injection** | timeout guard | Every dispatch is bounded by a deadline; a loop cannot stall the pipeline | **contained** (bounded dispatch) |
| **Cost blow-up** | context apoptosis | The bloated input is dehydrated on every call | **−80% to −97%** input tokens |

**Honest scope.** B.I.O.M.A. is **one layer** of defense-in-depth. It does **not** replace
network/host controls (firewall, EDR, IAM), does not scan for vulnerabilities, and does not
grant "immunity." It hardens the **LLM I/O boundary** — declared secrets and repetitive
floods — and bounds latency. See [`FINDINGS.md`](FINDINGS.md) for the full, honest
evaluation (including what we refuted).

---

## 7. Deployment topologies

| Topology | When | How |
| :--- | :--- | :--- |
| **Embedded library** | Python apps/agents | `import bioma.firewall_client`; call `shield()`/`harden()` inline |
| **Local sidecar** | polyglot stacks, microservices | run `bioma.server` on localhost; POST payloads to it |
| **Air-gapped / on-prem** | classified / regulated | library + a local model; apoptosis + firewall run offline, no network |

---

## 8. Validate & monitor

```bash
# unit suite (offline, deterministic)
python -m pytest tests/test_kernel.py tests/test_firewall.py tests/test_server.py -q

# real efficiency + security + universal-gains validations (needs a provider key)
python tests/test_enxuto_efficiency.py
python tests/test_sovereign_defense.py       # writes reports/BIOMA_IMMUNITY_VERDICT.md
python tests/test_universal_integration.py   # writes reports/BIOMA_UNIVERSAL_GAINS.md
```

Feed `h.telemetry` (reduction %, saturation, red_alert, kernel μs, secrets_redacted) into
your observability stack to track savings and alerts per request.

---

## 9. Rollout checklist

- [ ] `bioma_micro` built and imported in the target environment.
- [ ] `vault` populated with every secret that must never reach a model.
- [ ] Integration pattern chosen (A pure / B dispatcher / C local / D sidecar).
- [ ] `saturation_threshold` and `half_life` tuned to your workload.
- [ ] Response-side redaction in place (pattern B does it; pattern A: call `_redact`).
- [ ] Telemetry wired to observability; unit tests green in CI.
- [ ] For air-gapped: confirmed apoptosis + firewall run with no network/key.
