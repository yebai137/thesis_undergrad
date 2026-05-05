#!/usr/bin/env python3
"""Evaluate crowd keyframe predictions against YOLO labels."""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

CLASS_NAMES = {
    0: "person",
    1: "ebike",
}

CLASS_COLORS = {
    0: (64, 220, 96),
    1: (255, 180, 64),
}


@dataclass
class Box:
    class_id: int
    x1: float
    y1: float
    x2: float
    y2: float
    score: float = 1.0


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_font(size: int = 18) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size=size)
    except Exception:
        return ImageFont.load_default()


def image_size(path: Path) -> Tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def parse_yolo_box(parts: Sequence[str], width: int, height: int) -> Box:
    class_id = int(float(parts[0]))
    x_center = float(parts[1]) * width
    y_center = float(parts[2]) * height
    box_w = float(parts[3]) * width
    box_h = float(parts[4]) * height
    score = float(parts[5]) if len(parts) >= 6 else 1.0
    x1 = x_center - box_w / 2.0
    y1 = y_center - box_h / 2.0
    x2 = x_center + box_w / 2.0
    y2 = y_center + box_h / 2.0
    return Box(class_id=class_id, x1=x1, y1=y1, x2=x2, y2=y2, score=score)


def load_label_file(path: Path, width: int, height: int) -> List[Box]:
    if not path.exists():
        return []
    boxes: List[Box] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        boxes.append(parse_yolo_box(parts, width, height))
    return boxes


def rect_iou(lhs: Box, rhs: Box) -> float:
    inter_x1 = max(lhs.x1, rhs.x1)
    inter_y1 = max(lhs.y1, rhs.y1)
    inter_x2 = min(lhs.x2, rhs.x2)
    inter_y2 = min(lhs.y2, rhs.y2)
    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0
    inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
    lhs_area = max(0.0, lhs.x2 - lhs.x1) * max(0.0, lhs.y2 - lhs.y1)
    rhs_area = max(0.0, rhs.x2 - rhs.x1) * max(0.0, rhs.y2 - rhs.y1)
    union_area = lhs_area + rhs_area - inter_area
    if union_area <= 0.0:
        return 0.0
    return inter_area / union_area


def match_boxes(gt_boxes: List[Box], pred_boxes: List[Box], iou_threshold: float) -> Tuple[int, int, int]:
    matched_gt = set()
    matched_pred = set()
    candidates: List[Tuple[float, int, int]] = []
    for gt_idx, gt in enumerate(gt_boxes):
        for pred_idx, pred in enumerate(pred_boxes):
            if gt.class_id != pred.class_id:
                continue
            iou = rect_iou(gt, pred)
            if iou >= iou_threshold:
                candidates.append((iou, gt_idx, pred_idx))
    candidates.sort(reverse=True)
    tp = 0
    for _, gt_idx, pred_idx in candidates:
        if gt_idx in matched_gt or pred_idx in matched_pred:
            continue
        matched_gt.add(gt_idx)
        matched_pred.add(pred_idx)
        tp += 1
    fp = len(pred_boxes) - len(matched_pred)
    fn = len(gt_boxes) - len(matched_gt)
    return tp, fp, fn


def draw_text_box(draw: ImageDraw.ImageDraw, xy: Tuple[int, int], text: str, font: ImageFont.ImageFont, fill: Tuple[int, int, int], background: Tuple[int, int, int]) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x0, y0 = xy
    draw.rectangle([x0, y0, x0 + text_w + 12, y0 + text_h + 8], fill=background)
    draw.text((x0 + 6, y0 + 4), text, fill=fill, font=font)


def draw_overlay(image_path: Path, gt_boxes: List[Box], pred_boxes: List[Box], output_path: Path, title: str) -> None:
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = load_font(16)
    title_font = load_font(18)

    for box in gt_boxes:
        color = CLASS_COLORS.get(box.class_id, (255, 255, 255))
        draw.rectangle([box.x1, box.y1, box.x2, box.y2], outline=color, width=3)
        draw_text_box(draw, (int(box.x1) + 4, int(box.y1) + 4), f"GT {_class_name(box.class_id)}", font, (255, 255, 255), (0, 0, 0))

    for box in pred_boxes:
        color = CLASS_COLORS.get(box.class_id, (255, 255, 255))
        draw.rectangle([box.x1, box.y1, box.x2, box.y2], outline=color, width=2)
        draw_text_box(
            draw,
            (int(box.x1) + 4, max(4, int(box.y2) - 28)),
            f"Pred {_class_name(box.class_id)} {box.score:.2f}",
            font,
            (255, 255, 255),
            (0, 0, 0),
        )

    draw_text_box(draw, (12, 12), title, title_font, (255, 255, 255), (0, 0, 0))
    ensure_dir(output_path.parent)
    image.save(output_path, quality=95)


def write_contact_sheet(image_paths: Sequence[Path], output_path: Path, title: str, columns: int = 4) -> None:
    if not image_paths:
        return
    thumbs: List[Image.Image] = []
    for path in image_paths:
        image = Image.open(path).convert("RGB")
        image.thumbnail((320, 180))
        thumbs.append(image)
    font = load_font(18)
    title_font = load_font(22)
    margin = 16
    cell_w = 320
    cell_h = 180
    rows = int(math.ceil(len(thumbs) / columns))
    canvas = Image.new(
        "RGB",
        (margin * 2 + columns * cell_w + max(0, columns - 1) * margin, margin * 3 + 42 + rows * cell_h + max(0, rows - 1) * margin),
        (18, 18, 18),
    )
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, margin), title, fill=(255, 255, 255), font=title_font)
    for idx, thumb in enumerate(thumbs):
        row = idx // columns
        col = idx % columns
        x0 = margin + col * (cell_w + margin)
        y0 = margin * 2 + 42 + row * (cell_h + margin)
        canvas.paste(thumb, (x0 + (cell_w - thumb.width) // 2, y0 + (cell_h - thumb.height) // 2))
        draw.rectangle([x0, y0, x0 + cell_w, y0 + cell_h], outline=(90, 90, 90), width=2)
        draw.text((x0 + 8, y0 + 8), image_paths[idx].name, fill=(255, 255, 255), font=font)
    ensure_dir(output_path.parent)
    canvas.save(output_path, quality=95)


def _class_name(class_id: int) -> str:
    return CLASS_NAMES.get(int(class_id), f"cls{class_id}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate crowd keyframe predictions against YOLO labels")
    parser.add_argument("--images-dir", required=True)
    parser.add_argument("--labels-dir", required=True, help="Ground-truth YOLO label directory")
    parser.add_argument("--pred-labels-dir", required=True, help="Predicted YOLO label directory")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--top-k", type=int, default=16)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    images_dir = Path(args.images_dir)
    labels_dir = Path(args.labels_dir)
    pred_labels_dir = Path(args.pred_labels_dir)
    output_dir = ensure_dir(Path(args.output_dir))

    per_image_rows: List[Dict[str, object]] = []
    class_stats = {
        0: {"tp": 0, "fp": 0, "fn": 0},
        1: {"tp": 0, "fp": 0, "fn": 0},
    }

    for image_path in sorted(images_dir.iterdir()):
        if image_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        width, height = image_size(image_path)
        gt_boxes = load_label_file(labels_dir / f"{image_path.stem}.txt", width, height)
        pred_boxes = load_label_file(pred_labels_dir / f"{image_path.stem}.txt", width, height)
        gt_person = [box for box in gt_boxes if box.class_id == 0]
        pred_person = [box for box in pred_boxes if box.class_id == 0]
        gt_ebike = [box for box in gt_boxes if box.class_id == 1]
        pred_ebike = [box for box in pred_boxes if box.class_id == 1]
        for class_id, gt_list, pred_list in ((0, gt_person, pred_person), (1, gt_ebike, pred_ebike)):
            tp, fp, fn = match_boxes(gt_list, pred_list, args.iou_threshold)
            class_stats[class_id]["tp"] += tp
            class_stats[class_id]["fp"] += fp
            class_stats[class_id]["fn"] += fn
        per_image_rows.append(
            {
                "image_name": image_path.name,
                "gt_person_count": len(gt_person),
                "pred_person_count": len(pred_person),
                "gt_ebike_count": len(gt_ebike),
                "pred_ebike_count": len(pred_ebike),
                "person_abs_count_error": abs(len(pred_person) - len(gt_person)),
                "ebike_abs_count_error": abs(len(pred_ebike) - len(gt_ebike)),
            }
        )

    def precision(tp: int, fp: int) -> float:
        return float(tp / (tp + fp)) if tp + fp > 0 else 0.0

    def recall(tp: int, fn: int) -> float:
        return float(tp / (tp + fn)) if tp + fn > 0 else 0.0

    summary = {
        "iou_threshold": args.iou_threshold,
        "images_evaluated": len(per_image_rows),
        "classes": {
            _class_name(class_id): {
                "tp": stats["tp"],
                "fp": stats["fp"],
                "fn": stats["fn"],
                "precision": precision(stats["tp"], stats["fp"]),
                "recall": recall(stats["tp"], stats["fn"]),
            }
            for class_id, stats in class_stats.items()
        },
        "person_mean_abs_count_error": (
            sum(float(row["person_abs_count_error"]) for row in per_image_rows) / len(per_image_rows)
            if per_image_rows
            else 0.0
        ),
    }

    per_image_rows.sort(
        key=lambda row: (
            float(row["person_abs_count_error"]),
            float(row["ebike_abs_count_error"]),
            row["image_name"],
        ),
        reverse=True,
    )
    overlay_dir = ensure_dir(output_dir / "overlays")
    overlay_paths: List[Path] = []
    for row in per_image_rows[: max(0, args.top_k)]:
        image_path = images_dir / str(row["image_name"])
        width, height = image_size(image_path)
        gt_boxes = load_label_file(labels_dir / f"{image_path.stem}.txt", width, height)
        pred_boxes = load_label_file(pred_labels_dir / f"{image_path.stem}.txt", width, height)
        overlay_path = overlay_dir / image_path.name
        draw_overlay(
            image_path,
            gt_boxes,
            pred_boxes,
            overlay_path,
            title=(
                f"{image_path.name} "
                f"P:{row['pred_person_count']}/{row['gt_person_count']} "
                f"E:{row['pred_ebike_count']}/{row['gt_ebike_count']}"
            ),
        )
        overlay_paths.append(overlay_path)

    write_contact_sheet(overlay_paths[:16], output_dir / "overlay_contact_sheet.jpg", "crowd eval overlays")

    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (output_dir / "per_image.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(per_image_rows[0].keys()) if per_image_rows else ["image_name"])
        writer.writeheader()
        writer.writerows(per_image_rows)
    print(f"crowd evaluation written to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
