# B.I.O.M.A.

**A lean efficiency & resilience micro-kernel for LLM infrastructure.**

B.I.O.M.A. does not try to make an LLM "smarter" at everyday text. It makes AI
*processing* viable, sustainable, and resilient: a lock-free Rust hormonal bus and
an autonomous **context-apoptosis** filter that dehydrates wasted context before it
ever reaches the API — cutting input tokens (and cost) on every call.

> Every claim below is measured, reproducible, and audited in
> [`FINDINGS.md`](FINDINGS.md) — including what we tested and **refuted**.

## Proven results (ground truth)

| Capability | Result | Source |
|---|---|---|
| **Context apoptosis** | **−80% input tokens** (universal); up to **−97%** on long, noisy sessions | `tests/test_enxuto_efficiency.py` |
| **Hormonal bus — throughput** | **~2M signals/s** | `bioma_kernel_loadtest.py` |
| **Hormonal bus — latency** | **~5μs mean, bounded under 10× load** (p99 ≤ 27μs) | `bioma_kernel_loadtest.py` |
| Kernel apoptosis latency | **~1.6μs mean / 4μs peak** per round | `tests/test_enxuto_efficiency.py` |

**What we refuted (honestly):** multi-LLM *mitosis + synthesis* does **not** improve
answer quality or security remediation — neutral on frontier models (ceiling),
harmful on weaker ones (synthesis corrupts correct answers), across three
independent ground-truth experiments. It is **not** part of the product. Full
evidence in [`FINDINGS.md`](FINDINGS.md).

## Lean topology

| Component | What it is |
|---|---|
| [`bioma_micro/`](bioma_micro/) (Rust + PyO3) | The micro-kernel: `hormonal_bus.rs` (lock-free signal injection) + `context_apoptosis.rs` (history dehydration). Exposes strictly signal injection + the apoptosis filter. |
| [`bioma/`](bioma/) (Python) | `LeanOpenRouterClient` — resilient async OpenRouter dispatch that routes every payload through the Rust apoptosis filter first; exponential backoff on 429/5xx. |
| [`tests/`](tests/) | `test_enxuto_efficiency.py` — long-session end-to-end validation (kernel μs + % tokens saved). |

## Quickstart

```bash
# 1) Build & install the Rust micro-kernel (PyO3 extension)
python -m pip install maturin
cd bioma_micro && maturin build --release && \
  pip install --force-reinstall target/wheels/bioma_micro-*.whl && cd ..

# 2) Point at OpenRouter (key in .env — never commit it)
echo "OPENROUTER_API_KEY=sk-or-..." > .env

# 3) Validate the lean pipeline over a long session (real dispatch + real kernel)
python tests/test_enxuto_efficiency.py --rounds 16
```

Every script also runs offline in a clearly-labelled **mock/kernel-only** mode
without a key — the apoptosis metrics (μs latency, % saved) are always real.

## Security

- **Never commit secrets.** `.env` is git-ignored; keys live in `.env` locally and
  in your platform's secrets manager in production — never in the repo.
- Rotate your OpenRouter key at <https://openrouter.ai/keys>.

## Repository layout

```
bioma_micro/     Rust/PyO3 micro-kernel — hormonal bus + context apoptosis (the lean core)
bioma/           Python abstraction — resilient OpenRouter client with kernel apoptosis
tests/           end-to-end efficiency validation
FINDINGS.md      ground-truth evaluation (proven / refuted), reproducible
```

> Legacy layers (`bioma_orchestrator/`, `bioma_kernel/`) remain only to reproduce
> `FINDINGS.md` (the eval scripts + the resilience load-test). The torch/mitosis
> engine has been removed; `bioma_micro` + `bioma` are the product.

## License

MIT.
