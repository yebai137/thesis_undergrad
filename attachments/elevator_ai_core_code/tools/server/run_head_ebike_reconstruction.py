#!/usr/bin/env python3
"""Head+ebike pseudo-dataset reconstruction and training pipeline."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import statistics
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

import cv2
import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO


REPO_ROOT = Path("/home/ywj/elevator_ai")
SCUT_DATA_YAML = REPO_ROOT / "datasets/SCUT_HEAD_yolo_head/data.yaml"
PSEUDO_SOURCE_ROOT = REPO_ROOT / "datasets/PandE/personAndEbike"
PSEUDO_OUTPUT_ROOT = REPO_ROOT / "datasets/PandE/headAndEbike_pseudo_v1"
REVIEW_OUTPUT_ROOT = REPO_ROOT / "runs/head_ebike_review_v1"
MIXED_OUTPUT_ROOT = REPO_ROOT / "datasets/headEbike_mixed_v1"
INCUMBENT_MODEL = REPO_ROOT / "models/custom/yolov8n_100epoch_map0986.pt"

TRAIN_RUN_ROOT = REPO_ROOT / "runs/detect"
PIPELINE_RUN_ROOT = REPO_ROOT / "runs/head_ebike_pipeline_v1"

DEFAULT_TEACHER_TARGET = 0.95
DEFAULT_PSEUDO_CONF = 0.25
DEFAULT_LOW_IMPACT_WORKERS = 4
DEFAULT_LOW_IMPACT_NICE = 10


@dataclass(frozen=True)
class TeacherStage:
    name: str
    weights: str
    imgsz: int
    epochs: int
    batch: int
    patience: int


TEACHER_STAGES: Tuple[TeacherStage, ...] = (
    TeacherStage(name="head_teacher_yolov8s_960", weights="yolov8s.pt", imgsz=960, epochs=150, batch=16, patience=30),
    TeacherStage(name="head_teacher_yolov8m_960", weights="yolov8m.pt", imgsz=960, epochs=150, batch=8, patience=30),
    TeacherStage(name="head_teacher_yolov8m_1024", weights="yolov8m.pt", imgsz=1024, epochs=200, batch=6, patience=30),
    TeacherStage(name="head_teacher_yolov8l_960", weights="yolov8l.pt", imgsz=960, epochs=150, batch=4, patience=30),
)


@dataclass
class ImageRecord:
    split: str
    source_image: Path
    source_label: Path
    image_id: str
    source_index: int
    person_boxes: List[List[float]]
    ebike_boxes: List[List[float]]
    head_boxes: List[List[float]]
    head_scores: List[float]
    width: int
    height: int

    @property
    def gt_person_count(self) -> int:
        return len(self.person_boxes)

    @property
    def gt_ebike_count(self) -> int:
        return len(self.ebike_boxes)

    @property
    def pseudo_head_count(self) -> int:
        return len(self.head_boxes)

    @property
    def mean_head_conf(self) -> float:
        return float(sum(self.head_scores) / len(self.head_scores)) if self.head_scores else 0.0

    @property
    def max_head_conf(self) -> float:
        return float(max(self.head_scores)) if self.head_scores else 0.0

    @property
    def abs_count_delta(self) -> int:
        return abs(self.pseudo_head_count - self.gt_person_count)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Head+ebike pseudo-dataset reconstruction pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    teacher_parser = subparsers.add_parser("teacher", help="Train stronger head-only teacher")
    teacher_parser.add_argument("--data", type=Path, default=SCUT_DATA_YAML)
    teacher_parser.add_argument("--target-map50", type=float, default=DEFAULT_TEACHER_TARGET)
    teacher_parser.add_argument("--device", default="auto", help="'auto', GPU index, or 'cpu'")
    teacher_parser.add_argument("--workers", type=int, default=DEFAULT_LOW_IMPACT_WORKERS)
    teacher_parser.add_argument("--nice", type=int, default=DEFAULT_LOW_IMPACT_NICE)
    teacher_parser.add_argument("--summary-path", type=Path, default=PIPELINE_RUN_ROOT / "teacher_summary.json")

    pseudo_parser = subparsers.add_parser("pseudo", help="Build pseudo dataset and review artifacts")
    pseudo_parser.add_argument("--teacher-model", type=Path, required=True)
    pseudo_parser.add_argument("--teacher-imgsz", type=int, required=True)
    pseudo_parser.add_argument("--source-root", type=Path, default=PSEUDO_SOURCE_ROOT)
    pseudo_parser.add_argument("--output-root", type=Path, default=PSEUDO_OUTPUT_ROOT)
    pseudo_parser.add_argument("--review-root", type=Path, default=REVIEW_OUTPUT_ROOT)
    pseudo_parser.add_argument("--device", default="auto")
    pseudo_parser.add_argument("--conf", type=float, default=DEFAULT_PSEUDO_CONF)
    pseudo_parser.add_argument("--batch", type=int, default=32)
    pseudo_parser.add_argument("--workers", type=int, default=DEFAULT_LOW_IMPACT_WORKERS)
    pseudo_parser.add_argument("--copy-images", action="store_true", help="Copy images instead of symlink for pseudo dataset")

    mixed_parser = subparsers.add_parser("mixed", help="Build mixed head+ebike training dataset")
    mixed_parser.add_argument("--pseudo-root", type=Path, default=PSEUDO_OUTPUT_ROOT)
    mixed_parser.add_argument("--scut-root", type=Path, default=REPO_ROOT / "datasets/SCUT_HEAD_yolo_head")
    mixed_parser.add_argument("--output-root", type=Path, default=MIXED_OUTPUT_ROOT)
    mixed_parser.add_argument("--oversample-elevator-train", type=int, default=1)

    final_parser = subparsers.add_parser("train-final", help="Train and evaluate the final 2-class model")
    final_parser.add_argument("--teacher-model", type=Path, required=True)
    final_parser.add_argument("--mixed-root", type=Path, default=MIXED_OUTPUT_ROOT)
    final_parser.add_argument("--incumbent-model", type=Path, default=INCUMBENT_MODEL)
    final_parser.add_argument("--device", default="auto")
    final_parser.add_argument("--epochs", type=int, default=100)
    final_parser.add_argument("--patience", type=int, default=30)
    final_parser.add_argument("--workers", type=int, default=DEFAULT_LOW_IMPACT_WORKERS)
    final_parser.add_argument("--ebike-drop-threshold", type=float, default=0.03)
    final_parser.add_argument("--allow-oversample-retry", action="store_true")
    final_parser.add_argument("--summary-path", type=Path, default=PIPELINE_RUN_ROOT / "final_training_summary.json")

    all_parser = subparsers.add_parser("all", help="Run the full pipeline")
    all_parser.add_argument("--target-map50", type=float, default=DEFAULT_TEACHER_TARGET)
    all_parser.add_argument("--device", default="auto")
    all_parser.add_argument("--workers", type=int, default=DEFAULT_LOW_IMPACT_WORKERS)
    all_parser.add_argument("--nice", type=int, default=DEFAULT_LOW_IMPACT_NICE)
    all_parser.add_argument("--conf", type=float, default=DEFAULT_PSEUDO_CONF)
    all_parser.add_argument("--allow-oversample-retry", action="store_true")
    all_parser.add_argument("--ebike-drop-threshold", type=float, default=0.03)

    return parser.parse_args()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: object) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def write_yaml(path: Path, payload: dict) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)


def parse_yolo_label(path: Path) -> List[List[float]]:
    boxes: List[List[float]] = []
    if not path.exists():
        return boxes
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        boxes.append([float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])])
    return boxes


def format_yolo_line(class_id: int, box: Sequence[float]) -> str:
    x, y, w, h = box
    return f"{class_id} {x:.6f} {y:.6f} {w:.6f} {h:.6f}"


def safe_symlink(src: Path, dst: Path) -> None:
    ensure_dir(dst.parent)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    dst.symlink_to(src)


def copy_or_link(src: Path, dst: Path, *, copy_images: bool) -> None:
    ensure_dir(dst.parent)
    if dst.exists() or dst.is_symlink():
        if dst.is_dir():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    if copy_images:
        shutil.copy2(src, dst)
    else:
        safe_symlink(src, dst)


def set_low_impact(nice_value: int) -> None:
    if nice_value <= 0:
        return
    try:
        os.nice(nice_value)
    except OSError:
        pass
    os.environ.setdefault("OMP_NUM_THREADS", "4")
    os.environ.setdefault("MKL_NUM_THREADS", "4")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")


def pick_idle_gpu() -> Optional[str]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    best_index = None
    best_score = None
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        index_s, util_s, used_s, total_s = [part.strip() for part in line.split(",")]
        util = float(util_s)
        used = float(used_s)
        total = float(total_s)
        free = total - used
        if util > 10.0:
            continue
        score = (util, -free)
        if best_score is None or score < best_score:
            best_index = index_s
            best_score = score
    return best_index


def resolve_device(device: str) -> str:
    if device == "auto":
        chosen = pick_idle_gpu()
        return chosen if chosen is not None else "cpu"
    return device


def f1_score(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


def evaluate_model(
    model_path: Path | str,
    data_yaml: Path | str,
    *,
    split: str,
    device: str,
    imgsz: int,
    batch: int,
    workers: int,
) -> dict:
    model = YOLO(str(model_path))
    metrics = model.val(
        data=str(data_yaml),
        split=split,
        imgsz=imgsz,
        batch=batch,
        device=device,
        plots=False,
        save_json=False,
        verbose=False,
        workers=workers,
    )
    box = metrics.box
    class_results: Dict[str, dict] = {}
    available_class_metrics = len(box.p)
    for index, class_name in metrics.names.items():
        if index < available_class_metrics:
            p, r, ap50, ap = box.class_result(index)
        else:
            # Some evaluation sets only contain a subset of declared classes.
            p, r, ap50, ap = 0.0, 0.0, 0.0, 0.0
        class_results[str(index)] = {
            "class_name": class_name,
            "precision": float(p),
            "recall": float(r),
            "f1": f1_score(float(p), float(r)),
            "ap50": float(ap50),
            "ap50_95": float(ap),
        }
    return {
        "data_yaml": str(data_yaml),
        "split": split,
        "device": device,
        "imgsz": imgsz,
        "batch": batch,
        "overall": {
            "precision": float(box.mp),
            "recall": float(box.mr),
            "map50": float(box.map50),
            "map50_95": float(box.map),
        },
        "classes": class_results,
    }


def train_teacher_stage(
    stage: TeacherStage,
    *,
    data_yaml: Path,
    device: str,
    workers: int,
    nice_value: int,
) -> dict:
    set_low_impact(nice_value)
    model = YOLO(stage.weights)
    model.train(
        data=str(data_yaml),
        epochs=stage.epochs,
        batch=stage.batch,
        imgsz=stage.imgsz,
        device=device,
        name=stage.name,
        project=str(TRAIN_RUN_ROOT),
        patience=stage.patience,
        save=True,
        save_period=10,
        plots=True,
        verbose=True,
        workers=workers,
    )
    run_dir = TRAIN_RUN_ROOT / stage.name
    best_model = run_dir / "weights/best.pt"
    val_metrics = evaluate_model(best_model, data_yaml, split="val", device=device, imgsz=stage.imgsz, batch=stage.batch, workers=workers)
    test_metrics = evaluate_model(best_model, data_yaml, split="test", device=device, imgsz=stage.imgsz, batch=stage.batch, workers=workers)
    summary = {
        "stage": asdict(stage),
        "run_dir": str(run_dir),
        "best_model": str(best_model),
        "val": val_metrics,
        "test": test_metrics,
    }
    write_json(run_dir / "stage_summary.json", summary)
    return summary


def run_teacher_escalation(
    *,
    data_yaml: Path,
    target_map50: float,
    device: str,
    workers: int,
    nice_value: int,
    summary_path: Path,
) -> dict:
    ensure_dir(summary_path.parent)
    stage_summaries: List[dict] = []
    winner: Optional[dict] = None
    best_score = -1.0
    for stage in TEACHER_STAGES:
        summary = train_teacher_stage(stage, data_yaml=data_yaml, device=device, workers=workers, nice_value=nice_value)
        stage_summaries.append(summary)
        stage_score = min(summary["val"]["overall"]["map50"], summary["test"]["overall"]["map50"])
        if stage_score > best_score:
            best_score = stage_score
            winner = summary
        if summary["val"]["overall"]["map50"] >= target_map50 and summary["test"]["overall"]["map50"] >= target_map50:
            winner = summary
            break
    payload = {
        "target_map50": target_map50,
        "device": device,
        "workers": workers,
        "stages": stage_summaries,
        "winner": winner,
    }
    write_json(summary_path, payload)
    return payload


def list_images(image_dir: Path) -> List[Path]:
    return sorted([path for path in image_dir.iterdir() if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}])


def load_source_records(source_root: Path) -> List[ImageRecord]:
    records: List[ImageRecord] = []
    for split in ("train", "val"):
        image_dir = source_root / "images" / split
        label_dir = source_root / "labels" / split
        for index, image_path in enumerate(list_images(image_dir)):
            label_path = label_dir / f"{image_path.stem}.txt"
            parsed = parse_yolo_label(label_path)
            person_boxes = [box[1:] for box in parsed if int(box[0]) == 0]
            ebike_boxes = [box[1:] for box in parsed if int(box[0]) == 1]
            with Image.open(image_path) as image:
                width, height = image.size
            records.append(
                ImageRecord(
                    split=split,
                    source_image=image_path,
                    source_label=label_path,
                    image_id=image_path.stem,
                    source_index=index,
                    person_boxes=person_boxes,
                    ebike_boxes=ebike_boxes,
                    head_boxes=[],
                    head_scores=[],
                    width=width,
                    height=height,
                )
            )
    return records


def batched(items: Sequence[ImageRecord], batch_size: int) -> Iterator[Sequence[ImageRecord]]:
    for index in range(0, len(items), batch_size):
        yield items[index:index + batch_size]


def predict_heads(
    records: List[ImageRecord],
    *,
    model_path: Path,
    device: str,
    imgsz: int,
    conf: float,
    batch: int,
) -> None:
    model = YOLO(str(model_path))
    for chunk in batched(records, batch):
        results = model.predict(
            source=[str(item.source_image) for item in chunk],
            imgsz=imgsz,
            conf=conf,
            device=device,
            batch=batch,
            verbose=False,
            save=False,
            stream=True,
        )
        for item, result in zip(chunk, results):
            head_boxes: List[List[float]] = []
            head_scores: List[float] = []
            if result.boxes is not None and len(result.boxes) > 0:
                for box, score in zip(result.boxes.xywhn.cpu().numpy(), result.boxes.conf.cpu().numpy()):
                    head_boxes.append([float(box[0]), float(box[1]), float(box[2]), float(box[3])])
                    head_scores.append(float(score))
            ordering = sorted(range(len(head_boxes)), key=lambda idx: head_scores[idx], reverse=True)
            item.head_boxes = [head_boxes[idx] for idx in ordering]
            item.head_scores = [head_scores[idx] for idx in ordering]


def build_pseudo_dataset(
    records: List[ImageRecord],
    *,
    source_root: Path,
    output_root: Path,
    review_root: Path,
    conf: float,
    copy_images: bool,
) -> dict:
    if output_root.exists():
        shutil.rmtree(output_root)
    if review_root.exists():
        shutil.rmtree(review_root)
    ensure_dir(output_root)
    ensure_dir(review_root)

    data_yaml = {
        "path": str(output_root),
        "train": "images/train",
        "val": "images/val",
        "names": {0: "head", 1: "ebike"},
        "nc": 2,
    }
    write_yaml(output_root / "data.yaml", data_yaml)

    metadata_rows: List[dict] = []
    for record in records:
        image_dst = output_root / "images" / record.split / record.source_image.name
        label_dst = output_root / "labels" / record.split / f"{record.image_id}.txt"
        copy_or_link(record.source_image, image_dst, copy_images=copy_images)
        label_lines = [format_yolo_line(0, box) for box in record.head_boxes]
        label_lines.extend(format_yolo_line(1, box) for box in record.ebike_boxes)
        write_text(label_dst, "\n".join(label_lines) + ("\n" if label_lines else ""))
        metadata_rows.append(
            {
                "split": record.split,
                "image_name": record.source_image.name,
                "image_id": record.image_id,
                "source_label": str(record.source_label),
                "source_index": record.source_index,
                "gt_person_count": record.gt_person_count,
                "gt_ebike_count": record.gt_ebike_count,
                "pseudo_head_count": record.pseudo_head_count,
                "head_conf_mean": record.mean_head_conf,
                "head_conf_max": record.max_head_conf,
                "abs_count_delta": record.abs_count_delta,
            }
        )

    write_json(output_root / "metadata.json", metadata_rows)
    write_csv(
        output_root / "metadata.csv",
        metadata_rows,
        fieldnames=[
            "split",
            "image_name",
            "image_id",
            "source_label",
            "source_index",
            "gt_person_count",
            "gt_ebike_count",
            "pseudo_head_count",
            "head_conf_mean",
            "head_conf_max",
            "abs_count_delta",
        ],
    )
    review_summary = build_review_artifacts(records, review_root=review_root, pseudo_root=output_root, source_root=source_root)
    payload = {
        "source_root": str(source_root),
        "output_root": str(output_root),
        "review_root": str(review_root),
        "conf": conf,
        "images": len(records),
        "splits": summarize_records(records),
        "review": review_summary,
    }
    write_json(output_root / "summary.json", payload)
    return payload


def summarize_records(records: Sequence[ImageRecord]) -> Dict[str, dict]:
    result: Dict[str, dict] = {}
    for split in ("train", "val"):
        split_records = [record for record in records if record.split == split]
        result[split] = {
            "images": len(split_records),
            "gt_person_total": sum(record.gt_person_count for record in split_records),
            "gt_ebike_total": sum(record.gt_ebike_count for record in split_records),
            "pseudo_head_total": sum(record.pseudo_head_count for record in split_records),
            "mean_abs_count_delta": statistics.mean(record.abs_count_delta for record in split_records) if split_records else 0.0,
        }
    return result


def write_csv(path: Path, rows: Sequence[dict], *, fieldnames: Sequence[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def draw_yolo_boxes(
    image: np.ndarray,
    boxes: Sequence[Sequence[float]],
    *,
    color: Tuple[int, int, int],
    label: str,
    scores: Optional[Sequence[float]] = None,
) -> np.ndarray:
    canvas = image.copy()
    height, width = canvas.shape[:2]
    for index, box in enumerate(boxes):
        x_center, y_center, box_w, box_h = box
        x1 = int((x_center - box_w / 2.0) * width)
        y1 = int((y_center - box_h / 2.0) * height)
        x2 = int((x_center + box_w / 2.0) * width)
        y2 = int((y_center + box_h / 2.0) * height)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        text = label
        if scores is not None and index < len(scores):
            text = f"{label} {scores[index]:.2f}"
        cv2.putText(canvas, text, (x1, max(20, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)
    return canvas


def render_overlay(record: ImageRecord) -> np.ndarray:
    image = cv2.imread(str(record.source_image))
    if image is None:
        raise RuntimeError(f"failed to read image: {record.source_image}")
    image = draw_yolo_boxes(image, record.person_boxes, color=(0, 220, 0), label="person_ref")
    image = draw_yolo_boxes(image, record.ebike_boxes, color=(0, 165, 255), label="ebike_gt")
    image = draw_yolo_boxes(image, record.head_boxes, color=(255, 0, 255), label="head_pseudo", scores=record.head_scores)
    header = f"{record.source_image.name} | person={record.gt_person_count} ebike={record.gt_ebike_count} head={record.pseudo_head_count}"
    cv2.rectangle(image, (0, 0), (min(image.shape[1], 1600), 32), (20, 20, 20), -1)
    cv2.putText(image, header, (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
    return image


def choose_train_preview_sample(records: Sequence[ImageRecord]) -> List[ImageRecord]:
    train_records = [record for record in records if record.split == "train"]
    buckets = {
        "0": [record for record in train_records if record.gt_person_count == 0],
        "1": [record for record in train_records if record.gt_person_count == 1],
        "2": [record for record in train_records if record.gt_person_count == 2],
        "3+": [record for record in train_records if record.gt_person_count >= 3],
    }
    selected: List[ImageRecord] = []
    selected.extend(sorted(buckets["0"], key=lambda item: (-item.pseudo_head_count, -item.max_head_conf, item.source_index))[:40])
    selected.extend(sorted(buckets["1"], key=lambda item: (-item.abs_count_delta, item.mean_head_conf, item.source_index))[:80])
    selected.extend(sorted(buckets["2"], key=lambda item: (-item.abs_count_delta, item.mean_head_conf, item.source_index))[:60])
    selected.extend(sorted(buckets["3+"], key=lambda item: (-item.abs_count_delta, item.mean_head_conf, item.source_index))[:20])
    return selected


def save_overlay_set(records: Sequence[ImageRecord], output_dir: Path) -> List[dict]:
    rows: List[dict] = []
    for record in records:
        overlay = render_overlay(record)
        output_path = output_dir / record.split / record.source_image.name
        ensure_dir(output_path.parent)
        cv2.imwrite(str(output_path), overlay)
        rows.append(
            {
                "split": record.split,
                "image_name": record.source_image.name,
                "overlay_path": str(output_path),
                "gt_person_count": record.gt_person_count,
                "gt_ebike_count": record.gt_ebike_count,
                "pseudo_head_count": record.pseudo_head_count,
                "abs_count_delta": record.abs_count_delta,
                "head_conf_mean": record.mean_head_conf,
                "head_conf_max": record.max_head_conf,
            }
        )
    return rows


def create_contact_sheets(
    records: Sequence[dict],
    *,
    output_dir: Path,
    label_key: str,
    per_sheet: int = 16,
) -> List[str]:
    ensure_dir(output_dir)
    font = ImageFont.load_default()
    output_paths: List[str] = []
    for sheet_index in range(0, len(records), per_sheet):
        chunk = records[sheet_index:sheet_index + per_sheet]
        thumbs: List[Tuple[Image.Image, str]] = []
        for row in chunk:
            image = Image.open(row["overlay_path"]).convert("RGB")
            image.thumbnail((320, 220))
            thumbs.append((image, row[label_key]))
        columns = 4
        rows = math.ceil(len(thumbs) / columns)
        cell_w, cell_h = 340, 260
        canvas = Image.new("RGB", (columns * cell_w, rows * cell_h), (18, 18, 18))
        draw = ImageDraw.Draw(canvas)
        for idx, (thumb, label) in enumerate(thumbs):
            row = idx // columns
            col = idx % columns
            x = col * cell_w + 10
            y = row * cell_h + 10
            canvas.paste(thumb, (x, y))
            draw.text((x, y + 225), label[:44], font=font, fill=(255, 255, 255))
        output_path = output_dir / f"sheet_{sheet_index // per_sheet + 1:03d}.jpg"
        canvas.save(output_path, quality=90)
        output_paths.append(str(output_path))
    return output_paths


def build_review_artifacts(records: Sequence[ImageRecord], *, review_root: Path, pseudo_root: Path, source_root: Path) -> dict:
    val_records = [record for record in records if record.split == "val"]
    train_sample = choose_train_preview_sample(records)
    val_rows = save_overlay_set(val_records, review_root / "val_overlays")
    train_rows = save_overlay_set(train_sample, review_root / "train_sample_overlays")
    suspicious_rows = []
    for record in sorted(records, key=lambda item: (-item.abs_count_delta, item.mean_head_conf, item.source_index)):
        suspicious_rows.append(
            {
                "split": record.split,
                "image_name": record.source_image.name,
                "gt_person_count": record.gt_person_count,
                "pseudo_head_count": record.pseudo_head_count,
                "abs_count_delta": record.abs_count_delta,
                "head_conf_mean": record.mean_head_conf,
                "head_conf_max": record.max_head_conf,
            }
        )
    write_csv(review_root / "val_manifest.csv", val_rows, fieldnames=val_rows[0].keys() if val_rows else [])
    write_csv(review_root / "train_sample_manifest.csv", train_rows, fieldnames=train_rows[0].keys() if train_rows else [])
    write_csv(review_root / "suspicious_samples.csv", suspicious_rows, fieldnames=suspicious_rows[0].keys() if suspicious_rows else [])
    val_contact = create_contact_sheets(
        sorted(val_rows, key=lambda row: (-row["abs_count_delta"], row["head_conf_mean"], row["image_name"]))[:128],
        output_dir=review_root / "contact_sheets" / "val_top128",
        label_key="image_name",
    )
    train_contact = create_contact_sheets(train_rows, output_dir=review_root / "contact_sheets" / "train_sample", label_key="image_name")
    summary = {
        "pseudo_root": str(pseudo_root),
        "source_root": str(source_root),
        "val_overlay_count": len(val_rows),
        "train_overlay_count": len(train_rows),
        "contact_sheets": {
            "val_top128": val_contact,
            "train_sample": train_contact,
        },
    }
    write_json(review_root / "summary.json", summary)
    return summary


def build_mixed_dataset(
    pseudo_root: Path,
    *,
    scut_root: Path,
    output_root: Path,
    oversample_elevator_train: int,
) -> dict:
    if output_root.exists():
        shutil.rmtree(output_root)
    ensure_dir(output_root)
    mapping_rows: List[dict] = []

    def register_sample(prefix: str, split: str, image_path: Path, label_path: Path, *, dup_index: int = 0) -> None:
        suffix = image_path.suffix.lower()
        sample_name = f"{prefix}_{split}_{len(mapping_rows):06d}"
        if dup_index:
            sample_name += f"_dup{dup_index}"
        image_dst = output_root / "images" / split / f"{sample_name}{suffix}"
        label_dst = output_root / "labels" / split / f"{sample_name}.txt"
        safe_symlink(image_path, image_dst)
        safe_symlink(label_path, label_dst)
        mapping_rows.append(
            {
                "split": split,
                "sample_name": sample_name,
                "source_image": str(image_path),
                "source_label": str(label_path),
            }
        )

    for split in ("train", "val"):
        for image_path in list_images(scut_root / "images" / split):
            label_path = scut_root / "labels" / split / f"{image_path.stem}.txt"
            register_sample("scut", split, image_path, label_path)

    for split in ("train", "val"):
        dup_total = oversample_elevator_train if split == "train" else 1
        for image_path in list_images(pseudo_root / "images" / split):
            label_path = pseudo_root / "labels" / split / f"{image_path.stem}.txt"
            for dup_index in range(dup_total):
                register_sample("elevator", split, image_path, label_path, dup_index=dup_index)

    data_yaml = {
        "path": str(output_root),
        "train": "images/train",
        "val": "images/val",
        "names": {0: "head", 1: "ebike"},
        "nc": 2,
    }
    write_yaml(output_root / "data.yaml", data_yaml)
    scut_eval_yaml = {
        "path": str(scut_root),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": {0: "head", 1: "ebike"},
        "nc": 2,
    }
    write_yaml(output_root / "scut_eval_2class.yaml", scut_eval_yaml)
    write_json(output_root / "mapping.json", mapping_rows)
    summary = {
        "pseudo_root": str(pseudo_root),
        "scut_root": str(scut_root),
        "output_root": str(output_root),
        "oversample_elevator_train": oversample_elevator_train,
        "train_samples": sum(1 for row in mapping_rows if row["split"] == "train"),
        "val_samples": sum(1 for row in mapping_rows if row["split"] == "val"),
    }
    write_json(output_root / "summary.json", summary)
    return summary


def infer_teacher_stage_from_model(model_path: Path) -> TeacherStage:
    run_dir = model_path.parent.parent
    args_path = run_dir / "args.yaml"
    if not args_path.exists():
        raise FileNotFoundError(f"missing args.yaml for teacher model: {args_path}")
    args = load_yaml(args_path)
    weights = str(args.get("model"))
    name = str(run_dir.name)
    imgsz = int(args.get("imgsz", 960))
    batch = int(args.get("batch", 8))
    epochs = int(args.get("epochs", 100))
    patience = int(args.get("patience", 30))
    return TeacherStage(name=name, weights=weights, imgsz=imgsz, batch=batch, epochs=epochs, patience=patience)


def train_final_model(
    *,
    teacher_model: Path,
    mixed_root: Path,
    incumbent_model: Path,
    pseudo_root: Path,
    scut_root: Path,
    device: str,
    epochs: int,
    patience: int,
    workers: int,
    ebike_drop_threshold: float,
    allow_oversample_retry: bool,
    summary_path: Path,
) -> dict:
    stage = infer_teacher_stage_from_model(teacher_model)
    mixed_yaml = mixed_root / "data.yaml"
    scut_eval_yaml = mixed_root / "scut_eval_2class.yaml"
    run_name = f"head_ebike_2class_{stage.name}"
    model = YOLO(str(teacher_model))
    model.train(
        data=str(mixed_yaml),
        imgsz=stage.imgsz,
        batch=stage.batch,
        epochs=epochs,
        patience=patience,
        device=device,
        name=run_name,
        project=str(TRAIN_RUN_ROOT),
        save=True,
        save_period=10,
        plots=True,
        verbose=True,
        workers=workers,
    )
    run_dir = TRAIN_RUN_ROOT / run_name
    best_model = run_dir / "weights/best.pt"
    head_val = evaluate_model(best_model, scut_eval_yaml, split="val", device=device, imgsz=stage.imgsz, batch=stage.batch, workers=workers)
    head_test = evaluate_model(best_model, scut_eval_yaml, split="test", device=device, imgsz=stage.imgsz, batch=stage.batch, workers=workers)
    incumbent_eval = evaluate_model(incumbent_model, PSEUDO_SOURCE_ROOT / "data.yaml", split="val", device="cpu", imgsz=640, batch=16, workers=2)
    final_elevator_eval = evaluate_model(best_model, PSEUDO_SOURCE_ROOT / "data.yaml", split="val", device=device, imgsz=stage.imgsz, batch=stage.batch, workers=workers)
    incumbent_ebike = incumbent_eval["classes"]["1"]
    final_ebike = final_elevator_eval["classes"]["1"]
    ebike_drop = float(incumbent_ebike["f1"]) - float(final_ebike["f1"])
    retry_summary = None
    if ebike_drop > ebike_drop_threshold and allow_oversample_retry:
        rebuild = build_mixed_dataset(
            pseudo_root,
            scut_root=scut_root,
            output_root=mixed_root,
            oversample_elevator_train=2,
        )
        retry_name = f"{run_name}_oversample2x"
        retry_model = YOLO(str(teacher_model))
        retry_model.train(
            data=str(mixed_root / "data.yaml"),
            imgsz=stage.imgsz,
            batch=stage.batch,
            epochs=epochs,
            patience=patience,
            device=device,
            name=retry_name,
            project=str(TRAIN_RUN_ROOT),
            save=True,
            save_period=10,
            plots=True,
            verbose=True,
            workers=workers,
        )
        retry_dir = TRAIN_RUN_ROOT / retry_name
        retry_best = retry_dir / "weights/best.pt"
        retry_eval = evaluate_model(retry_best, PSEUDO_SOURCE_ROOT / "data.yaml", split="val", device=device, imgsz=stage.imgsz, batch=stage.batch, workers=workers)
        retry_summary = {
            "mixed_dataset_rebuild": rebuild,
            "run_dir": str(retry_dir),
            "best_model": str(retry_best),
            "elevator_val": retry_eval,
            "ebike_drop": float(incumbent_ebike["f1"]) - float(retry_eval["classes"]["1"]["f1"]),
        }
    summary = {
        "teacher_model": str(teacher_model),
        "mixed_root": str(mixed_root),
        "run_dir": str(run_dir),
        "best_model": str(best_model),
        "head_val": head_val,
        "head_test": head_test,
        "incumbent_elevator_val": incumbent_eval,
        "final_elevator_val": final_elevator_eval,
        "ebike_drop": ebike_drop,
        "ebike_drop_threshold": ebike_drop_threshold,
        "retry": retry_summary,
    }
    write_json(summary_path, summary)
    return summary


def command_teacher(args: argparse.Namespace) -> int:
    device = resolve_device(args.device)
    payload = run_teacher_escalation(
        data_yaml=args.data,
        target_map50=args.target_map50,
        device=device,
        workers=args.workers,
        nice_value=args.nice,
        summary_path=args.summary_path,
    )
    winner = payload["winner"]
    if winner is None:
        return 1
    return 0


def command_pseudo(args: argparse.Namespace) -> int:
    device = resolve_device(args.device)
    records = load_source_records(args.source_root)
    predict_heads(
        records,
        model_path=args.teacher_model,
        device=device,
        imgsz=args.teacher_imgsz,
        conf=args.conf,
        batch=args.batch,
    )
    build_pseudo_dataset(
        records,
        source_root=args.source_root,
        output_root=args.output_root,
        review_root=args.review_root,
        conf=args.conf,
        copy_images=args.copy_images,
    )
    return 0


def command_mixed(args: argparse.Namespace) -> int:
    build_mixed_dataset(
        args.pseudo_root,
        scut_root=args.scut_root,
        output_root=args.output_root,
        oversample_elevator_train=args.oversample_elevator_train,
    )
    return 0


def command_train_final(args: argparse.Namespace) -> int:
    device = resolve_device(args.device)
    train_final_model(
        teacher_model=args.teacher_model,
        mixed_root=args.mixed_root,
        incumbent_model=args.incumbent_model,
        pseudo_root=PSEUDO_OUTPUT_ROOT,
        scut_root=REPO_ROOT / "datasets/SCUT_HEAD_yolo_head",
        device=device,
        epochs=args.epochs,
        patience=args.patience,
        workers=args.workers,
        ebike_drop_threshold=args.ebike_drop_threshold,
        allow_oversample_retry=args.allow_oversample_retry,
        summary_path=args.summary_path,
    )
    return 0


def command_all(args: argparse.Namespace) -> int:
    device = resolve_device(args.device)
    teacher_summary_path = PIPELINE_RUN_ROOT / "teacher_summary.json"
    teacher_payload = run_teacher_escalation(
        data_yaml=SCUT_DATA_YAML,
        target_map50=args.target_map50,
        device=device,
        workers=args.workers,
        nice_value=args.nice,
        summary_path=teacher_summary_path,
    )
    winner = teacher_payload["winner"]
    if winner is None:
        raise SystemExit("teacher escalation failed to produce a winner")
    teacher_model = Path(winner["best_model"])
    teacher_stage = infer_teacher_stage_from_model(teacher_model)

    records = load_source_records(PSEUDO_SOURCE_ROOT)
    predict_heads(
        records,
        model_path=teacher_model,
        device=device,
        imgsz=teacher_stage.imgsz,
        conf=args.conf,
        batch=32,
    )
    build_pseudo_dataset(
        records,
        source_root=PSEUDO_SOURCE_ROOT,
        output_root=PSEUDO_OUTPUT_ROOT,
        review_root=REVIEW_OUTPUT_ROOT,
        conf=args.conf,
        copy_images=False,
    )
    build_mixed_dataset(
        PSEUDO_OUTPUT_ROOT,
        scut_root=REPO_ROOT / "datasets/SCUT_HEAD_yolo_head",
        output_root=MIXED_OUTPUT_ROOT,
        oversample_elevator_train=1,
    )
    train_final_model(
        teacher_model=teacher_model,
        mixed_root=MIXED_OUTPUT_ROOT,
        incumbent_model=INCUMBENT_MODEL,
        pseudo_root=PSEUDO_OUTPUT_ROOT,
        scut_root=REPO_ROOT / "datasets/SCUT_HEAD_yolo_head",
        device=device,
        epochs=100,
        patience=30,
        workers=args.workers,
        ebike_drop_threshold=args.ebike_drop_threshold,
        allow_oversample_retry=args.allow_oversample_retry,
        summary_path=PIPELINE_RUN_ROOT / "final_training_summary.json",
    )
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "teacher":
        return command_teacher(args)
    if args.command == "pseudo":
        return command_pseudo(args)
    if args.command == "mixed":
        return command_mixed(args)
    if args.command == "train-final":
        return command_train_final(args)
    if args.command == "all":
        return command_all(args)
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
