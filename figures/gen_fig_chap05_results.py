#!/usr/bin/env python3
"""Generate Chapter 5 result figures from real experiment artifacts."""

from __future__ import annotations

import csv
import json
import re
import shutil
from pathlib import Path
from statistics import mean

import matplotlib.font_manager as font_manager
import matplotlib.pyplot as plt
import numpy as np
from fontTools.ttLib import TTCollection
from PIL import Image, ImageDraw, ImageFont


FIG_DIR = Path(__file__).resolve().parent
THESIS_DIR = FIG_DIR.parent
REPO_ROOT = THESIS_DIR.parent
PAPER_IMAGE_DIR = THESIS_DIR / "paper" / "image" / "generated"
TIMING_ROOT = REPO_ROOT / "logs" / "direct_runs" / "20260427_timing_instrumentation"
FULL_VAL_METRICS = REPO_ROOT / "logs" / "direct_runs" / "20260419_phase3_3_full_val_synced" / "iter_01" / "analysis" / "performance_summary.json"
THRESHOLD_REPORT = REPO_ROOT / "doc" / "reports" / "2026-04-25_Thesis_Threshold_Sensitivity_Recompute.json"
TRAINING_RESULTS_CSV = REPO_ROOT / "runs" / "detect" / "elevator_train_100epoch3" / "results.csv"
TRAINING_VAL_PRED = REPO_ROOT / "runs" / "detect" / "elevator_train_100epoch3" / "val_batch0_pred.jpg"
COCO_BASELINE_LOG = REPO_ROOT / "logs" / "daily" / "2026-01-16.md"
FULL_VAL_ITER_ROOT = REPO_ROOT / "logs" / "direct_runs" / "20260419_phase3_3_full_val_synced" / "iter_01"
VAL_IMAGE_DIR = REPO_ROOT / "datasets" / "PandE" / "personAndEbike" / "images" / "val"

FONT_CACHE = FIG_DIR / ".cache" / "fonts"
NOTO_CJK_REGULAR_TTC = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
NOTO_CJK_BOLD_TTC = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")
DEJAVU_SANS = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
DEJAVU_SANS_BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


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


def _copy_generated_image(source: Path, stem: str, suffix: str = ".jpg") -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    PAPER_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    for out_dir in (FIG_DIR, PAPER_IMAGE_DIR):
        shutil.copy2(source, out_dir / f"{stem}{suffix}")


def _save_pil_image(image: Image.Image, stem: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    PAPER_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    rgb = image.convert("RGB")
    for out_dir in (FIG_DIR, PAPER_IMAGE_DIR):
        rgb.save(out_dir / f"{stem}.jpg", quality=95, optimize=True)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = DEJAVU_SANS_BOLD if bold else DEJAVU_SANS
    try:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    except OSError:
        pass
    return ImageFont.load_default()


def _float(row: dict[str, str], key: str) -> float:
    value = row.get(key, "")
    return float(value) if value not in ("", None) else 0.0


def _int(row: dict[str, str], key: str) -> int:
    value = row.get(key, "")
    return int(float(value)) if value not in ("", None) else 0


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


def _load_training_final_metrics() -> dict[str, float]:
    with TRAINING_RESULTS_CSV.open(newline="") as fp:
        rows = list(csv.DictReader(fp))
    if not rows:
        raise ValueError(f"No rows in {TRAINING_RESULTS_CSV}")
    final = rows[-1]
    precision = float(final["metrics/precision(B)"])
    recall = float(final["metrics/recall(B)"])
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "epoch": float(final["epoch"]),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "map50": float(final["metrics/mAP50(B)"]),
        "map50_95": float(final["metrics/mAP50-95(B)"]),
    }


def _load_coco_person_baseline() -> dict[str, float]:
    text = COCO_BASELINE_LOG.read_text()

    def percent(label: str) -> float:
        match = re.search(rf"\*\*{re.escape(label)}\*\*\s*\|\s*\*\*([0-9.]+)%\*\*", text)
        if not match:
            raise ValueError(f"Missing {label} in {COCO_BASELINE_LOG}")
        return float(match.group(1)) / 100.0

    f1_match = re.search(r"\*\*F1 Score\*\*\s*\|\s*\*\*([0-9.]+)\*\*", text)
    if not f1_match:
        raise ValueError(f"Missing F1 Score in {COCO_BASELINE_LOG}")
    return {
        "precision": percent("Precision"),
        "recall": percent("Recall"),
        "f1": float(f1_match.group(1)),
    }


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


def _load_full_val_qualitative_candidates() -> list[dict]:
    candidates: list[dict] = []
    artifact_root = FULL_VAL_ITER_ROOT / "artifacts"
    per_image_paths = sorted(
        artifact_root.glob("val_*/pulled/per_image.csv"),
        key=lambda path: path.parent.parent.name,
    )
    for per_image_path in per_image_paths:
        detections_path = per_image_path.with_name("detections.jsonl")
        if not detections_path.exists():
            continue
        detection_by_image = {}
        for line in detections_path.read_text().splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            detection_by_image[record["image_name"]] = record
        with per_image_path.open(newline="") as fp:
            for row in csv.DictReader(fp):
                if row.get("success") != "1":
                    continue
                if _int(row, "gt_person") <= 0 or _int(row, "gt_ebike") <= 0:
                    continue
                if _int(row, "tp_person") <= 0 or _int(row, "tp_ebike") <= 0:
                    continue
                if any(_int(row, key) != 0 for key in ("fp_person", "fp_ebike", "fn_person", "fn_ebike")):
                    continue
                image_path = VAL_IMAGE_DIR / row["image_name"]
                detection_record = detection_by_image.get(row["image_name"])
                if image_path.exists() and detection_record and detection_record.get("detections"):
                    candidates.append({
                        "image_name": row["image_name"],
                        "image_path": image_path,
                        "detections": detection_record["detections"],
                    })
    if len(candidates) < 6:
        raise ValueError(f"Need at least 6 qualitative board examples, found {len(candidates)}")
    return candidates


def _select_evenly(items: list[dict], count: int) -> list[dict]:
    if len(items) <= count:
        return items
    selected: list[dict] = []
    used: set[int] = set()
    for idx in [round(i * (len(items) - 1) / (count - 1)) for i in range(count)]:
        probe = idx
        while probe in used and probe + 1 < len(items):
            probe += 1
        while probe in used and probe > 0:
            probe -= 1
        used.add(probe)
        selected.append(items[probe])
    return selected


def _draw_detection_label(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    color: str,
    font: ImageFont.ImageFont,
    max_width: int,
    max_height: int,
    occupied: list[tuple[int, int, int, int]],
) -> None:
    x, y = xy
    left, top, right, bottom = draw.textbbox((x, y), text, font=font)
    label_h = bottom - top + 8
    label_w = right - left + 10
    x = max(0, min(x, max_width - label_w))
    label_y = max(0, y - label_h)
    bbox = (x, label_y, x + label_w, label_y + label_h)
    while any(not (bbox[2] <= other[0] or bbox[0] >= other[2] or bbox[3] <= other[1] or bbox[1] >= other[3]) for other in occupied):
        label_y = min(max_height - label_h, label_y + label_h + 2)
        bbox = (x, label_y, x + label_w, label_y + label_h)
        if label_y + label_h >= max_height:
            break
    draw.rectangle(bbox, fill=color)
    draw.text((bbox[0] + 5, bbox[1] + 3), text, fill="white", font=font)
    occupied.append(bbox)


def _render_board_panel(record: dict, size: tuple[int, int]) -> Image.Image:
    class_names = {0: "person", 1: "ebike"}
    class_colors = {0: "#0057D9", 1: "#00AFC7"}
    image = Image.open(record["image_path"]).convert("RGB")
    original_w, original_h = image.size
    panel_w, panel_h = size
    image = image.resize((panel_w, panel_h), Image.Resampling.LANCZOS)
    scale_x = panel_w / original_w
    scale_y = panel_h / original_h
    draw = ImageDraw.Draw(image)
    box_font = _font(22, bold=True)
    line_width = 5
    occupied_labels: list[tuple[int, int, int, int]] = []
    for det in record["detections"]:
        class_id = int(det.get("class_id", -1))
        color = class_colors.get(class_id, "#E76F51")
        x1 = max(0, min(panel_w - 1, int(round(float(det["x1"]) * scale_x))))
        y1 = max(0, min(panel_h - 1, int(round(float(det["y1"]) * scale_y))))
        x2 = max(0, min(panel_w - 1, int(round(float(det["x2"]) * scale_x))))
        y2 = max(0, min(panel_h - 1, int(round(float(det["y2"]) * scale_y))))
        draw.rectangle([x1, y1, x2, y2], outline=color, width=line_width)
        score = float(det.get("score", 0.0))
        label = f"{class_names.get(class_id, 'cls')} {score:.2f}"
        _draw_detection_label(draw, (x1, y1), label, color, box_font, panel_w, panel_h, occupied_labels)
    return image


def fig_training_val_predictions() -> None:
    _copy_generated_image(
        TRAINING_VAL_PRED,
        "fig_chap03_training_val_predictions",
        TRAINING_VAL_PRED.suffix,
    )


def fig_board_val_examples() -> None:
    records = _select_evenly(_load_full_val_qualitative_candidates(), 6)
    panel_size = (720, 405)
    caption_h = 42
    gutter = 18
    cols = 3
    rows = 2
    width = cols * panel_size[0] + (cols + 1) * gutter
    height = rows * (panel_size[1] + caption_h) + (rows + 1) * gutter
    sheet = Image.new("RGB", (width, height), "#F7F7F5")
    caption_font = _font(22, bold=True)
    for idx, record in enumerate(records):
        row = idx // cols
        col = idx % cols
        x = gutter + col * (panel_size[0] + gutter)
        y = gutter + row * (panel_size[1] + caption_h + gutter)
        panel = _render_board_panel(record, panel_size)
        sheet.paste(panel, (x, y))
        draw = ImageDraw.Draw(sheet)
        caption = f"({chr(ord('a') + idx)}) {record['image_name']}"
        draw.rectangle([x, y + panel_size[1], x + panel_size[0], y + panel_size[1] + caption_h], fill="white")
        draw.text((x + 12, y + panel_size[1] + 8), caption, fill="#264653", font=caption_font)
    _save_pil_image(sheet, "fig_chap05_board_val_examples")


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


def fig_stage_comparison() -> None:
    baseline = _load_coco_person_baseline()
    training = _load_training_final_metrics()
    board_overall = _load_full_val_overall()
    board = _micro_overall(board_overall["classes"])
    board["map50"] = float(board_overall["map50"])

    stages = [
        ("COCO-person\nbaseline", baseline),
        ("YOLOv8n\n训练阶段", training),
        ("Hi3516DV500\nFP16/OM", board),
    ]
    metrics = [
        ("Precision", "precision", COLORS["blue"], "////"),
        ("Recall", "recall", COLORS["teal"], "\\\\\\\\"),
        ("F1", "f1", COLORS["coral"], "...."),
    ]

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(7.45, 3.55),
        gridspec_kw={"width_ratios": [1.35, 0.82]},
    )

    x = np.arange(len(stages))
    width = 0.23
    for idx, (label, key, color, hatch) in enumerate(metrics):
        values = [stage[key] for _, stage in stages]
        bars = axes[0].bar(
            x + (idx - 1) * width,
            values,
            width=width,
            label=label,
            color=color,
            edgecolor="#2C2C2C",
            linewidth=0.45,
            hatch=hatch,
        )
        axes[0].bar_label(bars, labels=[f"{value:.3f}" for value in values], padding=2, fontsize=7.4)
    axes[0].set_title("同集阶段参照：P/R/F1")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels([name for name, _ in stages])
    axes[0].set_ylabel("指标值")
    axes[0].set_ylim(0.68, 1.02)

    map_labels = ["YOLOv8n\n训练阶段", "Hi3516DV500\nFP16/OM"]
    map_values = [training["map50"], board["map50"]]
    bars = axes[1].bar(
        np.arange(2),
        map_values,
        width=0.48,
        color=[COLORS["gold"], COLORS["sky"]],
        edgecolor="#2C2C2C",
        linewidth=0.45,
        hatch="----",
    )
    axes[1].set_title("mAP@0.5")
    axes[1].set_xticks(np.arange(2))
    axes[1].set_xticklabels(map_labels)
    axes[1].set_ylim(0.86, 1.00)
    axes[1].bar_label(bars, labels=[f"{value:.3f}" for value in map_values], padding=2, fontsize=8)
    axes[1].annotate(
        "下降 0.078",
        xy=(0.5, (map_values[0] + map_values[1]) / 2),
        xytext=(0.5, 0.965),
        textcoords="data",
        ha="center",
        va="center",
        fontsize=8,
        arrowprops={"arrowstyle": "<->", "linewidth": 0.9, "color": COLORS["gray"]},
        color=COLORS["blue"],
    )

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, bbox_to_anchor=(0.5, 0.01), frameon=False)
    fig.tight_layout(rect=[0, 0.13, 1, 1])
    _save(fig, "fig_chap05_stage_comparison")


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
    fig, axes = plt.subplots(1, 2, figsize=(7.35, 3.65))
    axes[0].plot(nms, [row["person_f1"] for row in rows], marker="o", label="person F1", color=COLORS["blue"])
    axes[0].plot(nms, [row["ebike_f1"] for row in rows], marker="s", label="ebike F1", color=COLORS["coral"])
    axes[0].set_title("分类别 F1")
    axes[0].set_xlabel("NMS IoU 阈值")
    axes[0].set_ylabel("F1")
    axes[0].set_xticks(nms)

    width = 0.018
    axes[1].bar(nms - width, [row["fp"] for row in rows], width=width, label="FP", color=COLORS["orange"])
    axes[1].bar(nms, [row["fn"] for row in rows], width=width, label="FN", color=COLORS["teal"])
    axes[1].bar(nms + width, [row["pred"] for row in rows], width=width, label="Pred", color=COLORS["gray"])
    axes[1].set_title("错误与预测框数量")
    axes[1].set_xlabel("NMS IoU 阈值")
    axes[1].set_ylabel("数量")
    axes[1].set_xticks(nms)
    handles0, labels0 = axes[0].get_legend_handles_labels()
    handles1, labels1 = axes[1].get_legend_handles_labels()
    fig.legend(
        handles0 + handles1,
        labels0 + labels1,
        loc="lower center",
        ncol=5,
        bbox_to_anchor=(0.5, 0.01),
        frameon=False,
        columnspacing=1.0,
    )
    fig.tight_layout(rect=[0, 0.14, 1, 1])
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
    fig, axes = plt.subplots(
        1,
        3,
        figsize=(7.35, 3.65),
        gridspec_kw={"width_ratios": [1.08, 1.08, 0.84]},
    )
    axes[0].bar(x - 0.16, [row["frame_proc"] for row in rows], width=0.32, label="frame_proc", color=COLORS["teal"])
    axes[0].bar(x + 0.16, [row["model_execute"] for row in rows], width=0.32, label="model_execute", color=COLORS["coral"])
    axes[0].set_xticks(x)
    axes[0].set_xticklabels([row["label"] for row in rows])
    axes[0].set_ylabel("耗时 / ms")
    axes[0].set_title("视频路径分段耗时")
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
    axes[1].set_xticks(x)
    axes[1].set_xticklabels([row["label"] for row in rows])
    axes[1].set_ylabel("事件/帧数")
    axes[1].set_title("连续输出稳定性")
    axes[1].bar_label(axes[1].containers[0], labels=[str(row["flash_windows"]) for row in rows], padding=2, fontsize=8)
    axes[1].bar_label(axes[1].containers[1], labels=[str(row["max_zero_segment"]) for row in rows], padding=2, fontsize=8)

    retention_bars = axes[2].bar(
        x,
        [row["retention"] * 100.0 for row in rows],
        width=0.42,
        color=COLORS["sky"],
        edgecolor="#2C2C2C",
        linewidth=0.45,
        hatch="\\\\\\\\",
    )
    axes[2].set_xticks(x)
    axes[2].set_xticklabels([row["label"] for row in rows])
    axes[2].set_ylim(95, 100)
    axes[2].set_ylabel("保持率 / %")
    axes[2].set_title("检测保持率")
    axes[2].bar_label(retention_bars, labels=[f"{row['retention'] * 100.0:.1f}" for row in rows], padding=2, fontsize=8)

    handles0, labels0 = axes[0].get_legend_handles_labels()
    handles1, labels1 = axes[1].get_legend_handles_labels()
    fig.legend(
        handles0 + handles1,
        labels0 + labels1,
        loc="lower center",
        ncol=4,
        bbox_to_anchor=(0.5, 0.01),
        frameon=False,
        columnspacing=1.0,
    )
    fig.tight_layout(rect=[0, 0.16, 1, 1])
    _save(fig, "fig_chap05_video_stability")
    return True


def main() -> None:
    fig_training_val_predictions()
    fig_stage_comparison()
    fig_detection_metrics()
    fig_board_val_examples()
    fig_threshold_sensitivity()
    fig_nms_sensitivity()
    fig_postprocess_ablation()
    fig_video_stability()
    fig_timing_breakdown()
    print(f"Saved figures to {FIG_DIR} and {PAPER_IMAGE_DIR}")


if __name__ == "__main__":
    main()
