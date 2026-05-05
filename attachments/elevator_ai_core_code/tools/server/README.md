# Server Tools

This directory is reserved for server-side helper scripts, such as:

- build and package helpers
- log collection and parsing
- board release archival
- deployment handoff generation

Current helper:

- `run_single_driver_campaign.py`
  Current stage entrypoint for the single-driver workflow. It builds/packages on the server, reaches Windows over the reverse tunnel, asks Windows helpers to run board work, and records audit artifacts under `logs/direct_runs/<campaign_id>/`.
- `run_video_optimization_campaign.py`
  Phase-oriented wrapper for the board video optimization loop. It handles Phase 0 preflight/input staging, Phase 1 baselines, Phase 2 runtime sweeps, Phase 3 regression sequencing, and Phase 4 report generation while delegating single iterations to `run_single_driver_campaign.py`.
- `export_crowd_keyframes.py`
  Export `crowd_keyframes_v1` from one board video iteration plus `frame_detections.jsonl`. This selects severe undercount, sudden drop, uniform coverage, duplicate-heavy, and backfill frames, then writes images, seed labels, overlays, manifest, and contact sheets.
- `evaluate_crowd_keyframes.py`
  Evaluate YOLO labels on crowd keyframes and emit structured precision/recall, count-error summaries, per-image CSV, and overlay previews.
- `build_person_ebike_crowd_dataset.py`
  Build a crowd-augmented `person+ebike` training dataset by keeping the original validation split unchanged, oversampling `crowd_keyframes_v1/train`, and preserving `crowd_keyframes_v1/val` as an independent benchmark.
- `convert_scut_head_to_yolo.py`
  Convert `datasets/SCUT_HEAD/` from Pascal VOC XML into a YOLO-format head-only dataset for offline head-detection evaluation.
- `create_session.sh`
  Create a new runtime session directory under `logs/sessions/` and bootstrap the minimal handoff files for one new task. This does not start sync; the pusher service is already responsible for automatic delivery.
- `push_sessions_to_windows.sh`
  Push runtime session metadata into the Windows repo path over SSH. Used by the service and can also be run manually for troubleshooting.
- `run_session_pusher_service.sh`
  Long-running wrapper that keeps retrying, prefers direct Windows SSH, and falls back to the reverse tunnel when needed.
- `install_session_pusher_service.sh`
  Install and start the `systemd --user` service for the session pusher.
- `run_session_server_worker.sh`
  Watch local session directories for `status.txt=waiting_server` and launch `codex exec` non-interactively to continue the server side of the same session.
- `install_session_server_worker_service.sh`
  Install and start the `systemd --user` service for the server-side session worker.

Current rollout note:

- Single-driver board validation is documented in:
  - `doc/current/2026-03-18_Single_Driver_Board_Validation_Stage.md`
- Single-driver reverse tunnel experience is documented in:
  - `doc/current/2026-03-18_Single_Driver_Reverse_Tunnel_Experience_Report.md`
- Crowd video optimization and runtime-vs-gate status are documented in:
  - `doc/current/2026-03-18_Crowd_Runtime_Optimization_Status.md`
- SCUT_HEAD head-detection evaluation is documented in:
  - `doc/current/2026-03-18_SCUT_HEAD_Head_Detection_Evaluation_Plan.md`
- Quick handoff/context entrypoints are:
  - `doc/README.md`
  - `doc/00_Next_Session_Context_Pack.md`
- During the single-driver stage, keep the reverse tunnel but stop the session pusher / session worker pair so `logs/sessions/*` cannot interfere with live board work.
- Historical closed-loop automation docs are archived under:
  - `doc/archive/dual_codex_session/`
- During first acceptance, prefer pinning `SESSION_FILTER` to the new automation acceptance session instead of immediately using `all`, because historical `waiting_server` sessions may still be present.
- If `elevator_ai-session-server-worker.service` runs under `systemd --user`, keep any required proxy variables in `~/.config/elevator_ai/session_server_worker.env` so `codex exec` can reach the network.
