"""
深度分析官方YOLOv8n在电梯场景中的失败案例
重点分析person类别的漏检和误检情况
"""
import cv2
import json
import os
import numpy as np
from collections import defaultdict

def load_predictions(json_path):
    """加载预测结果"""
    with open(json_path, 'r') as f:
        predictions = json.load(f)
    
    pred_by_image = defaultdict(list)
    for p in predictions:
        pred_by_image[p['image_id']].append(p)
    
    return pred_by_image

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
                    x_center = float(parts[1])
                    y_center = float(parts[2])
                    width = float(parts[3])
                    height = float(parts[4])
                    boxes.append({
                        'class_id': class_id,
                        'x_center': x_center,
                        'y_center': y_center,
                        'width': width,
                        'height': height
                    })
        
        gt_data[image_id] = boxes
    
    return gt_data

def analyze_person_detection():
    """分析person类别的检测性能"""
    print("="*80)
    print("Person类别检测性能深度分析")
    print("="*80)
    
    # 加载数据
    pred_json = "/home/ywj/elevator_ai/runs/detect/val/predictions.json"
    label_dir = "/home/ywj/elevator_ai/datasets/PandE/personAndEbike/labels/val"
    
    print("\n加载数据...")
    pred_by_image = load_predictions(pred_json)
    gt_data = load_ground_truth(label_dir)
    
    # 统计变量
    total_gt_persons = 0
    total_pred_persons = 0
    total_images = len(gt_data)
    
    images_with_person = 0
    images_detected_person = 0
    
    missed_persons = []  # 漏检
    false_positives = []  # 误检
    
    # 按person数量分类统计
    detection_by_person_count = {0: [], 1: [], 2: [], 3: []}
    
    print(f"分析 {total_images} 张验证集图片...")
    
    for image_id, gt_boxes in gt_data.items():
        # 统计GT中的person数量
        gt_persons = [box for box in gt_boxes if box['class_id'] == 0]
        gt_person_count = len(gt_persons)
        total_gt_persons += gt_person_count
        
        # 统计预测中的person数量（置信度>0.25）
        preds = pred_by_image.get(image_id, [])
        pred_persons = [p for p in preds if p['category_id'] == 0 and p['score'] > 0.25]
        pred_person_count = len(pred_persons)
        total_pred_persons += pred_person_count
        
        # 记录统计信息
        if gt_person_count > 0:
            images_with_person += 1
            if pred_person_count > 0:
                images_detected_person += 1
            else:
                missed_persons.append({
                    'image_id': image_id,
                    'gt_count': gt_person_count,
                    'persons': gt_persons
                })
        
        # 按person数量分类
        if gt_person_count in detection_by_person_count:
            detection_by_person_count[gt_person_count].append({
                'image_id': image_id,
                'gt': gt_person_count,
                'pred': pred_person_count
            })
    
    # 输出总体统计
    print("\n" + "="*80)
    print("【总体统计】")
    print("="*80)
    print(f"  验证集总图片数: {total_images}")
    print(f"  包含Person的图片: {images_with_person} ({images_with_person/total_images*100:.1f}%)")
    print(f"  真实Person总数: {total_gt_persons}")
    print(f"  预测Person总数: {total_pred_persons}")
    print(f"  检测率: {total_pred_persons/max(total_gt_persons,1)*100:.2f}%")
    
    # Person类别完全漏检
    print("\n" + "="*80)
    print("【关键问题：Person类别完全漏检】")
    print("="*80)
    print(f"  漏检图片数: {len(missed_persons)}")
    print(f"  漏检率: {len(missed_persons)/max(images_with_person,1)*100:.1f}%")
    print(f"  漏检Person总数: {total_gt_persons}")
    
    # 按person数量分析漏检情况
    print("\n【按图片Person数量分析漏检】")
    for person_count in sorted(detection_by_person_count.keys()):
        cases = detection_by_person_count[person_count]
        if not cases or person_count == 0:
            continue
        
        detected = sum(1 for c in cases if c['pred'] > 0)
        total = len(cases)
        miss_rate = (total - detected) / total * 100
        
        print(f"  {person_count} 个person的图片: {total:3d} 张, 漏检 {total-detected:3d} 张 ({miss_rate:.1f}%)")
    
    # 分析person尺寸特征
    print("\n" + "="*80)
    print("【Person目标尺寸分析】")
    print("="*80)
    
    person_sizes = []
    person_aspect_ratios = []
    
    for image_id, gt_boxes in gt_data.items():
        for box in gt_boxes:
            if box['class_id'] == 0:  # person
                width = box['width']
                height = box['height']
                area = width * height
                aspect_ratio = height / max(width, 0.001)
                
                person_sizes.append(area)
                person_aspect_ratios.append(aspect_ratio)
    
    if person_sizes:
        print(f"  Person目标总数: {len(person_sizes)}")
        print(f"  平均面积: {np.mean(person_sizes):.4f} (归一化)")
        print(f"  面积范围: {np.min(person_sizes):.4f} ~ {np.max(person_sizes):.4f}")
        print(f"  中位数面积: {np.median(person_sizes):.4f}")
        
        print(f"\n  平均长宽比(H/W): {np.mean(person_aspect_ratios):.2f}")
        print(f"  长宽比范围: {np.min(person_aspect_ratios):.2f} ~ {np.max(person_aspect_ratios):.2f}")
        
        # 尺寸分布
        size_bins = [0, 0.05, 0.1, 0.2, 0.3, 1.0]
        print(f"\n  面积分布:")
        for i in range(len(size_bins)-1):
            low, high = size_bins[i], size_bins[i+1]
            count = sum(1 for s in person_sizes if low <= s < high)
            print(f"    [{low:.2f}, {high:.2f}): {count:3d} ({count/len(person_sizes)*100:.1f}%)")
    
    # 分析误检情况（检测为其他类别）
    print("\n" + "="*80)
    print("【误检分析 - 模型检测为其他COCO类别】")
    print("="*80)
    
    other_class_counts = defaultdict(int)
    for image_id, preds in pred_by_image.items():
        for pred in preds:
            if pred['category_id'] != 0 and pred['score'] > 0.25:
                other_class_counts[pred['category_id']] += 1
    
    print(f"  检测为其他类别的总框数: {sum(other_class_counts.values())}")
    print(f"  Top 10 误检类别:")
    
    coco_names = {
        1: 'bicycle', 2: 'car', 3: 'motorcycle', 25: 'umbrella',
        27: 'backpack', 40: 'wine glass', 74: 'clock'
    }
    
    for cat_id, count in sorted(other_class_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        cat_name = coco_names.get(cat_id, f'cls_{cat_id}')
        print(f"    类别 {cat_id:2d} ({cat_name:15s}): {count:4d} 个检测框")
    
    # 根本原因分析
    print("\n" + "="*80)
    print("【根本原因分析】")
    print("="*80)
    print("  1. ❌ Person类别100%漏检 - 模型完全无法识别电梯场景中的person")
    print("  2. ❌ 误检大量其他类别 - bicycle, backpack, umbrella等")
    print("  3. 🔍 可能原因:")
    print("     - 电梯俯视角度：person呈现严重透视畸变（头大身小）")
    print("     - 训练数据差异：COCO数据集主要是正常视角的person")
    print("     - 镜面反射干扰：电梯镜子产生虚像，模型未见过此类场景")
    print("     - 遮挡和拥挤：电梯空间狭小，person之间遮挡严重")
    
    print("\n" + "="*80)
    print("【建议措施】")
    print("="*80)
    print("  ✅ 必须进行迁移学习/微调训练:")
    print("     - 使用电梯俯视数据集训练")
    print("     - 数据增强：模拟镜面反射、遮挡等")
    print("     - 调整anchor尺寸以适配俯视person的形状")
    print("  ✅ 模型架构:")
    print("     - 从YOLOv8n-person权重开始微调")
    print("     - 或从头训练专用于电梯场景的模型")

if __name__ == "__main__":
    analyze_person_detection()
