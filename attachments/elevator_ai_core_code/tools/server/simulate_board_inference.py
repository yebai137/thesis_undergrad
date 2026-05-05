#!/usr/bin/env python3
"""
simulate_board_inference.py — 服务端模拟板端 YOLOv8 推理 + 后处理

使用 ultralytics YOLOv8 在服务端运行推理,
然后通过 board_postprocess.py 中复刻的板端后处理逻辑来过滤和整理检测结果.
输出带检测框的抽帧图 + frame_detections.jsonl (与板端格式一致).

典型用法:
  conda run -n elevator_ai python3 tools/server/simulate_board_inference.py \\
    --model models/custom/yolov8n_self_trained_100epoch.pt \\
    --source /home/ywj/test2.mp4 \\
    --output-dir runs/codex_optim/test2_baseline \\
    --score 0.15 --nms 0.45 \\
    --sample-interval 30 \\
    --save-annotated-frames \\
    --device 0
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

# 确保 tools/server 在 path 中
sys.path.insert(0, str(Path(__file__).resolve().parent))
from board_postprocess import (
    Detection,
    MedianSmoother,
    ParseResult,
    Rect,
    TemporalHold,
    parse_yolo_detections,
)


def parse_args():
    p = argparse.ArgumentParser(description="服务端模拟板端 YOLOv8 推理")
    p.add_argument("--model", type=str, required=True, help="YOLOv8 .pt 模型路径")
    p.add_argument("--source", type=str, required=True, help="输入视频路径")
    p.add_argument("--output-dir", type=str, required=True, help="输出目录")
    p.add_argument("--score", type=float, default=0.15, help="score 阈值")
    p.add_argument("--nms", type=float, default=0.45, help="NMS IoU 阈值")
    p.add_argument("--smooth-window", type=int, default=5, help="平滑窗口大小")
    p.add_argument("--person-hold-frames", type=int, default=4, help="person temporal hold 帧数")
    p.add_argument("--person-hold-ms", type=int, default=400, help="person temporal hold 毫秒")
    p.add_argument("--sample-interval", type=int, default=30, help="抽帧间隔 (每N帧保存一张)")
    p.add_argument("--max-sample-frames", type=int, default=15, help="最多保存几张抽帧图")
    p.add_argument("--save-annotated-frames", action="store_true", help="保存带检测框的抽帧图")
    p.add_argument("--use-soft-nms", action="store_true", help="使用 Soft-NMS 替代 Hard NMS")
    p.add_argument("--soft-nms-sigma", type=float, default=0.5, help="Soft-NMS sigma")
    p.add_argument("--imgsz", type=int, default=640, help="推理输入尺寸")
    p.add_argument("--device", type=str, default="0", help="设备 (0,1,.. 或 cpu)")
    p.add_argument("--conf-raw", type=float, default=0.01,
                    help="ultralytics 内部 conf 阈值 (设很低, 后处理自己过滤)")
    return p.parse_args()


# ---------- 颜色定义 ----------
CLASS_COLORS = {
    0: (0, 255, 0),    # person - 绿色
    1: (0, 0, 255),    # ebike  - 红色
}
CLASS_NAMES = {
    0: "person",
    1: "ebike",
}


def draw_detections(frame: np.ndarray, result: ParseResult) -> np.ndarray:
    """在帧上绘制检测框和标签."""
    vis = frame.copy()
    for det in result.detections:
        color = CLASS_COLORS.get(det.class_id, (255, 255, 0))
        name = CLASS_NAMES.get(det.class_id, f"cls{det.class_id}")
        cv2.rectangle(vis, (det.rect.x1, det.rect.y1), (det.rect.x2, det.rect.y2), color, 2)
        label = f"{name} {det.score:.2f}"
        (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(vis, (det.rect.x1, det.rect.y1 - lh - 6),
                       (det.rect.x1 + lw, det.rect.y1), color, -1)
        cv2.putText(vis, label, (det.rect.x1, det.rect.y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    # 左上角 panel
    stats = result.stats
    panel_text = (
        f"P:{stats.person_count}({stats.smoothed_person_count}) "
        f"E:{stats.ebike_count}({stats.smoothed_ebike_count}) "
        f"FPS:{stats.fps:.1f}"
    )
    cv2.putText(vis, panel_text, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
    return vis


def make_contact_sheet(image_paths: list, cols: int = 4, thumb_width: int = 480) -> np.ndarray:
    """将多张图拼成 contact sheet."""
    if not image_paths:
        return np.zeros((100, 100, 3), dtype=np.uint8)

    thumbs = []
    for p in image_paths:
        img = cv2.imread(p)
        if img is None:
            continue
        h, w = img.shape[:2]
        scale = thumb_width / w
        new_h = int(h * scale)
        thumb = cv2.resize(img, (thumb_width, new_h))
        # 添加文件名标签
        fname = os.path.basename(p)
        cv2.putText(thumb, fname, (5, new_h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        thumbs.append(thumb)

    if not thumbs:
        return np.zeros((100, 100, 3), dtype=np.uint8)

    # 统一高度
    max_h = max(t.shape[0] for t in thumbs)
    padded = []
    for t in thumbs:
        if t.shape[0] < max_h:
            pad = np.zeros((max_h - t.shape[0], t.shape[1], 3), dtype=np.uint8)
            t = np.vstack([t, pad])
        padded.append(t)

    rows_list = []
    for i in range(0, len(padded), cols):
        row_imgs = padded[i:i + cols]
        while len(row_imgs) < cols:
            row_imgs.append(np.zeros_like(padded[0]))
        rows_list.append(np.hstack(row_imgs))

    return np.vstack(rows_list)


def detection_to_dict(det: Detection) -> dict:
    return {
        "class_id": det.class_id,
        "score": round(det.score, 6),
        "score_percent": det.score_percent,
        "x1": det.rect.x1,
        "y1": det.rect.y1,
        "x2": det.rect.x2,
        "y2": det.rect.y2,
    }


def main():
    args = parse_args()

    # 延迟导入 ultralytics
    from ultralytics import YOLO

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = output_dir / "annotated_frames"
    if args.save_annotated_frames:
        frames_dir.mkdir(exist_ok=True)

    # 加载模型
    print(f"[SIM] 加载模型: {args.model}")
    model = YOLO(args.model)

    # 打开视频
    print(f"[SIM] 打开视频: {args.source}")
    cap = cv2.VideoCapture(args.source)
    if not cap.isOpened():
        print(f"[ERROR] 无法打开视频: {args.source}", file=sys.stderr)
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    vid_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    vid_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[SIM] 视频: {vid_w}x{vid_h}, {total_frames} frames, {fps:.1f} FPS")

    # 初始化后处理组件
    smoother = MedianSmoother(window_size=args.smooth_window)
    temporal_hold = TemporalHold(
        max_hold_frames=args.person_hold_frames,
        max_hold_ms=args.person_hold_ms,
    )

    # 推理配置
    print(f"[SIM] 参数: score={args.score}, nms={args.nms}, imgsz={args.imgsz}")
    print(f"[SIM] 后处理: smooth_window={args.smooth_window}, "
          f"hold_frames={args.person_hold_frames}, hold_ms={args.person_hold_ms}")
    if args.use_soft_nms:
        print(f"[SIM] 使用 Soft-NMS (sigma={args.soft_nms_sigma})")

    # 保存参数
    params = {
        "model": args.model,
        "source": args.source,
        "score_threshold": args.score,
        "nms_threshold": args.nms,
        "smooth_window": args.smooth_window,
        "person_hold_frames": args.person_hold_frames,
        "person_hold_ms": args.person_hold_ms,
        "imgsz": args.imgsz,
        "use_soft_nms": args.use_soft_nms,
        "soft_nms_sigma": args.soft_nms_sigma,
        "video_width": vid_w,
        "video_height": vid_h,
        "total_frames": total_frames,
        "fps": fps,
    }
    with open(output_dir / "params.json", "w") as f:
        json.dump(params, f, indent=2)

    # 推理循环
    det_file = open(output_dir / "frame_detections.jsonl", "w")
    saved_frame_paths = []
    frame_idx = 0
    start_time = time.time()
    sample_count = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # ultralytics 推理 (使用极低的 conf, 让板端后处理来过滤)
            results = model.predict(
                source=frame,
                conf=args.conf_raw,
                iou=0.99,  # 禁用 ultralytics 内置 NMS (让板端逻辑做)
                imgsz=args.imgsz,
                device=args.device,
                verbose=False,
                max_det=300,
            )

            r = results[0]
            if r.boxes is not None and len(r.boxes) > 0:
                boxes_xyxy = r.boxes.xyxy.cpu().numpy()
                scores_raw = r.boxes.conf.cpu().numpy()
                class_ids = r.boxes.cls.cpu().numpy().astype(int)
            else:
                boxes_xyxy = np.zeros((0, 4))
                scores_raw = np.zeros(0)
                class_ids = np.zeros(0, dtype=int)

            # 板端后处理模拟
            # 注意: ultralytics 输出的坐标已经是原图坐标,
            # 所以 proc_size == show_size (不需要额外缩放)
            parse_result = parse_yolo_detections(
                boxes=boxes_xyxy,
                scores=scores_raw,
                class_ids=class_ids,
                proc_width=vid_w,
                proc_height=vid_h,
                show_width=vid_w,
                show_height=vid_h,
                score_threshold=args.score,
                nms_threshold=args.nms,
                use_soft_nms=args.use_soft_nms,
                soft_nms_sigma=args.soft_nms_sigma,
            )

            # temporal hold + smoother
            timestamp_ms = int(frame_idx * 1000.0 / fps)
            parse_result = temporal_hold.apply(parse_result, timestamp_ms)
            parse_result.stats = smoother.update(parse_result.stats, timestamp_ms)

            # 写 JSONL
            record = {
                "frame_index": frame_idx,
                "timestamp_ms": timestamp_ms,
                "person_count": parse_result.stats.person_count,
                "ebike_count": parse_result.stats.ebike_count,
                "smoothed_person_count": parse_result.stats.smoothed_person_count,
                "smoothed_ebike_count": parse_result.stats.smoothed_ebike_count,
                "fps": round(parse_result.stats.fps, 4),
                "detection_count": parse_result.detection_count,
                "detections": [detection_to_dict(d) for d in parse_result.detections],
            }
            det_file.write(json.dumps(record) + "\n")

            # 抽帧保存
            if (args.save_annotated_frames
                    and frame_idx % args.sample_interval == 0
                    and sample_count < args.max_sample_frames):
                vis = draw_detections(frame, parse_result)
                fname = f"frame_{frame_idx:06d}.jpg"
                fpath = str(frames_dir / fname)
                cv2.imwrite(fpath, vis)
                saved_frame_paths.append(fpath)
                sample_count += 1

            frame_idx += 1
            if frame_idx % 100 == 0:
                elapsed = time.time() - start_time
                speed = frame_idx / elapsed if elapsed > 0 else 0
                print(f"[SIM] {frame_idx}/{total_frames} frames ({speed:.1f} fps)")

    finally:
        det_file.close()
        cap.release()

    elapsed = time.time() - start_time

    # 生成 contact sheet
    if saved_frame_paths:
        print(f"[SIM] 生成 contact sheet ({len(saved_frame_paths)} 张)")
        sheet = make_contact_sheet(saved_frame_paths, cols=4, thumb_width=480)
        sheet_path = str(output_dir / "contact_sheet.jpg")
        cv2.imwrite(sheet_path, sheet, [cv2.IMWRITE_JPEG_QUALITY, 90])
        print(f"[SIM] Contact sheet 已保存: {sheet_path}")

    # 汇总统计
    summary = {
        "source": args.source,
        "total_frames_processed": frame_idx,
        "elapsed_seconds": round(elapsed, 2),
        "avg_processing_fps": round(frame_idx / elapsed, 2) if elapsed > 0 else 0,
        "sample_frames_saved": len(saved_frame_paths),
        "params": params,
    }
    with open(output_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n[SIM] 完成! {frame_idx} 帧, 耗时 {elapsed:.1f}s, "
          f"平均 {frame_idx / elapsed:.1f} fps")
    print(f"[SIM] 输出目录: {output_dir}")

    # 写入抽帧路径列表 (供 subagent 使用)
    with open(output_dir / "frame_paths.txt", "w") as f:
        for p in saved_frame_paths:
            f.write(p + "\n")


if __name__ == "__main__":
    main()
