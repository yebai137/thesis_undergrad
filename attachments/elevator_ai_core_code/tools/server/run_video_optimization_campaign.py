#!/usr/bin/env python3
"""Phase-aware board video optimization campaign orchestrator.

Boundary:
- This file owns phase sequencing, candidate selection, state transitions,
  aggregation, and final recommendation.
- Phase 0 operational work is intentionally performed at runtime by the main
  agent (and optionally a temporary ops subagent), then imported here as state.
- ``run_single_driver_campaign.py`` remains the only low-level board runner.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_single_driver_campaign as single


DEFAULT_PHASE1_CANDIDATES = [
    {"name": "B0", "score": 0.15, "nms": 0.45, "smooth_window": 5},
    {"name": "B1", "score": 0.15, "nms": 0.55, "smooth_window": 5},
]

DEFAULT_PHASE2_ROUND1 = [
    {"name": "R1", "score": 0.12, "nms": 0.50, "smooth_window": 5},
    {"name": "R2", "score": 0.10, "nms": 0.50, "smooth_window": 7},
    {"name": "R3", "score": 0.10, "nms": 0.55, "smooth_window": 7},
    {"name": "R4", "score": 0.12, "nms": 0.55, "smooth_window": 9},
]

DEFAULT_PHASE2_ROUND2 = {
    "miss": [
        {"name": "M1", "score": 0.08, "nms": 0.55, "smooth_window": 7},
        {"name": "M2", "score": 0.08, "nms": 0.60, "smooth_window": 9},
    ],
    "duplicate": [
        {"name": "D1", "score": 0.12, "nms": 0.40, "smooth_window": 5},
        {"name": "D2", "score": 0.15, "nms": 0.40, "smooth_window": 7},
    ],
    "instability": [
        {"name": "S1", "score": 0.10, "nms": 0.50, "smooth_window": 9},
        {"name": "S2", "score": 0.12, "nms": 0.50, "smooth_window": 11},
    ],
}


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def campaign_dir(repo_root: Path, campaign_id: str) -> Path:
    return repo_root / "logs" / "direct_runs" / campaign_id


def phase0_dir(campaign_root: Path) -> Path:
    return campaign_root / "phase0"


def phase_runs_dir(campaign_root: Path) -> Path:
    return campaign_root / "phase_runs"


def state_path(campaign_root: Path) -> Path:
    return campaign_root / "phase_state.json"


def aggregate_path(campaign_root: Path) -> Path:
    return campaign_root / "aggregate_summary.json"


def manifest_path(campaign_root: Path) -> Path:
    return campaign_root / "campaign_manifest.json"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def high_priority_video_names(manifest: Dict[str, Any]) -> List[str]:
    return [
        str(video["name"])
        for video in manifest.get("videos", [])
        if str(video.get("priority") or "").lower() == "high"
    ]


def main_video_names_set(manifest: Dict[str, Any]) -> set[str]:
    return set(high_priority_video_names(manifest))


def phase3_video_order(manifest: Dict[str, Any]) -> List[str]:
    preferred = ["test6", "test3", "test5", "test2"]
    available = main_video_names_set(manifest)
    ordered = [name for name in preferred if name in available]
    ordered.extend(name for name in high_priority_video_names(manifest) if name not in ordered)
    return ordered


def default_manifest(repo_root: Path) -> Dict[str, Any]:
    home_root = repo_root.parent
    return {
        "videos": [
            {
                "name": "test2",
                "priority": "high",
                "local_path": str((home_root / "test2.mp4").resolve()),
                "prepared_name": "test2.h264",
                "board_input_path": "/root/data/optimization_inputs/test2.h264",
                "expected_person_count": 4,
                "duration_seconds": 12,
                "duration_policy": "source-full",
                "reference_video": single.DEFAULT_REFERENCE_VIDEO,
                "reference_label": single.DEFAULT_REFERENCE_LABEL,
            },
            {
                "name": "test3",
                "priority": "high",
                "local_path": str((home_root / "test3.mp4").resolve()),
                "prepared_name": "test3.h264",
                "board_input_path": "/root/data/optimization_inputs/test3.h264",
                "expected_person_count": 2,
                "duration_seconds": 12,
                "duration_policy": "source-full",
                "reference_video": single.DEFAULT_REFERENCE_VIDEO,
                "reference_label": single.DEFAULT_REFERENCE_LABEL,
            },
            {
                "name": "test5",
                "priority": "high",
                "local_path": str((home_root / "test5.mp4").resolve()),
                "prepared_name": "test5.h264",
                "board_input_path": "/root/data/optimization_inputs/test5.h264",
                "expected_person_count": 0,
                "duration_seconds": 12,
                "duration_policy": "source-full",
                "reference_video": single.DEFAULT_REFERENCE_VIDEO,
                "reference_label": single.DEFAULT_REFERENCE_LABEL,
            },
            {
                "name": "test6",
                "priority": "high",
                "local_path": str((home_root / "test6.mp4").resolve()),
                "prepared_name": "test6.h264",
                "board_input_path": "/root/data/optimization_inputs/test6.h264",
                "expected_person_count": 0,
                "duration_seconds": 12,
                "duration_policy": "source-full",
                "reference_video": single.DEFAULT_REFERENCE_VIDEO,
                "reference_label": single.DEFAULT_REFERENCE_LABEL,
            },
            {
                "name": "dolls_video.h264",
                "priority": "medium",
                "board_input_path": "/root/data/image/dolls_video.h264",
                "expected_person_count": single.DEFAULT_VIDEO_EXPECTED_PERSON_COUNT,
                "duration_seconds": 12,
                "duration_policy": "fixed",
                "reference_video": single.DEFAULT_REFERENCE_VIDEO,
                "reference_label": single.DEFAULT_REFERENCE_LABEL,
            },
        ],
        "phase1_candidates": DEFAULT_PHASE1_CANDIDATES,
        "phase2_round1_candidates": DEFAULT_PHASE2_ROUND1,
        "phase2_round2_candidates": DEFAULT_PHASE2_ROUND2,
        "phase3_order": [
            "hold_6_600",
            "hold_8_800",
            "containment_4_90",
            "strip_9_060",
            "soft_nms_last",
        ],
    }


def load_manifest(repo_root: Path, input_manifest: Optional[str]) -> Dict[str, Any]:
    if input_manifest is None:
        return default_manifest(repo_root)
    payload = load_json(Path(input_manifest).expanduser().resolve())
    if "videos" not in payload:
        raise SystemExit("manifest must include videos")
    payload.setdefault("phase1_candidates", DEFAULT_PHASE1_CANDIDATES)
    payload.setdefault("phase2_round1_candidates", DEFAULT_PHASE2_ROUND1)
    payload.setdefault("phase2_round2_candidates", DEFAULT_PHASE2_ROUND2)
    payload.setdefault("phase3_order", default_manifest(repo_root)["phase3_order"])
    return payload


def ensure_campaign_layout(campaign_root: Path, manifest: Dict[str, Any]) -> None:
    campaign_root.mkdir(parents=True, exist_ok=True)
    phase0_dir(campaign_root).mkdir(parents=True, exist_ok=True)
    (phase0_dir(campaign_root) / "prepared_inputs").mkdir(parents=True, exist_ok=True)
    phase_runs_dir(campaign_root).mkdir(parents=True, exist_ok=True)
    write_json(manifest_path(campaign_root), manifest)


def load_or_init_state(campaign_root: Path, manifest: Dict[str, Any]) -> Dict[str, Any]:
    current = state_path(campaign_root)
    if current.exists():
        return load_json(current)
    state: Dict[str, Any] = {
        "manifest": manifest,
        "phase0": {"status": "pending"},
        "phase1": {"status": "pending"},
        "phase2": {
            "status": "pending",
            "round1_complete": False,
            "round2_issue": None,
            "round2_complete": False,
            "dolls_complete": False,
            "best_candidate": None,
            "best_score_main": None,
            "score_gap_vs_next": None,
            "converged": False,
            "no_significant_improvement": False,
        },
        "phase3": {"status": "pending", "candidates": {}},
        "phase4": {"status": "pending"},
        "package": {},
        "prepared_inputs": {},
        "runs": [],
    }
    write_json(current, state)
    return state


def save_state(campaign_root: Path, state: Dict[str, Any]) -> None:
    write_json(state_path(campaign_root), state)


def list_iterations(campaign_root: Path) -> List[str]:
    if not campaign_root.exists():
        return []
    return sorted(
        child.name
        for child in campaign_root.iterdir()
        if child.is_dir() and child.name.startswith("iter_")
    )


def detect_new_iteration(campaign_root: Path, before: Sequence[str]) -> Path:
    before_set = set(before)
    after = list_iterations(campaign_root)
    new_entries = [name for name in after if name not in before_set]
    if len(new_entries) != 1:
        raise SystemExit(f"expected exactly one new iteration, found: {new_entries!r}")
    return campaign_root / new_entries[0]


def single_driver_base_command(repo_root: Path, args: argparse.Namespace, subcommand: str) -> List[str]:
    return [
        sys.executable,
        str(repo_root / "tools" / "server" / "run_single_driver_campaign.py"),
        "--repo-root",
        str(repo_root),
        "--windows-env",
        str(Path(args.windows_env).expanduser()),
        "--campaign-id",
        args.campaign_id,
        "--board-host",
        args.board_host,
        "--board-user",
        args.board_user,
        "--board-password",
        args.board_password,
        subcommand,
    ]


def run_single_driver_command(
    repo_root: Path,
    campaign_root: Path,
    command: List[str],
    log_stem: str,
    failure_message: str,
) -> Path:
    before = list_iterations(campaign_root)
    result = subprocess.run(command, capture_output=True, text=True, cwd=str(repo_root))
    log_prefix = phase_runs_dir(campaign_root) / log_stem
    write_text(log_prefix.with_suffix(".stdout.txt"), result.stdout)
    write_text(log_prefix.with_suffix(".stderr.txt"), result.stderr)
    if result.returncode != 0:
        raise SystemExit(
            f"{failure_message}\n"
            f"stdout log: {log_prefix.with_suffix('.stdout.txt')}\n"
            f"stderr log: {log_prefix.with_suffix('.stderr.txt')}"
        )
    return detect_new_iteration(campaign_root, before)


def missing_review_paths(records: Sequence[Dict[str, Any]]) -> List[str]:
    missing: List[str] = []
    for record in records:
        review_path = Path(str(record["review_path"]))
        if not review_path.exists():
            missing.append(str(review_path))
            continue
        review_verdict = single.validate_visual_review(review_path)
        review = dict(review_verdict.get("payload") or {})
        if review_verdict.get("status") != "ready":
            missing.append(str(review_path))
            continue
        if review.get("overall_score") is None or review.get("recommendation") == "pending":
            missing.append(str(review_path))
    return missing


def _existing_local_path(raw_value: object) -> Optional[str]:
    text = str(raw_value or "").strip()
    if not text:
        return None
    candidate = Path(text)
    if candidate.is_absolute() and candidate.exists():
        return str(candidate)
    return None


def phase3_video_gate_verdict(record: Dict[str, Any]) -> Dict[str, Any]:
    iter_dir = Path(str(record["iteration_dir"]))
    analysis_dir = iter_dir / "analysis"
    issues: List[str] = []

    review_path = analysis_dir / "visual_review.json"
    review_verdict = single.validate_visual_review(review_path)
    review = dict(review_verdict.get("payload") or {})
    if review_verdict.get("status") != "ready":
        issues.append("visual_review_not_ready")
    if review.get("overall_score") is None:
        issues.append("missing_visual_review_score")
    if str(review.get("recommendation") or "").strip().lower() == "pending":
        issues.append("visual_review_recommendation_pending")
    if list(review.get("blocking_issues") or []):
        issues.append("visual_blockers_present")

    runtime_fidelity_path = analysis_dir / "runtime_fidelity_summary.json"
    runtime_fidelity = load_json(runtime_fidelity_path) if runtime_fidelity_path.exists() else {}
    if str(runtime_fidelity.get("status") or "").strip().lower() != "ready":
        issues.append("runtime_fidelity_not_ready")

    count_accuracy_path = analysis_dir / "count_accuracy_summary.json"
    count_accuracy = load_json(count_accuracy_path) if count_accuracy_path.exists() else {}
    if str(count_accuracy.get("status") or "").strip().lower() != "ready":
        issues.append("count_accuracy_not_ready")
    elif not bool(count_accuracy.get("target_met")):
        issues.append("count_accuracy_below_threshold")

    review_pack_path = analysis_dir / "review_pack.json"
    review_pack = load_json(review_pack_path) if review_pack_path.exists() else {}
    required_review_paths = {
        "primary_review_artifact": _existing_local_path(review_pack.get("primary_review_artifact")),
        "raw_review_h264": _existing_local_path(
            (review_pack.get("raw") or {}).get("review_video_h264")
            or (review_pack.get("secondary_review_artifacts") or {}).get("raw_output_review_h264")
        ),
        "public_review_h264": _existing_local_path(
            (review_pack.get("public") or {}).get("preview_video_h264")
            or (review_pack.get("clean") or {}).get("preview_video_h264")
            or (review_pack.get("secondary_review_artifacts") or {}).get("public_review_video_h264")
        ),
        "debug_review_h264": _existing_local_path(
            (review_pack.get("debug") or {}).get("preview_video_h264")
            or (review_pack.get("secondary_review_artifacts") or {}).get("debug_review_video_h264")
        ),
    }
    for key, resolved_path in required_review_paths.items():
        if resolved_path is None:
            issues.append(f"missing_{key}")

    return {
        "status": "ready" if not issues else "blocked",
        "issues": issues,
        "review_path": str(review_path),
        "iteration_dir": str(iter_dir),
        "video_name": record.get("video_name"),
        "runtime_fidelity_path": str(runtime_fidelity_path),
        "count_accuracy_path": str(count_accuracy_path),
        "review_pack_path": str(review_pack_path),
        "review": review,
        "runtime_fidelity": runtime_fidelity,
        "count_accuracy": count_accuracy,
    }


def load_iteration_metrics(iter_dir: Path) -> Dict[str, Any]:
    summary_path = iter_dir / "analysis" / "summary.json"
    review_path = iter_dir / "analysis" / "visual_review.json"
    summary = load_json(summary_path) if summary_path.exists() else {}
    frame_metrics = dict(summary.get("frame_metrics", {}).get("metrics", {}) or {})
    return {
        "summary_path": str(summary_path),
        "review_path": str(review_path),
        "frame_metrics": frame_metrics,
    }


def run_low_level_video(
    repo_root: Path,
    campaign_root: Path,
    args: argparse.Namespace,
    video_payload: Dict[str, Any],
    candidate: Dict[str, Any],
    candidate_group: str,
    package_info: Dict[str, Any],
) -> Dict[str, Any]:
    command = single_driver_base_command(repo_root, args, "run-video") + [
        "--score",
        str(candidate["score"]),
        "--nms",
        str(candidate["nms"]),
        "--smooth-window",
        str(candidate["smooth_window"]),
        "--duration-seconds",
        str(video_payload.get("duration_seconds", 12)),
        "--duration-policy",
        str(video_payload.get("duration_policy", "fixed")),
        "--input-path",
        str(video_payload["board_input_path"]),
        "--board-input-path",
        str(video_payload["board_input_path"]),
        "--expected-person-count",
        str(video_payload.get("expected_person_count", 0)),
        "--reference-video",
        str(video_payload.get("reference_video") or single.DEFAULT_REFERENCE_VIDEO),
        "--reference-label",
        str(video_payload.get("reference_label") or single.DEFAULT_REFERENCE_LABEL),
        "--video-label",
        str(video_payload["video_name"]),
        "--skip-build",
        "--reuse-package-dir",
        str(package_info["package_dir"]),
    ]
    if video_payload.get("source"):
        command.extend(["--input-local-path", str(video_payload["source"])])
    iter_dir = run_single_driver_command(
        repo_root,
        campaign_root,
        command,
        f"{candidate_group}_{video_payload['video_name']}_{candidate['name']}",
        f"run-video failed for {video_payload['video_name']} / {candidate['name']}",
    )
    metrics = load_iteration_metrics(iter_dir)
    run_result_path = iter_dir / "run_result.json"
    run_result = load_json(run_result_path) if run_result_path.exists() else {}
    return {
        "phase": candidate_group,
        "video_name": video_payload["video_name"],
        "candidate_name": candidate["name"],
        "score": candidate["score"],
        "nms": candidate["nms"],
        "smooth_window": candidate["smooth_window"],
        "iteration_dir": str(iter_dir),
        "summary_path": metrics["summary_path"],
        "review_path": metrics["review_path"],
        "frame_metrics": metrics["frame_metrics"],
        "binary_md5": run_result.get("package", {}).get("binary_md5"),
        "model_md5": run_result.get("package", {}).get("model_md5"),
    }


def run_low_level_batch_gate(
    repo_root: Path,
    campaign_root: Path,
    args: argparse.Namespace,
    package_info: Dict[str, Any],
    label: str,
) -> Dict[str, Any]:
    command = single_driver_base_command(repo_root, args, "run-batch") + [
        "--score",
        "0.15",
        "--nms",
        "0.45",
        "--skip-build",
        "--reuse-package-dir",
        str(package_info["package_dir"]),
    ]
    iter_dir = run_single_driver_command(
        repo_root,
        campaign_root,
        command,
        f"phase3_gate_{label}",
        f"run-batch gate failed for {label}",
    )
    gate_path = iter_dir / "analysis" / "gate_result.json"
    gate = load_json(gate_path) if gate_path.exists() else {}
    return {
        "label": label,
        "iteration_dir": str(iter_dir),
        "gate_path": str(gate_path),
        "gate": gate,
    }


def aggregate_campaign(campaign_root: Path, state: Dict[str, Any]) -> Dict[str, Any]:
    runs = state.get("runs", [])
    main_video_names = main_video_names_set(state.get("manifest", {}))
    by_candidate: Dict[str, Dict[str, Any]] = {}
    for record in runs:
        candidate_name = str(record["candidate_name"])
        candidate = by_candidate.setdefault(
            candidate_name,
            {
                "candidate_name": candidate_name,
                "phases": [],
                "runs": [],
                "main_video_scores": [],
                "blocking_issue_count": 0,
                "metric_accumulator": {
                    "mean_abs_count_error": [],
                    "undercount_ratio": [],
                    "duplicate_pair_rate": [],
                },
            },
        )
        if record["phase"] not in candidate["phases"]:
            candidate["phases"].append(record["phase"])
        review_path = Path(str(record["review_path"]))
        summary_path = Path(str(record["summary_path"]))
        review = load_json(review_path) if review_path.exists() else {}
        summary = load_json(summary_path) if summary_path.exists() else {}
        frame_metrics = summary.get("frame_metrics", {}).get("metrics", {}) or {}
        run_entry = {
            "video_name": record["video_name"],
            "phase": record["phase"],
            "iteration_dir": record["iteration_dir"],
            "summary_path": str(summary_path),
            "review_path": str(review_path),
            "overall_score": review.get("overall_score"),
            "blocking_issues": review.get("blocking_issues", []),
            "recommendation": review.get("recommendation"),
            "frame_metrics": frame_metrics,
            "binary_md5": record.get("binary_md5"),
            "model_md5": record.get("model_md5"),
        }
        candidate["runs"].append(run_entry)
        if record["video_name"] in main_video_names and review.get("overall_score") is not None:
            candidate["main_video_scores"].append(float(review["overall_score"]))
            candidate["blocking_issue_count"] += len(review.get("blocking_issues", []))
        for key in ("mean_abs_count_error", "undercount_ratio", "duplicate_pair_rate"):
            value = frame_metrics.get(key)
            if value is not None:
                candidate["metric_accumulator"][key].append(float(value))

    ranked: List[Dict[str, Any]] = []
    for payload in by_candidate.values():
        mean_score = None
        if payload["main_video_scores"]:
            mean_score = sum(payload["main_video_scores"]) / len(payload["main_video_scores"])
        metric_means = {
            key: (sum(values) / len(values) if values else None)
            for key, values in payload["metric_accumulator"].items()
        }
        payload["overall_score_mean_main"] = mean_score
        payload["metric_means"] = metric_means
        ranked.append(payload)

    def sort_key(item: Dict[str, Any]) -> Any:
        score = item["overall_score_mean_main"]
        metric_means = item["metric_means"]
        return (
            -(score if score is not None else -1.0),
            int(item["blocking_issue_count"]),
            float(metric_means["mean_abs_count_error"]) if metric_means["mean_abs_count_error"] is not None else 999.0,
            float(metric_means["undercount_ratio"]) if metric_means["undercount_ratio"] is not None else 999.0,
            float(metric_means["duplicate_pair_rate"]) if metric_means["duplicate_pair_rate"] is not None else 999.0,
        )

    ranked.sort(key=sort_key)
    payload = {
        "run_count": len(runs),
        "candidates": ranked,
    }
    write_json(aggregate_path(campaign_root), payload)
    return payload


def dominant_issue_from_candidates(aggregate: Dict[str, Any], candidate_names: Sequence[str]) -> str:
    miss_score = 0
    duplicate_score = 0
    instability_score = 0
    candidate_set = set(candidate_names)
    for candidate in aggregate.get("candidates", []):
        if candidate.get("candidate_name") not in candidate_set:
            continue
        for run in candidate.get("runs", []):
            review_path = Path(str(run["review_path"]))
            if not review_path.exists():
                continue
            review = load_json(review_path)
            miss_score += len(review.get("misses", []))
            duplicate_score += len(review.get("duplicates", [])) + len(review.get("false_positives", []))
            instability_score += len(review.get("small_target_stability", [])) + len(review.get("special_pose_vehicle", []))
            for blocker in review.get("blocking_issues", []):
                text = str(blocker)
                if "漏检" in text:
                    miss_score += 1
                if "重复" in text or "误检" in text:
                    duplicate_score += 1
                if "闪烁" in text or "不稳定" in text:
                    instability_score += 1
    if miss_score >= duplicate_score and miss_score >= instability_score:
        return "miss"
    if duplicate_score >= instability_score:
        return "duplicate"
    return "instability"


def default_phase0_result_path(campaign_root: Path) -> Path:
    return phase0_dir(campaign_root) / "phase0_runtime_result.json"


def default_prepared_input(video: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "video_name": str(video["name"]),
        "source": video.get("local_path"),
        "prepared_local_path": None,
        "board_input_path": str(video["board_input_path"]),
        "expected_person_count": int(video.get("expected_person_count", 0)),
        "duration_seconds": int(video.get("duration_seconds", 12)),
        "duration_policy": str(video.get("duration_policy", "fixed")),
        "reference_video": video.get("reference_video"),
        "reference_label": video.get("reference_label"),
        "priority": video.get("priority"),
    }


def normalize_prepared_inputs(manifest: Dict[str, Any], raw_inputs: Any) -> Dict[str, Dict[str, Any]]:
    if raw_inputs is None:
        raw_inputs = {}
    if not isinstance(raw_inputs, dict):
        raise SystemExit("phase0 prepared_inputs must be a JSON object keyed by video name")

    prepared: Dict[str, Dict[str, Any]] = {}
    for video in manifest.get("videos", []):
        name = str(video["name"])
        provided = raw_inputs.get(name, {})
        if provided is None:
            provided = {}
        if not isinstance(provided, dict):
            raise SystemExit(f"phase0 prepared_inputs[{name!r}] must be an object")
        merged = {**default_prepared_input(video), **provided}
        merged["video_name"] = name
        board_input_path = str(merged.get("board_input_path") or "").strip()
        if not board_input_path:
            raise SystemExit(f"phase0 prepared_inputs[{name!r}] is missing board_input_path")
        merged["board_input_path"] = board_input_path
        prepared[name] = merged
    return prepared


def load_phase0_result_payload(
    campaign_root: Path,
    manifest: Dict[str, Any],
    args: argparse.Namespace,
) -> Tuple[Path, Dict[str, Any]]:
    result_path = (
        Path(args.phase0_result).expanduser().resolve()
        if getattr(args, "phase0_result", None)
        else default_phase0_result_path(campaign_root)
    )
    if not result_path.exists():
        raise SystemExit(
            "Phase 0 is a runtime collaboration step. "
            f"Write a result JSON to {result_path} or pass --phase0-result."
        )

    payload = load_json(result_path)
    status = str(payload.get("status") or "done")
    checks = payload.get("checks", {})
    if checks is not None and not isinstance(checks, dict):
        raise SystemExit("phase0 checks must be a JSON object")

    package = payload.get("package")
    normalized_package = None
    if isinstance(package, dict) and str(package.get("package_dir") or "").strip():
        package_dir = Path(str(package["package_dir"])).expanduser().resolve()
        if package_dir.exists():
            normalized_package = {**package, "package_dir": str(package_dir)}

    normalized_prepared_inputs = None
    if payload.get("prepared_inputs") is not None:
        normalized_prepared_inputs = normalize_prepared_inputs(manifest, payload.get("prepared_inputs"))

    if status != "done":
        error = str(payload.get("error") or "Phase 0 reported a non-done status")
        return result_path, {
            "status": status,
            "checks": checks or {},
            "error": error,
            "board_preflight": payload.get("board_preflight"),
            "package": normalized_package,
            "prepared_inputs": normalized_prepared_inputs,
            "notes": payload.get("notes", []),
        }

    package = payload.get("package")
    if not isinstance(package, dict):
        raise SystemExit("phase0 result must include package")
    for key in ("package_dir", "binary_md5", "model_md5"):
        if not str(package.get(key) or "").strip():
            raise SystemExit(f"phase0 package is missing {key}")

    package_dir = Path(str(package["package_dir"])).expanduser().resolve()
    if not package_dir.exists():
        raise SystemExit(f"phase0 package_dir does not exist: {package_dir}")

    prepared_inputs = normalize_prepared_inputs(manifest, payload.get("prepared_inputs"))
    normalized_package = {**package, "package_dir": str(package_dir)}
    return result_path, {
        "status": "done",
        "checks": checks or {},
        "package": normalized_package,
        "prepared_inputs": prepared_inputs,
        "board_preflight": payload.get("board_preflight"),
        "notes": payload.get("notes", []),
    }


def phase0(
    campaign_root: Path,
    args: argparse.Namespace,
    state: Dict[str, Any],
) -> None:
    phase0_state = state.setdefault("phase0", {})
    result_path, result = load_phase0_result_payload(campaign_root, state["manifest"], args)
    phase0_state["checks"] = result.get("checks", {})
    phase0_state["runtime_result_path"] = str(result_path)
    phase0_state["source"] = "runtime_import"
    if result.get("status") != "done":
        phase0_state["status"] = str(result.get("status") or "blocked")
        phase0_state["error"] = result.get("error")
        phase0_state["notes"] = result.get("notes", [])
        if result.get("package") is not None:
            state["package"] = result["package"]
        if result.get("prepared_inputs") is not None:
            state["prepared_inputs"] = result["prepared_inputs"]
        if "board_preflight" in result:
            phase0_state["board_preflight"] = result.get("board_preflight")
        save_state(campaign_root, state)
        raise SystemExit(str(result.get("error") or "Phase 0 failed"))

    state["package"] = result["package"]
    state["prepared_inputs"] = result["prepared_inputs"]
    phase0_state["board_preflight"] = result.get("board_preflight")
    phase0_state["notes"] = result.get("notes", [])
    phase0_state["status"] = "done"
    phase0_state.pop("error", None)
    save_state(campaign_root, state)


def phase1(campaign_root: Path, repo_root: Path, args: argparse.Namespace, state: Dict[str, Any]) -> None:
    if state.get("phase0", {}).get("status") != "done":
        raise SystemExit("Phase 0 must complete before Phase 1")
    videos = state["manifest"]["videos"]
    baselines = state["manifest"]["phase1_candidates"]
    existing = {(run["phase"], run["video_name"], run["candidate_name"]) for run in state.get("runs", [])}
    for video in videos:
        for candidate in baselines:
            key = ("phase1", video["name"], candidate["name"])
            if key in existing:
                continue
            payload = state["prepared_inputs"].get(video["name"], {})
            run_record = run_low_level_video(repo_root, campaign_root, args, payload, candidate, "phase1", state["package"])
            state.setdefault("runs", []).append(run_record)
            save_state(campaign_root, state)
    aggregate = aggregate_campaign(campaign_root, state)
    baseline_records = [run for run in state["runs"] if run["phase"] == "phase1"]
    missing = missing_review_paths(baseline_records)
    state["phase1"]["aggregate_summary"] = str(aggregate_path(campaign_root))
    state["phase1"]["status"] = "awaiting_review" if missing else "done"
    if not missing and aggregate.get("candidates"):
        state["phase1"]["default_candidate"] = aggregate["candidates"][0]["candidate_name"]
    save_state(campaign_root, state)
    if missing:
        raise SystemExit("Phase 1 completed runs but is waiting for visual reviews")


def phase2(campaign_root: Path, repo_root: Path, args: argparse.Namespace, state: Dict[str, Any]) -> None:
    phase1_records = [run for run in state["runs"] if run["phase"] == "phase1"]
    missing = missing_review_paths(phase1_records)
    if missing:
        raise SystemExit("Phase 2 requires completed Phase 1 visual reviews")

    phase2_state = state.setdefault("phase2", {})
    main_video_names = main_video_names_set(state["manifest"])
    existing = {(run["phase"], run["video_name"], run["candidate_name"]) for run in state.get("runs", [])}

    if not phase2_state.get("round1_complete"):
        for candidate in state["manifest"]["phase2_round1_candidates"]:
            for video_name, payload in state["prepared_inputs"].items():
                if video_name not in main_video_names:
                    continue
                key = ("phase2_round1", video_name, candidate["name"])
                if key in existing:
                    continue
                run_record = run_low_level_video(repo_root, campaign_root, args, payload, candidate, "phase2_round1", state["package"])
                state.setdefault("runs", []).append(run_record)
                save_state(campaign_root, state)
        phase2_state["round1_complete"] = True
        phase2_state["status"] = "awaiting_round1_review"
        save_state(campaign_root, state)
        aggregate_campaign(campaign_root, state)
        raise SystemExit("Phase 2 round 1 finished; complete visual reviews before rerunning Phase 2")

    round1_records = [run for run in state["runs"] if run["phase"] == "phase2_round1"]
    missing = missing_review_paths(round1_records)
    if missing:
        raise SystemExit("Phase 2 round 1 is waiting for visual reviews")

    aggregate = aggregate_campaign(campaign_root, state)
    if not phase2_state.get("round2_complete"):
        round1_names = [candidate["name"] for candidate in state["manifest"]["phase2_round1_candidates"]]
        issue = dominant_issue_from_candidates(aggregate, round1_names)
        phase2_state["round2_issue"] = issue
        for candidate in state["manifest"]["phase2_round2_candidates"][issue]:
            for video_name, payload in state["prepared_inputs"].items():
                if video_name not in main_video_names:
                    continue
                key = ("phase2_round2", video_name, candidate["name"])
                if key in existing:
                    continue
                run_record = run_low_level_video(repo_root, campaign_root, args, payload, candidate, "phase2_round2", state["package"])
                state.setdefault("runs", []).append(run_record)
                save_state(campaign_root, state)
        phase2_state["round2_complete"] = True
        phase2_state["status"] = "awaiting_round2_review"
        save_state(campaign_root, state)
        aggregate_campaign(campaign_root, state)
        raise SystemExit("Phase 2 round 2 finished; complete visual reviews before rerunning Phase 2")

    round2_records = [run for run in state["runs"] if run["phase"] == "phase2_round2"]
    missing = missing_review_paths(round2_records)
    if missing:
        raise SystemExit("Phase 2 round 2 is waiting for visual reviews")

    aggregate = aggregate_campaign(campaign_root, state)
    if not phase2_state.get("dolls_complete"):
        runtime_candidate_names = {
            item["name"] for item in state["manifest"]["phase2_round1_candidates"]
        }
        runtime_candidate_names.update(
            item["name"] for item in state["manifest"]["phase2_round2_candidates"][phase2_state["round2_issue"]]
        )
        top_candidates = [
            item["candidate_name"]
            for item in aggregate.get("candidates", [])
            if item.get("overall_score_mean_main") is not None and item.get("candidate_name") in runtime_candidate_names
        ][:2]
        dolls_payload = state["prepared_inputs"]["dolls_video.h264"]
        for candidate_name in top_candidates:
            candidate = next(
                (item for item in state["manifest"]["phase2_round1_candidates"] if item["name"] == candidate_name),
                None,
            )
            if candidate is None and phase2_state.get("round2_issue"):
                candidate = next(
                    (
                        item
                        for item in state["manifest"]["phase2_round2_candidates"][phase2_state["round2_issue"]]
                        if item["name"] == candidate_name
                    ),
                    None,
                )
            if candidate is None:
                continue
            key = ("phase2_dolls", "dolls_video.h264", candidate["name"])
            if key in existing:
                continue
            run_record = run_low_level_video(repo_root, campaign_root, args, dolls_payload, candidate, "phase2_dolls", state["package"])
            state.setdefault("runs", []).append(run_record)
            save_state(campaign_root, state)
        phase2_state["dolls_complete"] = True
        phase2_state["status"] = "awaiting_dolls_review"
        save_state(campaign_root, state)
        aggregate_campaign(campaign_root, state)
        raise SystemExit("Phase 2 dolls runs finished; complete visual reviews before rerunning Phase 2")

    dolls_records = [run for run in state["runs"] if run["phase"] == "phase2_dolls"]
    missing = missing_review_paths(dolls_records)
    if missing:
        raise SystemExit("Phase 2 dolls runs are waiting for visual reviews")

    final_aggregate = aggregate_campaign(campaign_root, state)
    ranked = [item for item in final_aggregate.get("candidates", []) if item.get("overall_score_mean_main") is not None]
    best = ranked[0] if ranked else None
    second = ranked[1] if len(ranked) > 1 else None
    score_gap = None
    if best is not None and second is not None:
        score_gap = float(best["overall_score_mean_main"]) - float(second["overall_score_mean_main"])

    phase2_state["status"] = "done"
    phase2_state["best_candidate"] = best.get("candidate_name") if best else None
    phase2_state["best_score_main"] = best.get("overall_score_mean_main") if best else None
    phase2_state["score_gap_vs_next"] = score_gap
    phase2_state["converged"] = bool(
        best is not None
        and float(best.get("overall_score_mean_main") or 0.0) >= 7.0
        and int(best.get("blocking_issue_count") or 0) == 0
    )
    phase2_state["no_significant_improvement"] = bool(score_gap is not None and score_gap < 0.5)
    save_state(campaign_root, state)
    write_json(aggregate_path(campaign_root), final_aggregate)


def phase3_runtime_params(state: Dict[str, Any], args: argparse.Namespace) -> Tuple[str, float, float, int]:
    best_name = state.get("phase2", {}).get("best_candidate")
    if best_name is None:
        raise SystemExit("Phase 3 requires a best runtime candidate from Phase 2")
    chosen = next((run for run in state.get("runs", []) if run["candidate_name"] == best_name), None)
    if chosen is None:
        raise SystemExit("Unable to resolve runtime params for Phase 3")
    phase3_candidates = state.get("phase3", {}).get("candidates", {}) or {}
    pending_label = next(
        (
            name
            for name, payload in phase3_candidates.items()
            if isinstance(payload, dict) and payload.get("status") != "done"
        ),
        None,
    )
    label = args.phase3_label or pending_label or f"phase3_{best_name}"
    score = float(args.phase3_score) if args.phase3_score is not None else float(chosen["score"])
    nms = float(args.phase3_nms) if args.phase3_nms is not None else float(chosen["nms"])
    smooth = int(args.phase3_smooth_window) if args.phase3_smooth_window is not None else int(chosen["smooth_window"])
    return label, score, nms, smooth


def phase3(campaign_root: Path, repo_root: Path, args: argparse.Namespace, state: Dict[str, Any]) -> None:
    label, score, nms, smooth = phase3_runtime_params(state, args)
    phase3_state = state.setdefault("phase3", {})
    candidate_state = phase3_state.setdefault("candidates", {}).setdefault(label, {})
    if candidate_state.get("status") == "done":
        return

    build_args = argparse.Namespace(skip_build=False, reuse_package_dir=None)
    package_info = single.resolve_package_dir(repo_root, phase0_dir(campaign_root) / f"phase3_{label}", build_args)
    candidate_state["package"] = package_info
    candidate_state["runtime_seed_candidate"] = state.get("phase2", {}).get("best_candidate")
    candidate = {
        "name": label,
        "score": score,
        "nms": nms,
        "smooth_window": smooth,
    }
    for video_name in phase3_video_order(state["manifest"]):
        completed_records = [
            run
            for run in state.get("runs", [])
            if run["phase"] == "phase3" and run["candidate_name"] == label
        ]
        blocked_record = next(
            (
                item
                for item in completed_records
                if phase3_video_gate_verdict(item).get("status") != "ready"
            ),
            None,
        )
        if blocked_record is not None:
            blocked_verdict = phase3_video_gate_verdict(blocked_record)
            candidate_state["status"] = "awaiting_review"
            candidate_state["blocking_video"] = blocked_record.get("video_name")
            candidate_state["blocking_gate"] = blocked_verdict
            phase3_state["status"] = "awaiting_review"
            save_state(campaign_root, state)
            aggregate_campaign(campaign_root, state)
            raise SystemExit(
                f"Phase 3 is waiting on {blocked_record.get('video_name')} visual gate "
                f"before running the next video"
            )

        payload = state["prepared_inputs"][video_name]
        existing = next(
            (
                run
                for run in state.get("runs", [])
                if run["phase"] == "phase3" and run["video_name"] == video_name and run["candidate_name"] == label
            ),
            None,
        )
        if existing is not None:
            continue
        run_record = run_low_level_video(repo_root, campaign_root, args, payload, candidate, "phase3", package_info)
        state.setdefault("runs", []).append(run_record)
        save_state(campaign_root, state)
        gate_verdict = phase3_video_gate_verdict(run_record)
        candidate_state["status"] = "awaiting_review"
        candidate_state["blocking_video"] = video_name
        candidate_state["blocking_gate"] = gate_verdict
        phase3_state["status"] = "awaiting_review"
        save_state(campaign_root, state)
        aggregate_campaign(campaign_root, state)
        raise SystemExit(
            f"Phase 3 finished {video_name}; complete runtime/count/visual review and clear blockers before rerunning Phase 3"
        )

    phase3_records = [run for run in state["runs"] if run["phase"] == "phase3" and run["candidate_name"] == label]
    blocked_phase3 = [phase3_video_gate_verdict(run) for run in phase3_records]
    blocked_phase3 = [verdict for verdict in blocked_phase3 if verdict.get("status") != "ready"]
    if blocked_phase3:
        candidate_state["status"] = "awaiting_review"
        candidate_state["blocking_gate"] = blocked_phase3[0]
        phase3_state["status"] = "awaiting_review"
        save_state(campaign_root, state)
        aggregate_campaign(campaign_root, state)
        raise SystemExit("Phase 3 video runs finished; complete runtime/count/visual reviews before rerunning Phase 3")

    gate = run_low_level_batch_gate(repo_root, campaign_root, args, package_info, label)
    candidate_state["gate"] = gate
    candidate_state["status"] = "done"
    candidate_state.pop("blocking_video", None)
    candidate_state.pop("blocking_gate", None)
    phase3_state["status"] = "done"
    save_state(campaign_root, state)
    aggregate_campaign(campaign_root, state)


def reviewed_candidates(aggregate: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [item for item in aggregate.get("candidates", []) if item.get("overall_score_mean_main") is not None]


def phase3_gate_map(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    mapped: Dict[str, Dict[str, Any]] = {}
    for name, payload in state.get("phase3", {}).get("candidates", {}).items():
        mapped[name] = payload.get("gate", {}).get("gate", {}) or {}
    return mapped


def find_best_runtime_candidate(aggregate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for item in reviewed_candidates(aggregate):
        if "phase3" not in item.get("phases", []):
            return item
    return None


def find_best_gate_safe_phase3_candidate(aggregate: Dict[str, Any], state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    gates = phase3_gate_map(state)
    best: Optional[Dict[str, Any]] = None
    for item in reviewed_candidates(aggregate):
        if "phase3" not in item.get("phases", []):
            continue
        gate = gates.get(str(item["candidate_name"]), {})
        if not gate.get("passed"):
            continue
        if best is None or float(item.get("overall_score_mean_main") or 0.0) > float(best.get("overall_score_mean_main") or 0.0):
            best = item
    return best


def select_run_record(state: Dict[str, Any], candidate_name: str, allowed_phases: Sequence[str]) -> Optional[Dict[str, Any]]:
    for run in state.get("runs", []):
        if run["candidate_name"] == candidate_name and run["phase"] in allowed_phases:
            return run
    return None


def build_final_report(campaign_root: Path, state: Dict[str, Any], aggregate: Dict[str, Any]) -> Dict[str, Any]:
    runtime_best = find_best_runtime_candidate(aggregate)
    phase3_best = find_best_gate_safe_phase3_candidate(aggregate, state)
    if runtime_best is None and phase3_best is None:
        raise SystemExit("no reviewed candidates are available for Phase 4")

    selected_from = "phase2"
    best = runtime_best
    if phase3_best is not None and (
        runtime_best is None
        or float(phase3_best.get("overall_score_mean_main") or 0.0) >= float(runtime_best.get("overall_score_mean_main") or 0.0)
    ):
        selected_from = "phase3"
        best = phase3_best
    assert best is not None

    best_name = str(best["candidate_name"])
    allowed_phases = ("phase3",) if selected_from == "phase3" else ("phase1", "phase2_round1", "phase2_round2", "phase2_dolls")
    chosen_run = select_run_record(state, best_name, allowed_phases)
    gate_payload = phase3_gate_map(state).get(best_name) if selected_from == "phase3" else None
    recommended = {
        "selected_from": selected_from,
        "candidate_name": best_name,
        "score": chosen_run.get("score") if chosen_run else None,
        "nms": chosen_run.get("nms") if chosen_run else None,
        "smooth_window": chosen_run.get("smooth_window") if chosen_run else None,
        "binary_md5": chosen_run.get("binary_md5") if chosen_run else None,
        "model_md5": chosen_run.get("model_md5") if chosen_run else None,
        "batch_gate": gate_payload,
        "avg_overall_score_main": best.get("overall_score_mean_main"),
        "blocking_issue_count": best.get("blocking_issue_count"),
    }
    write_json(campaign_root / "recommended_params.json", recommended)

    best_runs = {run["video_name"]: run for run in best.get("runs", [])}
    main_video_names = high_priority_video_names(state["manifest"])
    lines = [
        f"# {campaign_root.name}",
        "",
        "## Selection",
        f"- selected_from: `{selected_from}`",
        f"- candidate: `{best_name}`",
        f"- score: `{recommended['score']}`",
        f"- nms: `{recommended['nms']}`",
        f"- smooth_window: `{recommended['smooth_window']}`",
        f"- binary_md5: `{recommended['binary_md5']}`",
        f"- model_md5: `{recommended['model_md5']}`",
        f"- avg_overall_score_main: `{best.get('overall_score_mean_main')}`",
        f"- blocking_issue_count: `{best.get('blocking_issue_count')}`",
        "",
        "## Main Videos",
    ]
    for video_name in main_video_names:
        run = best_runs.get(video_name)
        if not run:
            continue
        review = load_json(Path(str(run["review_path"])))
        lines.extend(
            [
                f"- {video_name}_iteration: `{run['iteration_dir']}`",
                f"- {video_name}_summary: `{run['summary_path']}`",
                f"- {video_name}_review: `{run['review_path']}`",
                f"- {video_name}_overall_score: `{review.get('overall_score')}`",
                f"- {video_name}_blocking_issues: `{review.get('blocking_issues', [])}`",
                f"- {video_name}_recommendation: `{review.get('recommendation')}`",
            ]
        )
    if "dolls_video.h264" in best_runs:
        run = best_runs["dolls_video.h264"]
        review = load_json(Path(str(run["review_path"])))
        lines.extend(
            [
                "",
                "## Dolls Reference",
                f"- dolls_iteration: `{run['iteration_dir']}`",
                f"- dolls_summary: `{run['summary_path']}`",
                f"- dolls_review: `{run['review_path']}`",
                f"- dolls_overall_score: `{review.get('overall_score')}`",
                f"- dolls_blocking_issues: `{review.get('blocking_issues', [])}`",
            ]
        )
    lines.extend(["", "## Gate"])
    if gate_payload:
        lines.append(f"- gate_passed: `{gate_payload.get('passed')}`")
        lines.append(f"- gate_measured: `{gate_payload.get('measured')}`")
    else:
        lines.append("- gate_passed: `not_run_or_not_required`")
    lines.extend(["", "## Next"])
    if float(best.get("overall_score_mean_main") or 0.0) >= 7.0 and int(best.get("blocking_issue_count") or 0) == 0:
        lines.append(f"- Main target met on {'/'.join(main_video_names)}.")
    elif selected_from == "phase3" and gate_payload and not gate_payload.get("passed"):
        lines.append("- Phase 3 visual result improved but failed the batch gate; keep the runtime candidate as the safe fallback.")
    else:
        lines.append("- Runtime and postprocess tuning are still below target; next step is model/data improvement or crowd-specific fine-tune.")
    write_text(campaign_root / "final_report.md", "\n".join(lines) + "\n")
    return recommended


def phase4(campaign_root: Path, state: Dict[str, Any]) -> None:
    aggregate = aggregate_campaign(campaign_root, state)
    build_final_report(campaign_root, state, aggregate)
    state.setdefault("phase4", {})["status"] = "done"
    save_state(campaign_root, state)


def should_run_phase3(state: Dict[str, Any], requested_phase: str) -> bool:
    if requested_phase == "phase3":
        return True
    if requested_phase != "all":
        return False
    phase2_state = state.get("phase2", {})
    if phase2_state.get("status") != "done":
        return False
    return not bool(phase2_state.get("converged"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Thin video optimization phase orchestrator")
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
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--phase", choices=["phase0", "phase1", "phase2", "phase3", "phase4", "all"], default="all")
    parser.add_argument(
        "--phase0-result",
        default=None,
        help="runtime-generated Phase 0 JSON; defaults to phase0/phase0_runtime_result.json under the campaign directory",
    )
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--reuse-package-dir", default=None)
    parser.add_argument("--phase3-label", default=None)
    parser.add_argument("--phase3-score", type=float, default=None)
    parser.add_argument("--phase3-nms", type=float, default=None)
    parser.add_argument("--phase3-smooth-window", type=int, default=None)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    manifest = load_manifest(repo_root, args.manifest)
    campaign_root = campaign_dir(repo_root, args.campaign_id)
    ensure_campaign_layout(campaign_root, manifest)
    state = load_or_init_state(campaign_root, manifest)

    if args.phase in {"phase0", "all"} and state.get("phase0", {}).get("status") != "done":
        phase0(campaign_root, args, state)
        state = load_or_init_state(campaign_root, manifest)

    if args.phase in {"phase1", "all"} and state.get("phase1", {}).get("status") != "done":
        phase1(campaign_root, repo_root, args, state)
        state = load_or_init_state(campaign_root, manifest)

    if args.phase in {"phase2", "all"} and state.get("phase2", {}).get("status") != "done":
        phase2(campaign_root, repo_root, args, state)
        state = load_or_init_state(campaign_root, manifest)

    if should_run_phase3(state, args.phase):
        phase3(campaign_root, repo_root, args, state)
        state = load_or_init_state(campaign_root, manifest)

    if args.phase in {"phase4", "all"}:
        phase4(campaign_root, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
