# Final Integrity Check 20260427

日期：2026-04-27  
Pipeline 阶段：Stage 4.5 Final Integrity  
目标：确认 Round 3--4 修订后，论文可编译、页数达标、引用完整、证据口径不越界。

## 1. 编译结果

命令：

```bash
cd /home/ywj/elevator_ai/thesis_undergrad/paper
make pdf
```

结果：

| 项目 | 状态 | 说明 |
|---|---:|---|
| PDF 编译 | PASS | `paper/main.pdf` 已生成 |
| 页数 | PASS | 49 页，位于 48--52 页目标范围 |
| 页面尺寸 | PASS | A4 |
| LaTeX Error | PASS | 未发现 |
| Undefined citations | PASS | 未发现 |
| Undefined references | PASS | 未发现 |
| Overfull | PASS | 未发现 |

最终清稿后再次编译，结果仍为 49 页。日志中仍有模板/字体相关的 underfull 与 font substitution 警告，属于模板排版层面的非阻塞警告，未影响 PDF 生成。

## 2. 引用检查

本轮新增正文引用但未新增 BibTeX 条目，主要复用 `paper/main.bib` 已有文献：

- `carion2020detr`
- `dong2019hawq`
- `wojke2017deepsort`
- `zhang2022bytetrack`
- `cao2017openpose`
- `feichtenhofer2019slowfast`

检查结果：

- 所有 `\cite{}` key 均存在于 `paper/main.bib`。
- 未生成未经核验的新 BibTeX。
- `references/curated_sources.md` 已修正 `lin2023elevatorcounting` 的作者说明，与 `paper/main.bib` 保持一致。

## 3. 证据与口径检查

### 3.1 运行时口径

通过检查：

- `1119.510 ms` 仍仅作为“板端 batch 图像验证链路端到端平均单图处理耗时”出现。
- 正文未将 `1119.510 ms` 写成“OM 模型裸推理时延”或“NPU 裸推理时延”。
- 分段计时结果仍限定为 50 张 batch 复查和代表性视频片段的工程观测。
- 视频结果仍明确不替代带人工标注的图像验证集指标，也不等价于产品级实时性能保证。

### 3.2 实验结论范围

通过检查：

- 摘要、绪论、方法、实验和结论中的三项贡献已统一为：
  1. 电梯双目标任务建模。
  2. 边缘兼容迁移接口契约。
  3. 部署一致性评价框架与板端证据链。
- 未将 PyTorch、ONNX、OM、board 四阶段逐样本匹配写成已完成结果。
- 未将人数统计、跌倒检测、跟踪或视频行为理解写成主体贡献。
- 未新增训练增强、模型规模对比或大规模板端实验结果。

## 4. 图表检查

检查对象：

- `fig_chap05_detection_metrics`
- `fig_chap05_threshold_sensitivity`
- `fig_chap05_timing_breakdown`

结果：

- 生成脚本已加入柱状图 hatch 纹理、深色边框和曲线线型。
- PDF 第 5 章图表页抽查未发现遮挡、乱码或图注错位。
- 图表仍只使用已有 full-val、阈值重算和分段计时真实数据。

## 5. 正文禁词与内部痕迹检查

正文扫描未发现：

- 内部绝对路径。
- Phase/test 编号。
- `Agent` 或答辩元叙事。
- `OSDI` / `SOSP` 顶会包装痕迹。
- “证据边界”“伪装”“当前版本”“审计闭环”“验证闭环”等内部审计口吻。

## 6. Verdict

**PASS**

论文已达到本轮 Academic Pipeline 的主要验收条件：

- 49 页，符合目标页数。
- 可编译。
- 引用完整。
- 核心实验结论均能回溯到既有证据。
- `1119.510 ms` 口径未越界。
- 图表可读性较 baseline 有改善。
- 未完成内容保留在局限与展望中。
