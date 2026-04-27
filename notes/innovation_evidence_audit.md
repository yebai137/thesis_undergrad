# 创新点与证据矩阵审计

审计日期：2026-04-27

## 审计方法

本次审计按 `AGENTS.md` 中的 thesis 主线和 AI-research-SKILLs 使用约束执行，只借用以下方法视角：

- `brainstorming-research-ideas`：用于收敛半成型创新点，避免从既有工程发散出新课题。
- `systems-paper-writing`：只借用 Problem -> Gap -> Insight -> Design -> Evaluation 的证据组织方式，不按顶会系统论文包装。
- `ml-paper-writing`：用于检查贡献表述、证据边界和引用纪律，不生成或补写未核验引用。

本审计不新增论文实验结果，不判定未完成实验已经完成。

## 总体判断

当前论文最稳妥的创新点组合应收敛为三项：

1. 面向电梯轿厢的 `person + ebike` 双目标检测任务建模。
2. 自训练 YOLO 模型到海思/昇腾类边缘开发板的兼容迁移接口契约。
3. 面向安全视觉的部署一致性评价与可复查实验闭环。

其中，第 1 项和第 3 项证据最完整；第 2 项作为方法设计是成立的，但如果写成“完整跨阶段逐样本一致性实测”则证据不足。原 notes 中“视觉增强策略 / hard-case weighting / targeted augmentation / model-scale comparison”目前更适合作为计划实验或后续工作，不宜作为当前已完成主体创新点。

## 创新点与证据矩阵

| 候选创新点 | 建议定位 | 当前证据强度 | 可用证据 | 可写入正文的边界 | 风险与处理 |
|---|---|---:|---|---|---|
| 电梯轿厢 `person + ebike` 双目标检测任务建模 | 主创新点 1 | 高 | `paper/docs/chap01.tex` 中研究目标和贡献；`paper/docs/chap04.tex` 中风险分类；720 张验证集包含 person/ebike 两类 GT 与预测统计 | 可以写成“任务建模”“场景约束定义”“双目标检测问题抽象” | 不要声称提出全新检测算法；不要扩展成完整电梯安全视觉平台 |
| 场景风险分类：反光、门口结构、局部可见、拥挤重叠、尺度变化、低照边角 | 支撑性创新 / 分析工具 | 中-高 | `paper/docs/chap04.tex` 风险分类表；`paper/docs/chap05.tex` 对 person/ebike 误差差异的解释 | 可以写成误差解释维度和实验讨论框架 | 当前没有逐风险子集指标表，不应写成“已完成 hard-case 分组定量评测” |
| 自训练 YOLO 到 ONNX/OM/board 的兼容迁移链路 | 主创新点 2 | 中-高 | `paper/docs/chap03.tex` 迁移流程、接口契约、分阶段验证策略；主工程部署报告与专利交底文档中有 ONNX/OM/board 链路材料；full-val 板端运行证明 OM/board 端可执行 | 可以写成“兼容迁移方法”“接口契约”“分阶段检查策略” | 不要写成 PyTorch、ONNX、OM、board 四阶段逐样本指标已经完整对齐 |
| 输入、类别、输出、后处理、运行五类接口契约 | 主创新点 2 的核心表达 | 高 | `paper/docs/chap03.tex` 表 `tab:migration_contract`；`paper/docs/chap05.tex` 分类别 TP/FP/FN 反向说明类别契约基本成立 | 可以写成方法框架和排错准则 | 契约本身是方法性贡献，不等同于所有契约都有独立定量消融 |
| 板端完整验证集检测结果 | 实验主证据 | 高 | `doc/reports/2026-04-19_Phase3_3_Full_Val_Metrics.md`；`logs/direct_runs/20260419_phase3_3_full_val_synced/iter_01/analysis/performance_summary.json`；论文表 `board_overall_results` 与 `board_class_results` | 可以报告 720 张验证图像、success=720、failure=0、precision=0.901、recall=0.923、F1=0.912、mAP@0.5=0.910、batch 图像验证端到端平均单图处理耗时约 1119.510 ms | 需要保留“板端 batch 图像验证链路”口径；不要把该结果解释成 OM 裸推理时延、连续视频帧间耗时或实时产品性能 |
| 分类别安全分析：ebike 召回更稳定，person 更受遮挡/重叠影响 | 实验分析亮点 | 高 | `performance_summary.json` 中 person: recall 0.8879, mAP50 0.869；ebike: recall 0.9611, mAP50 0.952；`paper/docs/chap05.tex` 分类别结果 | 可以写成安全任务下分类别指标比总体指标更有解释力 | 不要过度解释为所有电梯场景中 ebike 都比 person 更容易检测，只能限定在当前验证集 |
| 阈值敏感性后验重算 | 主创新点 3 的实验证据 | 中-高 | `doc/reports/2026-04-25_Thesis_Threshold_Sensitivity_Recompute.md`；`paper/docs/chap05.tex` 表 `threshold_sensitivity_results` | 可以写成“基于既有板端检测输出的后验筛选重算”，说明阈值 0.20--0.35 下 F1 与 ebike recall 稳定性 | 必须强调不是重新板端推理、不是全阈值证明；只能评估源运行 score>=0.15 后保留候选 |
| 运行时可靠性：720 成功、0 失败、batch 图像验证端到端平均耗时 1119.510 ms | 主创新点 3 的实验证据 | 高 | full-val report、`performance_summary.json`、`paper/docs/chap05.tex` | 可以写成可复查运行闭环与 batch 图像验证链路开销 | 不能写成“实时系统”或“OM 模型推理慢”；应明确这不是最终产品形态，也不是视频链路 FPS |
| 分段计时 instrumentation：batch `frame_proc_ms/model_execute_ms` 与视频 `frame_proc_ms/model_execute_ms` | 主创新点 3 的补充实验证据 | 高 | `notes/timing_instrumentation_result_20260427.md`；`logs/direct_runs/20260427_timing_instrumentation/*` | 可以解释 `1119.510 ms` 与连续视频运行之间的口径差异；可以报告 sanity batch 模型执行均值约 8.208 ms、代表性视频模型执行均值约 8.407 ms | 不能把 50 张 sanity batch 当作完整 720 full-val；不能把单个视频片段泛化为所有场景 SLA |
| 代表性视频片段机器侧统计 | 辅助证据 | 中 | `doc/reports/2026-04-19_Phase3_3_Test5_Repair_Evidence.md`、`doc/reports/2026-04-19_Phase3_3_Test5_Demo_Candidates.md`；论文中 14.58 s、437 帧描述 | 可以作为连续场景观察与运行状态补充 | 不能计算视频级 precision/recall；不能写成 formal visual signoff，报告明确仍需人工完整复看 |
| 跨阶段逐样本一致性：PyTorch/ONNX/OM/board 边框漂移 | 后续工作 / 方法设计 | 低-中 | `paper/docs/chap03.tex` 和 `paper/docs/chap04.tex` 已给出评价方法；`notes/experiment_spec.md` 将其列为 expected output | 可以写成设计方法、理想实验、研究局限和后续工作 | 当前不要写成已完成数值结果；论文现有“尚未完成逐样本统一匹配”的表述是正确边界 |
| 视觉增强策略：hard-case weighting、targeted augmentation、model-scale comparison | 后续工作或待补实验 | 低 | `notes/experiment_spec.md` 和 `notes/thesis_scope_and_contributions.md` 中为 planned ablations；正文当前没有结果表 | 可以作为“计划验证项”“可扩展方向”或开题原始设想的收缩说明 | 不应作为当前三大贡献之一；若保留在摘要/贡献中会造成证据不匹配 |
| 量化、剪枝、蒸馏等模型压缩 | 背景 / 相关工作 | 低 | `main.bib` 中有 Jacob、Han、Hinton 等文献；正文将其作为边缘部署背景 | 只能作为相关工作背景或后续优化方向 | 如果没有真实量化/剪枝/蒸馏实验，不要写成本文贡献 |
| 人数计数、跌倒检测、多异常行为识别 | 展望 | 低 | `notes/proposal_digest.md` 说明这是开题原始大范围；`AGENTS.md` 限定为展望 | 只放讨论与展望 | 不要进入主体章节，否则论文会发散且缺证据 |

## 当前正文与 notes 的不一致点

1. `notes/thesis_scope_and_contributions.md` 仍把“Visual enhancement strategy”列为 Contribution 2，但当前正文已经更稳妥地收缩为“兼容迁移方法”和“部署一致性评价”。
   - 建议：后续更新 notes 时，将视觉增强策略降级为“计划补充实验 / 后续工作”，不要作为已完成贡献。
2. `notes/experiment_spec.md` 中 hard-case weighting、targeted augmentation、model-scale comparison 都是 planned ablations。
   - 建议：只有在补齐真实实验后，才允许进入正文实验结果；否则只能作为实验设计或展望。
3. `evidence_index/project_evidence_map.md` 仍出现 Chapter 6 映射，但当前论文主体已是五章结构。
   - 建议：后续同步为 Chapter 3/4/5/Appendix，避免写作时误引用历史章号。
4. 论文正文已经较好地区分“已完成板端验证 / 阈值后验重算 / 未完成跨阶段逐样本对齐”。
   - 建议：继续保持该边界，不要为了增强创新性而把跨阶段对齐写成已实测。

## 建议的最终贡献表述

建议正文中的贡献保持三条，不再加入“视觉增强策略”作为并列贡献：

1. **面向电梯轿厢的双目标检测任务建模。**
   将电动车入梯治理抽象为 `person + ebike` 双目标检测问题，并结合反光、遮挡、局部可见、门口结构等场景风险解释检测误差来源。
2. **自训练 YOLO 模型的边缘兼容迁移方法。**
   围绕输入预处理、类别顺序、输出张量、后处理参数和运行状态建立接口契约，使训练权重、ONNX 中间表示、OM 离线模型和板端应用形成可检查链路。
3. **面向安全视觉的部署一致性评价。**
   在板端完整验证、分类别统计、阈值敏感性后验重算和代表性视频机器侧统计基础上，分析模型迁移后的类别语义、阈值行为和运行状态。

## 论文可写结论与不可写结论

### 可以写

- 本课题在 720 张验证图像上完成板端实测，成功样本数为 720，失败样本数为 0。
- 板端总体 precision 为 0.901、recall 为 0.923、F1 为 0.912、mAP@0.5 为 0.910。
- 电动车类别 mAP@0.5 为 0.952，recall 为 0.961；行人类别 mAP@0.5 为 0.869，recall 为 0.888。
- 在 0.20--0.35 置信度阈值范围内，后验重算的总体 F1 保持在 0.915--0.922，电动车召回率保持在 0.956 以上。
- 当前板端 batch 图像验证链路端到端平均单图处理耗时约为 1119.510 ms；该数值主要说明 batch/JPEG 验证链路开销较重，不能直接解释为 OM 裸推理时延或连续视频模式帧率。
- 跨阶段逐样本对齐仍是研究局限和后续工作。

### 不应写

- 本文已经完成 hard-case weighting / targeted augmentation / lightweight model-scale comparison 的消融并取得提升。
- 本文已经定量证明 PyTorch、ONNX、OM、board 四阶段逐样本边框完全一致。
- 将 `1119.510 ms` 直接写成 OM 模型裸推理时延、NPU 推理时延或连续视频帧间耗时。
- 本文覆盖人数计数、跌倒检测和所有异常行为识别。
- 本文提出通用目标检测新算法或通用安全视觉 foundation model。

## 后续最小补强建议

按收益与工作量排序：

1. **更新 notes 与 evidence_index**
   - 将 `Visual enhancement strategy` 从已完成贡献降级为待补实验或后续工作。
   - 将 Chapter 6 旧映射同步为当前五章结构。
2. **补一张“创新点—证据—章节”表到论文附录或写作 notes**
   - 目的不是凑页数，而是让每个贡献都能回溯到证据文件。
3. **如时间允许，补小样本跨阶段一致性对齐**
   - 选择少量代表性样本，固定输入、阈值、NMS，比较 ONNX/OM/board 输出数量、类别、框 IoU。
   - 若无法完成，则保持为局限，不影响当前主线成立。
4. **为阈值敏感性生成一张折线图**
   - 使用现有 `2026-04-25_Thesis_Threshold_Sensitivity_Recompute.md` 数据即可，不新增结果。

## 审计结论

当前论文最应强化的不是“发明更多算法创新”，而是把现有真实证据组织成一条稳固链路：

`电梯场景约束 -> 双目标检测任务 -> 迁移接口契约 -> 板端完整验证 -> 分类别与阈值分析 -> 局限与展望`

只要坚持这个证据边界，本科论文的创新点是成立且可辩护的；如果把 planned ablations 或跨阶段逐样本对齐写成已完成结果，反而会削弱可信度。
