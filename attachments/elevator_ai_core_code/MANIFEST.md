# 核心代码附件清单

## 基本信息

- 附件名称：`elevator_ai_core_code_20260505.zip`
- 生成日期：2026-05-05
- 源工程路径：`/home/ywj/elevator_ai`
- 附件暂存路径：`/home/ywj/elevator_ai/thesis_undergrad/attachments/elevator_ai_core_code`
- 父工程分支：`phase1-runtime-align`
- 父工程提交：`2d09b80`
- 论文仓库分支：`thesis-final-convergence`
- 论文仓库提交：`ffe3889`
- 生成口径：源码为主，目标体积 10 MB 以内
- 附件目录体积：约 2.1 MB
- 压缩包体积：约 368 KB

生成时父工程和论文仓库均存在未提交工作区改动，因此本附件记录的是生成时刻的工作区源码快照，而不是某个纯净提交的完整归档。

## 一级目录说明

| 路径 | 内容说明 |
| --- | --- |
| `src/` | 模型训练、验证、预训练基线评估、结果分析和样例可视化脚本 |
| `deployment/` | 权重整理、ONNX 导出、量化准备、ATC 编译辅助和推理检查脚本 |
| `board/` | Hi3516DV500 板端 C 工程源码、构建文件、部署脚本和 host 测试源码 |
| `tools/server/` | 服务器侧数据构建、评估、板端 campaign 编排和视频实验脚本 |
| `PROJECT_README.md` | 主工程 README 备份 |
| `requirements.txt` | Python 依赖说明 |
| `models_README.md` | 模型目录说明 |
| `.gitignore` | 主工程忽略规则备份 |

## 排除内容

本附件明确排除：

- `.git/`、`.planning/`、本地 IDE 配置和会话缓存；
- `datasets/`、`runs/`、`logs/`、`doc/`、`docs/`、`thesis_undergrad/paper/`；
- `*.pt`、`*.onnx`、`*.om`、`*.mp4`、`*.h264`、`*.h265` 等模型和媒体文件；
- `__pycache__/`、`*.pyc`、`*.o`、编译生成二进制和日志；
- `deployment/yolov8_export/`、`deployment/official_yolo_onnx_samples/` 等第三方或重资产参考目录。

## 生成命令摘要

```bash
cd /home/ywj/elevator_ai/thesis_undergrad
mkdir -p attachments/elevator_ai_core_code

rsync -a \
  --include='*/' \
  --include='*.py' \
  --include='*.c' \
  --include='*.h' \
  --include='*.sh' \
  --include='Makefile' \
  --include='README.md' \
  --include='requirements.txt' \
  --exclude='*' \
  /home/ywj/elevator_ai/src \
  /home/ywj/elevator_ai/board \
  /home/ywj/elevator_ai/tools/server \
  attachments/elevator_ai_core_code/

mkdir -p attachments/elevator_ai_core_code/deployment
cp /home/ywj/elevator_ai/deployment/{check_silence.py,convert_weights.py,export_onnx.py,onnx_inference_check.py,prepare_calib.py,quantize_yolov8.py,run_atc.sh,test_forward.py,test_model.py,wrapper.py} \
   attachments/elevator_ai_core_code/deployment/
```

清理禁入文件后，在 `attachments/` 目录下使用 `zip -r elevator_ai_core_code_20260505.zip elevator_ai_core_code` 生成最终附件。
