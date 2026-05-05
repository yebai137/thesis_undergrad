# Elevator Board Deployment

## Build

```bash
cd /home/ywj/elevator_ai/board
source /home/ywj/hi3516dv500_toolchain/env_setup.sh
make test-host
make clean && make
```

If `source/out/include` or `source/out/lib` is missing, run:

```bash
bash /home/ywj/resource/hi3519dv500/sdk.unpack
```

## Run

```bash
./elevator_yolo file \
  --input /app/elevator_ai/data/input/video.h264 \
  --model /app/elevator_ai/data/model/yolov8.om \
  --surface clean \
  --timing source \
  --single-shot \
  --source-fps 30 \
  --source-frame-count 437 \
  --source-duration-ms 14567 \
  --output-dir /app/elevator_ai/data/output/test5_clean \
  --score 0.35 \
  --nms 0.45 \
  --smooth-window 5 \
  --rtsp-port 554
```

The RTSP stream path is `/live.h264`.

`file` mode accepts H.264/H.265 elementary streams and single JPEG images (`.jpg` / `.jpeg`).
Board-native review surfaces now support `--surface clean|public|debug`, and `file` mode can write
`review_surface_run_manifest.json` alongside the usual `frame_counts.csv`,
`frame_detections.jsonl`, and `video_metrics_summary.json`.

`batch` mode evaluates a JPEG directory with matching YOLO labels and writes:

- `annotated/*.jpg`
- `summary.json`
- `per_image.csv`
- `detections.jsonl`

You can recompute `summary.json` on the server with:

```bash
python3 ./scripts/recompute_batch_metrics.py \
  /userdata/elevator_ai/runs/batch_val_10/detections.jsonl \
  --summary-json /userdata/elevator_ai/runs/batch_val_10/summary.json
```

For chunked runs, pass multiple `detections.jsonl` files and optionally write a merged summary:

```bash
python3 ./scripts/recompute_batch_metrics.py \
  /path/to/chunk00/detections.jsonl \
  /path/to/chunk25/detections.jsonl \
  --images-dir /userdata/elevator_ai/datasets/personAndEbike/images/val \
  --labels-dir /userdata/elevator_ai/datasets/personAndEbike/labels/val \
  --output-dir /userdata/elevator_ai/runs/batch_val50_chunked_merged \
  --limit 50 \
  --score-threshold 0.15 \
  --nms-threshold 0.45 \
  --write-summary-json /path/to/merged_summary.json
```

Example:

```bash
./elevator_yolo batch \
  --images-dir /userdata/elevator_ai/datasets/personAndEbike/images/val \
  --labels-dir /userdata/elevator_ai/datasets/personAndEbike/labels/val \
  --output-dir /userdata/elevator_ai/runs/batch_val_10 \
  --offset 0 \
  --limit 10 \
  --score 0.15 \
  --nms 0.45
```

If a long board-side run needs to be split into stable chunks, keep the same sorted dataset and vary `--offset` with `--limit`, for example `--offset 25 --limit 25` for the second half of a `50` image validation.

## Package

```bash
bash ./scripts/deploy.sh --package
```

This creates `out/package/` with the binary, model, and this README.
