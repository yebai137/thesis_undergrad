# 模型文件存放目录

本目录用于存放各类YOLO模型权重文件。

## 目录结构

```
models/
├── README.md              # 本说明文件
├── official/              # 官方预训练模型
│   └── yolov8n.pt        # YOLOv8n官方COCO预训练
├── custom/                # 第三方/别人训练的模型
│   └── yolov8n_xxx.pt    # 上传的自定义模型 ← 上传到这里
└── trained/               # 自己训练的模型
    └── best.pt           # 训练完成后的最佳权重
```

## 使用说明

### 1. 上传自定义模型

**推荐位置**: `models/custom/`

**命名规范**:
- `yolov8n_elevator_v1.pt` - 电梯场景专用
- `yolov8n_person_only.pt` - 只训练person类别
- `yolov8n_source_description.pt` - 描述性命名

**上传方式**:
```bash
# 方法1: 使用scp上传
scp /path/to/your/model.pt username@server:/home/ywj/elevator_ai/models/custom/

# 方法2: 使用文件管理器直接拖放到
#        /home/ywj/elevator_ai/models/custom/

# 方法3: 如果在同一台机器
cp /path/to/your/model.pt /home/ywj/elevator_ai/models/custom/
```

---

### 2. 测试上传的模型

#### 快速测试（单张图片）
```bash
conda activate elevator_ai
cd /home/ywj/elevator_ai

# 测试上传的模型
python src/test_custom_model.py \
    --model models/custom/your_model.pt \
    --source datasets/PandE/personAndEbike/images/val/sample.jpg
```

#### 完整评估（验证集）
```bash
# 在验证集上完整评估
python src/eval_custom_model.py \
    --model models/custom/your_model.pt \
    --data datasets/PandE/personAndEbike/data.yaml
```

#### 性能对比（与官方模型对比）
```bash
# 对比训练前后性能
python src/compare_models.py \
    --model1 yolov8n.pt \
    --model2 models/custom/your_model.pt
```

---

### 3. 模型信息查看

```bash
# 查看模型信息
yolo task=detect mode=val \
    model=models/custom/your_model.pt \
    data=datasets/PandE/personAndEbike/data.yaml
```

---

## 模型管理规范

### 命名规范
```
{base_model}_{dataset}_{version}_{特征}.pt

示例:
- yolov8n_elevator_v1.pt
- yolov8n_elevator_v2_finetuned.pt
- yolov8n_person_best.pt
```

### 备注信息
在同目录下创建`.info`文件记录模型信息：

```
models/custom/yolov8n_elevator_v1.pt
models/custom/yolov8n_elevator_v1.info  ← 模型说明
```

`.info`文件内容示例：
```yaml
model_name: yolov8n_elevator_v1
base_model: yolov8n
dataset: 电梯数据集 3601张
training_epochs: 100
performance:
  mAP@0.5: 0.89
  recall: 0.92
  precision: 0.87
notes: Fine-tuned from COCO, optimized for top-down view
date: 2026-01-16
```

---

## 快速命令参考

```bash
# 1. 激活环境
conda activate elevator_ai

# 2. 进入项目目录
cd /home/ywj/elevator_ai

# 3. 测试模型（推理单张图片）
yolo predict model=models/custom/your_model.pt source=test_image.jpg

# 4. 完整评估
yolo val model=models/custom/your_model.pt data=datasets/PandE/personAndEbike/data.yaml

# 5. 导出模型（部署用）
yolo export model=models/custom/your_model.pt format=onnx
```
