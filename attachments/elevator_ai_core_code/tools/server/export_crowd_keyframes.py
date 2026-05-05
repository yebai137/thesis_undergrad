#!/usr/bin/env python3
"""Export crowd keyframes and seed labels from a board video iteration."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import cv2
from PIL import Image, ImageDraw, ImageFont

CLASS_NAMES = {
    0: "person",
    1: "ebike",
}

CLASS_COLORS = {
    0: (64, 220, 96),
    1: (255, 180, 64),
}


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_font(size: int = 18) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size=size)
    except Exception:
        return ImageFont.load_default()


def rect_iou(lhs: Dict[str, Any], rhs: Dict[str, Any]) -> float:
    inter_x1 = max(int(lhs["x1"]), int(rhs["x1"]))
    inter_y1 = max(int(lhs["y1"]), int(rhs["y1"]))
    inter_x2 = min(int(lhs["x2"]), int(rhs["x2"]))
    inter_y2 = min(int(lhs["y2"]), int(rhs["y2"]))
    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0
    inter_area = float((inter_x2 - inter_x1) * (inter_y2 - inter_y1))
    lhs_area = float(max(0, int(lhs["x2"]) - int(lhs["x1"])) * max(0, int(lhs["y2"]) - int(lhs["y1"])))
    rhs_area = float(max(0, int(rhs["x2"]) - int(rhs["x1"])) * max(0, int(rhs["y2"]) - int(rhs["y1"])))
    union_area = lhs_area + rhs_area - inter_area
    if union_area <= 0.0:
        return 0.0
    return inter_area / union_area


def duplicate_pair_count(detections: Sequence[Dict[str, Any]], class_id: int = 0, iou_threshold: float = 0.5) -> int:
    persons = [item for item in detections if int(item.get("class_id", -1)) == class_id]
    duplicates = 0
    for idx in range(len(persons)):
        for jdx in range(idx + 1, len(persons)):
            if rect_iou(persons[idx], persons[jdx]) >= iou_threshold:
                duplicates += 1
    return duplicates


def load_records(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        item = json.loads(line)
        item["frame_index"] = int(item.get("frame_index", len(records)))
        item["person_count"] = int(item.get("person_count", 0))
        item["smoothed_person_count"] = int(item.get("smoothed_person_count", item["person_count"]))
        item["ebike_count"] = int(item.get("ebike_count", 0))
        item["elapsed_ms"] = float(item.get("elapsed_ms", 0.0))
        detections = list(item.get("detections", []))
        item["detections"] = detections
        item["duplicate_pair_count"] = int(item.get("duplicate_pair_count", duplicate_pair_count(detections)))
        records.append(item)
    records.sort(key=lambda item: int(item["frame_index"]))
    return records


def evenly_spaced_indices(total: int, count: int) -> List[int]:
    if total <= 0 or count <= 0:
        return []
    if count >= total:
        return list(range(total))
    if count == 1:
        return [total // 2]
    indices: List[int] = []
    for slot in range(count):
        value = int(round(slot * (total - 1) / (count - 1)))
        if indices and value <= indices[-1]:
            value = min(total - 1, indices[-1] + 1)
        indices.append(value)
    return indices


def select_records(
    records: List[Dict[str, Any]],
    *,
    expected_person_count: int,
    train_count: int,
    val_count: int,
) -> List[Dict[str, Any]]:
    total_needed = train_count + val_count
    if len(records) <= total_needed:
        selected = list(records)
        for item in selected:
            item["selection_reason"] = "all_frames"
        return selected

    selected: List[Dict[str, Any]] = []
    selected_ids = set()

    def add_from_bucket(items: Iterable[Dict[str, Any]], count: int, reason: str) -> None:
        for item in items:
            frame_index = int(item["frame_index"])
            if frame_index in selected_ids:
                continue
            clone = dict(item)
            clone["selection_reason"] = reason
            selected.append(clone)
            selected_ids.add(frame_index)
            if len([entry for entry in selected if entry["selection_reason"] == reason]) >= count:
                break

    undercount_ranked = sorted(
        records,
        key=lambda item: (
            expected_person_count - int(item["person_count"]),
            int(item.get("duplicate_pair_count", 0)),
            -int(item["frame_index"]),
        ),
        reverse=True,
    )
    add_from_bucket(undercount_ranked, 12, "severe_undercount")

    drop_candidates: List[Dict[str, Any]] = []
    previous_person = int(records[0]["person_count"]) if records else 0
    for item in records:
        current_person = int(item["person_count"])
        delta = max(0, previous_person - current_person)
        clone = dict(item)
        clone["drop_delta"] = delta
        drop_candidates.append(clone)
        previous_person = current_person
    drop_ranked = sorted(
        drop_candidates,
        key=lambda item: (
            int(item.get("drop_delta", 0)),
            expected_person_count - int(item["person_count"]),
            -int(item["frame_index"]),
        ),
        reverse=True,
    )
    add_from_bucket(drop_ranked, 8, "sudden_drop")

    uniform_indices = evenly_spaced_indices(len(records), 8)
    add_from_bucket([records[idx] for idx in uniform_indices], 8, "uniform_coverage")

    duplicate_ranked = sorted(
        records,
        key=lambda item: (
            int(item.get("duplicate_pair_count", 0)),
            expected_person_count - int(item["person_count"]),
            -int(item["frame_index"]),
        ),
        reverse=True,
    )
    add_from_bucket([item for item in duplicate_ranked if int(item.get("duplicate_pair_count", 0)) > 0], 4, "duplicate_focus")

    backfill_ranked = sorted(
        records,
        key=lambda item: (
            expected_person_count - int(item["person_count"]),
            int(item.get("duplicate_pair_count", 0)),
            abs(int(item["smoothed_person_count"]) - int(item["person_count"])),
            -int(item["frame_index"]),
        ),
        reverse=True,
    )
    add_from_bucket(backfill_ranked, total_needed - len(selected), "manual_backfill")

    if len(selected) < total_needed:
        for item in backfill_ranked:
            frame_index = int(item["frame_index"])
            if frame_index in selected_ids:
                continue
            clone = dict(item)
            clone["selection_reason"] = "manual_backfill"
            selected.append(clone)
            selected_ids.add(frame_index)
            if len(selected) >= total_needed:
                break

    selected.sort(key=lambda item: int(item["frame_index"]))
    return selected[:total_needed]


def split_selected_records(records: List[Dict[str, Any]], val_count: int) -> None:
    val_positions = set(evenly_spaced_indices(len(records), min(val_count, len(records))))
    for idx, item in enumerate(records):
        item["split"] = "val" if idx in val_positions else "train"


def read_frame(video_path: Path, frame_index: int) -> Image.Image:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"unable to open video: {video_path}")
    try:
        capture.set(cv2.CAP_PROP_POS_FRAMES, float(frame_index))
        ok, frame = capture.read()
        if not ok:
            raise RuntimeError(f"unable to read frame {frame_index} from {video_path}")
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)
    finally:
        capture.release()


def draw_text_box(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int],
    text: str,
    *,
    font: ImageFont.ImageFont,
    fill: Tuple[int, int, int],
    background: Tuple[int, int, int],
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pad_x = 6
    pad_y = 4
    x0, y0 = xy
    draw.rectangle([x0, y0, x0 + text_w + pad_x * 2, y0 + text_h + pad_y * 2], fill=background)
    draw.text((x0 + pad_x, y0 + pad_y), text, fill=fill, font=font)


def annotate_frame(image: Image.Image, record: Dict[str, Any], expected_person_count: int) -> Image.Image:
    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)
    font = load_font(16)
    title_font = load_font(18)

    for det in record.get("detections", []):
        class_id = int(det.get("class_id", -1))
        color = CLASS_COLORS.get(class_id, (255, 255, 255))
        x1 = int(det.get("x1", 0))
        y1 = int(det.get("y1", 0))
        x2 = int(det.get("x2", 0))
        y2 = int(det.get("y2", 0))
        if x2 <= x1 or y2 <= y1:
            continue
        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
        label = f"{CLASS_NAMES.get(class_id, f'cls{class_id}')} {float(det.get('score', 0.0)):.2f}"
        draw_text_box(
            draw,
            (x1 + 4, max(4, y1 + 4)),
            label,
            font=font,
            fill=(255, 255, 255),
            background=(0, 0, 0),
        )

    header = (
        f"idx={int(record['frame_index'])} "
        f"P={int(record['person_count'])}/{expected_person_count} "
        f"Ps={int(record['smoothed_person_count'])} "
        f"dup={int(record.get('duplicate_pair_count', 0))}"
    )
    draw_text_box(draw, (12, 12), header, font=title_font, fill=(255, 255, 255), background=(0, 0, 0))
    draw_text_box(
        draw,
        (12, 44),
        str(record.get("selection_reason", "")),
        font=font,
        fill=(255, 255, 255),
        background=(0, 0, 0),
    )
    return annotated


def detection_to_yolo(det: Dict[str, Any], width: int, height: int) -> str:
    class_id = int(det.get("class_id", 0))
    x1 = float(det.get("x1", 0.0))
    y1 = float(det.get("y1", 0.0))
    x2 = float(det.get("x2", 0.0))
    y2 = float(det.get("y2", 0.0))
    box_w = max(0.0, x2 - x1)
    box_h = max(0.0, y2 - y1)
    if box_w <= 0.0 or box_h <= 0.0:
        return ""
    x_center = (x1 + x2) / 2.0 / float(width)
    y_center = (y1 + y2) / 2.0 / float(height)
    norm_w = box_w / float(width)
    norm_h = box_h / float(height)
    return f"{class_id} {x_center:.6f} {y_center:.6f} {norm_w:.6f} {norm_h:.6f}"


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export crowd keyframes from a board video iteration")
    parser.add_argument("--video", required=True, help="Path to the local board output video")
    parser.add_argument("--frame-detections", required=True, help="Path to frame_detections.jsonl")
    parser.add_argument("--output-root", default="/home/ywj/elevator_ai/datasets/PandE/crowd_keyframes_v1")
    parser.add_argument("--expected-person-count", type=int, default=7)
    parser.add_argument("--train-count", type=int, default=32)
    parser.add_argument("--val-count", type=int, default=8)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    video_path = Path(args.video)
    frame_detections_path = Path(args.frame_detections)
    output_root = Path(args.output_root)

    records = load_records(frame_detections_path)
    if not records:
        raise SystemExit(f"no frame records found in {frame_detections_path}")

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise SystemExit(f"unable to open video: {video_path}")
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1080)
    capture.release()

    selected = select_records(
        records,
        expected_person_count=args.expected_person_count,
        train_count=args.train_count,
        val_count=args.val_count,
    )
    split_selected_records(selected, args.val_count)

    if output_root.exists():
        for child_name in ("images", "labels", "overlays"):
            child = output_root / child_name
            if child.exists():
                shutil.rmtree(child)
    ensure_dir(output_root / "images" / "train")
    ensure_dir(output_root / "images" / "val")
    ensure_dir(output_root / "labels" / "train")
    ensure_dir(output_root / "labels" / "val")
    ensure_dir(output_root / "overlays" / "train")
    ensure_dir(output_root / "overlays" / "val")

    manifest_rows: List[Dict[str, Any]] = []
    overlay_index: Dict[str, List[Path]] = {"train": [], "val": []}
    for item in selected:
        split = str(item["split"])
        frame_index = int(item["frame_index"])
        stem = f"crowd_{split}_{frame_index:04d}"
        image_path = output_root / "images" / split / f"{stem}.jpg"
        label_path = output_root / "labels" / split / f"{stem}.txt"
        overlay_path = output_root / "overlays" / split / f"{stem}.jpg"

        frame = read_frame(video_path, frame_index)
        frame.save(image_path, quality=95)
        annotate_frame(frame, item, args.expected_person_count).save(overlay_path, quality=95)
        overlay_index[split].append(overlay_path)

        label_lines = [
            line
            for line in (detection_to_yolo(det, width, height) for det in item.get("detections", []))
            if line
        ]
        label_path.write_text("\n".join(label_lines) + ("\n" if label_lines else ""), encoding="utf-8")

        manifest_rows.append(
            {
                "split": split,
                "image_name": image_path.name,
                "label_name": label_path.name,
                "frame_index": frame_index,
                "timestamp_sec": round(float(item.get("elapsed_ms", 0.0)) / 1000.0, 6),
                "selection_reason": item.get("selection_reason", ""),
                "person_count": int(item.get("person_count", 0)),
                "smoothed_person_count": int(item.get("smoothed_person_count", 0)),
                "ebike_count": int(item.get("ebike_count", 0)),
                "duplicate_pair_count": int(item.get("duplicate_pair_count", 0)),
                "seed_label_count": len(label_lines),
                "source_video": str(video_path),
                "source_frame_detections": str(frame_detections_path),
            }
        )

    manifest_path = output_root / "manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest_rows[0].keys()))
        writer.writeheader()
        writer.writerows(manifest_rows)

    (output_root / "data.yaml").write_text(
        "\n".join(
            [
                f"path: {output_root}",
                "train: images/train",
                "val: images/val",
                "nc: 2",
                "names:",
                "  0: person",
                "  1: ebike",
                "",
            ]
        ),
        encoding="utf-8",
    )

    summary = {
        "video_path": str(video_path),
        "frame_detections_path": str(frame_detections_path),
        "expected_person_count": args.expected_person_count,
        "image_size": {"width": width, "height": height},
        "train_count": sum(1 for row in manifest_rows if row["split"] == "train"),
        "val_count": sum(1 for row in manifest_rows if row["split"] == "val"),
        "selection_breakdown": {
            reason: sum(1 for row in manifest_rows if row["selection_reason"] == reason)
            for reason in sorted({str(row["selection_reason"]) for row in manifest_rows})
        },
    }
    (output_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_root / "README.md").write_text(
        "\n".join(
            [
                "# crowd_keyframes_v1",
                "",
                "- This package is a crowd benchmark seed set for manual refinement.",
                "- `images/{train,val}` contains extracted keyframes.",
                "- `labels/{train,val}` contains seed YOLO labels from current board detections.",
                "- `overlays/{train,val}` contains review previews with current detections drawn on the frame.",
                "- Edit labels in place using `person` as class `0` and `ebike` as class `1`.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    write_contact_sheet(overlay_index["train"][:16], output_root / "overlays" / "train_sheet.jpg", "crowd train preview")
    write_contact_sheet(overlay_index["val"][:16], output_root / "overlays" / "val_sheet.jpg", "crowd val preview")
    print(f"crowd keyframes exported to {output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
