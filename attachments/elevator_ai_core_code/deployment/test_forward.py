import sys
sys.path.insert(0, '/home/ywj/elevator_ai/deployment/yolov8_export')
import torch
from ultralytics.nn.tasks import DetectionModel
print("START")
model = DetectionModel('yolov8n.yaml', ch=3, nc=2)
model.load_state_dict(torch.load('/home/ywj/elevator_ai/deployment/yolov8n_state_dict.pt', map_location='cpu'), strict=False)
model.eval()

calib_tensor = torch.load('/home/ywj/elevator_ai/deployment/calibration_data.pt')
print("Loaded calibration data")
print("Running forward pass...")
with torch.no_grad():
    model(calib_tensor[0:1])
print("DONE")
