#!/usr/bin/env python3
"""Generate assets/how-it-works.png — a plain-language explainer anyone can read.

A conceptual (not data) diagram: every AI turn re-sends the whole conversation;
B.I.O.M.A. trims the stale part in ~1 µs before it is sent; the model gets a
small, clean payload and returns the same answer. No numbers to parse.
"""
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


def bubble(ax, x, y, w, h, color, edge=None):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.006,rounding_size=0.02",
                                linewidth=0, facecolor=color, edgecolor=edge or color))


def main():
    fig, ax = plt.subplots(figsize=(14, 6.2))
    ax.set_xlim(0, 14); ax.set_ylim(0, 6.2); ax.axis("off")
    fig.patch.set_facecolor("white")

    # ---- Stage 1: the problem -------------------------------------------- #
    ax.text(2.1, 5.7, "1 · The problem", fontsize=13, fontweight="bold", color=INK, ha="center")
    ax.text(2.1, 5.32, "Every turn re-sends the ENTIRE chat.\n50–60% of it is dead weight.",
            fontsize=10.5, color=MUTE, ha="center", va="top")
    labels = ["system", "turn 1", "turn 2", "turn 3", "turn 4", "turn 5", "turn 6", "…"]
    for i, lab in enumerate(labels):
        y = 4.05 - i * 0.42
        stale = i not in (0,)  # system stays; most turns are stale
        bubble(ax, 0.9, y, 2.4, 0.34, "#e2e8f0" if stale else "#cbd5e1")
        ax.text(1.02, y + 0.17, lab, fontsize=8.5, color=SLATE_D, va="center")
        if stale and i not in (7,):
            ax.text(3.05, y + 0.17, "stale", fontsize=7, color="#b91c1c", va="center", ha="right")
    ax.text(2.1, 0.5, "grows every single turn", fontsize=9, color="#b91c1c", ha="center", style="italic")

    # arrow 1
    ax.add_patch(FancyArrowPatch((3.7, 3.1), (5.0, 3.1), arrowstyle="-|>",
                                 mutation_scale=22, color=SLATE, lw=2))

    # ---- Stage 2: B.I.O.M.A. --------------------------------------------- #
    bubble(ax, 5.1, 1.6, 3.7, 3.0, "#f0fdfa", edge=TEAL)
    ax.add_patch(FancyBboxPatch((5.1, 1.6), 3.7, 3.0, boxstyle="round,pad=0.01,rounding_size=0.05",
                                linewidth=1.6, facecolor="none", edgecolor=TEAL))
    ax.text(6.95, 4.15, "B.I.O.M.A.", fontsize=15, fontweight="bold", color=TEAL, ha="center")
    ax.text(6.95, 3.72, "context apoptosis", fontsize=10.5, color=TEAL, ha="center", style="italic")
    ax.text(6.95, 3.2, "Runs inside your app, in ~1 µs.\nKeeps what matters,\ndrops the stale history —\nbefore anything is sent.",
            fontsize=10, color=INK, ha="center", va="center")
    ax.text(6.95, 1.85, "your provider · your keys · no rewrite", fontsize=8.5, color=MUTE, ha="center")

    # arrow 2
    ax.add_patch(FancyArrowPatch((8.9, 3.1), (10.2, 3.1), arrowstyle="-|>",
                                 mutation_scale=22, color=TEAL, lw=2))

    # ---- Stage 3: what's sent -------------------------------------------- #
    ax.text(12.0, 5.7, "3 · What's actually sent", fontsize=13, fontweight="bold", color=INK, ha="center")
    ax.text(12.0, 5.32, "A small, clean payload.\nSame answer from the model.",
            fontsize=10.5, color=MUTE, ha="center", va="top")
    for i, (lab, col) in enumerate([("system", TEAL), ("what matters", TEAL), ("your question", TEAL_L)]):
        y = 3.7 - i * 0.5
        bubble(ax, 10.7, y, 2.6, 0.4, col)
        ax.text(10.85, y + 0.2, lab, fontsize=9, color="white" if col == TEAL else INK, va="center", fontweight="bold")
    ax.text(12.0, 1.75, "the model answers exactly as before", fontsize=9, color=TEAL, ha="center", style="italic")

    # ---- bottom result banner -------------------------------------------- #
    bubble(ax, 0.9, -0.05, 12.4, 0.66, "#0f172a")
    ax.set_ylim(-0.2, 6.2)
    ax.text(7.0, 0.28,
            "Same answer  ·  ~84% fewer tokens  ·  less cost, energy & carbon  ·  and you can prove it",
            fontsize=12, color="white", ha="center", va="center", fontweight="bold")

    fig.suptitle("How B.I.O.M.A. works — in plain English",
                 fontsize=17, fontweight="bold", color=INK, y=0.99)
    fig.tight_layout(rect=(0, 0.02, 1, 0.95))
    out = ROOT / "how-it-works.png"
    fig.savefig(out, dpi=200, facecolor="white")
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
