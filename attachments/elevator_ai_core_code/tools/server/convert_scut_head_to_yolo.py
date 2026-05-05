#!/usr/bin/env python3
"""
Convert the SCUT_HEAD Pascal VOC dataset into a YOLO-format head-only dataset.

The generated dataset uses a single contiguous class:
    0 -> head

This script is intentionally scoped to the recommended quick-proof path:
train and validate a separate head detector first, without touching the
existing person/ebike dataset or board deployment pipeline.
"""

from __future__ import annotations

import argparse
import json
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from PIL import Image


@dataclass(frozen=True)
class Sample:
    split: str
    stem: str
    image_path: Path
    annotation_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert SCUT_HEAD VOC annotations into YOLO head labels")
    parser.add_argument(
        "--source-root",
        default="/home/ywj/elevator_ai/datasets/SCUT_HEAD",
        help="SCUT_HEAD source root containing SCUT_HEAD_Part_A and SCUT_HEAD_Part_B",
    )
    parser.add_argument(
        "--output-root",
        default="/home/ywj/elevator_ai/datasets/SCUT_HEAD_yolo_head",
        help="output root for the generated YOLO-format dataset",
    )
    parser.add_argument(
        "--class-name",
        default="head",
        help="single output class name to use in data.yaml",
    )
    parser.add_argument(
        "--source-object-name",
        default="person",
        help="object name expected in the source XML annotations",
    )
    parser.add_argument(
        "--copy-images",
        action="store_true",
        help="copy images instead of creating symlinks",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing output directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="only inspect and summarize the conversion plan",
    )
    return parser.parse_args()


def load_split_stems(image_set_file: Path) -> List[str]:
    return [line.strip() for line in image_set_file.read_text(encoding="utf-8").splitlines() if line.strip()]


def iter_samples(source_root: Path) -> Iterable[Sample]:
    for part_dir in sorted(p for p in source_root.iterdir() if p.is_dir()):
        image_set_root = part_dir / "ImageSets" / "Main"
        annotations_dir = part_dir / "Annotations"
        images_dir = part_dir / "JPEGImages"
        for split in ("train", "val", "test"):
            image_set_file = image_set_root / f"{split}.txt"
            if not image_set_file.exists():
                continue
            for stem in load_split_stems(image_set_file):
                yield Sample(
                    split=split,
                    stem=stem,
                    image_path=images_dir / f"{stem}.jpg",
                    annotation_path=annotations_dir / f"{stem}.xml",
                )


def voc_box_to_yolo(size: Tuple[int, int], xmin: float, ymin: float, xmax: float, ymax: float) -> Tuple[float, float, float, float]:
    width, height = size
    x_center = ((xmin + xmax) / 2.0) / width
    y_center = ((ymin + ymax) / 2.0) / height
    box_width = (xmax - xmin) / width
    box_height = (ymax - ymin) / height
    return x_center, y_center, box_width, box_height


def parse_annotation(path: Path, image_path: Path, expected_object_name: str) -> Tuple[Tuple[int, int], List[str]]:
    root = ET.parse(path).getroot()
    width = int(root.findtext("size/width", default="0"))
    height = int(root.findtext("size/height", default="0"))
    if width <= 0 or height <= 0:
        with Image.open(image_path) as image:
            width, height = image.size
        if width <= 0 or height <= 0:
            raise ValueError(f"invalid image size in {path} and could not recover from image file {image_path}")

    labels: List[str] = []
    for obj in root.findall("object"):
        name = (obj.findtext("name") or "").strip()
        if name != expected_object_name:
            continue
        bbox = obj.find("bndbox")
        if bbox is None:
            continue
        xmin = float(bbox.findtext("xmin", default="0"))
        ymin = float(bbox.findtext("ymin", default="0"))
        xmax = float(bbox.findtext("xmax", default="0"))
        ymax = float(bbox.findtext("ymax", default="0"))
        if xmax <= xmin or ymax <= ymin:
            continue
        x_center, y_center, box_width, box_height = voc_box_to_yolo((width, height), xmin, ymin, xmax, ymax)
        labels.append(f"0 {x_center:.6f} {y_center:.6f} {box_width:.6f} {box_height:.6f}")
    return (width, height), labels


def ensure_empty_output(path: Path, *, force: bool) -> None:
    if path.exists():
        if not force:
            raise SystemExit(f"output root already exists: {path} (use --force to overwrite)")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def link_or_copy_image(source: Path, destination: Path, *, copy_images: bool) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        destination.unlink()
    if copy_images:
        shutil.copy2(source, destination)
    else:
        destination.symlink_to(source.resolve())


def write_dataset_yaml(output_root: Path, class_name: str) -> None:
    content = (
        f"path: {output_root}\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n\n"
        "names:\n"
        f"  0: {class_name}\n\n"
        "nc: 1\n"
    )
    (output_root / "data.yaml").write_text(content, encoding="utf-8")


def summarize(samples: List[Sample], expected_object_name: str) -> Dict[str, object]:
    split_counts: Dict[str, int] = {"train": 0, "val": 0, "test": 0}
    object_counts: Dict[str, int] = {"train": 0, "val": 0, "test": 0}
    missing: List[str] = []
    for sample in samples:
        split_counts[sample.split] += 1
        if not sample.image_path.exists() or not sample.annotation_path.exists():
            missing.append(sample.stem)
            continue
        _, labels = parse_annotation(sample.annotation_path, sample.image_path, expected_object_name)
        object_counts[sample.split] += len(labels)
    return {
        "samples_per_split": split_counts,
        "objects_per_split": object_counts,
        "missing_samples": missing,
    }


def convert(samples: List[Sample], output_root: Path, *, class_name: str, expected_object_name: str, copy_images: bool) -> Dict[str, object]:
    split_counts: Dict[str, int] = {"train": 0, "val": 0, "test": 0}
    object_counts: Dict[str, int] = {"train": 0, "val": 0, "test": 0}

    for sample in samples:
        if not sample.image_path.exists():
            raise FileNotFoundError(f"missing image: {sample.image_path}")
        if not sample.annotation_path.exists():
            raise FileNotFoundError(f"missing annotation: {sample.annotation_path}")

        _, labels = parse_annotation(sample.annotation_path, sample.image_path, expected_object_name)
        image_destination = output_root / "images" / sample.split / sample.image_path.name
        label_destination = output_root / "labels" / sample.split / f"{sample.stem}.txt"

        link_or_copy_image(sample.image_path, image_destination, copy_images=copy_images)
        label_destination.parent.mkdir(parents=True, exist_ok=True)
        label_destination.write_text("\n".join(labels) + ("\n" if labels else ""), encoding="utf-8")

        split_counts[sample.split] += 1
        object_counts[sample.split] += len(labels)

    write_dataset_yaml(output_root, class_name)
    return {
        "samples_per_split": split_counts,
        "objects_per_split": object_counts,
        "class_name": class_name,
        "output_root": str(output_root),
    }


def main() -> int:
    args = parse_args()
    source_root = Path(args.source_root).resolve()
    output_root = Path(args.output_root).resolve()

    if not source_root.exists():
        raise SystemExit(f"source root does not exist: {source_root}")

    samples = list(iter_samples(source_root))
    if not samples:
        raise SystemExit(f"no samples discovered under {source_root}")

    summary = summarize(samples, args.source_object_name)
    summary["source_root"] = str(source_root)
    summary["class_name"] = args.class_name
    summary["source_object_name"] = args.source_object_name

    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    ensure_empty_output(output_root, force=args.force)
    result = convert(
        samples,
        output_root,
        class_name=args.class_name,
        expected_object_name=args.source_object_name,
        copy_images=args.copy_images,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
