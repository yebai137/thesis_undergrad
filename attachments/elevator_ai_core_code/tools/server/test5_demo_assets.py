#!/usr/bin/env python3
"""Helpers for Phase 3.3 test5 demo candidate indexing and board demo commands."""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path, PureWindowsPath
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _nested_get(mapping: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def _first_file_run(run_spec: Mapping[str, Any]) -> Mapping[str, Any]:
    runs = run_spec.get("runs", [])
    if not isinstance(runs, list):
        return {}
    for run in runs:
        if isinstance(run, Mapping) and run.get("mode") == "file":
            return run
    return {}


def _resolve_artifact_path(iter_path: Path, raw_value: Any, fallback_name: str) -> Optional[str]:
    fallback_path = iter_path / "analysis" / fallback_name
    if isinstance(raw_value, str) and raw_value:
        raw_path = Path(raw_value)
        if raw_path.exists():
            return str(raw_path)
        normalized_value = raw_value.replace("\\", "/")
        raw_basename = PureWindowsPath(normalized_value).name
        if raw_basename:
            local_basename_path = iter_path / "analysis" / raw_basename
            if local_basename_path.exists():
                return str(local_basename_path)
    if fallback_path.exists():
        return str(fallback_path)
    if isinstance(raw_value, str) and raw_value:
        return raw_value
    return None


def _duration_to_ms(duration_seconds: Any) -> Optional[int]:
    if duration_seconds is None:
        return None
    try:
        return int(round(float(duration_seconds) * 1000.0))
    except (TypeError, ValueError):
        return None


def build_candidate_record(
    iter_dir: Path | str,
    *,
    candidate_id: str,
    narrative: str,
    note: str,
) -> Dict[str, Any]:
    iter_path = Path(iter_dir)
    analysis_dir = iter_path / "analysis"
    summary = _read_json(analysis_dir / "summary.json")
    review_pack = _read_json(analysis_dir / "review_pack.json")
    visual_review = _read_json(analysis_dir / "visual_review.json")
    ebike_summary = _read_json(analysis_dir / "ebike_false_alarm_summary.json")
    prepared_input_metadata = _read_json(iter_path / "prepared_input_metadata.json")
    source_video_metadata = _read_json(iter_path / "source_video_metadata.json")
    run_spec = _read_json(iter_path / "board_run_spec.json")
    board_cfg = run_spec.get("board", {}) if isinstance(run_spec.get("board"), Mapping) else {}
    main_run = _first_file_run(run_spec)

    clean_preview_path = _resolve_artifact_path(
        iter_path,
        _nested_get(review_pack, "clean", "preview_video_h264")
        or _nested_get(review_pack, "clean", "preview_video")
        or review_pack.get("primary_review_artifact"),
        "preview_clean_h264.mp4",
    )
    if clean_preview_path is None:
        clean_preview_path = _resolve_artifact_path(iter_path, None, "preview_clean.mp4")
    public_preview_path = _resolve_artifact_path(
        iter_path,
        _nested_get(review_pack, "public", "preview_video_h264")
        or _nested_get(review_pack, "public", "preview_video"),
        "preview_public_h264.mp4",
    )
    if public_preview_path is None:
        public_preview_path = _resolve_artifact_path(iter_path, None, "preview_public.mp4")
    ebike_section = _nested_get(visual_review, "sections", "ebike_visibility", default={})
    if not isinstance(ebike_section, Mapping):
        ebike_section = {}

    source_fps = (
        prepared_input_metadata.get("fps")
        or _nested_get(prepared_input_metadata, "source_stream_metadata", "fps")
        or source_video_metadata.get("fps")
        or _nested_get(summary, "video", "fps")
    )
    source_frame_count = (
        prepared_input_metadata.get("frame_count")
        or _nested_get(prepared_input_metadata, "source_stream_metadata", "frame_count")
        or _nested_get(summary, "video", "frame_count")
    )

    duration_seconds = (
        prepared_input_metadata.get("duration_seconds")
        or _nested_get(prepared_input_metadata, "source_stream_metadata", "duration_seconds")
        or _nested_get(summary, "review_timeline", "duration_seconds")
    )
    if duration_seconds is None:
        frame_count = _nested_get(summary, "video", "frame_count")
        fps = _nested_get(summary, "video", "fps")
        if frame_count is not None and fps:
            duration_seconds = round(float(frame_count) / float(fps), 2)
    if duration_seconds is None:
        duration_seconds = _nested_get(run_spec, "analysis", "source_video_metadata", "duration_seconds")

    return {
        "candidate_id": candidate_id,
        "iteration_dir": str(iter_path.resolve()),
        "video_label": (
            _nested_get(summary, "video", "label")
            or _nested_get(run_spec, "analysis", "label")
            or iter_path.name
        ),
        "narrative": narrative,
        "note": note,
        "duration_seconds": duration_seconds,
        "primary_review_artifact": review_pack.get("primary_review_artifact"),
        "clean_preview_path": clean_preview_path,
        "public_preview_path": public_preview_path,
        "review_pack_path": str((analysis_dir / "review_pack.json").resolve()),
        "visual_review_path": str((analysis_dir / "visual_review.json").resolve()),
        "review_status": visual_review.get("status"),
        "review_recommendation": visual_review.get("recommendation", "pending"),
        "ebike_visibility_status": ebike_section.get("status", "unknown"),
        "ebike_visibility_summary": ebike_section.get("summary"),
        "public_gap_frames": ebike_summary.get("frames_with_confirmed_public_gap"),
        "frames_with_public_ebike": ebike_summary.get("frames_with_public_ebike"),
        "board_input_path": main_run.get("input_path"),
        "input_local_path": main_run.get("input_local_path"),
        "surface": "clean",
        "timing": "source",
        "single_shot": True,
        "source_fps": source_fps,
        "source_frame_count": source_frame_count,
        "score": main_run.get("score", board_cfg.get("score")),
        "nms": main_run.get("nms", board_cfg.get("nms")),
        "smooth_window": main_run.get("smooth_window", board_cfg.get("smooth_window")),
        "rtsp_port": main_run.get("rtsp_port", board_cfg.get("rtsp_port")),
        "output_dir": f"/root/direct_video_metrics_{candidate_id}",
        "binary_md5": _nested_get(run_spec, "package", "binary_md5"),
        "model_md5": _nested_get(run_spec, "package", "model_md5"),
    }


def build_demo_manifest(
    records: Sequence[Mapping[str, Any]],
    *,
    generated_at: str,
    default_binary_path: str = "/root/elevator_ai/elevator_yolo",
    default_model_path: str = "/root/elevator_ai/yolov8.om",
) -> Dict[str, Any]:
    profiles: List[Dict[str, Any]] = []
    for record in records:
        profile: Dict[str, Any] = {
            "candidate_id": record["candidate_id"],
            "board_input_path": record.get("board_input_path"),
            "demo_board_input_path": record.get("demo_board_input_path"),
            "input_local_path": record.get("input_local_path"),
            "surface": record.get("surface") or "clean",
            "timing": record.get("timing") or "source",
            "single_shot": bool(record.get("single_shot", True)),
            "source_fps": record.get("source_fps"),
            "source_frame_count": record.get("source_frame_count"),
            "score": record.get("score"),
            "nms": record.get("nms"),
            "smooth_window": record.get("smooth_window"),
            "rtsp_port": record.get("rtsp_port"),
            "output_dir": record.get("output_dir") or f"/root/direct_video_metrics_{record['candidate_id']}",
            "source_iteration_dir": record.get("iteration_dir"),
            "video_label": record.get("video_label"),
            "narrative": record.get("narrative"),
            "note": record.get("note"),
            "clean_preview_path": record.get("clean_preview_path"),
            "public_preview_path": record.get("public_preview_path"),
            "visual_review_path": record.get("visual_review_path"),
            "review_recommendation": record.get("review_recommendation"),
            "ebike_visibility_status": record.get("ebike_visibility_status"),
            "public_gap_frames": record.get("public_gap_frames"),
            "duration_seconds": record.get("duration_seconds"),
            "extra_args": list(record.get("extra_args", []) or []),
        }
        profiles.append(profile)
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "default_binary_path": default_binary_path,
        "default_model_path": default_model_path,
        "default_output_mode": "hdmi",
        "profiles": profiles,
    }


def render_candidate_markdown(records: Sequence[Mapping[str, Any]], *, generated_at: str) -> str:
    lines = [
        "# Phase 3.3 Test5 Demo Candidate Index",
        "",
        f"Generated at: {generated_at}",
        "",
        "These are candidate demo profiles only. Final board deployment waits for explicit user selection.",
    ]
    for record in records:
        lines.extend(
            [
                "",
                f"## {record['candidate_id']}",
                f"- iteration_dir: {record.get('iteration_dir')}",
                f"- video_label: {record.get('video_label')}",
                f"- narrative: {record.get('narrative')}",
                f"- note: {record.get('note')}",
                f"- clean_preview: {record.get('clean_preview_path')}",
                f"- public_preview: {record.get('public_preview_path')}",
                f"- visual_review: {record.get('visual_review_path')}",
                f"- recommendation: {record.get('review_recommendation')}",
                f"- ebike_visibility: {record.get('ebike_visibility_status')}",
                f"- public_gap_frames: {record.get('public_gap_frames')}",
                f"- duration_seconds: {record.get('duration_seconds')}",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def _quote_parts(parts: Iterable[object]) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts)


def _normalize_vo_intf_type(raw_value: Any) -> int:
    value = str(raw_value or "mipi").strip().lower()
    if value == "mipi":
        return 0
    if value == "bt1120":
        return 1
    raise ValueError(f"unsupported vo_intf_type: {raw_value}")


def build_board_demo_command(
    binary_path: str,
    model_path: str,
    profile: Mapping[str, Any],
    *,
    output_mode: str = "hdmi",
    rtsp_port: Optional[int] = None,
    vo_intf_type: Optional[str] = None,
) -> str:
    if output_mode not in {"hdmi", "rtsp"}:
        raise ValueError(f"unsupported output_mode: {output_mode}")

    input_path = profile.get("board_input_path") or profile.get("input_path") or profile.get("demo_board_input_path")
    if not input_path:
        raise ValueError("profile is missing board_input_path")

    parts: List[object] = [
        binary_path,
        "file",
        "--input",
        input_path,
        "--model",
        model_path,
        "--surface",
        str(profile.get("surface") or "clean"),
        "--timing",
        str(profile.get("timing") or "source"),
    ]
    if bool(profile.get("single_shot", True)):
        parts.append("--single-shot")
    if profile.get("source_fps") is not None:
        parts.extend(["--source-fps", profile["source_fps"]])
    if profile.get("source_frame_count") is not None:
        parts.extend(["--source-frame-count", int(profile["source_frame_count"])])
    duration_ms = _duration_to_ms(profile.get("duration_seconds"))
    if duration_ms is not None:
        parts.extend(["--source-duration-ms", duration_ms])
    if profile.get("output_dir"):
        parts.extend(["--output-dir", profile["output_dir"]])
    if profile.get("score") is not None:
        parts.extend(["--score", profile["score"]])
    if profile.get("nms") is not None:
        parts.extend(["--nms", profile["nms"]])
    if profile.get("smooth_window") is not None:
        parts.extend(["--smooth-window", int(profile["smooth_window"])])
    if output_mode == "rtsp":
        port = rtsp_port if rtsp_port is not None else profile.get("rtsp_port") or 554
        parts.extend(["--rtsp-port", int(port)])
    for extra in profile.get("extra_args", []) or []:
        parts.append(extra)
    return _quote_parts(parts)


def load_demo_manifest(path: Path | str) -> Dict[str, Any]:
    return _read_json(Path(path))


def select_profile(manifest: Mapping[str, Any], candidate_id: str) -> Dict[str, Any]:
    profiles = manifest.get("profiles", [])
    if not isinstance(profiles, list):
        raise KeyError(f"profile not found: {candidate_id}")
    for profile in profiles:
        if isinstance(profile, Mapping) and profile.get("candidate_id") == candidate_id:
            return dict(profile)
    raise KeyError(f"profile not found: {candidate_id}")


def _cmd_build_command(args: argparse.Namespace) -> int:
    manifest = load_demo_manifest(args.manifest)
    profile = select_profile(manifest, args.profile)
    binary_path = args.binary_path or manifest.get("default_binary_path")
    model_path = args.model_path or manifest.get("default_model_path")
    command = build_board_demo_command(
        str(binary_path),
        str(model_path),
        profile,
        output_mode=args.output_mode,
        rtsp_port=args.rtsp_port,
        vo_intf_type=args.vo_intf_type,
    )
    print(command)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 3.3 test5 demo asset helpers")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_command_parser = subparsers.add_parser("build-command", help="render one board-side demo command")
    build_command_parser.add_argument("--manifest", required=True)
    build_command_parser.add_argument("--profile", required=True)
    build_command_parser.add_argument("--binary-path", default=None)
    build_command_parser.add_argument("--model-path", default=None)
    build_command_parser.add_argument("--output-mode", choices=("hdmi", "rtsp"), default="hdmi")
    build_command_parser.add_argument("--rtsp-port", type=int, default=None)
    build_command_parser.add_argument("--vo-intf-type", choices=("mipi", "bt1120"), default=None)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "build-command":
        return _cmd_build_command(args)
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
