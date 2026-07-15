#!/usr/bin/env python3
"""
tests/e2e_agent_gateway.py — E2E com AGENTE REAL de tool-calling pelo gateway.

Um agente de verdade: mantém o histórico, chama ferramentas (ler arquivo,
escrever arquivo, rodar pytest) em loop até os testes passarem ou atingir o
limite de turnos. O MESMO agente roda em dois braços — direto no OpenRouter vs
pela `base_url` do gateway BIOMA — sobre um repositório real com um bug real.
Mede, de ponta a ponta: tokens/custo acumulados, nº de turnos, e sucesso
(pytest verde). É o que o protocolo original pedia; a única diferença do Claude
Code é o protocolo (OpenAI, não Anthropic — a superfície Anthropic é o próximo passo).

O gateway lida com os pares tool_call/tool como unidade e desidrata o histórico
que cresce a cada turno (saídas de teste, conteúdos de arquivo) — exatamente a
carga que o agente acumula. O histórico local do agente é sempre íntegro; só o
que sobe ao modelo é desidratado.

Requer o gateway rodando:  uvicorn bioma.gateway:app --port 8790

    python tests/e2e_agent_gateway.py --model anthropic/claude-sonnet-5
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, ".env"))
except Exception:
    pass
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

from openai import OpenAI  # noqa: E402

PORT = int(os.environ.get("BIOMA_GW_PORT", "8790"))

# --- o repositório-alvo real (bug de off-by-one em janela de datas) --------- #
BUGGY = '''\
from datetime import date, timedelta


def days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def month_window(year: int, month: int):
    """Return (start, end) for the month. BUG: consumers filter with ts < end
    (exclusive), so the last day is dropped. Fix: end should be the first day of
    the next month, so the exclusive filter includes the real last day."""
    start = date(year, month, 1)
    end = start + timedelta(days=days_in_month(year, month) - 1)
    return start, end
'''

TEST = '''\
from datetime import date
from window import month_window


def test_includes_last_day():
    start, end = month_window(2026, 2)  # Feb 2026, 28 days
    assert start == date(2026, 2, 1)
    # consumer filters with ts < end; to include Feb 28, end must be Mar 1
    assert end == date(2026, 3, 1)


def test_december_rolls_over():
    start, end = month_window(2026, 12)
    assert end == date(2027, 1, 1)
'''

SYSTEM = ("You are a coding agent fixing a bug in a small repo. Use the tools to "
          "read files, write files, and run the tests. Iterate until `run_pytest` "
          "reports all tests pass. The bug is an off-by-one in a date window. When "
          "tests pass, reply with the single word DONE.")

TOOLS = [
    {"type": "function", "function": {
        "name": "read_file", "description": "Read a file from the repo.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_file", "description": "Overwrite a file in the repo.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "run_pytest", "description": "Run the test suite; returns output.",
        "parameters": {"type": "object", "properties": {}}}},
]


class Repo:
    def __init__(self) -> None:
        self.dir = tempfile.mkdtemp(prefix="bioma_e2e_")
        with open(os.path.join(self.dir, "window.py"), "w") as f:
            f.write(BUGGY)
        with open(os.path.join(self.dir, "test_window.py"), "w") as f:
            f.write(TEST)

    def read(self, path: str) -> str:
        try:
            with open(os.path.join(self.dir, os.path.basename(path))) as f:
                return f.read()
        except OSError as e:
            return f"ERROR: {e}"

    def write(self, path: str, content: str) -> str:
        with open(os.path.join(self.dir, os.path.basename(path)), "w") as f:
            f.write(content)
        return f"wrote {len(content)} chars to {path}"

    def pytest(self) -> tuple[str, bool]:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", self.dir],
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr)[-1500:]
        return out, (r.returncode == 0)

    def passes(self) -> bool:
        return self.pytest()[1]

    def reset(self) -> None:
        with open(os.path.join(self.dir, "window.py"), "w") as f:
            f.write(BUGGY)

    def cleanup(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


def _seed_history(n: int) -> list[dict]:
    """Realistic accumulated history of a long-running agent: prior file reads,
    verbose test runs, resolved reasoning — the dead weight a real session carries
    into the current task. This is what the gateway dehydrates each turn."""
    h: list[dict] = []
    for i in range(n):
        h += [
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": f"seed{i}", "type": "function",
                             "function": {"name": "run_pytest", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": f"seed{i}",
             "content": (f"[prior run {i}] collected 148 items ... 147 passed 1 failed "
                         "in 12.4s ... DeprecationWarning x3 ... coverage 87% ... "
                         "long traceback ... AssertionError ... ") * 6},
            {"role": "user", "content": f"prior step {i}: keep going"},
            {"role": "assistant", "content": f"prior step {i}: unrelated area, moving on."},
        ]
    return h


def run_agent(client: OpenAI, model: str, repo: Repo, max_turns: int = 15,
              seed_turns: int = 0) -> dict:
    repo.reset()
    messages = [{"role": "system", "content": SYSTEM}]
    messages += _seed_history(seed_turns)
    messages.append({"role": "user", "content": "Fix the failing tests in this repo. Start by reading window.py."})
    tot_in = tot_out = turns = 0
    solved = False
    for turn in range(max_turns):
        turns += 1
        resp = client.chat.completions.create(
            model=model, messages=messages, tools=TOOLS,
            temperature=0.0, max_tokens=1500)
        u = resp.usage
        tot_in += int(u.prompt_tokens or 0)
        tot_out += int(u.completion_tokens or 0)
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        if not msg.tool_calls:
            if repo.passes():
                solved = True
            break
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if name == "read_file":
                result = repo.read(args.get("path", "window.py"))
            elif name == "write_file":
                result = repo.write(args.get("path", "window.py"), args.get("content", ""))
            elif name == "run_pytest":
                out, ok = repo.pytest()
                result = ("ALL TESTS PASS\n" if ok else "TESTS FAIL\n") + out
                if ok:
                    solved = True
            else:
                result = f"unknown tool {name}"
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
        if solved:
            break
    return {"in": tot_in, "out": tot_out, "turns": turns, "solved": solved}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="anthropic/claude-sonnet-5")
    ap.add_argument("--max-turns", type=int, default=15)
    ap.add_argument("--seed-turns", type=int, default=0,
                    help="prepend N turns of realistic accumulated history "
                         "(simulates a long-running agent — where apoptosis matters)")
    args = ap.parse_args()
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key.startswith("sk-or"):
        print("OPENROUTER_API_KEY ausente."); return 2

    import httpx
    try:
        httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=5).raise_for_status()
    except Exception:
        print(f"gateway não responde — inicie: uvicorn bioma.gateway:app --port {PORT}")
        return 3

    direct = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key)
    gw = OpenAI(base_url=f"http://127.0.0.1:{PORT}/v1", api_key=key)
    repo = Repo()

    print("=" * 96)
    print("  B.I.O.M.A. — E2E de agente real de tool-calling (direto vs gateway)")
    print("=" * 96)
    seed_note = (f" · histórico acumulado: {args.seed_turns} turnos"
                 if args.seed_turns else " · sessão limpa (sem histórico prévio)")
    print(f"  modelo {args.model} · repo real (bug de off-by-one) · ferramentas: "
          f"read_file/write_file/run_pytest · aceite: pytest verde{seed_note}\n")

    try:
        print("— braço A (direto no OpenRouter)")
        a = run_agent(direct, args.model, repo, args.max_turns, args.seed_turns)
        print(f"    {'RESOLVIDO' if a['solved'] else 'FALHOU':10s} · {a['turns']} turnos · "
              f"in {a['in']:,} out {a['out']:,} tokens")
        print("— braço B (pelo gateway BIOMA)")
        b = run_agent(gw, args.model, repo, args.max_turns, args.seed_turns)
        print(f"    {'RESOLVIDO' if b['solved'] else 'FALHOU':10s} · {b['turns']} turnos · "
              f"in {b['in']:,} out {b['out']:,} tokens")
    finally:
        repo.cleanup()

    print("\n" + "=" * 96)
    print("## Veredito E2E\n")
    print("| Métrica | Braço A (direto) | Braço B (BIOMA) | Δ |")
    print("| :--- | ---: | ---: | ---: |")
    red = (1 - b["in"] / a["in"]) * 100 if a["in"] else 0
    print(f"| Tokens de entrada acumulados | {a['in']:,} | {b['in']:,} | **−{red:.0f}%** |")
    print(f"| Tokens de saída | {a['out']:,} | {b['out']:,} | — |")
    print(f"| Turnos até resolver | {a['turns']} | {b['turns']} | — |")
    print(f"| Tarefa resolvida (pytest verde) | {'✅' if a['solved'] else '❌'} "
          f"| {'✅' if b['solved'] else '❌'} | {'paridade' if a['solved']==b['solved'] else 'DIVERGIU'} |")
    verdict = 0 if (b["solved"] or not a["solved"]) else 1
    if b["solved"] and a["solved"]:
        print(f"\n✅ Ambos resolveram o bug real; o agente pelo gateway usou −{red:.0f}% de")
        print("   tokens de entrada acumulados, com o histórico crescente desidratado a cada")
        print("   turno e os pares tool_call/tool preservados como unidade.")
    elif a["solved"] and not b["solved"]:
        print("\n❌ RESULTADO DE PRIMEIRA PÁGINA: o gateway QUEBROU a tarefa que o direto")
        print("   resolveu — a apoptose removeu estado necessário do loop. Investigar.")

    out = os.path.join(_ROOT, "resultados", "e2e_agent.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"model": args.model, "A": a, "B": b,
                   "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}, f, indent=2)
    print(f"\n📄 dados: {out}")
    return verdict


if __name__ == "__main__":
    raise SystemExit(main())
