#!/bin/sh
set -eu

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/../.." && pwd)
MANIFEST_PATH="${REPO_ROOT}/doc/reports/2026-04-19_Phase3_3_Test5_Demo_Profiles.json"
OUTPUT_MODE="hdmi"
PROFILE_ID=""
BINARY_PATH=""
MODEL_PATH=""
RTSP_PORT=""
VO_INTF_TYPE=""
DRY_RUN=0

print_usage() {
    cat <<EOF
Usage:
  $(basename "$0") --profile <candidate_id> [--manifest <path>] [--output-mode hdmi|rtsp]
                  [--binary <path>] [--model <path>] [--rtsp-port <n>]
                  [--vo-intf-type mipi|bt1120] [--dry-run]

Notes:
  - HDMI is the default primary path.
  - Both HDMI and RTSP use the same native \`elevator_yolo file\` pipeline.
  - Playback is source-timed, single-shot, and exits naturally after EOF.
  - \`--manifest\` and \`--vo-intf-type\` are kept for interface compatibility; current board-side runner uses built-in profiles.
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --profile)
            PROFILE_ID="${2:-}"
            shift 2
            ;;
        --manifest)
            MANIFEST_PATH="${2:-}"
            shift 2
            ;;
        --output-mode)
            OUTPUT_MODE="${2:-}"
            shift 2
            ;;
        --binary)
            BINARY_PATH="${2:-}"
            shift 2
            ;;
        --model)
            MODEL_PATH="${2:-}"
            shift 2
            ;;
        --rtsp-port)
            RTSP_PORT="${2:-}"
            shift 2
            ;;
        --vo-intf-type)
            VO_INTF_TYPE="${2:-}"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift 1
            ;;
        --help|-h)
            print_usage
            exit 0
            ;;
        *)
            echo "unknown option: $1" >&2
            print_usage >&2
            exit 1
            ;;
    esac
done

if [ -z "${PROFILE_ID}" ]; then
    echo "--profile is required" >&2
    print_usage >&2
    exit 1
fi

if [ "${OUTPUT_MODE}" != "hdmi" ] && [ "${OUTPUT_MODE}" != "rtsp" ]; then
    echo "unsupported --output-mode: ${OUTPUT_MODE}" >&2
    exit 1
fi

DEFAULT_BINARY_PATH="/root/elevator_ai/elevator_yolo"
DEFAULT_MODEL_PATH="/root/elevator_ai/yolov8.om"
RESET_CMD="killall -9 sample_vdec elevator_yolo sample_vo 2>/dev/null || true"

load_profile() {
    PROFILE_BOARD_INPUT_PATH=""
    PROFILE_SURFACE=""
    PROFILE_TIMING="source"
    PROFILE_SINGLE_SHOT="1"
    PROFILE_SOURCE_FPS="30.0"
    PROFILE_SOURCE_FRAME_COUNT="437"
    PROFILE_SOURCE_DURATION_MS="14567"
    PROFILE_OUTPUT_DIR=""
    PROFILE_SCORE="0.15"
    PROFILE_NMS="0.45"
    PROFILE_SMOOTH_WINDOW="5"
    PROFILE_RTSP_PORT="8555"

    case "${PROFILE_ID}" in
        test5_clean|phase3_3_iter02)
            PROFILE_BOARD_INPUT_PATH="/root/data/optimization_inputs/test5_annexb_repeat_headers_no_sei.h264"
            PROFILE_SURFACE="clean"
            PROFILE_OUTPUT_DIR="/root/direct_video_metrics_test5_clean"
            ;;
        test5_debug)
            PROFILE_BOARD_INPUT_PATH="/root/data/optimization_inputs/test5_annexb_repeat_headers_no_sei.h264"
            PROFILE_SURFACE="debug"
            PROFILE_OUTPUT_DIR="/root/direct_video_metrics_test5_debug"
            ;;
        *)
            echo "unknown profile: ${PROFILE_ID}" >&2
            exit 1
            ;;
    esac
}

append_arg() {
    RUN_CMD="${RUN_CMD} $1"
}

load_profile

BINARY="${BINARY_PATH:-${DEFAULT_BINARY_PATH}}"
MODEL="${MODEL_PATH:-${DEFAULT_MODEL_PATH}}"
PORT="${RTSP_PORT:-${PROFILE_RTSP_PORT}}"

RUN_CMD="${BINARY} file --input ${PROFILE_BOARD_INPUT_PATH} --model ${MODEL}"
append_arg "--surface ${PROFILE_SURFACE}"
append_arg "--timing ${PROFILE_TIMING}"
if [ "${PROFILE_SINGLE_SHOT}" = "1" ]; then
    append_arg "--single-shot"
fi
append_arg "--source-fps ${PROFILE_SOURCE_FPS}"
append_arg "--source-frame-count ${PROFILE_SOURCE_FRAME_COUNT}"
append_arg "--source-duration-ms ${PROFILE_SOURCE_DURATION_MS}"
append_arg "--output-dir ${PROFILE_OUTPUT_DIR}"
append_arg "--score ${PROFILE_SCORE}"
append_arg "--nms ${PROFILE_NMS}"
append_arg "--smooth-window ${PROFILE_SMOOTH_WINDOW}"
if [ "${OUTPUT_MODE}" = "rtsp" ] && [ -n "${PORT}" ]; then
    append_arg "--rtsp-port ${PORT}"
fi

RUN_CMD="${RESET_CMD}; ${RUN_CMD}"
echo "${RUN_CMD}"

if [ "${DRY_RUN}" -eq 1 ]; then
    exit 0
fi

sh -c "${RESET_CMD}"

set -- "${BINARY}" file \
    --input "${PROFILE_BOARD_INPUT_PATH}" \
    --model "${MODEL}" \
    --surface "${PROFILE_SURFACE}" \
    --timing "${PROFILE_TIMING}" \
    --source-fps "${PROFILE_SOURCE_FPS}" \
    --source-frame-count "${PROFILE_SOURCE_FRAME_COUNT}" \
    --source-duration-ms "${PROFILE_SOURCE_DURATION_MS}" \
    --output-dir "${PROFILE_OUTPUT_DIR}" \
    --score "${PROFILE_SCORE}" \
    --nms "${PROFILE_NMS}" \
    --smooth-window "${PROFILE_SMOOTH_WINDOW}"

if [ "${PROFILE_SINGLE_SHOT}" = "1" ]; then
    set -- "$@" --single-shot
fi
if [ "${OUTPUT_MODE}" = "rtsp" ] && [ -n "${PORT}" ]; then
    set -- "$@" --rtsp-port "${PORT}"
fi

exec "$@"
