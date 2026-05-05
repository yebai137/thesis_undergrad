#!/usr/bin/env bash
# =============================================================================
# Hi3516DV500 YOLOv8n 离线模型 (.om) ATC 编译脚本
# 使用方式: bash run_atc.sh
# 注意: 请勿与激活了 PyTorch/Ninja 的 Python 环境混用
# =============================================================================
set -eo pipefail

# ---- env_setup.sh 中 LD_LIBRARY_PATH 若未设置需提前初始化 -------------------
: "${LD_LIBRARY_PATH:=}"
export LD_LIBRARY_PATH

# ---- 环境激活 ----------------------------------------------------------------
echo "[  ATC  ] 正在加载 Hi3516DV500 工具链环境..."
source /home/ywj/hi3516dv500_toolchain/env_setup.sh

# ---- 路径定义 ----------------------------------------------------------------
DEPLOY="/home/ywj/elevator_ai/deployment"
ONNX_MODEL="${DEPLOY}/yolov8n_custom.onnx"
AIPP_CFG="${DEPLOY}/aipp.cfg"
IMAGE_LIST="${DEPLOY}/data/image_ref_list.txt"
OUTPUT_BASE="${DEPLOY}/yolov8n_hi3516dv500"
OUTPUT_OM="${OUTPUT_BASE}.om"

# ---- 前置条件检查 ------------------------------------------------------------
echo "[  ATC  ] 检查前置条件..."
if [ ! -f "${ONNX_MODEL}" ]; then
    echo "[ERROR] ONNX 模型文件不存在: ${ONNX_MODEL}"
    exit 1
fi
if [ ! -f "${AIPP_CFG}" ]; then
    echo "[ERROR] AIPP 配置文件不存在: ${AIPP_CFG}"
    exit 1
fi
if [ ! -f "${IMAGE_LIST}" ]; then
    echo "[ERROR] 图像参考列表不存在: ${IMAGE_LIST}"
    exit 1
fi
echo "[  ATC  ] 前置条件检查完毕。"
echo "[  ATC  ]   ONNX 源文件: ${ONNX_MODEL} ($(du -h ${ONNX_MODEL} | cut -f1))"
echo "[  ATC  ]   AIPP 配置:   ${AIPP_CFG}"
echo "[  ATC  ]   图像列表:    ${IMAGE_LIST}"
echo "[  ATC  ]   输出路径:    ${OUTPUT_OM}"
echo ""

# ---- ATC 正式编译 (mode=0) --------------------------------------------------
# 注意: ATC 读取 image_list 中的相对路径时以 image_list 所在目录为基准
echo "[  ATC  ] 开始正式编译 (--mode=0, FP16, Hi3516DV500)..."
echo "[  ATC  ] -------------------------------------------------------"

# 切换到 data 目录，使 image_list 中的相对路径正确解析
cd "${DEPLOY}/data"

atc \
  --mode=0 \
  --framework=5 \
  --model="${ONNX_MODEL}" \
  --output="${OUTPUT_BASE}" \
  --insert_op_conf="${AIPP_CFG}" \
  --input_shape="images:1,3,640,640" \
  --input_format=NCHW \
  --image_list="${IMAGE_LIST}" \
  --soc_version=Hi3516DV500

ATC_EXIT=$?

echo "[  ATC  ] -------------------------------------------------------"
echo ""

# ---- 编译结果验证 ------------------------------------------------------------
if [ ${ATC_EXIT} -ne 0 ]; then
    echo "[ERROR] ATC 编译失败，退出码: ${ATC_EXIT}"
    exit ${ATC_EXIT}
fi

if [ ! -f "${OUTPUT_OM}" ]; then
    echo "[ERROR] ATC 返回成功但 .om 文件未找到: ${OUTPUT_OM}"
    exit 2
fi

OM_SIZE=$(du -h "${OUTPUT_OM}" | cut -f1)
OM_BYTES=$(stat -c%s "${OUTPUT_OM}")
echo "[  ATC  ] ✅ 编译成功!"
echo "[  ATC  ]   输出文件: ${OUTPUT_OM}"
echo "[  ATC  ]   文件大小: ${OM_SIZE} (${OM_BYTES} bytes)"

# 体积合理性检查 (6MB ~ 20MB)
if [ "${OM_BYTES}" -lt 6000000 ] || [ "${OM_BYTES}" -gt 20000000 ]; then
    echo "[WARN ] .om 文件体积异常 (预期 6MB~20MB)，请人工确认。"
fi

echo ""
echo "[  ATC  ] 所有检查通过。下一步请在成功后运行 verify_om.sh 进行深度验证。"
