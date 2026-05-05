import os
import cv2
import numpy as np
import torch
import random
from ultralytics.yolo.data.augment import LetterBox

def prepare_calibration_data(image_dir, output_path, num_samples=32, target_size=(640, 640)):
    """
    Select random images from the dataset, preprocess them exactly as YOLOv8 does 
    (LetterBox resize, BGR to RGB, normalize to 0-1), and save as a batched PyTorch tensor.
    """
    all_images = [f for f in os.listdir(image_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    if len(all_images) < num_samples:
        print(f"Warning: Only found {len(all_images)} images, using all of them.")
        selected_images = all_images
    else:
        selected_images = random.sample(all_images, num_samples)
    
    tensors = []
    print(f"Processing {len(selected_images)} images for calibration...")
    
    letterbox = LetterBox(target_size, auto=False, stride=32)
    
    for img_name in selected_images:
        img_path = os.path.join(image_dir, img_name)
        img0 = cv2.imread(img_path)
        
        # 1. Letterbox resize
        img = letterbox(image=img0)
        
        # 2. BGR to RGB, HWC to CHW
        img = img[:, :, ::-1].transpose(2, 0, 1)  
        img = np.ascontiguousarray(img)
        
        # 3. To torch tensor and normalize 0-1
        tensor = torch.from_numpy(img).float()
        tensor /= 255.0
        
        # 4. Add batch dimension
        tensor = tensor.unsqueeze(0)
        tensors.append(tensor)
    
    # Concat along batch dimension
    calibration_batch = torch.cat(tensors, dim=0)
    print(f"Generated calibration tensor with shape: {calibration_batch.shape}")
    
    torch.save(calibration_batch, output_path)
    print(f"Saved to {output_path}")

if __name__ == "__main__":
    IMAGE_DIR = "/home/ywj/elevator_ai/datasets/PandE/personAndEbike/images/val"
    OUTPUT_PATH = "/home/ywj/elevator_ai/deployment/calibration_data.pt"
    prepare_calibration_data(IMAGE_DIR, OUTPUT_PATH)
