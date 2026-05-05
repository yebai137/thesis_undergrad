#!/usr/bin/env python3
"""Grounding DINO head annotation workflow up to the 200-image review gate."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, Dict, Iterable, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont


REPO_ROOT = Path("/home/ywj/elevator_ai")
DEFAULT_DATASET_ROOT = REPO_ROOT / "datasets/PandE/personAndEbike"
DEFAULT_RUN_ROOT = REPO_ROOT / "runs/gdino_head_annotation_v1"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "datasets/PandE/headAndEbike_gdino_v1"
DEFAULT_MODEL_DIR = REPO_ROOT / "models/grounding_dino"
DEFAULT_CONFIG_PATH = DEFAULT_MODEL_DIR / "GroundingDINO_SwinT_OGC.py"
DEFAULT_WEIGHTS_PATH = DEFAULT_MODEL_DIR / "groundingdino_swint_ogc.pth"
DEFAULT_PROMPT = "head . human head . top of head ."
DEFAULT_DEVICE = "cuda:2"
DEFAULT_BOX_THRESHOLD = 0.25
DEFAULT_TEXT_THRESHOLD = 0.20
DEFAULT_SLICE_SIZE = 640
DEFAULT_OVERLAP = 0.15
DEFAULT_NMS_IOU = 0.50
DEFAULT_SLICE_TRIGGER_MAX_DIM = 960
DEFAULT_CONTACT_COLUMNS = 4
DEFAULT_CELL_SIZE = 320
DEFAULT_BACKEND = "official"
DEFAULT_HF_MODEL_ID = "IDEA-Research/grounding-dino-tiny"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
HEAD_COLOR = (255, 48, 184)
EBIKE_COLOR = (255, 170, 58)
TEXT_BG = (0, 0, 0, 180)
GRID_COLOR = (255, 255, 255, 88)


STAGE_SPECS = {
    "smoke": {
        "summary_name": "smoke",
        "review_limit": 3,
    },
    "pilot32": {
        "summary_name": "pilot32",
        "quotas": {"zero": 8, "one": 16, "multi": 8},
        "review_limit": 32,
    },
    "validate200": {
        "summary_name": "validate200",
        "quotas": {"zero": 40, "one": 120, "multi": 40},
        "review_limit": 200,
    },
}


@dataclass(frozen=True)
class SourceRecord:
    split: str
    image_name: str
    image_path: Path
    label_path: Path
    image_id: str
    width: int
    height: int
    resolution: str
    source_index: int
    person_count: int
    ebike_boxes: List[List[float]]

    @property
    def ebike_count(self) -> int:
        return len(self.ebike_boxes)

    @property
    def max_dim(self) -> int:
        return max(self.width, self.height)


@dataclass
class StagePrediction:
    record: SourceRecord
    head_boxes: List[List[float]]
    head_scores: List[float]
    used_slicing: bool
    slice_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Grounding DINO head annotation workflow")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("smoke", "pilot32", "validate200"):
        subparser = subparsers.add_parser(command, help=f"Run the {command} stage")
        add_common_args(subparser)

    return parser.parse_args()


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS_PATH)
    parser.add_argument("--backend", choices=("official", "hf"), default=DEFAULT_BACKEND)
    parser.add_argument("--hf-model-id", default=DEFAULT_HF_MODEL_ID)
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--box-threshold", type=float, default=DEFAULT_BOX_THRESHOLD)
    parser.add_argument("--text-threshold", type=float, default=DEFAULT_TEXT_THRESHOLD)
    parser.add_argument("--slice-size", type=int, default=DEFAULT_SLICE_SIZE)
    parser.add_argument("--overlap", type=float, default=DEFAULT_OVERLAP)
    parser.add_argument("--nms-iou", type=float, default=DEFAULT_NMS_IOU)
    parser.add_argument("--slice-trigger-max-dim", type=int, default=DEFAULT_SLICE_TRIGGER_MAX_DIM)
    parser.add_argument("--contact-columns", type=int, default=DEFAULT_CONTACT_COLUMNS)
    parser.add_argument("--cell-size", type=int, default=DEFAULT_CELL_SIZE)
    parser.add_argument("--force", action="store_true", help="Replace an existing stage directory.")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: object) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_yaml(path: Path, payload: dict) -> None:
    ensure_dir(path.parent)
    lines: List[str] = []
    for key, value in payload.items():
        if isinstance(value, dict):
            lines.append(f"{key}:")
            for inner_key, inner_value in value.items():
                lines.append(f"  {inner_key}: {inner_value}")
        else:
            lines.append(f"{key}: {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Sequence[dict], fieldnames: Sequence[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def safe_symlink(src: Path, dst: Path) -> None:
    ensure_dir(dst.parent)
    if dst.exists() or dst.is_symlink():
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    dst.symlink_to(src)


def load_font(size: int = 18) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if not path.exists():
            continue
        try:
            return ImageFont.truetype(str(path), size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def extract_numeric_index(name: str) -> int:
    match = re.search(r"\((\d+)\)", name)
    if match:
        return int(match.group(1))
    digits = re.findall(r"\d+", name)
    if digits:
        return int(digits[-1])
    return 0


def parse_yolo_label(path: Path) -> List[List[float]]:
    boxes: List[List[float]] = []
    if not path.exists():
        return boxes
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 5:
            raise ValueError(f"invalid YOLO line in {path}: {line!r}")
        boxes.append([float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])])
    return boxes


def format_yolo_line(class_id: int, box: Sequence[float]) -> str:
    x_center, y_center, width, height = box
    return f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"


def clamp_box(box: Sequence[float]) -> List[float]:
    x_center, y_center, width, height = [float(value) for value in box]
    width = min(max(width, 1e-6), 1.0)
    height = min(max(height, 1e-6), 1.0)
    x_center = min(max(x_center, width / 2.0), 1.0 - width / 2.0)
    y_center = min(max(y_center, height / 2.0), 1.0 - height / 2.0)
    return [x_center, y_center, width, height]


def box_to_xyxy(box: Sequence[float], width: int, height: int) -> List[float]:
    x_center, y_center, box_width, box_height = [float(value) for value in box]
    return [
        (x_center - box_width / 2.0) * width,
        (y_center - box_height / 2.0) * height,
        (x_center + box_width / 2.0) * width,
        (y_center + box_height / 2.0) * height,
    ]


def xyxy_to_yolo(box: Sequence[float], width: int, height: int) -> List[float]:
    x1, y1, x2, y2 = [float(value) for value in box]
    x1 = min(max(x1, 0.0), float(width))
    y1 = min(max(y1, 0.0), float(height))
    x2 = min(max(x2, 0.0), float(width))
    y2 = min(max(y2, 0.0), float(height))
    box_width = max(1e-6, x2 - x1)
    box_height = max(1e-6, y2 - y1)
    x_center = x1 + box_width / 2.0
    y_center = y1 + box_height / 2.0
    return clamp_box([x_center / width, y_center / height, box_width / width, box_height / height])


def yolo_to_pixels(box: Sequence[float], width: int, height: int) -> Tuple[int, int, int, int]:
    x_center, y_center, box_width, box_height = [float(value) for value in box]
    x1 = int(round((x_center - box_width / 2.0) * width))
    y1 = int(round((y_center - box_height / 2.0) * height))
    x2 = int(round((x_center + box_width / 2.0) * width))
    y2 = int(round((y_center + box_height / 2.0) * height))
    return x1, y1, x2, y2


def iou_xyxy(box_a: Sequence[float], box_b: Sequence[float]) -> float:
    ax1, ay1, ax2, ay2 = [float(value) for value in box_a]
    bx1, by1, bx2, by2 = [float(value) for value in box_b]
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter = inter_w * inter_h
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def nms_xyxy(boxes: Sequence[Sequence[float]], scores: Sequence[float], threshold: float) -> List[int]:
    order = sorted(range(len(boxes)), key=lambda index: scores[index], reverse=True)
    keep: List[int] = []
    while order:
        current = order.pop(0)
        keep.append(current)
        order = [index for index in order if iou_xyxy(boxes[current], boxes[index]) <= threshold]
    return keep


def iter_images(image_dir: Path) -> List[Path]:
    return sorted(
        [path for path in image_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES],
        key=lambda path: (extract_numeric_index(path.name), path.name),
    )


def load_source_records(dataset_root: Path) -> List[SourceRecord]:
    records: List[SourceRecord] = []
    for split in ("train", "val"):
        image_dir = dataset_root / "images" / split
        label_dir = dataset_root / "labels" / split
        if not image_dir.exists():
            raise FileNotFoundError(f"missing image dir: {image_dir}")
        if not label_dir.exists():
            raise FileNotFoundError(f"missing label dir: {label_dir}")
        for image_path in iter_images(image_dir):
            label_path = label_dir / f"{image_path.stem}.txt"
            parsed = parse_yolo_label(label_path)
            person_count = sum(1 for row in parsed if int(row[0]) == 0)
            ebike_boxes = [clamp_box(row[1:]) for row in parsed if int(row[0]) == 1]
            with Image.open(image_path) as image:
                width, height = image.size
            records.append(
                SourceRecord(
                    split=split,
                    image_name=image_path.name,
                    image_path=image_path,
                    label_path=label_path,
                    image_id=image_path.stem,
                    width=width,
                    height=height,
                    resolution=f"{width}x{height}",
                    source_index=extract_numeric_index(image_path.name),
                    person_count=person_count,
                    ebike_boxes=ebike_boxes,
                )
            )
    return records


def person_bucket(person_count: int) -> str:
    if person_count == 0:
        return "zero"
    if person_count == 1:
        return "one"
    return "multi"


def round_robin_select(records: Sequence[SourceRecord], limit: int) -> List[SourceRecord]:
    grouped: Dict[Tuple[str, str], Deque[SourceRecord]] = {}
    for key, bucket_records in group_by_split_resolution(records).items():
        grouped[key] = deque(sorted(bucket_records, key=lambda item: (item.source_index, item.image_name)))
    bucket_order = sorted(grouped.keys(), key=lambda key: (-len(grouped[key]), split_order(key[0]), key[1]))
    selected: List[SourceRecord] = []
    while len(selected) < limit and bucket_order:
        next_order: List[Tuple[str, str]] = []
        for key in bucket_order:
            bucket = grouped[key]
            if not bucket:
                continue
            selected.append(bucket.popleft())
            if len(selected) >= limit:
                break
            if bucket:
                next_order.append(key)
        bucket_order = next_order
    if len(selected) != limit:
        raise RuntimeError(f"unable to sample {limit} records; only got {len(selected)}")
    return selected


def group_by_split_resolution(records: Sequence[SourceRecord]) -> Dict[Tuple[str, str], List[SourceRecord]]:
    grouped: Dict[Tuple[str, str], List[SourceRecord]] = defaultdict(list)
    for record in records:
        grouped[(record.split, record.resolution)].append(record)
    return grouped


def split_order(split: str) -> int:
    return 0 if split == "val" else 1


def select_smoke_records(records: Sequence[SourceRecord]) -> List[SourceRecord]:
    ordered = sorted(records, key=lambda item: (split_order(item.split), item.source_index, item.image_name))
    chosen: List[SourceRecord] = []

    def pick(predicate) -> Optional[SourceRecord]:
        for item in ordered:
            if item in chosen:
                continue
            if predicate(item):
                chosen.append(item)
                return item
        return None

    large = pick(lambda item: item.person_count > 0 and item.max_dim > DEFAULT_SLICE_TRIGGER_MAX_DIM)
    if large is None:
        raise RuntimeError("smoke selection failed: no large image with person annotations found")

    medium_sizes = {"704x576", "960x544", "640x480", "352x288"}
    medium = pick(lambda item: item.person_count > 0 and item.max_dim <= DEFAULT_SLICE_TRIGGER_MAX_DIM and item.resolution in medium_sizes)
    if medium is None:
        medium = pick(lambda item: item.person_count > 0 and item.max_dim <= DEFAULT_SLICE_TRIGGER_MAX_DIM)
    if medium is None:
        raise RuntimeError("smoke selection failed: no medium image with person annotations found")

    empty = pick(lambda item: item.person_count == 0)
    if empty is None:
        raise RuntimeError("smoke selection failed: no person=0 image found")
    return chosen


def select_stage_records(records: Sequence[SourceRecord], stage_name: str) -> List[SourceRecord]:
    if stage_name == "smoke":
        return select_smoke_records(records)
    quotas = STAGE_SPECS[stage_name]["quotas"]
    selected: List[SourceRecord] = []
    for bucket_name, limit in quotas.items():
        bucket_records = [record for record in records if person_bucket(record.person_count) == bucket_name]
        if len(bucket_records) < limit:
            raise RuntimeError(f"not enough records for bucket {bucket_name}: need {limit}, found {len(bucket_records)}")
        selected.extend(round_robin_select(bucket_records, limit))
    return sorted(selected, key=lambda item: (split_order(item.split), item.source_index, item.image_name))


class OfficialGroundingDinoBackend:
    def __init__(
        self,
        *,
        config_path: Path,
        weights_path: Path,
        device: str,
        box_threshold: float,
        text_threshold: float,
    ) -> None:
        self.config_path = config_path
        self.weights_path = weights_path
        self.device = device
        self.box_threshold = box_threshold
        self.text_threshold = text_threshold
        self._load()

    def _load(self) -> None:
        if not self.config_path.exists():
            raise FileNotFoundError(f"missing Grounding DINO config: {self.config_path}")
        if not self.weights_path.exists():
            raise FileNotFoundError(f"missing Grounding DINO weights: {self.weights_path}")
        try:
            import torch
            import groundingdino.datasets.transforms as transforms
            from groundingdino.util.inference import load_model
            from groundingdino.util.utils import get_phrases_from_posmap
        except ImportError as exc:
            raise RuntimeError(
                "Grounding DINO is not installed in the active environment. "
                "Use the gdino310 conda env and install the official dependencies first."
            ) from exc
        self.torch = torch
        self.transforms = transforms
        self.get_phrases_from_posmap = get_phrases_from_posmap
        self.model = load_model(str(self.config_path), str(self.weights_path))
        self.model = self.model.to(self.device)
        self.model.eval()
        self.transform = transforms.Compose(
            [
                transforms.RandomResize([800], max_size=1333),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )

    def predict_pil(self, image: Image.Image, caption: str) -> Tuple[List[List[float]], List[float], List[str]]:
        caption = preprocess_caption(caption)
        image_tensor, _ = self.transform(image.convert("RGB"), None)
        image_tensor = image_tensor.to(self.device)
        with self.torch.no_grad():
            outputs = self.model(image_tensor[None], captions=[caption])
        prediction_logits = outputs["pred_logits"].cpu().sigmoid()[0]
        prediction_boxes = outputs["pred_boxes"].cpu()[0]
        prediction_scores = prediction_logits.max(dim=1)[0]
        keep_mask = prediction_scores > self.box_threshold
        logits = prediction_logits[keep_mask]
        boxes = prediction_boxes[keep_mask]
        scores = prediction_scores[keep_mask]
        tokenizer = self.model.tokenizer
        tokenized = tokenizer(caption)
        phrases = [
            self.get_phrases_from_posmap(logit > self.text_threshold, tokenized, tokenizer).replace(".", "").strip()
            for logit in logits
        ]
        return boxes.tolist(), scores.tolist(), phrases


class HuggingFaceGroundingDinoBackend:
    def __init__(
        self,
        *,
        model_id: str,
        device: str,
        box_threshold: float,
        text_threshold: float,
    ) -> None:
        self.model_id = model_id
        self.device = device
        self.box_threshold = box_threshold
        self.text_threshold = text_threshold
        self._load()

    def _load(self) -> None:
        try:
            import torch
            from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
        except ImportError as exc:
            raise RuntimeError(
                "The Hugging Face Grounding DINO backend requires transformers. "
                "Install it in the active Python 3.10 environment first."
            ) from exc
        self.torch = torch
        self.processor = AutoProcessor.from_pretrained(self.model_id)
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained(self.model_id)
        self.model = self.model.to(self.device)
        self.model.eval()

    def predict_pil(self, image: Image.Image, caption: str) -> Tuple[List[List[float]], List[float], List[str]]:
        normalized_caption = preprocess_caption(caption)
        inputs = self.processor(images=image, text=normalized_caption, return_tensors="pt")
        prepared_inputs = {}
        for key, value in inputs.items():
            if hasattr(value, "to"):
                prepared_inputs[key] = value.to(self.device)
            else:
                prepared_inputs[key] = value
        with self.torch.no_grad():
            outputs = self.model(**prepared_inputs)
        target_sizes = self.torch.tensor([[image.size[1], image.size[0]]], device=self.device)
        result = self.processor.post_process_grounded_object_detection(
            outputs,
            prepared_inputs["input_ids"],
            box_threshold=self.box_threshold,
            text_threshold=self.text_threshold,
            target_sizes=target_sizes,
        )[0]
        width, height = image.size
        boxes = [xyxy_to_yolo(box, width, height) for box in result["boxes"].detach().cpu().tolist()]
        scores = [float(score) for score in result["scores"].detach().cpu().tolist()]
        labels = [str(label) for label in result["labels"]]
        return boxes, scores, labels


def create_backend(args: argparse.Namespace):
    if args.backend == "hf":
        return HuggingFaceGroundingDinoBackend(
            model_id=args.hf_model_id,
            device=args.device,
            box_threshold=args.box_threshold,
            text_threshold=args.text_threshold,
        )
    return OfficialGroundingDinoBackend(
        config_path=args.config,
        weights_path=args.weights,
        device=args.device,
        box_threshold=args.box_threshold,
        text_threshold=args.text_threshold,
    )


def preprocess_caption(caption: str) -> str:
    normalized = caption.strip().lower()
    if not normalized.endswith("."):
        normalized += "."
    return normalized


def generate_slices(width: int, height: int, slice_size: int, overlap: float) -> List[Tuple[int, int, int, int]]:
    x_starts = sliding_window_starts(width, slice_size, overlap)
    y_starts = sliding_window_starts(height, slice_size, overlap)
    windows: List[Tuple[int, int, int, int]] = []
    for y_start in y_starts:
        for x_start in x_starts:
            x_end = min(width, x_start + slice_size)
            y_end = min(height, y_start + slice_size)
            windows.append((x_start, y_start, x_end, y_end))
    return windows


def sliding_window_starts(length: int, window: int, overlap: float) -> List[int]:
    if length <= window:
        return [0]
    stride = max(1, int(round(window * (1.0 - overlap))))
    starts = list(range(0, max(length - window, 0) + 1, stride))
    last_start = length - window
    if starts[-1] != last_start:
        starts.append(last_start)
    return starts


def infer_record(
    record: SourceRecord,
    *,
    backend,
    prompt: str,
    slice_trigger_max_dim: int,
    slice_size: int,
    overlap: float,
    nms_iou: float,
) -> StagePrediction:
    with Image.open(record.image_path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        candidate_boxes_xyxy: List[List[float]] = []
        candidate_scores: List[float] = []
        used_slicing = record.max_dim > slice_trigger_max_dim
        slice_count = 0

        if used_slicing:
            for x1, y1, x2, y2 in generate_slices(width, height, slice_size, overlap):
                crop = rgb.crop((x1, y1, x2, y2))
                boxes, scores, _phrases = backend.predict_pil(crop, prompt)
                slice_count += 1
                crop_width = x2 - x1
                crop_height = y2 - y1
                for box, score in zip(boxes, scores):
                    crop_xyxy = box_to_xyxy(box, crop_width, crop_height)
                    candidate_boxes_xyxy.append(
                        [
                            crop_xyxy[0] + x1,
                            crop_xyxy[1] + y1,
                            crop_xyxy[2] + x1,
                            crop_xyxy[3] + y1,
                        ]
                    )
                    candidate_scores.append(float(score))
        else:
            boxes, scores, _phrases = backend.predict_pil(rgb, prompt)
            slice_count = 1
            for box, score in zip(boxes, scores):
                candidate_boxes_xyxy.append(box_to_xyxy(box, width, height))
                candidate_scores.append(float(score))

    if not candidate_boxes_xyxy:
        return StagePrediction(record=record, head_boxes=[], head_scores=[], used_slicing=used_slicing, slice_count=slice_count)

    keep_indices = nms_xyxy(candidate_boxes_xyxy, candidate_scores, nms_iou)
    kept_boxes = [xyxy_to_yolo(candidate_boxes_xyxy[index], width, height) for index in keep_indices]
    kept_scores = [round(float(candidate_scores[index]), 6) for index in keep_indices]
    ordered = sorted(range(len(kept_boxes)), key=lambda index: kept_scores[index], reverse=True)
    return StagePrediction(
        record=record,
        head_boxes=[kept_boxes[index] for index in ordered],
        head_scores=[kept_scores[index] for index in ordered],
        used_slicing=used_slicing,
        slice_count=slice_count,
    )


def draw_box_set(
    draw: ImageDraw.ImageDraw,
    boxes: Sequence[Sequence[float]],
    scores: Optional[Sequence[float]],
    image_width: int,
    image_height: int,
    *,
    color: Tuple[int, int, int],
    label_prefix: str,
    font: ImageFont.ImageFont,
) -> None:
    for index, box in enumerate(boxes, start=1):
        x1, y1, x2, y2 = yolo_to_pixels(box, image_width, image_height)
        draw.rectangle((x1, y1, x2, y2), outline=color, width=3)
        label = f"{label_prefix}{index}"
        if scores is not None and index - 1 < len(scores):
            label = f"{label} {scores[index - 1]:.2f}"
        text_box = draw.textbbox((0, 0), label, font=font)
        text_width = text_box[2] - text_box[0]
        text_height = text_box[3] - text_box[1]
        top = max(0, y1 - text_height - 8)
        draw.rectangle((x1, top, x1 + text_width + 8, top + text_height + 6), fill=color)
        draw.text((x1 + 4, top + 2), label, font=font, fill=(0, 0, 0))


def render_overlay(prediction: StagePrediction) -> Image.Image:
    with Image.open(prediction.record.image_path) as source_image:
        image = source_image.convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    font = load_font(18)
    draw_box_set(
        draw,
        prediction.record.ebike_boxes,
        None,
        prediction.record.width,
        prediction.record.height,
        color=EBIKE_COLOR,
        label_prefix="e",
        font=font,
    )
    draw_box_set(
        draw,
        prediction.head_boxes,
        prediction.head_scores,
        prediction.record.width,
        prediction.record.height,
        color=HEAD_COLOR,
        label_prefix="h",
        font=font,
    )
    header = (
        f"{prediction.record.image_name} | person_gt={prediction.record.person_count} "
        f"ebike={prediction.record.ebike_count} head_pred={len(prediction.head_boxes)}"
    )
    draw.rectangle((0, 0, min(prediction.record.width, 1800), 34), fill=TEXT_BG)
    draw.text((10, 8), header, font=font, fill=(255, 255, 255))
    return image


def build_cell_image(image_path: Path, *, title: str, footer: str, cell_size: int) -> Image.Image:
    image = Image.open(image_path).convert("RGB").resize((cell_size, cell_size), Image.Resampling.BILINEAR)
    draw = ImageDraw.Draw(image, "RGBA")
    font = load_font(16)
    for divider in (0.25, 0.5, 0.75):
        x = int(round(cell_size * divider))
        y = int(round(cell_size * divider))
        draw.line((x, 0, x, cell_size), fill=GRID_COLOR, width=1)
        draw.line((0, y, cell_size, y), fill=GRID_COLOR, width=1)
    draw.rectangle((0, 0, cell_size - 1, cell_size - 1), outline=(255, 255, 255, 140), width=2)
    title_box = draw.textbbox((0, 0), title, font=font)
    footer_box = draw.textbbox((0, 0), footer, font=font)
    title_height = title_box[3] - title_box[1]
    footer_height = footer_box[3] - footer_box[1]
    draw.rectangle((0, 0, cell_size, title_height + 12), fill=TEXT_BG)
    draw.rectangle((0, cell_size - footer_height - 12, cell_size, cell_size), fill=TEXT_BG)
    draw.text((8, 6), title, font=font, fill=(255, 255, 255))
    draw.text((8, cell_size - footer_height - 8), footer, font=font, fill=(255, 255, 255))
    return image


def compose_contact_sheets(
    rows: Sequence[dict],
    *,
    output_dir: Path,
    columns: int,
    cell_size: int,
) -> List[dict]:
    ensure_dir(output_dir)
    per_sheet = columns * columns
    manifests: List[dict] = []
    for offset in range(0, len(rows), per_sheet):
        chunk = rows[offset:offset + per_sheet]
        sheet_index = offset // per_sheet + 1
        grid_rows = math.ceil(len(chunk) / columns)
        canvas = Image.new("RGB", (columns * cell_size, grid_rows * cell_size), (18, 18, 18))
        cells: List[dict] = []
        for chunk_index, row in enumerate(chunk):
            grid_id = f"grid_{chunk_index + 1:02d}"
            title = f"{grid_id} | {row['image_name']}"
            footer = (
                f"{row['resolution']} | head={row['head_pred_count']} "
                f"ebike={row['ebike_count']} delta={row['count_delta']}"
            )
            cell_image = build_cell_image(Path(row["overlay_path"]), title=title, footer=footer, cell_size=cell_size)
            row_index = chunk_index // columns
            column_index = chunk_index % columns
            canvas.paste(cell_image, (column_index * cell_size, row_index * cell_size))
            cells.append(
                {
                    "grid_id": grid_id,
                    "image_name": row["image_name"],
                    "split": row["split"],
                    "overlay_path": row["overlay_path"],
                    "label_path": row["label_path"],
                }
            )
        sheet_path = output_dir / f"sheet_{sheet_index:03d}.png"
        canvas.save(sheet_path)
        manifests.append({"sheet_path": str(sheet_path), "cells": cells})
    return manifests


def create_preview_dataset(predictions: Sequence[StagePrediction], preview_root: Path) -> None:
    if preview_root.exists():
        shutil.rmtree(preview_root)
    ensure_dir(preview_root / "images")
    ensure_dir(preview_root / "labels")
    present_splits = sorted({prediction.record.split for prediction in predictions})
    for prediction in predictions:
        image_dst = preview_root / "images" / prediction.record.split / prediction.record.image_name
        label_dst = preview_root / "labels" / prediction.record.split / f"{prediction.record.image_id}.txt"
        safe_symlink(prediction.record.image_path, image_dst)
        label_lines = [format_yolo_line(0, box) for box in prediction.head_boxes]
        label_lines.extend(format_yolo_line(1, box) for box in prediction.record.ebike_boxes)
        ensure_dir(label_dst.parent)
        label_dst.write_text("\n".join(label_lines) + ("\n" if label_lines else ""), encoding="utf-8")
    yaml_payload = {
        "path": str(preview_root),
        "names": {0: "head", 1: "ebike"},
        "nc": 2,
    }
    if "train" in present_splits:
        yaml_payload["train"] = "images/train"
    if "val" in present_splits:
        yaml_payload["val"] = "images/val"
    write_yaml(preview_root / "data.yaml", yaml_payload)


def verify_label_output(label_path: Path, prediction: StagePrediction) -> Tuple[int, bool]:
    parsed = parse_yolo_label(label_path)
    invalid_box_count = 0
    out_head_boxes = [row[1:] for row in parsed if int(row[0]) == 0]
    out_ebike_boxes = [row[1:] for row in parsed if int(row[0]) == 1]
    for box in out_head_boxes + out_ebike_boxes:
        if any(value < 0.0 or value > 1.0 for value in box):
            invalid_box_count += 1
    normalized_output = [[round(float(value), 6) for value in box] for box in out_ebike_boxes]
    normalized_source = [[round(float(value), 6) for value in box] for box in prediction.record.ebike_boxes]
    ebike_copy_ok = normalized_output == normalized_source
    return invalid_box_count, ebike_copy_ok


def build_stage_rows(predictions: Sequence[StagePrediction], stage_dir: Path) -> Tuple[List[dict], List[dict]]:
    overlays_dir = stage_dir / "overlays"
    labels_dir = stage_dir / "labels"
    raw_rows: List[dict] = []
    per_image_rows: List[dict] = []
    for prediction in predictions:
        overlay_path = overlays_dir / prediction.record.split / prediction.record.image_name
        label_path = labels_dir / prediction.record.split / f"{prediction.record.image_id}.txt"
        ensure_dir(overlay_path.parent)
        ensure_dir(label_path.parent)
        overlay = render_overlay(prediction)
        overlay.save(overlay_path)
        label_lines = [format_yolo_line(0, box) for box in prediction.head_boxes]
        label_lines.extend(format_yolo_line(1, box) for box in prediction.record.ebike_boxes)
        label_path.write_text("\n".join(label_lines) + ("\n" if label_lines else ""), encoding="utf-8")
        invalid_box_count, ebike_copy_ok = verify_label_output(label_path, prediction)
        count_delta = len(prediction.head_boxes) - prediction.record.person_count
        empty_frame_false_positive = prediction.record.person_count == 0 and len(prediction.head_boxes) > 0
        missed_all_heads = prediction.record.person_count > 0 and len(prediction.head_boxes) == 0
        high_delta_priority = (
            empty_frame_false_positive
            or missed_all_heads
            or abs(count_delta) >= max(2, prediction.record.person_count)
        )
        raw_rows.append(
            {
                "split": prediction.record.split,
                "image_name": prediction.record.image_name,
                "image_path": str(prediction.record.image_path),
                "label_path": str(label_path),
                "overlay_path": str(overlay_path),
                "resolution": prediction.record.resolution,
                "person_gt_count": prediction.record.person_count,
                "ebike_count": prediction.record.ebike_count,
                "head_boxes": prediction.head_boxes,
                "head_scores": prediction.head_scores,
                "used_slicing": prediction.used_slicing,
                "slice_count": prediction.slice_count,
            }
        )
        per_image_rows.append(
            {
                "split": prediction.record.split,
                "image_name": prediction.record.image_name,
                "image_path": str(prediction.record.image_path),
                "label_path": str(label_path),
                "overlay_path": str(overlay_path),
                "width": prediction.record.width,
                "height": prediction.record.height,
                "resolution": prediction.record.resolution,
                "person_gt_count": prediction.record.person_count,
                "head_pred_count": len(prediction.head_boxes),
                "count_delta": count_delta,
                "ebike_count": prediction.record.ebike_count,
                "empty_frame_false_positive": int(empty_frame_false_positive),
                "missed_all_heads": int(missed_all_heads),
                "high_delta_priority": int(high_delta_priority),
                "used_slicing": int(prediction.used_slicing),
                "slice_count": prediction.slice_count,
                "max_head_score": round(max(prediction.head_scores), 6) if prediction.head_scores else 0.0,
                "mean_head_score": round(sum(prediction.head_scores) / len(prediction.head_scores), 6) if prediction.head_scores else 0.0,
                "invalid_box_count": invalid_box_count,
                "ebike_copy_ok": int(ebike_copy_ok),
            }
        )
    return raw_rows, per_image_rows


def summarize_by_key(rows: Sequence[dict], key: str) -> Dict[str, dict]:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(row)
    summary: Dict[str, dict] = {}
    for group_key, group_rows in grouped.items():
        summary[group_key] = aggregate_rows(group_rows)
    return dict(sorted(summary.items()))


def aggregate_rows(rows: Sequence[dict]) -> dict:
    return {
        "images": len(rows),
        "person_gt_total": sum(int(row["person_gt_count"]) for row in rows),
        "head_pred_total": sum(int(row["head_pred_count"]) for row in rows),
        "ebike_total": sum(int(row["ebike_count"]) for row in rows),
        "empty_frame_false_positive_total": sum(int(row["empty_frame_false_positive"]) for row in rows),
        "missed_all_heads_total": sum(int(row["missed_all_heads"]) for row in rows),
        "high_delta_priority_total": sum(int(row["high_delta_priority"]) for row in rows),
        "used_slicing_total": sum(int(row["used_slicing"]) for row in rows),
        "mean_abs_count_delta": round(
            sum(abs(int(row["count_delta"])) for row in rows) / len(rows),
            6,
        )
        if rows
        else 0.0,
    }


def engineering_gate(rows: Sequence[dict]) -> dict:
    reasons: List[str] = []
    missing_output_total = sum(
        1
        for row in rows
        if not Path(row["overlay_path"]).exists() or not Path(row["label_path"]).exists()
    )
    invalid_box_total = sum(int(row["invalid_box_count"]) for row in rows)
    ebike_copy_mismatch_total = sum(1 for row in rows if int(row["ebike_copy_ok"]) != 1)
    large_positive_rows = [
        row
        for row in rows
        if max(int(row["width"]), int(row["height"])) > DEFAULT_SLICE_TRIGGER_MAX_DIM and int(row["person_gt_count"]) > 0
    ]
    if missing_output_total > 0:
        reasons.append(f"missing_output_total={missing_output_total}")
    if invalid_box_total > 0:
        reasons.append(f"invalid_box_total={invalid_box_total}")
    if ebike_copy_mismatch_total > 0:
        reasons.append(f"ebike_copy_mismatch_total={ebike_copy_mismatch_total}")
    if large_positive_rows and all(int(row["head_pred_count"]) == 0 for row in large_positive_rows):
        reasons.append("all_large_positive_images_have_zero_head_predictions")
    return {
        "pass": not reasons,
        "reasons": reasons,
        "missing_output_total": missing_output_total,
        "invalid_box_total": invalid_box_total,
        "ebike_copy_mismatch_total": ebike_copy_mismatch_total,
        "large_positive_images": len(large_positive_rows),
    }


def build_quality_report(
    *,
    stage_name: str,
    args: argparse.Namespace,
    stage_dir: Path,
    selected_records: Sequence[SourceRecord],
    raw_rows: Sequence[dict],
    per_image_rows: Sequence[dict],
    contact_manifest_all: Sequence[dict],
    contact_manifest_priority: Sequence[dict],
) -> dict:
    sorted_review_rows = sorted(
        per_image_rows,
        key=lambda row: (
            -int(row["high_delta_priority"]),
            -abs(int(row["count_delta"])),
            -int(row["missed_all_heads"]),
            -int(row["empty_frame_false_positive"]),
            row["split"],
            row["image_name"],
        ),
    )
    report = {
        "stage": stage_name,
        "dataset_root": str(args.dataset_root),
        "run_root": str(args.run_root),
        "stage_dir": str(stage_dir),
        "planned_output_root": str(args.output_root),
        "config_path": str(args.config),
        "weights_path": str(args.weights),
        "device": args.device,
        "backend": args.backend,
        "hf_model_id": args.hf_model_id,
        "prompt": args.prompt,
        "box_threshold": args.box_threshold,
        "text_threshold": args.text_threshold,
        "slice_size": args.slice_size,
        "overlap": args.overlap,
        "nms_iou": args.nms_iou,
        "slice_trigger_max_dim": args.slice_trigger_max_dim,
        "images": len(per_image_rows),
        "selection": {
            "person_zero": sum(1 for row in per_image_rows if int(row["person_gt_count"]) == 0),
            "person_one": sum(1 for row in per_image_rows if int(row["person_gt_count"]) == 1),
            "person_multi": sum(1 for row in per_image_rows if int(row["person_gt_count"]) >= 2),
            "splits": sorted({record.split for record in selected_records}),
            "resolutions": sorted({record.resolution for record in selected_records}),
        },
        "overall": aggregate_rows(per_image_rows),
        "by_split": summarize_by_key(per_image_rows, "split"),
        "by_resolution": summarize_by_key(per_image_rows, "resolution"),
        "engineering_gate": engineering_gate(per_image_rows),
        "top_priority_samples": sorted_review_rows[: min(64, len(sorted_review_rows))],
        "contact_sheets": {
            "all": contact_manifest_all,
            "priority": contact_manifest_priority,
        },
        "raw_detection_path": str(stage_dir / "detections.json"),
        "per_image_csv": str(stage_dir / "per_image.csv"),
        "review_manifest_json": str(stage_dir / "review_manifest.json"),
    }
    return report


def run_stage(args: argparse.Namespace) -> None:
    stage_name = args.command
    stage_dir = args.run_root / stage_name
    if stage_dir.exists():
        if not args.force:
            raise RuntimeError(f"stage dir already exists: {stage_dir} (use --force to replace it)")
        shutil.rmtree(stage_dir)
    ensure_dir(stage_dir)

    records = load_source_records(args.dataset_root)
    selected_records = select_stage_records(records, stage_name)
    print(f"[{stage_name}] selected {len(selected_records)} images", flush=True)

    backend = create_backend(args)

    predictions: List[StagePrediction] = []
    for index, record in enumerate(selected_records, start=1):
        predictions.append(
            infer_record(
                record,
                backend=backend,
                prompt=args.prompt,
                slice_trigger_max_dim=args.slice_trigger_max_dim,
                slice_size=args.slice_size,
                overlap=args.overlap,
                nms_iou=args.nms_iou,
            )
        )
        if index == 1 or index == len(selected_records) or index % 10 == 0:
            print(f"[{stage_name}] processed {index}/{len(selected_records)}", flush=True)

    create_preview_dataset(predictions, stage_dir / "dataset_preview")
    raw_rows, per_image_rows = build_stage_rows(predictions, stage_dir)

    write_json(stage_dir / "sample_manifest.json", [record_to_json(record) for record in selected_records])
    write_json(stage_dir / "detections.json", raw_rows)
    write_csv(stage_dir / "per_image.csv", per_image_rows, fieldnames=per_image_rows[0].keys())

    review_rows = sorted(
        per_image_rows,
        key=lambda row: (
            -int(row["high_delta_priority"]),
            -abs(int(row["count_delta"])),
            row["split"],
            row["image_name"],
        ),
    )
    write_json(stage_dir / "review_manifest.json", review_rows)

    contact_all = compose_contact_sheets(
        per_image_rows,
        output_dir=stage_dir / "contact_sheets" / "all",
        columns=args.contact_columns,
        cell_size=args.cell_size,
    )
    priority_rows = review_rows[: min(len(review_rows), STAGE_SPECS[stage_name]["review_limit"])]
    contact_priority = compose_contact_sheets(
        priority_rows,
        output_dir=stage_dir / "contact_sheets" / "priority",
        columns=args.contact_columns,
        cell_size=args.cell_size,
    )

    report = build_quality_report(
        stage_name=stage_name,
        args=args,
        stage_dir=stage_dir,
        selected_records=selected_records,
        raw_rows=raw_rows,
        per_image_rows=per_image_rows,
        contact_manifest_all=contact_all,
        contact_manifest_priority=contact_priority,
    )
    write_json(stage_dir / "quality_report.json", report)
    print(f"[{stage_name}] wrote outputs to {stage_dir}", flush=True)


def record_to_json(record: SourceRecord) -> dict:
    return {
        "split": record.split,
        "image_name": record.image_name,
        "image_path": str(record.image_path),
        "label_path": str(record.label_path),
        "image_id": record.image_id,
        "width": record.width,
        "height": record.height,
        "resolution": record.resolution,
        "source_index": record.source_index,
        "person_count": record.person_count,
        "ebike_count": record.ebike_count,
    }


def main() -> None:
    args = parse_args()
    run_stage(args)


if __name__ == "__main__":
    main()
