"""
board_postprocess.py — Python 复刻 board/src/elevator_postprocess.c 的后处理逻辑

忠实复刻以下板端算法:
  - score 过滤
  - geometry validity (min 4px, aspect ratio <= 8:1)
  - low-score strip artifact 过滤
  - NMS (hard NMS)
  - containment cleanup
  - temporal hold (person)
  - median smoother

这样 Codex 在服务端模拟推理时, 后处理行为与板端一致,
调参结果可直接迁移到板端.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional


# ---------- 板端常量复刻 ----------
CONTAINMENT_MIN_AREA_RATIO = 5
CONTAINMENT_MIN_COVERAGE_PERCENT = 92
CONTAINMENT_MIN_SCORE_MARGIN = 0.05
LOW_SCORE_STRIP_MAX_RATIO = 7
LOW_SCORE_STRIP_SCORE_CEILING = 0.55
MAX_DETECTIONS = 64
MAX_SMOOTH_WINDOW = 16
DEFAULT_PERSON_HOLD_MAX_FRAMES = 4
DEFAULT_PERSON_HOLD_MAX_MS = 400


@dataclass
class Rect:
    x1: int = 0
    y1: int = 0
    x2: int = 0
    y2: int = 0

    @property
    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(0, self.y2 - self.y1)

    @property
    def area(self) -> int:
        return self.width * self.height


@dataclass
class Detection:
    rect: Rect
    class_id: int = 0
    score: float = 0.0
    score_percent: int = 0


@dataclass
class CountStats:
    person_count: int = 0
    ebike_count: int = 0
    smoothed_person_count: int = 0
    smoothed_ebike_count: int = 0
    fps: float = 0.0


@dataclass
class ParseResult:
    detections: List[Detection] = field(default_factory=list)
    stats: CountStats = field(default_factory=CountStats)

    @property
    def detection_count(self) -> int:
        return len(self.detections)


# ---------- 辅助函数 ----------

def _align_even(value: int) -> int:
    return value & (~1)


def _clamp_to_frame_even(value: int, frame_size: int) -> int:
    if frame_size <= 1:
        return 0
    max_val = frame_size - 1
    if max_val & 1:
        max_val -= 1
    if value > max_val:
        value = max_val
    return _align_even(value)


def _round_u32(value: float) -> int:
    if not math.isfinite(value) or value <= 0.0:
        return 0
    return max(0, round(value))


def _rect_iou(a: Rect, b: Rect) -> float:
    ix1 = max(a.x1, b.x1)
    iy1 = max(a.y1, b.y1)
    ix2 = min(a.x2, b.x2)
    iy2 = min(a.y2, b.y2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    union = a.area + b.area - inter
    if union == 0:
        return 0.0
    return inter / union


def _rect_intersection_area(a: Rect, b: Rect) -> int:
    ix1 = max(a.x1, b.x1)
    iy1 = max(a.y1, b.y1)
    ix2 = min(a.x2, b.x2)
    iy2 = min(a.y2, b.y2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0
    return (ix2 - ix1) * (iy2 - iy1)


def _is_geometry_valid(rect: Rect) -> bool:
    w, h = rect.width, rect.height
    if w < 4 or h < 4:
        return False
    if w * 8 < h or h * 8 < w:
        return False
    return True


def _is_low_score_strip_artifact(
    rect: Rect,
    score: float,
    max_ratio: int = LOW_SCORE_STRIP_MAX_RATIO,
    score_ceiling: float = LOW_SCORE_STRIP_SCORE_CEILING,
) -> bool:
    if not math.isfinite(score) or score >= score_ceiling:
        return False
    w, h = rect.width, rect.height
    if w == 0 or h == 0:
        return True
    if w * max_ratio < h:
        return True
    if h * max_ratio < w:
        return True
    return False


# ---------- NMS ----------

def apply_nms(detections: List[Detection], nms_threshold: float) -> List[Detection]:
    """Hard NMS, 与板端 elevator_apply_nms 一致."""
    if len(detections) <= 1:
        return list(detections)

    # 按 score 降序排序
    sorted_dets = sorted(detections, key=lambda d: d.score, reverse=True)
    suppressed = [False] * len(sorted_dets)
    result = []

    for i, det_i in enumerate(sorted_dets):
        if suppressed[i]:
            continue
        result.append(det_i)
        for j in range(i + 1, len(sorted_dets)):
            if suppressed[j]:
                continue
            if sorted_dets[j].class_id != det_i.class_id:
                continue
            if _rect_iou(det_i.rect, sorted_dets[j].rect) > nms_threshold:
                suppressed[j] = True

    return result


# ---------- Soft-NMS (备用, 优化阶段可启用) ----------

def apply_soft_nms(
    detections: List[Detection],
    nms_threshold: float,
    sigma: float = 0.5,
    score_threshold: float = 0.01,
    method: str = "gaussian",
) -> List[Detection]:
    """Soft-NMS: 不直接抑制重叠框, 而是衰减其得分."""
    import copy
    dets = [copy.deepcopy(d) for d in detections]
    result = []

    while dets:
        # 找最高分
        best_idx = max(range(len(dets)), key=lambda i: dets[i].score)
        best = dets.pop(best_idx)
        result.append(best)

        remaining = []
        for d in dets:
            if d.class_id != best.class_id:
                remaining.append(d)
                continue
            iou = _rect_iou(best.rect, d.rect)
            if method == "gaussian":
                weight = math.exp(-(iou * iou) / sigma)
            else:  # linear
                weight = 1 - iou if iou > nms_threshold else 1.0
            d.score *= weight
            d.score_percent = _round_u32(d.score * 100.0)
            if d.score >= score_threshold:
                remaining.append(d)
        dets = remaining

    return result


# ---------- Containment Cleanup ----------

def apply_containment_cleanup(
    detections: List[Detection],
    area_ratio: int = CONTAINMENT_MIN_AREA_RATIO,
    coverage_percent: int = CONTAINMENT_MIN_COVERAGE_PERCENT,
    score_margin: float = CONTAINMENT_MIN_SCORE_MARGIN,
) -> List[Detection]:
    """复刻 elevator_apply_containment_cleanup."""
    if len(detections) <= 1:
        return list(detections)

    suppressed = [False] * len(detections)
    result = []

    for i, anchor in enumerate(detections):
        if suppressed[i]:
            continue
        anchor_area = anchor.rect.area
        if anchor_area == 0:
            result.append(anchor)
            continue

        for j in range(i + 1, len(detections)):
            if suppressed[j]:
                continue
            candidate = detections[j]
            if candidate.class_id != anchor.class_id:
                continue
            if anchor.score < candidate.score + score_margin:
                continue
            cand_area = candidate.rect.area
            if cand_area == 0:
                continue
            if anchor_area < cand_area * area_ratio:
                continue
            intersection = _rect_intersection_area(anchor.rect, candidate.rect)
            if intersection * 100 < cand_area * coverage_percent:
                continue
            suppressed[j] = True

        result.append(anchor)

    return result


# ---------- 主解析函数 ----------

def parse_yolo_detections(
    boxes,      # numpy array shape (N, 4) in xyxy format, in model input coords
    scores,     # numpy array shape (N,)
    class_ids,  # numpy array shape (N,)
    proc_width: int,
    proc_height: int,
    show_width: int,
    show_height: int,
    score_threshold: float = 0.15,
    nms_threshold: float = 0.45,
    use_soft_nms: bool = False,
    soft_nms_sigma: float = 0.5,
    strip_max_ratio: int = LOW_SCORE_STRIP_MAX_RATIO,
    strip_score_ceiling: float = LOW_SCORE_STRIP_SCORE_CEILING,
) -> ParseResult:
    """
    复刻 elevator_parse_raw_outputs: 从 YOLO 原始输出解析检测结果.

    参数:
        boxes: (N, 4) xyxy 坐标, 在模型输入坐标系下
        scores: (N,) 置信度
        class_ids: (N,) 类别 ID
        proc_width/proc_height: 模型推理输入分辨率 (通常 640x640)
        show_width/show_height: 显示/原始视频分辨率
        score_threshold: 得分阈值
        nms_threshold: NMS IoU 阈值
    """
    result = ParseResult()
    detections = []

    for i in range(len(scores)):
        s = float(scores[i])
        if not math.isfinite(s) or s < 0:
            s = 0.0
        elif s > 1.0:
            s = 1.0
        if s < score_threshold:
            continue

        x1_raw = float(boxes[i, 0])
        y1_raw = float(boxes[i, 1])
        x2_raw = float(boxes[i, 2])
        y2_raw = float(boxes[i, 3])

        # 坐标缩放: 模型输入 → 显示分辨率
        sx1 = (x1_raw / proc_width) * show_width
        sy1 = (y1_raw / proc_height) * show_height
        sx2 = (x2_raw / proc_width) * show_width
        sy2 = (y2_raw / proc_height) * show_height

        rx1 = _clamp_to_frame_even(_round_u32(sx1), show_width)
        ry1 = _clamp_to_frame_even(_round_u32(sy1), show_height)
        rx2 = _clamp_to_frame_even(_round_u32(sx2), show_width)
        ry2 = _clamp_to_frame_even(_round_u32(sy2), show_height)

        # 确保 x1 < x2, y1 < y2
        if rx2 < rx1:
            rx1, rx2 = rx2, rx1
        if ry2 < ry1:
            ry1, ry2 = ry2, ry1

        if rx2 <= rx1 or ry2 <= ry1:
            continue

        rect = Rect(rx1, ry1, rx2, ry2)

        if not _is_geometry_valid(rect):
            continue
        if _is_low_score_strip_artifact(rect, s, strip_max_ratio, strip_score_ceiling):
            continue

        det = Detection(
            rect=rect,
            score=s,
            score_percent=_round_u32(s * 100.0),
            class_id=_round_u32(float(class_ids[i])),
        )
        detections.append(det)

        if len(detections) >= MAX_DETECTIONS:
            break

    # NMS
    if len(detections) > 1:
        if use_soft_nms:
            detections = apply_soft_nms(detections, nms_threshold, sigma=soft_nms_sigma)
        else:
            detections = apply_nms(detections, nms_threshold)
        detections = apply_containment_cleanup(detections)

    # 统计
    person_count = sum(1 for d in detections if d.class_id == 0)
    ebike_count = sum(1 for d in detections if d.class_id == 1)

    result.detections = detections
    result.stats = CountStats(
        person_count=person_count,
        ebike_count=ebike_count,
        smoothed_person_count=person_count,
        smoothed_ebike_count=ebike_count,
    )
    return result


# ---------- Temporal Hold ----------

class TemporalHold:
    """复刻 elevator_temporal_hold."""

    def __init__(
        self,
        max_hold_frames: int = DEFAULT_PERSON_HOLD_MAX_FRAMES,
        max_hold_ms: int = DEFAULT_PERSON_HOLD_MAX_MS,
    ):
        self.max_hold_frames = max_hold_frames
        self.max_hold_ms = max_hold_ms
        self.has_previous = False
        self.previous_result: Optional[ParseResult] = None
        self.last_timestamp_ms: int = 0
        self.consecutive_holds: int = 0

    def apply(self, result: ParseResult, timestamp_ms: int) -> ParseResult:
        if not self.has_previous:
            self.previous_result = result
            self.last_timestamp_ms = timestamp_ms
            self.consecutive_holds = 0
            self.has_previous = True
            return result

        current_person = result.stats.person_count
        prev_person = self.previous_result.stats.person_count

        within_time = (
            self.last_timestamp_ms != 0
            and timestamp_ms >= self.last_timestamp_ms
            and timestamp_ms - self.last_timestamp_ms <= self.max_hold_ms
        )
        severe_drop = prev_person > current_person + 1

        if within_time and severe_drop and self.consecutive_holds < self.max_hold_frames:
            # 合并: 保留前一帧的 person 检测, 保留当前帧的 ebike 检测
            merged_dets = []
            for d in self.previous_result.detections:
                if d.class_id == 0:  # person
                    merged_dets.append(d)
            for d in result.detections:
                if d.class_id == 1:  # ebike
                    merged_dets.append(d)
                    
            if len(merged_dets) > MAX_DETECTIONS:
                merged_dets = merged_dets[:MAX_DETECTIONS]

            merged = ParseResult(
                detections=merged_dets,
                stats=CountStats(
                    person_count=self.previous_result.stats.person_count,
                    ebike_count=result.stats.ebike_count,
                    smoothed_person_count=result.stats.smoothed_person_count,
                    smoothed_ebike_count=result.stats.smoothed_ebike_count,
                    fps=result.stats.fps,
                ),
            )
            self.previous_result = merged
            self.last_timestamp_ms = timestamp_ms
            self.consecutive_holds += 1
            return merged

        self.previous_result = result
        self.last_timestamp_ms = timestamp_ms
        self.consecutive_holds = 0
        self.has_previous = True
        return result


# ---------- Median Smoother ----------

class MedianSmoother:
    """复刻 elevator_smoother."""

    def __init__(self, window_size: int = 5):
        self.window_size = min(max(window_size, 1), MAX_SMOOTH_WINDOW)
        self.person_history: List[int] = []
        self.ebike_history: List[int] = []
        self.last_timestamp_ms: int = 0

    def update(self, stats: CountStats, timestamp_ms: int) -> CountStats:
        self.person_history.append(stats.person_count)
        self.ebike_history.append(stats.ebike_count)

        if len(self.person_history) > self.window_size:
            self.person_history = self.person_history[-self.window_size:]
        if len(self.ebike_history) > self.window_size:
            self.ebike_history = self.ebike_history[-self.window_size:]

        smoothed_person = sorted(self.person_history)[len(self.person_history) // 2]
        smoothed_ebike = sorted(self.ebike_history)[len(self.ebike_history) // 2]

        if self.last_timestamp_ms == 0 or timestamp_ms <= self.last_timestamp_ms:
            fps = 0.0
        else:
            fps = 1000.0 / (timestamp_ms - self.last_timestamp_ms)
        self.last_timestamp_ms = timestamp_ms

        return CountStats(
            person_count=stats.person_count,
            ebike_count=stats.ebike_count,
            smoothed_person_count=smoothed_person,
            smoothed_ebike_count=smoothed_ebike,
            fps=fps,
        )
