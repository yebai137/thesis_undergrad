"""
随机抽取验证集样本并可视化官方YOLOv8n的检测结果
"""
import cv2
import json
import os
import random
import numpy as np
from pathlib import Path

def load_predictions(json_path):
    """加载预测结果"""
    with open(json_path, 'r') as f:
        predictions = json.load(f)
    
    # 按图片组织预测结果
    pred_by_image = {}
    for p in predictions:
        image_id = p['image_id']
        if image_id not in pred_by_image:
            pred_by_image[image_id] = []
        pred_by_image[image_id].append(p)
    
    return pred_by_image

def load_ground_truth(label_path):
    """加载真实标注（YOLO格式）"""
    boxes = []
    if os.path.exists(label_path):
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
                    boxes.append([class_id, x_center, y_center, width, height])
    return boxes

def yolo_to_xyxy(x_center, y_center, width, height, img_w, img_h):
    """将YOLO格式转换为xyxy格式"""
    x1 = int((x_center - width/2) * img_w)
    y1 = int((y_center - height/2) * img_h)
    x2 = int((x_center + width/2) * img_w)
    y2 = int((y_center + height/2) * img_h)
    return x1, y1, x2, y2

def draw_boxes(image, gt_boxes, pred_boxes, img_name):
    """在图像上绘制真实框和预测框"""
    img_h, img_w = image.shape[:2]
    
    # 绘制真实标注（绿色）
    for box in gt_boxes:
        class_id, x_center, y_center, width, height = box
        x1, y1, x2, y2 = yolo_to_xyxy(x_center, y_center, width, height, img_w, img_h)
        
        # 根据类别选择颜色和标签
        if class_id == 0:  # person
            color = (0, 255, 0)  # 绿色
            label = "GT: person"
        else:  # ebike
            color = (0, 200, 200)  # 青色
            label = "GT: ebike"
        
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        cv2.putText(image, label, (x1, y1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    
    # 绘制预测框（红色为person，其他颜色为其他类别）
    if pred_boxes:
        for pred in pred_boxes:
            x1, y1, x2, y2 = pred['bbox']
            x1, y1, x2, y2 = int(x1), int(y1), int(x1+x2), int(y1+y2)
            score = pred['score']
            cat_id = pred['category_id']
            
            # COCO类别映射
            coco_names = {
                0: 'person', 1: 'bicycle', 2: 'car', 3: 'motorcycle',
                25: 'umbrella', 27: 'backpack', 40: 'wine glass', 74: 'clock'
            }
            cat_name = coco_names.get(cat_id, f'cls_{cat_id}')
            
            # person用红色，其他类别用蓝色
            if cat_id == 0:
                color = (0, 0, 255)  # 红色 - person
            else:
                color = (255, 0, 0)  # 蓝色 - 其他类别
            
            # 只显示置信度>0.25的预测
            if score > 0.25:
                cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
                label = f"Pred: {cat_name} {score:.2f}"
                cv2.putText(image, label, (x1, y2+15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    
    # 添加图片名称
    cv2.putText(image, img_name, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    
    return image

def main():
    print("="*80)
    print("可视化官方YOLOv8n检测结果")
    print("="*80)
    
    # 路径配置
    pred_json = "/home/ywj/elevator_ai/runs/detect/val/predictions.json"
    image_dir = "/home/ywj/elevator_ai/datasets/PandE/personAndEbike/images/val"
    label_dir = "/home/ywj/elevator_ai/datasets/PandE/personAndEbike/labels/val"
    output_dir = "/home/ywj/elevator_ai/runs/detect/val/visualizations"
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 加载预测结果
    print("\n加载预测结果...")
    pred_by_image = load_predictions(pred_json)
    
    # 获取所有图片
    all_images = [f for f in os.listdir(image_dir) if f.endswith('.jpg')]
    print(f"验证集图片总数: {len(all_images)}")
    
    # 随机抽取20张图片
    num_samples = min(20, len(all_images))
    sample_images = random.sample(all_images, num_samples)
    
    print(f"\n随机抽取 {num_samples} 张图片进行可视化...")
    print("-"*80)
    
    for i, img_file in enumerate(sample_images, 1):
        img_name = img_file.replace('.jpg', '')
        img_path = os.path.join(image_dir, img_file)
        label_path = os.path.join(label_dir, img_name + '.txt')
        
        # 读取图片
        image = cv2.imread(img_path)
        if image is None:
            print(f"  {i}. 无法读取: {img_file}")
            continue
        
        # 加载真实标注
        gt_boxes = load_ground_truth(label_path)
        
        # 获取预测结果
        pred_boxes = pred_by_image.get(img_name, [])
        
        # 统计person数量
        gt_person = sum(1 for box in gt_boxes if box[0] == 0)
        pred_person = sum(1 for p in pred_boxes if p['category_id'] == 0 and p['score'] > 0.25)
        
        # 绘制检测框
        vis_image = draw_boxes(image.copy(), gt_boxes, pred_boxes, img_name)
        
        # 保存可视化结果
        output_path = os.path.join(output_dir, f"sample_{i:02d}_{img_file}")
        cv2.imwrite(output_path, vis_image)
        
        print(f"  {i:2d}. {img_file:30s} | GT_person={gt_person}, Pred_person={pred_person}, Total_preds={len(pred_boxes)}")
    
    print("\n" + "="*80)
    print(f"可视化完成！结果保存在: {output_dir}/")
    print("="*80)
    
    print("\n【图例说明】")
    print("  - 绿色框: 真实标注 (person)")
    print("  - 青色框: 真实标注 (ebike)")
    print("  - 红色框: 预测结果 (person)")
    print("  - 蓝色框: 预测结果 (其他COCO类别)")
    print("  - 只显示置信度 > 0.25 的预测框")
    
    print("\n【关键观察】")
    print("  1. 官方YOLOv8n在COCO上训练，person是类别0")
    print("  2. 但检测结果显示Person检测框数=0，说明模型未能检测到电梯场景中的person")
    print("  3. 原因可能是：")
    print("     - 电梯俯视角度与COCO训练数据差异大")
    print("     - 镜面反射、遮挡等场景特殊性")
    print("     - 需要针对电梯场景进行微调训练")

if __name__ == "__main__":
    random.seed(42)  # 固定随机种子
    main()
