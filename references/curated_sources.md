# Curated Sources

## Core Thesis Direction

### Elevator / edge application background

1. Shi W, Cao J, Zhang Q, et al. Edge Computing: Vision and Challenges.
   支撑边缘计算在时延、隐私、本地决策方面的理论背景。
2. Lin Y C, Liu H C, et al. Edge-Computing-Based People-Counting System for Elevators Using MobileNet-SSD.
   支撑电梯场景边缘视觉应用落地的直接背景。

### Detection and hard-case improvement

1. Shrivastava A, Gupta A, Girshick R. OHEM.
   支撑难例挖掘和困难样本重加权的理论依据。
2. Chen C, et al. Scale-Aware Automatic Augmentation for Object Detection.
   支撑目标检测定向增强策略。
3. Wang C Y, Bochkovskiy A, Liao H Y M. Scaled-YOLOv4.
   支撑模型尺度与效率权衡讨论。
4. EdgeYOLO.
   支撑边缘实时检测器设计方向。

### Multi-task / optimization references

1. Kendall A, Gal Y, Cipolla R. Multi-Task Learning Using Uncertainty to Weigh Losses...
2. Chen Z, et al. GradNorm...

说明：
本 thesis 最终不以完整多任务平台为主线，但这两篇文献可以作为开题报告原始设想与 future work 的方法背景。

### Quantization / deployment consistency

1. Jacob B, et al. Quantization and Training of Neural Networks for Efficient Integer-Arithmetic-Only Inference.
2. Dong Z, et al. HAWQ.
3. Chen J, et al. AQD: Towards Accurate Quantized Object Detection.
4. Stacker S A, et al. Deployment of DNNs for Object Detection on Edge AI Devices With Runtime Optimization.

### Lightweight backbone / efficient detector

1. Howard A, et al. MobileNetV3.
2. Tan M, Le Q V. EfficientNet.
3. Tan M, Pang R, Le Q V. EfficientDet.
4. Redmon J, Farhadi A. YOLO9000.

## Local Evidence Sources

以下不是学术 bibliographic source，但属于论文的工程事实依据：

- `/home/ywj/elevator_ai/doc/reports/2026-04-19_Phase3_3_Full_Val_Metrics.md`
- `/home/ywj/elevator_ai/logs/direct_runs/20260417_phase3_mature_fix/round_report.md`
- `/home/ywj/elevator_ai/logs/direct_runs/20260419_phase3_3_full_val_synced/manifest.md`
- `/home/ywj/elevator_ai/README.md`

## Recommended Use By Chapter

- Chapter 1:
  edge computing, elevator application, lightweight detector overview
- Chapter 2:
  detection, augmentation, quantization, deployment, evaluation foundations
- Chapter 4:
  OHEM, augmentation, model scale comparison
- Chapter 5:
  quantization and edge deployment consistency
- Chapter 6:
  local evidence + related deployment benchmark references
