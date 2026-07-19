| Model | Tier | N | Median reduction (95% CI) | Success baseline | Success BIOMA | $ saved / 1k sessions |
| :--- | :--- | ---: | :--- | ---: | ---: | ---: |
| gpt-5.6-sol | frontier | 90 | 84% [84, 84] | 91% | 89% | $20 |
| gpt-5.5 | frontier | 90 | 84% [84, 84] | 86% | 86% | $20 |
| gemini-pro | frontier | 90 | 84% [83, 84] | 63% | 60% | $9 |
| fable-5 | frontier | 90 | 83% [83, 84] | 33% | 47% | $62 |
| claude-opus | frontier | 90 | 83% [83, 84] | 97% | 96% | $31 |
| gpt-mini | budget | 90 | 84% [84, 84] | 97% | 99% | $3 |
| claude-haiku | budget | 90 | 84% [83, 84] | 97% | 97% | $5 |
| deepseek-chat | budget | 90 | 84% [83, 84] | 87% | 83% | $1 |

_Paired A/B, N=30 tasks, 3 reps, temperature=0.2. Reduction = input-token reduction, median over pairs with bootstrap 95% CI. $ saved extrapolates the measured mean input-token saving × models.yaml input price to 1,000 sessions (list prices 2026-07-19). Raw data & methodology: github.com/jonathascordeiro20/bioma-framework/benchmarks/ab-publico._
