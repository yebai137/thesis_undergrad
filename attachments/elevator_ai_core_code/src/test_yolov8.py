"""
YOLOv8n 环境测试脚本
测试 YOLOv8 是否能正常运行
"""
import sys
from ultralytics import YOLO
import torch
import cv2
import numpy as np

def test_environment():
    """测试环境配置"""
    print("=" * 60)
    print("环境测试")
    print("=" * 60)
    
    # 检查 PyTorch
    print(f"PyTorch 版本: {torch.__version__}")
    print(f"CUDA 是否可用: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA 版本: {torch.version.cuda}")
        print(f"GPU 数量: {torch.cuda.device_count()}")
        for i in range(torch.cuda.device_count()):
            print(f"  GPU {i}: {torch.cuda.get_device_name(i)}")
    
    # 检查 OpenCV
    print(f"OpenCV 版本: {cv2.__version__}")
    print()

def test_yolov8n_image():
    """测试 YOLOv8n 图像推理"""
    print("=" * 60)
    print("测试 YOLOv8n 图像推理")
    print("=" * 60)
    
    # 加载预训练模型（会自动下载）
    print("正在加载 YOLOv8n 预训练模型...")
    model = YOLO('yolov8n.pt')
    
    # 创建一个测试图像（随机图像）
    print("创建测试图像...")
    test_img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
    
    # 推理
    print("开始推理...")
    results = model(test_img)
    
    print(f"✅ 推理成功！")
    print(f"检测到 {len(results[0].boxes)} 个目标")
    print()
    
    return model

def test_yolov8n_video():
    """测试 YOLOv8n 视频推理性能"""
    print("=" * 60)
    print("测试 YOLOv8n 视频推理性能")
    print("=" * 60)
    
    model = YOLO('yolov8n.pt')
    
    # 创建测试视频帧
    print("测试推理速度（100帧）...")
    test_img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
    
    import time
    start_time = time.time()
    
    for i in range(100):
        results = model(test_img, verbose=False)
        if (i + 1) % 20 == 0:
            print(f"  已处理 {i + 1} 帧...")
    
    end_time = time.time()
    elapsed = end_time - start_time
    fps = 100 / elapsed
    
    print(f"✅ 性能测试完成！")
    print(f"总耗时: {elapsed:.2f} 秒")
    print(f"平均 FPS: {fps:.2f}")
    print()

def test_person_detection():
    """测试人员检测功能"""
    print("=" * 60)
    print("测试人员检测功能")
    print("=" * 60)
    
    model = YOLO('yolov8n.pt')
    
    # 创建一个模拟图像
    test_img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
    
    # 推理
    results = model(test_img)
    
    # 筛选出 person 类别（COCO 数据集中 person 类别 ID = 0）
    person_count = 0
    for box in results[0].boxes:
        if int(box.cls) == 0:  # person 类别
            person_count += 1
            conf = float(box.conf)
            print(f"  检测到人员，置信度: {conf:.2f}")
    
    print(f"✅ 人员检测测试完成！")
    print(f"检测到 {person_count} 个人员目标")
    print()

def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("YOLOv8n 环境测试程序")
    print("=" * 60 + "\n")
    
    try:
        # 1. 测试环境
        test_environment()
        
        # 2. 测试图像推理
        model = test_yolov8n_image()
        
        # 3. 测试视频推理性能
        test_yolov8n_video()
        
        # 4. 测试人员检测
        test_person_detection()
        
        print("=" * 60)
        print("✅ 所有测试通过！环境配置正常！")
        print("=" * 60)
        print("\n下一步:")
        print("1. 准备电梯俯视视角的数据集")
        print("2. 使用 labelImg 或 Roboflow 进行标注")
        print("3. 开始训练自定义模型")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
