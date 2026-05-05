#!/usr/bin/env bash
set -eu

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
OUT_DIR="${ROOT_DIR}/out/package"

if [ "${1:-}" = "--package" ] && [ $# -ge 2 ]; then
    OUT_DIR="$2"
fi

BIN_PATH="${ROOT_DIR}/elevator_yolo"
MODEL_PATH="${ROOT_DIR}/data/model/yolov8.om"
README_PATH="${ROOT_DIR}/README.md"

if [ ! -f "${BIN_PATH}" ]; then
    echo "missing binary: ${BIN_PATH}"
    echo "run: make"
    exit 1
fi

if [ ! -f "${MODEL_PATH}" ]; then
    echo "missing model: ${MODEL_PATH}"
    exit 1
fi

mkdir -p "${OUT_DIR}"
cp "${BIN_PATH}" "${OUT_DIR}/"
cp "${MODEL_PATH}" "${OUT_DIR}/"
cp "${README_PATH}" "${OUT_DIR}/"

echo "package created at ${OUT_DIR}"
