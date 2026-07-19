# A/B paired multi-model benchmark — BIOMA Cognitive Firewall

Measures what `CognitiveFirewall.shield()` is worth on realistic long
coding-agent sessions: for every (task, model, rep) the same request runs twice —

* **arm A (baseline)** — full session history sent verbatim;
* **arm B (bioma)** — history passed through `fw.shield(history, final_prompt,
  system)`; the hardened `h.prompt` / `h.system` are sent instead, and
  `h.telemetry` is recorded.

Pairing per task makes tokens, latency and task success directly comparable.

## Files

| file | purpose |
|---|---|
| `models.yaml` | model roster in two tiers (`frontier`, `budget`); ids, prices, key env vars. Entries marked `# VERIFY` need confirmation against official docs before a paid run. |
| `tasks.json` | 30 tasks (Python 10, TypeScript 8, Rust 6, SQL/Django 6) with `stale_ratio` labels: 10 high (~70% stale context), 10 medium (~40%), 10 low (~15%). The 10 Python tasks carry an executable pytest gate (`test_code`). |
| `run_benchmark.py` | runs the arms; `--tier`, `--models`, `--tasks`, `--reps`, `--mock` |
| `analyze.py` | paired Wilcoxon, bootstrap CI95, success per arm, $ and energy saved (energy via `bioma.esg` declared coefficients), per-`stale_ratio` and cross-tier tables |
| `estimate_cost.py` | estimated cost of the full run per model — no API calls |

## Quality gate

Tasks with `test_code`: the first ` ```python ` block of the response is written
to `solution.py` and the task's pytest file runs against it in a subprocess
(30s timeout). All other tasks: every `success_keywords` entry must appear in
the response (keywords are objectively required identifiers/APIs only).

## Usage

```bash
pip install -e ../..           # bioma + kernel
pip install anthropic openai scipy pyyaml numpy pytest

python estimate_cost.py --reps 3          # decide what to run
python run_benchmark.py --models deepseek-chat --tasks 1 --reps 1   # cheap smoke
python run_benchmark.py --tier budget --reps 3
python run_benchmark.py --tier frontier --reps 3
python analyze.py
```

`--mock` exercises the full pipeline without network or API keys; mock success
rates are meaningless by design (integration check only).

Results append to `results/results.jsonl`; delete it between unrelated runs.
