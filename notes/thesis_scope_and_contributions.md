# Thesis Scope And Contributions

## Final Thesis Positioning

论文题目：

`基于深度学习的电梯边缘AI安全视觉关键技术研究与实现`

论文落地解释：

在电梯轿厢这一高约束空间中，围绕 `person + ebike` 双目标检测，研究如何将自训练 YOLO 检测模型可靠迁移到海思/昇腾类边缘开发板，并通过可复查实验评价检测性能、阈值行为和部署一致性。

## Contribution Package

### Contribution 1: Elevator dual-task problem formalization

把电梯轿厢中的人/电动车检测从“普通目标检测”进一步细化为：

- 遮挡与重叠显著的双任务检测
- 反光、门口大框干扰、局部可见等 hard cases 主导性能上限
- 边缘部署后的阈值行为和后处理稳定性与离线指标同样重要

### Contribution 2: Edge-compatible migration contract

把训练权重到边缘设备运行的过程从“格式转换”提升为可检查的迁移契约，重点约束：

- 输入尺寸、颜色通道、归一化和缩放方式
- `person / ebike` 类别数量、类别顺序和标签名称
- YOLO 输出张量维度、坐标格式和置信度含义
- 置信度阈值、NMS 阈值和类别处理方式
- 模型文件、板端二进制、成功样本数和平均时延等运行状态

### Contribution 3: Deployment consistency methodology

不是只报告“模型导出了、板子跑起来了”，而是把以下问题变成论文的一部分：

- 板端完整验证集上的检测精度与分类别表现
- 阈值变化对 `person / ebike` 召回率和 F1 的影响
- 成功样本数、失败样本数、batch 图像验证端到端耗时和分段计时等运行时可靠性指标
- 代表性视频片段的机器侧输出稳定性观察

## Runtime Metric Interpretation

当前证据中必须区分两条运行链路：

1. **图像 full-val / batch JPEG 验证链路**
   - `1119.510 ms` 来自 720 张验证图像的板端 batch 模式端到端单图处理耗时。
   - 该耗时统计的是 `elevator_run_single_batch_image(...)` 外围的完整处理时间，包含 JPEG 输入、媒体初始化/解码、fallback、预处理、NPU 执行、后处理、结果写出等开销。
   - 该数值不应写成“OM 模型裸推理时延”或“连续视频模式帧间耗时”。
2. **连续视频 / file replay 链路**
   - 项目中另有代表性视频片段的板端运行证据，例如 repaired `test5` native board replay 在 source-timed 单次播放下完成 `437/437` 帧，耗时约 `14.885 s`，对应约 `29 fps` 的视频处理节奏。
   - 该证据可用于说明视频链路具备连续帧运行能力，但由于缺少逐帧人工标注，不应替代图像验证集的 precision、recall 或 mAP 结论。
3. **分段计时 instrumentation 链路**
   - 2026-04-27 的 sanity batch 重跑显示，50 张图像 batch 模式下 `elapsed_ms` 均值约 `1123.300 ms`，但 `frame_proc_ms` 均值约 `21.459 ms`，`model_execute_ms` 均值约 `8.208 ms`。
   - 同日 source-full 视频重跑显示，连续视频路径 `frame_proc_ms` 均值约 `11.870 ms`，`model_execute_ms` 均值约 `8.407 ms`。
   - 这些分段结果证明 batch 图像验证链路的端到端耗时与 OM/NPU 模型执行阶段不是同一指标。

因此，论文默认用语应为：

- 对 `1119.510 ms`：写作“板端 batch 图像验证链路端到端平均单图处理耗时约为 1119.510 ms”。
- 对视频链路：写作“代表性视频片段完成 source-timed 连续帧处理，机器侧统计用于观察输出稳定性”。
- 对分段计时：写作“新增分段计时显示，模型执行阶段的工程观测值约为 8 ms 量级；该数值用于解释链路拆解，不作为所有场景下的产品 SLA”。
- 避免写作：“平均单图推理时延”“OM 模型平均推理时延”“当前系统不具备视频实时性”“模型执行阶段保证任意输入均达到固定帧率”。

## Planned / Follow-up Experiments

以下内容保留为待补实验或后续工作，除非未来补齐真实实验结果，否则不作为当前已完成主体贡献：

- hard-case subset weighting
- targeted augmentation
- lightweight model-scale comparison
- `PyTorch -> ONNX -> OM -> board` 四阶段逐样本边框漂移对齐
- hard-case taxonomy 分组定量评测
- 完整 720 张 full-val 的分段时延重跑

## What We Intentionally Do Not Claim

- 不声称做了完整的电梯安全 foundation model
- 不声称覆盖了全部异常行为场景
- 不声称当前所有实验都已完成
- 不把尚未补齐的 ablation 写成既成事实
- 不声称已经完成四阶段逐样本一致性实测
- 不声称 batch 图像验证耗时等同于 OM 裸推理时延或连续视频帧率
- 不把 50 张 sanity batch 和单个代表性视频的分段计时泛化为所有输入、所有阈值和所有后处理配置下的产品实时性保证
