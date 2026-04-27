# Project Evidence Map

## Purpose

本文件把 `/home/ywj/elevator_ai` 已有工程证据映射到论文章节，避免后续写作时只记得“项目里做过”，却找不到可直接引用的材料。

## Chapter Mapping

当前论文主体为五章结构：

- Chapter 1：绪论
- Chapter 2：技术基础与相关工作
- Chapter 3：YOLO 双目标检测模型的边缘兼容迁移方法
- Chapter 4：数据集、场景风险与评测协议
- Chapter 5：实验结果与分析
- Conclusion / Appendix：结论、展望与补充复查表格

### Chapter 1 / Chapter 3

- 工程入口：
  - `/home/ywj/elevator_ai/README.md`
- 工程规则与系统边界：
  - `/home/ywj/elevator_ai/AGENTS.md`

用于支撑：

- 当前项目真实运行链路
- 电梯场景任务边界
- board-oriented deployment reality

### Chapter 3 / Chapter 5

- full-val 指标摘要：
  - `/home/ywj/elevator_ai/doc/reports/2026-04-19_Phase3_3_Full_Val_Metrics.md`
- 对应原始分析：
  - `/home/ywj/elevator_ai/logs/direct_runs/20260419_phase3_3_full_val_synced/iter_01/analysis/performance_summary.json`
  - `/home/ywj/elevator_ai/logs/direct_runs/20260419_phase3_3_full_val_synced/iter_01/analysis/overall_summary.json`

用于支撑：

- 全量验证基线
- 每类指标
- 720 张验证集板端结果
- `1119.510 ms` 作为 **batch 图像验证链路端到端平均单图处理耗时**，不是 OM 裸推理时延，也不是连续视频模式 FPS

补充解释证据：

- batch 计时来源：
  - `/home/ywj/elevator_ai/board/src/elevator_yolo.c`
    - `elevator_run_single_batch_image(...)` 外围计时
    - `report.elapsed_ms = elapsed_ms`
  - `/home/ywj/elevator_ai/board/src/elevator_batch.c`
    - `elevator_batch_eval_note_run(...)` 累加 `total_elapsed_ms`
    - `average_elapsed_ms = total_elapsed_ms / success_count`
- fallback 证据：
  - `/home/ywj/elevator_ai/logs/direct_runs/20260419_phase3_3_full_val_synced/iter_01/artifacts/val_0000/stdout.txt`
  - 日志中可见 `jpeg infer fallback engaged after 1 infer wait retries` 与 `scale base frame 1920x1080 -> 640x640 for inference`
- per-image 分布：
  - `/home/ywj/elevator_ai/logs/direct_runs/20260419_phase3_3_full_val_synced/iter_01/artifacts/*/pulled/per_image.csv`
  - 720 张中 `667` 张触发 fallback；fallback 平均约 `1197 ms`，非 fallback 平均约 `141 ms`

### Chapter 3 / Chapter 5

- campaign manifest：
  - `/home/ywj/elevator_ai/logs/direct_runs/20260419_phase3_3_full_val_synced/manifest.md`

用于支撑：

- `server -> Windows -> board` 运行链路
- board 目标设备与 staging 方式
- true-board evidence collection

### Chapter 4 / Chapter 5 / Appendix

- promote round report：
  - `/home/ywj/elevator_ai/logs/direct_runs/20260417_phase3_mature_fix/round_report.md`

用于支撑：

- fixed review set：`test6 -> test3 -> test2 -> test5 -> batch gate`
- hard-case 分析入口
- count-aware review 作为辅助稳定性证据

### Chapter 5 / Appendix

- test5 修复与 demo 报告：
  - `/home/ywj/elevator_ai/doc/reports/2026-04-19_Phase3_3_Test5_Repair_Evidence.md`
  - `/home/ywj/elevator_ai/doc/reports/2026-04-19_Phase3_3_Test5_Demo_Candidates.md`

用于支撑：

- 电动车可见性问题的代表性案例
- demo candidate 说明
- 现有工程面向演示与验证的输出组织方式
- 连续视频链路与 batch 图像验证链路不同；代表性视频片段可用于说明 source-timed 连续帧运行和机器侧稳定性观察
- final native board replay 证据中，`test5_clean/debug` 均完成 `437/437` 帧，summary duration 约 `14884--14885 ms`，对应约 `29 fps` 的 source-timed 视频处理节奏

### Chapter 5

- 阈值敏感性后验重算：
  - `/home/ywj/elevator_ai/doc/reports/2026-04-25_Thesis_Threshold_Sensitivity_Recompute.md`

用于支撑：

- 基于既有板端检测输出的多阈值后验筛选
- `0.20 / 0.25 / 0.30 / 0.35` 置信度阈值下的 precision、recall、F1、分类别召回率
- 说明阈值重算不是新的板端推理，也不是完整跨阶段一致性实测

### Chapter 5 / Conclusion

- 分段计时 instrumentation 结果：
  - `/home/ywj/elevator_ai/thesis_undergrad/notes/timing_instrumentation_result_20260427.md`
  - `/home/ywj/elevator_ai/logs/direct_runs/20260427_timing_instrumentation/iter_01/analysis/merged_summary.json`
  - `/home/ywj/elevator_ai/logs/direct_runs/20260427_timing_instrumentation/iter_01/artifacts/chunk00/pulled/per_image.csv`
  - `/home/ywj/elevator_ai/logs/direct_runs/20260427_timing_instrumentation/iter_01/artifacts/chunk25/pulled/per_image.csv`
  - `/home/ywj/elevator_ai/logs/direct_runs/20260427_timing_instrumentation/iter_02/artifacts/main/pulled/direct_video_metrics_20260427_timing_instrumentation_iter_02/video_metrics_summary.json`
  - `/home/ywj/elevator_ai/logs/direct_runs/20260427_timing_instrumentation/iter_02/artifacts/main/pulled/direct_video_metrics_20260427_timing_instrumentation_iter_02/frame_counts.csv`
  - `/home/ywj/elevator_ai/logs/direct_runs/20260427_timing_instrumentation/iter_02/artifacts/main/board_resource_summary.json`

用于支撑：

- 50 张 sanity batch 中 `elapsed_ms`、`frame_proc_ms` 与 `model_execute_ms` 的差异
- source-full 视频路径中 `frame_proc_ms` 与 `model_execute_ms` 的分段观测
- `1119.510 ms` 不应解释为 OM/NPU 裸执行时延
- 连续视频路径具备较低单帧核心处理耗时的证据，但不替代带人工标注的图像验证集指标

## Immediate Citation Strategy

论文正文中：

1. 学术背景引用 `main.bib` 中的公开文献。
2. 项目自身结果以“本课题工程基线”“当前项目实测结果”“板端 full-val 基线”等方式叙述。
3. 需要追溯时，在附录或写作注释中补充文件路径，而不是把日志原文直接塞进正文。
4. 若某项只存在于 `notes/experiment_spec.md` 中，默认视为计划实验，不能直接写成已完成结果。

## Runtime Metric Wording Rules

1. `1119.510 ms` 只能写成“板端 batch 图像验证链路端到端平均单图处理耗时”。
2. 不得把 `1119.510 ms` 写成“OM 模型推理时延”“NPU 裸推理时延”或“视频帧间耗时”。
3. 视频链路证据应单独表述为“代表性视频片段机器侧统计”或“source-timed native replay 处理节奏”，不与图像验证集 mAP/precision/recall 混成同一指标。
4. 分段计时已经完成 sanity batch 与 source-full 视频重跑；论文可引用 `frame_proc_ms`、`model_execute_ms`、`preprocess_ms`、`postprocess_ms`、`render_ms/osd_ms`，但必须说明样本范围和运行模式。
5. 完整 720 张 full-val 尚未重跑分段 instrumentation，因此不能把 50 张 sanity batch 的均值直接替换原 full-val 的完整耗时统计。
