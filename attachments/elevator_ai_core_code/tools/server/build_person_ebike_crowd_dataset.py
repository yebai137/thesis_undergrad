#!/usr/bin/env python3
"""Build a crowd-augmented person+ebike dataset from keyframe labels."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_images(path: Path) -> List[Path]:
    return sorted(item for item in path.iterdir() if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES)


def transfer_file(src: Path, dst: Path, mode: str) -> str:
    ensure_dir(dst.parent)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    if mode == "copy":
        shutil.copy2(src, dst)
        return "copy"
    if mode == "symlink":
        dst.symlink_to(src.resolve())
        return "symlink"
    try:
        os.link(src, dst)
        return "hardlink"
    except OSError:
        shutil.copy2(src, dst)
        return "copy_fallback"


def write_data_yaml(path: Path, dataset_root: Path, *, train_rel: str, val_rel: str) -> None:
    path.write_text(
        "\n".join(
            [
                "# Auto-generated crowd-augmented dataset",
                f"path: {dataset_root}",
                f"train: {train_rel}",
                f"val: {val_rel}",
                "names:",
                "  0: person",
                "  1: ebike",
                "nc: 2",
                "",
            ]
        ),
        encoding="utf-8",
    )


def require_label(label_path: Path) -> Path:
    if not label_path.exists():
        raise FileNotFoundError(f"missing label file: {label_path}")
    return label_path


def write_readme(path: Path, summary: Dict[str, object]) -> None:
    lines = [
        "# personAndEbike crowd-augmented dataset",
        "",
        "- This dataset keeps the original `personAndEbike` validation split unchanged.",
        "- Crowd keyframes are added only to `train/` and physically oversampled.",
        "- `crowd_benchmark/` stores the crowd validation frames as an independent benchmark.",
        "",
        "## Summary",
        "",
        f"- base train images: {summary['base_train_images']}",
        f"- base val images: {summary['base_val_images']}",
        f"- crowd train source images: {summary['crowd_train_source_images']}",
        f"- crowd train oversample factor: {summary['crowd_train_oversample']}",
        f"- crowd train injected images: {summary['crowd_train_injected_images']}",
        f"- crowd val images: {summary['crowd_val_images']}",
        f"- link mode requested: {summary['link_mode_requested']}",
        f"- transfer modes used: {json.dumps(summary['transfer_modes_used'], ensure_ascii=False)}",
        "",
        "## Layout",
        "",
        "- `images/train`, `labels/train`: original base train set + oversampled crowd keyframes",
        "- `images/val`, `labels/val`: original base validation set only",
        "- `crowd_benchmark/images/val`, `crowd_benchmark/labels/val`: independent crowd validation set",
        "- `manifests/crowd_train_manifest.csv`: expanded crowd oversample mapping",
        "",
        "## Notes",
        "",
        "- Build this dataset only after the crowd keyframe labels are reviewed if you want it for authoritative fine-tuning.",
        "- The script can also be used on seed labels for pipeline smoke testing; in that case treat the result as a staging dataset.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def copy_split(
    *,
    images_dir: Path,
    labels_dir: Path,
    out_images_dir: Path,
    out_labels_dir: Path,
    link_mode: str,
    transfer_modes_used: Dict[str, int],
) -> int:
    count = 0
    for image_path in list_images(images_dir):
        label_path = require_label(labels_dir / f"{image_path.stem}.txt")
        image_mode = transfer_file(image_path, out_images_dir / image_path.name, link_mode)
        label_mode = transfer_file(label_path, out_labels_dir / label_path.name, link_mode)
        transfer_modes_used[image_mode] = transfer_modes_used.get(image_mode, 0) + 1
        transfer_modes_used[label_mode] = transfer_modes_used.get(label_mode, 0) + 1
        count += 1
    return count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a crowd-augmented person+ebike dataset")
    parser.add_argument("--base-dir", default="datasets/PandE/personAndEbike")
    parser.add_argument("--crowd-dir", default="datasets/PandE/crowd_keyframes_v1")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--crowd-train-oversample", type=int, default=4)
    parser.add_argument("--link-mode", choices=("hardlink", "copy", "symlink"), default="hardlink")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    base_dir = Path(args.base_dir).resolve()
    crowd_dir = Path(args.crowd_dir).resolve()
    output_dir = Path(args.output_dir).resolve()

    if output_dir.exists():
        if not args.force:
            raise SystemExit(f"output already exists: {output_dir} (use --force to rebuild)")
        shutil.rmtree(output_dir)

    transfer_modes_used: Dict[str, int] = {}
    ensure_dir(output_dir)

    out_images_train = ensure_dir(output_dir / "images" / "train")
    out_images_val = ensure_dir(output_dir / "images" / "val")
    out_labels_train = ensure_dir(output_dir / "labels" / "train")
    out_labels_val = ensure_dir(output_dir / "labels" / "val")
    crowd_benchmark_images_val = ensure_dir(output_dir / "crowd_benchmark" / "images" / "val")
    crowd_benchmark_labels_val = ensure_dir(output_dir / "crowd_benchmark" / "labels" / "val")
    manifests_dir = ensure_dir(output_dir / "manifests")

    base_train_count = copy_split(
        images_dir=base_dir / "images" / "train",
        labels_dir=base_dir / "labels" / "train",
        out_images_dir=out_images_train,
        out_labels_dir=out_labels_train,
        link_mode=args.link_mode,
        transfer_modes_used=transfer_modes_used,
    )
    base_val_count = copy_split(
        images_dir=base_dir / "images" / "val",
        labels_dir=base_dir / "labels" / "val",
        out_images_dir=out_images_val,
        out_labels_dir=out_labels_val,
        link_mode=args.link_mode,
        transfer_modes_used=transfer_modes_used,
    )

    crowd_train_rows: List[Dict[str, object]] = []
    crowd_train_source = 0
    crowd_train_injected = 0
    for image_path in list_images(crowd_dir / "images" / "train"):
        label_path = require_label(crowd_dir / "labels" / "train" / f"{image_path.stem}.txt")
        crowd_train_source += 1
        for repeat_idx in range(args.crowd_train_oversample):
            suffix = image_path.suffix.lower()
            name = f"{image_path.stem}__crowd_os{repeat_idx + 1:02d}{suffix}"
            label_name = f"{image_path.stem}__crowd_os{repeat_idx + 1:02d}.txt"
            image_mode = transfer_file(image_path, out_images_train / name, args.link_mode)
            label_mode = transfer_file(label_path, out_labels_train / label_name, args.link_mode)
            transfer_modes_used[image_mode] = transfer_modes_used.get(image_mode, 0) + 1
            transfer_modes_used[label_mode] = transfer_modes_used.get(label_mode, 0) + 1
            crowd_train_rows.append(
                {
                    "source_image": image_path.name,
                    "source_label": label_path.name,
                    "output_image": name,
                    "output_label": label_name,
                    "repeat_index": repeat_idx + 1,
                }
            )
            crowd_train_injected += 1

    crowd_val_count = copy_split(
        images_dir=crowd_dir / "images" / "val",
        labels_dir=crowd_dir / "labels" / "val",
        out_images_dir=crowd_benchmark_images_val,
        out_labels_dir=crowd_benchmark_labels_val,
        link_mode=args.link_mode,
        transfer_modes_used=transfer_modes_used,
    )

    manifest_path = manifests_dir / "crowd_train_manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["source_image", "source_label", "output_image", "output_label", "repeat_index"],
        )
        writer.writeheader()
        writer.writerows(crowd_train_rows)

    write_data_yaml(output_dir / "data.yaml", output_dir, train_rel="images/train", val_rel="images/val")
    write_data_yaml(
        output_dir / "crowd_benchmark" / "data.yaml",
        output_dir / "crowd_benchmark",
        train_rel="images/val",
        val_rel="images/val",
    )

    summary = {
        "base_dir": str(base_dir),
        "crowd_dir": str(crowd_dir),
        "output_dir": str(output_dir),
        "base_train_images": base_train_count,
        "base_val_images": base_val_count,
        "crowd_train_source_images": crowd_train_source,
        "crowd_train_oversample": args.crowd_train_oversample,
        "crowd_train_injected_images": crowd_train_injected,
        "crowd_val_images": crowd_val_count,
        "train_images_total": base_train_count + crowd_train_injected,
        "val_images_total": base_val_count,
        "link_mode_requested": args.link_mode,
        "transfer_modes_used": transfer_modes_used,
        "manifests": {
            "crowd_train_manifest": str(manifest_path),
        },
        "benchmark": {
            "data_yaml": str(output_dir / "crowd_benchmark" / "data.yaml"),
            "images_val": str(crowd_benchmark_images_val),
            "labels_val": str(crowd_benchmark_labels_val),
        },
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_readme(output_dir / "README.md", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
