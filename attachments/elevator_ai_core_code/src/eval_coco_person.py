"""
使用COCO类别体系评估YOLOv8n的Person检测性能
直接对比COCO-person预测与电梯数据集的person标注
"""
from ultralytics import YOLO
import os
import cv2
import numpy as np
from pathlib import Path
from collections import defaultdict

def load_ground_truth(label_dir):
    """加载真实标注（YOLO格式）"""
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
                    if class_id == 0:  # 只要person
                        x_center = float(parts[1])
                        y_center = float(parts[2])
                        width = float(parts[3])
                        height = float(parts[4])
                        boxes.append({
                            'x': x_center,
                            'y': y_center,
                            'w': width,
                            'h': height
                        })
        
        gt_data[image_id] = boxes
    
    return gt_data

def compute_iou(box1, box2, img_w, img_h):
    """计算两个YOLO格式box的IoU"""
    # box1: GT (normalized)
    # box2: pred (xyxy pixel)
    
    # 转换GT到像素坐标
    x1_center, y1_center, w1, h1 = box1['x'], box1['y'], box1['w'], box1['h']
    x1_min = (x1_center - w1/2) * img_w
    y1_min = (y1_center - h1/2) * img_h
    x1_max = (x1_center + w1/2) * img_w
    y1_max = (y1_center + h1/2) * img_h
    
    # box2已经是xyxy像素坐标
    x2_min, y2_min, x2_max, y2_max = box2
    
    # 计算交集
    inter_x_min = max(x1_min, x2_min)
    inter_y_min = max(y1_min, y2_min)
    inter_x_max = min(x1_max, x2_max)
    inter_y_max = min(y1_max, y2_max)
    
    if inter_x_max < inter_x_min or inter_y_max < inter_y_min:
        return 0.0
    
    inter_area = (inter_x_max - inter_x_min) * (inter_y_max - inter_y_min)
    
    # 计算并集
    box1_area = w1 * img_w * h1 * img_h
    box2_area = (x2_max - x2_min) * (y2_max - y2_min)
    union_area = box1_area + box2_area - inter_area
    
    return inter_area / union_area if union_area > 0 else 0.0

def evaluate_person_detection():
    """评估YOLOv8n在电梯场景中的Person检测性能"""
    print("="*80)
    print("YOLOv8n-COCO Person检测性能评估（真实指标）")
    print("="*80)
    
    # 路径配置
    model_path = "/home/ywj/elevator_ai/yolov8n.pt"
    image_dir = "/home/ywj/elevator_ai/datasets/PandE/personAndEbike/images/val"
    label_dir = "/home/ywj/elevator_ai/datasets/PandE/personAndEbike/labels/val"
    
    # 加载模型（使用COCO类别）
    print("\n1. 加载YOLOv8n模型...")
    model = YOLO(model_path)
    print("   ✓ 模型加载成功（COCO 80类）")
    
    # 加载真实标注
    print("\n2. 加载真实标注...")
    gt_data = load_ground_truth(label_dir)
    print(f"   ✓ 加载 {len(gt_data)} 张图片的标注")
    
    # 统计GT中的person数量
    total_gt_persons = sum(len(boxes) for boxes in gt_data.values())
    print(f"   ✓ 真实Person总数: {total_gt_persons}")
    
    # 获取所有验证集图片
    image_files = sorted([f for f in os.listdir(image_dir) if f.endswith('.jpg')])
    print(f"\n3. 开始推理 {len(image_files)} 张图片...")
    
    # 统计变量
    all_predictions = []  # 所有预测框
    matched_gts = set()   # 已匹配的GT
    
    TP = 0  # True Positives
    FP = 0  # False Positives
    FN = 0  # False Negatives
    
    # IoU阈值
    iou_threshold = 0.5
    conf_threshold = 0.25
    
    # 按图片处理
    for i, img_file in enumerate(image_files, 1):
        img_name = img_file.replace('.jpg', '')
        img_path = os.path.join(image_dir, img_file)
        
        # 读取图片
        image = cv2.imread(img_path)
        if image is None:
            continue
        img_h, img_w = image.shape[:2]
        
        # YOLOv8推理（COCO类别）
        results = model(image, verbose=False)
        
        # 提取person预测（COCO class_id=0）
        pred_persons = []
        for box in results[0].boxes:
            cls = int(box.cls[0])
            conf = float(box.conf[0])
            
            if cls == 0 and conf >= conf_threshold:  # person类别
                xyxy = box.xyxy[0].cpu().numpy()
                pred_persons.append({
                    'box': xyxy,
                    'conf': conf
                })
        
        # 获取GT
        gt_boxes = gt_data.get(img_name, [])
        
        # 匹配预测与GT
        matched_pred = set()
        matched_gt_local = set()
        
        # 对每个预测框，找最佳匹配的GT
        for pred_idx, pred in enumerate(pred_persons):
            best_iou = 0
            best_gt_idx = -1
            
            for gt_idx, gt_box in enumerate(gt_boxes):
                if gt_idx in matched_gt_local:
                    continue
                
                iou = compute_iou(gt_box, pred['box'], img_w, img_h)
                if iou > best_iou:
                    best_iou = iou
                    best_gt_idx = gt_idx
            
            if best_iou >= iou_threshold:
                TP += 1
                matched_pred.add(pred_idx)
                matched_gt_local.add(best_gt_idx)
            else:
                FP += 1
        
        # 未匹配的GT = FN
        FN += len(gt_boxes) - len(matched_gt_local)
        
        # 进度显示
        if i % 100 == 0 or i == len(image_files):
            print(f"   处理进度: {i}/{len(image_files)} ({i/len(image_files)*100:.1f}%)")
    
    print("   ✓ 推理完成！")
    
    # 计算性能指标
    print("\n" + "="*80)
    print("📊 性能指标统计")
    print("="*80)
    
    # 基础统计
    print(f"\n【检测统计】")
    print(f"  真实Person总数 (GT): {total_gt_persons}")
    print(f"  True Positives (TP): {TP}")
    print(f"  False Positives (FP): {FP}")
    print(f"  False Negatives (FN): {FN}")
    
    # 计算指标
    precision = TP / (TP + FP) if (TP + FP) > 0 else 0
    recall = TP / (TP + FN) if (TP + FN) > 0 else 0
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    print(f"\n【核心指标】（IoU阈值={iou_threshold}, 置信度阈值={conf_threshold}）")
    print(f"  ✓ Precision (精确率): {precision:.4f} ({precision*100:.2f}%)")
    print(f"  ✓ Recall (召回率):    {recall:.4f} ({recall*100:.2f}%)")
    print(f"  ✓ F1 Score:           {f1_score:.4f}")
    
    # 漏检/误检率
    miss_rate = FN / total_gt_persons if total_gt_persons > 0 else 0
    false_alarm_rate = FP / (TP + FP) if (TP + FP) > 0 else 0
    
    print(f"\n【错误分析】")
    print(f"  ✗ 漏检率 (Miss Rate): {miss_rate:.4f} ({miss_rate*100:.2f}%)")
    print(f"  ✗ 误检率 (False Alarm): {false_alarm_rate:.4f} ({false_alarm_rate*100:.2f}%)")
    
    # 与项目目标对比
    print("\n" + "="*80)
    print("📈 与项目目标对比")
    print("="*80)
    
    project_goals = {
        'Recall': {'current': recall, 'target': 0.90, 'name': '召回率'},
        'Precision': {'current': precision, 'target': 0.85, 'name': '精确率'},
        'Miss Rate': {'current': miss_rate, 'target': 0.05, 'name': '漏检率'}
    }
    
    for metric, values in project_goals.items():
        current = values['current']
        target = values['target']
        name = values['name']
        
        if metric == 'Miss Rate':
            gap = current - target
            status = '✓' if current <= target else '✗'
        else:
            gap = current - target
            status = '✓' if current >= target else '✗'
        
        print(f"\n  {status} {name} ({metric})")
        print(f"     当前值: {current:.4f} ({current*100:.2f}%)")
        print(f"     目标值: {target:.4f} ({target*100:.2f}%)")
        print(f"     差距:   {gap:+.4f} ({gap*100:+.2f}%)")
    
    # 结论
    print("\n" + "="*80)
    print("💡 结论与建议")
    print("="*80)
    
    if recall >= 0.90:
        print("\n  ✅ 原版YOLOv8n性能满足项目要求！")
        print("     可以直接使用或进行轻量级优化")
    elif recall >= 0.75:
        print("\n  🟡 原版YOLOv8n性能中等")
        print("     建议进行Fine-tuning训练以提升性能")
        print(f"     预期提升空间: {(0.90-recall)*100:.1f}%")
    else:
        print("\n  ❌ 原版YOLOv8n性能不足")
        print("     必须使用电梯数据集进行重新训练")
        print(f"     需要提升: {(0.90-recall)*100:.1f}%")
    
    print("\n" + "="*80)
    
    return {
        'precision': precision,
        'recall': recall,
        'f1': f1_score,
        'TP': TP,
        'FP': FP,
        'FN': FN
    }

if __name__ == "__main__":
    results = evaluate_person_detection()
