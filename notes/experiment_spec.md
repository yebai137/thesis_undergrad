# Experiment Specification

## Phase 05: Visual Enhancement Experiments

### Locked baseline

- 当前基线来源：
  - accepted promote candidate: `20260417_phase3_mature_fix`
  - full-val metric pack: `20260419_phase3_3_full_val_synced`
- 核心指标：
  - per-class precision / recall / F1 / mAP50
  - hard-case subgroup success ratio
  - representative failure cases

### Planned ablations

1. Hard-case subset weighting
   - 目标：提升遮挡、反光、局部可见电动车样本的召回。
   - 对比：baseline vs weighted sampler / loss reweighting。
2. Targeted augmentation
   - 目标：模拟门口区域、反光区域、弱光与尺度变化。
   - 对比：baseline vs augmentation policy。
3. Lightweight model-scale comparison
   - 目标：比较较轻与较重模型在板端部署收益/代价。
   - 对比：至少两种模型规模或两档宽度系数。

### Deliverables

- 总体结果表
- hard-case taxonomy 分组结果表
- 典型成功/失败案例图

## Phase 06: Deployment Consistency Experiments

### Chain

`PyTorch -> ONNX -> OM -> board`

### Metrics

- Accuracy drift:
  - overall mAP50 drift
  - per-class F1 drift
- Runtime:
  - average latency
  - throughput
  - fallback / failure count
- Consistency:
  - bbox position drift
  - class confidence ordering drift
  - threshold sensitivity drift

### Expected outputs

- 迁移链对比表
- 部署误差来源分析
- 关键差异案例可视化
