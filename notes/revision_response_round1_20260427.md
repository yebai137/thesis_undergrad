# Revision Response Round 1

日期：2026-04-27  
对应评审：`notes/academic_review_round1_20260427.md`  
修订阶段：Academic Pipeline Stage 4 Targeted Revision  

## 1. 修订总览

本轮修订目标是关闭 Round 1 中的 major 问题，同时保持中文本科毕业论文风格，不引入未验证实验结果。修订范围包括：

- 摘要、绪论、方法章、实验章和结论中的贡献口径。
- 第二章技术基础与相关工作的聚焦扩写。
- 第五章图表脚本与生成图的黑白可读性。
- 文献来源说明与引用一致性。

## 2. 对 Major 问题的回应

### M1. 部署一致性表述略强

处理结果：已修订。

主要动作：

- 将“部署一致性验证/闭环/同一条验证链路”等容易暗示全链路逐样本实证完成的说法，统一降调为“部署一致性评价”“评价框架”“板端证据链”。
- 将“边框一致性”改为“边框解释”“边框解释一致性设计”等更准确的表述。
- 在结论中明确当前结果主要支撑当前验证集与代表性片段范围内的双目标检测能力和可复查评价证据。

涉及文件：

- `paper/docs/abstract.tex`
- `paper/docs/chap01.tex`
- `paper/docs/chap03.tex`
- `paper/docs/chap04.tex`
- `paper/docs/chap05.tex`
- `paper/docs/conclusion.tex`

### M2. 正文仍有内部审计口吻

处理结果：已修订。

主要动作：

- 将第五章标题“实验设置与证据边界”改为“实验设置与评价范围”。
- 将“证据边界”替换为“适用范围”“实验适用范围”“评价范围”等论文正文表述。
- 将“写成”“伪装”“当前版本”等过程性表达从正文中移除或改写。
- 将“证明”类强措辞多处改为“表明”“说明”“支持”。

涉及文件：

- `paper/docs/chap01.tex`
- `paper/docs/chap03.tex`
- `paper/docs/chap04.tex`
- `paper/docs/chap05.tex`
- `paper/docs/conclusion.tex`

### M3. 第 5 章图表黑白可读性不足

处理结果：已修订。

主要动作：

- 在总体/分类别指标柱状图中加入 hatch 纹理和深色边框。
- 在分段计时柱状图中加入 hatch 纹理和深色边框。
- 在阈值敏感性曲线中加入不同线型，并将图例改为两行布局。
- 重新生成 `figures/` 与 `paper/image/generated/` 下的 PDF/PNG 图表。

涉及文件：

- `figures/gen_fig_chap05_results.py`
- `figures/fig_chap05_detection_metrics.*`
- `figures/fig_chap05_threshold_sensitivity.*`
- `figures/fig_chap05_timing_breakdown.*`
- `paper/image/generated/fig_chap05_detection_metrics.*`
- `paper/image/generated/fig_chap05_threshold_sensitivity.*`
- `paper/image/generated/fig_chap05_timing_breakdown.*`

### M4. 第 2 章可作为页数与质量的主要增量

处理结果：已修订。

主要动作：

- 增补 mAP@0.5 与部署评价之间的关系，说明为什么需要分类别指标、阈值重算和分段计时。
- 增补 DETR 作为相邻检测路线，与 YOLO 的边缘部署成熟度形成对比。
- 增补混合精度量化对部署行为的影响，用于解释边缘部署不是简单格式转换。
- 新增“相邻视觉任务与本文边界”，引用目标跟踪、姿态估计和视频识别相关工作，明确本文不扩展为完整视频理解任务。

涉及文件：

- `paper/docs/chap02.tex`
- `paper/main.bib`
- `references/curated_sources.md`

说明：

本轮未新增 BibTeX 条目，而是复用 `main.bib` 中已有条目并补充正文引用；因此没有引入未核验的新参考文献。

## 3. 编译与验证结果

本轮修订后已运行：

```bash
cd /home/ywj/elevator_ai/thesis_undergrad/paper
make pdf
```

结果：

- PDF 可编译。
- `paper/main.pdf` 页数为 49 页，位于 48--52 页目标范围内。
- 未发现 `LaTeX Error`、undefined citation、undefined reference 或 `Overfull` 硬问题。
- 引用 key 均能在 `paper/main.bib` 中找到。
- 正文扫描未发现内部路径、Phase/test 编号、Agent、答辩元叙事或将 `1119.510 ms` 写成 OM/NPU 裸推理时延的问题。
- 抽查第 5 章图表页，未发现文字遮挡或图注错位。

## 4. Remaining Limitations

以下内容仍作为论文局限或后续工作保留：

- 未完成 PyTorch、ONNX、OM 和板端四阶段逐样本统一匹配。
- 完整 720 张 full-val 尚未使用新增计时埋点重跑分段统计。
- 代表性视频片段缺少逐帧人工标注，不用于计算视频级 precision、recall 或 mAP。
- 人数统计、跌倒检测、跟踪和视频行为理解不作为本文主体贡献。
