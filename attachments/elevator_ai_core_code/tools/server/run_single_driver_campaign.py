#!/usr/bin/env python3
"""Single-driver board validation orchestrator.

This script replaces the session-file control loop during the current
single-driver stage. The server remains the only decision-maker. Windows is
used as a board-facing execution hop over the reverse SSH tunnel.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


BASELINE_BATCH = {
    "map50": 0.9562604428428233,
    "person_f1": 0.944,
    "ebike_f1": 0.9702970297029702,
}
FULL_DATASET_ROOT = "/tmp/personAndEbike_gate"
DEFAULT_VIDEO_EXPECTED_PERSON_COUNT = 7
DEFAULT_REFERENCE_VIDEO = "D:/elevator_ai/windows_outputs/20260317_0053_board_param_tuning_round_1_iter_03_stream_chn0.mp4"
DEFAULT_REFERENCE_LABEL = "iter03"
DEFAULT_SERVER_FFMPEG = "/home/ywj/miniconda3/bin/ffmpeg"
SOURCE_FULL_WATCHDOG_MIN_PROCESS_FPS = 4.0
SOURCE_FULL_WATCHDOG_DRAIN_MARGIN_SECONDS = 30.0
FULL_DATASET_DEFAULT_SPLITS: List[Tuple[str, int]] = [
    ("train", 3601),
    ("val", 720),
]
ELEMENTARY_VIDEO_EXTENSIONS = {".h264", ".264", ".h265", ".265"}
CONTAINER_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv"}
ACCEPTANCE_REVIEW_SET = ["test6", "test3", "test5", "test2"]
ACCEPTANCE_ORDER = ["safety", "count", "visual", "gate_resources"]
REVIEW_RECOMMENDATION_VALUES = ["pending", "promote", "keep_as_experiment", "reject"]
VISUAL_REVIEW_SCHEMA_VERSION = 3
VISUAL_REVIEW_SECTION_KEYS = (
    "person_stability",
    "ebike_visibility",
    "public_debug_consistency",
    "counting",
)
VISUAL_REVIEW_READY_SECTION_STATUSES = {"pass", "caveat", "blocker"}
VISUAL_REVIEW_SURFACE_KEYS = ("clean", "public")
VISUAL_REVIEW_FINDING_SURFACES = {"clean", "public", "debug", "raw"}
DEFAULT_FILE_RTSP_PORT = 8555


def discover_ffmpeg_path(
    *,
    exists=os.path.exists,
    which=shutil.which,
) -> Optional[str]:
    if exists(DEFAULT_SERVER_FFMPEG):
        return DEFAULT_SERVER_FFMPEG
    return which("ffmpeg")


def discover_ffprobe_path(
    ffmpeg_path: Optional[str] = None,
    *,
    exists=os.path.exists,
    which=shutil.which,
) -> Optional[str]:
    candidates: List[Path] = []
    if ffmpeg_path:
        candidates.append(Path(ffmpeg_path).with_name("ffprobe"))
    candidates.append(Path(DEFAULT_SERVER_FFMPEG).with_name("ffprobe"))
    for candidate in candidates:
        if exists(str(candidate)):
            return str(candidate)
    return which("ffprobe")


def parse_fractional_rate(raw_value: object) -> Optional[float]:
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if not text or text == "0/0":
        return None
    if "/" in text:
        numerator_text, denominator_text = text.split("/", 1)
        try:
            numerator = float(numerator_text)
            denominator = float(denominator_text)
        except ValueError:
            return None
        if denominator == 0.0:
            return None
        return numerator / denominator
    try:
        return float(text)
    except ValueError:
        return None


def _optional_int(raw_value: object) -> Optional[int]:
    if raw_value is None or raw_value == "N/A":
        return None
    try:
        return int(float(str(raw_value)))
    except ValueError:
        return None


def _optional_float(raw_value: object) -> Optional[float]:
    if raw_value is None or raw_value == "N/A":
        return None
    try:
        return float(str(raw_value))
    except ValueError:
        return None


def probe_video_stream_metadata(
    local_path: Path,
    iter_dir: Optional[Path] = None,
    prefix: str = "media",
) -> Dict[str, object]:
    ffmpeg_path = discover_ffmpeg_path()
    ffprobe_path = discover_ffprobe_path(ffmpeg_path)
    metadata: Dict[str, object] = {
        "source_path": str(local_path),
        "exists": local_path.exists(),
        "file_size_bytes": local_path.stat().st_size if local_path.exists() else None,
        "status": "missing" if not local_path.exists() else "ready",
    }
    if not local_path.exists():
        return metadata
    if not ffprobe_path:
        metadata["status"] = "ffprobe_missing"
        metadata["error"] = "ffprobe not found"
        return metadata

    cmd = [
        ffprobe_path,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,profile,pix_fmt,width,height,avg_frame_rate,r_frame_rate,has_b_frames,level,nb_frames,duration",
        "-of",
        "json",
        str(local_path),
    ]
    result = run_local(cmd, check=False, capture_output=True)
    if iter_dir is not None:
        write_text(iter_dir / f"{prefix}_ffprobe_stdout.json", result.stdout)
        write_text(iter_dir / f"{prefix}_ffprobe_stderr.txt", result.stderr)
    metadata["ffprobe_path"] = ffprobe_path
    if result.returncode != 0:
        metadata["status"] = "ffprobe_failed"
        metadata["error"] = result.stderr[-1000:] if result.stderr else f"ffprobe exited with code {result.returncode}"
        if iter_dir is not None:
            write_json(iter_dir / f"{prefix}_stream_metadata.json", metadata)
        return metadata

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        metadata["status"] = "ffprobe_parse_failed"
        metadata["error"] = str(exc)
        if iter_dir is not None:
            write_json(iter_dir / f"{prefix}_stream_metadata.json", metadata)
        return metadata

    streams = payload.get("streams") if isinstance(payload, dict) else None
    stream = streams[0] if isinstance(streams, list) and streams else {}
    if not isinstance(stream, dict):
        stream = {}
    fps = parse_fractional_rate(stream.get("avg_frame_rate")) or parse_fractional_rate(stream.get("r_frame_rate"))
    duration_seconds = _optional_float(stream.get("duration"))
    frame_count = _optional_int(stream.get("nb_frames"))
    if frame_count is None and duration_seconds is not None and fps is not None:
        frame_count = int(round(duration_seconds * fps))
    metadata.update(
        {
            "status": "ready",
            "codec_name": stream.get("codec_name"),
            "video_codec": stream.get("codec_name"),
            "profile": stream.get("profile"),
            "pix_fmt": stream.get("pix_fmt"),
            "width": _optional_int(stream.get("width")),
            "height": _optional_int(stream.get("height")),
            "fps": round(float(fps), 6) if fps is not None else None,
            "has_b_frames": _optional_int(stream.get("has_b_frames")),
            "level": _optional_int(stream.get("level")),
            "duration_seconds": round(float(duration_seconds), 6) if duration_seconds is not None else None,
            "frame_count": frame_count,
        }
    )
    if iter_dir is not None:
        write_json(iter_dir / f"{prefix}_stream_metadata.json", metadata)
    return metadata


def parse_ffmpeg_duration_seconds(raw_text: str) -> Optional[float]:
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", raw_text)
    if not match:
        return None
    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    return hours * 3600.0 + minutes * 60.0 + seconds


def parse_ffmpeg_video_metadata(raw_text: str, source_path: Path) -> Dict[str, object]:
    video_line = ""
    for line in raw_text.splitlines():
        if " Video:" in line:
            video_line = line.strip()
            break
    duration_seconds = parse_ffmpeg_duration_seconds(raw_text)
    codec_match = re.search(r"Video:\s*([^,\s]+)", video_line)
    size_match = re.search(r"(\d{2,5})x(\d{2,5})", video_line)
    fps_match = re.search(r"(\d+(?:\.\d+)?)\s*fps", video_line)
    return {
        "source_path": str(source_path),
        "duration_seconds": duration_seconds,
        "video_codec": codec_match.group(1) if codec_match else None,
        "width": int(size_match.group(1)) if size_match else None,
        "height": int(size_match.group(2)) if size_match else None,
        "fps": float(fps_match.group(1)) if fps_match else None,
    }


def source_full_timeout_seconds(source_video_metadata: Dict[str, object]) -> int:
    duration = source_video_metadata.get("duration_seconds")
    if duration is None:
        raise SystemExit("source-full duration policy requires source video duration metadata")
    return int(math.ceil(float(duration) * 1.25 + 5.0))


def source_full_watchdog_seconds(
    source_video_metadata: Dict[str, object],
    prepared_input_metadata: Optional[Dict[str, object]] = None,
) -> int:
    nominal_timeout = source_full_timeout_seconds(source_video_metadata)
    metadata_candidates = [
        prepared_input_metadata if isinstance(prepared_input_metadata, dict) else None,
        source_video_metadata,
    ]
    frame_count = None
    for metadata in metadata_candidates:
        if not metadata:
            continue
        raw_frame_count = metadata.get("frame_count")
        if raw_frame_count is not None:
            try:
                frame_count = int(raw_frame_count)
                break
            except (TypeError, ValueError):
                frame_count = None
        duration = metadata.get("duration_seconds")
        fps = metadata.get("fps")
        if duration is not None and fps is not None:
            try:
                frame_count = int(math.ceil(float(duration) * float(fps)))
                break
            except (TypeError, ValueError):
                frame_count = None
    if frame_count is None or frame_count <= 0:
        return nominal_timeout
    slow_board_timeout = int(
        math.ceil(frame_count / SOURCE_FULL_WATCHDOG_MIN_PROCESS_FPS + SOURCE_FULL_WATCHDOG_DRAIN_MARGIN_SECONDS)
    )
    return max(nominal_timeout, slow_board_timeout)


def resolve_video_duration_seconds(args: argparse.Namespace, source_video_metadata: Optional[Dict[str, object]]) -> int:
    policy = str(getattr(args, "duration_policy", "fixed") or "fixed")
    if policy == "source-full":
        return source_full_timeout_seconds(source_video_metadata or {})
    return max(1, int(getattr(args, "duration_seconds", 12)))


def probe_source_video_metadata(local_input_path: Path, iter_dir: Path) -> Dict[str, object]:
    ffmpeg_path = discover_ffmpeg_path()
    if not ffmpeg_path:
        raise SystemExit("ffmpeg not found; source-full video runs require ffmpeg metadata probing")
    result = run_local(
        [ffmpeg_path, "-hide_banner", "-i", str(local_input_path)],
        check=False,
        capture_output=True,
    )
    write_text(iter_dir / "source_video_probe_stdout.txt", result.stdout)
    write_text(iter_dir / "source_video_probe_stderr.txt", result.stderr)
    metadata = parse_ffmpeg_video_metadata(result.stderr + "\n" + result.stdout, local_input_path)
    metadata["ffmpeg_path"] = ffmpeg_path
    metadata["file_size_bytes"] = local_input_path.stat().st_size if local_input_path.exists() else None
    if metadata.get("duration_seconds") is None:
        raise SystemExit(f"failed to read source video duration from {local_input_path}")
    write_json(iter_dir / "source_video_metadata.json", metadata)
    return metadata


def probe_local_media_metadata(local_path: Path) -> Dict[str, object]:
    metadata: Dict[str, object] = {
        "source_path": str(local_path),
        "exists": local_path.exists(),
        "duration_seconds": None,
        "fps": None,
        "frame_count": None,
        "width": None,
        "height": None,
        "file_size_bytes": local_path.stat().st_size if local_path.exists() else None,
    }
    if not local_path.exists():
        metadata["status"] = "missing"
        return metadata
    try:
        import cv2  # type: ignore
    except Exception as exc:
        metadata["status"] = "cv2_missing"
        metadata["error"] = str(exc)
        return metadata

    capture = cv2.VideoCapture(str(local_path))
    if not capture.isOpened():
        metadata["status"] = "open_failed"
        return metadata
    try:
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    finally:
        capture.release()

    duration_seconds = None
    if fps > 0.0 and frame_count > 0:
        duration_seconds = frame_count / fps

    metadata.update(
        {
            "status": "ready",
            "duration_seconds": round(float(duration_seconds), 6) if duration_seconds is not None else None,
            "fps": round(float(fps), 6) if fps > 0.0 else None,
            "frame_count": frame_count if frame_count > 0 else None,
            "width": width if width > 0 else None,
            "height": height if height > 0 else None,
        }
    )
    return metadata


def _fidelity_shortfall(expected: Optional[float], actual: Optional[float]) -> Optional[float]:
    if expected is None or actual is None or expected <= 0.0:
        return None
    return round(float(actual) / float(expected), 6)


def parse_dataset_splits(raw_values: Optional[List[str]]) -> List[Tuple[str, int]]:
    if not raw_values:
        return list(FULL_DATASET_DEFAULT_SPLITS)

    parsed: List[Tuple[str, int]] = []
    for raw in raw_values:
        text = raw.strip()
        if not text:
            continue
        match = re.match(r"^([A-Za-z0-9_-]+)\s*[:=]\s*(\d+)$", text)
        if not match:
            raise SystemExit(f"invalid --dataset-split value: {raw!r}; expected split=count")
        split_name = match.group(1)
        split_count = int(match.group(2))
        if split_count <= 0:
            raise SystemExit(f"dataset split count must be positive: {raw!r}")
        parsed.append((split_name, split_count))
    if not parsed:
        raise SystemExit("at least one dataset split is required")
    return parsed


def total_dataset_images(split_specs: Iterable[Tuple[str, int]]) -> int:
    return sum(count for _, count in split_specs)


def build_review_acceptance_metadata(video_label: Optional[str]) -> Dict[str, object]:
    normalized_label = (video_label or "").strip().lower()
    return {
        "review_set": list(ACCEPTANCE_REVIEW_SET),
        "acceptance_order": list(ACCEPTANCE_ORDER),
        "recommendation_values": list(REVIEW_RECOMMENDATION_VALUES),
        "review_priority": "high" if normalized_label == "test6" else "standard",
        "primary_visual_surface": "clean",
        "secondary_visual_surface": "public",
        "still_artifacts_policy": "navigation_only_not_signoff",
    }


def _resolve_review_input_path(review_path: Path, raw_path: object) -> Optional[Path]:
    if raw_path is None:
        return None
    text = str(raw_path).strip()
    if not text:
        return None
    candidate = Path(text)
    if candidate.is_absolute():
        return candidate
    return (review_path.parent / candidate).resolve()


def _validate_ready_review_pack(review_path: Path, payload: Dict[str, object], errors: List[str]) -> None:
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    if not isinstance(inputs, dict):
        return

    primary_artifact = str(inputs.get("primary_review_artifact") or "").strip()
    if not primary_artifact:
        errors.append("missing_primary_review_artifact")

    review_pack_path = _resolve_review_input_path(review_path, inputs.get("review_pack_json"))
    review_pack: Dict[str, object] = {}
    if review_pack_path and review_pack_path.exists():
        try:
            loaded = json.loads(review_pack_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                review_pack = loaded
        except Exception:
            errors.append("invalid_review_pack_json")
            return

    if review_pack:
        primary_artifact = str(review_pack.get("primary_review_artifact") or primary_artifact).strip()
        clean_payload = review_pack.get("clean") if isinstance(review_pack.get("clean"), dict) else {}
        public_payload = review_pack.get("public") if isinstance(review_pack.get("public"), dict) else {}
        clean_h264 = str(clean_payload.get("preview_video_h264") or clean_payload.get("preview_video") or "").strip()
        public_h264 = str(public_payload.get("preview_video_h264") or public_payload.get("preview_video") or "").strip()
        if primary_artifact and "preview_public" in primary_artifact:
            errors.append("primary_review_artifact_not_clean")
        if clean_h264 and primary_artifact != clean_h264:
            errors.append("primary_review_artifact_not_clean")
        if clean_h264 and public_h264 and clean_h264 == public_h264:
            errors.append("clean_public_aliasing_detected")
        if not clean_h264 or not public_h264:
            errors.append("missing_clean_or_public_surface")
    elif primary_artifact and "preview_public" in primary_artifact:
        errors.append("primary_review_artifact_not_clean")


def validate_visual_review(review_path: Path | str) -> Dict[str, object]:
    path = Path(review_path)
    if not path.exists():
        return {"status": "missing", "errors": ["missing_review_file"], "path": str(path)}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "invalid", "errors": ["invalid_json"], "path": str(path)}

    errors: List[str] = []
    status = str(payload.get("status") or "").strip().lower()
    review_schema_version = int(payload.get("review_schema_version") or 0)
    sections = payload.get("sections") if isinstance(payload.get("sections"), dict) else {}
    findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []
    blocking_issues = payload.get("blocking_issues") if isinstance(payload.get("blocking_issues"), list) else []
    review_method = payload.get("review_method") if isinstance(payload.get("review_method"), dict) else {}
    surface_verdicts = payload.get("surface_verdicts") if isinstance(payload.get("surface_verdicts"), dict) else {}

    if review_schema_version < VISUAL_REVIEW_SCHEMA_VERSION:
        errors.append("review_schema_version_too_old")

    if status == "ready":
        missing_sections = [key for key in VISUAL_REVIEW_SECTION_KEYS if key not in sections]
        if missing_sections:
            errors.append("missing_sections")
        for key in VISUAL_REVIEW_SECTION_KEYS:
            section = sections.get(key) if isinstance(sections, dict) else None
            if not isinstance(section, dict):
                continue
            section_status = str(section.get("status") or "").strip().lower()
            if section_status not in VISUAL_REVIEW_READY_SECTION_STATUSES:
                errors.append("invalid_section_status")
                break
            if not str(section.get("summary") or "").strip():
                errors.append("missing_section_summary")
                break
            evidence_paths = section.get("evidence_paths")
            if not isinstance(evidence_paths, list) or not evidence_paths:
                errors.append("missing_section_evidence_paths")
                break
        if not isinstance(review_method, dict):
            errors.append("missing_review_method")
        else:
            if str(review_method.get("protocol") or "").strip() != "video_primary_with_still_navigation":
                errors.append("invalid_review_method_protocol")
            full_video_watched = review_method.get("full_video_watched") if isinstance(review_method.get("full_video_watched"), dict) else {}
            if not full_video_watched.get("clean") or not full_video_watched.get("public"):
                errors.append("full_video_watched_missing")
            diagnostic_video_reviewed = review_method.get("diagnostic_video_reviewed")
            if not isinstance(diagnostic_video_reviewed, dict):
                errors.append("missing_diagnostic_video_reviewed")
            still_artifacts_used = review_method.get("still_artifacts_used")
            if not isinstance(still_artifacts_used, list):
                errors.append("missing_still_artifacts_used")
            if review_method.get("still_only_verdict") is not False:
                errors.append("still_only_verdict_true")
        missing_surface_verdicts = [key for key in VISUAL_REVIEW_SURFACE_KEYS if key not in surface_verdicts]
        if missing_surface_verdicts:
            errors.append("missing_surface_verdicts")
        else:
            for key in VISUAL_REVIEW_SURFACE_KEYS:
                verdict = surface_verdicts.get(key) if isinstance(surface_verdicts, dict) else None
                if not isinstance(verdict, dict):
                    errors.append("missing_surface_verdicts")
                    break
                verdict_status = str(verdict.get("status") or "").strip().lower()
                if verdict_status not in VISUAL_REVIEW_READY_SECTION_STATUSES:
                    errors.append("invalid_surface_verdict_status")
                    break
                if not str(verdict.get("summary") or "").strip():
                    errors.append("missing_surface_verdict_summary")
                    break
                evidence_paths = verdict.get("evidence_paths")
                if not isinstance(evidence_paths, list) or not evidence_paths:
                    errors.append("missing_surface_verdict_evidence_paths")
                    break
        if not findings:
            errors.append("ready_requires_findings")
        else:
            for finding in findings:
                if not isinstance(finding, dict):
                    errors.append("invalid_finding")
                    break
                surfaces = finding.get("surfaces")
                if (
                    not isinstance(surfaces, list) or
                    not surfaces or
                    any(str(item).strip().lower() not in VISUAL_REVIEW_FINDING_SURFACES for item in surfaces)
                ):
                    errors.append("invalid_finding_surfaces")
                    break
                if not str(finding.get("category") or "").strip():
                    errors.append("missing_finding_category")
                    break
                if str(finding.get("severity") or "").strip().lower() not in {"caveat", "blocker"}:
                    errors.append("invalid_finding_severity")
                    break
                if finding.get("start_timestamp_sec") is None or finding.get("end_timestamp_sec") is None:
                    errors.append("missing_finding_timestamps")
                    break
                if not str(finding.get("summary") or "").strip():
                    errors.append("missing_finding_summary")
                    break
                evidence_paths = finding.get("evidence_paths")
                if not isinstance(evidence_paths, list) or not evidence_paths:
                    errors.append("missing_finding_evidence_paths")
                    break
        _validate_ready_review_pack(path, payload, errors)
        blocker_summaries = [
            str(finding.get("summary") or "").strip()
            for finding in findings
            if isinstance(finding, dict) and str(finding.get("severity") or "").strip().lower() == "blocker"
        ]
        normalized_blocking_issues = [str(item).strip() for item in blocking_issues if str(item).strip()]
        if normalized_blocking_issues != blocker_summaries:
            errors.append("blocking_issues_mismatch")

    result_status = "ready" if not errors and status == "ready" else ("invalid" if errors else status or "pending")
    return {
        "status": result_status,
        "errors": errors,
        "path": str(path),
        "payload": payload,
    }


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def utc_now_string() -> str:
    return datetime.now().isoformat(timespec="seconds")


def parse_key_value_env(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def looks_like_windows_path(value: str) -> bool:
    text = str(value).strip()
    return bool(re.match(r"^[A-Za-z]:[\\/]", text)) or text.startswith("\\\\")


def run_local(
    args: List[str],
    *,
    cwd: Optional[Path] = None,
    check: bool = True,
    capture_output: bool = True,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd is not None else None,
        check=check,
        capture_output=capture_output,
        text=True,
        errors="replace",
    )


def write_text(path: Path, content: str) -> None:
    ensure_directory(path.parent)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: object) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def next_iteration_id(campaign_dir: Path) -> str:
    max_index = 0
    pattern = re.compile(r"iter_(\d+)$")
    if campaign_dir.exists():
        for child in campaign_dir.iterdir():
            if not child.is_dir():
                continue
            match = pattern.match(child.name)
            if match:
                max_index = max(max_index, int(match.group(1)))
    return f"iter_{max_index + 1:02d}"


def current_git_head(repo_root: Path) -> Dict[str, str]:
    revision = run_local(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True,
    ).stdout.strip()
    status = run_local(
        ["git", "-C", str(repo_root), "status", "--short"],
        capture_output=True,
    ).stdout.strip()
    return {
        "head": revision,
        "dirty": "yes" if status else "no",
        "status": status,
    }


def powershell_command(script: str) -> str:
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    return f"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded}"


def package_info_from_dir(package_dir: Path) -> Dict[str, str]:
    resolved_dir = package_dir.resolve()
    binary_path = resolved_dir / "elevator_yolo"
    model_path = resolved_dir / "yolov8.om"
    readme_path = resolved_dir / "README.md"
    for path in (binary_path, model_path, readme_path):
        if not path.exists():
            raise SystemExit(f"missing packaged file: {path}")
    return {
        "package_dir": str(resolved_dir),
        "binary_md5": md5_file(binary_path),
        "model_md5": md5_file(model_path),
    }


def resolve_package_dir(repo_root: Path, iter_dir: Path, args: argparse.Namespace) -> Dict[str, str]:
    reuse_dir = getattr(args, "reuse_package_dir", None)
    if reuse_dir:
        write_text(iter_dir / "build_stdout.txt", f"reuse-package-dir requested: {reuse_dir}\n")
        write_text(iter_dir / "build_stderr.txt", "")
        return package_info_from_dir(Path(reuse_dir).expanduser())
    if bool(getattr(args, "skip_build", False)):
        write_text(iter_dir / "build_stdout.txt", "skip-build requested; using board/out/package\n")
        write_text(iter_dir / "build_stderr.txt", "")
        return package_info_from_dir(repo_root / "board" / "out" / "package")
    return build_board_package(repo_root, iter_dir)


@dataclass
class WindowsConfig:
    host: str
    port: int
    user: str
    repo_root: str
    identity_file: Path


class WindowsRemote:
    def __init__(self, config: WindowsConfig) -> None:
        self.config = config

    def _ssh_base(self) -> List[str]:
        return [
            "ssh",
            "-i",
            str(self.config.identity_file),
            "-p",
            str(self.config.port),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ConnectTimeout=10",
        ]

    def _scp_base(self) -> List[str]:
        return [
            "scp",
            "-i",
            str(self.config.identity_file),
            "-P",
            str(self.config.port),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ConnectTimeout=10",
        ]

    @property
    def remote_host(self) -> str:
        return f"{self.config.user}@{self.config.host}"

    def ssh(self, remote_command: str, *, check: bool = True) -> subprocess.CompletedProcess:
        args = self._ssh_base() + [self.remote_host, remote_command]
        return run_local(args, check=check, capture_output=True)

    def scp_to(self, sources: Iterable[Path], remote_destination: str, *, recursive: bool = False) -> None:
        args = self._scp_base()
        if recursive:
            args.append("-r")
        for source in sources:
            args.append(str(source))
        args.append(f"{self.remote_host}:{remote_destination}")
        run_local(args, check=True, capture_output=True)

    def scp_from(self, remote_source: str, local_destination: Path, *, recursive: bool = False) -> None:
        ensure_directory(local_destination if local_destination.is_dir() else local_destination.parent)
        args = self._scp_base()
        if recursive:
            args.append("-r")
        args.append(f"{self.remote_host}:{remote_source}")
        args.append(str(local_destination))
        run_local(args, check=True, capture_output=True)


def load_windows_config(args: argparse.Namespace) -> WindowsConfig:
    env_values = parse_key_value_env(Path(args.windows_env).expanduser())
    host = args.windows_host or env_values.get("FALLBACK_WINDOWS_HOST") or "127.0.0.1"
    port = args.windows_port or int(env_values.get("FALLBACK_SSH_PORT", "10023"))
    user = args.windows_user or env_values.get("WINDOWS_USER") or "yewei"
    repo_root = args.windows_repo_root or env_values.get("WINDOWS_REPO_ROOT") or "D:/elevator_ai/elevator_ai"
    identity = Path(args.identity_file or env_values.get("IDENTITY_FILE", "")).expanduser()
    if not identity.exists():
        raise SystemExit(f"missing Windows identity file: {identity}")
    return WindowsConfig(
        host=host,
        port=port,
        user=user,
        repo_root=repo_root,
        identity_file=identity,
    )


def ensure_campaign_manifest(campaign_dir: Path, campaign_id: str, config: WindowsConfig, repo_root: Path) -> None:
    manifest_path = campaign_dir / "manifest.md"
    if manifest_path.exists():
        return
    git_info = current_git_head(repo_root)
    content = textwrap.dedent(
        f"""\
        # {campaign_id}

        ## Stage
        - mode: `single-driver`
        - created_at: `{utc_now_string()}`
        - transport: `server -> 127.0.0.1:10023 -> Windows -> board`
        - windows_repo_root: `{config.repo_root}`
        - board_target: `root@192.168.1.168`
        - dataset_path: `/tmp/personAndEbike_gate`

        ## Baseline Batch Gate
        - strategy: `val50 = 25 + 25`
        - score: `0.15`
        - nms: `0.45`
        - success target: `50/50`
        - map50 floor: `{BASELINE_BATCH["map50"]:.10f}`
        - person f1 floor: `{BASELINE_BATCH["person_f1"]:.3f}`
        - ebike f1 floor: `{BASELINE_BATCH["ebike_f1"]:.10f}`

        ## Video Baseline
        - session: `20260317_0053_board_param_tuning_round_1`
        - iteration: `iter_03`
        - input: `/root/data/image/dolls_video.h264`
        - quality target: `high-appearance-balance`

        ## Source Snapshot
        - git_head: `{git_info["head"]}`
        - worktree_dirty: `{git_info["dirty"]}`

        ## Notes
        - This campaign does not use `logs/sessions/*` as a control plane.
        - Iteration artifacts under `iter_XX/` are audit records only.
        """
    )
    write_text(manifest_path, content)

    manifest_json = {
        "campaign_id": campaign_id,
        "created_at": utc_now_string(),
        "windows_repo_root": config.repo_root,
        "board_host": "192.168.1.168",
        "dataset_path": "/tmp/personAndEbike_gate",
        "batch_baseline": BASELINE_BATCH,
        "video_baseline": {
            "session_id": "20260317_0053_board_param_tuning_round_1",
            "iteration_id": "iter_03",
            "input_path": "/root/data/image/dolls_video.h264",
        },
        "git": git_info,
    }
    write_json(campaign_dir / "manifest.json", manifest_json)


def sync_windows_support_files(remote: WindowsRemote, repo_root: Path) -> None:
    files = [
        repo_root / "tools" / "windows" / "Run-DirectBoardIteration.py",
        repo_root / "tools" / "windows" / "Analyze-BoardVideo.py",
        repo_root / "tools" / "windows" / "BoardPreflight.py",
        repo_root / "tools" / "windows" / "README.md",
        repo_root / "doc" / "README.md",
        repo_root / "doc" / "00_Next_Session_Context_Pack.md",
        repo_root / "doc" / "current" / "2026-03-18_Single_Driver_Board_Validation_Stage.md",
        repo_root / "doc" / "current" / "2026-03-18_Single_Driver_Reverse_Tunnel_Experience_Report.md",
        repo_root / "doc" / "handoff" / "2026-03-18_Server_Codex_Reset_Handoff.md",
        repo_root / "doc" / "archive" / "dual_codex_session" / "2026-03-18_Automation_Closed_Loop_Stage.md",
        repo_root / "doc" / "archive" / "dual_codex_session" / "2026-03-17_Windows_Automation_Capability_Note.md",
        repo_root / "doc" / "archive" / "dual_codex_session" / "2026-03-16_Session_Pusher_Service_Runbook.md",
        repo_root / "tools" / "server" / "README.md",
    ]
    if not all(path.exists() for path in files):
        missing = [str(path) for path in files if not path.exists()]
        raise SystemExit("missing support files before Windows sync:\n" + "\n".join(missing))

    remote_dirs = sorted(
        {
            f"{remote.config.repo_root}/{source.relative_to(repo_root).parent.as_posix()}"
            for source in files
        }
    )
    mkdir_script = "; ".join(
        f"New-Item -ItemType Directory -Force -Path '{path}' | Out-Null" for path in remote_dirs
    )
    remote.ssh(powershell_command(mkdir_script))

    for source in files:
        relative_path = source.relative_to(repo_root).as_posix()
        destination = f"{remote.config.repo_root}/{relative_path}"
        remote.scp_to([source], destination)


def create_windows_iter_layout(remote: WindowsRemote, windows_iter_dir: str) -> None:
    script = textwrap.dedent(
        f"""\
        New-Item -ItemType Directory -Force -Path '{windows_iter_dir}' | Out-Null
        New-Item -ItemType Directory -Force -Path '{windows_iter_dir}/artifacts' | Out-Null
        New-Item -ItemType Directory -Force -Path '{windows_iter_dir}/analysis' | Out-Null
        New-Item -ItemType Directory -Force -Path '{windows_iter_dir}/windows_package' | Out-Null
        New-Item -ItemType Directory -Force -Path '{windows_iter_dir}/inputs' | Out-Null
        New-Item -ItemType Directory -Force -Path '{windows_iter_dir}/references' | Out-Null
        """
    ).strip().replace("\n", "; ")
    remote.ssh(powershell_command(script))


def sync_file_to_windows(remote: WindowsRemote, local_path: Path, windows_dir: str) -> str:
    target_name = local_path.name
    remote_path = f"{windows_dir.rstrip('/')}/{target_name}"
    create_script = f"New-Item -ItemType Directory -Force -Path '{windows_dir}' | Out-Null"
    remote.ssh(powershell_command(create_script))
    remote.scp_to([local_path], remote_path)
    return remote_path


def _h264_start_codes(data: bytes) -> Iterable[Tuple[int, int]]:
    index = 0
    length = len(data)
    while index < length - 3:
        if data[index : index + 4] == b"\x00\x00\x00\x01":
            yield index, 4
            index += 4
            continue
        if data[index : index + 3] == b"\x00\x00\x01":
            yield index, 3
            index += 3
            continue
        index += 1


def scan_h264_nal_unit_types(path: Path, *, max_bytes: int = 2 * 1024 * 1024, max_units: int = 32) -> List[int]:
    if not path.exists() or path.stat().st_size <= 0:
        return []
    data = path.read_bytes()[:max_bytes]
    nal_types: List[int] = []
    for offset, prefix_len in _h264_start_codes(data):
        header_index = offset + prefix_len
        if header_index >= len(data):
            continue
        nal_types.append(data[header_index] & 0x1F)
        if len(nal_types) >= max_units:
            break
    return nal_types


def validate_prepared_h264_bitstream(path: Path) -> Dict[str, object]:
    errors: List[str] = []
    nal_types = scan_h264_nal_unit_types(path)
    first_idr_index = next((index for index, nal_type in enumerate(nal_types) if nal_type == 5), None)
    first_sps_index = next((index for index, nal_type in enumerate(nal_types) if nal_type == 7), None)
    first_pps_index = next((index for index, nal_type in enumerate(nal_types) if nal_type == 8), None)

    if not path.exists():
        errors.append("missing_file")
    elif path.stat().st_size <= 0:
        errors.append("empty_file")
    if first_sps_index is None:
        errors.append("missing_sps")
    if first_pps_index is None:
        errors.append("missing_pps")
    if first_idr_index is None:
        errors.append("missing_idr")
    if first_idr_index is not None:
        early_nal_types = nal_types[:first_idr_index]
        if 6 in early_nal_types:
            errors.append("early_sei_before_idr")
        if first_sps_index is not None and first_sps_index > first_idr_index:
            errors.append("sps_after_idr")
        if first_pps_index is not None and first_pps_index > first_idr_index:
            errors.append("pps_after_idr")

    return {
        "schema_version": 1,
        "source_path": str(path),
        "exists": path.exists(),
        "file_size_bytes": path.stat().st_size if path.exists() else None,
        "nal_unit_types": nal_types,
        "status": "blocked" if errors else "ready",
        "errors": errors,
    }


def source_stream_is_copy_compatible_for_board(metadata: Dict[str, object]) -> bool:
    codec = str(metadata.get("codec_name") or metadata.get("video_codec") or "").lower()
    pix_fmt = str(metadata.get("pix_fmt") or "").lower()
    has_b_frames = metadata.get("has_b_frames")
    width = metadata.get("width")
    height = metadata.get("height")
    return (
        codec == "h264"
        and pix_fmt == "yuv420p"
        and has_b_frames == 0
        and isinstance(width, int)
        and width > 0
        and isinstance(height, int)
        and height > 0
    )


def _successful_output(path: Path, result: subprocess.CompletedProcess) -> bool:
    return result.returncode == 0 and path.exists() and path.stat().st_size > 0


def build_prepared_input_metadata(base_metadata: Dict[str, object], prepare_report: Dict[str, object]) -> Dict[str, object]:
    metadata = dict(base_metadata)
    strategy = prepare_report.get("strategy")
    source_stream = prepare_report.get("source_stream_metadata")
    if not isinstance(source_stream, dict):
        source_stream = {}
    for key in ("duration_seconds", "frame_count", "width", "height"):
        if metadata.get(key) is None and source_stream.get(key) is not None:
            metadata[key] = source_stream.get(key)
    if strategy in {"copy_annexb_repeat_headers_no_sei", "copy_annexb_no_sei"} and source_stream.get("fps") is not None:
        metadata["fps"] = source_stream.get("fps")
    elif metadata.get("fps") is None and source_stream.get("fps") is not None:
        metadata["fps"] = source_stream.get("fps")
    preflight = prepare_report.get("preflight")
    if not isinstance(preflight, dict):
        preflight = {}
    metadata.update(
        {
            "prepare_strategy": strategy,
            "prepare_report": prepare_report,
            "source_stream_metadata": source_stream,
            "preflight_status": preflight.get("status"),
            "preflight_errors": preflight.get("errors", []),
            "nal_unit_types": preflight.get("nal_unit_types", []),
        }
    )
    return metadata


def prepare_local_board_input(local_input_path: Path, iter_dir: Path) -> Path:
    suffix = local_input_path.suffix.lower()
    if suffix in ELEMENTARY_VIDEO_EXTENSIONS:
        preflight = (
            validate_prepared_h264_bitstream(local_input_path)
            if suffix in {".h264", ".264"}
            else {"status": "skipped_non_h264_elementary", "errors": []}
        )
        report = {
            "schema_version": 1,
            "strategy": "existing_elementary",
            "source_path": str(local_input_path),
            "prepared_path": str(local_input_path),
            "source_stream_metadata": probe_video_stream_metadata(local_input_path, iter_dir, "input_source"),
            "attempts": [],
            "preflight": preflight,
        }
        write_json(iter_dir / "prepared_input_report.json", report)
        if preflight.get("status") == "blocked":
            raise SystemExit(f"prepared input failed preflight; see {iter_dir / 'prepared_input_report.json'}")
        return local_input_path
    if suffix not in CONTAINER_VIDEO_EXTENSIONS:
        return local_input_path

    prepared_dir = iter_dir / "prepared_inputs"
    ensure_directory(prepared_dir)
    ffmpeg_path = discover_ffmpeg_path()
    if not ffmpeg_path:
        raise SystemExit("ffmpeg not found; local MP4 input preparation requires ffmpeg")

    source_stream_metadata = probe_video_stream_metadata(local_input_path, iter_dir, "input_source")
    attempts: List[Dict[str, object]] = []

    def finish_attempt(strategy: str, output_path: Path, result: subprocess.CompletedProcess) -> Optional[Path]:
        preflight = validate_prepared_h264_bitstream(output_path) if _successful_output(output_path, result) else {
            "status": "blocked",
            "errors": ["prepare_command_failed"],
            "nal_unit_types": [],
        }
        attempt = {
            "strategy": strategy,
            "command_returncode": result.returncode,
            "output_path": str(output_path),
            "output_size_bytes": output_path.stat().st_size if output_path.exists() else None,
            "preflight": preflight,
        }
        attempts.append(attempt)
        if _successful_output(output_path, result) and preflight.get("status") == "ready":
            report = {
                "schema_version": 1,
                "strategy": strategy,
                "source_path": str(local_input_path),
                "prepared_path": str(output_path),
                "source_stream_metadata": source_stream_metadata,
                "attempts": attempts,
                "preflight": preflight,
            }
            write_json(iter_dir / "prepared_input_report.json", report)
            return output_path
        return None

    if source_stream_is_copy_compatible_for_board(source_stream_metadata):
        copy_output = prepared_dir / f"{local_input_path.stem}_annexb_repeat_headers_no_sei.h264"
        copy_cmd = [
            ffmpeg_path,
            "-y",
            "-i",
            str(local_input_path),
            "-an",
            "-map",
            "0:v:0",
            "-c:v",
            "copy",
            "-bsf:v",
            "h264_mp4toannexb,dump_extra=freq=keyframe,filter_units=remove_types=6",
            "-f",
            "h264",
            str(copy_output),
        ]
        copy_result = run_local(copy_cmd, check=False, capture_output=True)
        write_text(iter_dir / "input_prepare_copy_stdout.txt", copy_result.stdout)
        write_text(iter_dir / "input_prepare_copy_stderr.txt", copy_result.stderr)
        prepared = finish_attempt("copy_annexb_repeat_headers_no_sei", copy_output, copy_result)
        if prepared is not None:
            return prepared

    reencode_output = prepared_dir / f"{local_input_path.stem}_main_nob_no_sei.h264"
    reencode_cmd = [
        ffmpeg_path,
        "-y",
        "-i",
        str(local_input_path),
        "-an",
        "-c:v",
        "libx264",
        "-profile:v",
        "main",
        "-level:v",
        "4.2",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        "-bf",
        "0",
        "-x264-params",
        "bframes=0:force-cfr=1:repeat-headers=1",
        "-bsf:v",
        "filter_units=remove_types=6",
        "-f",
        "h264",
        str(reencode_output),
    ]
    reencode_result = run_local(reencode_cmd, check=False, capture_output=True)
    write_text(iter_dir / "input_prepare_reencode_stdout.txt", reencode_result.stdout)
    write_text(iter_dir / "input_prepare_reencode_stderr.txt", reencode_result.stderr)
    prepared = finish_attempt("reencode_main_nob_no_sei", reencode_output, reencode_result)
    if prepared is not None:
        return prepared

    report = {
        "schema_version": 1,
        "strategy": "failed",
        "source_path": str(local_input_path),
        "prepared_path": str(reencode_output),
        "source_stream_metadata": source_stream_metadata,
        "attempts": attempts,
        "preflight": attempts[-1]["preflight"] if attempts else {"status": "blocked", "errors": ["no_attempts"]},
    }
    write_json(iter_dir / "prepared_input_report.json", report)

    raise SystemExit(
        "failed to prepare local input for board file-mode; "
        f"{iter_dir / 'prepared_input_report.json'}"
    )


def prepare_mode(args: argparse.Namespace, remote: WindowsRemote, repo_root: Path) -> None:
    service_names = [
        "elevator_ai-session-pusher.service",
        "elevator_ai-session-server-worker.service",
    ]
    run_local(
        [
            "systemctl",
            "--user",
            "disable",
            "--now",
            *service_names,
        ],
        check=True,
        capture_output=True,
    )

    watcher_script = textwrap.dedent(
        """\
        $watcher = Get-ScheduledTask -TaskName 'ElevatorAICodexSessionWatcher' -ErrorAction SilentlyContinue
        if ($null -ne $watcher) {
            try { Stop-ScheduledTask -TaskName 'ElevatorAICodexSessionWatcher' -ErrorAction SilentlyContinue | Out-Null } catch {}
            Disable-ScheduledTask -TaskName 'ElevatorAICodexSessionWatcher' | Out-Null
        }
        $tunnel = Get-ScheduledTask -TaskName 'ElevatorAISessionPushTunnel' -ErrorAction SilentlyContinue
        $tn = Test-NetConnection -ComputerName '192.168.1.168' -Port 22 -WarningAction SilentlyContinue
        [ordered]@{
            watcher_present = ($null -ne $watcher)
            watcher_state = if ($null -ne $watcher) { (Get-ScheduledTask -TaskName 'ElevatorAICodexSessionWatcher').State.ToString() } else { 'absent' }
            tunnel_present = ($null -ne $tunnel)
            tunnel_state = if ($null -ne $tunnel) { (Get-ScheduledTask -TaskName 'ElevatorAISessionPushTunnel').State.ToString() } else { 'absent' }
            board_ssh_reachable = [bool]$tn.TcpTestSucceeded
        } | ConvertTo-Json -Compress
        """
    ).strip()
    remote_status = remote.ssh(powershell_command(watcher_script))
    stdout_lines = [line.strip() for line in remote_status.stdout.splitlines() if line.strip()]
    if not stdout_lines:
        raise SystemExit(
            "Windows prepare-mode status probe returned no JSON.\n"
            f"stdout:\n{remote_status.stdout}\n"
            f"stderr:\n{remote_status.stderr}"
        )
    status_json = json.loads(stdout_lines[-1])

    local_report = {
        "timestamp": utc_now_string(),
        "local_services_disabled": service_names,
        "remote_status": status_json,
    }
    report_path = repo_root / "logs" / "direct_runs" / "prepare_mode_report.json"
    write_json(report_path, local_report)
    print(json.dumps(local_report, ensure_ascii=False, indent=2))


def build_board_package(repo_root: Path, iter_dir: Path) -> Dict[str, str]:
    build_stdout = iter_dir / "build_stdout.txt"
    build_stderr = iter_dir / "build_stderr.txt"
    command = (
        "cd /home/ywj/elevator_ai/board && "
        "source /home/ywj/hi3516dv500_toolchain/env_setup.sh && "
        "make test-host && "
        "make clean && "
        "make package"
    )
    result = subprocess.run(
        ["bash", "-lc", command],
        capture_output=True,
        text=True,
    )
    write_text(build_stdout, result.stdout)
    write_text(build_stderr, result.stderr)
    if result.returncode != 0:
        raise SystemExit(f"board build/package failed; see {build_stdout} and {build_stderr}")

    return package_info_from_dir(repo_root / "board" / "out" / "package")


def sync_package_to_windows(remote: WindowsRemote, local_package_dir: Path, windows_package_dir: str) -> None:
    create_script = f"New-Item -ItemType Directory -Force -Path '{windows_package_dir}' | Out-Null"
    remote.ssh(powershell_command(create_script))
    files = sorted(path for path in local_package_dir.iterdir() if path.is_file())
    for file_path in files:
        remote.scp_to([file_path], f"{windows_package_dir}/{file_path.name}")


def prepare_video_iteration_assets(
    remote: WindowsRemote,
    iter_dir: Path,
    windows_iter_dir: str,
    args: argparse.Namespace,
) -> Dict[str, Optional[str]]:
    resolved_input_path = str(args.input_path)
    windows_input_local_path: Optional[str] = None
    source_video_metadata: Optional[Dict[str, object]] = None
    prepared_input_metadata: Optional[Dict[str, object]] = None
    if getattr(args, "input_local_path", None):
        local_input_path = Path(str(args.input_local_path)).expanduser().resolve()
        if not local_input_path.exists():
            raise SystemExit(f"input local path not found: {local_input_path}")
        source_video_metadata = probe_source_video_metadata(local_input_path, iter_dir)
        local_input_path = prepare_local_board_input(local_input_path, iter_dir)
        prepared_base_metadata = probe_local_media_metadata(local_input_path)
        prepare_report_path = iter_dir / "prepared_input_report.json"
        prepare_report = (
            json.loads(prepare_report_path.read_text(encoding="utf-8"))
            if prepare_report_path.exists()
            else {}
        )
        prepared_input_metadata = build_prepared_input_metadata(prepared_base_metadata, prepare_report)
        write_json(iter_dir / "prepared_input_metadata.json", prepared_input_metadata)
        windows_input_local_path = sync_file_to_windows(
            remote,
            local_input_path,
            f"{windows_iter_dir}/inputs",
        )
        if getattr(args, "board_input_path", None):
            resolved_input_path = str(args.board_input_path)
        else:
            resolved_input_path = f"/root/data/optimization_inputs/{local_input_path.name}"
    elif getattr(args, "board_input_path", None):
        resolved_input_path = str(args.board_input_path)

    if str(getattr(args, "duration_policy", "fixed")) == "source-full" and source_video_metadata is None:
        raise SystemExit("source-full duration policy requires --input-local-path so source duration can be measured")

    resolved_reference_video: Optional[str] = None
    if getattr(args, "reference_video", None):
        raw_reference = str(args.reference_video).strip()
        if looks_like_windows_path(raw_reference):
            resolved_reference_video = raw_reference
        else:
            local_reference = Path(raw_reference).expanduser().resolve()
            if not local_reference.exists():
                raise SystemExit(f"reference video not found: {local_reference}")
            resolved_reference_video = sync_file_to_windows(
                remote,
                local_reference,
                f"{windows_iter_dir}/references",
            )

    return {
        "input_path": resolved_input_path,
        "input_local_path": windows_input_local_path,
        "reference_video": resolved_reference_video,
        "source_video_metadata": source_video_metadata,
        "prepared_input_metadata": prepared_input_metadata,
    }


def write_remote_stdout(iter_dir: Path, prefix: str, result: subprocess.CompletedProcess) -> None:
    write_text(iter_dir / f"{prefix}_stdout.txt", result.stdout)
    write_text(iter_dir / f"{prefix}_stderr.txt", result.stderr)


def run_windows_python(remote: WindowsRemote, script_path: str, args: List[str]) -> subprocess.CompletedProcess:
    def ps_quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    parts = ["py", ps_quote(script_path)]
    parts.extend(ps_quote(arg) for arg in args)
    ps_script = "& " + " ".join(parts)
    return remote.ssh(powershell_command(ps_script), check=False)


def batch_gate(summary: Dict[str, object]) -> Dict[str, object]:
    classes = {item["class_name"]: item for item in summary.get("classes", [])}
    person = classes.get("person", {})
    ebike = classes.get("ebike", {})
    passed = (
        int(summary.get("failure_count", -1)) == 0
        and int(summary.get("success_count", -1)) == 50
        and float(summary.get("map50", 0.0)) >= BASELINE_BATCH["map50"]
        and float(person.get("f1", 0.0)) >= BASELINE_BATCH["person_f1"]
        and float(ebike.get("f1", 0.0)) >= BASELINE_BATCH["ebike_f1"]
    )
    return {
        "passed": passed,
        "measured": {
            "success_count": summary.get("success_count"),
            "failure_count": summary.get("failure_count"),
            "map50": summary.get("map50"),
            "person_f1": person.get("f1"),
            "ebike_f1": ebike.get("f1"),
        },
        "baseline": BASELINE_BATCH,
    }


def class_map(summary: Dict[str, object]) -> Dict[str, Dict[str, object]]:
    return {item["class_name"]: item for item in summary.get("classes", [])}


def batch_pass_streak(campaign_dir: Path) -> int:
    pattern = re.compile(r"iter_(\d+)$")
    entries: List[Path] = []
    for child in campaign_dir.iterdir():
        if child.is_dir() and pattern.match(child.name):
            entries.append(child)
    entries.sort(key=lambda path: int(pattern.match(path.name).group(1)))  # type: ignore[union-attr]

    streak = 0
    for iter_dir in entries:
        gate_path = iter_dir / "analysis" / "gate_result.json"
        if not gate_path.exists():
            streak = 0
            continue
        payload = json.loads(gate_path.read_text(encoding="utf-8"))
        if payload.get("phase") != "batch":
            streak = 0
            continue
        if payload.get("passed"):
            streak += 1
        else:
            streak = 0
    return streak


def recompute_batch_metrics(repo_root: Path, iter_dir: Path, dataset_root: str = FULL_DATASET_ROOT) -> Dict[str, object]:
    analysis_dir = iter_dir / "analysis"
    ensure_directory(analysis_dir)
    script = repo_root / "board" / "scripts" / "recompute_batch_metrics.py"
    det_chunk00 = iter_dir / "artifacts" / "chunk00" / "pulled" / "detections.jsonl"
    det_chunk25 = iter_dir / "artifacts" / "chunk25" / "pulled" / "detections.jsonl"
    if not det_chunk00.exists() or not det_chunk25.exists():
        raise SystemExit("missing detections.jsonl from pulled chunk artifacts")

    merged_summary_path = analysis_dir / "merged_summary.json"
    cmd = [
        "python3",
        str(script),
        str(det_chunk00),
        str(det_chunk25),
        "--images-dir",
        f"{dataset_root.rstrip('/')}/images/val",
        "--labels-dir",
        f"{dataset_root.rstrip('/')}/labels/val",
        "--output-dir",
        "/userdata/elevator_ai/runs/batch_val50_chunked_merged",
        "--limit",
        "50",
        "--score-threshold",
        "0.15",
        "--nms-threshold",
        "0.45",
        "--write-summary-json",
        str(merged_summary_path),
    ]
    result = run_local(cmd, capture_output=True)
    write_text(analysis_dir / "recompute_stdout.json", result.stdout)
    summary = json.loads(result.stdout)
    gate = batch_gate(summary)
    gate["phase"] = "batch"
    write_json(analysis_dir / "gate_result.json", gate)
    write_json(analysis_dir / "merged_metrics.json", summary)
    return summary


def recompute_named_batch_metrics(
    repo_root: Path,
    detections_paths: List[Path],
    *,
    analysis_dir: Path,
    stem: str,
    images_dir: str,
    labels_dir: str,
    output_dir: str,
    limit: int,
    score_threshold: float,
    nms_threshold: float,
) -> Dict[str, object]:
    if not detections_paths:
        raise SystemExit(f"missing detections.jsonl inputs for {stem}")

    script = repo_root / "board" / "scripts" / "recompute_batch_metrics.py"
    summary_path = analysis_dir / f"{stem}_summary.json"
    stdout_path = analysis_dir / f"{stem}_recompute_stdout.json"
    cmd = [
        "python3",
        str(script),
        *[str(path) for path in detections_paths],
        "--images-dir",
        images_dir,
        "--labels-dir",
        labels_dir,
        "--output-dir",
        output_dir,
        "--limit",
        str(limit),
        "--score-threshold",
        str(score_threshold),
        "--nms-threshold",
        str(nms_threshold),
        "--write-summary-json",
        str(summary_path),
    ]
    result = run_local(cmd, capture_output=True)
    write_text(stdout_path, result.stdout)
    summary = json.loads(result.stdout)
    write_json(analysis_dir / f"{stem}_metrics.json", summary)
    return summary


def write_batch_summary(iter_dir: Path, run_result: Dict[str, object], merged_summary: Dict[str, object], streak: int) -> None:
    classes = class_map(merged_summary)
    gate = json.loads((iter_dir / "analysis" / "gate_result.json").read_text(encoding="utf-8"))
    spec = json.loads((iter_dir / "board_run_spec.json").read_text(encoding="utf-8"))
    package = run_result.get("package", {})
    content = textwrap.dedent(
        f"""\
        # {iter_dir.name}

        ## Phase
        - phase: `batch`
        - created_at: `{utc_now_string()}`
        - gate_passed: `{gate["passed"]}`
        - consecutive_passes: `{streak}`

        ## Candidate
        - binary_md5: `{package.get("binary_md5", "unknown")}`
        - model_md5: `{package.get("model_md5", "unknown")}`
        - score: `{spec["runs"][0]["score"]}`
        - nms: `{spec["runs"][0]["nms"]}`
        - ebike_cleanup: `{spec["runs"][0].get("ebike_cleanup", "auto")}`

        ## Batch Result
        - success_count: `{merged_summary["success_count"]}`
        - failure_count: `{merged_summary["failure_count"]}`
        - map50: `{merged_summary["map50"]:.10f}`
        - person_f1: `{classes["person"]["f1"]:.6f}`
        - ebike_f1: `{classes["ebike"]["f1"]:.10f}`

        ## Gate Floor
        - map50_floor: `{BASELINE_BATCH["map50"]:.10f}`
        - person_f1_floor: `{BASELINE_BATCH["person_f1"]:.3f}`
        - ebike_f1_floor: `{BASELINE_BATCH["ebike_f1"]:.10f}`

        ## Next
        - dataset_phase_complete: `{"yes" if streak >= 3 and gate["passed"] else "no"}`
        - note: `continuous val50=25+25 passes are required before video tuning starts`
        """
    )
    write_text(iter_dir / "summary.md", content)


def write_full_batch_spec(
    iter_dir: Path,
    windows_iter_dir: str,
    package_info: Dict[str, str],
    args: argparse.Namespace,
    remote: WindowsRemote,
) -> Dict[str, object]:
    split_specs = parse_dataset_splits(args.dataset_split)
    chunk_size = max(1, int(args.chunk_size))
    dataset_root = args.dataset_root.rstrip("/")
    runs: List[Dict[str, object]] = []

    for split_name, split_count in split_specs:
        images_dir = f"{dataset_root}/images/{split_name}"
        labels_dir = f"{dataset_root}/labels/{split_name}"
        for offset in range(0, split_count, chunk_size):
            limit = min(chunk_size, split_count - offset)
            run_name = f"{split_name}_{offset:04d}"
            output_dir = f"/userdata/elevator_ai/runs/direct_{args.campaign_id}_{iter_dir.name}_{run_name}"
            runs.append(
                {
                    "name": run_name,
                    "mode": "batch",
                    "split": split_name,
                    "images_dir": images_dir,
                    "labels_dir": labels_dir,
                    "score": args.score,
                    "nms": args.nms,
                    "ebike_cleanup": args.ebike_cleanup,
                    "offset": offset,
                    "limit": limit,
                    "timeout_seconds": max(300, chunk_size * 8),
                    "output_dir": output_dir,
                    "pull_paths": [
                        f"{output_dir}/detections.jsonl",
                        f"{output_dir}/per_image.csv",
                        f"{output_dir}/summary.json",
                        f"{output_dir}/board_resource_samples.jsonl",
                    ],
                    "cleanup_remote_output_dir": True,
                }
            )

    spec = {
        "campaign_id": args.campaign_id,
        "iteration_id": iter_dir.name,
        "local_repo_root": remote.config.repo_root,
        "iteration_dir": windows_iter_dir,
        "dataset_root": dataset_root,
        "dataset_splits": [
            {"name": split_name, "count": split_count} for split_name, split_count in split_specs
        ],
        "chunk_size": chunk_size,
        "package": {
            "local_dir": f"{windows_iter_dir}/windows_package",
            "remote_root": "/root/elevator_ai",
            "binary_md5": package_info["binary_md5"],
            "model_md5": package_info["model_md5"],
            "executable_targets": ["elevator_yolo"],
        },
        "board": {
            "host": args.board_host,
            "user": args.board_user,
            "password": args.board_password,
            "workdir": "/root",
            "binary_path": "/root/elevator_ai/elevator_yolo",
            "model_path": "/root/elevator_ai/yolov8.om",
            "score": args.score,
            "nms": args.nms,
            "ebike_cleanup": args.ebike_cleanup,
        },
        "runs": runs,
    }
    write_json(iter_dir / "board_run_spec.json", spec)
    return spec


def summarize_full_batch(
    repo_root: Path,
    iter_dir: Path,
    run_result: Dict[str, object],
    spec: Dict[str, object],
    args: argparse.Namespace,
) -> None:
    analysis_dir = iter_dir / "analysis"
    split_specs = [(item["name"], int(item["count"])) for item in spec.get("dataset_splits", [])]
    total_images = total_dataset_images(split_specs)

    overall_paths: List[Path] = []
    split_paths: Dict[str, List[Path]] = {split_name: [] for split_name, _ in split_specs}
    for run in spec.get("runs", []):
        run_name = str(run["name"])
        det_path = iter_dir / "artifacts" / run_name / "pulled" / "detections.jsonl"
        if not det_path.exists():
            raise SystemExit(f"missing detections.jsonl for full batch run {run_name}")
        overall_paths.append(det_path)
        split_paths[str(run.get("split"))].append(det_path)

    overall_summary = recompute_named_batch_metrics(
        repo_root,
        overall_paths,
        analysis_dir=analysis_dir,
        stem="overall",
        images_dir=f"{args.dataset_root}/images",
        labels_dir=f"{args.dataset_root}/labels",
        output_dir=f"/userdata/elevator_ai/runs/direct_{args.campaign_id}_{iter_dir.name}_overall_merged",
        limit=total_images,
        score_threshold=args.score,
        nms_threshold=args.nms,
    )

    split_summaries: Dict[str, Dict[str, object]] = {}
    for split_name, split_count in split_specs:
        split_summaries[split_name] = recompute_named_batch_metrics(
            repo_root,
            split_paths[split_name],
            analysis_dir=analysis_dir,
            stem=f"split_{split_name}",
            images_dir=f"{args.dataset_root}/images/{split_name}",
            labels_dir=f"{args.dataset_root}/labels/{split_name}",
            output_dir=f"/userdata/elevator_ai/runs/direct_{args.campaign_id}_{iter_dir.name}_{split_name}_merged",
            limit=split_count,
            score_threshold=args.score,
            nms_threshold=args.nms,
        )

    overall_classes = class_map(overall_summary)
    images_per_second = (
        float(overall_summary["success_count"]) / (float(overall_summary["total_elapsed_ms"]) / 1000.0)
        if float(overall_summary.get("total_elapsed_ms", 0.0)) > 0.0
        else 0.0
    )
    performance_payload = {
        "total_images": total_images,
        "split_counts": {split_name: split_count for split_name, split_count in split_specs},
        "overall": {
            "success_count": overall_summary["success_count"],
            "failure_count": overall_summary["failure_count"],
            "fallback_count": overall_summary["fallback_count"],
            "total_elapsed_ms": overall_summary["total_elapsed_ms"],
            "average_elapsed_ms": overall_summary["average_elapsed_ms"],
            "images_per_second": images_per_second,
            "map50": overall_summary["map50"],
            "classes": overall_summary["classes"],
        },
        "wall_clock_duration_sec": run_result.get("duration_sec"),
        "splits": split_summaries,
    }
    write_json(analysis_dir / "performance_summary.json", performance_payload)

    summary_lines = [
        f"# {iter_dir.name}",
        "",
        "## Phase",
        "- phase: `batch_full`",
        f"- created_at: `{utc_now_string()}`",
        f"- total_images: `{total_images}`",
        f"- wall_clock_duration_sec: `{run_result.get('duration_sec')}`",
        "",
        "## Candidate",
        f"- binary_md5: `{run_result.get('package', {}).get('binary_md5', 'unknown')}`",
        f"- model_md5: `{run_result.get('package', {}).get('model_md5', 'unknown')}`",
        f"- score: `{args.score}`",
        f"- nms: `{args.nms}`",
        f"- ebike_cleanup: `{args.ebike_cleanup}`",
        f"- chunk_size: `{args.chunk_size}`",
        "",
        "## Overall Board OM Metrics",
        f"- success_count: `{overall_summary['success_count']}`",
        f"- failure_count: `{overall_summary['failure_count']}`",
        f"- fallback_count: `{overall_summary['fallback_count']}`",
        f"- map50: `{overall_summary['map50']:.10f}`",
        f"- total_elapsed_ms: `{float(overall_summary['total_elapsed_ms']):.3f}`",
        f"- average_elapsed_ms: `{float(overall_summary['average_elapsed_ms']):.3f}`",
        f"- images_per_second: `{images_per_second:.6f}`",
        f"- person_precision: `{float(overall_classes['person']['precision']):.10f}`",
        f"- person_recall: `{float(overall_classes['person']['recall']):.10f}`",
        f"- person_f1: `{float(overall_classes['person']['f1']):.10f}`",
        f"- person_ap50: `{float(overall_classes['person']['ap50']):.10f}`",
        f"- ebike_precision: `{float(overall_classes['ebike']['precision']):.10f}`",
        f"- ebike_recall: `{float(overall_classes['ebike']['recall']):.10f}`",
        f"- ebike_f1: `{float(overall_classes['ebike']['f1']):.10f}`",
        f"- ebike_ap50: `{float(overall_classes['ebike']['ap50']):.10f}`",
        "",
        "## Split Metrics",
    ]
    for split_name, split_count in split_specs:
        split_summary = split_summaries[split_name]
        split_classes = class_map(split_summary)
        summary_lines.extend(
            [
                f"- {split_name}_images: `{split_count}`",
                f"- {split_name}_success_count: `{split_summary['success_count']}`",
                f"- {split_name}_failure_count: `{split_summary['failure_count']}`",
                f"- {split_name}_map50: `{float(split_summary['map50']):.10f}`",
                f"- {split_name}_person_f1: `{float(split_classes['person']['f1']):.10f}`",
                f"- {split_name}_ebike_f1: `{float(split_classes['ebike']['f1']):.10f}`",
            ]
        )

    summary_lines.extend(
        [
            "",
            "## Outputs",
            "- overall_metrics: `analysis/overall_metrics.json`",
            "- overall_summary: `analysis/overall_summary.json`",
            "- performance_summary: `analysis/performance_summary.json`",
        ]
    )
    for split_name, _ in split_specs:
        summary_lines.extend(
            [
                f"- split_{split_name}_metrics: `analysis/split_{split_name}_metrics.json`",
                f"- split_{split_name}_summary: `analysis/split_{split_name}_summary.json`",
            ]
        )
    write_text(iter_dir / "summary.md", "\n".join(summary_lines) + "\n")


def init_iteration(repo_root: Path, campaign_id: str) -> Path:
    campaign_dir = repo_root / "logs" / "direct_runs" / campaign_id
    ensure_directory(campaign_dir)
    iter_id = next_iteration_id(campaign_dir)
    iter_dir = campaign_dir / iter_id
    ensure_directory(iter_dir)
    ensure_directory(iter_dir / "artifacts")
    ensure_directory(iter_dir / "analysis")
    return iter_dir


def copy_remote_result_tree(remote: WindowsRemote, windows_iter_dir: str, iter_dir: Path) -> None:
    run_result_remote = f"{windows_iter_dir}/run_result.json"
    remote.scp_from(run_result_remote, iter_dir / "run_result.json", recursive=False)

    artifacts_dir = iter_dir / "artifacts"
    if artifacts_dir.exists():
        # Keep local analysis/spec files and replace pulled runtime artifacts.
        for child in list(artifacts_dir.iterdir()):
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    remote.scp_from(f"{windows_iter_dir}/artifacts", iter_dir, recursive=True)

    remote_analysis_dir = f"{windows_iter_dir}/analysis"
    result = remote.ssh(
        powershell_command(
            f"if (Test-Path -LiteralPath '{remote_analysis_dir}') {{ Write-Output 'present' }}"
        ),
        check=False,
    )
    if "present" in result.stdout:
        local_analysis_dir = iter_dir / "analysis"
        if local_analysis_dir.exists():
            for child in list(local_analysis_dir.iterdir()):
                if child.name in {"gate_result.json", "merged_metrics.json", "merged_summary.json", "recompute_stdout.json"}:
                    continue
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        remote.scp_from(remote_analysis_dir, iter_dir, recursive=True)


def write_batch_spec(
    iter_dir: Path,
    windows_iter_dir: str,
    package_info: Dict[str, str],
    args: argparse.Namespace,
    remote: WindowsRemote,
) -> Dict[str, object]:
    dataset_root = getattr(args, "dataset_root", FULL_DATASET_ROOT).rstrip("/")
    spec = {
        "campaign_id": args.campaign_id,
        "iteration_id": iter_dir.name,
        "local_repo_root": remote.config.repo_root,
        "iteration_dir": windows_iter_dir,
        "package": {
            "local_dir": f"{windows_iter_dir}/windows_package",
            "remote_root": "/root/elevator_ai",
            "binary_md5": package_info["binary_md5"],
            "model_md5": package_info["model_md5"],
            "executable_targets": ["elevator_yolo"],
        },
        "board": {
            "host": args.board_host,
            "user": args.board_user,
            "password": args.board_password,
            "workdir": "/root",
            "binary_path": "/root/elevator_ai/elevator_yolo",
            "model_path": "/root/elevator_ai/yolov8.om",
            "score": args.score,
            "nms": args.nms,
            "ebike_cleanup": args.ebike_cleanup,
        },
        "runs": [
            {
                "name": "chunk00",
                "mode": "batch",
                "images_dir": f"{dataset_root}/images/val",
                "labels_dir": f"{dataset_root}/labels/val",
                "score": args.score,
                "nms": args.nms,
                "ebike_cleanup": args.ebike_cleanup,
                "offset": 0,
                "limit": 25,
                "output_dir": f"/userdata/elevator_ai/runs/direct_{args.campaign_id}_{iter_dir.name}_chunk00",
                "pull_paths": [
                    f"/userdata/elevator_ai/runs/direct_{args.campaign_id}_{iter_dir.name}_chunk00/detections.jsonl",
                    f"/userdata/elevator_ai/runs/direct_{args.campaign_id}_{iter_dir.name}_chunk00/per_image.csv",
                    f"/userdata/elevator_ai/runs/direct_{args.campaign_id}_{iter_dir.name}_chunk00/summary.json",
                    f"/userdata/elevator_ai/runs/direct_{args.campaign_id}_{iter_dir.name}_chunk00/board_resource_samples.jsonl",
                ],
            },
            {
                "name": "chunk25",
                "mode": "batch",
                "images_dir": f"{dataset_root}/images/val",
                "labels_dir": f"{dataset_root}/labels/val",
                "score": args.score,
                "nms": args.nms,
                "ebike_cleanup": args.ebike_cleanup,
                "offset": 25,
                "limit": 25,
                "output_dir": f"/userdata/elevator_ai/runs/direct_{args.campaign_id}_{iter_dir.name}_chunk25",
                "pull_paths": [
                    f"/userdata/elevator_ai/runs/direct_{args.campaign_id}_{iter_dir.name}_chunk25/detections.jsonl",
                    f"/userdata/elevator_ai/runs/direct_{args.campaign_id}_{iter_dir.name}_chunk25/per_image.csv",
                    f"/userdata/elevator_ai/runs/direct_{args.campaign_id}_{iter_dir.name}_chunk25/summary.json",
                    f"/userdata/elevator_ai/runs/direct_{args.campaign_id}_{iter_dir.name}_chunk25/board_resource_samples.jsonl",
                ],
            },
        ],
    }
    write_json(iter_dir / "board_run_spec.json", spec)
    return spec


def write_video_spec(
    iter_dir: Path,
    windows_iter_dir: str,
    package_info: Dict[str, str],
    args: argparse.Namespace,
    remote: WindowsRemote,
    *,
    windows_package_dir: Optional[str] = None,
    resolved_input_path: Optional[str] = None,
    windows_input_local_path: Optional[str] = None,
    resolved_reference_video: Optional[str] = None,
    source_video_metadata: Optional[Dict[str, object]] = None,
    prepared_input_metadata: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    metrics_output_dir = f"/root/direct_video_metrics_{args.campaign_id}_{iter_dir.name}"
    package_local_dir = windows_package_dir or f"{windows_iter_dir}/windows_package"
    effective_input_path = resolved_input_path or str(args.input_path)
    duration_policy = str(getattr(args, "duration_policy", "fixed") or "fixed")
    if duration_policy == "source-full":
        effective_duration_seconds = source_full_watchdog_seconds(source_video_metadata or {}, prepared_input_metadata)
    else:
        effective_duration_seconds = resolve_video_duration_seconds(args, source_video_metadata)
    spec = {
        "campaign_id": args.campaign_id,
        "iteration_id": iter_dir.name,
        "local_repo_root": remote.config.repo_root,
        "iteration_dir": windows_iter_dir,
        "package": {
            "local_dir": package_local_dir,
            "remote_root": "/root/elevator_ai",
            "binary_md5": package_info["binary_md5"],
            "model_md5": package_info["model_md5"],
            "executable_targets": ["elevator_yolo"],
        },
        "board": {
            "host": args.board_host,
            "user": args.board_user,
            "password": args.board_password,
            "workdir": "/root",
            "binary_path": "/root/elevator_ai/elevator_yolo",
            "model_path": "/root/elevator_ai/yolov8.om",
            "score": args.score,
            "nms": args.nms,
            "smooth_window": args.smooth_window,
            "ebike_cleanup": args.ebike_cleanup,
            "rtsp_port": getattr(args, "rtsp_port", None),
        },
        "runs": [
            {
                "name": "main",
                "mode": "file",
                "input_path": effective_input_path,
                "output_path": "/root/stream_chn0.h264",
                "output_dir": metrics_output_dir,
                "osd_enable": False,
                "score": args.score,
                "nms": args.nms,
                "smooth_window": args.smooth_window,
                "ebike_cleanup": args.ebike_cleanup,
                "duration_seconds": effective_duration_seconds,
                "duration_policy": duration_policy,
                "watchdog_timeout_seconds": effective_duration_seconds if duration_policy == "source-full" else None,
                "pull_paths": [
                    "/root/stream_chn0.h264",
                    metrics_output_dir,
                ],
                "cleanup_remote_output_dir": True,
            }
        ],
        "analysis": {
            "expected_person_count": args.expected_person_count,
            "label": getattr(args, "video_label", None),
            "reference_video": resolved_reference_video,
            "reference_label": getattr(args, "reference_label", None),
            "duration_policy": duration_policy,
            "source_video_metadata": source_video_metadata,
            "prepared_input_metadata": prepared_input_metadata,
        },
    }
    if windows_input_local_path:
        run_spec = spec["runs"][0]
        assert isinstance(run_spec, dict)
        run_spec["input_local_path"] = windows_input_local_path
        run_spec["input_remote_path"] = effective_input_path
    write_json(iter_dir / "board_run_spec.json", spec)
    return spec


def fetch_run_result(iter_dir: Path) -> Dict[str, object]:
    result_path = iter_dir / "run_result.json"
    if not result_path.exists():
        raise SystemExit(f"missing run_result.json in {iter_dir}")
    return json.loads(result_path.read_text(encoding="utf-8"))


def transcode_video_to_h264(input_path: Path, output_path: Path) -> Dict[str, object]:
    result: Dict[str, object] = {
        "status": "missing_input",
        "ffmpeg_path": None,
        "source_video": str(input_path),
        "output_video": str(output_path),
        "error": None,
    }
    if not input_path.exists():
        return result
    ffmpeg_path = discover_ffmpeg_path()
    result["ffmpeg_path"] = ffmpeg_path
    if not ffmpeg_path:
        result["status"] = "ffmpeg_missing"
        result["error"] = "ffmpeg not found"
        return result
    ensure_directory(output_path.parent)
    command = [
        ffmpeg_path,
        "-y",
        "-fflags",
        "+genpts",
        "-i",
        str(input_path),
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    completed = run_local(command, check=False, capture_output=True)
    result["stdout"] = completed.stdout[-1000:] if completed.stdout else ""
    result["stderr"] = completed.stderr[-1000:] if completed.stderr else ""
    if completed.returncode != 0 or not output_path.exists() or output_path.stat().st_size <= 0:
        result["status"] = "transcode_failed"
        result["error"] = completed.stderr[-1000:] if completed.stderr else f"ffmpeg exited with code {completed.returncode}"
        return result
    result["status"] = "ready"
    return result


def write_runtime_fidelity_summary(iter_dir: Path, spec: Dict[str, object]) -> Dict[str, object]:
    analysis_dir = iter_dir / "analysis"
    analysis_spec = spec.get("analysis", {}) if isinstance(spec.get("analysis"), dict) else {}
    run_spec = (spec.get("runs") or [{}])[0] if isinstance(spec.get("runs"), list) else {}
    source_video = analysis_spec.get("source_video_metadata")
    prepared_input = analysis_spec.get("prepared_input_metadata")
    if not isinstance(source_video, dict):
        source_video = None
    if not isinstance(prepared_input, dict):
        prepared_input = None

    raw_output = probe_local_media_metadata(iter_dir / "artifacts" / "main" / "stream_chn0.h264")

    public_review_path = analysis_dir / "preview_public_h264.mp4"
    if not public_review_path.exists():
        public_review_path = analysis_dir / "preview_public.mp4"
    debug_review_path = analysis_dir / "preview_debug_h264.mp4"
    if not debug_review_path.exists():
        debug_review_path = analysis_dir / "preview_debug.mp4"
    raw_review_path = analysis_dir / "raw_output_review_h264.mp4"
    if not raw_review_path.exists():
        raw_review_path = analysis_dir / "raw_output_review.mp4"

    public_review = probe_local_media_metadata(public_review_path)
    debug_review = probe_local_media_metadata(debug_review_path)
    raw_review = probe_local_media_metadata(raw_review_path)

    expected = prepared_input or source_video
    expected_duration = (
        float(expected.get("duration_seconds"))
        if isinstance(expected, dict) and expected.get("duration_seconds") is not None
        else None
    )
    expected_frames = (
        int(expected.get("frame_count"))
        if isinstance(expected, dict) and expected.get("frame_count") is not None
        else None
    )
    actual_duration = float(raw_output.get("duration_seconds")) if raw_output.get("duration_seconds") is not None else None
    if actual_duration is None and raw_review.get("duration_seconds") is not None:
        actual_duration = float(raw_review.get("duration_seconds"))

    actual_frames = int(raw_output.get("frame_count")) if raw_output.get("frame_count") is not None else None
    if actual_frames is None and raw_review.get("frame_count") is not None:
        actual_frames = int(raw_review.get("frame_count"))

    duration_ratio = _fidelity_shortfall(expected_duration, actual_duration)
    frame_ratio = (
        _fidelity_shortfall(float(expected_frames), float(actual_frames))
        if expected_frames is not None and actual_frames is not None
        else None
    )

    status = "ready"
    blocked_reason = None
    if str(run_spec.get("duration_policy") or "fixed") == "source-full":
        if expected is None or raw_output.get("status") != "ready":
            status = "missing_fidelity_inputs"
            blocked_reason = "missing_expected_or_raw_output"
        elif (duration_ratio is not None and duration_ratio < 0.9) or (frame_ratio is not None and frame_ratio < 0.9):
            status = "blocked_duration_mismatch"
            blocked_reason = "raw_output_shorter_than_source_full_expectation"

    summary = {
        "schema_version": 1,
        "status": status,
        "blocked_reason": blocked_reason,
        "duration_policy": run_spec.get("duration_policy"),
        "source_video": source_video,
        "prepared_input": prepared_input,
        "raw_output": raw_output,
        "raw_review": raw_review,
        "public_review": public_review,
        "debug_review": debug_review,
        "checks": {
            "expected_duration_seconds": expected_duration,
            "expected_frame_count": expected_frames,
            "raw_duration_ratio": duration_ratio,
            "raw_frame_ratio": frame_ratio,
        },
    }
    write_json(analysis_dir / "runtime_fidelity_summary.json", summary)
    return summary


def load_runtime_fidelity_summary(iter_dir: Path) -> Optional[Dict[str, object]]:
    path = iter_dir / "analysis" / "runtime_fidelity_summary.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def ensure_server_review_artifacts(iter_dir: Path) -> None:
    analysis_dir = iter_dir / "analysis"
    review_pack_path = analysis_dir / "review_pack.json"
    if not analysis_dir.exists():
        return

    transcode_summary: Dict[str, object] = {}
    clean_h264 = analysis_dir / "preview_clean_h264.mp4"
    public_h264 = analysis_dir / "preview_public_h264.mp4"
    debug_h264 = analysis_dir / "preview_debug_h264.mp4"
    raw_review_h264 = analysis_dir / "raw_output_review_h264.mp4"

    if not clean_h264.exists():
        clean_source = analysis_dir / "preview_clean.mp4"
        if clean_source.exists():
            transcode_summary["clean_review_h264_server"] = transcode_video_to_h264(
                clean_source,
                clean_h264,
            )
    if not public_h264.exists():
        public_source = analysis_dir / "preview_public.mp4"
        if public_source.exists():
            transcode_summary["public_review_h264_server"] = transcode_video_to_h264(
                public_source,
                public_h264,
            )
    if not debug_h264.exists():
        transcode_summary["debug_preview_h264_server"] = transcode_video_to_h264(
            analysis_dir / "preview_debug.mp4",
            debug_h264,
        )
    if not raw_review_h264.exists():
        raw_source = analysis_dir / "raw_output_review.mp4"
        if raw_source.exists():
            transcode_summary["raw_output_review_h264_server"] = transcode_video_to_h264(
                raw_source,
                raw_review_h264,
            )
        else:
            transcode_summary["raw_output_review_h264_server"] = transcode_video_to_h264(
                iter_dir / "artifacts" / "main" / "stream_chn0.h264",
                raw_review_h264,
            )

    legacy_stream_review = analysis_dir / "stream_chn0_review.mp4"
    if raw_review_h264.exists() and not legacy_stream_review.exists():
        shutil.copyfile(raw_review_h264, legacy_stream_review)

    if not review_pack_path.exists():
        if transcode_summary:
            write_json(analysis_dir / "server_transcode_summary.json", transcode_summary)
        return

    review_pack = json.loads(review_pack_path.read_text(encoding="utf-8"))
    secondary = dict(review_pack.get("secondary_review_artifacts", {}) or {})
    clean = dict(review_pack.get("clean", {}) or {})
    public = dict(review_pack.get("public", {}) or {})
    debug = dict(review_pack.get("debug", {}) or {})
    raw = dict(review_pack.get("raw", {}) or {})
    preview_transcode = dict(review_pack.get("preview_transcode", {}) or {})

    if clean_h264.exists():
        review_pack["primary_review_artifact"] = str(clean_h264)
        secondary["clean_review_video_h264"] = str(clean_h264)
        clean["preview_video_h264"] = str(clean_h264)
    if public_h264.exists():
        secondary["public_review_video_h264"] = str(public_h264)
        public["preview_video_h264"] = str(public_h264)
    if debug_h264.exists():
        secondary["debug_review_video_h264"] = str(debug_h264)
        debug["preview_video_h264"] = str(debug_h264)
    if raw_review_h264.exists():
        secondary["raw_output_review_h264"] = str(raw_review_h264)
        raw["review_video_h264"] = str(raw_review_h264)
    if transcode_summary:
        preview_transcode.update(transcode_summary)

    review_pack["secondary_review_artifacts"] = secondary
    review_pack["clean"] = clean
    review_pack["public"] = public
    review_pack["debug"] = debug
    review_pack["raw"] = raw
    review_pack["preview_transcode"] = preview_transcode
    write_json(review_pack_path, review_pack)
    if transcode_summary:
        write_json(analysis_dir / "server_transcode_summary.json", transcode_summary)


def update_campaign_index(iter_dir: Path, spec: Dict[str, object], run_result: Dict[str, object]) -> None:
    campaign_dir = iter_dir.parent
    run_spec = (spec.get("runs") or [{}])[0] if isinstance(spec.get("runs"), list) else {}
    analysis_spec = spec.get("analysis", {}) if isinstance(spec.get("analysis"), dict) else {}
    review_pack_path = iter_dir / "analysis" / "review_pack.json"
    primary_review_artifact = None
    if review_pack_path.exists():
        try:
            review_pack = json.loads(review_pack_path.read_text(encoding="utf-8"))
            primary_review_artifact = review_pack.get("primary_review_artifact")
        except Exception:
            primary_review_artifact = None

    source_video_metadata = analysis_spec.get("source_video_metadata")
    if not isinstance(source_video_metadata, dict):
        source_video_metadata = None
    runtime_fidelity = load_runtime_fidelity_summary(iter_dir)

    entry = {
        "iteration_id": iter_dir.name,
        "phase": "video" if run_spec.get("mode") == "file" else str(run_spec.get("mode") or "batch"),
        "video_label": analysis_spec.get("label"),
        "input_path": run_spec.get("input_path"),
        "duration_policy": run_spec.get("duration_policy"),
        "duration_seconds": run_spec.get("duration_seconds"),
        "source_duration_seconds": source_video_metadata.get("duration_seconds") if source_video_metadata else None,
        "source_video_metadata": source_video_metadata,
        "primary_review_artifact": primary_review_artifact,
        "runtime_fidelity": runtime_fidelity,
        "status": run_result.get("status"),
        "summary_path": str(iter_dir / "summary.md") if (iter_dir / "summary.md").exists() else None,
    }

    index_path = campaign_dir / "campaign_index.json"
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        index = {
            "schema_version": 1,
            "campaign_id": campaign_dir.name,
            "updated_at": None,
            "iterations": [],
        }
    existing = [item for item in index.get("iterations", []) if item.get("iteration_id") != iter_dir.name]
    existing.append(entry)
    existing.sort(key=lambda item: int(str(item.get("iteration_id", "iter_0")).split("_")[-1]))
    index["updated_at"] = utc_now_string()
    index["iterations"] = existing
    write_json(index_path, index)

    lines = [
        f"# {campaign_dir.name}",
        "",
        "| Iteration | Label | Mode | Duration | Fidelity | Primary Artifact | Status |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in existing:
        label = item.get("video_label") or "-"
        mode = item.get("duration_policy") or item.get("phase") or "-"
        duration = item.get("duration_seconds") or "-"
        fidelity = (item.get("runtime_fidelity") or {}).get("status", "-")
        artifact = item.get("primary_review_artifact") or item.get("summary_path") or "-"
        status = item.get("status") or "-"
        lines.append(
            f"| {item.get('iteration_id')} - {label} | {label} | {mode} | {duration} | {fidelity} | `{artifact}` | {status} |"
        )
    write_text(campaign_dir / "INDEX.md", "\n".join(lines) + "\n")


def write_video_summary(iter_dir: Path, run_result: Dict[str, object]) -> None:
    analysis_summary = iter_dir / "analysis" / "summary.json"
    review_path = iter_dir / "analysis" / "visual_review.json"
    if review_path.exists():
        review_payload = json.loads(review_path.read_text(encoding="utf-8"))
        review_state = str(review_payload.get("status", "pending"))
    else:
        review_state = "analysis_ready" if analysis_summary.exists() else "analysis_missing"
    spec = json.loads((iter_dir / "board_run_spec.json").read_text(encoding="utf-8"))
    analysis_spec = spec.get("analysis", {})
    video_label = analysis_spec.get("label") or iter_dir.name
    source_metadata = analysis_spec.get("source_video_metadata") or {}
    prepared_metadata = analysis_spec.get("prepared_input_metadata") or {}
    fidelity_summary = load_runtime_fidelity_summary(iter_dir) or {}
    source_duration = source_metadata.get("duration_seconds", "unknown")
    prepared_strategy = prepared_metadata.get("prepare_strategy", "unknown") if isinstance(prepared_metadata, dict) else "unknown"
    prepared_preflight = prepared_metadata.get("preflight_status", "unknown") if isinstance(prepared_metadata, dict) else "unknown"
    duration_policy = analysis_spec.get("duration_policy") or spec["runs"][0].get("duration_policy", "fixed")
    review_pack_path = iter_dir / "analysis" / "review_pack.json"
    primary_artifact = "analysis/preview_clean.mp4"
    if review_pack_path.exists():
        try:
            review_pack = json.loads(review_pack_path.read_text(encoding="utf-8"))
            primary_artifact = str(review_pack.get("primary_review_artifact") or primary_artifact)
        except Exception:
            primary_artifact = "analysis/preview_clean.mp4"
    package = run_result.get("package", {})
    candidate_video = "artifacts/main/stream_chn0.h264"
    reference_note = (
        "Watch `analysis/preview_clean_h264.mp4` end-to-end first. "
        "Then watch `analysis/preview_public_h264.mp4`, and only use storyboard_pages / issue_windows / "
        "contact_sheet as navigation evidence before checking debug/raw."
    )
    if spec.get("analysis", {}).get("reference_video"):
        reference_note += " Use `analysis/comparison_contact_sheet.jpg` only for side-by-side navigation."
    content = textwrap.dedent(
        f"""\
        # {iter_dir.name} - {video_label}

        ## Phase
        - phase: `video`
        - created_at: `{utc_now_string()}`
        - review_state: `{review_state}`
        - video_label: `{video_label}`

        ## Candidate
        - binary_md5: `{package.get("binary_md5", "unknown")}`
        - model_md5: `{package.get("model_md5", "unknown")}`
        - score: `{spec["runs"][0]["score"]}`
        - nms: `{spec["runs"][0]["nms"]}`
        - smooth_window: `{spec["runs"][0]["smooth_window"]}`
        - ebike_cleanup: `{spec["runs"][0].get("ebike_cleanup", "auto")}`
        - duration_seconds: `{spec["runs"][0]["duration_seconds"]}`
        - duration_policy: `{duration_policy}`
        - source_duration_seconds: `{source_duration}`
        - prepared_strategy: `{prepared_strategy}`
        - prepared_preflight_status: `{prepared_preflight}`
        - fidelity_status: `{fidelity_summary.get("status", "missing")}`

        ## Artifact
        - output_video: `{candidate_video}`
        - primary_playable_artifact: `{primary_artifact}`
        - note: `{reference_note}`
        - prepared_input_metadata: `prepared_input_metadata.json`
        - prepared_input_report: `prepared_input_report.json`
        - review_pack: `analysis/review_pack.json`
        - runtime_fidelity_summary: `analysis/runtime_fidelity_summary.json`
        - raw_output_review: `analysis/raw_output_review.mp4`
        - raw_output_review_h264: `analysis/raw_output_review_h264.mp4`
        - preview_clean: `analysis/preview_clean.mp4`
        - preview_clean_h264: `analysis/preview_clean_h264.mp4`
        - preview_public: `analysis/preview_public.mp4`
        - preview_public_h264: `analysis/preview_public_h264.mp4`
        - preview_debug: `analysis/preview_debug.mp4`
        - preview_debug_h264: `analysis/preview_debug_h264.mp4`
        - occupancy_reference: `analysis/occupancy_reference.json`
        - count_accuracy_summary: `analysis/count_accuracy_summary.json`
        - board_resource_summary: `analysis/board_resource_summary.json`
        - review_method_validation: `analysis/review_method_validation.json`

        ## Next
        - note: `The main agent must update analysis/visual_review.json before this iteration is considered final.`
        """
    )
    write_text(iter_dir / "summary.md", content)


def write_review_method_validation_stub(iter_dir: Path) -> Path:
    analysis_dir = iter_dir / "analysis"
    summary_path = analysis_dir / "summary.json"
    validation_path = analysis_dir / "review_method_validation.json"
    if validation_path.exists() or not summary_path.exists():
        return validation_path

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    review_artifacts = summary.get("review_artifacts") if isinstance(summary.get("review_artifacts"), dict) else {}
    payload = {
        "schema_version": 1,
        "status": "pending",
        "policy": "still_navigation_only",
        "iteration_id": iter_dir.name,
        "video_label": summary.get("video", {}).get("label") if isinstance(summary.get("video"), dict) else iter_dir.name,
        "still_review": {
            "status": "pending",
            "artifacts_reviewed": [],
            "suspected_findings": [],
        },
        "full_video_review": {
            "status": "pending",
            "clean_watched": False,
            "public_watched": False,
            "diagnostic_surfaces_reviewed": {
                "debug": False,
                "raw": False,
            },
            "final_findings": [],
        },
        "comparison": {
            "missed_blockers": [],
            "missed_caveats": [],
            "extra_still_false_alarms": [],
            "sampling_improvements": [],
        },
        "inputs": {
            "preview_clean_h264_mp4": (review_artifacts.get("clean") or {}).get("preview_video_h264"),
            "preview_public_h264_mp4": (review_artifacts.get("public") or {}).get("preview_video_h264"),
            "preview_debug_h264_mp4": (review_artifacts.get("debug") or {}).get("preview_video_h264"),
            "raw_output_review_h264_mp4": (review_artifacts.get("raw") or {}).get("review_video_h264"),
            "clean_storyboard_pages": (review_artifacts.get("clean") or {}).get("storyboard_pages"),
            "public_storyboard_pages": (review_artifacts.get("public") or {}).get("storyboard_pages"),
            "debug_storyboard_pages": (review_artifacts.get("debug") or {}).get("storyboard_pages"),
            "clean_issue_windows": (review_artifacts.get("clean") or {}).get("issue_windows"),
            "public_issue_windows": (review_artifacts.get("public") or {}).get("issue_windows"),
            "debug_issue_windows": (review_artifacts.get("debug") or {}).get("issue_windows"),
        },
    }
    write_json(validation_path, payload)
    return validation_path


def write_visual_review_stub(iter_dir: Path) -> None:
    analysis_dir = iter_dir / "analysis"
    summary_path = analysis_dir / "summary.json"
    if not summary_path.exists():
        return

    spec = json.loads((iter_dir / "board_run_spec.json").read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    review_pack_path = analysis_dir / "review_pack.json"
    review_pack = json.loads(review_pack_path.read_text(encoding="utf-8")) if review_pack_path.exists() else {}
    runtime_fidelity_path = analysis_dir / "runtime_fidelity_summary.json"
    run_spec = spec.get("runs", [{}])[0]
    analysis_spec = spec.get("analysis", {})
    review_path = analysis_dir / "visual_review.json"
    review_method_validation_path = write_review_method_validation_stub(iter_dir)
    if review_path.exists():
        return

    payload = {
        "review_schema_version": VISUAL_REVIEW_SCHEMA_VERSION,
        "status": "pending",
        "reviewer": "main_agent",
        "review_execution_mode": "main_agent_serial",
        "iteration_id": iter_dir.name,
        "video_label": analysis_spec.get("label") or summary.get("video", {}).get("label") or iter_dir.name,
        "acceptance_metadata": build_review_acceptance_metadata(
            analysis_spec.get("label") or summary.get("video", {}).get("label") or iter_dir.name
        ),
        "candidate": {
            "score": run_spec.get("score"),
            "nms": run_spec.get("nms"),
            "smooth_window": run_spec.get("smooth_window"),
            "ebike_cleanup": run_spec.get("ebike_cleanup"),
        },
        "review_method": {
            "protocol": "video_primary_with_still_navigation",
            "full_video_watched": {
                "clean": False,
                "public": False,
            },
            "diagnostic_video_reviewed": {
                "debug": False,
                "raw": False,
            },
            "still_artifacts_used": [],
            "still_only_verdict": False,
        },
        "inputs": {
            "contact_sheet": summary.get("contact_sheet"),
            "debug_contact_sheet": summary.get("debug_contact_sheet"),
            "worst_frames_contact_sheet": summary.get("worst_frames", {}).get("contact_sheet"),
            "debug_worst_frames_contact_sheet": summary.get("debug_worst_frames", {}).get("contact_sheet"),
            "comparison_contact_sheet": summary.get("comparison_contact_sheet"),
            "summary_json": str(summary_path),
            "occupancy_reference_json": summary.get("occupancy_reference"),
            "count_accuracy_summary_json": summary.get("count_accuracy_summary"),
            "board_resource_summary_json": summary.get("board_resource_summary"),
            "review_pack_json": summary.get("review_pack"),
            "primary_review_artifact": review_pack.get("primary_review_artifact"),
            "preview_clean_mp4": summary.get("review_artifacts", {}).get("clean", {}).get("preview_video"),
            "preview_clean_h264_mp4": review_pack.get("clean", {}).get("preview_video_h264"),
            "preview_public_mp4": summary.get("review_artifacts", {}).get("public", {}).get("preview_video"),
            "preview_public_h264_mp4": review_pack.get("public", {}).get("preview_video_h264"),
            "preview_debug_mp4": summary.get("review_artifacts", {}).get("debug", {}).get("preview_video"),
            "preview_debug_h264_mp4": review_pack.get("debug", {}).get("preview_video_h264"),
            "raw_output_review_mp4": summary.get("review_artifacts", {}).get("raw", {}).get("review_video"),
            "raw_output_review_h264_mp4": review_pack.get("raw", {}).get("review_video_h264")
            or review_pack.get("secondary_review_artifacts", {}).get("raw_output_review_h264"),
            "runtime_fidelity_summary_json": str(runtime_fidelity_path) if runtime_fidelity_path.exists() else None,
            "event_timeline_json": summary.get("review_artifacts", {}).get("event_timeline_json"),
            "issue_index_jsonl": summary.get("review_artifacts", {}).get("issue_index_jsonl"),
            "review_method_validation_json": str(review_method_validation_path),
            "clean_storyboard_pages": summary.get("review_artifacts", {}).get("clean", {}).get("storyboard_pages"),
            "public_storyboard_pages": summary.get("review_artifacts", {}).get("public", {}).get("storyboard_pages"),
            "debug_storyboard_pages": summary.get("review_artifacts", {}).get("debug", {}).get("storyboard_pages"),
            "clean_issue_windows": summary.get("review_artifacts", {}).get("clean", {}).get("issue_windows"),
            "public_issue_windows": summary.get("review_artifacts", {}).get("public", {}).get("issue_windows"),
            "debug_issue_windows": summary.get("review_artifacts", {}).get("debug", {}).get("issue_windows"),
        },
        "misses": [],
        "false_positives": [],
        "duplicates": [],
        "box_precision": [],
        "small_target_stability": [],
        "special_pose_vehicle": [],
        "counting": [],
        "surface_verdicts": {
            key: {
                "status": "pending",
                "summary": "",
                "evidence_paths": [],
            }
            for key in VISUAL_REVIEW_SURFACE_KEYS
        },
        "sections": {
            key: {
                "status": "pending",
                "summary": "",
                "evidence_paths": [],
            }
            for key in VISUAL_REVIEW_SECTION_KEYS
        },
        "findings": [],
        "dominant_issue": None,
        "overall_score": None,
        "blocking_issues": [],
        "recommendation": "pending",
    }
    write_json(review_path, payload)


def run_batch(args: argparse.Namespace, remote: WindowsRemote, repo_root: Path) -> None:
    iter_dir = init_iteration(repo_root, args.campaign_id)
    campaign_dir = iter_dir.parent
    ensure_campaign_manifest(campaign_dir, args.campaign_id, remote.config, repo_root)

    sync_windows_support_files(remote, repo_root)
    create_windows_iter_layout(remote, f"{remote.config.repo_root}/logs/direct_runs/{args.campaign_id}/{iter_dir.name}")

    package_info = resolve_package_dir(repo_root, iter_dir, args)
    local_package_dir = Path(package_info["package_dir"])
    windows_iter_dir = f"{remote.config.repo_root}/logs/direct_runs/{args.campaign_id}/{iter_dir.name}"
    sync_package_to_windows(remote, local_package_dir, f"{windows_iter_dir}/windows_package")

    write_batch_spec(iter_dir, windows_iter_dir, package_info, args, remote)
    remote.scp_to([iter_dir / "board_run_spec.json"], f"{windows_iter_dir}/board_run_spec.json")

    result = run_windows_python(
        remote,
        f"{remote.config.repo_root}/tools/windows/Run-DirectBoardIteration.py",
        ["--spec", f"{windows_iter_dir}/board_run_spec.json"],
    )
    write_remote_stdout(iter_dir, "windows_runner", result)
    if result.returncode != 0:
        try:
            copy_remote_result_tree(remote, windows_iter_dir, iter_dir)
        except Exception:
            pass
        raise SystemExit(f"Windows batch runner failed; see {iter_dir / 'windows_runner_stdout.txt'}")

    copy_remote_result_tree(remote, windows_iter_dir, iter_dir)
    run_result = fetch_run_result(iter_dir)
    merged_summary = recompute_batch_metrics(repo_root, iter_dir, args.dataset_root)
    streak = batch_pass_streak(campaign_dir)
    write_batch_summary(iter_dir, run_result, merged_summary, streak)
    update_campaign_index(
        iter_dir,
        json.loads((iter_dir / "board_run_spec.json").read_text(encoding="utf-8")),
        run_result,
    )
    print(f"batch iteration complete: {iter_dir}")


def run_video(args: argparse.Namespace, remote: WindowsRemote, repo_root: Path) -> None:
    iter_dir = init_iteration(repo_root, args.campaign_id)
    campaign_dir = iter_dir.parent
    ensure_campaign_manifest(campaign_dir, args.campaign_id, remote.config, repo_root)

    sync_windows_support_files(remote, repo_root)
    create_windows_iter_layout(remote, f"{remote.config.repo_root}/logs/direct_runs/{args.campaign_id}/{iter_dir.name}")

    package_info = resolve_package_dir(repo_root, iter_dir, args)
    local_package_dir = Path(package_info["package_dir"])
    windows_iter_dir = f"{remote.config.repo_root}/logs/direct_runs/{args.campaign_id}/{iter_dir.name}"
    sync_package_to_windows(remote, local_package_dir, f"{windows_iter_dir}/windows_package")

    staged_assets = prepare_video_iteration_assets(remote, iter_dir, windows_iter_dir, args)
    spec = write_video_spec(
        iter_dir,
        windows_iter_dir,
        package_info,
        args,
        remote,
        resolved_input_path=staged_assets["input_path"],
        windows_input_local_path=staged_assets["input_local_path"],
        resolved_reference_video=staged_assets["reference_video"],
        source_video_metadata=staged_assets["source_video_metadata"],
        prepared_input_metadata=staged_assets["prepared_input_metadata"],
    )
    remote.scp_to([iter_dir / "board_run_spec.json"], f"{windows_iter_dir}/board_run_spec.json")

    result = run_windows_python(
        remote,
        f"{remote.config.repo_root}/tools/windows/Run-DirectBoardIteration.py",
        ["--spec", f"{windows_iter_dir}/board_run_spec.json"],
    )
    write_remote_stdout(iter_dir, "windows_runner", result)
    if result.returncode != 0:
        try:
            copy_remote_result_tree(remote, windows_iter_dir, iter_dir)
        except Exception:
            pass
        raise SystemExit(f"Windows video runner failed; see {iter_dir / 'windows_runner_stdout.txt'}")

    candidate_remote_video = f"{windows_iter_dir}/artifacts/main/stream_chn0.h264"
    metrics_remote_dir = spec["runs"][0].get("output_dir")
    metrics_dir_name = Path(str(metrics_remote_dir)).name if metrics_remote_dir else None
    frame_detections_remote = (
        f"{windows_iter_dir}/artifacts/main/pulled/{metrics_dir_name}/frame_detections.jsonl"
        if metrics_dir_name
        else None
    )
    analyzer_result = run_windows_python(
        remote,
        f"{remote.config.repo_root}/tools/windows/Analyze-BoardVideo.py",
        (
            [
            "--video",
            candidate_remote_video,
            "--output-dir",
            f"{windows_iter_dir}/analysis",
            "--label",
            getattr(args, "video_label", None) or iter_dir.name,
            "--expected-person-count",
            str(args.expected_person_count),
            "--board-run-spec",
            f"{windows_iter_dir}/board_run_spec.json",
        ]
            + (
                [
                    "--reference-video",
                    staged_assets["reference_video"],
                    "--reference-label",
                    getattr(args, "reference_label", None) or "reference",
                ]
                if staged_assets["reference_video"]
                else []
            )
            + (["--frame-detections", frame_detections_remote] if frame_detections_remote else [])
        ),
    )
    write_remote_stdout(iter_dir, "windows_analyzer", analyzer_result)
    if analyzer_result.returncode != 0:
        try:
            copy_remote_result_tree(remote, windows_iter_dir, iter_dir)
        except Exception:
            pass
        raise SystemExit(f"Windows video analyzer failed; see {iter_dir / 'windows_analyzer_stdout.txt'}")

    copy_remote_result_tree(remote, windows_iter_dir, iter_dir)
    run_result = fetch_run_result(iter_dir)
    ensure_server_review_artifacts(iter_dir)
    write_runtime_fidelity_summary(iter_dir, spec)
    write_visual_review_stub(iter_dir)
    write_video_summary(iter_dir, run_result)
    update_campaign_index(iter_dir, spec, run_result)
    print(f"video iteration complete: {iter_dir}")


def run_batch_full(args: argparse.Namespace, remote: WindowsRemote, repo_root: Path) -> None:
    iter_dir = init_iteration(repo_root, args.campaign_id)
    campaign_dir = iter_dir.parent
    ensure_campaign_manifest(campaign_dir, args.campaign_id, remote.config, repo_root)

    sync_windows_support_files(remote, repo_root)
    create_windows_iter_layout(remote, f"{remote.config.repo_root}/logs/direct_runs/{args.campaign_id}/{iter_dir.name}")

    package_info = resolve_package_dir(repo_root, iter_dir, args)
    local_package_dir = Path(package_info["package_dir"])
    windows_iter_dir = f"{remote.config.repo_root}/logs/direct_runs/{args.campaign_id}/{iter_dir.name}"
    sync_package_to_windows(remote, local_package_dir, f"{windows_iter_dir}/windows_package")

    spec = write_full_batch_spec(iter_dir, windows_iter_dir, package_info, args, remote)
    remote.scp_to([iter_dir / "board_run_spec.json"], f"{windows_iter_dir}/board_run_spec.json")

    result = run_windows_python(
        remote,
        f"{remote.config.repo_root}/tools/windows/Run-DirectBoardIteration.py",
        ["--spec", f"{windows_iter_dir}/board_run_spec.json"],
    )
    write_remote_stdout(iter_dir, "windows_runner", result)
    if result.returncode != 0:
        try:
            copy_remote_result_tree(remote, windows_iter_dir, iter_dir)
        except Exception:
            pass
        raise SystemExit(f"Windows full batch runner failed; see {iter_dir / 'windows_runner_stdout.txt'}")

    copy_remote_result_tree(remote, windows_iter_dir, iter_dir)
    run_result = fetch_run_result(iter_dir)
    summarize_full_batch(repo_root, iter_dir, run_result, spec, args)
    print(f"full batch iteration complete: {iter_dir}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Single-driver board validation orchestrator")
    parser.add_argument("--repo-root", default=str(repo_root_from_script()))
    parser.add_argument("--windows-env", default=str(Path("~/.config/elevator_ai/session_pusher.env").expanduser()))
    parser.add_argument("--windows-host", default=None)
    parser.add_argument("--windows-port", type=int, default=None)
    parser.add_argument("--windows-user", default=None)
    parser.add_argument("--windows-repo-root", default=None)
    parser.add_argument("--identity-file", default=None)
    parser.add_argument("--board-host", default="192.168.1.168")
    parser.add_argument("--board-user", default="root")
    parser.add_argument("--board-password", default="ebaina")
    parser.add_argument("--campaign-id", required=True)

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("prepare-mode", help="disable session automation and verify the tunnel path")

    batch_parser = subparsers.add_parser("run-batch", help="run one val50=25+25 batch iteration")
    batch_parser.add_argument("--score", type=float, default=0.15)
    batch_parser.add_argument("--nms", type=float, default=0.45)
    batch_parser.add_argument("--ebike-cleanup", choices=("auto", "full", "safe", "off"), default="auto")
    batch_parser.add_argument("--dataset-root", default=FULL_DATASET_ROOT)
    batch_parser.add_argument("--skip-build", action="store_true")
    batch_parser.add_argument("--reuse-package-dir", default=None)

    full_batch_parser = subparsers.add_parser("run-batch-full", help="run the full board dataset in stable chunks")
    full_batch_parser.add_argument("--score", type=float, default=0.15)
    full_batch_parser.add_argument("--nms", type=float, default=0.45)
    full_batch_parser.add_argument("--ebike-cleanup", choices=("auto", "full", "safe", "off"), default="auto")
    full_batch_parser.add_argument("--chunk-size", type=int, default=25)
    full_batch_parser.add_argument("--dataset-root", default=FULL_DATASET_ROOT)
    full_batch_parser.add_argument("--skip-build", action="store_true")
    full_batch_parser.add_argument("--reuse-package-dir", default=None)
    full_batch_parser.add_argument(
        "--dataset-split",
        action="append",
        default=None,
        help="repeatable split=count spec, for example --dataset-split train=3601 --dataset-split val=720",
    )

    video_parser = subparsers.add_parser("run-video", help="run one file-mode video iteration")
    video_parser.add_argument("--score", type=float, default=0.15)
    video_parser.add_argument("--nms", type=float, default=0.45)
    video_parser.add_argument("--smooth-window", type=int, default=5)
    video_parser.add_argument("--ebike-cleanup", choices=("auto", "full", "safe", "off"), default="auto")
    video_parser.add_argument("--duration-seconds", type=int, default=12)
    video_parser.add_argument("--duration-policy", choices=("fixed", "source-full"), default="fixed")
    video_parser.add_argument("--rtsp-port", type=int, default=DEFAULT_FILE_RTSP_PORT)
    video_parser.add_argument("--input-path", default="/root/data/image/dolls_video.h264")
    video_parser.add_argument("--input-local-path", default=None)
    video_parser.add_argument("--board-input-path", default=None)
    video_parser.add_argument("--expected-person-count", type=int, default=DEFAULT_VIDEO_EXPECTED_PERSON_COUNT)
    video_parser.add_argument("--reference-video", default=DEFAULT_REFERENCE_VIDEO)
    video_parser.add_argument("--reference-label", default=DEFAULT_REFERENCE_LABEL)
    video_parser.add_argument("--video-label", default=None)
    video_parser.add_argument("--skip-build", action="store_true")
    video_parser.add_argument("--reuse-package-dir", default=None)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    remote = WindowsRemote(load_windows_config(args))

    if args.command == "prepare-mode":
        prepare_mode(args, remote, repo_root)
        return 0
    if args.command == "run-batch":
        run_batch(args, remote, repo_root)
        return 0
    if args.command == "run-batch-full":
        run_batch_full(args, remote, repo_root)
        return 0
    if args.command == "run-video":
        run_video(args, remote, repo_root)
        return 0
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
