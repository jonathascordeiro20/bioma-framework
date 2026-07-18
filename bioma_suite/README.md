# bioma-suite

**One install for the whole B.I.O.M.A. stack.** / **Um install para a pilha B.I.O.M.A. inteira.**

```bash
pip install bioma-suite
bioma-doctor            # verify every component / confira cada componente
```

A meta-package: it ships no runtime of its own, just the pinned dependency set
so a single command pulls everything —

| Component | Package |
| :--- | :--- |
| Rust micro-kernel (context apoptosis + hormonal bus) | `bioma-micro` |
| Python framework — gateway, clients, vision, ESG, live monitor | `bioma-framework[all]` |
| LangChain integration (`BiomaDehydrator` Runnable) | `bioma-langchain` |

— plus `bioma-doctor`, a stdlib-only checkup: which components import, their
versions, and a real kernel smoke test (a measured `dehydrate()` round-trip).
Exit 0 = core healthy.

Prefer a lighter footprint? Install tiers individually:
`pip install bioma-framework[gateway]` (see the
[main README](https://github.com/jonathascordeiro20/bioma-framework)).

License: FSL-1.1-MIT (fair-source; converts to MIT two years after each release).
