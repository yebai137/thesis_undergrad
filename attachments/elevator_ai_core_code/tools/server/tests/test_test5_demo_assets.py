import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "test5_demo_assets.py"
    spec = importlib.util.spec_from_file_location("test5_demo_assets", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()
BOARD_RUNNER = Path(__file__).resolve().parents[3] / "board" / "scripts" / "run_test5_demo_once.sh"


class Test5DemoAssetsTests(unittest.TestCase):
    def test_build_candidate_record_collects_key_iteration_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            iter_dir = Path(tmpdir) / "iter_22"
            analysis_dir = iter_dir / "analysis"
            analysis_dir.mkdir(parents=True)

            (analysis_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "video": {"label": "test5"},
                        "review_timeline": {"duration_seconds": 14.58},
                    }
                ),
                encoding="utf-8",
            )
            (analysis_dir / "review_pack.json").write_text(
                json.dumps(
                    {
                        "primary_review_artifact": str(analysis_dir / "preview_clean_h264.mp4"),
                        "clean": {"preview_video_h264": str(analysis_dir / "preview_clean_h264.mp4")},
                        "public": {"preview_video_h264": str(analysis_dir / "preview_public_h264.mp4")},
                    }
                ),
                encoding="utf-8",
            )
            (analysis_dir / "visual_review.json").write_text(
                json.dumps(
                    {
                        "status": "ready",
                        "recommendation": "keep_as_experiment",
                        "sections": {
                            "ebike_visibility": {
                                "status": "blocker",
                                "summary": "public ebike disappears for long stretches",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            (analysis_dir / "ebike_false_alarm_summary.json").write_text(
                json.dumps(
                    {
                        "frames_with_public_ebike": 27,
                        "frames_with_confirmed_public_gap": 318,
                    }
                ),
                encoding="utf-8",
            )

            record = MODULE.build_candidate_record(
                iter_dir,
                candidate_id="phase3_1_iter22",
                narrative="early_general_effect",
                note="long public ebike gap",
            )

        self.assertEqual(record["candidate_id"], "phase3_1_iter22")
        self.assertEqual(record["video_label"], "test5")
        self.assertEqual(record["narrative"], "early_general_effect")
        self.assertEqual(record["public_gap_frames"], 318)
        self.assertEqual(record["ebike_visibility_status"], "blocker")
        self.assertTrue(record["clean_preview_path"].endswith("preview_clean_h264.mp4"))
        self.assertTrue(record["public_preview_path"].endswith("preview_public_h264.mp4"))
        self.assertIsNone(record["source_fps"])
        self.assertIsNone(record["source_frame_count"])

    def test_build_candidate_record_prefers_local_preview_when_review_pack_uses_windows_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            iter_dir = Path(tmpdir) / "iter_30"
            analysis_dir = iter_dir / "analysis"
            analysis_dir.mkdir(parents=True)

            (analysis_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "video": {"label": "test5_auto_prepare", "frame_count": 165, "fps": 25.0},
                    }
                ),
                encoding="utf-8",
            )
            (analysis_dir / "preview_clean.mp4").write_text("stub", encoding="utf-8")
            (analysis_dir / "preview_public.mp4").write_text("stub", encoding="utf-8")
            (analysis_dir / "review_pack.json").write_text(
                json.dumps(
                    {
                        "primary_review_artifact": "D:/elevator_ai/elevator_ai/logs/direct_runs/iter_30/analysis/preview_clean.mp4",
                        "clean": {"preview_video": "D:/elevator_ai/elevator_ai/logs/direct_runs/iter_30/analysis/preview_clean.mp4"},
                        "public": {"preview_video": "D:/elevator_ai/elevator_ai/logs/direct_runs/iter_30/analysis/preview_public.mp4"},
                    }
                ),
                encoding="utf-8",
            )

            record = MODULE.build_candidate_record(
                iter_dir,
                candidate_id="wave2c_iter30",
                narrative="later_contrast_candidate",
                note="local path fallback",
            )

        self.assertTrue(record["clean_preview_path"].endswith("analysis/preview_clean.mp4"))
        self.assertTrue(record["public_preview_path"].endswith("analysis/preview_public.mp4"))
        self.assertEqual(record["duration_seconds"], 6.6)

    def test_build_candidate_record_prefers_local_preview_when_review_pack_uses_backslash_windows_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            iter_dir = Path(tmpdir) / "iter_16"
            analysis_dir = iter_dir / "analysis"
            analysis_dir.mkdir(parents=True)

            (analysis_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "video": {"label": "test5_wave2c_dd2a", "frame_count": 174, "fps": 25.0},
                    }
                ),
                encoding="utf-8",
            )
            (analysis_dir / "preview_clean.mp4").write_text("stub", encoding="utf-8")
            (analysis_dir / "review_pack.json").write_text(
                json.dumps(
                    {
                        "primary_review_artifact": "D:\\elevator_ai\\elevator_ai\\logs\\direct_runs\\20260402_wave2c\\iter_16\\analysis\\preview_clean.mp4",
                        "clean": {"preview_video": "D:\\elevator_ai\\elevator_ai\\logs\\direct_runs\\20260402_wave2c\\iter_16\\analysis\\preview_clean.mp4"},
                    }
                ),
                encoding="utf-8",
            )

            record = MODULE.build_candidate_record(
                iter_dir,
                candidate_id="wave2c_iter16",
                narrative="early_general_effect",
                note="local path fallback for backslash windows path",
            )

        self.assertTrue(record["clean_preview_path"].endswith("analysis/preview_clean.mp4"))
        self.assertEqual(record["duration_seconds"], 6.96)

    def test_render_candidate_markdown_lists_paths_and_notes(self):
        markdown = MODULE.render_candidate_markdown(
            [
                {
                    "candidate_id": "wave2c_iter16",
                    "iteration_dir": "/repo/logs/direct_runs/20260402_wave2c/iter_16",
                    "video_label": "test5_wave2c_dd2a",
                    "narrative": "early_general_effect",
                    "note": "early look, sparse but believable ebike frames",
                    "clean_preview_path": "/repo/logs/direct_runs/20260402_wave2c/iter_16/analysis/preview_clean.mp4",
                    "public_preview_path": "/repo/logs/direct_runs/20260402_wave2c/iter_16/analysis/preview_public_h264.mp4",
                    "visual_review_path": "/repo/logs/direct_runs/20260402_wave2c/iter_16/analysis/visual_review.json",
                    "review_recommendation": "pending",
                    "ebike_visibility_status": "unknown",
                    "public_gap_frames": None,
                    "duration_seconds": 6.92,
                }
            ],
            generated_at="2026-04-19T23:59:59Z",
        )

        self.assertIn("wave2c_iter16", markdown)
        self.assertIn("early_general_effect", markdown)
        self.assertIn("/repo/logs/direct_runs/20260402_wave2c/iter_16/analysis/preview_clean.mp4", markdown)
        self.assertIn("early look, sparse but believable ebike frames", markdown)

    def test_build_board_demo_command_supports_hdmi_and_rtsp_modes(self):
        profile = {
            "candidate_id": "test5_clean",
            "board_input_path": "/root/data/demo_inputs/test5_iter30.h264",
            "surface": "clean",
            "timing": "source",
            "single_shot": True,
            "source_fps": 30.0,
            "source_frame_count": 437,
            "duration_seconds": 14.566667,
            "output_dir": "/root/direct_video_metrics_test5_clean",
            "score": 0.15,
            "nms": 0.45,
            "smooth_window": 5,
        }

        hdmi_command = MODULE.build_board_demo_command(
            "/root/elevator_ai/elevator_yolo",
            "/root/elevator_ai/yolov8.om",
            profile,
            output_mode="hdmi",
        )
        rtsp_command = MODULE.build_board_demo_command(
            "/root/elevator_ai/elevator_yolo",
            "/root/elevator_ai/yolov8.om",
            profile,
            output_mode="rtsp",
            rtsp_port=8555,
        )

        self.assertIn("/root/elevator_ai/elevator_yolo file", hdmi_command)
        self.assertIn("--surface clean", hdmi_command)
        self.assertIn("--timing source", hdmi_command)
        self.assertIn("--single-shot", hdmi_command)
        self.assertIn("--source-fps 30.0", hdmi_command)
        self.assertIn("--source-frame-count 437", hdmi_command)
        self.assertIn("--source-duration-ms 14567", hdmi_command)
        self.assertIn("--output-dir /root/direct_video_metrics_test5_clean", hdmi_command)
        self.assertIn("--rtsp-port 8555", rtsp_command)
        self.assertIn("--input /root/data/demo_inputs/test5_iter30.h264", rtsp_command)

    def test_build_demo_manifest_preserves_surface_and_source_timing_metadata(self):
        manifest = MODULE.build_demo_manifest(
            [
                {
                    "candidate_id": "test5_clean",
                    "board_input_path": "/root/data/optimization_inputs/test5_annexb_repeat_headers_no_sei.h264",
                    "surface": "clean",
                    "timing": "source",
                    "single_shot": True,
                    "source_fps": 30.0,
                    "source_frame_count": 437,
                    "duration_seconds": 14.566667,
                }
            ],
            generated_at="2026-04-20T00:00:00Z",
        )

        self.assertEqual(
            manifest["profiles"][0]["surface"],
            "clean",
        )
        self.assertEqual(manifest["profiles"][0]["timing"], "source")
        self.assertTrue(manifest["profiles"][0]["single_shot"])
        self.assertEqual(manifest["profiles"][0]["source_fps"], 30.0)
        self.assertEqual(manifest["profiles"][0]["source_frame_count"], 437)

    def test_build_board_demo_command_uses_board_native_review_surface_for_hdmi_and_rtsp(self):
        profile = {
            "candidate_id": "test5_debug",
            "board_input_path": "/root/data/optimization_inputs/test5_annexb_repeat_headers_no_sei.h264",
            "surface": "debug",
            "timing": "source",
            "single_shot": True,
            "source_fps": 30.0,
            "source_frame_count": 437,
            "duration_seconds": 14.566667,
            "output_dir": "/root/direct_video_metrics_test5_debug",
            "score": 0.15,
            "nms": 0.45,
            "smooth_window": 5,
        }

        hdmi_command = MODULE.build_board_demo_command(
            "/root/elevator_ai/elevator_yolo",
            "/root/elevator_ai/yolov8.om",
            profile,
            output_mode="hdmi",
        )
        rtsp_command = MODULE.build_board_demo_command(
            "/root/elevator_ai/elevator_yolo",
            "/root/elevator_ai/yolov8.om",
            profile,
            output_mode="rtsp",
            rtsp_port=8555,
        )

        self.assertIn("--surface debug", hdmi_command)
        self.assertIn("--surface debug", rtsp_command)
        self.assertIn("--timing source", hdmi_command)
        self.assertIn("--single-shot", hdmi_command)
        self.assertIn("--output-dir /root/direct_video_metrics_test5_debug", hdmi_command)
        self.assertIn("--source-fps 30.0", hdmi_command)
        self.assertIn("--input /root/data/optimization_inputs/test5_annexb_repeat_headers_no_sei.h264", rtsp_command)
        self.assertNotIn("/root/sample_vdec", hdmi_command)

    def test_board_runner_is_posix_sh_compatible(self):
        first_line = BOARD_RUNNER.read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(first_line, "#!/bin/sh")

        result = subprocess.run(
            ["sh", str(BOARD_RUNNER), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("--vo-intf-type mipi|bt1120", result.stdout)

    def test_board_runner_dry_run_does_not_require_python_on_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_dir = Path(tmpdir)
            dirname_path = shutil.which("dirname") or "/usr/bin/dirname"
            (bin_dir / "dirname").symlink_to(dirname_path)

            env = os.environ.copy()
            env["PATH"] = str(bin_dir)
            env.pop("PYTHON_BIN", None)

            result = subprocess.run(
                ["/bin/sh", str(BOARD_RUNNER), "--profile", "test5_clean", "--dry-run"],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("/root/elevator_ai/elevator_yolo file", result.stdout)
        self.assertIn("--surface clean", result.stdout)
        self.assertIn("--timing source", result.stdout)
        self.assertIn("--single-shot", result.stdout)
        self.assertIn("--source-frame-count 437", result.stdout)
        self.assertIn("killall -9 sample_vdec elevator_yolo sample_vo 2>/dev/null || true", result.stdout)

    def test_board_runner_dry_run_supports_debug_profile(self):
        result = subprocess.run(
            ["/bin/sh", str(BOARD_RUNNER), "--profile", "test5_debug", "--dry-run"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("/root/elevator_ai/elevator_yolo file", result.stdout)
        self.assertIn("--surface debug", result.stdout)
        self.assertIn("--timing source", result.stdout)


if __name__ == "__main__":
    unittest.main()
