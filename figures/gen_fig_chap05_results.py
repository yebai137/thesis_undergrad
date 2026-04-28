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
FULL_VAL_METRICS = REPO_ROOT / "logs" / "direct_runs" / "20260419_phase3_3_full_val_synced" / "iter_01" / "analysis" / "performance_summary.json"
THRESHOLD_REPORT = REPO_ROOT / "doc" / "reports" / "2026-04-25_Thesis_Threshold_Sensitivity_Recompute.json"

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


def _load_full_val_overall() -> dict:
    payload = json.loads(FULL_VAL_METRICS.read_text())
    return payload["overall"]


def _micro_overall(classes: list[dict]) -> dict[str, float]:
    tp = sum(float(item.get("tp", 0.0)) for item in classes)
    fp = sum(float(item.get("fp", 0.0)) for item in classes)
    fn = sum(float(item.get("fn", 0.0)) for item in classes)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def _candidate_campaign_roots(campaign_id: str) -> list[Path]:
    exact = REPO_ROOT / "logs" / "direct_runs" / campaign_id
    roots: list[Path] = []
    if exact.exists():
        roots.append(exact)

    retry_pattern = f"{campaign_id}_r*"
    retry_roots = sorted(
        (REPO_ROOT / "logs" / "direct_runs").glob(retry_pattern),
        key=lambda path: int(path.name.rsplit("_r", 1)[1]) if "_r" in path.name and path.name.rsplit("_r", 1)[1].isdigit() else -1,
        reverse=True,
    )
    roots.extend(path for path in retry_roots if path not in roots)
    return roots


def _load_threshold_rows() -> list[dict]:
    payload = json.loads(THRESHOLD_REPORT.read_text())
    rows: list[dict] = []
    for item in payload["thresholds"]:
        classes = item["classes"]
        overall = item.get("overall") or _micro_overall(classes)
        rows.append({
            "conf": float(item["score_threshold"]),
            "precision": float(overall["precision"]),
            "recall": float(overall["recall"]),
            "f1": float(overall["f1"]),
            "person_recall": float(classes[0]["recall"]),
            "ebike_recall": float(classes[1]["recall"]),
            "predictions": int(item.get("prediction_count", overall.get("pred", 0))),
        })
    return rows


def _load_summary_from_campaign(campaign_id: str) -> dict | None:
    for campaign_root in _candidate_campaign_roots(campaign_id):
        candidates = sorted(campaign_root.glob("iter_*/analysis/split_val_summary.json"))
        if not candidates:
            candidates = sorted(campaign_root.glob("iter_*/analysis/overall_summary.json"))
        if not candidates:
            candidates = sorted(campaign_root.glob("iter_*/analysis/performance_summary.json"))
        if not candidates:
            continue
        payload = json.loads(candidates[-1].read_text())
        summary = payload["overall"] if "overall" in payload else payload
        if int(summary.get("failure_count", 0) or 0) != 0:
            continue
        return summary
    return None


def _load_video_metric_summary(campaign_id: str) -> dict | None:
    for campaign_root in _candidate_campaign_roots(campaign_id):
        candidates = sorted(campaign_root.glob("iter_*/analysis/summary.json"))
        if not candidates:
            continue
        return json.loads(candidates[-1].read_text())
    return None


def _load_video_stability_row(label: str, campaign_id: str) -> dict | None:
    for campaign_root in _candidate_campaign_roots(campaign_id):
        summary_candidates = sorted(campaign_root.glob("iter_*/analysis/summary.json"))
        event_candidates = sorted(campaign_root.glob("iter_*/analysis/event_timeline.json"))
        frame_candidates = sorted(campaign_root.glob(
            "iter_*/artifacts/main/pulled/direct_video_metrics_*/frame_detections.jsonl"
        ))
        if not summary_candidates or not event_candidates or not frame_candidates:
            continue
        summary = json.loads(summary_candidates[-1].read_text())
        events = json.loads(event_candidates[-1].read_text()).get("events", [])
        rows = [json.loads(line) for line in frame_candidates[-1].read_text().splitlines() if line.strip()]
        if not rows:
            continue

        frame_proc_values = [
            float(row.get("timing_ms", {}).get("frame_proc_ms", 0.0))
            for row in rows
            if row.get("timing_ms")
        ]
        model_execute_values = [
            float(row.get("timing_ms", {}).get("model_execute_ms", 0.0))
            for row in rows
            if row.get("timing_ms")
        ]
        present_frames = sum(1 for row in rows if int(row.get("person_count", 0) or 0) > 0)
        zero_segments: list[int] = []
        current_zero = 0
        for row in rows:
            if int(row.get("person_count", 0) or 0) == 0:
                current_zero += 1
            elif current_zero:
                zero_segments.append(current_zero)
                current_zero = 0
        if current_zero:
            zero_segments.append(current_zero)

        person_flash_windows = sum(
            1 for event in events if event.get("dominant_issue") == "person_flash"
        )
        person_flash_frames = sum(
            int(event.get("issue_counts", {}).get("person_flash", 0) or 0)
            for event in events
        )

        return {
            "label": label,
            "frame_count": int(summary.get("video", {}).get("frame_count", len(rows)) or len(rows)),
            "frame_proc": mean(frame_proc_values) if frame_proc_values else 0.0,
            "model_execute": mean(model_execute_values) if model_execute_values else 0.0,
            "retention": present_frames / len(rows),
            "flash_windows": person_flash_windows,
            "flash_frames": person_flash_frames,
            "zero_segments": len(zero_segments),
            "max_zero_segment": max(zero_segments or [0]),
        }
    return None


def fig_detection_metrics() -> None:
    overall = _load_full_val_overall()
    classes = {item["class_name"]: item for item in overall["classes"]}
    micro = _micro_overall(overall["classes"])
    overall_metrics = {
        "Precision": micro["precision"],
        "Recall": micro["recall"],
        "F1": micro["f1"],
        "mAP@0.5": overall["map50"],
    }
    class_metrics = {
        "person": {"Recall": classes["person"]["recall"], "mAP@0.5": classes["person"]["ap50"]},
        "ebike": {"Recall": classes["ebike"]["recall"], "mAP@0.5": classes["ebike"]["ap50"]},
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
    rows = _load_threshold_rows()
    conf = np.array([row["conf"] for row in rows])
    precision = np.array([row["precision"] for row in rows])
    recall = np.array([row["recall"] for row in rows])
    f1 = np.array([row["f1"] for row in rows])
    ebike_recall = np.array([row["ebike_recall"] for row in rows])
    person_recall = np.array([row["person_recall"] for row in rows])
    predictions = np.array([row["predictions"] for row in rows])

    fig, ax = plt.subplots(figsize=(7.35, 3.75))
    ax.plot(conf, precision, marker="o", linestyle="-", label="Precision", color=COLORS["blue"])
    ax.plot(conf, recall, marker="s", linestyle="--", label="Recall", color=COLORS["teal"])
    ax.plot(conf, f1, marker="^", linestyle="-.", label="F1", color=COLORS["coral"])
    ax.plot(conf, ebike_recall, marker="D", linestyle=":", label="ebike Recall", color=COLORS["gold"])
    ax.plot(conf, person_recall, marker="v", linestyle=(0, (5, 2, 1, 2)), label="person Recall", color=COLORS["gray"])
    ax2 = ax.twinx()
    ax2.plot(conf, predictions, marker="x", linestyle="-", label="Pred boxes", color="#4B5563", alpha=0.75)
    ax2.set_ylabel("预测框数量")
    ax2.set_ylim(max(0, predictions.min() - 60), predictions.max() + 60)
    ax.set_title("置信度阈值敏感性")
    ax.set_xlabel("置信度阈值")
    ax.set_ylabel("指标值")
    ax.set_xticks(conf)
    ax.set_ylim(0.84, 0.98)
    handles, labels = ax.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(handles + handles2, labels + labels2, ncol=3, loc="upper center",
              bbox_to_anchor=(0.5, -0.24), columnspacing=1.2)
    fig.tight_layout(rect=[0, 0.18, 1, 1])
    _save(fig, "fig_chap05_threshold_sensitivity")


def fig_nms_sensitivity() -> bool:
    configs = [
        ("0.35", "20260428_thesis_consistency_nms035"),
        ("0.45", "20260428_thesis_consistency_nms045"),
        ("0.55", "20260428_thesis_consistency_nms055"),
    ]
    rows = []
    for nms_label, campaign_id in configs:
        summary = _load_summary_from_campaign(campaign_id)
        if summary is None:
            print(f"skip fig_chap05_nms_sensitivity: missing {campaign_id}")
            return False
        classes = {item["class_name"]: item for item in summary["classes"]}
        rows.append({
            "nms": float(nms_label),
            "person_f1": classes["person"]["f1"],
            "ebike_f1": classes["ebike"]["f1"],
            "fp": sum(item["fp"] for item in summary["classes"]),
            "fn": sum(item["fn"] for item in summary["classes"]),
            "pred": sum(item["pred"] for item in summary["classes"]),
        })

    nms = np.array([row["nms"] for row in rows])
    fig, axes = plt.subplots(1, 2, figsize=(7.35, 3.35))
    axes[0].plot(nms, [row["person_f1"] for row in rows], marker="o", label="person F1", color=COLORS["blue"])
    axes[0].plot(nms, [row["ebike_f1"] for row in rows], marker="s", label="ebike F1", color=COLORS["coral"])
    axes[0].set_title("分类别 F1")
    axes[0].set_xlabel("NMS IoU 阈值")
    axes[0].set_ylabel("F1")
    axes[0].set_xticks(nms)
    axes[0].legend()

    width = 0.018
    axes[1].bar(nms - width, [row["fp"] for row in rows], width=width, label="FP", color=COLORS["orange"])
    axes[1].bar(nms, [row["fn"] for row in rows], width=width, label="FN", color=COLORS["teal"])
    axes[1].bar(nms + width, [row["pred"] for row in rows], width=width, label="Pred", color=COLORS["gray"])
    axes[1].set_title("错误与预测框数量")
    axes[1].set_xlabel("NMS IoU 阈值")
    axes[1].set_xticks(nms)
    axes[1].legend()
    fig.tight_layout()
    _save(fig, "fig_chap05_nms_sensitivity")
    return True


def fig_postprocess_ablation() -> bool:
    configs = [
        ("full", "20260428_thesis_consistency_cleanup_full"),
        ("safe", "20260428_thesis_consistency_cleanup_safe"),
        ("off", "20260428_thesis_consistency_cleanup_off"),
    ]
    rows = []
    for label, campaign_id in configs:
        summary = _load_summary_from_campaign(campaign_id)
        if summary is None:
            print(f"skip fig_chap05_postprocess_ablation: missing {campaign_id}")
            return False
        classes = {item["class_name"]: item for item in summary["classes"]}
        rows.append({
            "label": label,
            "fp": sum(item["fp"] for item in summary["classes"]),
            "fn": sum(item["fn"] for item in summary["classes"]),
            "ebike_recall": classes["ebike"]["recall"],
        })

    x = np.arange(len(rows))
    fig, axes = plt.subplots(1, 2, figsize=(7.35, 3.35))
    axes[0].bar(x - 0.16, [row["fp"] for row in rows], width=0.32, label="FP", color=COLORS["orange"])
    axes[0].bar(x + 0.16, [row["fn"] for row in rows], width=0.32, label="FN", color=COLORS["teal"])
    axes[0].set_xticks(x)
    axes[0].set_xticklabels([row["label"] for row in rows])
    axes[0].set_title("后处理消融错误数")
    axes[0].legend()
    axes[1].plot(x, [row["ebike_recall"] for row in rows], marker="o", color=COLORS["coral"])
    axes[1].set_xticks(x)
    axes[1].set_xticklabels([row["label"] for row in rows])
    axes[1].set_ylim(0.85, 1.0)
    axes[1].set_title("ebike recall")
    fig.tight_layout()
    _save(fig, "fig_chap05_postprocess_ablation")
    return True


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


def fig_video_stability() -> bool:
    configs = [
        ("window=1", "20260428_thesis_consistency_video_smooth1"),
        ("window=5", "20260428_thesis_consistency_video_smooth5"),
    ]
    rows = []
    for label, campaign_id in configs:
        row = _load_video_stability_row(label, campaign_id)
        if row is None:
            print(f"skip fig_chap05_video_stability: missing {campaign_id}")
            return False
        rows.append(row)

    x = np.arange(len(rows))
    fig, axes = plt.subplots(1, 2, figsize=(7.35, 3.35))
    axes[0].bar(x - 0.16, [row["frame_proc"] for row in rows], width=0.32, label="frame_proc", color=COLORS["teal"])
    axes[0].bar(x + 0.16, [row["model_execute"] for row in rows], width=0.32, label="model_execute", color=COLORS["coral"])
    axes[0].set_xticks(x)
    axes[0].set_xticklabels([row["label"] for row in rows])
    axes[0].set_ylabel("耗时 / ms")
    axes[0].set_title("视频路径分段耗时")
    axes[0].legend()
    axes[0].bar_label(axes[0].containers[0], labels=[f"{row['frame_proc']:.1f}" for row in rows], padding=2, fontsize=8)
    axes[0].bar_label(axes[0].containers[1], labels=[f"{row['model_execute']:.1f}" for row in rows], padding=2, fontsize=8)

    axes[1].bar(
        x - 0.18,
        [row["flash_windows"] for row in rows],
        width=0.24,
        label="闪烁窗口",
        color=COLORS["orange"],
        edgecolor="#2C2C2C",
        linewidth=0.45,
        hatch="////",
    )
    axes[1].bar(
        x + 0.08,
        [row["max_zero_segment"] for row in rows],
        width=0.24,
        label="最长无输出段",
        color=COLORS["gray"],
        edgecolor="#2C2C2C",
        linewidth=0.45,
        hatch="....",
    )
    ax_retention = axes[1].twinx()
    ax_retention.plot(
        x,
        [row["retention"] * 100.0 for row in rows],
        marker="o",
        color=COLORS["teal"],
        label="检测保持率",
    )
    axes[1].set_xticks(x)
    axes[1].set_xticklabels([row["label"] for row in rows])
    axes[1].set_ylabel("事件/帧数")
    axes[1].set_title("连续输出稳定性")
    ax_retention.set_ylabel("保持率 / %")
    ax_retention.set_ylim(90, 100)
    handles, labels = axes[1].get_legend_handles_labels()
    handles2, labels2 = ax_retention.get_legend_handles_labels()
    axes[1].legend(handles + handles2, labels + labels2, loc="upper center", bbox_to_anchor=(0.5, -0.20), ncol=2)
    fig.tight_layout(rect=[0, 0.08, 1, 1])
    _save(fig, "fig_chap05_video_stability")
    return True


def main() -> None:
    fig_detection_metrics()
    fig_threshold_sensitivity()
    fig_nms_sensitivity()
    fig_postprocess_ablation()
    fig_video_stability()
    fig_timing_breakdown()
    print(f"Saved figures to {FIG_DIR} and {PAPER_IMAGE_DIR}")


if __name__ == "__main__":
    main()
