# Academic Pipeline Round 1 Integrity Audit

审计日期：2026-04-27  
审计入口：`academic-pipeline` Stage 2.5 Integrity  
基线提交：`e67c44a baseline: current thesis draft before academic pipeline iteration`  
远端：`https://github.com/yebai137/thesis_undergrad.git`，`main` 已推送  

## 1. 编译与仓库状态

| 项目 | 结果 | 说明 |
|---|---:|---|
| PDF 编译 | PASS | `paper/main.pdf` 可生成 |
| PDF 页数 | 47 | A4 页面，距离目标 48--52 页略少 |
| LaTeX 硬错误 | PASS | 未发现 `LaTeX Error`、undefined citation、undefined reference |
| 字体警告 | MINOR | `main.log` 中存在字体形状替代警告，不影响 PDF 生成 |
| 当前 git baseline | PASS | 独立仓库已初始化并推送 `main` |

## 2. 引用完整性

### 2.1 已引用且存在于 `main.bib`

正文 `\cite{}` 中使用的 key 均能在 `paper/main.bib` 中找到：

- `chen2021aqd`
- `chen2021scaleaware`
- `han2016deep`
- `hinton2015distilling`
- `howard2019mobilenetv3`
- `jacob2018quantization`
- `lin2023elevatorcounting`
- `redmon2017yolo9000`
- `shi2016edge`
- `shrivastava2016ohem`
- `stacker2021deployment`
- `tan2019efficientnet`
- `tan2020efficientdet`
- `zhou2023edgeyolo`

### 2.2 暂未引用的 BibTeX key

以下 key 存在于 `main.bib` 但未被正文引用，可在后续第二章扩写或文献精简时处理：

- `cao2017openpose`
- `carion2020detr`
- `chen2018gradnorm`
- `dong2019hawq`
- `feichtenhofer2019slowfast`
- `kendall2018multi`
- `wojke2017deepsort`
- `zhang2022bytetrack`

### 2.3 Citation policy

后续新增参考文献必须满足：

1. 先能在公开来源或已有 BibTeX 中核验，再写入 `main.bib`。
2. 不生成无法确认来源的 BibTeX。
3. 若只作为待核验材料，先放入 `references/`，不要直接进入正文引用。

## 3. 数值与证据追溯

### 3.1 已有证据支撑的核心数值

| 正文数值 | 审计结论 | 证据入口 |
|---|---|---|
| 720 张验证图像 | PASS | `doc/reports/2026-04-19_Phase3_3_Full_Val_Metrics.md` |
| success=720、failure=0 | PASS | 同上 |
| precision=0.901、recall=0.923、F1=0.912、mAP@0.5=0.910 | PASS | 同上，由原始值四舍五入 |
| person mAP@0.5=0.869、ebike mAP@0.5=0.952 | PASS | 同上，由原始值四舍五入 |
| 阈值 0.20--0.35 下 F1=0.915--0.922 | PASS | `doc/reports/2026-04-25_Thesis_Threshold_Sensitivity_Recompute.md` |
| ebike recall >= 0.956 | PASS | 同上 |
| full-val batch 平均单图处理耗时 1119.510 ms | PASS_WITH_WORDING_RISK | 只能解释为 batch 图像验证链路端到端耗时 |
| 50 张 batch 分段计时：`frame_proc_ms=21.459`、`model_execute_ms=8.208` | PASS | `notes/timing_instrumentation_result_20260427.md` |
| 437 帧视频分段计时：`frame_proc_ms=11.870`、`model_execute_ms=8.407` | PASS | 同上 |

### 3.2 需要保持的运行时口径

- `1119.510 ms` 只能写作“板端 batch 图像验证链路端到端平均单图处理耗时”。
- `1119.510 ms` 不能写作“OM 模型推理时延”“NPU 裸推理时延”或“连续视频帧间耗时”。
- `model_execute_ms` 是当前二进制、模型、阈值和板端环境下的工程观测值，不是产品 SLA。
- 50 张 batch sanity 与 437 帧视频分段计时可解释口径差异，但不能替代完整 720 张 full-val 的检测指标。

## 4. 正文风险扫描

### 4.1 Blocker

暂未发现会导致基线不可编译、引用缺失或数值明显伪造的 blocker。

### 4.2 Major

1. **正文仍显得偏“证据审计口吻”**  
   `chap05` 中多处直接使用“证据边界”等表达。该词能帮助内部审计，但进入本科论文正文时略像写作说明。后续建议改成“实验范围”“适用条件”“结果解释边界”等更自然的学术表述。

2. **第 2 章仍可扩充但必须聚焦**  
   论文目前 47 页，距 48--52 页目标略少。优先扩充 YOLO 检测、边缘部署、量化/模型压缩、部署一致性与电梯安全视觉相关基础，不通过空泛段落凑页数。

3. **第 5 章图表需要视觉复查**  
   当前图表已引入总体/分类别指标、阈值曲线和分段时延图，但仍需按 `academic-plotting` 标准检查黑白可读性、标签遮挡、字号和 caption 与正文一致性。

4. **贡献链需要继续统一语言**  
   三项贡献已经基本固定为“场景任务建模、边缘兼容迁移接口契约、部署一致性评价”，后续摘要、绪论、方法、实验、结论需继续保持同一组关键词，避免回到“难例增强/模型规模对比”这类未完成贡献。

### 4.3 Minor

1. **摘要使用约数 `1120 ms`，正文与结论使用 `1119.510 ms`**  
   二者不矛盾，但建议正文首次给精确数，摘要与结论使用约数并明确 batch 链路口径。

2. **`main.bib` 存在未引用条目**  
   不影响编译。后续可在第二章自然引用，或最终精简。

3. **LaTeX 字体替代警告**  
   当前不影响输出，除非学校模板检查对字体日志有特殊要求，否则可暂缓。

## 5. 后续修订约束

1. 正文不得出现内部路径、工程 campaign、Phase/test 编号、Agent 或答辩元叙事。
2. 未完成实验只能作为“不足与展望”，不能写成已完成结果。
3. 图表只能使用已有真实数据或新增真实分段计时数据。
4. 每次修改 `paper/` 后必须运行 `make pdf`。
5. 每轮 revision 应保持小提交，方便回滚和比较。

## 6. Round 1 结论

当前论文基线可编译、核心数值可追溯，`1119.510 ms` 的口径已基本修正为 batch 端到端链路耗时。下一轮应进入独立评审，重点评估：主线是否足够清楚、第二章是否需要有效扩充、第五章图表是否存在排版负优化、以及整篇论文是否保持本科毕业论文而非顶会论文的表达尺度。
