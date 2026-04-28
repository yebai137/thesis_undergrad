# Citation Audit 20260428

## 核验口径

- 使用 `ml-paper-writing` 的 citation discipline：不凭记忆新增 BibTeX；优先核验 DOI、arXiv、CVF OpenAccess、PMLR、MDPI 或会议出版页。
- DOI 条目优先通过 Crossref 元数据核验；arXiv 条目通过 arXiv id、标题、作者与年份核验；无 DOI/arXiv 的会议论文用出版页核验。
- 正文引用检查不只检查 key 是否存在，还检查引用所在句是否确实由该文献支撑。
- 本轮保留 `paper/main.bib` 53 条，正文唯一引用 50 条；未在正文引用的条目仅保留在 BibTeX 备用池，不会进入最终参考文献列表。

## BibTeX 元数据修正

- `han2016deep`：补充 arXiv `1510.00149`。
- `tan2019efficientnet`：补充 arXiv `1905.11946`。
- `chen2018gradnorm`：页码修正为 `794--803`，补充 arXiv `1711.02257`。
- `chen2021scaleaware`：CVPR 页码修正为 `9563--9572`。
- `chen2021aqd`：补充 DOI `10.1109/CVPR46437.2021.00017`。

## 逐条核验记录

| BibTeX key | 核验来源 | 正文引用语境 | 处理 |
|---|---|---|---|
| `shi2016edge` | DOI `10.1109/JIOT.2016.2579198` | 边缘计算背景、端侧推理动机 | 保留 |
| `jacob2018quantization` | DOI `10.1109/CVPR.2018.00286` | 整数量化与边缘部署 | 保留 |
| `han2016deep` | arXiv `1510.00149` / ICLR | 剪枝、量化、压缩背景 | 补充 arXiv 后保留 |
| `hinton2015distilling` | arXiv `1503.02531` | 知识蒸馏背景 | 保留 |
| `dong2019hawq` | DOI `10.1109/ICCV.2019.00038` | 混合精度量化 | 保留 |
| `howard2019mobilenetv3` | DOI `10.1109/ICCV.2019.00140` | 轻量网络与硬件延迟搜索 | 保留 |
| `tan2019efficientnet` | PMLR / arXiv `1905.11946` | EfficientNet 缩放思想 | 补充 arXiv 后保留 |
| `tan2020efficientdet` | DOI `10.1109/CVPR42600.2020.01079` | EfficientDet 检测器缩放 | 保留 |
| `redmon2017yolo9000` | DOI `10.1109/CVPR.2017.690` | YOLO 系列发展 | 保留 |
| `carion2020detr` | DOI `10.1007/978-3-030-58452-8_13` | DETR 作为另一类检测路线 | 保留 |
| `kendall2018multi` | DOI `10.1109/CVPR.2018.00781` | 当前未正文引用，备用多任务背景 | 保留在 BibTeX，不进最终参考列表 |
| `chen2018gradnorm` | PMLR / arXiv `1711.02257` | 当前未正文引用，备用多任务背景 | 修正页码并保留在 BibTeX |
| `shrivastava2016ohem` | DOI `10.1109/CVPR.2016.89` | 难例挖掘背景 | 保留 |
| `chen2021scaleaware` | CVF OpenAccess | 目标检测定向增强 | 修正页码后保留 |
| `chen2021aqd` | DOI `10.1109/CVPR46437.2021.00017` | 量化检测与部署一致性风险 | 补充 DOI 后保留 |
| `stacker2021deployment` | arXiv `2108.08166` | 边缘目标检测部署优化 | 保留 |
| `zhou2023edgeyolo` | arXiv `2302.07483` | 边缘实时检测器方向 | 保留 |
| `lin2023elevatorcounting` | DOI `10.3390/fi15100337` | 电梯边缘人数统计相关工作 | 保留 |
| `wojke2017deepsort` | DOI `10.1109/ICIP.2017.8296962` | 视频跟踪相关工作 | 保留 |
| `zhang2022bytetrack` | DOI `10.1007/978-3-031-20047-2_1` | 视频跟踪相关工作 | 保留 |
| `cao2017openpose` | DOI `10.1109/CVPR.2017.143` | 姿态估计相邻方向 | 保留 |
| `feichtenhofer2019slowfast` | DOI `10.1109/ICCV.2019.00630` | 视频识别相邻方向 | 保留 |
| `redmon2016yolo` | DOI `10.1109/CVPR.2016.91` | YOLOv1 单阶段检测 | 保留 |
| `redmon2018yolov3` | arXiv `1804.02767` | YOLOv3 多尺度预测 | 保留 |
| `bochkovskiy2020yolov4` | arXiv `2004.10934` | YOLOv4 训练技巧与结构组合 | 保留 |
| `ge2021yolox` | arXiv `2107.08430` | YOLOX anchor-free 工程路线 | 保留 |
| `wang2022yolov7` | arXiv `2207.02696` | YOLOv7 实时检测器 | 保留 |
| `li2022yolov6` | arXiv `2209.02976` | YOLOv6 工业应用检测器 | 保留 |
| `girshick2014rcnn` | DOI `10.1109/CVPR.2014.81` | 两阶段检测发展 | 保留 |
| `girshick2015fast` | DOI `10.1109/ICCV.2015.169` | Fast R-CNN | 保留 |
| `ren2017faster` | DOI `10.1109/TPAMI.2016.2577031` | Faster R-CNN / RPN | 保留 |
| `liu2016ssd` | DOI `10.1007/978-3-319-46448-0_2` | 单阶段 SSD | 保留 |
| `lin2017fpn` | DOI `10.1109/CVPR.2017.106` | 多尺度特征 | 保留 |
| `lin2017focal` | DOI `10.1109/ICCV.2017.324` | 正负样本不均衡与难例加权 | 保留 |
| `zhao2019object` | DOI `10.1109/TNNLS.2018.2876865` | 当前未正文引用，备用综述 | 保留在 BibTeX，不进最终参考列表 |
| `he2016resnet` | DOI `10.1109/CVPR.2016.90` | 残差网络背景 | 保留 |
| `szegedy2015inception` | DOI `10.1109/CVPR.2015.7298594` | 多分支卷积背景 | 保留 |
| `howard2017mobilenets` | arXiv `1704.04861` | 深度可分离卷积轻量网络 | 保留 |
| `sandler2018mobilenetv2` | DOI `10.1109/CVPR.2018.00474` | 倒残差与轻量骨干 | 保留 |
| `iandola2016squeezenet` | arXiv `1602.07360` | 小参数量网络背景 | 保留 |
| `ma2018shufflenetv2` | DOI `10.1007/978-3-030-01264-9_8` | 移动端网络设计准则 | 保留 |
| `tan2018mnasnet` | arXiv `1807.11626` | 平台感知 NAS | 保留 |
| `cai2019onceforall` | arXiv `1908.09791` | 多部署约束网络适配 | 保留 |
| `chen2018tvm` | arXiv `1802.04799` | 深度学习编译优化 | 保留 |
| `jouppi2017tpu` | DOI `10.1145/3079856.3080246` | 专用加速器系统背景 | 保留 |
| `krishnamoorthi2018quantizing` | arXiv `1806.08342` | 卷积网络推理量化白皮书 | 保留 |
| `gholami2021quantization` | arXiv `2103.13630` | 量化方法综述 | 保留 |
| `bodla2017softnms` | DOI `10.1109/ICCV.2017.593` | NMS 后处理讨论 | 保留 |
| `rezatofighi2019giou` | DOI `10.1109/CVPR.2019.00075` | 边框质量评价 | 保留 |
| `zheng2020diou` | DOI `10.1609/AAAI.V34I07.6999` | 边框回归评价 | 保留 |
| `he2017mask` | DOI `10.1109/ICCV.2017.322` | 实例分割扩展相关工作 | 保留 |
| `zhou2019centernet` | arXiv `1904.07850` | anchor-free 检测相关工作 | 保留 |
| `bewley2016sort` | DOI `10.1109/ICIP.2016.7533003` | 简单在线跟踪相关工作 | 保留 |

## 结论

- 当前正文唯一引用数为 50，满足不少于 45 的要求。
- `paper/main.bib` 条目数为 53，满足 50--55 的要求。
- 未发现需要删除的虚构文献；本轮仅做元数据修正与核验记录。
- 后续正文修改若新增引用，必须先更新本审计文件或新增同类审计记录。
