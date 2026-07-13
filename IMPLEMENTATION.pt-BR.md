# B.I.O.M.A. — Manual de Implantação

**🌐 [English](IMPLEMENTATION.md) · Português**

Guia passo a passo para implantar o B.I.O.M.A. numa organização — na frente de **modelos
locais** e de **APIs de provedores online** (Anthropic, Google, OpenAI e outras big techs).

> **Regra de ouro.** O B.I.O.M.A. roda **in-process, localmente**. Ele endurece o *payload*
> (desidrata + redige + protege) e entrega o prompt limpo ao *seu* modelo — online ou local.
> O modelo nunca vê o desperdício nem os segredos. Nada sai da máquina sem ser endurecido.

---

## 1. Arquitetura — onde o B.I.O.M.A. fica

```
        ┌─────────────────────────── SUA APLICAÇÃO / AGENTE ─────────────────────────────┐
        │  histórico + query + segredos no contexto                                      │
        └───────────────────────────────────┬────────────────────────────────────────────┘
                                             │  (1) payload cru
                                             ▼
        ┌────────────────── B.I.O.M.A. — PERÍMETRO COGNITIVO (local, μs) ──────────────────┐
        │  saturation_scan → alerta 0x0F   ·   apoptose de contexto (−80%)   ·   redação    │
        │  ── o payload é desidratado, checado contra flood e sem segredos ──               │
        └───────────────────────────────────┬────────────────────────────────────────────┘
                                             │  (2) prompt limpo  (h.prompt / h.system)
                       ┌─────────────────────┼─────────────────────┐
                       ▼                     ▼                     ▼
             ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
             │ PROVEDOR ONLINE  │  │ PROVEDOR ONLINE  │  │  LOCAL / ON-PREM  │
             │ API Anthropic    │  │ OpenAI · Google  │  │ Llama · vLLM ·    │
             │ (Claude)         │  │ Azure · Bedrock  │  │ Ollama · llama.cpp│
             └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
                      └─────────────────────┼─────────────────────┘
                                            │  (3) resposta
                                            ▼
                    B.I.O.M.A. também redige segredos da resposta
                                            │
                                            ▼
                                  de volta à sua aplicação
```

**Posição na defesa em profundidade** — o B.I.O.M.A. é a camada de IA que a pilha clássica não tem:

```
Rede / Host    Firewall · WAF · EDR · IDS/IPS · IAM        (já existe)
Aplicação      validação de input · secrets manager         (já existe)
PERÍMETRO IA   ▸ B.I.O.M.A.  ← esta camada                  (a lacuna que você fecha)
Modelo         Anthropic · Google · OpenAI · on-prem
```

---

## 2. Como funciona — o ciclo de vida da requisição

1. Sua app monta o payload usual (histórico + query atual; segredos podem estar presentes).
2. `fw.shield(history, query)` roda **localmente, em microssegundos**:
   - **saturation_scan** mede repetição → se parece um flood de DDoS cognitivo, dispara o
     alerta vermelho `0x0F` no barramento hormonal;
   - **apoptose de contexto** atribui peso metabólico, decai por meia-vida e **purga** os
     blocos de baixo valor — desidratando a entrada em ~80–97%;
   - **redação de segredos** remove todo valor do vault do payload de saída.
3. Você envia `h.prompt` / `h.system` para **qualquer** modelo (API online ou local).
4. Na volta, o B.I.O.M.A. redige segredos da **resposta** também (defesa em profundidade).

`h.telemetry` traz a auditoria: `saturation`, `red_alert`, `apoptosis_reduction`,
`tokens_before/after`, `secrets_redacted`, `kernel_latency_us`.

---

## 3. Pré-requisitos e instalação

```bash
# 1) Toolchain Rust (para o build do kernel) + maturin
python -m pip install maturin

# 2) Compile e instale o micro-kernel (extensão PyO3)
cd bioma_micro && maturin build --release
pip install --force-reinstall target/wheels/bioma_micro-*.whl && cd ..

# 3) A camada Python é o pacote `bioma/` (adicione a raiz do repo ao PYTHONPATH,
#    ou `pip install -e .` quando adicionar um pyproject pra ele)
```

Nenhuma chave de API é necessária para o endurecimento em si — apoptose, saturação e redação
rodam totalmente offline. As chaves são só as do seu provedor de modelo, usadas pelo *seu* SDK.

---

## 4. Padrões de integração

### A. Provedor online — o padrão puro `shield()` (recomendado)

Endureça localmente e chame o SDK do provedor você mesmo. Funciona com **qualquer** fornecedor.

```python
from bioma.firewall_client import CognitiveFirewall

fw = CognitiveFirewall(vault={"db_password": DB_PW, "api_key": CHAVE_INTERNA})

h = fw.shield(history, "refatore este módulo")   # local, μs — desidratado + redigido
# h.prompt, h.system estão limpos; h.telemetry tem a auditoria
```

**OpenAI (ou Azure OpenAI):**
```python
from openai import OpenAI
r = OpenAI().chat.completions.create(
    model="gpt-5.5",
    messages=([{"role":"system","content":h.system}] if h.system else []) +
             [{"role":"user","content":h.prompt}])
```

**Anthropic (Claude):**
```python
import anthropic
r = anthropic.Anthropic().messages.create(
    model="claude-sonnet-5", max_tokens=1024,
    system=h.system or "", messages=[{"role":"user","content":h.prompt}])
```

**Google (Gemini):**
```python
from google import genai
r = genai.Client().models.generate_content(
    model="gemini-3.1-pro", contents=(h.system+"\n\n" if h.system else "")+h.prompt)
```

**AWS Bedrock / Vertex / qualquer gateway compatível com OpenAI:** mesma ideia — envie `h.prompt`.

> Redija a resposta também: `safe = fw._redact(texto_resp)[0]` (ou use o padrão **B**, que
> faz isso automaticamente).

### B. Traga seu dispatcher async — guards automáticos

Envolva *qualquer* chamada async de provedor; você ganha o **timeout guard** e a **redação da
resposta** de graça.

```python
async def chamar_claude(prompt, system):
    msg = await anthropic.AsyncAnthropic().messages.create(
        model="claude-sonnet-5", max_tokens=1024, system=system or "",
        messages=[{"role":"user","content":prompt}])
    return msg.content[0].text

shield = await fw.harden(history, "refatore", dispatch_fn=chamar_claude)
# shield.answer (com segredo redigido), shield.timed_out, shield.apoptosis_reduction, ...
```

### C. Modelo local / on-prem (air-gapped)

O mesmo `shield()`; o dispatcher é seu runtime local. Zero rede.

```python
# Ollama
import ollama
h = fw.shield(history, query)
out = ollama.chat(model="llama3.3", messages=[{"role":"user","content":h.prompt}])

# vLLM / llama.cpp (servidor compatível com OpenAI)
from openai import OpenAI
local = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="local")
r = local.chat.completions.create(model="local-model",
        messages=[{"role":"user","content":h.prompt}])
```

Os ganhos de eficiência e segurança são **idênticos** ao caso online — o B.I.O.M.A. age no
payload, não no modelo.

### D. Como serviço sidecar local (agnóstico de linguagem)

Rode o serviço FastAPI incluso para apps não-Python chamarem o B.I.O.M.A. via localhost.

```bash
uvicorn bioma.server:app --host 127.0.0.1 --port 8900
#   GET  /health        → liveness + versão do kernel
#   POST /v1/dispatch   → {history, query, model} → despacho endurecido (+ auditoria de apoptose)
```

Qualquer serviço (Node, Go, Java) faz POST do payload em `http://127.0.0.1:8900/v1/dispatch`.

---

## 5. Configuração

```python
CognitiveFirewall(
    vault={"nome": "VALOR_SECRETO", ...},  # valores removidos da saída + resposta
    saturation_threshold=0.85,             # ≥ isto → alerta vermelho 0x0F (DDoS cognitivo)
    dispatch_timeout=20.0,                 # segundos; limita qualquer chamada (padrão B)
    half_life=6.0,                         # agressividade da apoptose (menor = mais poda)
    safe_threshold=0.35,                   # piso de oxigênio abaixo do qual o bloco é purgado
)
```

- **Classes duráveis nunca são purgadas:** blocos `SYSTEM` e `FACT` são reforçados.
- Marque os itens do histórico por papel (`system`/`user`/`assistant`/`tool`/`fact`) para o
  kernel atribuir o peso metabólico certo (logs `tool` verbosos são o alvo primário da apoptose).

---

## 6. Defesa em profundidade — como funciona e o impacto medido

| Ameaça | Mecanismo | Como protege | Impacto medido |
| :--- | :--- | :--- | :--- |
| **Exfiltração de segredo** (prompt injection) | Redação de segredos | Valores do vault são removidos da saída **e** da resposta → o modelo nunca os recebe, então a injeção não tem o que exfiltrar | **0 vazados** nos 6 modelos de fronteira (baseline vaza; B.I.O.M.A. não) |
| **DDoS cognitivo** (flood / exaustão de contexto) | saturation_scan → `0x0F` → apoptose | Floods repetitivos são detectados e desidratados antes do despacho, então a janela de contexto nunca esgota | flood **32.317 → 13 tokens**, saturação 0.999, em **0,6μs** |
| **Injeção de loop / trava** | timeout guard | Todo despacho tem um deadline; um loop não trava o pipeline | **contido** (despacho limitado) |
| **Explosão de custo** | apoptose de contexto | A entrada inchada é desidratada em cada chamada | **−80% a −97%** de tokens de entrada |

**Escopo honesto.** O B.I.O.M.A. é **uma camada** de defesa em profundidade. Ele **não**
substitui controles de rede/host (firewall, EDR, IAM), não faz scan de vulnerabilidade, e não
concede "imunidade". Ele endurece a **fronteira de I/O do LLM** — segredos declarados e floods
repetitivos — e limita latência. Veja [`FINDINGS.pt-BR.md`](FINDINGS.pt-BR.md) para a avaliação
completa e honesta (inclusive o que refutamos).

---

## 7. Topologias de implantação

| Topologia | Quando | Como |
| :--- | :--- | :--- |
| **Biblioteca embutida** | apps/agentes Python | `import bioma.firewall_client`; chame `shield()`/`harden()` inline |
| **Sidecar local** | stacks poliglotas, microsserviços | rode o `bioma.server` no localhost; POST dos payloads pra ele |
| **Air-gapped / on-prem** | classificado / regulado | biblioteca + um modelo local; apoptose + firewall rodam offline, sem rede |

---

## 8. Validar e monitorar

```bash
# suíte unitária (offline, determinística)
python -m pytest tests/test_kernel.py tests/test_firewall.py tests/test_server.py -q

# validações reais de eficiência + segurança + ganhos universais (precisa de chave de provedor)
python tests/test_enxuto_efficiency.py
python tests/test_sovereign_defense.py       # gera reports/BIOMA_IMMUNITY_VERDICT.md
python tests/test_universal_integration.py   # gera reports/BIOMA_UNIVERSAL_GAINS.md
```

Alimente a `h.telemetry` (% de redução, saturação, red_alert, μs do kernel, secrets_redacted)
no seu stack de observabilidade para acompanhar economia e alertas por requisição.

---

## 9. Checklist de rollout

- [ ] `bioma_micro` compilado e importado no ambiente-alvo.
- [ ] `vault` preenchido com todo segredo que jamais pode chegar a um modelo.
- [ ] Padrão de integração escolhido (A puro / B dispatcher / C local / D sidecar).
- [ ] `saturation_threshold` e `half_life` ajustados ao seu workload.
- [ ] Redação da resposta no lugar (padrão B faz; padrão A: chame `_redact`).
- [ ] Telemetria ligada à observabilidade; testes unitários verdes no CI.
- [ ] Para air-gapped: confirmado que apoptose + firewall rodam sem rede/chave.
