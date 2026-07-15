# B.I.O.M.A. — Energia Medida por Dispatch (bancada local, hardware real)

> Gerado por `tests/test_energy_local.py` em 2026-07-14, executado na bateria
> (fuel gauge WMI `BatteryStatus.DischargeRate`, 2 Hz, idle de 15,58 W medido e
> subtraído). Modelo real local: **Llama 3.2 1B via Ollama**, CPU i7-1355U.
> 3 trials por braço, intercalados contra drift térmico, temperatura 0, seed fixa.
> Dados brutos: `reports/energy_local_runs.jsonl`.

## Resultado (medianas de 3 trials)

| Métrica (medida no hardware) | sem BIOMA | com BIOMA | redução |
| :--- | ---: | ---: | ---: |
| Tokens de prefill (tokenizer do modelo) | 7.481 | 212 | −97,2% |
| Tempo de prefill (compute) | 411,13s | 1,76s | −99,6% |
| Tempo total do dispatch | 416,57s | 7,05s | −98,3% |
| **Energia marginal por dispatch** | **2.714,7 J** (0,754 Wh) | **69,5 J** (0,019 Wh) | **−97,4%** |
| Qualidade (probes objetivas) | 100% | 100% | paridade ✅ |

## Sanidade física (a integral fecha)

Consumo médio do sistema no braço baseline: ~22,2 W · idle 15,58 W → potência
marginal ~6,6 W × 411s ≈ **2.714 J** — bate com a mediana integrada pelo fuel gauge.

## Leituras principais

1. **A energia medida acompanha a redução de tokens (−97,4% ≈ −97,2%)** — valida,
   por medição direta, a premissa de proporcionalidade tokens↔energia usada no
   cenário global de `gtm/ANALISE_SUSTENTABILIDADE_GLOBAL.md`.
2. **O compute cai superlinearmente** (−99,6% de tempo de prefill para −97,2% de
   tokens): cada token de peso morto custa *mais* que um token útil (atenção
   cresce mais que linear com o contexto).
3. **Escala ilustrativa**: um dispatch inchado neste notebook custou 0,754 Wh —
   2,5× a estimativa Epoch AI (~0,3 Wh) para uma query GPT-4o em data center.
   Com B.I.O.M.A.: 0,019 Wh. Peso morto de contexto transforma até um modelo de
   1B em consumidor pesado; a apoptose remove isso na origem.

## Limites declarados

- **Braço BIOMA tem incerteza alta por trial** (dispatch de ~7s vs atualização
  lenta do fuel gauge): o trial 2 registrou 0,0 J (leitura abaixo do idle).
  A mediana absorve o ruído; a ordem de grandeza (~70 J) é o dado confiável.
  O braço baseline (411s ≫ período do gauge) é robusto.
- **CPU de notebook ≠ GPU de data center**: os valores absolutos não transferem;
  a **razão** (−97%) é o sinal transferível, agora medido de ponta a ponta
  (tokens → tempo de compute → joules) com qualidade 100% preservada.
- Medição em GPU de data center (nvidia-smi/DCGM) permanece como próximo passo.
