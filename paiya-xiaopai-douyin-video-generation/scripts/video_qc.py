#!/usr/bin/env python3
"""视频分镜脚本质检（规则层 + 结构层 + 覆盖层）。

用法：
  python3 video_qc.py --file storyboard.md --version V1
  python3 video_qc.py --file storyboard.md --version V1 --brief ../references/mock/mock-video-fact-card.json

只检查指定版本块，避免整份成品卡的元信息污染数字校验。
"""

import argparse
import json
import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_BRIEF = SKILL_DIR / "references" / "mock" / "mock-video-fact-card.json"

HARD_BLOCK = [
    "减肥", "燃脂", "瘦身", "提神醒脑", "治疗", "治愈", "疗效", "增强免疫力",
]
ABSOLUTE_PATTERNS = [r"最好", r"全网最低", r"唯一", r"100%", r"行业第一", r"销量第一", r"排名第一", r"第一品牌", r"第一选择"]
OFFSITE = ["加微信", "私信领券", "淘宝搜", "主页看链接", "站外"]

SHOT_ID = re.compile(r"^S\d+$")
TIMECODE = re.compile(r"(\d+(?:\.\d+)?)\s*[-~–—]\s*(\d+(?:\.\d+)?)")
DURATION = re.compile(r"(\d+(?:\.\d+)?)")
NUM = re.compile(r"\d+(?:\.\d+)?")


def read_text(path):
    return Path(path).read_text(encoding="utf-8")


def extract_version(text, version):
    start = re.search(rf"###\s*{re.escape(version)}\s*[｜|]", text)
    if not start:
        return None
    rest = text[start.start():]
    end = re.search(r"\n###\s*V\d", rest[5:])
    return rest if not end else rest[: end.start() + 5]


def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_shots(block):
    shots = []
    columns = 0
    for line in block.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = split_row(line)
        if "镜号" in cells:
            columns = len(cells)
            continue
        if set(cells[0]) <= {"-", ":", " "}:
            continue
        if SHOT_ID.match(cells[0]):
            shots.append(cells)
    return shots, columns


def clean_chars(s):
    return re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", s)


def parse_float(s, default=0.0):
    m = DURATION.search(s or "")
    return float(m.group(1)) if m else default


def check(block, shots, columns, brief):
    issues = []

    def add(level, code, msg, shot=None):
        issues.append({"level": level, "code": code, "shot": shot, "msg": msg})

    vcfg = brief.get("video", {})
    duration = vcfg.get("duration_sec", 30)
    tol = vcfg.get("duration_tolerance", 2)
    max_shot = vcfg.get("max_shot_sec", 5)
    chars_per_sec = vcfg.get("oral_chars_per_sec", 5)
    hook_deadline = vcfg.get("hook_deadline_sec", 3)
    shots_min, shots_max = vcfg.get("shots_min", 8), vcfg.get("shots_max", 14)

    # 结构层
    if not shots:
        add("BLOCK", "NO_TABLE", "未找到分镜表（首列为 S1、S2… 的行）")
        return issues
    if columns != 9:
        add("BLOCK", "COLUMNS", f"分镜表应为 9 列，实际 {columns} 列")

    parsed = []
    for cells in shots:
        if len(cells) < 9:
            cells = cells + [""] * (9 - len(cells))
        sid, tc, dur_s, size, visual, line, sub, audio, trans = cells[:9]
        m = TIMECODE.search(tc)
        if not m:
            add("BLOCK", "TIMECODE", "时间码格式应为 起-止s", sid)
            continue
        start, end = float(m.group(1)), float(m.group(2))
        dur = parse_float(dur_s, end - start)
        parsed.append({"id": sid, "start": start, "end": end, "dur": dur,
                       "line": line, "sub": sub, "visual": visual})

    if not parsed:
        return issues

    if parsed[0]["start"] != 0:
        add("BLOCK", "START_ZERO", f"首个镜头应从 0s 开始，实际 {parsed[0]['start']}s", parsed[0]["id"])

    for prev, cur in zip(parsed, parsed[1:]):
        if abs(cur["start"] - prev["end"]) > 0.5:
            add("BLOCK", "CONTINUITY", f"时间码不连续：{prev['id']} 止于 {prev['end']}s，{cur['id']} 起于 {cur['start']}s", cur["id"])

    total = parsed[-1]["end"]
    if abs(total - duration) > tol:
        add("BLOCK", "TOTAL", f"总时长 {total}s，与 brief {duration}s 偏差超过 {tol}s")

    if not (shots_min <= len(parsed) <= shots_max):
        add("WARN", "SHOT_COUNT", f"镜头数 {len(parsed)}，建议 {shots_min}–{shots_max}")

    for p in parsed:
        if p["dur"] > max_shot + 1:
            add("BLOCK", "SHOT_TOO_LONG", f"单镜 {p['dur']}s 超过 {max_shot}s", p["id"])
        elif p["dur"] > max_shot:
            add("WARN", "SHOT_LONG", f"单镜 {p['dur']}s 略超 {max_shot}s", p["id"])

    first = parsed[0]
    if first["end"] > hook_deadline or not clean_chars(first["line"] + first["sub"]):
        add("BLOCK", "HOOK", f"前 {hook_deadline}s 钩子不成立（首镜 {first['end']}s，台词/字幕为空）", first["id"])

    oral = sum(len(clean_chars(p["line"])) for p in parsed)
    limit = duration * chars_per_sec
    if oral > limit:
        add("BLOCK", "ORAL_LIMIT", f"口播共 {oral} 字，超过 {duration}s × {chars_per_sec} 字上限 {int(limit)}")

    for p in parsed:
        line_chars = len(clean_chars(p["line"]))
        if p["dur"] and line_chars > p["dur"] * chars_per_sec:
            add("WARN", "LINE_DENSITY", f"该镜 {p['dur']}s 却配 {line_chars} 字，念不完", p["id"])

    if "9:16" not in block and "9：16" not in block:
        add("WARN", "RATIO", "未标注 9:16 竖屏比例")

    last_two = parsed[-2:] if len(parsed) >= 2 else parsed
    tail_text = "".join(p["line"] + p["sub"] + p["visual"] for p in last_two)
    if not any(k in tail_text for k in ["山栖", "咖啡液"]):
        add("BLOCK", "PRODUCT_ENDING", "最后两镜未出现产品名")
    if not re.search(r"69|99", tail_text):
        add("BLOCK", "PRICE_ENDING", "最后两镜未出现价格信息")

    # 规则层
    full_text = block
    for w in HARD_BLOCK:
        if w in full_text:
            add("BLOCK", "FORBIDDEN", f"命中功效宣称词「{w}」")
    for ptn in ABSOLUTE_PATTERNS:
        m = re.search(ptn, full_text)
        if m:
            add("WARN", "ABSOLUTE", f"命中绝对化用语「{m.group(0)}」，建议改写")
    for w in OFFSITE:
        if w in full_text:
            add("BLOCK", "OFFSITE", f"命中站外引流「{w}」")

    # 覆盖层
    groups = brief.get("selling_point_keys", [])
    covered = [any(alias in full_text for alias in g) for g in groups]
    for idx, ok in enumerate(covered, 1):
        if not ok:
            add("WARN", "SP_MISS", f"第 {idx} 条卖点未落地")

    allow = {float(n) for n in brief.get("numbers_allowlist", [])}
    allow.add(round(69 / 10, 1))
    tail_numbers = []
    for p in parsed:
        for cell in (p["line"], p["sub"], p["visual"]):
            cleaned = TIMECODE.sub("", cell)
            cleaned = re.sub(r"\d{1,2}:\d{2}", "", cleaned)
            cleaned = re.sub(rf"{p['id']}", "", cleaned)
            cleaned = re.sub(r"V\d-S\d", "", cleaned)
            cleaned = re.sub(r"\d+(?:\.\d+)?\s*s\b", "", cleaned)
            for n in NUM.findall(cleaned):
                if float(n) not in allow:
                    tail_numbers.append(n)
    if tail_numbers:
        add("WARN", "NUMBER", f"待核对数字：{', '.join(sorted(set(tail_numbers)))}")

    return issues


def summarize(issues):
    blocks = [i for i in issues if i["level"] == "BLOCK"]
    warns = [i for i in issues if i["level"] == "WARN"]
    if blocks:
        verdict = "BLOCK"
    elif warns:
        verdict = "WARN"
    else:
        verdict = "PASS"
    return verdict, blocks, warns


def main():
    parser = argparse.ArgumentParser(description="视频脚本单版质检")
    parser.add_argument("--file", required=True, help="成品卡或脚本 Markdown")
    parser.add_argument("--version", required=True, help="V1 / V2 / V3")
    parser.add_argument("--brief", default=str(DEFAULT_BRIEF))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    text = read_text(args.file)
    block = extract_version(text, args.version)
    if not block:
        print(f"未找到 {args.version} 版本块（需以 `### V1｜...` 开头）")
        raise SystemExit(1)

    brief = json.loads(read_text(args.brief))
    shots, columns = parse_shots(block)
    issues = check(block, shots, columns, brief)
    verdict, blocks, warns = summarize(issues)

    if args.json:
        print(json.dumps({"version": args.version, "verdict": verdict,
                          "blocks": blocks, "warns": warns, "issues": issues},
                         ensure_ascii=False, indent=2))
        return

    print(f"{args.version} 质检：{verdict}")
    print(f"- 镜头 {len(shots)} 个｜列 {columns}｜口播 {sum(len(clean_chars(s[5])) for s in shots)} 字")
    if blocks:
        print("- BLOCK：")
        for i in blocks:
            print(f"  · [{i['code']}] {i['msg']}")
    if warns:
        print("- WARN：")
        for i in warns:
            print(f"  · [{i['code']}] {i['msg']}")
    if not issues:
        print("- 三层检查全部通过")


if __name__ == "__main__":
    main()
