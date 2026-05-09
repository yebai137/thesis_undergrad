#!/usr/bin/env python3
"""Generate v1 AIGC highlight to current LaTeX comparison artifacts."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_JSON = ROOT / "finish" / "aigc_report_segments.json"
V2_REPORT_JSON = ROOT / "finish" / "v2_retry_aigc_report_segments.json"
OUT_MD = ROOT / "finish" / "v1_to_current_aigc_highlight_comparison.md"
OUT_JSON = ROOT / "finish" / "v1_to_current_aigc_highlight_comparison.json"

RISK_LABELS = {
    "ordered_three_part": "整齐编号/三段式",
    "generic_conclusion": "泛化总结句",
    "ai_high_freq": "AI高频词堆叠",
    "passive_formula": "被动分析套话",
    "template_problem": "模板化问题陈述",
}

HIGH_RISK_PATTERNS = [
    "具有重要意义",
    "由此可见",
    "综上所述",
    "实验结果表明",
    "该结果说明",
    "结果表明",
    "首先",
    "其次",
    "再次",
    "最后",
    "第一",
    "第二",
    "第三",
    "第四",
    "第五",
    "系统性指出",
    "构建",
    "稳定",
    "完整",
    "有效",
    "显著",
    "评价",
    "部署一致性",
    "上述",
]


@dataclass
class Candidate:
    file: str
    start_para: int
    end_para: int
    start_line: int
    text: str
    plain: str


def remove_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        cut = []
        escaped = False
        for ch in line:
            if ch == "%" and not escaped:
                break
            cut.append(ch)
            escaped = ch == "\\" and not escaped
            if ch != "\\":
                escaped = False
        lines.append("".join(cut).rstrip())
    return "\n".join(lines)


def extract_balanced_macro(text: str, name: str) -> str:
    marker = "\\" + name
    start = text.find(marker)
    if start < 0:
        return ""
    brace = text.find("{", start)
    if brace < 0:
        return ""
    depth = 0
    out = []
    escaped = False
    for ch in text[brace + 1 :]:
        if escaped:
            out.append(ch)
            escaped = False
            continue
        if ch == "\\":
            out.append(ch)
            escaped = True
            continue
        if ch == "{":
            depth += 1
            out.append(ch)
            continue
        if ch == "}":
            if depth == 0:
                return "".join(out)
            depth -= 1
            out.append(ch)
            continue
        out.append(ch)
    return ""


def latex_to_plain(text: str) -> str:
    text = text.replace("\\%", "%")
    text = text.replace("\\&", "&")
    text = text.replace("\\_", "_")
    text = text.replace("\\#", "#")
    text = text.replace("\\textasciitilde", "~")
    text = text.replace("---", "—").replace("--", "–")
    text = re.sub(r"\\cite[tp]?(?:\[[^\]]*\])?\{([^{}]*)\}", r"[\1]", text)
    text = re.sub(r"\\ref\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\label\{[^{}]*\}", "", text)
    text = re.sub(r"\\(section|subsection|subsubsection)\*?\{([^{}]*)\}", r"\2", text)
    # Repeatedly unwrap simple one-argument formatting commands.
    command_arg = re.compile(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?\{([^{}]*)\}")
    previous = None
    while previous != text:
        previous = text
        text = command_arg.sub(r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", "", text)
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_for_match(text: str) -> str:
    text = latex_to_plain(text).lower()
    text = text.replace("，", ",").replace("。", ".").replace("；", ";")
    text = text.replace("：", ":").replace("（", "(").replace("）", ")")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^\u4e00-\u9fff0-9a-z@._+\-]", "", text)
    return text


def grams(text: str, n: int = 2) -> set[str]:
    if len(text) <= n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def key_terms(text: str) -> set[str]:
    plain = latex_to_plain(text)
    terms = set(re.findall(r"[A-Za-z][A-Za-z0-9@.+_-]{1,}", plain))
    terms.update(re.findall(r"\d+(?:\.\d+)?", plain))
    terms.update(re.findall(r"[\u4e00-\u9fff]{2,6}", plain))
    stop = {"本文", "需要", "通过", "进行", "可以", "用于", "阶段", "结果", "分析"}
    return {t.lower() for t in terms if t and t not in stop}


def similarity(a: str, b: str) -> tuple[float, float, float]:
    na = normalize_for_match(a)
    nb = normalize_for_match(b)
    if not na or not nb:
        return 0.0, 0.0, 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    ga = grams(na)
    gb = grams(nb)
    jac = len(ga & gb) / len(ga | gb) if ga and gb else 0.0
    ka = key_terms(a)
    kb = key_terms(b)
    key = len(ka & kb) / len(ka) if ka else 0.0
    score = 0.50 * seq + 0.30 * jac + 0.20 * key
    return score, seq, key


def continuous_coverage(short_text: str, long_text: str) -> float:
    short_norm = normalize_for_match(short_text)
    long_norm = normalize_for_match(long_text)
    if not short_norm or not long_norm:
        return 0.0
    if short_norm in long_norm:
        return 1.0
    match = SequenceMatcher(None, short_norm, long_norm).find_longest_match(
        0, len(short_norm), 0, len(long_norm)
    )
    return match.size / max(len(short_norm), 1)


def split_paragraphs(raw: str) -> list[tuple[int, str]]:
    cleaned = remove_comments(raw)
    chunks = re.split(r"\n\s*\n", cleaned)
    out = []
    line_cursor = 1
    for chunk in chunks:
        start_line = line_cursor
        line_cursor += chunk.count("\n") + 2
        plain = latex_to_plain(chunk)
        if len(normalize_for_match(plain)) >= 35:
            out.append((start_line, chunk.strip()))
    return out


def build_candidates(file_rel: str, raw: str) -> list[Candidate]:
    paras = split_paragraphs(raw)
    candidates: list[Candidate] = []
    for i in range(len(paras)):
        for width in range(1, 6):
            j = i + width
            if j > len(paras):
                continue
            chunk = "\n\n".join(p[1] for p in paras[i:j])
            plain = latex_to_plain(chunk)
            candidates.append(
                Candidate(
                    file=file_rel,
                    start_para=i + 1,
                    end_para=j,
                    start_line=paras[i][0],
                    text=chunk,
                    plain=plain,
                )
            )
    return candidates


def current_text_for_segment(segment: dict, sources: dict[str, str]) -> tuple[dict, str]:
    file_rel = segment["match"]["file"]
    raw = sources[file_rel]
    text = segment["text"]

    if file_rel.endswith("abstract.tex"):
        macro = "cabstract" if segment["index"] == 1 else "eabstract"
        extracted = extract_balanced_macro(raw, macro)
        plain = latex_to_plain(extracted)
        score, seq, key = similarity(text, plain)
        return {
            "file": file_rel,
            "source": f"\\{macro}{{...}}",
            "line": 1,
            "match_score": round(score, 3),
            "sequence_score": round(seq, 3),
            "key_coverage": round(key, 3),
            "start_para": None,
            "end_para": None,
        }, plain

    candidates = build_candidates(file_rel, raw)
    scored = []
    for cand in candidates:
        score, seq, key = similarity(text, cand.plain)
        length_ratio = min(
            len(normalize_for_match(text)), len(normalize_for_match(cand.plain))
        ) / max(len(normalize_for_match(text)), len(normalize_for_match(cand.plain)), 1)
        adjusted = score * (0.85 + 0.15 * length_ratio)
        scored.append((adjusted, score, seq, key, cand))
    scored.sort(key=lambda item: item[0], reverse=True)
    adjusted, score, seq, key, cand = scored[0]
    return {
        "file": file_rel,
        "source": f"paragraphs {cand.start_para}-{cand.end_para}",
        "line": cand.start_line,
        "match_score": round(score, 3),
        "adjusted_score": round(adjusted, 3),
        "sequence_score": round(seq, 3),
        "key_coverage": round(key, 3),
        "start_para": cand.start_para,
        "end_para": cand.end_para,
    }, cand.plain


def classify(segment_text: str, current_text: str, match: dict) -> tuple[str, str]:
    score = float(match.get("match_score") or 0)
    seq = float(match.get("sequence_score") or 0)
    key = float(match.get("key_coverage") or 0)
    norm_old = normalize_for_match(segment_text)
    norm_cur = normalize_for_match(current_text)
    if not current_text.strip() or score < 0.16 or key < 0.12:
        return "需人工复核", "相似度或关键词覆盖不足，当前位置只能作为候选，不能视为可靠对应。"

    old_patterns = [p for p in HIGH_RISK_PATTERNS if p in segment_text]
    cur_patterns = [p for p in HIGH_RISK_PATTERNS if p in current_text]
    retained = sorted(set(old_patterns) & set(cur_patterns))

    containment = 0.0
    if norm_old and norm_cur:
        common = SequenceMatcher(None, norm_old, norm_cur).find_longest_match(
            0, len(norm_old), 0, len(norm_cur)
        ).size
        containment = common / max(len(norm_old), 1)

    if score >= 0.72 or seq >= 0.68 or containment >= 0.55:
        note = "当前段落与 v1 高光文本仍有较高连续重合度。"
        if retained:
            note += " 仍可见残留触发词：" + "、".join(retained[:8]) + "。"
        return "基本保留", note
    if score >= 0.43:
        note = "核心论述对象和部分关键词保留，但句序或表达已有调整。"
        if retained:
            note += " 仍保留：" + "、".join(retained[:8]) + "。"
        return "部分改写", note
    note = "同一论述位置仍可定位，但句式、衔接方式或段落组织已经明显变化。"
    if cur_patterns:
        note += " 当前候选仍出现：" + "、".join(cur_patterns[:8]) + "，建议人工查看语境。"
    return "已明显改写", note


def risk_text(flags: dict) -> str:
    if not flags:
        return "无显式标签"
    parts = []
    for key, words in flags.items():
        label = RISK_LABELS.get(key, key)
        detail = "、".join(words) if words else ""
        parts.append(f"{label}({detail})" if detail else label)
    return "；".join(parts)


def v2_flags_text(flags: list[str] | dict) -> str:
    if not flags:
        return "无显式标签"
    if isinstance(flags, dict):
        return risk_text(flags)
    return "；".join(flags)


def v2_file_rel(matched_file: str | None) -> str:
    if not matched_file:
        return ""
    if "/" in matched_file:
        return matched_file
    return f"paper/docs/{matched_file}"


def excerpt(text: str, limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "……"


def priority_for_overlap(record: dict, hits: list[dict]) -> tuple[str, str]:
    flagged = sum(1 for h in hits if h["risk_flags"])
    match_score = float(record["match"].get("match_score") or 0)
    if flagged >= 1 or len(hits) >= 3 or match_score >= 0.80:
        reasons = []
        if flagged:
            reasons.append(f"v2 仍有 {flagged} 条命中风险标签")
        if len(hits) >= 3:
            reasons.append(f"v2 同一区域命中 {len(hits)} 个非噪声片段")
        if match_score >= 0.80:
            reasons.append(f"当前表述与 v1 高光连续相似度较高({match_score:.3f})")
        return "高", "；".join(reasons)
    return "中", "v1 与 v2 均命中，但 v2 命中数量或显式标签较少，建议作为第二批处理。"


def build_v2_overlap_records(records: list[dict]) -> tuple[dict | None, list[dict]]:
    if not V2_REPORT_JSON.exists():
        return None, []
    v2_data = json.loads(V2_REPORT_JSON.read_text(encoding="utf-8"))
    v2_segments = v2_data.get("segments", [])
    overlap_records = []

    for record in records:
        if record["judgment"] != "基本保留":
            continue
        hits = []
        for segment in v2_segments:
            if segment.get("noise"):
                continue
            if v2_file_rel(segment.get("matched_file")) != record["file"]:
                continue
            text = segment.get("text", "")
            if len(normalize_for_match(text)) < 18:
                continue
            current_coverage = continuous_coverage(text, record["current_text"])
            v1_coverage = continuous_coverage(text, record["v1_highlight_text"])
            if current_coverage >= 0.62 and v1_coverage >= 0.35:
                hits.append(
                    {
                        "v2_id": segment.get("id"),
                        "text": text,
                        "chars": segment.get("chars"),
                        "aigc_percent": segment.get("aigc_percent"),
                        "risk_flags": segment.get("risk_flags") or [],
                        "current_coverage": round(current_coverage, 3),
                        "v1_coverage": round(v1_coverage, 3),
                    }
                )
        if not hits:
            continue
        hits.sort(
            key=lambda h: (
                bool(h["risk_flags"]),
                h["current_coverage"],
                h.get("chars") or 0,
            ),
            reverse=True,
        )
        priority, reason = priority_for_overlap(record, hits)
        overlap_records.append(
            {
                "v1_index": record["index"],
                "file": record["file"],
                "current_location": record["match"]["source"],
                "line": record["match"]["line"],
                "v1_match_score": record["match"]["match_score"],
                "v1_risk_summary": record["risk_summary"],
                "v2_hit_count": len(hits),
                "v2_flagged_hit_count": sum(1 for h in hits if h["risk_flags"]),
                "priority": priority,
                "priority_reason": reason,
                "top_v2_hits": hits[:8],
                "current_excerpt": excerpt(record["current_text"]),
            }
        )

    overlap_records.sort(
        key=lambda r: (
            r["priority"] == "高",
            r["v2_flagged_hit_count"],
            r["v2_hit_count"],
            r["v1_match_score"],
        ),
        reverse=True,
    )
    summary = {
        "v2_aigc_percent": v2_data.get("summary", {}).get("aigc_percent"),
        "v2_human_percent": v2_data.get("summary", {}).get("human_percent"),
        "v2_segment_count": len(v2_segments),
        "v2_non_noise_segment_count": sum(1 for s in v2_segments if not s.get("noise")),
        "double_hit_basic_retained_count": len(overlap_records),
        "double_hit_v2_segment_count": sum(r["v2_hit_count"] for r in overlap_records),
        "high_priority_count": sum(1 for r in overlap_records if r["priority"] == "高"),
        "file_distribution": dict(Counter(r["file"] for r in overlap_records)),
    }
    return summary, overlap_records


def fenced(text: str) -> str:
    return "```text\n" + text.strip() + "\n```"


def main() -> None:
    data = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    segments = data["segments"]
    if round(float(data["summary"]["aigc_percent"]), 2) != 47.60:
        raise SystemExit("Unexpected v1 AIGC percent")
    if len(segments) != 39:
        raise SystemExit(f"Unexpected segment count: {len(segments)}")

    source_files = sorted({s["match"]["file"] for s in segments})
    sources = {f: (ROOT / f).read_text(encoding="utf-8") for f in source_files}

    records = []
    for segment in segments:
        match, current = current_text_for_segment(segment, sources)
        judgment, note = classify(segment["text"], current, match)
        records.append(
            {
                "index": segment["index"],
                "file": segment["match"]["file"],
                "v1_aigc_chars": segment["aigc_chars"],
                "v1_aigc_share": segment["aigc_share"],
                "risk_flags": segment.get("risk_flags", {}),
                "risk_summary": risk_text(segment.get("risk_flags", {})),
                "v1_highlight_text": segment["text"],
                "current_text": current,
                "match": match,
                "judgment": judgment,
                "note": note,
            }
        )

    v2_overlap_summary, v2_overlap_records = build_v2_overlap_records(records)
    judgment_counts = Counter(r["judgment"] for r in records)
    risk_counts = Counter()
    for r in records:
        risk_counts.update(r["risk_flags"].keys())

    attention = defaultdict(Counter)
    for r in records:
        if r["judgment"] in {"基本保留", "部分改写", "需人工复核"}:
            attention[r["file"]][r["judgment"]] += 1

    machine = {
        "source_report": str(REPORT_JSON.relative_to(ROOT)),
        "current_source_glob": "paper/docs/*.tex",
        "summary": {
            "v1_aigc_percent": data["summary"]["aigc_percent"],
            "v1_human_percent": data["summary"]["human_percent"],
            "v1_paper_chars": data["summary"]["paper_chars"],
            "v1_paper_pages": data["summary"]["paper_pages"],
            "segment_count": len(records),
            "judgment_counts": dict(judgment_counts),
            "risk_flag_distribution": dict(risk_counts),
            "attention_by_file": {k: dict(v) for k, v in sorted(attention.items())},
            "v2_overlap_summary": v2_overlap_summary,
        },
        "v2_overlap_basic_retained_records": v2_overlap_records,
        "records": records,
    }
    OUT_JSON.write_text(json.dumps(machine, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = []
    lines.append("# v1 AIGC 高光句与当前论文表述对照\n")
    lines.append("## 整体统计\n")
    lines.append(f"- v1 报告总疑似 AIGC：{data['summary']['aigc_percent']:.2f}%")
    lines.append(f"- v1 高光/疑似片段数：{len(records)} 条")
    lines.append(
        "- 当前论文来源：`paper/docs/*.tex` 工作区内容；本文件不比较 PDF，也不修改论文正文。"
    )
    lines.append(
        "- 判断统计："
        + "；".join(f"{k} {judgment_counts.get(k, 0)} 条" for k in ["已明显改写", "部分改写", "基本保留", "需人工复核"])
    )
    lines.append(
        "- 风险标签分布："
        + "；".join(
            f"{RISK_LABELS.get(k, k)} {v} 条" for k, v in risk_counts.most_common()
        )
    )
    if attention:
        parts = []
        for file, counts in sorted(attention.items()):
            detail = "、".join(f"{k}{v}" for k, v in counts.items())
            parts.append(f"`{file}`({detail})")
        lines.append("- 当前仍需重点关注：" + "；".join(parts))
    lines.append(
        "\n说明：`匹配分数` 用于辅助定位，不等同于 AIGC 率；`基本保留` 表示连续句式或核心模板仍较相似，`部分改写` 表示主要内容对应但表达已有调整。"
    )

    lines.append("\n## 关键观察\n")
    lines.append(
        "- 摘要和 Abstract 已不再是 v1 的原始三段式写法，但仍保留相同研究对象、关键指标和部分结果句式，因此归为“部分改写”。"
    )
    lines.append(
        "- 第一章开头和第五章开篇有较明显重组；相比之下，第二章、第三章、第四章的理论/方法说明段与 v1 高光文本仍有较高连续重合度。"
    )
    lines.append(
        "- 仍需优先人工复核的残留模式包括：整齐编号串联、部署一致性相关高频词反复出现、以及“结果表明/说明/上述”等总结或被动分析句。"
    )
    lines.append(
        "- 这份文档只回答“v1 高光句现在对应论文哪里、相似到什么程度”，不判断新的维普检测一定会给出怎样的百分比。"
    )
    if v2_overlap_summary:
        lines.append(
            f"- 结合 v2 报告复核后，v1 中仍属“基本保留”的 31 条里，有 {v2_overlap_summary['double_hit_basic_retained_count']} 条还能与 v2 非噪声高光片段对上；这类内容是下一轮最应该优先处理的风险区。"
        )

    if v2_overlap_summary:
        lines.append("\n## v1/v2 双重命中且当前基本保留的高风险清单\n")
        lines.append(f"- v2 报告总疑似 AIGC：{v2_overlap_summary['v2_aigc_percent']:.2f}%")
        lines.append(
            f"- v2 片段数：{v2_overlap_summary['v2_segment_count']} 条，其中非噪声片段 {v2_overlap_summary['v2_non_noise_segment_count']} 条"
        )
        lines.append(
            f"- 双重命中且当前仍“基本保留”：{v2_overlap_summary['double_hit_basic_retained_count']} 条 v1 记录，覆盖 {v2_overlap_summary['double_hit_v2_segment_count']} 条 v2 非噪声高光片段"
        )
        lines.append(f"- 高优先级：{v2_overlap_summary['high_priority_count']} 条")
        file_parts = [
            f"`{file}` {count} 条"
            for file, count in sorted(v2_overlap_summary["file_distribution"].items())
        ]
        lines.append("- 章节分布：" + "；".join(file_parts))
        lines.append(
            "\n判定口径：仅统计 v1 判断为“基本保留”的记录；v2 片段必须是非噪声，且在当前 LaTeX 对应表述中仍有较高连续覆盖。优先级“高”表示 v2 仍出现显式风险标签、同一区域命中片段较多，或当前表述与 v1 高光连续相似度很高。"
        )

        for i, record in enumerate(v2_overlap_records, start=1):
            lines.append(
                f"\n### D{i:02d}. v1-{record['v1_index']:02d} / {record['file']}\n"
            )
            lines.append(f"- 风险优先级：**{record['priority']}**")
            lines.append(
                f"- 当前定位：`{record['current_location']}`，约第 {record['line']} 行；v1 匹配分数 {record['v1_match_score']:.3f}"
            )
            lines.append(f"- v1 风险标签：{record['v1_risk_summary']}")
            lines.append(
                f"- v2 重复命中：{record['v2_hit_count']} 条，其中带显式风险标签 {record['v2_flagged_hit_count']} 条"
            )
            lines.append(f"- 为什么大概率仍会被查到：{record['priority_reason']}")
            lines.append("- v2 高光片段摘录：")
            for hit in record["top_v2_hits"]:
                flag = v2_flags_text(hit["risk_flags"])
                lines.append(
                    f"  - V2#{hit['v2_id']}，{hit['chars']} 字，AIGC {hit['aigc_percent']}%，"
                    f"当前覆盖 {hit['current_coverage']:.2f}，标签：{flag}：{excerpt(hit['text'], 150)}"
                )
            lines.append("\n当前仍基本保留的对应表述摘录：\n")
            lines.append(fenced(record["current_excerpt"]))

    lines.append("\n## 逐条对照\n")
    for r in records:
        lines.append(f"### {r['index']:02d}. {r['file']}\n")
        lines.append(f"- v1 疑似字数/占比：{r['v1_aigc_chars']} / {r['v1_aigc_share']}")
        lines.append(f"- v1 风险标签：{r['risk_summary']}")
        lines.append(
            "- 当前定位："
            f"`{r['match']['source']}`，约第 {r['match']['line']} 行，"
            f"匹配分数 {r['match']['match_score']:.3f}，关键词覆盖 {r['match']['key_coverage']:.3f}"
        )
        lines.append(f"- 判断：**{r['judgment']}**")
        lines.append(f"- 简短说明：{r['note']}")
        lines.append("\n**v1 报告高光文本**\n")
        lines.append(fenced(r["v1_highlight_text"]))
        lines.append("\n**当前论文对应表述**\n")
        lines.append(fenced(r["current_text"]))
        lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_JSON}")
    print(json.dumps(machine["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
