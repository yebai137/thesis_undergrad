#!/usr/bin/env python3
"""Generate thesis schematic figures with gpt-image-2.

The script intentionally reads the same local Codex configuration used by the
agent runtime. It does not print secrets and stores generated candidates under
``figures/gpt_image2`` before the selected image is copied into ``paper/image``.
"""

from __future__ import annotations

import base64
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
FIGURE_DIR = ROOT / "figures"
CANDIDATE_DIR = FIGURE_DIR / "gpt_image2"
PAPER_IMAGE_DIR = ROOT / "paper" / "image"
CODEX_CONFIG = Path("/home/ywj/.codex/config.toml")
CODEX_AUTH = Path("/home/ywj/.codex/auth.json")


@dataclass(frozen=True)
class FigureSpec:
    stem: str
    output_name: str
    prompt: str


STYLE = """
绘制为中文本科毕业论文中的高质量学术流程图，横向 3:2 比例，白色背景，深蓝与青绿色为主色，
线条清晰，留白充足，适合黑白打印。使用扁平化矢量风格、细边框圆角卡片、明确箭头、少量简洁图标。
所有文字必须是简体中文，不要出现繁体字，不要出现英文乱码，不要加水印，不要加论文外的说明文字。
图片内部可以有短标题，但不要出现“图 2-2”“图 3-1”或 caption。
"""


FIGURES = [
    FigureSpec(
        stem="fig2_2_ascend_deploy",
        output_name="fig3-ascend-deploy.png",
        prompt=f"""{STYLE}
主题：海思/昇腾类开发板上的 YOLO 部署链路。
请绘制一张更高级、更完整的部署链路图，表达从训练端到板端应用的全过程。

主要流程从左到右，必须包含 6 个阶段，文字保持短句：
1. 训练权重
   PyTorch / YOLO
2. ONNX 导出
   输入输出形状
3. ATC 编译
   算子与 AIPP
4. OM 模型
   离线部署
5. NPU 推理
   模型执行
6. 解码与 NMS
   安全输出

在流程上方加入一条浅色约束带，写：输入尺寸、颜色空间、类别顺序、张量布局。
在流程下方加入两段括号式分组：
左侧覆盖阶段 1--4，写：模型格式转换；
右侧覆盖阶段 5--6，写：板端运行与后处理。
在右下角加入小型检查点卡片，写：耗时口径、输出一致性。
整体要有学术质感，避免过于简单的线框，文字必须清楚可读。""",
    ),
    FigureSpec(
        stem="fig3_1_migration_method",
        output_name="fig4-migration-method.png",
        prompt=f"""{STYLE}
主题：YOLO 双目标检测模型的边缘兼容迁移方法。
请绘制一张更高级的“方法总览图”，表达不是简单模型转换，而是带接口契约和一致性评价的迁移流程。

中央主流程从左到右，必须包含 5 个阶段：
1. 双目标任务建模
   person / ebike
2. 检测头适配
   类别数与输出维度
3. 格式迁移
   PyTorch → ONNX → OM
4. 板端推理
   NPU 执行与后处理
5. 一致性评价
   类别、边框、阈值、耗时

左侧加入场景约束面板，写三项：轿厢空间、遮挡反光、局部可见。
右侧加入接口契约面板，写五项：输入契约、类别契约、输出契约、后处理契约、运行契约。
从“一致性评价”画一条细反馈箭头回到“检测头适配/格式迁移”，表示发现问题后定位修正。
整体要比普通流程图更有层次，但不要拥挤；所有文字必须是简体中文。""",
    ),
]


def _load_client_config() -> tuple[str, str]:
    config_text = CODEX_CONFIG.read_text(encoding="utf-8")
    auth_data = json.loads(CODEX_AUTH.read_text(encoding="utf-8"))
    match = re.search(r'base_url\s*=\s*"([^"]+)"', config_text)
    if not match:
        raise RuntimeError(f"Cannot find base_url in {CODEX_CONFIG}")
    api_key = auth_data.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(f"Cannot find OPENAI_API_KEY in {CODEX_AUTH}")
    return match.group(1).rstrip("/"), api_key


def _generate_one(base_url: str, api_key: str, spec: FigureSpec, index: int) -> Path:
    payload = {
        "model": "gpt-image-2",
        "prompt": spec.prompt,
        "size": "1536x1024",
        "n": 1,
        "response_format": "b64_json",
    }
    response = requests.post(
        f"{base_url}/images/generations",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=240,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Image generation failed: {response.status_code} {response.text[:800]}")
    data = response.json()
    item = data["data"][0]
    image_bytes = base64.b64decode(item["b64_json"])
    CANDIDATE_DIR.mkdir(parents=True, exist_ok=True)
    output = CANDIDATE_DIR / f"{spec.stem}_candidate{index}.png"
    output.write_bytes(image_bytes)
    if revised_prompt := item.get("revised_prompt"):
        (CANDIDATE_DIR / f"{spec.stem}_candidate{index}.prompt.txt").write_text(
            revised_prompt,
            encoding="utf-8",
        )
    return output


def main() -> None:
    base_url, api_key = _load_client_config()
    print(f"Using image endpoint: {base_url}/images/generations")
    generated: list[Path] = []
    for spec in FIGURES:
        for index in range(1, 3):
            path = _generate_one(base_url, api_key, spec, index)
            generated.append(path)
            print(f"generated {path.relative_to(ROOT)}")

    print("Candidates generated. Inspect them before copying selected files into paper/image.")


if __name__ == "__main__":
    main()
