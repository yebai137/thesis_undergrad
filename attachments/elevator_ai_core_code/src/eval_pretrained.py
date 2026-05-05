"""
使用官方预训练 YOLOv8n 评估电梯数据集性能
"""
from ultralytics import YOLO
import os

def main():
    print("=" * 80)
    print("官方 YOLOv8n 模型在电梯数据集上的性能评估")
    print("=" * 80)
    
    # 数据集配置文件路径
    data_yaml = "/home/ywj/elevator_ai/datasets/PandE/personAndEbike/data.yaml"
    
    # 加载官方预训练模型
    print("\n正在加载官方 YOLOv8n 预训练模型...")
    model = YOLO('/home/ywj/elevator_ai/yolov8n.pt')
    
    print(f"模型加载成功！")
    print(f"数据集配置: {data_yaml}")
    
    # 在验证集上评估
    print("\n开始在验证集上评估性能...")
    print("注意：官方模型训练于COCO数据集，只能评估person类别（class_id=0）")
    print("-" * 80)
    
    results = model.val(
        data=data_yaml,
        split='val',
        imgsz=640,
        batch=16,
        conf=0.001,  # 低置信度阈值以获得完整评估
        iou=0.6,
        device=0,
        save_json=True,
        save_hybrid=True,
        plots=True,
        verbose=True
    )
    
    print("\n" + "=" * 80)
    print("评估完成！性能指标总结：")
    print("=" * 80)
    
    # 打印关键指标
    print(f"\n【总体性能】")
    print(f"  mAP@0.5     : {results.box.map50:.4f}")
    print(f"  mAP@0.5:0.95: {results.box.map:.4f}")
    print(f"  Precision   : {results.box.mp:.4f}")
    print(f"  Recall      : {results.box.mr:.4f}")
    
    # 按类别输出
    print(f"\n【各类别性能】")
    class_names = ['person', 'ebike']
    
    if hasattr(results.box, 'maps') and len(results.box.maps) > 0:
        for i, (name, map50) in enumerate(zip(class_names, results.box.maps)):
            print(f"  {name:8s}: mAP@0.5 = {map50:.4f}")
    
    print(f"\n【重要提示】")
    print(f"  - 官方YOLOv8n在COCO数据集上训练，COCO中person类别ID=0")
    print(f"  - 但本数据集person类别ID也是0，所以person类别可以直接评估")
    print(f"  - ebike类别在COCO中不存在（或对应其他类别），评估结果仅供参考")
    print(f"  - 结果保存在: runs/detect/val/")
    
    # 保存详细结果
    results_dir = "runs/detect/val"
    print(f"\n详细评估结果已保存到: {results_dir}/")
    print(f"  - confusion_matrix.png : 混淆矩阵")
    print(f"  - PR_curve.png        : PR曲线")  
    print(f"  - F1_curve.png        : F1曲线")
    print(f"  - results.csv         : 详细数据")
    
    return results

if __name__ == "__main__":
    main()
