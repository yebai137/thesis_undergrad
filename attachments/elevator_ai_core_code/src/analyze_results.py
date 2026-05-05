"""
分析官方YOLOv8n在电梯数据集上的评估结果
"""
import json
import os
from collections import defaultdict, Counter
import numpy as np

# COCO数据集类别映射（常用类别）
COCO_CLASSES = {
    0: 'person', 1: 'bicycle', 2: 'car', 3: 'motorcycle', 4: 'airplane',
    5: 'bus', 6: 'train', 7: 'truck', 8: 'boat', 9: 'traffic light',
    # ... 更多类别
    74: 'clock', 73: 'book', 25: 'umbrella', 27: 'backpack', 40: 'wine glass'
}

def load_predictions(json_path):
    """加载预测结果JSON"""
    print(f"加载预测结果: {json_path}")
    with open(json_path, 'r') as f:
        predictions = json.load(f)
    print(f"  总预测框数: {len(predictions)}")
    return predictions

def load_ground_truth(label_dir):
    """加载真实标注"""
    print(f"加载真实标注: {label_dir}")
    gt_data = {}
    
    label_files = [f for f in os.listdir(label_dir) if f.endswith('.txt')]
    
    for label_file in label_files:
        image_id = label_file.replace('.txt', '')
        label_path = os.path.join(label_dir, label_file)
        
        boxes = []
        with open(label_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split()
                    class_id = int(parts[0])
                    boxes.append(class_id)
        
        gt_data[image_id] = boxes
    
    print(f"  标注文件数: {len(gt_data)}")
    return gt_data

def analyze_predictions(predictions, gt_data):
    """分析预测结果"""
    print("\n" + "="*80)
    print("预测结果分析")
    print("="*80)
    
    # 统计预测类别分布
    pred_categories = [p['category_id'] for p in predictions]
    category_counter = Counter(pred_categories)
    
    print(f"\n【预测类别分布】（Top 10，置信度 > 0.001）")
    for cat_id, count in category_counter.most_common(10):
        cat_name = COCO_CLASSES.get(cat_id, f'unknown_{cat_id}')
        print(f"  类别 {cat_id:2d} ({cat_name:15s}): {count:5d} 个检测框")
    
    # 统计person类别（category_id=0）的预测
    person_preds = [p for p in predictions if p['category_id'] == 0]
    print(f"\n【Person类别预测统计】")
    print(f"  Person检测框总数: {len(person_preds)}")
    
    if person_preds:
        person_scores = [p['score'] for p in person_preds]
        print(f"  置信度范围: {min(person_scores):.4f} ~ {max(person_scores):.4f}")
        print(f"  平均置信度: {np.mean(person_scores):.4f}")
        print(f"  置信度中位数: {np.median(person_scores):.4f}")
        
        # 按置信度区间统计
        score_bins = [0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0]
        print(f"\n  置信度分布:")
        for i in range(len(score_bins)-1):
            low, high = score_bins[i], score_bins[i+1]
            count = sum(1 for s in person_scores if low <= s < high)
            print(f"    [{low:.1f}, {high:.1f}): {count:5d} ({count/len(person_scores)*100:.1f}%)")
    
    # 统计真实标注类别分布
    print(f"\n【真实标注类别分布】")
    gt_class_counts = defaultdict(int)
    total_images = len(gt_data)
    
    for image_id, boxes in gt_data.items():
        for class_id in boxes:
            gt_class_counts[class_id] += 1
    
    print(f"  验证集图片数: {total_images}")
    for class_id, count in sorted(gt_class_counts.items()):
        class_name = ['person', 'ebike'][class_id] if class_id < 2 else f'unknown_{class_id}'
        print(f"  类别 {class_id} ({class_name:10s}): {count:5d} 个目标")
    
    # 统计每张图片的person数量分布
    person_counts = []
    for image_id, boxes in gt_data.items():
        person_count = sum(1 for c in boxes if c == 0)
        person_counts.append(person_count)
    
    print(f"\n【每张图片Person数量统计】")
    print(f"  平均每张图片: {np.mean(person_counts):.2f} 个person")
    print(f"  最多: {max(person_counts)} 个person")
    print(f"  最少: {min(person_counts)} 个person")
    
    # 统计person数量分布
    count_distribution = Counter(person_counts)
    print(f"\n  Person数量分布:")
    for num_persons in sorted(count_distribution.keys()):
        num_images = count_distribution[num_persons]
        print(f"    {num_persons} 个person: {num_images:3d} 张图片 ({num_images/total_images*100:.1f}%)")

def analyze_by_image(predictions, gt_data):
    """按图片分析预测结果"""
    print("\n" + "="*80)
    print("按图片分析预测性能")
    print("="*80)
    
    # 组织预测结果按图片
    pred_by_image = defaultdict(list)
    for p in predictions:
        if p['category_id'] == 0:  # 只统计person
            pred_by_image[p['image_id']].append(p)
    
    # 比较预测vs真实
    total_gt_person = 0
    total_pred_person = 0
    images_with_person = 0
    images_detected_person = 0
    
    detection_errors = []
    
    for image_id, gt_boxes in gt_data.items():
        gt_person_count = sum(1 for c in gt_boxes if c == 0)
        pred_person_count = len(pred_by_image.get(image_id, []))
        
        total_gt_person += gt_person_count
        total_pred_person += pred_person_count
        
        if gt_person_count > 0:
            images_with_person += 1
            if pred_person_count > 0:
                images_detected_person += 1
        
        # 记录检测差异较大的图片
        if abs(gt_person_count - pred_person_count) >= 2:
            detection_errors.append({
                'image_id': image_id,
                'gt': gt_person_count,
                'pred': pred_person_count,
                'diff': pred_person_count - gt_person_count
            })
    
    print(f"\n【整体统计】")
    print(f"  真实Person总数: {total_gt_person}")
    print(f"  预测Person总数: {total_pred_person}")
    print(f"  检测率: {total_pred_person/total_gt_person*100:.2f}%")
    
    print(f"\n【图片级统计】")
    print(f"  包含Person的图片: {images_with_person}/{len(gt_data)} ({images_with_person/len(gt_data)*100:.1f}%)")
    print(f"  成功检测到Person的图片: {images_detected_person}/{images_with_person} ({images_detected_person/images_with_person*100:.1f}%)")
    
    if detection_errors:
        print(f"\n【检测偏差较大的图片】（差异>=2）")
        print(f"  共 {len(detection_errors)} 张图片")
        
        # 显示最严重的10个案例
        detection_errors.sort(key=lambda x: abs(x['diff']), reverse=True)
        print(f"\n  Top 10 检测偏差:")
        for i, err in enumerate(detection_errors[:10], 1):
            print(f"    {i:2d}. {err['image_id']:20s}: GT={err['gt']:2d}, Pred={err['pred']:2d}, Diff={err['diff']:+3d}")

def main():
    # 路径配置
    pred_json = "/home/ywj/elevator_ai/runs/detect/val/predictions.json"
    label_dir = "/home/ywj/elevator_ai/datasets/PandE/personAndEbike/labels/val"
    
    # 加载数据
    predictions = load_predictions(pred_json)
    gt_data = load_ground_truth(label_dir)
    
    # 分析预测结果
    analyze_predictions(predictions, gt_data)
    
    # 按图片分析
    analyze_by_image(predictions, gt_data)
    
    print("\n" + "="*80)
    print("分析完成！")
    print("="*80)
    print("\n【关键发现】")
    print("1. 官方YOLOv8n模型在COCO数据集上训练，person类别(ID=0)可以直接使用")
    print("2. 但模型会检测出很多COCO中的其他类别，这些在电梯场景中多为误检")
    print("3. 需要查看可视化结果(val_batch*_pred.jpg)来评估实际检测效果")
    print("4. 建议：针对电梯场景微调模型，只保留person和ebike两个类别")

if __name__ == "__main__":
    main()
