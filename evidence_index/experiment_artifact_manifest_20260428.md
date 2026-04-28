# 2026-04-28 论文部署一致性实验产物索引

本索引用于把论文仓库中的图表、正文结论与父仓库实验日志建立可回溯关系。实验日志保留在父仓库 `/home/ywj/elevator_ai/logs/direct_runs/`，论文仓库只提交本索引和由真实 artifacts 生成的图表。

## 工具与模型版本

- 父仓库工具提交：`2d09b80 experiments: support thesis consistency campaigns`
- 板端 package：`/home/ywj/elevator_ai/board/out/package`
- 板端二进制 md5：`cd7a40389454b3bdb2ccbe0e9dedc6bb`
- OM 模型 md5：`e3d03dc1627d6ba44baa7211951c9dbe`
- 统一验证集：`val=720`
- batch 统一参数：`score=0.15`，除 NMS 敏感性外 `nms=0.45`
- 视频统一输入：`/home/ywj/test5.mp4`，`duration-policy=source-full`

## 采用与失败尝试

| 实验项 | 最终采用 campaign | 状态 | 失败或不采用尝试 | 说明 |
| --- | --- | --- | --- | --- |
| NMS=0.35 | `20260428_thesis_consistency_nms035_r4` | 采用 | `20260428_thesis_consistency_nms035`、`20260428_thesis_consistency_nms035_r2`、`20260428_thesis_consistency_nms035_r3` | 前两次未形成完整 analysis；`_r3` 返回码为 0 但 `failure_count=75`，不采用 |
| NMS=0.45 | `20260428_thesis_consistency_nms045` | 采用 | 无 | `success_count=720`，`failure_count=0` |
| NMS=0.55 | `20260428_thesis_consistency_nms055` | 采用 | 无 | `success_count=720`，`failure_count=0` |
| cleanup=full | `20260428_thesis_consistency_cleanup_full` | 采用 | 无 | `success_count=720`，`failure_count=0` |
| cleanup=safe | `20260428_thesis_consistency_cleanup_safe` | 采用 | 无 | `success_count=720`，`failure_count=0` |
| cleanup=off | `20260428_thesis_consistency_cleanup_off` | 采用 | 无 | `success_count=720`，`failure_count=0` |
| smooth-window=1 | `20260428_thesis_consistency_video_smooth1` | 采用 | 无 | `frame_count=437` |
| smooth-window=5 | `20260428_thesis_consistency_video_smooth5` | 采用 | 无 | `frame_count=437` |

## NMS 敏感性指标

来源文件：`iter_01/analysis/performance_summary.json`

| NMS | campaign | Pred | FP | FN | person F1 | ebike F1 | ebike recall | mAP@0.5 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.35 | `20260428_thesis_consistency_nms035_r4` | 1526 | 146 | 116 | 0.877707 | 0.951791 | 0.959722 | 0.905713 |
| 0.45 | `20260428_thesis_consistency_nms045` | 1533 | 152 | 115 | 0.877707 | 0.948595 | 0.961111 | 0.910354 |
| 0.55 | `20260428_thesis_consistency_nms055` | 1542 | 160 | 114 | 0.877707 | 0.944142 | 0.962500 | 0.910317 |

图表对应：`fig_chap05_nms_sensitivity.{pdf,png}`

## 后处理消融指标

来源文件：`iter_01/analysis/performance_summary.json`

| cleanup | campaign | Pred | FP | FN | ebike FP | ebike FN | ebike recall | ebike F1 | mAP@0.5 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| full | `20260428_thesis_consistency_cleanup_full` | 1383 | 143 | 256 | 38 | 169 | 0.765278 | 0.841864 | 0.812084 |
| safe | `20260428_thesis_consistency_cleanup_safe` | 1533 | 152 | 115 | 47 | 28 | 0.961111 | 0.948595 | 0.910354 |
| off | `20260428_thesis_consistency_cleanup_off` | 1542 | 160 | 114 | 55 | 27 | 0.962500 | 0.944142 | 0.910329 |

图表对应：`fig_chap05_postprocess_ablation.{pdf,png}`

## 视频稳定性指标

来源文件：

- `iter_01/analysis/summary.json`
- `iter_01/analysis/event_timeline.json`
- `iter_01/artifacts/main/pulled/direct_video_metrics_*/frame_detections.jsonl`

| smooth window | campaign | 帧数 | 检测保持率 | 闪烁窗口数 | 闪烁帧数 | 连续无输出段数 | 最长无输出段/帧 | frame_proc/ms | model_execute/ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `20260428_thesis_consistency_video_smooth1` | 437 | 0.981693 | 3 | 5 | 2 | 5 | 11.811 | 8.359 |
| 5 | `20260428_thesis_consistency_video_smooth5` | 437 | 0.981693 | 3 | 5 | 2 | 5 | 11.951 | 8.365 |

图表对应：`fig_chap05_video_stability.{pdf,png}`

说明：视频实验缺少逐帧人工标注，因此上述“检测保持率”和“连续无输出段”只描述连续输出稳定性，不作为视频级 precision、recall 或 mAP。

## 定性示例图

训练端示例来源：

- 原始文件：`/home/ywj/elevator_ai/runs/detect/elevator_train_100epoch3/val_batch0_pred.jpg`
- 生成产物：`fig_chap03_training_val_predictions.jpg`
- 用途：展示 YOLOv8n 自训练模型在验证集上的预测输出形态，不替代 `results.csv` 中的训练端定量指标。

板端示例来源：

- campaign：`20260419_phase3_3_full_val_synced`
- 原始图像：`/home/ywj/elevator_ai/datasets/PandE/personAndEbike/images/val/`
- 检测输出：`iter_01/artifacts/val_*/pulled/detections.jsonl`
- 筛选统计：`iter_01/artifacts/val_*/pulled/per_image.csv`
- 选图规则：成功样本、同时包含 `person` 与 `ebike`、两类均有 TP、无 FP/FN；在候选样本中按验证集顺序分位抽取 6 张。
- 采用样本：`1 (1002).jpg`、`1 (1554).jpg`、`1 (2186).jpg`、`1 (291).jpg`、`1 (4087).jpg`、`1 (998).jpg`
- 生成产物：`fig_chap05_board_val_examples.jpg`
- 用途：展示 Hi3516DV500 板端检测输出形态，定量结论仍以 720 张完整验证集统计为准。

## 图表生成

图表脚本：`figures/gen_fig_chap05_results.py`

输出目录：

- `figures/`
- `paper/image/generated/`

本轮图表生成命令：

```bash
cd /home/ywj/elevator_ai/thesis_undergrad
/home/ywj/miniconda3/bin/python figures/gen_fig_chap05_results.py
```

运行结果：成功生成所有第五章图表，未出现 `skip fig_chap05_nms_sensitivity`、`skip fig_chap05_postprocess_ablation` 或 `skip fig_chap05_video_stability`。
