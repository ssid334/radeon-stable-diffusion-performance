#!/usr/bin/env python3
"""Generate SVG/PNG charts for the MI50 vs RX 7700 XT report from data/*.json."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CHARTS = ROOT / "charts"

MI50 = "#d1495b"
RX = "#00798c"
DUAL = "#edae49"
DUAL_BIAS = "#6a4c93"
SEQ = "#8d99ae"
PAR = "#2a9d8f"

plt.rcParams.update({
    "figure.dpi": 160,
    "savefig.dpi": 160,
    "font.size": 10,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "axes.labelsize": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "svg.fonttype": "path",
})


def load(name: str) -> dict:
    with open(DATA / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


def save(fig: plt.Figure, stem: str) -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    for ext in ("svg", "png"):
        fig.savefig(CHARTS / f"{stem}.{ext}", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def annotate(ax, bars, fmt="{:.1f}", dy=1.5, size=9) -> None:
    for bar in bars:
        h = bar.get_height()
        if h != h or h <= 0:
            continue
        ax.annotate(
            fmt.format(h),
            (bar.get_x() + bar.get_width() / 2, h),
            xytext=(0, dy), textcoords="offset points",
            ha="center", va="bottom", fontsize=size,
        )


def single_card() -> None:
    rows = [
        ("SD1.5 512² / 20", "mi50-sd15-512-s20", "rx7700xt-sd15-512-s20"),
        ("SDXL 1024² / 20", "mi50-sdxl-1024-s20", "rx7700xt-sdxl-1024-s20"),
        ("SDXL 1024² / 30", "mi50-sdxl-1024-s30", "rx7700xt-sdxl-1024-s30"),
    ]
    labels = [r[0] for r in rows]
    mi = [load(r[1])["median_wall_s"] for r in rows]
    rx = [load(r[2])["median_wall_s"] for r in rows]

    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    x = range(len(rows))
    w = 0.36
    b1 = ax.bar([i - w / 2 for i in x], mi, w, label="MI50 32 GB", color=MI50)
    b2 = ax.bar([i + w / 2 for i in x], rx, w, label="RX 7700 XT 12 GB", color=RX)
    annotate(ax, b1)
    annotate(ax, b2)
    for i, (a, b) in enumerate(zip(mi, rx)):
        ax.annotate(f"{a / b:.2f}× faster", (i, max(a, b)), xytext=(0, 22),
                    textcoords="offset points", ha="center", fontsize=9,
                    color="#333333", fontweight="bold")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("End-to-end job wall time (s)")
    ax.set_title("Single-card generation latency (median)")
    ax.set_ylim(0, max(mi) * 1.22)
    ax.legend(frameon=False, loc="upper left")
    save(fig, "single-card-wall-time")


def phase_breakdown() -> None:
    rows = [
        ("SD1.5 512²/20 — MI50", "mi50-sd15-512-s20", MI50),
        ("SD1.5 512²/20 — RX 7700 XT", "rx7700xt-sd15-512-s20", RX),
        ("SDXL 1024²/20 — MI50", "mi50-sdxl-1024-s20", MI50),
        ("SDXL 1024²/20 — RX 7700 XT", "rx7700xt-sdxl-1024-s20", RX),
        ("SDXL 1024²/30 — MI50", "mi50-sdxl-1024-s30", MI50),
        ("SDXL 1024²/30 — RX 7700 XT", "rx7700xt-sdxl-1024-s30", RX),
    ]
    labels, sampling, decode, other, sample_vals = [], [], [], [], []
    for label, name, _ in rows:
        d = load(name)
        s, dec, wall = d["median_sampling_s"], d["median_decode_s"], d["median_wall_s"]
        labels.append(label)
        sampling.append(s)
        decode.append(dec)
        other.append(max(0.0, wall - s - dec))
        sample_vals.append(s)

    fig, ax = plt.subplots(figsize=(10, 5.0))
    y = list(range(len(rows)))[::-1]
    left = [0.0] * len(rows)
    for vals, color, lab in (
        (sampling, "#264653", "sampling"),
        (decode, "#2a9d8f", "VAE decode"),
        (other, "#e9c46a", "conditioning / overhead"),
    ):
        ax.barh(y, vals, left=left, color=color, label=lab, height=0.62)
        left = [a + b for a, b in zip(left, vals)]
    for yi, s, total in zip(y, sample_vals, left):
        ax.annotate(f"sample {s:.1f}s · total {total:.1f}s",
                    (total, yi), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=8.5)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Seconds")
    ax.set_title("Where the time goes: sampling vs VAE decode")
    ax.set_xlim(0, max(left) * 1.28)
    ax.grid(axis="x", alpha=0.25)
    ax.grid(axis="y", visible=False)
    ax.legend(frameon=False, loc="upper right")
    save(fig, "phase-breakdown")


def dual_single_task() -> None:
    groups = ["SDXL 1024² / 20", "SD1.5 512² / 20"]
    series = [
        ("MI50 alone", [load("mi50-sdxl-1024-s20")["median_wall_s"],
                        load("mi50-sd15-512-s20")["median_wall_s"]], MI50),
        ("RX 7700 XT alone", [load("rx7700xt-sdxl-1024-s20")["median_wall_s"],
                              load("rx7700xt-sd15-512-s20")["median_wall_s"]], RX),
        ("Dual split (layer)", [load("dual-sdxl-1024-s20-layer")["median_wall_s"],
                                load("dual-sd15-512-s20-layer")["median_wall_s"]], DUAL),
        ("Dual split, biased", [load("dual-sdxl-1024-s20-bias")["median_wall_s"],
                                float("nan")], DUAL_BIAS),
    ]
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    x = range(len(groups))
    n = len(series)
    w = 0.8 / n
    for i, (label, vals, color) in enumerate(series):
        pos = [j - 0.4 + w * (i + 0.5) for j in x]
        bars = ax.bar(pos, vals, w, label=label, color=color)
        annotate(ax, bars, size=8.5)
    ax.set_xticks(list(x))
    ax.set_xticklabels(groups)
    ax.set_ylabel("End-to-end job wall time (s)")
    ax.set_title("One task split across both cards vs a single card")
    ax.legend(frameon=False, ncol=2, loc="upper right")
    ax.set_ylim(0, 62)
    save(fig, "dual-single-task")


def dual_parallel() -> None:
    d = load("dual-parallel-sdxl-1024-s20")
    seq = d["sequential"]["pair_span_s"]
    par = d["parallel"]["pair_span_s"]
    speedup = d["speedup"]

    fig, ax = plt.subplots(figsize=(6.8, 4.4))
    bars = ax.bar(["Sequential\n(one card at a time)", "Parallel\n(both cards at once)"],
                  [seq, par], color=[SEQ, PAR], width=0.55)
    annotate(ax, bars, fmt="{:.1f} s", size=10)
    ax.annotate(f"{speedup:.2f}× throughput", (1, par), xytext=(0, 24),
                textcoords="offset points", ha="center", fontsize=10,
                fontweight="bold", color="#1d6f66")
    ax.set_ylabel("Wall time for two SDXL jobs (s)")
    ax.set_title("Two independent SDXL 1024²/20 jobs")
    ax.set_ylim(0, seq * 1.2)
    save(fig, "dual-parallel")


def main() -> None:
    single_card()
    phase_breakdown()
    dual_single_task()
    dual_parallel()
    print("\n".join(str(p) for p in sorted(CHARTS.glob("*.svg"))))


if __name__ == "__main__":
    main()
