# Paper Workspace

本目录是本科毕业论文的实际写作工程，已从 `../upstream/SCUT-thesis/` 初始化，但内容已经切换为电梯边缘 AI 论文专用版本。

## 写作入口

- 主文件：`main.tex`
- 信息页：`docs/info.tex`
- 摘要：`docs/abstract.tex`
- 正文：
  - `docs/chap01.tex`
  - `docs/chap02.tex`
  - `docs/chap03.tex`
  - `docs/chap04.tex`
  - `docs/chap05.tex`
  - `docs/chap06.tex`
  - `docs/conclusion.tex`
- 参考文献：`main.bib`

## 编译

```bash
cd /home/ywj/elevator_ai/thesis_undergrad/paper
make clean
make pdf
```

如果需要单轮调试：

```bash
xelatex -interaction=nonstopmode -file-line-error -shell-escape main.tex
```

## 论文主线

- 题目：`基于深度学习的电梯边缘AI安全视觉关键技术研究与实现`
- 聚焦任务：电梯轿厢 `person + ebike` 双任务检测
- 核心贡献包：
  - 电梯难例场景 formalization
  - 视觉性能增强策略
  - 边缘部署一致性分析

## 注意

- 不要再把 `paper/` 当成上游模板示例目录使用。
- 如果需要对照模板原状，请查看 `../upstream/SCUT-thesis/`。
- 如果正文里某实验尚未补齐，请明确写为“计划实验”或“待补对照”。
