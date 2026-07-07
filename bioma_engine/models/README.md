# `models/` — optional local weights (sovereign, offline)

**This directory is empty by default — and B.I.O.M.A. needs it to be.**

The framework is **autarkic by construction**: its code engine is a local
`torch.nn.Module` plus a **deterministic AST-transform optimizer**. It requires
**no downloaded weights, no external model, no API, no network**. With this
folder empty, `LocalInferenceEngine` reports `backend = "deterministic_ast"` —
the sovereign, shipped, tested path.

## Optional: bring your own local weights

If you want an additional **local-only** free-form inference backend, drop a
quantized model here and install the optional extra:

```bash
# 1. place a quantized model in this folder
#    models/your-model.Q4_K_M.gguf        (or a .safetensors file)

# 2. install the optional on-device inference binding (compiles llama.cpp)
pip install "bioma-engine[local-llm]"
```

`LocalInferenceEngine` then reports `backend = "local_gguf"` and runs the weights
**entirely on your CPU via llama.cpp** — still zero network egress. Point at a
custom location with `--models-dir <path>` or `BIOMA_MODELS_DIR`.

> No weights are shipped or downloaded by this project. Nothing here contacts a
> cloud provider (no OpenAI, no Anthropic, no Google Cloud).
