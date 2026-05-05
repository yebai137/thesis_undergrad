import os
import sys
sys.path.insert(0, '/home/ywj/elevator_ai/deployment/yolov8_export')
print("[TRACE] Importing torch")
import torch
print("[TRACE] Importing YOLO")
from ultralytics import YOLO
print("[TRACE] Importing amct_pytorch")
from hotwheels import amct_pytorch
print("[TRACE] Imports finished")

def main():
    print("=== YOLOv8 AMCT PTQ Quantization ===")
    
    # Paths
    model_path = '/home/ywj/elevator_ai/models/custom/yolov8n_self_trained_100epoch.pt'
    calib_data_path = '/home/ywj/elevator_ai/deployment/calibration_data.pt'
    output_dir = '/home/ywj/elevator_ai/deployment/amct_output'
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Load Patched YOLOv8 Model
    print("Loading YOLOv8 model architecture...")
    import sys
    sys.path.insert(0, '/home/ywj/elevator_ai/deployment/yolov8_export')
    from ultralytics.nn.tasks import DetectionModel
    from ultralytics import YOLO

    state_dict_path = '/home/ywj/elevator_ai/deployment/yolov8n_state_dict.pt'
    print(f"Loading bare state_dict from {state_dict_path}...")
    
    # Init blank model (nc=2 for person/ebike)
    model = DetectionModel('yolov8n.yaml', ch=3, nc=2)
    state_dict = torch.load(state_dict_path, map_location='cpu')
    model.load_state_dict(state_dict, strict=False)
    
    # Model compatibility updates
    for m in model.modules():
        t = type(m)
        if t in (torch.nn.Hardswish, torch.nn.LeakyReLU, torch.nn.ReLU, torch.nn.ReLU6, torch.nn.SiLU):
            m.inplace = True

    model.eval()
    
    # 2. Get Calibration Data
    print(f"Loading calibration data from {calib_data_path}...")
    calib_tensor = torch.load(calib_data_path)
    print(f"Calibration data shape: {calib_tensor.shape}")
    
    # 3. AMCT Config
    print("Running dummy forward pass to initialize anchors...")
    with torch.no_grad():
        model(calib_tensor[0:1])
        
    print("Generating AMCT config...")
    config_json_file = os.path.join(output_dir, 'config.json')
    record_file = os.path.join(output_dir, 'record.txt')
    
    # We must skip the final Detect head (model.22) because it contains custom dummy ops
    # that AMCT doesn't support for quantization. We only quantize backbone and neck.
    skip_layers = []
    for name, module in model.named_modules():
        if 'model.22' in name:
            skip_layers.append(name)
            
    amct_pytorch.create_quant_config(
        config_file=config_json_file,
        model=model,
        input_data=calib_tensor[0:1], # Dummy input for tracing
        skip_layers=skip_layers,
        batch_num=2, # Perform calibration in 2 batches (16 images per batch assuming 32 total)
        activation_offset=True
    )
    print(f"Config successfully generated to {config_json_file}")
    
    # 4. Calibration Phase
    print("Starting PTQ Calibration...")
    def calibration_forward(model, data):
        # Pass the calibration data through the model to collect statistics
        with torch.no_grad():
            for i in range(0, data.size(0), 16):
                batch = data[i:i+16]
                model(batch)
                
    quant_model = amct_pytorch.quantize_model(
        config_file=config_json_file,
        record_file=record_file,
        model=model,
        input_data=calib_tensor[0:1]
    )
    
    # Run the forward pass to gather stats
    calibration_forward(quant_model, calib_tensor)
    
    # 5. Export to ONNX
    print("Exporting FakeQuant model to ONNX...")
    deploy_model_path = os.path.join(output_dir, 'yolov8n_quant_deployed.onnx')
    amct_pytorch.save_model(
        model=quant_model,
        record_file=record_file,
        save_path=os.path.join(output_dir, 'yolov8n_quant_deployed'), # amct appends .onnx
        input_data=calib_tensor[0:1],
        dynamic_axes=None
    )
    
    print(f"Model successfully quantized and exported to: {deploy_model_path}")

if __name__ == "__main__":
    main()
