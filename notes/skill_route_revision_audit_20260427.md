# Skill Route Revision Audit 20260427

## 使用的 Skill 路线

本轮按以下顺序重塑论文：

1. `brainstorming-research-ideas`：收敛创新点，不继续发散新课题。
2. `systems-paper-writing`：借用 Problem -> Gap -> Insight -> Method -> Evaluation 结构。
3. `academic-plotting`：重绘第五章结果图，解决图例遮挡、标签拥挤和换行错误。
4. `ml-paper-writing`：核验贡献、结果和引用边界，不新增未验证引用或实验结论。

## 创新点收敛结果

当前论文只固定三项贡献：

1. 电梯轿厢 `person + ebike` 双目标任务建模。
2. 自训练 YOLO 模型的边缘兼容迁移接口契约。
3. 面向安全视觉的部署一致性评价。

以下内容只作为后续工作或局限讨论：

- 困难样本重加权训练。
- 定向数据增强。
- 模型尺度对比。
- PyTorch / ONNX / OM / board 四阶段逐样本对齐。
- 完整 720 张验证集分段计时重跑。

## 本轮正文落点

- `paper/docs/abstract.tex`：加入核心判断，统一摘要贡献边界。
- `paper/docs/chap01.tex`：新增问题链、技术缺口、处理方式和贡献证据落点表。
- `paper/docs/chap03.tex`：强化迁移接口契约，把输入、类别、输出、后处理和运行五类契约写成方法核心。
- `paper/docs/chap04.tex`：补充四个评价问题，作为第五章实验组织依据。
- `paper/docs/chap05.tex`：按 RQ1--RQ4 重组结果章节，并明确分段计时证据边界。
- `figures/gen_fig_chap05_results.py`：修复图例遮挡、xlabel 与 legend 重叠、时延图字面 `\\n` 换行错误。

## 证据边界

- `1119.510 ms` 只表示板端 batch 图像验证链路端到端平均单图处理耗时。
- 分段计时可写入 `frame_proc_ms` 和 `model_execute_ms`，但必须说明样本范围和运行模式。
- 代表性视频片段用于说明连续处理路径和机器侧稳定性，不替代有人工标注的图像验证集指标。
