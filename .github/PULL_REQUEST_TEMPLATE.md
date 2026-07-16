## What

<!-- One-paragraph summary of the change. -->

## Why

<!-- Problem/issue it solves. Link issues. -->

## Evidence

<!-- This project ships measured claims only. If the change affects tokens,
     latency, cost or answer quality: which harness in tests/ measures it,
     and what were the numbers before/after? "N/A" is fine for docs/chores. -->

## Checklist

- [ ] CI green (offline suite, 3 OSes)
- [ ] Rust: `cargo fmt` + `cargo clippy -- -D warnings` (if `bioma_micro/` touched)
- [ ] Docs/CHANGELOG updated if user-facing
- [ ] Honest limits documented (if the feature has a failure mode)
