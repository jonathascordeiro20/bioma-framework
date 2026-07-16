# bioma-langchain

Context apoptosis for LangChain: prune stale, low-value history with the
[B.I.O.M.A.](https://github.com/jonathascordeiro20/bioma-framework) Rust kernel
(~1 µs decision) before messages reach the model.

Custom LangChain agents that resend a growing history are exactly where the
kernel measured **−84% input tokens** (and up to −97.6% on bloated sessions)
with answer quality at parity — see the repo's honest benchmark report,
including where it does *not* help.

## Install

```bash
pip install bioma-langchain
```

## Use

```python
from bioma_langchain import BiomaDehydrator
from langchain_core.messages import HumanMessage

dehydrator = BiomaDehydrator()      # tool-calling default: safe_threshold=0.2

# LCEL — drop it right before the model:
chain = dehydrator | llm

# or call it directly:
lean_history = dehydrator.invoke(messages)
print(dehydrator.last_audit)        # tokens_before/after, reduction, µs
```

Durable values must be marked to survive forever (the usage contract):

```python
HumanMessage("The rollback token is RBK-5521.",
             additional_kwargs={"bioma": "fact"})
```

## Class mapping

| LangChain message | Kernel class | Behavior |
| :--- | :--- | :--- |
| `SystemMessage` | `SYSTEM` | never purged |
| `additional_kwargs={"bioma": "fact"}` | `FACT` | never purged |
| `HumanMessage` / `AIMessage` | `USER`/`ASSISTANT` | decay by recency |
| `ToolMessage`, tool-call-only `AIMessage` | `TOOL` | dehydrates first |

Declared limit: an *old, untagged* value decays below the threshold and is
purged by design — tag durable info as `fact`.
