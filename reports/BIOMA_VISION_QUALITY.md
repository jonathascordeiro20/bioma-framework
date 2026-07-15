# B.I.O.M.A. — Apoptose sobre Contexto de Imagens (dispatch real, modelos com visão)

> Gerado por `tests/test_vision_quality_preservation.py`. Probes = strings exatas
> RENDIDAS NOS PIXELS de screenshots sintéticos; baseline = todas as imagens;
> BIOMA = kernel inalterado + adaptador de visão (marcadores com custo nominal de
> 1.600 tok/imagem; screenshots como USER — recência decide; referência como FACT).

| Cenário | Modelo | Baseline | BIOMA | in_tok (usage real) | imagens | veredito |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| V1 | GPT-5.5 | 100% | 100% | 10,221 → 4,747 | 13 → 6 | ✅ paridade |
| V1 | Claude Sonnet 5 | 100% | 100% | 11,484 → 5,338 | 13 → 6 | ✅ paridade |
| V1 | Gemini 3.1 Pro | 100% | 100% | 14,418 → 6,683 | 13 → 6 | ✅ paridade |
| V2 | GPT-5.5 | 100% | 100% | 9,436 → 3,962 | 12 → 5 | ✅ paridade |
| V2 | Claude Sonnet 5 | 100% | 100% | 10,604 → 4,458 | 12 → 5 | ✅ paridade |
| V2 | Gemini 3.1 Pro | 100% | 100% | 13,310 → 5,576 | 12 → 5 | ✅ paridade |
| V3 | GPT-5.5 | 100% | 0% | 9,435 → 3,963 | 12 → 5 | purga by design (fixe como FACT) |
| V3 | Claude Sonnet 5 | 100% | 0% | 10,608 → 4,465 | 12 → 5 | purga by design (fixe como FACT) |
| V3 | Gemini 3.1 Pro | 100% | 0% | 13,309 → 5,577 | 12 → 5 | purga by design (fixe como FACT) |

Custo total: $0.3718 · duração 123s

Limites: purga tudo-ou-nada por imagem (sem tiers downscale/caption);
firewall não faz OCR (segredos em pixels não são redigidos); custo nominal
por imagem declarado em 1.600 tokens — os tokens reais vêm do usage da API.
