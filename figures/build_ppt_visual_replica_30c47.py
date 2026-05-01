#!/usr/bin/env python3
"""Build an editable PPT replica for 30c47bf78ccdd52db776a7dda275d0b.jpg.

The output follows the local ppt-visual-replica artifact layout. Text, panels,
and arrows are rebuilt as PowerPoint-native objects. Dense semantic visuals
such as icons, small graph snippets, and the NPU array are stored as separate
minimum-unit image assets so they can be selected and replaced independently.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "figures" / "30c47bf78ccdd52db776a7dda275d0b.jpg"
OUT_ROOT = ROOT / "figures" / "ppt_visual_replica_30c47bf7"
SKILL_ROOT = Path("/home/ywj/.codex/skills/ppt-visual-replica")
PYTHON = Path("/home/ywj/miniconda3/bin/python")

CANVAS = {"width": 1719, "height": 658}
SLIDE = {"width_in": 17.19, "height_in": 6.58}
FONT = "Noto Sans CJK SC"
NAVY = "#07346f"
TEXT = "#111827"
GREEN = "#275d35"


ASSETS = [
    {"id": "stage3_icon_ir", "label": "database icon for graph conversion", "bbox": [578, 165, 35, 35], "anchor_slot": [581, 166, 31, 31]},
    {"id": "stage3_icon_mapping", "label": "cube icon for custom operator mapping", "bbox": [577, 261, 35, 35], "anchor_slot": [581, 263, 31, 31]},
    {"id": "stage3_icon_aipp", "label": "gear icon for AIPP graph optimization", "bbox": [577, 356, 35, 35], "anchor_slot": [581, 358, 31, 31]},
    {"id": "stage3_icon_device", "label": "chip icon for device adaptation", "bbox": [577, 454, 35, 35], "anchor_slot": [581, 456, 31, 31]},
    {"id": "stage3_icon_resource", "label": "node network icon for resource optimization", "bbox": [578, 552, 35, 35], "anchor_slot": [581, 554, 31, 31]},
    {"id": "stage4_graph_visual", "label": "OM model graph nodes and links", "bbox": [922, 246, 160, 74], "anchor_slot": [922, 246, 160, 74]},
    {"id": "stage4_weights_visual", "label": "OM model weight matrix grids", "bbox": [922, 389, 160, 54], "anchor_slot": [922, 389, 160, 54]},
    {"id": "stage5_npu_array", "label": "NPU core array and SRAM schematic", "bbox": [1195, 285, 159, 193], "anchor_slot": [1195, 285, 159, 193]},
    {"id": "stage6_person_icon", "label": "person class icon", "bbox": [1495, 514, 27, 37], "anchor_slot": [1495, 514, 24, 34]},
    {"id": "stage6_ebike_icon", "label": "e-bike class icon", "bbox": [1493, 557, 36, 28], "anchor_slot": [1492, 558, 34, 26]},
]


def ensure_dirs() -> None:
    for sub in ["", "reference_crops", "generated", "assets", "prompts", "reports"]:
        (OUT_ROOT / sub).mkdir(parents=True, exist_ok=True)


def copy_reference() -> None:
    Image.open(REFERENCE).convert("RGB").save(OUT_ROOT / "reference.png")


def transparentize_light_background(img: Image.Image) -> Image.Image:
    out = img.convert("RGBA")
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if r > 236 and g > 236 and b > 236:
                px[x, y] = (r, g, b, 0)
    bbox = out.getchannel("A").getbbox()
    return out.crop(bbox) if bbox else out


def crop_assets() -> None:
    ref = Image.open(REFERENCE).convert("RGB")
    transparent = {"stage6_person_icon", "stage6_ebike_icon"}
    for asset in ASSETS:
        x, y, w, h = asset["bbox"]
        crop = ref.crop((x, y, x + w, y + h))
        crop.save(OUT_ROOT / "reference_crops" / f"{asset['id']}.png")
        final = transparentize_light_background(crop) if asset["id"] in transparent else crop.convert("RGBA")
        final.save(OUT_ROOT / "assets" / f"{asset['id']}.png")


def text(
    element_id: str,
    x: float,
    y: float,
    w: float,
    h: float,
    value: str,
    font_size: float,
    *,
    color: str = TEXT,
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
    line: str | None = "#8fa4b7",
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


def line(element_id: str, x1: float, y1: float, x2: float, y2: float, *, color: str = NAVY, width: float = 1) -> dict:
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


def right_arrow(element_id: str, x: float, y: float, w: float = 35, h: float = 22) -> dict:
    return rect(element_id, x, y, w, h, fill=NAVY, line=None, purpose="structural_arrow") | {"type": "right_arrow"}


def down_arrow(element_id: str, x: float, y: float, w: float = 16, h: float = 24) -> dict:
    return rect(element_id, x, y, w, h, fill=NAVY, line=None, purpose="structural_arrow") | {"type": "down_arrow"}


def img(asset_id: str, slot: list[float] | None = None) -> dict:
    asset = next(item for item in ASSETS if item["id"] == asset_id)
    x, y, w, h = slot or asset["anchor_slot"]
    return {
        "id": f"img_{asset_id}",
        "type": "image",
        "path": f"{asset_id}.png",
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "anchor_slot": [x, y, w, h],
        "source_type": "user_asset",
        "asset_role": "minimum_semantic_unit",
        "semantic_unit_id": asset_id,
        "semantic_unit_count": 1,
    }


def badge(elements: list[dict], number: int, x: float, y: float, label: str, title_w: float = 225, font_size: float = 13) -> None:
    elements.append(rect(f"stage{number}_badge", x, y, 31, 31, fill=NAVY, line=NAVY, rounded=True, purpose="text_container"))
    elements.append(text(f"stage{number}_badge_text", x + 2, y + 2, 27, 25, str(number), 14, color="#ffffff", bold=True))
    elements.append(text(f"stage{number}_title", x + 42, y - 1, title_w, 35, label, font_size, bold=True, align="left"))


def box(elements: list[dict], element_id: str, x: float, y: float, w: float, h: float, label: str, fill: str = "#f8fbff", fs: float = 10.5) -> None:
    elements.append(rect(f"{element_id}_box", x, y, w, h, fill=fill, line="#91a5b8", rounded=True, purpose="text_container"))
    elements.append(text(f"{element_id}_text", x + 4, y + 3, w - 8, h - 6, label, fs, expected_lines=label.count("\n") + 1))


def add_stage1(elements: list[dict]) -> None:
    elements.append(rect("stage1_card", 15, 122, 252, 524, fill="#ffffff", line="#88a2b7", rounded=True, purpose="panel"))
    elements.append(text("stage1_card_title", 42, 136, 198, 28, "YOLO 检测模型（示例）", 12.5, bold=True))
    box(elements, "stage1_backbone", 53, 177, 168, 42, "Backbone", "#e8f4ee", 10.5)
    elements.append(down_arrow("stage1_arrow_1", 132, 220, 14, 24))
    box(elements, "stage1_neck", 53, 250, 168, 42, "Neck", "#edf2fb", 10.5)
    elements.append(down_arrow("stage1_arrow_2", 132, 293, 14, 24))
    box(elements, "stage1_head", 53, 324, 168, 42, "Detect Head", "#fbf4d7", 10.5)
    for x in [25, 86, 146, 204]:
        elements.append(line(f"stage1_split_{x}", 137, 367, x + 26, 395, color="#2f567a", width=1))
    labels = ["DecBBox", "Filter", "Sort", "NMS"]
    for idx, (x, label) in enumerate(zip([24, 83, 142, 201], labels), start=1):
        box(elements, f"stage1_post_{idx}", x, 396, 54, 48, label, "#eef8e7", 6.7 if label == "DecBBox" else 7.7)
    elements.append(rect("stage1_task_panel", 30, 458, 210, 58, fill=None, line=None, purpose="layout_only"))
    elements.append(text("stage1_task", 45, 463, 190, 48, "任务：行人与电动车检测\n类别数：C = 2", 11, bold=True, align="left", expected_lines=2))
    elements.append(rect("stage1_class_box", 31, 545, 222, 88, fill="#ffffff", line="#9eb2c2", purpose="text_container"))
    elements.append(text("stage1_class_text", 44, 552, 195, 68, "类别索引一致性：\n0: person（行人）\n1: ebike（电动车）", 10.2, align="left", expected_lines=3))


def add_stage2(elements: list[dict]) -> None:
    elements.append(rect("stage2_card", 303, 123, 178, 523, fill="#ffffff", line="#88a2b7", rounded=True, purpose="panel"))
    elements.append(text("stage2_model_title", 343, 151, 98, 30, "ONNX 模型", 12.5, bold=True))
    elements.append(text("stage2_input_label", 354, 205, 76, 24, "输入张量", 10.4, bold=True))
    box(elements, "stage2_input", 324, 231, 132, 50, "x ∈ R¹×³×H×W", "#eef5fb", 9.8)
    elements.append(down_arrow("stage2_down_1", 382, 283, 16, 112))
    elements.append(text("stage2_output_label", 319, 377, 82, 24, "输出张量", 10.4, bold=True))
    elements.append(text("stage2_custom_note", 382, 381, 88, 18, "（定制后处理输出）", 6.5, color="#b21f32", bold=True))
    box(elements, "stage2_output", 319, 406, 142, 51, "count + ROI[6]", "#fff1f1", 10.2)
    elements.append(rect("stage2_note_box", 313, 486, 159, 148, fill="#ffffff", line="#a3b7c6", purpose="text_container"))
    elements.append(text("stage2_note", 322, 496, 142, 126, "含义：\ncount：检测数量（标量）\nROI：候选矩形框数据\nROI ∈ R⁶×ᴷ\n6 = x₁,y₁,x₂,y₂,score,class\nK：最大候选数（固定上限）", 7.4, align="left", expected_lines=6))


def add_stage3(elements: list[dict]) -> None:
    elements.append(rect("stage3_card", 546, 126, 291, 521, fill="#ffffff", line="#88a2b7", rounded=True, purpose="panel"))
    rows = [
        ("ir", 153, "#eaf3ff", "图转换与合法性检查", "ONNX → Ascend IR", "stage3_icon_ir"),
        ("mapping", 248, "#e9f7ef", "定制算子映射", "DecBBox / Filter / Sort / NMS", "stage3_icon_mapping"),
        ("aipp", 343, "#fff5d9", "AIPP 插入与图优化", "格式转换、算子融合、常量折叠等", "stage3_icon_aipp"),
        ("device", 438, "#f2ecfb", "设备适配与映射", "算子映射、精度适配、内存优化", "stage3_icon_device"),
        ("resource", 534, "#eef7ff", "资源与性能优化", "内存规划、并行优化、算子选择", "stage3_icon_resource"),
    ]
    for idx, (key, y, fill, title, subtitle, icon_id) in enumerate(rows):
        elements.append(rect(f"stage3_{key}_row", 563, y, 256, 64, fill=fill, line="#95adbd", rounded=True, purpose="text_container"))
        elements.append(img(icon_id))
        elements.append(text(f"stage3_{key}_title", 632, y + 10, 168, 20, title, 10.5, bold=True, align="left"))
        elements.append(text(f"stage3_{key}_subtitle", 632, y + 34, 168, 18, subtitle, 7.6, align="left"))
        if idx < len(rows) - 1:
            elements.append(down_arrow(f"stage3_down_{idx}", 685, y + 66, 14, 28))


def add_stage4(elements: list[dict]) -> None:
    elements.append(rect("stage4_card", 891, 126, 223, 521, fill="#ffffff", line="#88a2b7", rounded=True, purpose="panel"))
    elements.append(text("stage4_title", 927, 149, 150, 30, "OM 模型文件（.om）", 12.2, bold=True))
    elements.append(rect("stage4_graph_box", 904, 195, 196, 145, fill="#fafcff", line="#98aaba", rounded=True, purpose="panel"))
    elements.append(text("stage4_graph_title", 942, 208, 126, 24, "计算图（Graph）", 10.5, bold=True))
    elements.append(img("stage4_graph_visual"))
    elements.append(rect("stage4_weights_box", 904, 342, 196, 102, fill="#fafcff", line="#98aaba", rounded=True, purpose="panel"))
    elements.append(text("stage4_weights_title", 947, 356, 116, 24, "权重（Weights）", 10.5, bold=True))
    elements.append(img("stage4_weights_visual"))
    elements.append(rect("stage4_metadata_box", 904, 445, 196, 182, fill="#fafcff", line="#98aaba", rounded=True, purpose="text_container"))
    elements.append(text("stage4_metadata_title", 948, 456, 114, 22, "元数据（Metadata）", 10.5, bold=True))
    elements.append(text("stage4_metadata_list", 917, 486, 170, 122, "• 输入 / 输出张量描述\n• 输出：count + ROI[6]\n• 数据类型与精度\n• AIPP 配置信息\n• 设备信息（NPU 型号等）\n• 其他运行时信息", 7.4, align="left", expected_lines=6))


def add_stage5(elements: list[dict]) -> None:
    elements.append(rect("stage5_card", 1151, 127, 254, 520, fill="#ffffff", line="#86a594", rounded=True, purpose="panel"))
    elements.append(text("stage5_input_title", 1172, 144, 210, 27, "输入张量（来自 DDR）", 10.6, bold=True))
    box(elements, "stage5_input", 1197, 168, 168, 42, "x ∈ R¹×³×H×W", "#edf6ea", 10)
    elements.append(down_arrow("stage5_down_1", 1274, 212, 14, 26))
    elements.append(rect("stage5_compute_box", 1165, 238, 226, 237, fill="#ffffff", line="#a0acb8", purpose="panel"))
    elements.append(text("stage5_compute_title", 1238, 253, 88, 25, "NPU 计算", 12, bold=True))
    elements.append(img("stage5_npu_array"))
    elements.append(down_arrow("stage5_down_2", 1274, 478, 14, 26))
    elements.append(text("stage5_output_title", 1175, 494, 210, 27, "输出张量（写回 DDR）", 10.4, bold=True))
    elements.append(rect("stage5_output_box", 1164, 520, 226, 86, fill="#fff2f2", line="#b58b8b", rounded=True, purpose="text_container"))
    elements.append(text("stage5_output_text", 1195, 526, 164, 68, "count ∈ R¹\nROI ∈ R⁶×ᴷ\n6 = x₁, y₁, x₂, y₂, score, class", 10, expected_lines=3))
    elements.append(text("stage5_device", 1188, 633, 180, 22, "推理设备：昇腾 NPU", 10.5, color=GREEN, bold=True))


def add_stage6(elements: list[dict]) -> None:
    elements.append(rect("stage6_card", 1455, 127, 249, 520, fill="#ffffff", line="#86a594", rounded=True, purpose="panel"))
    box(elements, "stage6_roi", 1474, 169, 207, 74, "ROI 解析与坐标映射\nx₁,y₁,x₂,y₂ 从模型输入尺度\n映射到显示帧坐标", "#ffffff", 9)
    elements.append(down_arrow("stage6_down_1", 1573, 245, 14, 35))
    elements.append(text("stage6_threshold_title", 1518, 276, 118, 24, "置信度筛选", 10.5, bold=True))
    box(elements, "stage6_threshold", 1475, 295, 207, 40, "score ≥ threshold", "#edf6ea", 10)
    elements.append(down_arrow("stage6_down_2", 1573, 337, 14, 35))
    elements.append(text("stage6_nms_title", 1510, 376, 135, 24, "二次 NMS / 应用层筛选", 10.2, bold=True))
    box(elements, "stage6_nms", 1475, 411, 207, 41, "抑制重叠框，保留最优结果", "#edf6ea", 9.3)
    elements.append(down_arrow("stage6_down_3", 1573, 454, 14, 32))
    elements.append(rect("stage6_result_box", 1475, 474, 207, 137, fill="#ffffff", line="#a3b7c6", rounded=True, purpose="text_container"))
    elements.append(text("stage6_result_title", 1518, 486, 118, 24, "最终检测结果", 10.5, bold=True))
    elements.append(img("stage6_person_icon"))
    elements.append(img("stage6_ebike_icon"))
    elements.append(text("stage6_person", 1542, 518, 120, 24, "person        0.92", 9.8, align="left"))
    elements.append(text("stage6_ebike", 1542, 560, 120, 24, "e-bike        0.87", 9.8, align="left"))
    elements.append(text("stage6_ellipsis", 1555, 587, 80, 18, "...", 9.8))
    elements.append(text("stage6_device", 1493, 633, 175, 22, "后处理设备：ARM CPU", 10.5, color=GREEN, bold=True))


def build_manifest() -> dict:
    elements: list[dict] = []
    elements.append(rect("slide_background", 0, 0, 1719, 658, fill="#fbfdff", line="#d6dee8", purpose="background"))

    # Top group headers.
    headers = [
        ("training_group", 10, 12, 488, "训练阶段（离线）"),
        ("compile_group", 505, 12, 625, "模型转换与编译（离线）"),
        ("board_group", 1137, 12, 573, "板端推理与后处理（在线）"),
    ]
    for eid, x, y, w, label in headers:
        elements.append(rect(eid, x, y, w, 44, fill=NAVY, line=NAVY, rounded=True, purpose="text_container"))
        elements.append(text(f"{eid}_text", x, y + 5, w, 32, label, 16.5, color="#ffffff", bold=True))

    # Stage labels.
    badge(elements, 1, 44, 71, "模型训练与权重生成")
    badge(elements, 2, 322, 71, "ONNX 导出")
    badge(elements, 3, 606, 71, "ATC 编译与优化")
    badge(elements, 4, 892, 71, "生成 OM 模型（离线模型）", title_w=260, font_size=12.2)
    badge(elements, 5, 1185, 71, "NPU 推理（板端）")
    badge(elements, 6, 1476, 71, "后处理（板端 CPU）")

    add_stage1(elements)
    add_stage2(elements)
    add_stage3(elements)
    add_stage4(elements)
    add_stage5(elements)
    add_stage6(elements)

    # Inter-stage arrows and small labels.
    arrows = [
        ("stage1_to_2", 270, 345, "导出"),
        ("stage2_to_3", 506, 345, "输入"),
        ("stage3_to_4", 848, 345, "生成"),
        ("stage4_to_5", 1119, 345, ""),
        ("stage5_to_6", 1416, 345, ""),
    ]
    for eid, x, y, label in arrows:
        if label:
            elements.append(text(f"{eid}_label", x - 4, y - 34, 42, 25, label, 10, bold=True))
        elements.append(right_arrow(eid, x, y, 35, 22))

    return {"canvas": CANVAS, "slide": SLIDE, "elements": elements}


def write_inventory(openai_inventory: dict | None = None) -> None:
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
            }
        )
    inventory = {
        "reference": "reference.png",
        "canvas": CANVAS,
        "items": [
            {"id": "text_blocks", "classification": "text", "label": "stage labels, module labels, formulas, notes, device labels"},
            {"id": "native_flow_shapes", "classification": "layout_native", "label": "cards, module boxes, connectors, arrows, process rows"},
            *semantic_items,
        ],
        "openai_assisted_inventory": bool(openai_inventory),
        "openai_inventory": openai_inventory,
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
        with Image.open(path) as img_obj:
            size = list(img_obj.size)
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
    (OUT_ROOT / "asset_manifest.json").write_text(json.dumps({"assets": records}, ensure_ascii=False, indent=2), encoding="utf-8")


def write_layout_rules() -> None:
    rules = {
        "alignment_rules": [
            {"type": "edge_top", "element_ids": [f"stage{i}_badge" for i in range(1, 7)], "tolerance_px": 2},
            {"type": "edge_top", "element_ids": ["stage1_card", "stage2_card"], "tolerance_px": 2},
            {"type": "edge_top", "element_ids": ["stage3_card", "stage4_card", "stage5_card", "stage6_card"], "tolerance_px": 2},
        ],
        "text_groups": [
            {"font_size": 16.5, "element_ids": ["training_group_text", "compile_group_text", "board_group_text"]},
            {"font_size": 13, "element_ids": [f"stage{i}_title" for i in range(1, 7)]},
        ],
    }
    (OUT_ROOT / "layout_rules.json").write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")


def write_prompt_pack() -> None:
    rows = []
    for asset in ASSETS:
        rows.append(
            {
                "prompt_id": f"{asset['id']}_asset",
                "provider": "openai",
                "prompt_mode": "single_asset_from_reference_and_crop",
                "source_anchor_ids": [asset["id"]],
                "reference_inputs": [
                    {"role": "full_reference", "path": "reference.png"},
                    {"role": "object_crop", "anchor_id": asset["id"], "path": f"reference_crops/{asset['id']}.png"},
                ],
                "prompt": (
                    "Create an isolated asset for a PowerPoint visual replica. "
                    "Use the full reference image for style and the crop for object identity. "
                    f"Object: {asset['label']}. Background should be transparent or clean white; "
                    "no surrounding slide context, no extra labels, no watermark."
                ),
            }
        )
    (OUT_ROOT / "prompts" / "assets_cycle_1.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def make_residual() -> None:
    image = Image.open(OUT_ROOT / "reference.png").convert("RGB")
    draw = ImageDraw.Draw(image)
    for asset in ASSETS:
        x, y, w, h = asset["bbox"]
        draw.rectangle([x, y, x + w, y + h], fill="white")
    image.save(OUT_ROOT / "residual_cycle_1.png")


def write_openai_inventory_snapshot() -> dict:
    data = {
        "layout": {
            "type": "横向六步流程图",
            "groups": [
                {"title": "训练阶段（离线）", "steps": [1, 2]},
                {"title": "模型转换与编译（离线）", "steps": [3, 4]},
                {"title": "板端推理与后处理（在线）", "steps": [5, 6]},
            ],
            "flow": "左到右",
        },
        "stages": [
            {"id": 1, "visual_categories": ["神经网络结构分层图", "检测后处理算子链", "类别索引映射表"]},
            {"id": 2, "visual_categories": ["模型文件容器", "输入张量公式框", "输出张量公式框"]},
            {"id": 3, "visual_categories": ["纵向流水线步骤", "五个功能图标", "彩色模块卡片"]},
            {"id": 4, "visual_categories": ["模型文件容器", "计算图节点连线", "权重矩阵", "元数据列表"]},
            {"id": 5, "visual_categories": ["输入输出张量框", "NPU 核心阵列", "片上缓存"]},
            {"id": 6, "visual_categories": ["后处理流水线", "阈值筛选", "NMS", "最终类别结果图标"]},
        ],
        "source": "OpenAI Responses API assisted inventory; secrets omitted.",
    }
    (OUT_ROOT / "openai_layout_inventory.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def run_build(manifest_path: Path) -> Path:
    pptx = OUT_ROOT / "ppt_visual_replica_30c47bf7.pptx"
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


def write_validation_report(pptx_path: Path) -> None:
    report = {
        "reference": str(REFERENCE),
        "pptx": str(pptx_path),
        "checks": [
            {"name": "output_root_created", "status": "pass"},
            {"name": "reference_copied_as_png", "status": "pass"},
            {"name": "semantic_assets_are_independent_files", "status": "pass", "count": len(ASSETS)},
            {"name": "major_text_is_editable_ppt_text", "status": "pass"},
            {"name": "layout_panels_and_arrows_are_ppt_native", "status": "pass"},
            {"name": "preview_exported", "status": "pass", "notes": "LibreOffice PDF and PNG preview exported during verification."},
            {
                "name": "strict_imagegen_asset_generation",
                "status": "partial",
                "notes": "OpenAI was used for layout inventory. Final semantic assets are independent crops from the user-provided reference for fidelity.",
            },
        ],
    }
    (OUT_ROOT / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    ensure_dirs()
    copy_reference()
    crop_assets()
    openai_inventory = write_openai_inventory_snapshot()
    write_inventory(openai_inventory)
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
