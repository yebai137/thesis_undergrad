# Runtime Latency Audit

审计日期：2026-04-27

## Question

论文中出现“平均单图推理时延约为 `1119.510 ms`”，但项目中代表性视频片段又能在板端连续运行，甚至有超过 `20 fps` 的运行证据。二者看起来冲突，需要先定位指标来源，再决定论文口径。

## Root Cause Summary

`1119.510 ms` 不是 OM 模型裸推理时延，也不是连续视频模式的帧间耗时。它来自 full-val 的 **batch JPEG 图像验证链路端到端单图处理耗时**。

该链路按单张 JPEG 反复进入板端 batch 运行路径，耗时包含：

- JPEG 输入与媒体链路配置
- VDEC/VPSS 解码或兜底路径
- 预处理到模型输入格式
- NPU 执行
- YOLO 输出解析与后处理
- 结果图保存与结构化日志写出

因此，它可以作为“板端验证链路可复查性与批量图像验证成本”的证据，但不能写成“OM 模型平均推理时延”。

## Evidence

### Full-Val Summary

来源：

- `/home/ywj/elevator_ai/doc/reports/2026-04-19_Phase3_3_Full_Val_Metrics.md`
- `/home/ywj/elevator_ai/logs/direct_runs/20260419_phase3_3_full_val_synced/iter_01/analysis/performance_summary.json`

关键数值：

- total images: `720`
- success_count: `720`
- failure_count: `0`
- fallback_count: `667`
- total_elapsed_ms: `806047.504`
- average_elapsed_ms: `1119.510`
- images_per_second: `0.893`

### Per-Image Distribution

来源：

- `/home/ywj/elevator_ai/logs/direct_runs/20260419_phase3_3_full_val_synced/iter_01/artifacts/*/pulled/per_image.csv`

重新统计结果：

| 分组 | 数量 | 平均耗时/ms | 中位数/ms | 最小/ms | 最大/ms |
|---|---:|---:|---:|---:|---:|
| 全部样本 | 720 | 1119.510 | 1202.904 | 135.632 | 1753.188 |
| fallback 样本 | 667 | 1197.284 | 1202.924 | 1135.386 | 1753.188 |
| 非 fallback 样本 | 53 | 140.731 | 136.666 | 135.632 | 163.912 |

解释：

- full-val 均值被 `667/720` 的 fallback 样本主导。
- 非 fallback 的约 `141 ms` 也仍是单图端到端 batch 路径耗时，不是纯 NPU 推理时延。

### Code Path

batch 计时来源：

- `/home/ywj/elevator_ai/board/src/elevator_yolo.c`
  - `elevator_now_ms()` 使用 `CLOCK_MONOTONIC`
  - batch 循环在 `elevator_run_single_batch_image(...)` 前后计时
  - `report.elapsed_ms = elapsed_ms`
- `/home/ywj/elevator_ai/board/src/elevator_batch.c`
  - `elevator_batch_eval_note_run(...)` 累加 `total_elapsed_ms`
  - finalize 阶段计算 `average_elapsed_ms = total_elapsed_ms / success_count`

fallback 证据：

- `/home/ywj/elevator_ai/board/src/elevator_yolo.c`
  - JPEG payload 无法从 infer channel 及时取帧时进入 `jpeg_infer_fallback`
  - fallback 后使用 base frame 缩放到模型输入尺寸，再完成推理和保存
- `/home/ywj/elevator_ai/logs/direct_runs/20260419_phase3_3_full_val_synced/iter_01/artifacts/val_0000/stdout.txt`
  - 日志可见 `jpeg infer fallback engaged after 1 infer wait retries`
  - 日志可见 `jpeg infer fallback active: scale base frame 1920x1080 -> 640x640 for inference`

## Video Pipeline Evidence

视频链路是另一类证据，不能与 full-val 图像 batch 耗时混用。

来源：

- `/home/ywj/elevator_ai/doc/reports/2026-04-19_Phase3_3_Test5_Repair_Evidence.md`
- `/home/ywj/elevator_ai/doc/reports/2026-04-19_Phase3_3_Test5_Demo_Candidates.md`

关键证据：

- repaired `test5` native board replay 使用 source-timed 单次播放。
- final clean replay:
  - processed_frame_count: `437`
  - summary frame_count: `437`
  - summary duration_ms: `14885`
- final debug replay:
  - processed_frame_count: `437`
  - summary frame_count: `437`
  - summary duration_ms: `14884`
- source contract:
  - `30 fps`
  - `437` frames
  - `14.566667 s`

解释：

- final native replay 证明该代表性视频链路能完整处理 source-timed 约 `30 fps` 的连续帧。
- 这支持“板端连续视频链路具备实时或准实时运行能力”的判断。
- 但该视频证据缺少逐帧人工标注，因此只能作为运行节奏和机器侧输出稳定性证据，不能替代图像验证集的检测指标。

## Thesis Wording Decision

应采用：

- “板端 batch 图像验证链路端到端平均单图处理耗时约为 `1119.510 ms`。”
- “代表性视频片段在 source-timed native replay 中完成连续帧处理，机器侧统计用于观察输出稳定性。”

不应采用：

- “平均单图推理时延约为 `1119.510 ms`。”
- “OM 模型平均推理时延约为 `1119.510 ms`。”
- “由于单图 `1119.510 ms`，所以视频链路不能达到实时。”
- “由于视频链路约 `30 fps`，所以图像 full-val batch 链路也具备同等吞吐。”

## Segmented Instrumentation Experiment Design

本轮应新增分段计时 instrumentation，而不是继续争论 `1119.510 ms` 的语义。实验目标不是证明某个预设结论，而是把 batch 图像验证、连续视频 replay 与 OM/NPU 裸执行时间拆开。

### Instrumentation Fields

工程侧结构化输出应至少包含以下字段：

| 字段 | 含义 | 论文口径 |
|---|---|---|
| `frame_proc_ms` | 单帧核心处理路径耗时，包含预处理、NPU 执行、后处理、时序平滑、渲染/OSD；不应包含 batch 外围启动与保存成本 | 可作为单帧板端处理拆解入口 |
| `prepare_ms` | 选择/准备推理帧，包括 fallback 缩放准备 | 解释 JPEG fallback 与视频 ext frame 的差异 |
| `preprocess_ms` | 输入帧转 BGR planar 等模型输入预处理 | 预处理成本 |
| `input_update_ms` | 将预处理结果更新到 NPU 输入 buffer | 输入拷贝/同步成本 |
| `model_execute_ms` | `sample_common_svp_npu_model_execute(...)` 包围的 OM/NPU 执行时间 | 最接近“裸 OM/NPU 推理时延”的工程观测值 |
| `output_fetch_ms` | 输出 buffer 获取与维度解析 | 输出取回成本 |
| `postprocess_ms` | `elevator_parse_raw_outputs(...)`，含解码、阈值、NMS/清理等 | YOLO 后处理成本 |
| `temporal_ms` | hold/tracker/smoother 等时序逻辑 | 视频稳定性额外成本 |
| `render_prepare_ms` | 检测结果转渲染结构 | 可视化准备成本 |
| `render_ms` | 框绘制 | 可视化成本 |
| `osd_ms` | OSD panel 与 score 渲染 | OSD 成本 |

### Output Contract

新增证据应写入：

- batch 模式：
  - `per_image.csv`：每张图增加上述分段列。
  - `detections.jsonl`：每行增加 `timing_ms` 对象。
  - `summary.json`：增加 `timing_ms_average`。
- file/native replay 模式：
  - `frame_counts.csv`：逐帧增加上述分段列。
  - `frame_detections.jsonl`：每帧增加 `timing_ms` 对象。
  - `video_metrics_summary.json`：增加 `timing_ms_average`。

## Segmented Instrumentation Result

2026-04-27 已完成新增 instrumentation 的真实板端重跑，证据记录见：

- `/home/ywj/elevator_ai/thesis_undergrad/notes/timing_instrumentation_result_20260427.md`
- `/home/ywj/elevator_ai/logs/direct_runs/20260427_timing_instrumentation/iter_01`
- `/home/ywj/elevator_ai/logs/direct_runs/20260427_timing_instrumentation/iter_02`

本轮只跑计划中的 sanity batch 与 source-full 视频，不先跑完整 720 张 full-val。

### Batch Sanity Result

设置：验证集 50 张图像，板端 batch 模式，`score=0.15`，`nms=0.45`。

| 指标 | 均值/ms | 中位数/ms | 解释 |
|---|---:|---:|---|
| `elapsed_ms` | 1123.300 | 1202.895 | batch 图像验证链路端到端单图耗时 |
| `frame_proc_ms` | 21.459 | 21.644 | 单帧核心处理路径耗时 |
| `model_execute_ms` | 8.208 | 8.180 | OM/NPU 模型执行调用包围计时 |
| `preprocess_ms` | 1.220 | 1.205 | 模型输入预处理 |
| `postprocess_ms` | 0.019 | 0.017 | YOLO 输出解析与后处理 |
| `render_ms` | 3.271 | 3.157 | 检测框绘制 |
| `osd_ms` | 1.799 | 1.796 | OSD 渲染 |

fallback 分组结果：

| 分组 | 数量 | `elapsed_ms` 均值/ms | `frame_proc_ms` 均值/ms | `model_execute_ms` 均值/ms |
|---|---:|---:|---:|---:|
| 非 fallback | 4 | 149.794 | 15.710 | 8.351 |
| fallback | 46 | 1207.953 | 21.959 | 8.196 |

解释：

- sanity batch 的 `elapsed_ms` 仍与 full-val 的 `1119.510 ms` 处于同一数量级，说明二者同属 batch/JPEG 验证链路口径。
- `frame_proc_ms` 与 `model_execute_ms` 显著低于 `elapsed_ms`，说明 batch 外围输入、媒体链路、fallback 和结果写出等成本不能被误认为 OM/NPU 执行时间。
- fallback 拉高 `elapsed_ms`，但没有同步拉高 `model_execute_ms`。

### Source-Full Video Result

设置：代表性视频 `437` 帧，`30 fps`，约 `14.58 s`，板端 source-full/file 模式，`--no-osd`。

| 指标 | 均值/ms | 中位数/ms | 解释 |
|---|---:|---:|---|
| `frame_proc_ms` | 11.870 | 12.077 | 连续视频路径单帧核心处理 |
| `model_execute_ms` | 8.407 | 8.390 | OM/NPU 模型执行调用包围计时 |
| `preprocess_ms` | 1.177 | 1.166 | 模型输入预处理 |
| `postprocess_ms` | 0.017 | 0.018 | YOLO 输出解析与后处理 |
| `render_ms` | 2.217 | 2.450 | 检测框绘制 |
| `osd_ms` | 0.000 | 0.000 | 本次使用 `--no-osd` |

解释：

- source-full 视频中的 `frame_proc_ms` 均值约 `11.870 ms`，与既有视频链路能够按 source-timed 方式处理连续帧的观察相符。
- `model_execute_ms` 均值约 `8.407 ms`，可作为本轮板端模型执行阶段的工程观测值，但不应泛化成所有输入、所有后处理配置下的产品 SLA。
- `video_metrics_summary.json` 中 `duration_ms=7234.0` 是板端机器侧处理时间戳跨度，不是源视频实际时长；源视频实际时长应以 `437` 帧、`30 fps`、约 `14.58 s` 为准。

### Experimental Protocol

建议按三组运行，且所有结论必须来自真实板端输出：

1. **Batch JPEG 小样本 sanity run**
   - 选取 `10--30` 张验证图像。
   - 目的：确认 `elapsed_ms` 与 `frame_proc_ms` 的差距，拆出 batch 外围开销。
   - 重点看：`elapsed_ms - frame_proc_ms`、`fallback_used`、`prepare_ms`、`model_execute_ms`。
2. **Batch JPEG full-val rerun**
   - 对 720 张验证图像重跑一次新 binary。
   - 目的：给论文中 batch 图像验证链路补充分段均值。
   - 重点看：fallback 与非 fallback 两组的 `timing_ms_average`。
3. **Source-timed video replay rerun**
   - 使用已有代表性视频，保持 native replay / source-timed 设置。
   - 目的：解释视频链路为何能达到约 `20--30 fps`，并确认 `model_execute_ms` 是否明显低于 batch `elapsed_ms`。
   - 重点看：`frame_proc_ms`、`model_execute_ms`、`postprocess_ms` 与实际 `frame_count / duration_ms`。

### Thesis Use Rule

当前已完成 sanity batch 与 source-full 视频重跑，论文可以写：

- 已有 `1119.510 ms` 是 batch 图像验证链路端到端耗时。
- sanity batch 中 `frame_proc_ms` 均值约 `21.459 ms`，`model_execute_ms` 均值约 `8.208 ms`。
- source-full 视频中 `frame_proc_ms` 均值约 `11.870 ms`，`model_execute_ms` 均值约 `8.407 ms`。
- 上述分段值来自新增 instrumentation 的真实板端输出，可用于解释 batch 外围耗时与模型执行阶段耗时的区别。

不能写：

- “已证明 OM/NPU 裸推理达到某 fps/某 ms”。
- “1119ms 是 OM/NPU 裸推理时延”。
- “source-full 视频分段计时已经等同于完整产品 SLA”。
