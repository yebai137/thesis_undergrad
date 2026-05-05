# Elevator AI

`elevator_ai` 是电梯场景“人 + 电动车”检测项目的主工作区，统一承载模型训练、导出量化、板端部署，以及跨机器协作与交付工具链。

## 当前主线

当前默认主线是 single-driver 板端验证流程：

1. 在服务器上训练或评估候选模型
2. 导出或打包板端部署产物
3. 通过 Linux 服务器 + Windows 隧道链路在 Hi3516DV500 板端验证
4. 将证据保存在 `logs/direct_runs/`，并在 `doc/current/` 中沉淀结论

## 仓库结构

```text
elevator_ai/
├── board/              # Hi3516DV500 板端 C 工程
├── src/                # Python 训练、评估与分析脚本
├── deployment/         # 导出、量化、ATC 与部署辅助脚本
├── tools/server/       # Linux / 服务器侧编排与数据工具
├── tools/windows/      # Windows 侧隧道与板端执行工具
├── doc/                # 项目内容文档：当前工作、交接、汇报、归档
├── docs/               # 仓库治理文档：结构规则、流程规则
├── logs/               # 运行证据、交接记录、历史 session 痕迹
├── runs/               # 训练和评估输出
├── datasets/           # 本地数据集与转换数据
└── models/             # 本地模型与模型说明
```

## 内容分区

- 核心代码：
  `board/`, `src/`, `deployment/`, `tools/`
- 项目内容文档：
  `doc/`
- 仓库结构与流程规则：
  `docs/`
- 证据与生成物：
  `logs/`, `runs/`, `board/out/`
- 本地重资产：
  `datasets/`, `models/`

关键边界：

- `doc/` 是项目内容文档根目录。
- `docs/` 是仓库治理文档根目录。
- `logs/` 和 `runs/` 是证据 / 输出区，不是主要导航层。

## 快速开始

### 板端构建

```bash
cd /home/ywj/elevator_ai/board
source /home/ywj/hi3516dv500_toolchain/env_setup.sh
make test-host
make clean && make
make package
```

打包产物会生成到 `board/out/package/`。

### Python 环境

```bash
cd /home/ywj/elevator_ai
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 常用命令示例

```bash
python src/train_yolov8.py
python src/eval_custom_model.py --model models/custom/your_model.pt
python deployment/export_onnx.py
python tools/server/run_single_driver_campaign.py --help
```

根据任务实际情况调整数据集路径、模型路径和运行参数。

## 常用入口文档

- 项目文档总入口：
  [doc/README.md](./doc/README.md)
- 仓库结构规则：
  [docs/PROJECT_STRUCTURE.md](./docs/PROJECT_STRUCTURE.md)
- 交付与产物流转规则：
  [docs/DELIVERY_WORKFLOW.md](./docs/DELIVERY_WORKFLOW.md)
- 稳定结构索引：
  [doc/PROJECT_STRUCTURE_INDEX.md](./doc/PROJECT_STRUCTURE_INDEX.md)
- 下一次会话上下文包：
  [doc/00_Next_Session_Context_Pack.md](./doc/00_Next_Session_Context_Pack.md)
- 当前经验沉淀：
  [doc/current/Rolling_Lessons_Learned.md](./doc/current/Rolling_Lessons_Learned.md)
- 板端验证主线：
  [doc/current/2026-03-18_Single_Driver_Board_Validation_Stage.md](./doc/current/2026-03-18_Single_Driver_Board_Validation_Stage.md)
- 反向隧道经验记录：
  [doc/current/2026-03-18_Single_Driver_Reverse_Tunnel_Experience_Report.md](./doc/current/2026-03-18_Single_Driver_Reverse_Tunnel_Experience_Report.md)

## 开发流程

1. 从本 README 开始，再进入 [doc/README.md](./doc/README.md)。
2. 改代码或改路径前，先搜索代码、文档和脚本中的引用关系。
3. 新文件优先放到已有 owner 目录，不另起平行结构。
4. 长期有效的规则与决策写入 `docs/` 或稳定 `doc/` 文档，不写在根目录零散文件里。
5. 证据保留在 `logs/` 或 `runs/`，文档里用链接引用，不复制输出。

## 仓库规则

- 协作与放置规则：
  [AGENTS.md](./AGENTS.md)
- 结构规则：
  [docs/PROJECT_STRUCTURE.md](./docs/PROJECT_STRUCTURE.md)
- 交付规则：
  [docs/DELIVERY_WORKFLOW.md](./docs/DELIVERY_WORKFLOW.md)

## 说明

- `deployment/yolov8_export/` 被视为本地上游 / 参考树，不应随意重组。
- `tools/server/run_single_driver_campaign.py`、`tools/windows/*`、`logs/direct_runs/*`、`logs/sessions/*` 都是路径敏感区，本轮治理明确不动。
- 仓库根目录里旧的速查文件暂时保留，但当前推荐导航路径已经切换为本 README 与上面的 `doc/`、`docs/` 入口。
