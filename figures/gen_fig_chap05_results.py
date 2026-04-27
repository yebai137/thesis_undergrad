#!/usr/bin/env python3
"""Generate Chapter 5 result figures from real experiment artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import mean

import matplotlib.font_manager as font_manager
import matplotlib.pyplot as plt
import numpy as np
from fontTools.ttLib import TTCollection


FIG_DIR = Path(__file__).resolve().parent
THESIS_DIR = FIG_DIR.parent
REPO_ROOT = THESIS_DIR.parent
PAPER_IMAGE_DIR = THESIS_DIR / "paper" / "image" / "generated"
TIMING_ROOT = REPO_ROOT / "logs" / "direct_runs" / "20260427_timing_instrumentation"

FONT_CACHE = FIG_DIR / ".cache" / "fonts"
NOTO_CJK_REGULAR_TTC = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
NOTO_CJK_BOLD_TTC = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")


def _extract_noto_sc_face(ttc_path: Path, output_path: Path) -> Path | None:
    if not ttc_path.exists():
        return None
    if output_path.exists() and output_path.stat().st_mtime >= ttc_path.stat().st_mtime:
        return output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    collection = TTCollection(str(ttc_path))
    collection.fonts[2].save(output_path)
    return output_path


FONT_REGULAR = _extract_noto_sc_face(NOTO_CJK_REGULAR_TTC, FONT_CACHE / "NotoSansCJKSC-Regular.otf")
FONT_BOLD = _extract_noto_sc_face(NOTO_CJK_BOLD_TTC, FONT_CACHE / "NotoSansCJKSC-Bold.otf")
for font_path in (FONT_REGULAR, FONT_BOLD):
    if font_path is not None and font_path.exists():
        font_manager.fontManager.addfont(str(font_path))

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Noto Sans CJK SC", "Noto Sans CJK JP", "Droid Sans Fallback", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "font.size": 10,
    "axes.titlesize": 10.5,
    "axes.titleweight": "bold",
    "axes.labelsize": 10,
    "legend.fontsize": 8.2,
    "legend.frameon": False,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.18,
    "grid.linestyle": "-",
    "lines.linewidth": 1.9,
    "lines.markersize": 5.5,
})

COLORS = {
    "blue": "#264653",
    "teal": "#2A9D8F",
    "gold": "#E9C46A",
    "orange": "#F4A261",
    "coral": "#E76F51",
    "sky": "#56B4E9",
    "gray": "#7B8794",
}

HATCHES = ["////", "\\\\\\\\", "....", "xxxx", "----"]


def _save(fig: plt.Figure, stem: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    PAPER_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    for out_dir in (FIG_DIR, PAPER_IMAGE_DIR):
        fig.savefig(out_dir / f"{stem}.pdf")
        fig.savefig(out_dir / f"{stem}.png")
    plt.close(fig)


def _float(row: dict[str, str], key: str) -> float:
    value = row.get(key, "")
    return float(value) if value not in ("", None) else 0.0


def _load_batch_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(TIMING_ROOT.glob("iter_01/artifacts/chunk*/pulled/per_image.csv")):
        with path.open(newline="") as fp:
            rows.extend(csv.DictReader(fp))
    if not rows:
        raise FileNotFoundError("No batch timing rows found")
    return rows


def _load_video_summary() -> dict:
    matches = list(TIMING_ROOT.glob(
        "iter_02/artifacts/main/pulled/direct_video_metrics_*/video_metrics_summary.json"
    ))
    if not matches:
        raise FileNotFoundError("No video timing summary found")
    return json.loads(matches[0].read_text())


def fig_detection_metrics() -> None:
    overall_metrics = {
        "Precision": 0.901,
        "Recall": 0.923,
        "F1": 0.912,
        "mAP@0.5": 0.910,
    }
    class_metrics = {
        "person": {"Recall": 0.888, "mAP@0.5": 0.869},
        "ebike": {"Recall": 0.961, "mAP@0.5": 0.952},
    }

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(7.4, 3.35),
        gridspec_kw={"width_ratios": [1.08, 1.0]},
    )

    names = list(overall_metrics)
    values = [overall_metrics[name] for name in names]
    bars = axes[0].bar(
        names,
        values,
        color=[COLORS["blue"], COLORS["teal"], COLORS["gold"], COLORS["coral"]],
        edgecolor="#2C2C2C",
        linewidth=0.45,
    )
    for bar, hatch in zip(bars, HATCHES):
        bar.set_hatch(hatch)
    axes[0].set_title("总体检测指标")
    axes[0].set_ylabel("指标值")
    axes[0].set_ylim(0.84, 0.94)
    axes[0].bar_label(bars, labels=[f"{v:.3f}" for v in values], padding=2, fontsize=8)

    x = np.arange(len(class_metrics))
    width = 0.34
    recalls = [class_metrics[name]["Recall"] for name in class_metrics]
    maps = [class_metrics[name]["mAP@0.5"] for name in class_metrics]
    bars_recall = axes[1].bar(
        x - width / 2,
        recalls,
        width,
        label="Recall",
        color=COLORS["teal"],
        edgecolor="#2C2C2C",
        linewidth=0.45,
        hatch="////",
    )
    bars_map = axes[1].bar(
        x + width / 2,
        maps,
        width,
        label="mAP@0.5",
        color=COLORS["coral"],
        edgecolor="#2C2C2C",
        linewidth=0.45,
        hatch="....",
    )
    axes[1].set_title("分类别指标")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(list(class_metrics))
    axes[1].set_ylim(0.82, 1.00)
    axes[1].legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2)
    axes[1].bar_label(bars_recall, labels=[f"{v:.3f}" for v in recalls], padding=2, fontsize=8)
    axes[1].bar_label(bars_map, labels=[f"{v:.3f}" for v in maps], padding=2, fontsize=8)

    fig.tight_layout(rect=[0, 0.10, 1, 1])
    _save(fig, "fig_chap05_detection_metrics")


def fig_threshold_sensitivity() -> None:
    conf = np.array([0.20, 0.25, 0.30, 0.35])
    precision = np.array([0.911, 0.921, 0.925, 0.935])
    recall = np.array([0.919, 0.916, 0.912, 0.909])
    f1 = np.array([0.915, 0.919, 0.919, 0.922])
    ebike_recall = np.array([0.957, 0.957, 0.956, 0.956])
    person_recall = np.array([0.884, 0.878, 0.872, 0.866])

    fig, ax = plt.subplots(figsize=(7.2, 3.55))
    ax.plot(conf, precision, marker="o", linestyle="-", label="Precision", color=COLORS["blue"])
    ax.plot(conf, recall, marker="s", linestyle="--", label="Recall", color=COLORS["teal"])
    ax.plot(conf, f1, marker="^", linestyle="-.", label="F1", color=COLORS["coral"])
    ax.plot(conf, ebike_recall, marker="D", linestyle=":", label="ebike Recall", color=COLORS["gold"])
    ax.plot(conf, person_recall, marker="v", linestyle=(0, (5, 2, 1, 2)), label="person Recall", color=COLORS["gray"])
    ax.set_title("置信度阈值敏感性")
    ax.set_xlabel("置信度阈值")
    ax.set_ylabel("指标值")
    ax.set_xticks(conf)
    ax.set_ylim(0.84, 0.97)
    ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.24), columnspacing=1.2)
    fig.tight_layout(rect=[0, 0.18, 1, 1])
    _save(fig, "fig_chap05_threshold_sensitivity")


def fig_timing_breakdown() -> None:
    batch_rows = _load_batch_rows()
    video_summary = _load_video_summary()
    video_timing = video_summary["timing_ms_average"]

    values = [
        mean(_float(row, "elapsed_ms") for row in batch_rows),
        mean(_float(row, "frame_proc_ms") for row in batch_rows),
        mean(_float(row, "model_execute_ms") for row in batch_rows),
        video_timing["frame_proc_ms"],
        video_timing["model_execute_ms"],
    ]
    labels = [
        "Batch\n端到端",
        "Batch\n单帧处理",
        "Batch\n模型执行",
        "Video\n单帧处理",
        "Video\n模型执行",
    ]

    fig, ax = plt.subplots(figsize=(7.2, 3.55))
    colors = [COLORS["gray"], COLORS["teal"], COLORS["coral"], COLORS["sky"], COLORS["orange"]]
    bars = ax.bar(labels, values, color=colors, edgecolor="#2C2C2C", linewidth=0.45)
    for bar, hatch in zip(bars, HATCHES):
        bar.set_hatch(hatch)
    ax.set_title("板端分段计时结果（不同运行口径）")
    ax.set_ylabel("耗时 / ms（log）")
    ax.set_yscale("log")
    ax.set_ylim(5, 2200)
    ax.axhline(
        33.3,
        color=COLORS["blue"],
        linestyle="--",
        linewidth=1.1,
        alpha=0.82,
        label="30 fps 帧间隔 33.3 ms",
    )
    ax.bar_label(bars, labels=[f"{v:.1f}" for v in values], padding=3, fontsize=8)
    ax.legend(loc="upper right")
    fig.tight_layout()
    _save(fig, "fig_chap05_timing_breakdown")


def main() -> None:
    fig_detection_metrics()
    fig_threshold_sensitivity()
    fig_timing_breakdown()
    print(f"Saved figures to {FIG_DIR} and {PAPER_IMAGE_DIR}")


if __name__ == "__main__":
    main()
