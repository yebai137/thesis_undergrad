"""
使用 YOLOv8 训练电梯间人与电动车检测模型
"""
import argparse
from pathlib import Path
from ultralytics import YOLO
import torch


def parse_args():
    parser = argparse.ArgumentParser(description="训练YOLOv8模型")
    parser.add_argument(
        "--model",
        type=str,
        default="yolov8n.pt",
        help="预训练模型，例如 yolov8n.pt, yolov8s.pt, yolov8m.pt"
    )
    parser.add_argument(
        "--data",
        type=str,
        default="datasets/PandE/personAndEbike/data.yaml",
        help="数据集配置文件路径"
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=100,
        help="训练轮数"
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=16,
        help="批次大小"
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="输入图像尺寸"
    )
    parser.add_argument(
        "--device",
        type=str,
        default="1",
        help="设备选择：0,1,2等GPU编号，或cpu"
    )
    parser.add_argument(
        "--name",
        type=str,
        default="elevator_yolov8",
        help="实验名称"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="从上次中断处继续训练"
    )
    return parser.parse_args()


def train_model(args):
    """训练模型"""
    print("="*80)
    print("🚀 YOLOv8 模型训练")
    print("="*80)
    
    # 检查数据集配置
    data_path = Path(args.data)
    if not data_path.exists():
        raise FileNotFoundError(f"数据集配置文件不存在: {data_path}")
    
    print(f"\n📋 训练配置:")
    print(f"  预训练模型: {args.model}")
    print(f"  数据集配置: {args.data}")
    print(f"  训练轮数:   {args.epochs}")
    print(f"  批次大小:   {args.batch}")
    print(f"  图像尺寸:   {args.imgsz}")
    print(f"  设备:       {args.device}")
    print(f"  实验名称:   {args.name}")
    
    # 检查 GPU
    if args.device != "cpu":
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(int(args.device))
            print(f"\n🎮 GPU: {gpu_name}")
        else:
            print("\n⚠️  GPU 不可用，将使用 CPU 训练")
            args.device = "cpu"
    
    # 加载预训练模型
    print(f"\n1. 加载预训练模型: {args.model}")
    model = YOLO(args.model)
    print("   ✓ 模型加载成功")
    
    # 开始训练
    print(f"\n2. 开始训练...")
    print("-" * 80)
    
    results = model.train(
        data=args.data,
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        device=args.device,
        name=args.name,
        patience=50,           # 早停耐心值
        save=True,             # 保存检查点
        save_period=10,        # 每10轮保存一次
        plots=True,            # 生成训练曲线图
        verbose=True,
        resume=args.resume,
    )
    
    print("\n" + "="*80)
    print("✅ 训练完成!")
    print("="*80)
    
    # 打印结果路径
    print(f"\n📂 结果保存位置: runs/detect/{args.name}/")
    print(f"  - weights/best.pt : 最佳模型权重")
    print(f"  - weights/last.pt : 最新模型权重")
    print(f"  - results.csv     : 训练指标记录")
    print(f"  - *.png           : 训练曲线图")
    
    return results


def main():
    args = parse_args()
    results = train_model(args)


if __name__ == "__main__":
    main()
