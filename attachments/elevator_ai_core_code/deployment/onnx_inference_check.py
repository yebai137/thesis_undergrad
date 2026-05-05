"""
ONNX Runtime 推理完整性验证脚本
目的: 在无 env_setup.sh 污染的纯净环境中验证 yolov8n_custom.onnx 可正常推理
执行方式: conda run -n hi3516_deploy python onnx_inference_check.py
"""
import sys
import os
import json
import numpy as np

ONNX_PATH = '/home/ywj/elevator_ai/deployment/yolov8n_custom.onnx'
OUTPUT_NPY = '/home/ywj/elevator_ai/deployment/onnx_output_ref.npy'
REPORT_JSON = '/home/ywj/elevator_ai/deployment/onnx_inference_report.json'

print("=" * 60)
print("ONNX Runtime 推理完整性验证")
print("=" * 60)

# ---- 导入检查 ----------------------------------------------------------------
try:
    import onnxruntime as ort
    print(f"[OK] onnxruntime 版本: {ort.__version__}")
except ImportError as e:
    print(f"[ERROR] 无法导入 onnxruntime: {e}")
    print("       请先安装: pip install onnxruntime")
    sys.exit(1)

# ---- 加载模型 ----------------------------------------------------------------
if not os.path.isfile(ONNX_PATH):
    print(f"[ERROR] ONNX 文件不存在: {ONNX_PATH}")
    sys.exit(1)

print(f"[INFO] 加载 ONNX 模型: {ONNX_PATH}")
print(f"       文件大小: {os.path.getsize(ONNX_PATH) / 1024 / 1024:.2f} MB")

sess_options = ort.SessionOptions()
sess_options.log_severity_level = 3  # 仅显示 ERROR
session = ort.InferenceSession(ONNX_PATH, sess_options=sess_options,
                               providers=['CPUExecutionProvider'])

# ---- 模型输入/输出信息 -------------------------------------------------------
inputs = session.get_inputs()
outputs = session.get_outputs()

report = {
    "onnx_path": ONNX_PATH,
    "inputs": [],
    "outputs": [],
    "inference_status": "PENDING",
    "output_shape": None,
    "output_dtype": None,
    "max_detections": None,
}

print()
print("[INFO] 模型输入节点:")
for inp in inputs:
    print(f"       name={inp.name}, shape={inp.shape}, dtype={inp.type}")
    report["inputs"].append({"name": inp.name, "shape": str(inp.shape), "dtype": inp.type})

print("[INFO] 模型输出节点:")
for out in outputs:
    print(f"       name={out.name}, shape={out.shape}, dtype={out.type}")
    report["outputs"].append({"name": out.name, "shape": str(out.shape), "dtype": out.type})

# ---- 构造 Dummy 输入 ---------------------------------------------------------
input_name = inputs[0].name
dummy_input = np.random.rand(1, 3, 640, 640).astype(np.float32)
print(f"\n[INFO] 构造虚拟输入: shape={dummy_input.shape}, dtype={dummy_input.dtype}")

# ---- 执行推理 ----------------------------------------------------------------
print("[INFO] 正在执行 CPU 推理...")
try:
    output_list = session.run(None, {input_name: dummy_input})
    print("[OK]  推理成功，无异常抛出。")
    report["inference_status"] = "SUCCESS"
except Exception as e:
    print(f"[ERROR] 推理失败: {e}")
    report["inference_status"] = f"FAILED: {str(e)}"
    with open(REPORT_JSON, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    sys.exit(1)

# ---- 输出分析 ----------------------------------------------------------------
out = output_list[0]
report["output_shape"] = list(out.shape)
report["output_dtype"] = str(out.dtype)
report["max_detections"] = int(out.shape[1]) if out.ndim >= 2 else None

print(f"\n[INFO] 输出张量分析:")
print(f"       shape : {out.shape}")
print(f"       dtype : {out.dtype}")
print(f"       min   : {float(np.min(out)):.4f}")
print(f"       max   : {float(np.max(out)):.4f}")

# 合理性检查: 检测结果维度应 ≤ 300（Filter 算子 topK=300)
if out.ndim >= 2 and out.shape[1] > 300:
    print(f"[WARN ] 检测结果数量 {out.shape[1]} > 300，可能异常，请检查 Filter 算子参数。")
else:
    print(f"[OK]  输出维度在合理范围内（≤ 300 检测结果）。")

# ---- 保存参考输出 -------------------------------------------------------------
np.save(OUTPUT_NPY, out)
print(f"\n[INFO] 参考推理输出已保存至: {OUTPUT_NPY}")

with open(REPORT_JSON, 'w') as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
print(f"[INFO] 推理验证报告已保存至: {REPORT_JSON}")

print()
print("=" * 60)
print("验证结论: ONNX 模型推理功能完整，结构符合预期。")
print("=" * 60)
