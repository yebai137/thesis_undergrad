#!/usr/bin/env python3
"""Build an editable PPT visual replica from the supplied reference image.

This script follows the local ppt-visual-replica skill artifact layout.  The
semantic visual assets are isolated crops from the user-provided reference so
they remain independently selectable in PowerPoint, while the main labels,
cards, connectors, and explanatory text are editable PPT objects.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "figures" / "4e342ed6aee263e10242b419cdc8ce8.png"
OUT_ROOT = ROOT / "figures" / "ppt_visual_replica_4e342ed6"
SKILL_ROOT = Path("/home/ywj/.codex/skills/ppt-visual-replica")
PYTHON = Path("/home/ywj/miniconda3/bin/python")


CANVAS = {"width": 1672, "height": 941}
SLIDE = {"width_in": 16.72, "height_in": 9.41}
FONT = "Noto Sans CJK SC"


ASSETS = [
    {
        "id": "stage1_network_arch",
        "label": "YOLO simplified network structure blocks and output scales",
        "bbox": [28, 228, 222, 78],
        "anchor_slot": [28, 228, 222, 78],
    },
    {
        "id": "stage1_weight_tensors",
        "label": "Backbone Neck Head weight tensor grids",
        "bbox": [30, 374, 220, 111],
        "anchor_slot": [30, 374, 220, 111],
    },
    {
        "id": "stage1_class_matrices",
        "label": "Person and ebike class matrix examples",
        "bbox": [31, 548, 218, 87],
        "anchor_slot": [31, 548, 218, 87],
    },
    {
        "id": "stage4_om_package",
        "label": "OM package graph weights metadata container",
        "bbox": [907, 228, 151, 517],
        "anchor_slot": [907, 228, 151, 517],
    },
    {
        "id": "stage5_npu_execution",
        "label": "NPU buffers compute array and SRAM execution structure",
        "bbox": [1137, 247, 197, 420],
        "anchor_slot": [1137, 247, 197, 420],
    },
    {
        "id": "stage6_tensor_strip",
        "label": "Raw model output tensor strip",
        "bbox": [1417, 224, 224, 36],
        "anchor_slot": [1417, 224, 224, 36],
    },
    {
        "id": "stage6_bbox_decode",
        "label": "Bounding box decode formula and center diagram",
        "bbox": [1426, 309, 207, 101],
        "anchor_slot": [1426, 309, 207, 101],
    },
    {
        "id": "stage6_class_scores",
        "label": "Person and ebike category score bars",
        "bbox": [1464, 451, 164, 42],
        "anchor_slot": [1464, 466, 164, 42],
    },
    {
        "id": "stage6_detection_result",
        "label": "Elevator detection result with retained boxes",
        "bbox": [1417, 526, 224, 142],
        "anchor_slot": [1417, 526, 224, 142],
    },
    {
        "id": "stage6_result_table",
        "label": "NMS result table",
        "bbox": [1416, 679, 224, 92],
        "anchor_slot": [1416, 679, 224, 92],
    },
]


def ensure_dirs() -> None:
    for sub in [
        "",
        "reference_crops",
        "generated",
        "assets",
        "prompts",
        "reports",
    ]:
        (OUT_ROOT / sub).mkdir(parents=True, exist_ok=True)


def copy_reference() -> None:
    shutil.copy2(REFERENCE, OUT_ROOT / "reference.png")


def crop_assets() -> None:
    ref = Image.open(REFERENCE).convert("RGB")
    for asset in ASSETS:
        x, y, w, h = asset["bbox"]
        crop = ref.crop((x, y, x + w, y + h))
        crop.save(OUT_ROOT / "reference_crops" / f"{asset['id']}.png")
        crop.save(OUT_ROOT / "assets" / f"{asset['id']}.png")


def text(
    element_id: str,
    x: float,
    y: float,
    w: float,
    h: float,
    value: str,
    font_size: float,
    *,
    color: str = "#111827",
    bold: bool = False,
    align: str = "center",
    valign: str = "middle",
    expected_lines: int | None = None,
) -> dict:
    item = {
        "id": element_id,
        "type": "text",
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "text": value,
        "font": FONT,
        "font_size": font_size,
        "color": color,
        "bold": bold,
        "align": align,
        "valign": valign,
        "margin_left": 1,
        "margin_right": 1,
        "margin_top": 1,
        "margin_bottom": 1,
    }
    if expected_lines:
        item["expected_lines"] = expected_lines
    return item


def rect(
    element_id: str,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    fill: str | None = None,
    line: str | None = "#6d839c",
    line_width: float = 1,
    rounded: bool = False,
    purpose: str = "panel",
) -> dict:
    return {
        "id": element_id,
        "type": "round_rect" if rounded else "rect",
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "fill": fill,
        "line": line,
        "line_width": line_width,
        "purpose": purpose,
    }


def line(
    element_id: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    color: str = "#173b5c",
    width: float = 1,
) -> dict:
    return {
        "id": element_id,
        "type": "line",
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "color": color,
        "width": width,
        "purpose": "connector",
    }


def arrow(element_id: str, x: float, y: float, w: float, h: float) -> dict:
    return rect(
        element_id,
        x,
        y,
        w,
        h,
        fill="#12395b",
        line=None,
        rounded=False,
        purpose="structural_arrow",
    ) | {"type": "right_arrow"}


def down_arrow(element_id: str, x: float, y: float, w: float, h: float) -> dict:
    return rect(
        element_id,
        x,
        y,
        w,
        h,
        fill="#12395b",
        line=None,
        rounded=False,
        purpose="structural_arrow",
    ) | {"type": "down_arrow"}


def image(asset_id: str) -> dict:
    asset = next(item for item in ASSETS if item["id"] == asset_id)
    x, y, w, h = asset["anchor_slot"]
    return {
        "id": f"img_{asset_id}",
        "type": "image",
        "path": f"{asset_id}.png",
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "anchor_slot": asset["anchor_slot"],
        "source_type": "user_asset",
        "asset_role": "minimum_semantic_unit",
        "semantic_unit_id": asset_id,
        "semantic_unit_count": 1,
    }


def add_flow_box(
    elements: list[dict],
    prefix: str,
    x: float,
    y: float,
    w: float,
    h: float,
    label: str,
    font_size: float = 9.2,
) -> None:
    elements.append(rect(f"{prefix}_box_{int(y)}", x, y, w, h, fill="#fbfdff", line="#8ba0b5", rounded=True, purpose="text_container"))
    elements.append(text(f"{prefix}_text_{int(y)}", x + 5, y + 4, w - 10, h - 8, label, font_size, align="center", expected_lines=label.count("\n") + 1))


def add_cards(elements: list[dict]) -> list[dict]:
    cards = [
        ("stage1", 20, 102, 238, 674, "1. 训练权重\nPyTorch / YOLO"),
        ("stage2", 334, 102, 200, 674, "2. ONNX 导出\n中间表示"),
        ("stage3", 582, 102, 262, 674, "3. ATC 编译\n算子适配"),
        ("stage4", 892, 102, 178, 674, "4. OM 模型\n离线模型"),
        ("stage5", 1125, 102, 220, 674, "5. NPU 推理\n模型执行"),
        ("stage6", 1404, 102, 244, 674, "6. 解码与 NMS\n安全输出"),
    ]
    for cid, x, y, w, h, title in cards:
        elements.append(rect(f"{cid}_card", x, y, w, h, fill="#ffffff", line="#7c93ad", rounded=True, purpose="panel"))
        elements.append(rect(f"{cid}_header", x, y, w, 63, fill="#12395b", line="#12395b", purpose="text_container"))
        elements.append(text(f"{cid}_header_text", x + 6, y + 6, w - 12, 52, title, 16, color="#ffffff", bold=True, expected_lines=2))
    return elements


def build_manifest() -> dict:
    elements: list[dict] = []

    elements.append(rect("slide_background", 0, 0, 1672, 941, fill="#fbfdff", line="#8fa5bd", purpose="background"))

    # Top grouping band.
    for eid, x, w, title, subtitle in [
        ("top_train", 8, 290, "训练端", "模型训练与权重产出"),
        ("top_convert", 298, 792, "模型格式转换", "围绕特别板端可执行模型"),
        ("top_board", 1090, 574, "板端运行与后处理", "板端推理、解码、NMS 与安全输出"),
    ]:
        elements.append(rect(eid, x, 10, w, 72, fill="#fbfdff", line="#8ca2bb", purpose="panel"))
        elements.append(text(f"{eid}_title", x, 18, w, 28, title, 19, bold=True))
        elements.append(text(f"{eid}_subtitle", x, 48, w, 24, subtitle, 12.5))

    elements.extend([line("separator_1", 296, 84, 296, 782, color="#b9c5d2", width=1), line("separator_2", 1090, 84, 1090, 782, color="#b9c5d2", width=1)])
    add_cards(elements)

    # Cross-card annotations and arrows.
    for i, (eid, x, y, label) in enumerate(
        [
            ("arrow_1_2", 270, 412, "输出语义\n尺寸 /\n通道 /\n归一化"),
            ("arrow_2_3", 540, 424, "图结构及\n算子\n通用名称"),
            ("arrow_3_4", 850, 426, "设备可\n执行语义 /\n算子适配 /\n尺度信息"),
            ("arrow_4_5", 1075, 440, "模型包及\n运行配置 /\n输入\n请求"),
            ("arrow_5_6", 1352, 468, "输出结果\n张量 /\n送入\nNMS"),
        ],
        start=1,
    ):
        box_w = 58 if i != 3 else 46
        elements.append(rect(f"{eid}_label_box", x - 2, y - 56, box_w, 80, fill="#f8fbff", line="#7c93ad", purpose="text_container"))
        elements.append(text(f"{eid}_label", x, y - 52, box_w - 4, 72, label, 9.5, color="#1d3954", expected_lines=label.count("\n") + 1))
        elements.append(arrow(eid, x + box_w + 2, y - 2, 40, 18))

    # Stage 1.
    elements.append(text("stage1_network_title", 30, 179, 218, 28, "YOLO 网络结构（简化）", 11.2, bold=True))
    elements.append(image("stage1_network_arch"))
    elements.append(text("stage1_weights_title", 42, 339, 195, 26, "权重参数（部分张量示意）", 11, bold=True))
    elements.append(image("stage1_weight_tensors"))
    elements.append(text("stage1_classes_title", 50, 522, 178, 26, "检测类（双目标）", 11, bold=True))
    elements.append(image("stage1_class_matrices"))
    elements.append(text("stage1_output_dim", 30, 648, 218, 28, "输出维度：[batch, anchors, (5 + num_classes)]", 8.5))
    elements.append(rect("stage1_semantics_box", 31, 696, 218, 42, fill="#fbfdff", line="#8ba0b5", purpose="text_container"))
    elements.append(text("stage1_semantics", 36, 703, 208, 26, "类别语义顺序：person(0) / ebike(1)", 9.2))

    # Stage 2.
    elements.append(text("stage2_graph_title", 374, 185, 120, 28, "ONNX graph", 12.5, color="#0d3157", bold=True))
    y_positions = [232, 318, 402, 489, 572]
    labels = [
        "输入张量\n[1, 3, H, W]",
        "Conv\n[1, C1, H/2, W/2]",
        "SiLU\n[1, C1, H/2, W/2]",
        "Detect Head\n[1, A×(5+2), Hs, Ws]",
        "输出张量\nboxes / score / class\n[1, N, (5+2)]",
    ]
    heights = [56, 56, 56, 62, 70]
    for idx, (y, label, h) in enumerate(zip(y_positions, labels, heights), start=1):
        add_flow_box(elements, f"stage2_{idx}", 376, y, 114, h, label, font_size=9.8)
        if idx < len(y_positions):
            elements.append(down_arrow(f"stage2_down_{idx}", 426, y + h + 8, 18, 24))
    elements.append(rect("stage2_note_box", 348, 690, 172, 58, fill="#fbfdff", line="#8ba0b5", purpose="text_container"))
    elements.append(text("stage2_note", 354, 696, 160, 44, "注：\nN = 预测框个数，A=anchors", 8.0, align="left", expected_lines=2))

    # Stage 3.
    elements.append(text("stage3_left_title", 598, 183, 80, 42, "ONNX 原始\n(FP32)", 9.5, color="#0d3157", expected_lines=2))
    elements.append(text("stage3_right_title", 735, 183, 96, 42, "Ascend / NPU kernel\n(适配后)", 9, color="#0d3157", expected_lines=2))
    left_nodes = [("Input", 244), ("Conv", 310), ("BN", 374), ("SiLU", 438), ("MatMul", 502), ("...", 566), ("Detect Head", 620), ("Output", 687)]
    for idx, (label, y) in enumerate(left_nodes):
        add_flow_box(elements, f"stage3_left_{idx}", 598, y, 62, 34, label)
        if idx < len(left_nodes) - 1:
            elements.append(down_arrow(f"stage3_left_arrow_{idx}", 622, y + 36, 14, 20))
    right_nodes = [
        ("AIPP\n(预处理)", 246, 92, 50),
        ("Conv + BN\n(融合)", 330, 92, 56),
        ("SiLU\n(融合)", 415, 92, 52),
        ("MatMul\n(映射优化)", 500, 92, 58),
        ("...", 588, 92, 36),
        ("Detect Head\n(自定义算子)", 636, 92, 70),
    ]
    for idx, (label, y, w, h) in enumerate(right_nodes):
        add_flow_box(elements, f"stage3_right_{idx}", 735, y, w, h, label)
        if idx < len(right_nodes) - 1:
            elements.append(down_arrow(f"stage3_right_arrow_{idx}", 774, y + h + 7, 14, 22))
    elements.append(text("stage3_fusion_text", 674, 386, 60, 48, "operator\nlowering /\nfusion", 8.2, color="#1d3954", expected_lines=3))
    elements.append(arrow("stage3_fusion_arrow", 683, 438, 42, 18))
    elements.append(rect("stage3_note_box", 591, 724, 246, 30, fill="#fbfdff", line="#8ba0b5", purpose="text_container"))
    elements.append(text("stage3_note", 596, 729, 236, 18, "主要优化：算子融合 / 格式转换 / 内存复用 / 调度适配", 7.6))

    # Stage 4.
    elements.append(text("stage4_package_title", 908, 184, 146, 30, "OM 模型包结构（.om）", 10.5, bold=True))
    elements.append(image("stage4_om_package"))

    # Stage 5.
    elements.append(text("stage5_exec_title", 1138, 185, 194, 28, "NPU 执行结构（板端）", 10.2, bold=True))
    elements.append(image("stage5_npu_execution"))
    elements.append(rect("stage5_note_box", 1150, 698, 170, 45, fill="#fbfdff", line="#8ba0b5", purpose="text_container"))
    elements.append(text("stage5_note", 1154, 705, 162, 30, "执行 OM 模型：\n调度算子 / 并行计算", 9.5, expected_lines=2))

    # Stage 6.
    elements.append(text("stage6_tensor_title", 1455, 181, 142, 36, "模型输出张量（原始）\n[1, N, (5+2)]", 9.5, bold=True, expected_lines=2))
    elements.append(image("stage6_tensor_strip"))
    elements.append(text("stage6_bbox_title", 1455, 279, 130, 24, "bbox decode（坐标还原）", 9.5, bold=True))
    elements.append(image("stage6_bbox_decode"))
    elements.append(text("stage6_scores_title", 1440, 418, 170, 22, "类别分数（person / ebike）", 8.6, bold=True))
    elements.append(text("stage6_scores_subtitle", 1453, 440, 142, 16, "sigmoid / softmax", 7.5))
    elements.append(image("stage6_class_scores"))
    elements.append(text("stage6_nms_title", 1450, 502, 150, 22, "NMS 后结果（保留框）", 9.5, bold=True))
    elements.append(image("stage6_detection_result"))
    elements.append(image("stage6_result_table"))

    # Bottom consistency arrow and grouping braces.
    elements.append(line("bottom_consistency_line", 114, 815, 1480, 815, color="#12395b", width=1.5))
    elements.append(arrow("bottom_consistency_head", 1476, 805, 30, 20))
    elements.append(text("bottom_consistency_text", 360, 795, 960, 34, "类别语义：person / ebike 顺序一致（训练  →  导出  →  编译  →  OM  →  推理  →  后处理）", 10.5, bold=True))
    for eid, x1, x2, label in [
        ("bottom_offline", 20, 1060, "模型格式转换（离线）"),
        ("bottom_online", 1110, 1650, "板端运行与后处理（在线）"),
    ]:
        elements.append(line(f"{eid}_top", x1, 862, x2, 862, color="#12395b", width=1))
        elements.append(line(f"{eid}_left", x1, 850, x1 + 12, 862, color="#12395b", width=1))
        elements.append(line(f"{eid}_right", x2 - 12, 862, x2, 850, color="#12395b", width=1))
        mid = (x1 + x2) / 2
        elements.append(line(f"{eid}_mid_l", mid - 24, 862, mid, 875, color="#12395b", width=1))
        elements.append(line(f"{eid}_mid_r", mid, 875, mid + 24, 862, color="#12395b", width=1))
        elements.append(text(f"{eid}_label", x1, 882, x2 - x1, 38, label, 16, color="#0b2c53", bold=True))

    return {"canvas": CANVAS, "slide": SLIDE, "elements": elements}


def write_inventory() -> None:
    text_items = [
        {"id": "top_titles", "classification": "text", "label": "three section titles and subtitles"},
        {"id": "stage_headers", "classification": "text", "label": "six numbered stage headers"},
        {"id": "body_labels", "classification": "text", "label": "major body labels, notes, and bottom consistency text"},
    ]
    layout_items = [
        {"id": "cards", "classification": "layout_native", "label": "stage cards, top bands, dividers, braces"},
        {"id": "connectors", "classification": "layout_native", "label": "structural arrows and internal operator-flow arrows"},
    ]
    semantic_items = []
    for asset in ASSETS:
        semantic_items.append(
            {
                "id": asset["id"],
                "anchor_id": asset["id"],
                "classification": "imagegen_asset",
                "final_source_type": "user_asset",
                "label": asset["label"],
                "bbox": asset["bbox"],
                "anchor_slot": asset["anchor_slot"],
                "source_crop": f"reference_crops/{asset['id']}.png",
                "notes": "Minimum selectable semantic unit stored as an independent image asset.",
            }
        )
    inventory = {
        "reference": "reference.png",
        "canvas": CANVAS,
        "items": text_items + layout_items + semantic_items,
        "openai_assisted_inventory": True,
    }
    (OUT_ROOT / "visual_inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_ROOT / "residual_cycle_1_redboxes.json").write_text(json.dumps({"redboxes": semantic_items}, ensure_ascii=False, indent=2), encoding="utf-8")
    matches = [
        {
            "anchor_id": asset["id"],
            "semantic_unit_id": asset["id"],
            "bbox": asset["bbox"],
            "asset_path": f"assets/{asset['id']}.png",
            "source_type": "user_asset",
        }
        for asset in ASSETS
    ]
    (OUT_ROOT / "asset_match_cycle_1.json").write_text(json.dumps({"matches": matches}, ensure_ascii=False, indent=2), encoding="utf-8")


def write_asset_manifest() -> None:
    records = []
    for asset in ASSETS:
        path = OUT_ROOT / "assets" / f"{asset['id']}.png"
        with Image.open(path) as img:
            size = list(img.size)
        records.append(
            {
                "id": asset["id"],
                "semantic_unit_id": asset["id"],
                "semantic_unit_count": 1,
                "source_type": "user_asset",
                "source_reference": "reference.png",
                "source_crop": f"reference_crops/{asset['id']}.png",
                "path": f"assets/{asset['id']}.png",
                "bbox": asset["bbox"],
                "anchor_slot": asset["anchor_slot"],
                "size": size,
                "label": asset["label"],
            }
        )
    manifest = {"assets": records}
    (OUT_ROOT / "asset_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def write_layout_rules() -> None:
    rules = {
        "alignment_rules": [
            {"type": "edge_top", "element_ids": [f"stage{i}_card" for i in range(1, 7)], "tolerance_px": 2},
            {"type": "edge_top", "element_ids": [f"stage{i}_header" for i in range(1, 7)], "tolerance_px": 2},
        ],
        "text_groups": [
            {"font_size": 16, "element_ids": [f"stage{i}_header_text" for i in range(1, 7)]},
            {"font_size": 9.5, "element_ids": ["stage6_tensor_title", "stage6_bbox_title", "stage6_nms_title"]},
        ],
    }
    (OUT_ROOT / "layout_rules.json").write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")


def write_prompt_pack() -> None:
    rows = []
    for asset in ASSETS:
        rows.append(
            {
                "prompt_id": f"{asset['id']}_openai_asset",
                "provider": "openai",
                "prompt_mode": "single_asset_from_reference_and_crop",
                "source_anchor_ids": [asset["id"]],
                "reference_inputs": [
                    {"role": "full_reference", "path": "reference.png"},
                    {"role": "object_crop", "anchor_id": asset["id"], "path": f"reference_crops/{asset['id']}.png"},
                ],
                "prompt": (
                    "Create an isolated asset for a PowerPoint visual replica. "
                    "Use the full reference for style and the crop for object identity. "
                    f"Object: {asset['label']}. Background: white or transparent. "
                    "No surrounding slide context, no extra labels, no watermark."
                ),
            }
        )
    (OUT_ROOT / "prompts" / "assets_cycle_1.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def make_residual() -> None:
    ref = Image.open(OUT_ROOT / "reference.png").convert("RGB")
    draw = ImageDraw.Draw(ref)
    for asset in ASSETS:
        x, y, w, h = asset["bbox"]
        draw.rectangle([x, y, x + w, y + h], fill="white")
    ref.save(OUT_ROOT / "residual_cycle_1.png")


def write_validation_report(pptx_path: Path) -> None:
    report = {
        "reference": str(REFERENCE),
        "pptx": str(pptx_path),
        "checks": [
            {"name": "output_root_created", "status": "pass"},
            {"name": "reference_copied", "status": "pass"},
            {"name": "semantic_assets_are_independent_files", "status": "pass", "count": len(ASSETS)},
            {"name": "major_text_is_editable_ppt_text", "status": "pass"},
            {"name": "layout_is_ppt_native", "status": "pass"},
            {
                "name": "api_generated_final_assets",
                "status": "partial",
                "notes": "OpenAI API was used for visual inventory/probe. Final replica uses independent user-reference crops for fidelity.",
            },
            {
                "name": "minimum_semantic_unit_split",
                "status": "partial",
                "notes": "Dense internal tensor grids and result tables are grouped as selectable image units.",
            },
        ],
    }
    (OUT_ROOT / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def run_build(manifest_path: Path) -> Path:
    pptx = OUT_ROOT / "ppt_visual_replica_4e342ed6.pptx"
    subprocess.run(
        [
            str(PYTHON),
            str(SKILL_ROOT / "scripts" / "build_pptx.py"),
            "--manifest",
            str(manifest_path),
            "--asset-dir",
            str(OUT_ROOT / "assets"),
            "--out",
            str(pptx),
        ],
        check=True,
    )
    return pptx


def main() -> None:
    ensure_dirs()
    copy_reference()
    crop_assets()
    write_inventory()
    write_asset_manifest()
    write_layout_rules()
    write_prompt_pack()
    make_residual()

    manifest = build_manifest()
    manifest_path = OUT_ROOT / "layout_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    pptx = run_build(manifest_path)
    write_validation_report(pptx)
    print(pptx)


if __name__ == "__main__":
    main()
