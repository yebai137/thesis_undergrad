import torch
import sys

# DO NOT import ultralytics before manipulating paths
# We want to use the system ultralytics (8.0.145) to load the checkpoint
from ultralytics.nn.tasks import attempt_load_weights

def convert_weights(src_path, dst_path):
    print(f"Loading weights from {src_path} using system ultralytics...")
    model = attempt_load_weights(src_path, device='cpu')
    
    print("Extracting state_dict...")
    state_dict = model.state_dict()
    
    print(f"Saving pure state_dict to {dst_path}...")
    torch.save(state_dict, dst_path)
    print("Done!")

if __name__ == "__main__":
    convert_weights(
        '/home/ywj/elevator_ai/models/custom/yolov8n_self_trained_100epoch.pt',
        '/home/ywj/elevator_ai/deployment/yolov8n_state_dict.pt'
    )
