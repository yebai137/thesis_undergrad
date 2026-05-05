import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "run_video_optimization_campaign.py"
    spec = importlib.util.spec_from_file_location("run_video_optimization_campaign", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()
REPO_ROOT = Path(__file__).resolve().parents[3]


class RunVideoOptimizationCampaignTests(unittest.TestCase):
    @staticmethod
    def _write_phase3_gate_iteration(
        iter_dir: Path,
        *,
        blocker: bool = False,
        runtime_status: str = "ready",
        count_status: str = "ready",
        target_met: bool = True,
    ) -> dict:
        analysis_dir = iter_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)

        raw_h264 = analysis_dir / "raw_output_review_h264.mp4"
        clean_h264 = analysis_dir / "preview_clean_h264.mp4"
        public_h264 = analysis_dir / "preview_public_h264.mp4"
        debug_h264 = analysis_dir / "preview_debug_h264.mp4"
        for artifact in (raw_h264, clean_h264, public_h264, debug_h264):
            artifact.write_bytes(b"mp4")

        finding_summary = "visible blocker" if blocker else "minor caveat"
        review_payload = {
            "review_schema_version": 3,
            "status": "ready",
            "inputs": {
                "review_pack_json": str(analysis_dir / "review_pack.json"),
                "primary_review_artifact": str(clean_h264),
            },
            "review_method": {
                "protocol": "video_primary_with_still_navigation",
                "full_video_watched": {"clean": True, "public": True},
                "diagnostic_video_reviewed": {"debug": True, "raw": True},
                "still_artifacts_used": [str(analysis_dir / "issue_windows" / "clean" / "issue_001.jpg")],
                "still_only_verdict": False,
            },
            "surface_verdicts": {
                "clean": {
                    "status": "blocker" if blocker else "caveat",
                    "summary": finding_summary,
                    "evidence_paths": [str(clean_h264)],
                },
                "public": {
                    "status": "blocker" if blocker else "caveat",
                    "summary": finding_summary,
                    "evidence_paths": [str(public_h264)],
                },
            },
            "sections": {
                "person_stability": {
                    "status": "blocker" if blocker else "caveat",
                    "summary": finding_summary,
                    "evidence_paths": [str(clean_h264)],
                },
                "ebike_visibility": {
                    "status": "pass",
                    "summary": "ok",
                    "evidence_paths": [str(clean_h264)],
                },
                "public_debug_consistency": {
                    "status": "pass",
                    "summary": "ok",
                    "evidence_paths": [str(debug_h264)],
                },
                "counting": {
                    "status": "pass",
                    "summary": "ok",
                    "evidence_paths": [str(analysis_dir / "count_accuracy_summary.json")],
                },
            },
            "findings": [
                {
                    "surfaces": ["clean", "public"],
                    "category": "person_flash" if blocker else "visual_caveat",
                    "severity": "blocker" if blocker else "caveat",
                    "start_timestamp_sec": 1.0,
                    "end_timestamp_sec": 2.0,
                    "summary": finding_summary,
                    "evidence_paths": [str(clean_h264)],
                }
            ],
            "blocking_issues": [finding_summary] if blocker else [],
            "overall_score": 8.2,
            "recommendation": "keep_as_experiment",
        }
        (analysis_dir / "visual_review.json").write_text(
            json.dumps(review_payload),
            encoding="utf-8",
        )
        (analysis_dir / "runtime_fidelity_summary.json").write_text(
            json.dumps({"status": runtime_status}),
            encoding="utf-8",
        )
        (analysis_dir / "count_accuracy_summary.json").write_text(
            json.dumps(
                {
                    "status": count_status,
                    "target_met": target_met,
                    "track_count_accuracy": 0.95 if target_met else 0.72,
                }
            ),
            encoding="utf-8",
        )
        (analysis_dir / "review_pack.json").write_text(
            json.dumps(
                {
                    "primary_review_artifact": str(clean_h264),
                    "raw": {"review_video_h264": str(raw_h264)},
                    "clean": {"preview_video_h264": str(clean_h264)},
                    "public": {"preview_video_h264": str(public_h264)},
                    "debug": {"preview_video_h264": str(debug_h264)},
                }
            ),
            encoding="utf-8",
        )
        return {
            "iteration_dir": str(iter_dir),
            "review_path": str(analysis_dir / "visual_review.json"),
            "video_name": "test6",
        }

    def test_default_manifest_includes_test6_as_high_priority_video(self):
        manifest = MODULE.default_manifest(REPO_ROOT)
        videos_by_name = {item["name"]: item for item in manifest["videos"]}

        self.assertIn("test6", videos_by_name)
        self.assertEqual(videos_by_name["test6"]["priority"], "high")
        self.assertEqual(
            videos_by_name["test6"]["local_path"],
            str((REPO_ROOT.parent / "test6.mp4").resolve()),
        )
        self.assertEqual(
            videos_by_name["test6"]["board_input_path"],
            "/root/data/optimization_inputs/test6.h264",
        )
        self.assertEqual(videos_by_name["test6"]["expected_person_count"], 0)
        self.assertEqual(videos_by_name["test6"]["duration_policy"], "source-full")

    def test_default_manifest_uses_source_full_for_fixed_review_set(self):
        manifest = MODULE.default_manifest(REPO_ROOT)
        videos_by_name = {item["name"]: item for item in manifest["videos"]}

        for video_name in ("test6", "test3", "test2", "test5"):
            self.assertEqual(videos_by_name[video_name]["duration_policy"], "source-full")

    def test_default_prepared_input_carries_duration_policy_and_source_path(self):
        manifest = MODULE.default_manifest(REPO_ROOT)
        test6 = next(item for item in manifest["videos"] if item["name"] == "test6")

        prepared = MODULE.default_prepared_input(test6)

        self.assertEqual(prepared["duration_policy"], "source-full")
        self.assertEqual(prepared["source"], test6["local_path"])

    def test_phase3_video_order_reviews_test6_first(self):
        manifest = MODULE.default_manifest(REPO_ROOT)

        self.assertEqual(
            MODULE.phase3_video_order(manifest)[:4],
            ["test6", "test3", "test5", "test2"],
        )

    def test_missing_review_paths_treats_invalid_ready_review_as_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            analysis_dir = Path(tmpdir) / "analysis"
            analysis_dir.mkdir(parents=True)
            review_path = analysis_dir / "visual_review.json"
            review_path.write_text(
                json.dumps(
                    {
                        "review_schema_version": 3,
                        "status": "ready",
                        "sections": {},
                        "findings": [],
                        "blocking_issues": [],
                        "recommendation": "keep_as_experiment",
                    }
                ),
                encoding="utf-8",
            )

            missing = MODULE.missing_review_paths([{"review_path": str(review_path)}])

            self.assertEqual(missing, [str(review_path)])

    def test_phase3_video_gate_verdict_blocks_visual_blocker_reviews(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            record = self._write_phase3_gate_iteration(Path(tmpdir) / "iter_01", blocker=True)

            verdict = MODULE.phase3_video_gate_verdict(record)

            self.assertEqual(verdict["status"], "blocked")
            self.assertIn("visual_blockers_present", verdict["issues"])

    def test_phase3_video_gate_verdict_blocks_count_or_fidelity_regressions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            record = self._write_phase3_gate_iteration(
                Path(tmpdir) / "iter_01",
                runtime_status="blocked",
                target_met=False,
            )

            verdict = MODULE.phase3_video_gate_verdict(record)

            self.assertEqual(verdict["status"], "blocked")
            self.assertIn("runtime_fidelity_not_ready", verdict["issues"])
            self.assertIn("count_accuracy_below_threshold", verdict["issues"])

    def test_phase3_video_gate_verdict_accepts_complete_blocker_free_iteration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            record = self._write_phase3_gate_iteration(Path(tmpdir) / "iter_01", blocker=False)

            verdict = MODULE.phase3_video_gate_verdict(record)

            self.assertEqual(verdict["status"], "ready")
            self.assertEqual(verdict["issues"], [])


if __name__ == "__main__":
    unittest.main()
