# B.I.O.M.A. — Preservação de Qualidade sob Apoptose (dispatch real online)

> Gerado por `tests/test_quality_preservation.py`. Ground truth: probes objetivas
> (valores exatos plantados no histórico) verificadas na resposta do modelo.
> Baseline = contexto completo; BIOMA = mesmo prompt após `bioma_micro.dehydrate`.

| Cenário | Modelo | Baseline | BIOMA | in_tok base→BIOMA | redução | veredito |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| S1 | GPT-5.5 | 100% | 100% | 7,612 → 193 | −97% | ✅ paridade |
| S1 | Claude Sonnet 5 | 100% | 100% | 11,694 → 298 | −97% | ✅ paridade |
| S1 | Claude Fable 5 | 0% | 0% | 11,694 → 298 | −97% | ⚠ erro de API: empty response (finish=content_filter) |
| S1 | Gemini 3.1 Pro | 100% | 100% | 8,793 → 215 | −97% | ✅ paridade |
| S1 | Grok 4.5 | 100% | 100% | 7,812 → 393 | −97% | ✅ paridade |
| S1 | GLM-5.2 | 100% | 100% | 7,619 → 200 | −97% | ✅ paridade |
| S2 | GPT-5.5 | 100% | 100% | 7,083 → 152 | −97% | ✅ paridade |
| S2 | Claude Sonnet 5 | 100% | 100% | 10,893 → 244 | −97% | ✅ paridade |
| S2 | Claude Fable 5 | 0% | 0% | 10,893 → 244 | −97% | ⚠ erro de API: empty response (finish=content_filter) |
| S2 | Gemini 3.1 Pro | 100% | 100% | 8,177 → 171 | −97% | ✅ paridade |
| S2 | Grok 4.5 | 100% | 100% | 7,284 → 353 | −97% | ✅ paridade |
| S2 | GLM-5.2 | 100% | 100% | 7,093 → 162 | −97% | ✅ paridade |
| S3 | GPT-5.5 | 100% | 0% | 7,556 → 119 | −98% | purga by design (use FACT) |
| S3 | Claude Sonnet 5 | 100% | 0% | 11,620 → 194 | −98% | purga by design (use FACT) |
| S3 | Claude Fable 5 | 0% | 0% | 11,620 → 194 | −98% | ⚠ erro de API: empty response (finish=content_filter) |
| S3 | Gemini 3.1 Pro | 100% | 0% | 8,730 → 130 | −98% | purga by design (use FACT) |
| S3 | Grok 4.5 | 100% | 0% | 7,755 → 319 | −98% | purga by design (use FACT) |
| S3 | GLM-5.2 | 100% | 0% | 7,562 → 125 | −98% | purga by design (use FACT) |

Custo total: $0.1852 · duração 144s · modelos: GPT-5.5, Claude Sonnet 5, Claude Fable 5, Gemini 3.1 Pro, Grok 4.5, GLM-5.2

**Contrato de uso comprovado:** valores duráveis marcados como `FACT` e contexto recente
sobrevivem à apoptose com resposta final íntegra; informação durável não marcada em turnos
antigos é purgada por design (S3) — tague-a como `FACT`.
