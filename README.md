# Thesis Track: `elevator_ai/thesis_undergrad`

本目录是基于 `/home/ywj/elevator_ai` 独立建立的本科毕业论文工作流，不参与主工程 `.planning/ROADMAP.md` 的阶段推进，也不改写当前工程主线叙事。

## 当前定位

- 论文题目：`基于深度学习的电梯边缘AI安全视觉关键技术研究与实现`
- 当前 thesis phase：`Phase 04 - Bootstrap`
- 学术聚焦：`电梯轿厢 person + ebike 双任务检测`
- 贡献打包：`视觉性能增强 + 边缘部署一致性`
- 明确不扩张为：
  - 全量多任务安全基础模型
  - 完整跌倒检测论文主线
  - 完整人数统计 / 拥挤度系统论文主线

## 目录说明

- `AGENTS.md`
  Thesis-only 协作规则与写作/证据约束。
- `.planning/`
  Thesis-only 规划、状态、phase 记录。
- `upstream/SCUT-thesis/`
  上游 SCUT 模板参考副本，仅做最小编译适配，作为可比对基线。
- `paper/`
  当前可编辑论文工程，后续只在这里继续写作。
- `references/`
  论文参考文献筛选与整理说明。
- `notes/`
  选题收敛、开题摘要、章节设计、实验方案等笔记。
- `figures/`
  后续图示素材与导出图表的归档位置。
- `evidence_index/`
  将工程项目证据映射为论文章节证据入口。

## 快速开始

验证上游模板：

```bash
cd /home/ywj/elevator_ai/thesis_undergrad/upstream/SCUT-thesis
make clean
make pdf
```

编译论文工程：

```bash
cd /home/ywj/elevator_ai/thesis_undergrad/paper
make clean
make pdf
```

如果需要手动单轮编译：

```bash
xelatex -interaction=nonstopmode -file-line-error -shell-escape main.tex
```

## 说明

- `paper/` 已经切换为论文专用内容，不再保留上游 README 作为编辑入口。
- 真实实验结果优先引用 `/home/ywj/elevator_ai/logs/direct_runs/` 与 `doc/reports/` 的已有证据。
- 如果某项实验尚未完成，正文中必须明确写成“后续实验计划”或“待补齐对照”。
