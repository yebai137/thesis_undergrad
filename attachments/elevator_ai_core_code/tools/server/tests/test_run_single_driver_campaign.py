import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "run_single_driver_campaign.py"
    spec = importlib.util.spec_from_file_location("run_single_driver_campaign", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


class RunSingleDriverCampaignTests(unittest.TestCase):
    @staticmethod
    def _write_h264_nals(path: Path, nal_types):
        data = bytearray()
        for nal_type in nal_types:
            data.extend(b"\x00\x00\x00\x01")
            data.append(0x60 | int(nal_type))
            data.extend(b"\x88\x84")
        path.write_bytes(bytes(data))

    def test_default_dataset_root_uses_verified_gate_staging_path(self):
        self.assertEqual(MODULE.FULL_DATASET_ROOT, "/tmp/personAndEbike_gate")

    def test_review_acceptance_metadata_marks_test6_high_priority(self):
        metadata = MODULE.build_review_acceptance_metadata("test6")

        self.assertEqual(metadata["review_priority"], "high")
        self.assertEqual(
            metadata["recommendation_values"],
            ["pending", "promote", "keep_as_experiment", "reject"],
        )
        self.assertEqual(
            metadata["acceptance_order"],
            ["safety", "count", "visual", "gate_resources"],
        )

    def test_parse_ffmpeg_metadata_extracts_duration_codec_resolution_and_fps(self):
        stderr = """
Input #0, mov,mp4,m4a,3gp,3g2,mj2, from '/home/ywj/test6.mp4':
  Duration: 00:00:40.31, start: 0.000000, bitrate: 7811 kb/s
  Stream #0:0[0x1](und): Video: h264 (Main), yuv420p(tv), 1280x720, 7652 kb/s, 30 fps, 30 tbr
"""

        metadata = MODULE.parse_ffmpeg_video_metadata(stderr, Path("/home/ywj/test6.mp4"))

        self.assertEqual(metadata["source_path"], "/home/ywj/test6.mp4")
        self.assertAlmostEqual(metadata["duration_seconds"], 40.31, places=2)
        self.assertEqual(metadata["video_codec"], "h264")
        self.assertEqual(metadata["width"], 1280)
        self.assertEqual(metadata["height"], 720)
        self.assertEqual(metadata["fps"], 30.0)

    def test_source_full_timeout_uses_source_duration_with_margin(self):
        self.assertEqual(MODULE.source_full_timeout_seconds({"duration_seconds": 40.31}), 56)

    def test_source_full_watchdog_uses_frame_count_when_board_processing_is_slower_than_realtime(self):
        self.assertEqual(
            MODULE.source_full_watchdog_seconds(
                {"duration_seconds": 40.31},
                {"frame_count": 1209, "fps": 30.0},
            ),
            333,
        )

    def test_resolve_video_duration_uses_source_full_policy(self):
        args = type(
            "Args",
            (),
            {
                "duration_policy": "source-full",
                "duration_seconds": 12,
            },
        )()

        self.assertEqual(
            MODULE.resolve_video_duration_seconds(args, {"duration_seconds": 13.31}),
            22,
        )

    def test_resolve_video_duration_keeps_fixed_policy_compatible(self):
        args = type(
            "Args",
            (),
            {
                "duration_policy": "fixed",
                "duration_seconds": 12,
            },
        )()

        self.assertEqual(
            MODULE.resolve_video_duration_seconds(args, {"duration_seconds": 40.31}),
            12,
        )

    def test_scan_h264_nal_types_detects_early_sei_before_idr(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.h264"
            self._write_h264_nals(path, [7, 8, 6, 5])

            preflight = MODULE.validate_prepared_h264_bitstream(path)

            self.assertEqual(preflight["status"], "blocked")
            self.assertIn("early_sei_before_idr", preflight["errors"])
            self.assertEqual(preflight["nal_unit_types"][:4], [7, 8, 6, 5])

    def test_scan_h264_nal_types_accepts_sps_pps_idr_without_early_sei(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "good.h264"
            self._write_h264_nals(path, [7, 8, 5])

            preflight = MODULE.validate_prepared_h264_bitstream(path)

            self.assertEqual(preflight["status"], "ready")
            self.assertEqual(preflight["errors"], [])
            self.assertEqual(preflight["nal_unit_types"][:3], [7, 8, 5])

    def test_prepare_local_board_input_copy_first_strips_sei_for_board_compatible_h264_mp4(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            iter_dir = Path(tmpdir) / "iter_01"
            iter_dir.mkdir()
            source = Path(tmpdir) / "test6.mp4"
            source.write_bytes(b"fake mp4")
            calls = []
            original_discover = MODULE.discover_ffmpeg_path
            original_probe = MODULE.probe_video_stream_metadata
            original_run_local = MODULE.run_local

            def fake_probe(path, iter_dir=None, prefix="media"):
                return {
                    "source_path": str(path),
                    "codec_name": "h264",
                    "profile": "Main",
                    "pix_fmt": "yuv420p",
                    "width": 1280,
                    "height": 720,
                    "fps": 30.0,
                    "has_b_frames": 0,
                    "level": 42,
                    "duration_seconds": 40.31,
                    "frame_count": 1209,
                }

            def fake_run_local(args, **kwargs):
                calls.append(args)
                output = Path(args[-1])
                self._write_h264_nals(output, [7, 8, 5])
                return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

            try:
                MODULE.discover_ffmpeg_path = lambda: "/usr/bin/ffmpeg"
                MODULE.probe_video_stream_metadata = fake_probe
                MODULE.run_local = fake_run_local

                prepared = MODULE.prepare_local_board_input(source, iter_dir)
            finally:
                MODULE.discover_ffmpeg_path = original_discover
                MODULE.probe_video_stream_metadata = original_probe
                MODULE.run_local = original_run_local

            self.assertEqual(prepared.name, "test6_annexb_repeat_headers_no_sei.h264")
            self.assertTrue(prepared.exists())
            self.assertEqual(calls[0][calls[0].index("-c:v") + 1], "copy")
            self.assertIn("h264_mp4toannexb,dump_extra=freq=keyframe,filter_units=remove_types=6", calls[0])
            report = json.loads((iter_dir / "prepared_input_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["strategy"], "copy_annexb_repeat_headers_no_sei")
            self.assertEqual(report["preflight"]["status"], "ready")

    def test_prepare_local_board_input_reencodes_incompatible_sources_with_sei_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            iter_dir = Path(tmpdir) / "iter_01"
            iter_dir.mkdir()
            source = Path(tmpdir) / "test6.mp4"
            source.write_bytes(b"fake mp4")
            calls = []
            original_discover = MODULE.discover_ffmpeg_path
            original_probe = MODULE.probe_video_stream_metadata
            original_run_local = MODULE.run_local

            def fake_probe(path, iter_dir=None, prefix="media"):
                return {
                    "source_path": str(path),
                    "codec_name": "h264",
                    "profile": "Main",
                    "pix_fmt": "yuv420p",
                    "width": 1280,
                    "height": 720,
                    "fps": 30.0,
                    "has_b_frames": 2,
                    "level": 42,
                }

            def fake_run_local(args, **kwargs):
                calls.append(args)
                output = Path(args[-1])
                self._write_h264_nals(output, [7, 8, 5])
                return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

            try:
                MODULE.discover_ffmpeg_path = lambda: "/usr/bin/ffmpeg"
                MODULE.probe_video_stream_metadata = fake_probe
                MODULE.run_local = fake_run_local

                prepared = MODULE.prepare_local_board_input(source, iter_dir)
            finally:
                MODULE.discover_ffmpeg_path = original_discover
                MODULE.probe_video_stream_metadata = original_probe
                MODULE.run_local = original_run_local

            self.assertEqual(prepared.name, "test6_main_nob_no_sei.h264")
            self.assertEqual(calls[0][calls[0].index("-c:v") + 1], "libx264")
            self.assertEqual(calls[0][calls[0].index("-level:v") + 1], "4.2")
            self.assertIn("filter_units=remove_types=6", calls[0])
            report = json.loads((iter_dir / "prepared_input_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["strategy"], "reencode_main_nob_no_sei")
            self.assertEqual(report["preflight"]["status"], "ready")

    def test_build_prepared_input_metadata_carries_strategy_and_preflight(self):
        base = {"status": "ready", "duration_seconds": None, "file_size_bytes": 1234}
        report = {
            "strategy": "copy_annexb_repeat_headers_no_sei",
            "source_stream_metadata": {"codec_name": "h264", "has_b_frames": 0},
            "preflight": {"status": "ready", "errors": [], "nal_unit_types": [7, 8, 5]},
        }

        metadata = MODULE.build_prepared_input_metadata(base, report)

        self.assertEqual(metadata["prepare_strategy"], "copy_annexb_repeat_headers_no_sei")
        self.assertEqual(metadata["preflight_status"], "ready")
        self.assertEqual(metadata["preflight_errors"], [])
        self.assertEqual(metadata["nal_unit_types"], [7, 8, 5])
        self.assertEqual(metadata["source_stream_metadata"]["codec_name"], "h264")

    def test_build_prepared_input_metadata_prefers_source_stream_timing_for_raw_h264(self):
        base = {"status": "ready", "duration_seconds": None, "fps": 25.0, "frame_count": None}
        report = {
            "strategy": "copy_annexb_repeat_headers_no_sei",
            "source_stream_metadata": {
                "duration_seconds": 40.31,
                "fps": 30.0,
                "frame_count": 1209,
                "width": 1280,
                "height": 720,
            },
            "preflight": {"status": "ready", "errors": [], "nal_unit_types": [7, 8, 5]},
        }

        metadata = MODULE.build_prepared_input_metadata(base, report)

        self.assertAlmostEqual(metadata["duration_seconds"], 40.31, places=2)
        self.assertEqual(metadata["fps"], 30.0)
        self.assertEqual(metadata["frame_count"], 1209)

    def test_discover_ffmpeg_prefers_project_known_conda_path(self):
        calls = []

        def fake_exists(path):
            return str(path) == "/home/ywj/miniconda3/bin/ffmpeg"

        def fake_which(name):
            calls.append(name)
            return "/usr/bin/ffmpeg"

        self.assertEqual(
            MODULE.discover_ffmpeg_path(exists=fake_exists, which=fake_which),
            "/home/ywj/miniconda3/bin/ffmpeg",
        )
        self.assertEqual(calls, [])

    def test_campaign_index_records_iter_label_and_playable_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            campaign_dir = Path(tmpdir)
            iter_dir = campaign_dir / "iter_02"
            (iter_dir / "analysis").mkdir(parents=True)
            spec = {
                "campaign_id": "phase2",
                "iteration_id": "iter_02",
                "analysis": {
                    "label": "test6",
                    "source_video_metadata": {
                        "source_path": "/home/ywj/test6.mp4",
                        "duration_seconds": 40.31,
                    },
                },
                "runs": [{"duration_policy": "source-full", "duration_seconds": 56}],
            }
            run_result = {"status": "done"}
            review_pack = {
                "primary_review_artifact": str(iter_dir / "analysis" / "preview_clean_h264.mp4")
            }
            (iter_dir / "analysis" / "review_pack.json").write_text(json.dumps(review_pack), encoding="utf-8")

            MODULE.update_campaign_index(iter_dir, spec, run_result)

            index = json.loads((campaign_dir / "campaign_index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["iterations"][0]["iteration_id"], "iter_02")
            self.assertEqual(index["iterations"][0]["video_label"], "test6")
            self.assertEqual(index["iterations"][0]["duration_policy"], "source-full")
            self.assertEqual(index["iterations"][0]["source_duration_seconds"], 40.31)
            self.assertEqual(index["iterations"][0]["primary_review_artifact"], review_pack["primary_review_artifact"])
            self.assertIn("iter_02 - test6", (campaign_dir / "INDEX.md").read_text(encoding="utf-8"))

    def test_campaign_index_records_runtime_fidelity_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            campaign_dir = Path(tmpdir)
            iter_dir = campaign_dir / "iter_03"
            analysis_dir = iter_dir / "analysis"
            analysis_dir.mkdir(parents=True)
            spec = {
                "campaign_id": "phase3",
                "iteration_id": "iter_03",
                "analysis": {
                    "label": "test2",
                    "source_video_metadata": {
                        "source_path": "/home/ywj/test2.mp4",
                        "duration_seconds": 13.31,
                    },
                },
                "runs": [{"duration_policy": "source-full", "duration_seconds": 22}],
            }
            run_result = {"status": "done"}
            review_pack = {
                "primary_review_artifact": str(analysis_dir / "preview_public_h264.mp4")
            }
            fidelity = {
                "status": "blocked_duration_mismatch",
                "prepared_input": {"duration_seconds": 13.31, "frame_count": 399},
                "raw_output": {"duration_seconds": 6.44, "frame_count": 161},
                "public_review": {"duration_seconds": 6.44, "frame_count": 161},
                "debug_review": {"duration_seconds": 6.44, "frame_count": 161},
            }
            (analysis_dir / "review_pack.json").write_text(json.dumps(review_pack), encoding="utf-8")
            (analysis_dir / "runtime_fidelity_summary.json").write_text(json.dumps(fidelity), encoding="utf-8")

            MODULE.update_campaign_index(iter_dir, spec, run_result)

            index = json.loads((campaign_dir / "campaign_index.json").read_text(encoding="utf-8"))
            entry = index["iterations"][0]
            self.assertEqual(entry["runtime_fidelity"]["status"], "blocked_duration_mismatch")
            self.assertAlmostEqual(entry["runtime_fidelity"]["raw_output"]["duration_seconds"], 6.44, places=2)
            self.assertAlmostEqual(entry["runtime_fidelity"]["prepared_input"]["duration_seconds"], 13.31, places=2)

    def test_runtime_fidelity_summary_blocks_when_raw_h264_probe_lacks_counts_but_raw_review_is_short(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            iter_dir = Path(tmpdir) / "iter_04"
            analysis_dir = iter_dir / "analysis"
            artifacts_dir = iter_dir / "artifacts" / "main"
            analysis_dir.mkdir(parents=True)
            artifacts_dir.mkdir(parents=True)
            (artifacts_dir / "stream_chn0.h264").write_bytes(b"raw")
            (analysis_dir / "raw_output_review_h264.mp4").write_bytes(b"raw-review")
            (analysis_dir / "preview_public_h264.mp4").write_bytes(b"public-review")
            (analysis_dir / "preview_debug_h264.mp4").write_bytes(b"debug-review")

            spec = {
                "runs": [{"duration_policy": "source-full"}],
                "analysis": {
                    "source_video_metadata": {
                        "duration_seconds": 64.71,
                        "frame_count": 1941,
                    },
                    "prepared_input_metadata": {
                        "duration_seconds": 64.70,
                        "frame_count": 1941,
                    },
                },
            }
            original_probe = MODULE.probe_local_media_metadata

            def fake_probe(path):
                name = Path(path).name
                if name == "stream_chn0.h264":
                    return {"status": "ready", "duration_seconds": None, "frame_count": None}
                if name == "raw_output_review_h264.mp4":
                    return {"status": "ready", "duration_seconds": 47.2, "frame_count": 1416}
                if name == "preview_public_h264.mp4":
                    return {"status": "ready", "duration_seconds": 64.71, "frame_count": 1416}
                if name == "preview_debug_h264.mp4":
                    return {"status": "ready", "duration_seconds": 64.71, "frame_count": 1416}
                raise AssertionError(f"unexpected probe path: {path}")

            try:
                MODULE.probe_local_media_metadata = fake_probe
                summary = MODULE.write_runtime_fidelity_summary(iter_dir, spec)
            finally:
                MODULE.probe_local_media_metadata = original_probe

            self.assertEqual(summary["status"], "blocked_duration_mismatch")
            self.assertEqual(summary["blocked_reason"], "raw_output_shorter_than_source_full_expectation")
            self.assertAlmostEqual(summary["checks"]["raw_duration_ratio"], 47.2 / 64.7, places=3)
            self.assertAlmostEqual(summary["checks"]["raw_frame_ratio"], 1416 / 1941.0, places=3)

    def test_write_visual_review_stub_links_clean_public_raw_debug_and_method_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            iter_dir = Path(tmpdir) / "iter_01"
            analysis_dir = iter_dir / "analysis"
            analysis_dir.mkdir(parents=True)
            spec = {
                "runs": [{"score": 0.15, "nms": 0.45, "smooth_window": 5}],
                "analysis": {"label": "test6"},
            }
            summary = {
                "video": {"label": "test6"},
                "contact_sheet": "analysis/contact_sheet.jpg",
                "debug_contact_sheet": "analysis/debug_contact_sheet.jpg",
                "worst_frames": {"contact_sheet": "analysis/worst_frames_contact_sheet.jpg"},
                "debug_worst_frames": {"contact_sheet": "analysis/debug_worst_frames_contact_sheet.jpg"},
                "comparison_contact_sheet": "analysis/comparison_contact_sheet.jpg",
                "occupancy_reference": "analysis/occupancy_reference.json",
                "count_accuracy_summary": "analysis/count_accuracy_summary.json",
                "board_resource_summary": "analysis/board_resource_summary.json",
                "review_pack": "analysis/review_pack.json",
                "review_artifacts": {
                    "clean": {"preview_video_h264": "analysis/preview_clean_h264.mp4"},
                    "public": {"preview_video_h264": "analysis/preview_public_h264.mp4"},
                    "debug": {"preview_video_h264": "analysis/preview_debug_h264.mp4"},
                    "raw": {"review_video_h264": "analysis/raw_output_review_h264.mp4"},
                },
            }
            review_pack = {
                "primary_review_artifact": "analysis/preview_clean_h264.mp4",
                "clean": {"preview_video_h264": "analysis/preview_clean_h264.mp4"},
                "public": {"preview_video_h264": "analysis/preview_public_h264.mp4"},
                "debug": {"preview_video_h264": "analysis/preview_debug_h264.mp4"},
                "raw": {"review_video_h264": "analysis/raw_output_review_h264.mp4"},
            }
            fidelity = {
                "status": "ready",
                "source_video": {"duration_seconds": 40.31},
                "prepared_input": {"duration_seconds": 40.31},
                "raw_output": {"duration_seconds": 40.10},
            }
            (iter_dir / "board_run_spec.json").write_text(json.dumps(spec), encoding="utf-8")
            (analysis_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
            (analysis_dir / "review_pack.json").write_text(json.dumps(review_pack), encoding="utf-8")
            (analysis_dir / "runtime_fidelity_summary.json").write_text(json.dumps(fidelity), encoding="utf-8")

            MODULE.write_visual_review_stub(iter_dir)

            payload = json.loads((analysis_dir / "visual_review.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["review_schema_version"], 3)
            self.assertEqual(payload["reviewer"], "main_agent")
            self.assertEqual(payload["review_execution_mode"], "main_agent_serial")
            self.assertEqual(payload["inputs"]["primary_review_artifact"], "analysis/preview_clean_h264.mp4")
            self.assertEqual(payload["inputs"]["preview_clean_h264_mp4"], "analysis/preview_clean_h264.mp4")
            self.assertEqual(payload["inputs"]["preview_public_h264_mp4"], "analysis/preview_public_h264.mp4")
            self.assertEqual(payload["inputs"]["preview_debug_h264_mp4"], "analysis/preview_debug_h264.mp4")
            self.assertEqual(payload["inputs"]["raw_output_review_h264_mp4"], "analysis/raw_output_review_h264.mp4")
            self.assertEqual(
                payload["inputs"]["review_method_validation_json"],
                str(analysis_dir / "review_method_validation.json"),
            )
            self.assertEqual(
                payload["inputs"]["runtime_fidelity_summary_json"],
                str(analysis_dir / "runtime_fidelity_summary.json"),
            )
            self.assertEqual(payload["review_method"]["protocol"], "video_primary_with_still_navigation")
            self.assertFalse(payload["review_method"]["still_only_verdict"])
            self.assertEqual(payload["surface_verdicts"]["clean"]["status"], "pending")
            self.assertEqual(payload["surface_verdicts"]["public"]["status"], "pending")
            self.assertEqual(
                sorted(payload["sections"].keys()),
                [
                    "counting",
                    "ebike_visibility",
                    "person_stability",
                    "public_debug_consistency",
                ],
            )
            self.assertEqual(payload["findings"], [])
            review_method_validation = json.loads(
                (analysis_dir / "review_method_validation.json").read_text(encoding="utf-8")
            )
            self.assertEqual(review_method_validation["status"], "pending")
            self.assertEqual(review_method_validation["policy"], "still_navigation_only")

    def test_visual_review_ready_requires_structured_sections_and_findings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            analysis_dir = Path(tmpdir) / "analysis"
            analysis_dir.mkdir(parents=True)
            review_path = analysis_dir / "visual_review.json"
            review_path.write_text(
                json.dumps(
                    {
                        "review_schema_version": 3,
                        "status": "ready",
                        "review_method": {
                            "protocol": "video_primary_with_still_navigation",
                            "full_video_watched": {"clean": True, "public": False},
                            "diagnostic_video_reviewed": {"debug": False, "raw": False},
                            "still_artifacts_used": [],
                            "still_only_verdict": True,
                        },
                        "surface_verdicts": {
                            "clean": {
                                "status": "pass",
                                "summary": "looks ok",
                                "evidence_paths": ["analysis/preview_clean_h264.mp4"],
                            }
                        },
                        "sections": {
                            "person_stability": {
                                "status": "pass",
                                "summary": "looks stable",
                                "evidence_paths": ["analysis/preview_clean_h264.mp4"],
                            }
                        },
                        "findings": [],
                        "blocking_issues": [],
                        "recommendation": "keep_as_experiment",
                    }
                ),
                encoding="utf-8",
            )

            verdict = MODULE.validate_visual_review(review_path)

            self.assertEqual(verdict["status"], "invalid")
            self.assertIn("missing_sections", verdict["errors"])
            self.assertIn("missing_surface_verdicts", verdict["errors"])
            self.assertIn("full_video_watched_missing", verdict["errors"])
            self.assertIn("still_only_verdict_true", verdict["errors"])
            self.assertIn("ready_requires_findings", verdict["errors"])

    def test_visual_review_ready_rejects_alias_clean_public_and_invalid_finding_surfaces(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            analysis_dir = Path(tmpdir) / "analysis"
            analysis_dir.mkdir(parents=True)
            review_pack_path = analysis_dir / "review_pack.json"
            review_pack_path.write_text(
                json.dumps(
                    {
                        "primary_review_artifact": "analysis/preview_public_h264.mp4",
                        "clean": {"preview_video_h264": "analysis/preview_public_h264.mp4"},
                        "public": {"preview_video_h264": "analysis/preview_public_h264.mp4"},
                        "debug": {"preview_video_h264": "analysis/preview_debug_h264.mp4"},
                        "raw": {"review_video_h264": "analysis/raw_output_review_h264.mp4"},
                    }
                ),
                encoding="utf-8",
            )
            review_path = analysis_dir / "visual_review.json"
            review_path.write_text(
                json.dumps(
                    {
                        "review_schema_version": 3,
                        "status": "ready",
                        "inputs": {
                            "review_pack_json": str(review_pack_path),
                            "primary_review_artifact": "analysis/preview_public_h264.mp4",
                        },
                        "review_method": {
                            "protocol": "video_primary_with_still_navigation",
                            "full_video_watched": {"clean": True, "public": True},
                            "diagnostic_video_reviewed": {"debug": True, "raw": True},
                            "still_artifacts_used": ["analysis/storyboard_pages/clean/page_001.jpg"],
                            "still_only_verdict": False,
                        },
                        "surface_verdicts": {
                            "clean": {
                                "status": "blocker",
                                "summary": "vehicle missing on clean",
                                "evidence_paths": ["analysis/preview_clean_h264.mp4"],
                            },
                            "public": {
                                "status": "blocker",
                                "summary": "vehicle missing on public",
                                "evidence_paths": ["analysis/preview_public_h264.mp4"],
                            },
                        },
                        "sections": {
                            "person_stability": {
                                "status": "pass",
                                "summary": "stable enough",
                                "evidence_paths": ["analysis/preview_clean_h264.mp4"],
                            },
                            "ebike_visibility": {
                                "status": "blocker",
                                "summary": "vehicle disappears",
                                "evidence_paths": ["analysis/preview_clean_h264.mp4"],
                            },
                            "public_debug_consistency": {
                                "status": "blocker",
                                "summary": "public diverges from debug",
                                "evidence_paths": ["analysis/preview_debug_h264.mp4"],
                            },
                            "counting": {
                                "status": "pass",
                                "summary": "counting ok",
                                "evidence_paths": ["analysis/count_accuracy_summary.json"],
                            },
                        },
                        "findings": [
                            {
                                "surfaces": ["bogus"],
                                "category": "clean_public_vehicle_loss",
                                "severity": "blocker",
                                "start_timestamp_sec": 1.0,
                                "end_timestamp_sec": 2.0,
                                "summary": "vehicle disappears",
                                "evidence_paths": ["analysis/preview_clean_h264.mp4"],
                            }
                        ],
                        "blocking_issues": ["vehicle disappears"],
                        "recommendation": "keep_as_experiment",
                    }
                ),
                encoding="utf-8",
            )

            verdict = MODULE.validate_visual_review(review_path)

            self.assertEqual(verdict["status"], "invalid")
            self.assertIn("invalid_finding_surfaces", verdict["errors"])
            self.assertIn("primary_review_artifact_not_clean", verdict["errors"])
            self.assertIn("clean_public_aliasing_detected", verdict["errors"])

    def test_visual_review_ready_with_blocker_finding_requires_blocking_issue_mirror(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            analysis_dir = Path(tmpdir) / "analysis"
            analysis_dir.mkdir(parents=True)
            review_path = analysis_dir / "visual_review.json"
            payload = {
                "review_schema_version": 3,
                "status": "ready",
                "inputs": {
                    "review_pack_json": str(analysis_dir / "review_pack.json"),
                    "primary_review_artifact": "analysis/preview_clean_h264.mp4",
                },
                "review_method": {
                    "protocol": "video_primary_with_still_navigation",
                    "full_video_watched": {"clean": True, "public": True},
                    "diagnostic_video_reviewed": {"debug": True, "raw": True},
                    "still_artifacts_used": ["analysis/issue_windows/clean/issue_001_person_flash.jpg"],
                    "still_only_verdict": False,
                },
                "surface_verdicts": {
                    "clean": {
                        "status": "blocker",
                        "summary": "flash remains on clean",
                        "evidence_paths": ["analysis/preview_clean_h264.mp4"],
                    },
                    "public": {
                        "status": "blocker",
                        "summary": "public diverges from clean",
                        "evidence_paths": ["analysis/preview_public_h264.mp4"],
                    },
                },
                "sections": {
                    "person_stability": {
                        "status": "blocker",
                        "summary": "flash remains",
                        "evidence_paths": ["analysis/issue_windows/clean/issue_001_person_flash.jpg"],
                    },
                    "ebike_visibility": {
                        "status": "pass",
                        "summary": "ok",
                        "evidence_paths": ["analysis/preview_clean_h264.mp4"],
                    },
                    "public_debug_consistency": {
                        "status": "blocker",
                        "summary": "public and debug disagree",
                        "evidence_paths": ["analysis/preview_debug_h264.mp4"],
                    },
                    "counting": {
                        "status": "pass",
                        "summary": "counting preserved",
                        "evidence_paths": ["analysis/count_accuracy_summary.json"],
                    },
                },
                "findings": [
                    {
                        "surfaces": ["public", "debug"],
                        "category": "public_debug_mismatch",
                        "severity": "blocker",
                        "start_timestamp_sec": 3.0,
                        "end_timestamp_sec": 4.5,
                        "summary": "debug has stable rider while public drops",
                        "evidence_paths": ["analysis/preview_debug_h264.mp4"],
                    }
                ],
                "blocking_issues": [],
                "recommendation": "keep_as_experiment",
            }
            (analysis_dir / "review_pack.json").write_text(
                json.dumps(
                    {
                        "primary_review_artifact": "analysis/preview_clean_h264.mp4",
                        "clean": {"preview_video_h264": "analysis/preview_clean_h264.mp4"},
                        "public": {"preview_video_h264": "analysis/preview_public_h264.mp4"},
                        "debug": {"preview_video_h264": "analysis/preview_debug_h264.mp4"},
                        "raw": {"review_video_h264": "analysis/raw_output_review_h264.mp4"},
                    }
                ),
                encoding="utf-8",
            )
            review_path.write_text(json.dumps(payload), encoding="utf-8")

            verdict = MODULE.validate_visual_review(review_path)

            self.assertEqual(verdict["status"], "invalid")
            self.assertIn("blocking_issues_mismatch", verdict["errors"])

    def test_write_video_summary_points_reviewer_to_clean_and_public_video_first(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            iter_dir = Path(tmpdir) / "iter_02"
            analysis_dir = iter_dir / "analysis"
            analysis_dir.mkdir(parents=True)
            spec = {
                "analysis": {
                    "label": "test5",
                    "duration_policy": "source-full",
                    "source_video_metadata": {"duration_seconds": 15.0},
                    "prepared_input_metadata": {"prepare_strategy": "copy", "preflight_status": "ready"},
                },
                "runs": [{"score": 0.15, "nms": 0.45, "smooth_window": 5, "duration_seconds": 22}],
            }
            run_result = {"package": {"binary_md5": "abc", "model_md5": "def"}}
            (iter_dir / "board_run_spec.json").write_text(json.dumps(spec), encoding="utf-8")
            (analysis_dir / "summary.json").write_text(json.dumps({"video": {"label": "test5"}}), encoding="utf-8")
            (analysis_dir / "review_pack.json").write_text(
                json.dumps({"primary_review_artifact": "analysis/preview_clean_h264.mp4"}),
                encoding="utf-8",
            )

            MODULE.write_video_summary(iter_dir, run_result)

            summary_text = (iter_dir / "summary.md").read_text(encoding="utf-8")
            self.assertIn("Watch `analysis/preview_clean_h264.mp4` end-to-end first", summary_text)
            self.assertIn("Then watch `analysis/preview_public_h264.mp4`", summary_text)


    def test_write_video_spec_carries_explicit_rtsp_port(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            iter_dir = Path(tmpdir) / "iter_01"
            iter_dir.mkdir(parents=True)
            args = type(
                "Args",
                (),
                {
                    "campaign_id": "phase3",
                    "board_host": "192.168.1.168",
                    "board_user": "root",
                    "board_password": "ebaina",
                    "score": 0.15,
                    "nms": 0.45,
                    "smooth_window": 5,
                    "duration_policy": "fixed",
                    "duration_seconds": 12,
                    "expected_person_count": 0,
                    "reference_label": "iter03",
                    "video_label": "test6",
                    "input_path": "/root/data/optimization_inputs/test6_main_nob.h264",
                    "rtsp_port": 8555,
                },
            )()
            remote = type("Remote", (), {"config": type("Config", (), {"repo_root": "D:/elevator_ai/elevator_ai"})()})()
            package_info = {"binary_md5": "abc", "model_md5": "def"}

            spec = MODULE.write_video_spec(
                iter_dir,
                "D:/elevator_ai/elevator_ai/logs/direct_runs/phase3/iter_01",
                package_info,
                args,
                remote,
                resolved_input_path="/root/data/optimization_inputs/test6_main_nob.h264",
                resolved_reference_video="D:/windows/reference.mp4",
                source_video_metadata={"duration_seconds": 40.31},
                prepared_input_metadata={"duration_seconds": 40.31},
            )

        self.assertEqual(spec["board"]["rtsp_port"], 8555)


if __name__ == "__main__":
    unittest.main()
