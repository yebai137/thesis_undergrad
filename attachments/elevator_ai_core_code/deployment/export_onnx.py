"""
YOLOv8 ONNX Export — 官方 SDK 推荐方式（修正版）
由于用户模型训练于新版 Ultralytics (nc=2)，但补丁要求旧版，
我们手动构建 DetectionModel(nc=2) 并加载 state_dict，然后用 torch.onnx.export。
"""
import sys
import os

# 强制使用打补丁版本的 ultralytics
sys.path.insert(0, '/home/ywj/elevator_ai/deployment/yolov8_export')

import torch
from ultralytics.nn.tasks import DetectionModel

print("[1/4] Building patched YOLOv8n model (nc=2)...")
model = DetectionModel('yolov8n.yaml', ch=3, nc=2)

print("[2/4] Loading self-trained state_dict...")
sd = torch.load('/home/ywj/elevator_ai/deployment/yolov8n_state_dict.pt', map_location='cpu')
model.load_state_dict(sd, strict=False)

# 设置推理模式并进行兼容性修改
for m in model.modules():
    t = type(m)
    if t in (torch.nn.Hardswish, torch.nn.LeakyReLU, torch.nn.ReLU, torch.nn.ReLU6, torch.nn.SiLU):
        m.inplace = True

model.eval()
model.float()

print("[3/4] Exporting to ONNX via torch.onnx.export (JIT trace)...")

# 准备 dummy 输入
dummy_input = torch.randn(1, 3, 640, 640)

# 先运行一次 forward 将锚点等动态属性初始化
with torch.no_grad():
    model(dummy_input)

output_path = '/home/ywj/elevator_ai/deployment/yolov8n_custom.onnx'

torch.onnx.export(
    model,
    dummy_input,
    output_path,
    opset_version=13,
    input_names=['images'],
    output_names=['output'],
    do_constant_folding=True,
)

file_size = os.path.getsize(output_path) / (1024 * 1024)
print(f"[4/4] ONNX exported successfully!")
print(f"  -> Path: {output_path}")
print(f"  -> Size: {file_size:.1f} MB")
