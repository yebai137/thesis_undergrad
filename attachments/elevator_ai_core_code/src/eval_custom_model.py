"""
评估自定义模型（第三方训练的模型）在电梯数据集上的性能
"""
import argparse
from pathlib import Path
from ultralytics import YOLO
import os
import cv2
import numpy as np
from collections import defaultdict
import random
import yaml

def parse_args():
    parser = argparse.ArgumentParser(description="评估自定义YOLOv8模型")
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="模型路径，例如 models/custom/yolov8n_elevator.pt"
    )
    parser.add_argument(
        "--data",
        type=str,
        default="datasets/PandE/personAndEbike/data.yaml",
        help="数据集配置文件路径"
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="置信度阈值"
    )
    parser.add_argument(
        "--iou",
        type=float,
        default=0.5,
        help="IoU阈值"
    )
    parser.add_argument(
        "--device",
        type=str,
        default="0",
        help="设备选择：0,1,2等GPU编号，或cpu"
    )
    parser.add_argument(
        "--save_examples",
        action="store_true",
        help="是否生成可视化示例图片"
    )
    parser.add_argument(
        "--num_examples",
        type=int,
        default=20,
        help="生成可视化示例图片的数量"
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default=None,
        help="可视化示例输出目录，默认为 runs/detect/val/visualizations"
    )
    return parser.parse_args()


def generate_visualization_examples(model, data_yaml_path, num_examples=20, output_dir=None, conf=0.25, device="0"):
    """
    从验证集中随机选择图片，运行模型推理并生成可视化示例
    
    Args:
        model: YOLO模型
        data_yaml_path: 数据集配置文件路径
        num_examples: 生成示例数量
        output_dir: 输出目录
        conf: 置信度阈值
        device: 设备
    """
    print("\n" + "="*80)
    print("🖼️  生成可视化示例图片")
    print("="*80)
    
    # 读取数据集配置
    with open(data_yaml_path, 'r', encoding='utf-8') as f:
        data_config = yaml.safe_load(f)
    
    dataset_path = Path(data_config['path'])
    val_images_path = dataset_path / data_config['val']
    class_names = data_config['names']
    
    # 获取验证集所有图片
    image_extensions = ['.jpg', '.jpeg', '.png', '.bmp']
    all_images = []
    for ext in image_extensions:
        all_images.extend(list(val_images_path.glob(f'*{ext}')))
        all_images.extend(list(val_images_path.glob(f'*{ext.upper()}')))
    
    if not all_images:
        print(f"  ⚠️  验证集目录中未找到图片: {val_images_path}")
        return
    
    print(f"\n  验证集图片总数: {len(all_images)}")
    
    # 随机选择图片
    num_to_select = min(num_examples, len(all_images))
    selected_images = random.sample(all_images, num_to_select)
    print(f"  随机选择图片数: {num_to_select}")
    
    # 设置输出目录
    if output_dir is None:
        output_dir = Path("runs/detect/val/visualizations")
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"  输出目录: {output_dir}")
    
    # YOLOv8 官方风格颜色 (BGR格式)
    # person: 青色, ebike: 橙色
    colors = {
        0: (255, 191, 0),   # person: 青色 (cyan)
        1: (0, 165, 255),   # ebike: 橙色 (orange)
    }
    
    print(f"\n  开始生成可视化示例...")
    
    for idx, img_path in enumerate(selected_images, 1):
        # 读取原图
        img = cv2.imread(str(img_path))
        if img is None:
            print(f"    ⚠️  无法读取图片: {img_path}")
            continue
        
        img_h, img_w = img.shape[:2]
        
        # 运行推理
        results = model.predict(
            source=str(img_path),
            conf=conf,
            device=device,
            verbose=False
        )
        
        # 绘制检测框 (YOLOv8 官方风格)
        result = results[0]
        for box in result.boxes:
            # 获取边界框坐标
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
            cls_id = int(box.cls[0].cpu().numpy())
            confidence = float(box.conf[0].cpu().numpy())
            
            # 获取颜色
            color = colors.get(cls_id, (255, 191, 0))
            
            # 计算边框线宽 (根据图片大小自适应)
            line_width = max(2, int(min(img_w, img_h) / 200))
            
            # 绘制边界框
            cv2.rectangle(img, (x1, y1), (x2, y2), color, line_width)
            
            # 准备标签文本 (YOLOv8 风格: 类名 置信度)
            class_name = class_names.get(cls_id, f'class_{cls_id}')
            label = f"{class_name} {confidence:.1f}"
            
            # 计算文本尺寸 (根据图片大小自适应)
            font_scale = max(0.5, min(img_w, img_h) / 1000)
            font_thickness = max(1, int(min(img_w, img_h) / 500))
            (text_width, text_height), baseline = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness
            )
            
            # 标签位置 (在边框上方)
            label_y = y1 - 5
            if label_y - text_height < 0:  # 如果上方空间不足，放在框内
                label_y = y1 + text_height + 5
            
            # 创建半透明背景
            overlay = img.copy()
            bg_pt1 = (x1, label_y - text_height - 4)
            bg_pt2 = (x1 + text_width + 6, label_y + 4)
            cv2.rectangle(overlay, bg_pt1, bg_pt2, color, -1)
            
            # 混合原图和覆盖层 (半透明效果)
            alpha = 0.6
            cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)
            
            # 绘制标签文本 (白色)
            cv2.putText(
                img, 
                label, 
                (x1 + 3, label_y), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                font_scale, 
                (255, 255, 255), 
                font_thickness,
                cv2.LINE_AA
            )
        
        # 保存结果图片
        output_filename = f"sample_{idx:02d}_{img_path.name}"
        output_path = output_dir / output_filename
        cv2.imwrite(str(output_path), img)
        
        # 统计检测结果
        num_person = sum(1 for b in result.boxes if int(b.cls[0]) == 0)
        num_ebike = sum(1 for b in result.boxes if int(b.cls[0]) == 1)
        print(f"    [{idx:02d}/{num_to_select}] {img_path.name} -> 检测到 {num_person} 人, {num_ebike} 电动车")
    
    print(f"\n  ✓ 可视化示例生成完成!")
    print(f"  ✓ 保存位置: {output_dir.absolute()}")
    print(f"  ✓ 共生成 {num_to_select} 张示例图片")

def load_ground_truth(label_dir):
    """加载真实标注"""
    gt_data = {}
    
    for label_file in os.listdir(label_dir):
        if not label_file.endswith('.txt'):
            continue
            
        image_id = label_file.replace('.txt', '')
        label_path = os.path.join(label_dir, label_file)
        
        boxes = []
        with open(label_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split()
                    class_id = int(parts[0])
                    boxes.append({
                        'class_id': class_id,
                        'x': float(parts[1]),
                        'y': float(parts[2]),
                        'w': float(parts[3]),
                        'h': float(parts[4])
                    })
        
        gt_data[image_id] = boxes
    
    return gt_data

def compute_iou(box1, box2, img_w, img_h):
    """计算IoU"""
    # box1: GT (normalized)
    # box2: pred (xyxy pixel)
    
    x1_center, y1_center, w1, h1 = box1['x'], box1['y'], box1['w'], box1['h']
    x1_min = (x1_center - w1/2) * img_w
    y1_min = (y1_center - h1/2) * img_h
    x1_max = (x1_center + w1/2) * img_w
    y1_max = (y1_center + h1/2) * img_h
    
    x2_min, y2_min, x2_max, y2_max = box2
    
    inter_x_min = max(x1_min, x2_min)
    inter_y_min = max(y1_min, y2_min)
    inter_x_max = min(x1_max, x2_max)
    inter_y_max = min(y1_max, y2_max)
    
    if inter_x_max < inter_x_min or inter_y_max < inter_y_min:
        return 0.0
    
    inter_area = (inter_x_max - inter_x_min) * (inter_y_max - inter_y_min)
    box1_area = w1 * img_w * h1 * img_h
    box2_area = (x2_max - x2_min) * (y2_max - y2_min)
    union_area = box1_area + box2_area - inter_area
    
    return inter_area / union_area if union_area > 0 else 0.0

def evaluate_model(args):
    """评估模型性能"""
    print("="*80)
    print("自定义模型性能评估")
    print("="*80)
    
    # 检查模型文件
    model_path = Path(args.model)
    if not model_path.exists():
        raise FileNotFoundError(f"模型文件不存在: {model_path}")
    
    print(f"\n模型路径: {model_path}")
    print(f"数据集配置: {args.data}")
    print(f"置信度阈值: {args.conf}")
    print(f"IoU阈值: {args.iou}")
    print(f"设备: {args.device}")
    
    # 加载模型
    print("\n1. 加载模型...")
    model = YOLO(str(model_path))
    print("   ✓ 模型加载成功")
    
    # 使用YOLOv8官方评估（会生成完整报告）
    print("\n2. 使用YOLOv8官方评估工具...")
    print("-" * 80)
    
    results = model.val(
        data=args.data,
        split='val',
        imgsz=640,
        batch=16,
        conf=args.conf,
        iou=args.iou,
        device=args.device,
        save_json=True,
        save_hybrid=True,
        plots=True,
        verbose=True
    )
    
    print("\n" + "="*80)
    print("📊 评估结果")
    print("="*80)
    
    # 打印总体性能
    print(f"\n【总体性能】")
    print(f"  mAP@0.5     : {results.box.map50:.4f}")
    print(f"  mAP@0.5:0.95: {results.box.map:.4f}")
    print(f"  Precision   : {results.box.mp:.4f}")
    print(f"  Recall      : {results.box.mr:.4f}")
    
    # 按类别输出
    print(f"\n【各类别性能】")
    class_names = ['person', 'ebike']
    
    if hasattr(results.box, 'ap_class_index'):
        for i in range(len(class_names)):
            if i < len(results.box.maps):
                print(f"  {class_names[i]:8s}: mAP@0.5 = {results.box.maps[i]:.4f}")
    
    # 与项目目标对比
    print("\n" + "="*80)
    print("📈 与项目目标对比")
    print("="*80)
    
    project_goals = {
        'Recall': {'current': results.box.mr, 'target': 0.90},
        'Precision': {'current': results.box.mp, 'target': 0.85},
        'mAP@0.5': {'current': results.box.map50, 'target': 0.85}
    }
    
    all_passed = True
    for metric, values in project_goals.items():
        current = values['current']
        target = values['target']
        gap = current - target
        status = '✓' if current >= target else '✗'
        
        if current < target:
            all_passed = False
        
        print(f"\n  {status} {metric}")
        print(f"     当前值: {current:.4f} ({current*100:.2f}%)")
        print(f"     目标值: {target:.4f} ({target*100:.2f}%)")
        print(f"     差距:   {gap:+.4f} ({gap*100:+.2f}%)")
    
    # 结论
    print("\n" + "="*80)
    print("💡 评估结论")
    print("="*80)
    
    if all_passed:
        print("\n  ✅ 模型性能满足项目要求！")
    else:
        print("\n  ⚠️  模型性能未完全达标，但可能已有显著改进")
    
    print(f"\n  详细结果保存在: runs/detect/val/")
    print(f"  - confusion_matrix.png : 混淆矩阵")
    print(f"  - PR_curve.png        : PR曲线")
    print(f"  - val_batch*_pred.jpg : 可视化结果")
    
    print("\n" + "="*80)
    
    return results, model

def main():
    args = parse_args()
    results, model = evaluate_model(args)
    
    # 如果需要生成可视化示例
    if args.save_examples:
        generate_visualization_examples(
            model=model,
            data_yaml_path=args.data,
            num_examples=args.num_examples,
            output_dir=args.output_dir,
            conf=args.conf,
            device=args.device
        )

if __name__ == "__main__":
    main()

