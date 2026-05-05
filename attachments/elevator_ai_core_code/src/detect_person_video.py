"""
YOLOv8n 电梯场景视频人员检测测试脚本
使用官方预训练模型对视频逐帧检测，并输出标注视频与统计信息
"""
import argparse
import time
from pathlib import Path

import cv2
from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="YOLOv8n 电梯视频人员检测测试")
    parser.add_argument(
        "--source",
        type=str,
        required=True,
        help="输入视频路径，例如 datasets/videos/elevator.mp4",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="runs/detect/person_video.mp4",
        help="输出视频路径（带检测框和人数）",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="检测置信度阈值",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="推理输入尺寸",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="",
        help="设备选择：''自动，'cpu' 或 '0','1' 等GPU编号",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    source_path = Path(args.source)
    if not source_path.exists():
        raise FileNotFoundError(f"找不到输入视频: {source_path}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("YOLOv8n 电梯视频人员检测测试")
    print("=" * 60)
    print(f"输入视频: {source_path}")
    print(f"输出视频: {output_path}")
    print(f"置信度阈值: {args.conf}")
    print(f"推理尺寸: {args.imgsz}")
    print(f"设备: {args.device if args.device else '自动'}")
    print()

    model = YOLO("yolov8n.pt")

    cap = cv2.VideoCapture(str(source_path))
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频: {source_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    frame_idx = 0
    total_person = 0
    start_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = model.predict(
            source=frame,
            conf=args.conf,
            imgsz=args.imgsz,
            device=args.device,
            verbose=False,
        )

        result = results[0]
        person_count = 0
        if result.boxes is not None and result.boxes.cls is not None:
            person_count = int((result.boxes.cls == 0).sum().item())

        total_person += person_count

        annotated = result.plot()
        cv2.putText(
            annotated,
            f"Persons: {person_count}",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

        writer.write(annotated)

        frame_idx += 1
        if frame_idx % 50 == 0:
            elapsed = time.time() - start_time
            fps_now = frame_idx / elapsed if elapsed > 0 else 0
            print(
                f"已处理 {frame_idx}/{total_frames if total_frames else '?'} 帧, "
                f"当前FPS: {fps_now:.2f}"
            )

    cap.release()
    writer.release()

    elapsed = time.time() - start_time
    avg_fps = frame_idx / elapsed if elapsed > 0 else 0

    print()
    print("✅ 视频处理完成")
    print(f"总帧数: {frame_idx}")
    print(f"平均FPS: {avg_fps:.2f}")
    print(f"平均每帧人数: {total_person / frame_idx:.2f}" if frame_idx else "平均每帧人数: 0")
    print(f"输出视频: {output_path}")


if __name__ == "__main__":
    main()
