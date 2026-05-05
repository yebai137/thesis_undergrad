#!/usr/bin/env python3
import argparse
import json
import math
from pathlib import Path


CLASS_NAMES = ["person", "ebike"]
TIMING_KEYS = [
    "frame_proc_ms",
    "prepare_ms",
    "preprocess_ms",
    "input_update_ms",
    "model_execute_ms",
    "output_fetch_ms",
    "postprocess_ms",
    "temporal_ms",
    "render_prepare_ms",
    "render_ms",
    "osd_ms",
]


def empty_timing():
    return {key: 0.0 for key in TIMING_KEYS}


def add_timing(total, timing):
    if not isinstance(timing, dict):
        return
    for key in TIMING_KEYS:
        total[key] += float(timing.get(key, 0.0))


def average_timing(total, count):
    if count <= 0:
        return empty_timing()
    return {key: total[key] / count for key in TIMING_KEYS}


def rect_iou(lhs, rhs):
    inter_x1 = max(lhs["x1"], rhs["x1"])
    inter_y1 = max(lhs["y1"], rhs["y1"])
    inter_x2 = min(lhs["x2"], rhs["x2"])
    inter_y2 = min(lhs["y2"], rhs["y2"])
    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0
    inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
    lhs_area = (lhs["x2"] - lhs["x1"]) * (lhs["y2"] - lhs["y1"])
    rhs_area = (rhs["x2"] - rhs["x1"]) * (rhs["y2"] - rhs["y1"])
    union_area = lhs_area + rhs_area - inter_area
    if union_area <= 0:
        return 0.0
    return inter_area / union_area


def compute_ap(points, gt_total):
    if gt_total == 0 or not points:
        return 0.0
    points = sorted(points, key=lambda item: (-item["score"], -item["tp"]))
    precision = []
    recall = []
    cum_tp = 0
    cum_fp = 0
    for point in points:
        if point["tp"]:
            cum_tp += 1
        else:
            cum_fp += 1
        precision.append(cum_tp / (cum_tp + cum_fp))
        recall.append(cum_tp / gt_total)
    for idx in range(len(precision) - 2, -1, -1):
        precision[idx] = max(precision[idx], precision[idx + 1])
    ap = 0.0
    for step in range(101):
        threshold = step / 100.0
        best = 0.0
        for prec, rec in zip(precision, recall):
            if rec >= threshold and prec > best:
                best = prec
        ap += best
    return ap / 101.0


def recompute(detections_paths, score_threshold=0.0):
    summary = {
        "image_count": 0,
        "success_count": 0,
        "failure_count": 0,
        "fallback_count": 0,
        "total_elapsed_ms": 0.0,
        "average_elapsed_ms": 0.0,
        "prediction_count": 0,
        "timing_ms_average": empty_timing(),
        "map50": 0.0,
        "classes": [],
    }
    timing_total = empty_timing()
    class_state = [
        {"gt": 0, "pred": 0, "tp": 0, "fp": 0, "fn": 0, "points": []}
        for _ in CLASS_NAMES
    ]

    for detections_path in detections_paths:
        with open(detections_path, "r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                item = json.loads(line)
                summary["image_count"] += 1
                summary["total_elapsed_ms"] += float(item.get("elapsed_ms", 0.0))
                if item.get("fallback_used"):
                    summary["fallback_count"] += 1
                if item.get("success"):
                    summary["success_count"] += 1
                    add_timing(timing_total, item.get("timing_ms"))
                else:
                    summary["failure_count"] += 1

                ground_truths = item.get("ground_truths", [])
                detections = [
                    detection for detection in item.get("detections", [])
                    if float(detection.get("score", 0.0)) >= score_threshold
                ]
                summary["prediction_count"] += len(detections)

                for class_id in range(len(CLASS_NAMES)):
                    gt_of_class = [gt for gt in ground_truths if gt.get("class_id") == class_id]
                    pred_of_class = [pred for pred in detections if pred.get("class_id") == class_id]
                    matched = [False] * len(gt_of_class)

                    class_state[class_id]["gt"] += len(gt_of_class)
                    class_state[class_id]["pred"] += len(pred_of_class)

                    pred_of_class.sort(key=lambda pred: pred.get("score", 0.0), reverse=True)
                    matched_count = 0
                    for pred in pred_of_class:
                        best_iou = 0.0
                        best_idx = None
                        for idx, gt in enumerate(gt_of_class):
                            if matched[idx]:
                                continue
                            iou = rect_iou(pred, gt)
                            if iou > best_iou:
                                best_iou = iou
                                best_idx = idx
                        if best_idx is not None and best_iou >= 0.5:
                            matched[best_idx] = True
                            matched_count += 1
                            class_state[class_id]["tp"] += 1
                            class_state[class_id]["points"].append({"score": float(pred.get("score", 0.0)), "tp": 1})
                        else:
                            class_state[class_id]["fp"] += 1
                            class_state[class_id]["points"].append({"score": float(pred.get("score", 0.0)), "tp": 0})
                    class_state[class_id]["fn"] += len(gt_of_class) - matched_count

    if summary["success_count"] > 0:
        summary["average_elapsed_ms"] = summary["total_elapsed_ms"] / summary["success_count"]
        summary["timing_ms_average"] = average_timing(timing_total, summary["success_count"])

    for class_id, class_name in enumerate(CLASS_NAMES):
        state = class_state[class_id]
        precision = state["tp"] / (state["tp"] + state["fp"]) if (state["tp"] + state["fp"]) else 0.0
        recall = state["tp"] / (state["tp"] + state["fn"]) if (state["tp"] + state["fn"]) else 0.0
        f1 = (2.0 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        ap50 = compute_ap(state["points"], state["gt"])
        summary["classes"].append(
            {
                "class_id": class_id,
                "class_name": class_name,
                "gt": state["gt"],
                "pred": state["pred"],
                "tp": state["tp"],
                "fp": state["fp"],
                "fn": state["fn"],
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "ap50": ap50,
            }
        )
        summary["map50"] += ap50

    if CLASS_NAMES:
        summary["map50"] /= len(CLASS_NAMES)
    return summary


def build_summary_json(summary, images_dir="", labels_dir="", output_dir="", limit=0,
                       score_threshold=0.15, nms_threshold=0.45, iou_threshold=0.5):
    return {
        "images_dir": images_dir,
        "labels_dir": labels_dir,
        "output_dir": output_dir,
        "limit": limit,
        "score_threshold": score_threshold,
        "nms_threshold": nms_threshold,
        "iou_threshold": iou_threshold,
        "image_count": summary["image_count"],
        "success_count": summary["success_count"],
        "failure_count": summary["failure_count"],
        "fallback_count": summary["fallback_count"],
        "total_elapsed_ms": summary["total_elapsed_ms"],
        "average_elapsed_ms": summary["average_elapsed_ms"],
        "prediction_count": summary.get("prediction_count", 0),
        "timing_ms_average": summary.get("timing_ms_average", empty_timing()),
        "map50": summary["map50"],
        "classes": summary["classes"],
    }


def compare_summary(actual, expected, epsilon):
    def close(lhs, rhs):
        return math.isclose(float(lhs), float(rhs), rel_tol=epsilon, abs_tol=epsilon)

    if len(actual["classes"]) != len(expected.get("classes", [])):
        return False, "class count mismatch"
    scalar_keys = ["image_count", "success_count", "failure_count", "fallback_count"]
    for key in scalar_keys:
        if int(actual[key]) != int(expected.get(key, -1)):
            return False, f"{key} mismatch: {actual[key]} != {expected.get(key)}"
    float_keys = ["total_elapsed_ms", "average_elapsed_ms", "map50"]
    for key in float_keys:
        if not close(actual[key], expected.get(key, 0.0)):
            return False, f"{key} mismatch: {actual[key]} != {expected.get(key)}"
    if "timing_ms_average" in expected:
        actual_timing = actual.get("timing_ms_average", {})
        expected_timing = expected.get("timing_ms_average", {})
        for key in TIMING_KEYS:
            if key in expected_timing and not close(actual_timing.get(key, 0.0), expected_timing.get(key, 0.0)):
                return False, f"timing_ms_average.{key} mismatch: {actual_timing.get(key, 0.0)} != {expected_timing.get(key)}"
    for class_id, actual_class in enumerate(actual["classes"]):
        expected_class = expected["classes"][class_id]
        for key in ["gt", "pred", "tp", "fp", "fn"]:
            if int(actual_class[key]) != int(expected_class.get(key, -1)):
                return False, f"class {class_id} {key} mismatch: {actual_class[key]} != {expected_class.get(key)}"
        for key in ["precision", "recall", "f1", "ap50"]:
            if not close(actual_class[key], expected_class.get(key, 0.0)):
                return False, f"class {class_id} {key} mismatch: {actual_class[key]} != {expected_class.get(key)}"
    return True, "ok"


def main():
    parser = argparse.ArgumentParser(description="Recompute board batch metrics from detections.jsonl")
    parser.add_argument("detections_jsonl", nargs="+", type=Path)
    parser.add_argument("--summary-json", type=Path, default=None,
                        help="Optional board-generated summary.json to compare against")
    parser.add_argument("--write-summary-json", type=Path, default=None,
                        help="Optional path to write a board-style summary.json")
    parser.add_argument("--images-dir", default="")
    parser.add_argument("--labels-dir", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--score-threshold", type=float, default=0.15)
    parser.add_argument("--nms-threshold", type=float, default=0.45)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--epsilon", type=float, default=1e-6)
    args = parser.parse_args()

    summary = recompute(args.detections_jsonl, score_threshold=args.score_threshold)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.write_summary_json is not None:
        summary_doc = build_summary_json(
            summary,
            images_dir=args.images_dir,
            labels_dir=args.labels_dir,
            output_dir=args.output_dir,
            limit=args.limit,
            score_threshold=args.score_threshold,
            nms_threshold=args.nms_threshold,
            iou_threshold=args.iou_threshold,
        )
        args.write_summary_json.write_text(
            json.dumps(summary_doc, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if args.summary_json is not None:
        expected = json.loads(args.summary_json.read_text(encoding="utf-8"))
        ok, message = compare_summary(summary, expected, args.epsilon)
        if not ok:
            raise SystemExit(f"summary mismatch: {message}")
        print("summary comparison passed")


if __name__ == "__main__":
    main()
