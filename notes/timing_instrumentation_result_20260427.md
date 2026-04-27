# Timing Instrumentation Result 20260427

审计日期：2026-04-27

## 目的

本实验用于解释论文中 `1119.510 ms` 与板端连续视频可运行帧率之间的表面矛盾。核心问题不是重新追求一个更好看的时延数值，而是把板端运行拆成可复查的分段指标：

- `elapsed_ms`：batch 图像验证链路端到端单图耗时，包含外围输入、媒体链路、推理、后处理与结果写出。
- `frame_proc_ms`：单帧核心处理路径耗时，包含预处理、NPU 执行、后处理、时序逻辑和渲染等内部处理。
- `model_execute_ms`：包围 OM/NPU 模型执行调用的工程计时，最接近“模型执行阶段耗时”的板端观测值。

## 运行概况

本轮实验 campaign 为 `20260427_timing_instrumentation`，采用真实板端链路：

`server -> 127.0.0.1:10023 -> Windows -> board`

模型和二进制指纹如下：

| 项目 | MD5 |
|---|---|
| board binary `elevator_yolo` | `27ac0420aa05106ddcb142bdb209062d` |
| OM model `yolov8.om` | `e3d03dc1627d6ba44baa7211951c9dbe` |

对应证据入口：

- batch sanity：`/home/ywj/elevator_ai/logs/direct_runs/20260427_timing_instrumentation/iter_01`
- source-full 视频：`/home/ywj/elevator_ai/logs/direct_runs/20260427_timing_instrumentation/iter_02`
- campaign manifest：`/home/ywj/elevator_ai/logs/direct_runs/20260427_timing_instrumentation/manifest.md`

## 实验 1：Batch Sanity

实验设置：

- 输入：验证集前 50 张图像，分为 `offset=0, limit=25` 与 `offset=25, limit=25` 两个 chunk。
- 模式：板端 batch 图像验证。
- score threshold：`0.15`
- NMS threshold：`0.45`
- 成功样本数：`50`
- 失败样本数：`0`
- fallback 样本数：`46`

主要统计：

| 指标 | 均值/ms | 中位数/ms | 最小/ms | 最大/ms |
|---|---:|---:|---:|---:|
| `elapsed_ms` | 1123.300 | 1202.895 | 138.917 | 1645.381 |
| `frame_proc_ms` | 21.459 | 21.644 | 15.092 | 24.178 |
| `model_execute_ms` | 8.208 | 8.180 | 8.160 | 8.696 |
| `preprocess_ms` | 1.220 | 1.205 | 1.189 | 1.430 |
| `postprocess_ms` | 0.019 | 0.017 | 0.015 | 0.060 |
| `render_ms` | 3.271 | 3.157 | 1.388 | 5.517 |
| `osd_ms` | 1.799 | 1.796 | 1.674 | 1.987 |

fallback 分组：

| 分组 | 数量 | `elapsed_ms` 均值/ms | `frame_proc_ms` 均值/ms | `model_execute_ms` 均值/ms |
|---|---:|---:|---:|---:|
| 非 fallback | 4 | 149.794 | 15.710 | 8.351 |
| fallback | 46 | 1207.953 | 21.959 | 8.196 |

结论：

- batch sanity 与既有 full-val 结果同向：`elapsed_ms` 主要反映 batch/JPEG 验证外围链路成本，不应写成 OM/NPU 裸推理时延。
- 即使 batch `elapsed_ms` 均值约为 `1123 ms`，同一批样本的 `frame_proc_ms` 均值约为 `21.459 ms`，`model_execute_ms` 均值约为 `8.208 ms`。
- fallback 样本显著拉高 `elapsed_ms`，但没有显著拉高 `model_execute_ms`，说明 `1119.510 ms` 的主要语义是 batch 端到端验证链路耗时，而不是模型执行阶段耗时。

## 实验 2：Source-Full 视频

实验设置：

- 输入：`test5.mp4` 转换得到的 H.264 elementary stream。
- 源视频元信息：`437` 帧，`30 fps`，约 `14.58 s`，分辨率 `1280x720`。
- 模式：板端 file/source-full 连续视频处理。
- score threshold：`0.15`
- NMS threshold：`0.45`
- smooth window：`5`
- 命令使用 `--no-osd`，因此 `osd_ms` 为 `0`。

主要统计：

| 指标 | 均值/ms | 中位数/ms | 最小/ms | 最大/ms |
|---|---:|---:|---:|---:|
| `frame_proc_ms` | 11.870 | 12.077 | 9.391 | 13.113 |
| `model_execute_ms` | 8.407 | 8.390 | 8.187 | 8.977 |
| `preprocess_ms` | 1.177 | 1.166 | 1.156 | 1.366 |
| `postprocess_ms` | 0.017 | 0.018 | 0.004 | 0.054 |
| `render_ms` | 2.217 | 2.450 | 0.003 | 3.405 |
| `osd_ms` | 0.000 | 0.000 | 0.000 | 0.000 |

板端资源摘要：

- resource samples：`25`
- 平均 CPU 利用率：`3.536%`
- 最大 CPU 利用率：`9.259%`
- 平均进程 RSS：`3611.2 KB`
- NPU 利用率采样在活跃阶段出现约 `48--50` 的数值。

注意：

- `video_metrics_summary.json` 中的 `duration_ms=7234.0` 是机器侧处理时间戳跨度，不是源视频实际时长。
- 源视频时长应以输入元信息为准：`437` 帧、`30 fps`、约 `14.58 s`。
- `runtime_fidelity_summary.json` 因服务器侧缺少 `cv2` 标记为 `missing_fidelity_inputs`，但板端原始 `frame_counts.csv`、`frame_detections.jsonl` 和 `video_metrics_summary.json` 均已拉回，可用于分段计时证据。

## 对论文的写作结论

论文正文可以安全写入：

- `1119.510 ms` 是 720 张图像 full-val 中 **板端 batch 图像验证链路端到端平均单图处理耗时**。
- 新增分段计时表明，在 50 张 sanity batch 中，`frame_proc_ms` 均值约为 `21.459 ms`，`model_execute_ms` 均值约为 `8.208 ms`。
- 在 source-full 视频路径中，`frame_proc_ms` 均值约为 `11.870 ms`，`model_execute_ms` 均值约为 `8.407 ms`。
- 因此，batch 图像验证耗时与连续视频路径中的单帧核心处理时间不是同一指标，不能相互替代。

论文正文不应写入：

- “OM 模型平均推理时延约为 `1119.510 ms`”。
- “NPU 裸推理时延约为 `1119.510 ms`”。
- “由于 batch 单图耗时约 `1119 ms`，所以连续视频不能实时运行”。
- “视频 source-full 计时已经等同于完整产品实时性保证”。

## 后续可用图表

建议在第五章加入一张分段时延表或柱状图，区分：

1. batch `elapsed_ms`
2. batch `frame_proc_ms`
3. batch `model_execute_ms`
4. video `frame_proc_ms`
5. video `model_execute_ms`

图表标题建议使用“板端分段计时结果”，不要使用“推理时延对比”作为唯一标题，以免再次混淆 batch 外围链路与模型执行阶段。
