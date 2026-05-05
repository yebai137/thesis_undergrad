import sys
sys.path.insert(0, '/home/ywj/elevator_ai/deployment/yolov8_export')
from ultralytics.nn.tasks import DetectionModel
import traceback
import torch

try:
    print("Loading DetectionModel...")
    model = DetectionModel('yolov8n.yaml', ch=3, nc=2)
    print("Model loaded successfully!")
    x = torch.randn(1, 3, 640, 640)
    print("Running forward pass...")
    y = model(x)
    print("Forward pass successful!")
    print(len(y))
except Exception as e:
    print("Error occurred:")
    traceback.print_exc()

