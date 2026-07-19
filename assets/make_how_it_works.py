#!/usr/bin/env python3
"""Generate the plain-language explainer anyone can read (EN + pt-BR).

A conceptual (not data) diagram: every AI turn re-sends the whole conversation;
B.I.O.M.A. trims the stale part in ~1 µs before it is sent; the model gets a
small, clean payload and returns the same answer. No numbers to parse.

    python make_how_it_works.py            # writes both languages
    python make_how_it_works.py --lang pt  # just pt-BR
"""
import argparse
import pathlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = pathlib.Path(__file__).resolve().parent
SLATE = "#64748b"
SLATE_D = "#475569"
TEAL = "#0f766e"
TEAL_L = "#5eead4"
INK = "#0f172a"
MUTE = "#6b7280"

STRINGS = {
    "en": {
        "file": "how-it-works.png",
        "title": "How B.I.O.M.A. works — in plain English",
        "s1_h": "1 · The problem", "s1_sub": "Every turn re-sends the ENTIRE chat.\n50–60% of it is dead weight.",
        "turns": ["system", "turn 1", "turn 2", "turn 3", "turn 4", "turn 5", "turn 6", "…"],
        "stale": "stale", "grows": "grows every single turn",
        "apop": "context apoptosis",
        "b_body": "Runs inside your app, in ~1 µs.\nKeeps what matters,\ndrops the stale history —\nbefore anything is sent.",
        "b_foot": "your provider · your keys · no rewrite",
        "s3_h": "3 · What's actually sent", "s3_sub": "A small, clean payload.\nSame answer from the model.",
        "sent": ["system", "what matters", "your question"],
        "s3_note": "the model answers exactly as before",
        "banner": "Same answer  ·  ~84% fewer tokens  ·  less cost, energy & carbon  ·  and you can prove it",
    },
    "pt": {
        "file": "how-it-works.pt-BR.png",
        "title": "Como o B.I.O.M.A. funciona — em português simples",
        "s1_h": "1 · O problema", "s1_sub": "Cada turno reenvia o chat INTEIRO.\n50–60% disso é peso morto.",
        "turns": ["system", "turno 1", "turno 2", "turno 3", "turno 4", "turno 5", "turno 6", "…"],
        "stale": "obsoleto", "grows": "cresce a cada turno",
        "apop": "apoptose de contexto",
        "b_body": "Roda dentro do seu app, em ~1 µs.\nMantém o que importa,\ndescarta o histórico obsoleto —\nantes de qualquer envio.",
        "b_foot": "seu provedor · suas chaves · sem reescrever",
        "s3_h": "3 · O que é enviado", "s3_sub": "Um payload pequeno e limpo.\nMesma resposta do modelo.",
        "sent": ["system", "o que importa", "sua pergunta"],
        "s3_note": "o modelo responde igual a antes",
        "banner": "Mesma resposta  ·  ~84% menos tokens  ·  menos custo, energia e carbono  ·  e você pode provar",
    },
}


def bubble(ax, x, y, w, h, color, edge=None):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.006,rounding_size=0.02",
                                linewidth=0, facecolor=color, edgecolor=edge or color))


def render(lang: str):
    s = STRINGS[lang]
    fig, ax = plt.subplots(figsize=(14, 6.2))
    ax.set_xlim(0, 14); ax.set_ylim(-0.2, 6.2); ax.axis("off")
    fig.patch.set_facecolor("white")

    # ---- Stage 1: the problem -------------------------------------------- #
    ax.text(2.1, 5.7, s["s1_h"], fontsize=13, fontweight="bold", color=INK, ha="center")
    ax.text(2.1, 5.32, s["s1_sub"], fontsize=10.5, color=MUTE, ha="center", va="top")
    for i, lab in enumerate(s["turns"]):
        y = 4.05 - i * 0.42
        stale = i not in (0,)  # system stays; most turns are stale
        bubble(ax, 0.9, y, 2.4, 0.34, "#e2e8f0" if stale else "#cbd5e1")
        ax.text(1.02, y + 0.17, lab, fontsize=8.5, color=SLATE_D, va="center")
        if stale and i != len(s["turns"]) - 1:
            ax.text(3.05, y + 0.17, s["stale"], fontsize=7, color="#b91c1c", va="center", ha="right")
    ax.text(2.1, 0.5, s["grows"], fontsize=9, color="#b91c1c", ha="center", style="italic")

    ax.add_patch(FancyArrowPatch((3.7, 3.1), (5.0, 3.1), arrowstyle="-|>",
                                 mutation_scale=22, color=SLATE, lw=2))

    # ---- Stage 2: B.I.O.M.A. --------------------------------------------- #
    bubble(ax, 5.1, 1.6, 3.7, 3.0, "#f0fdfa", edge=TEAL)
    ax.add_patch(FancyBboxPatch((5.1, 1.6), 3.7, 3.0, boxstyle="round,pad=0.01,rounding_size=0.05",
                                linewidth=1.6, facecolor="none", edgecolor=TEAL))
    ax.text(6.95, 4.15, "B.I.O.M.A.", fontsize=15, fontweight="bold", color=TEAL, ha="center")
    ax.text(6.95, 3.72, s["apop"], fontsize=10.5, color=TEAL, ha="center", style="italic")
    ax.text(6.95, 3.2, s["b_body"], fontsize=10, color=INK, ha="center", va="center")
    ax.text(6.95, 1.85, s["b_foot"], fontsize=8.5, color=MUTE, ha="center")

    ax.add_patch(FancyArrowPatch((8.9, 3.1), (10.2, 3.1), arrowstyle="-|>",
                                 mutation_scale=22, color=TEAL, lw=2))

    # ---- Stage 3: what's sent -------------------------------------------- #
    ax.text(12.0, 5.7, s["s3_h"], fontsize=13, fontweight="bold", color=INK, ha="center")
    ax.text(12.0, 5.32, s["s3_sub"], fontsize=10.5, color=MUTE, ha="center", va="top")
    for i, (lab, col) in enumerate(zip(s["sent"], (TEAL, TEAL, TEAL_L))):
        y = 3.7 - i * 0.5
        bubble(ax, 10.7, y, 2.6, 0.4, col)
        ax.text(10.85, y + 0.2, lab, fontsize=9, color="white" if col == TEAL else INK,
                va="center", fontweight="bold")
    ax.text(12.0, 1.75, s["s3_note"], fontsize=9, color=TEAL, ha="center", style="italic")

    # ---- bottom result banner -------------------------------------------- #
    bubble(ax, 0.9, -0.05, 12.4, 0.66, "#0f172a")
    ax.text(7.0, 0.28, s["banner"], fontsize=12, color="white", ha="center",
            va="center", fontweight="bold")

    fig.suptitle(s["title"], fontsize=17, fontweight="bold", color=INK, y=0.99)
    fig.tight_layout(rect=(0, 0.02, 1, 0.95))
    out = ROOT / s["file"]
    fig.savefig(out, dpi=200, facecolor="white")
    plt.close(fig)
    print(f"wrote {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=["en", "pt", "all"], default="all")
    args = ap.parse_args()
    for lang in (["en", "pt"] if args.lang == "all" else [args.lang]):
        render(lang)


if __name__ == "__main__":
    main()
