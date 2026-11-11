#!/usr/bin/env python3
"""脚本质检器（POC）：规则层 + 覆盖层。

语义层需要模型判断，本脚本不覆盖。

用法：
  python3 qc_check.py --file /path/to/script.md
  python3 qc_check.py --text "正文内容"
  python3 qc_check.py --file x.md --brief references/mock/mock-fact-card.json
"""

import argparse
import json
import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_BRIEF = SKILL_DIR / "references" / "mock" / "mock-fact-card.json"

HARD_TERMS = {
    "绝对化用语": [
        "最好", "最强", "最低", "最高", "第一品牌", "全网最低", "史上最低",
        "顶级", "极致", "唯一", "永久", "彻底", "根治", "100%有效", "100% 有效", "绝对",
    ],
    "功效宣称": [
        "治疗", "治愈", "疗效", "防癌", "抗癌", "降血糖", "降血压", "降血脂",
        "减肥", "瘦身", "燃脂", "排毒", "增强免疫力", "抗衰老", "提神醒脑",
    ],
    "金融承诺": ["稳赚", "保本", "零风险", "无效退款"],
    "站外引流": [
        "加微信", "加V", "加v", "vx", "VX", "私信我", "私信领", "淘宝搜",
        "链接在评论区", "主页有链接", "代购", "扫码加",
    ],
    "违规暗示": ["内部价", "渠道价", "员工价", "绕过平台", "私下交易"],
}

WARN_PATTERNS = {
    # 只盯评价性用法；「最后」「最近」「最里面」属于正常词，不该报警
    "绝对化倾向": r"最(?:划算|值得|推荐|优惠|便宜|好吃|好喝|好用|好看|香|美|棒|佳|正宗|新鲜|适合)",
    "百分比断言": r"9[0-9]%|100%",
    # 只盯「时长 + 效果」的承诺；「5 分钟早餐」是时长描述，不是承诺
    "时效承诺": r"\d+\s*(?:天|周)\s*(?:见效|有效|变白|变瘦|瘦|改善|治好)|(?:立刻|马上|立即)\s*(?:见效|有效|变|瘦|就不|就能)",
    "程度副词": r"超级|巨[好大小]|爆炸|绝了|无敌",
}

REPLACEMENTS = {
    "最好": "我个人更常",
    "最强": "我用下来更顺手的",
    "最低": "我对比到的价格里比较划算的",
    "全网最低": "我对比到的价格里比较划算的",
    "史上最低": "我对比到的价格里比较划算的",
    "100%有效": "我自己的感受是",
    "100% 有效": "我自己的感受是",
    "永久": "长期",
    "彻底": "明显",
    "根治": "改善",
    "减肥": "热量上更放心",
    "瘦身": "热量上更放心",
    "燃脂": "热量上更放心",
    "提神醒脑": "状态回来了",
    "治疗": "（删除，食品不得宣称疗效）",
    "治愈": "（删除，食品不得宣称疗效）",
    "加微信": "评论区聊",
    "私信我": "评论区聊",
    "私信领": "主页有整理",
    "淘宝搜": "（删除站外引导）",
    "顶级": "具体的（改写为可验证事实）",
}

STRUCTURE_FIELDS = ["标题", "封面", "标签", "配图"]
BODY_ANCHORS = ["B1", "B2", "B3", "B4", "B5", "B6"]


def load_brief(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def rule_layer(text, brief_text=""):
    hits = []
    for category, terms in HARD_TERMS.items():
        for term in terms:
            start = text.find(term)
            while start != -1:
                snippet = text[max(0, start - 12): start + len(term) + 12]
                hits.append(
                    {
                        "category": category,
                        "term": term,
                        "position": start,
                        "snippet": snippet.replace("\n", " "),
                        "suggestion": REPLACEMENTS.get(term, "改写为具体、可验证的表述"),
                    }
                )
                start = text.find(term, start + len(term))
    warnings = []
    for name, pattern in WARN_PATTERNS.items():
        for match in re.finditer(pattern, text):
            term = match.group(0)
            if name == "绝对化倾向" and any(h["term"].startswith("最") for h in hits):
                continue
            if term and term in brief_text:
                # 来自 brief 的事实（如「12 小时冷萃」），不是编造，跳过
                continue
            warnings.append(
                {
                    "category": name,
                    "term": term,
                    "position": match.start(),
                    "snippet": text[max(0, match.start() - 12): match.start() + len(term) + 12].replace("\n", " "),
                }
            )
    return hits, warnings


def coverage_layer(text, brief, daily=False):
    structure = {
        "fields": {field: field in text for field in STRUCTURE_FIELDS},
        "anchors": {anchor: anchor in text for anchor in BODY_ANCHORS},
    }
    structure_ok = all(structure["fields"].values()) and all(structure["anchors"].values())

    if daily:
        # 日常创作没有 brief：只校验结构，不做卖点覆盖与事实对照
        return {
            "mode": "daily",
            "selling_points": {"covered": [], "missing": [], "count": 0, "total": 0, "skipped": True},
            "numbers": {"candidates": [], "allowlist": [], "skipped": True},
            "structure": structure,
            "structure_ok": structure_ok,
            "forbidden_claim_hits": [],
        }

    groups = brief.get("selling_point_keys", [])
    labels = brief.get("selling_points", [])
    covered = []
    missing = []
    for index, group in enumerate(groups):
        label = labels[index] if index < len(labels) else f"卖点{index + 1}"
        if any(key.replace(" ", "") in text.replace(" ", "") for key in group):
            covered.append(label)
        else:
            missing.append(label)

    allowed = {str(n) for n in brief.get("numbers_allowlist", [])}
    # 去掉锚点编号（B1/P1/V1/T1）与时间（7:40），否则会被误判成事实数字
    number_scope = re.sub(r"\b[BPVT]\d+\b", "", text)
    number_scope = re.sub(r"\d{1,2}:\d{2}", "", number_scope)
    numbers = re.findall(r"\d+(?:\.\d+)?", number_scope)
    candidates = []
    for number in numbers:
        base = number.rstrip("0").rstrip(".") if "." in number else number
        if number not in allowed and base not in allowed:
            candidates.append(number)

    structure = {
        "fields": {field: field in text for field in STRUCTURE_FIELDS},
        "anchors": {anchor: anchor in text for anchor in BODY_ANCHORS},
    }
    structure_ok = all(structure["fields"].values()) and all(structure["anchors"].values())

    forbidden = brief.get("forbidden_claims", [])
    forbidden_hits = [claim for claim in forbidden if claim in text]

    return {
        "selling_points": {
            "covered": covered,
            "missing": missing,
            "count": len(covered),
            "total": len(groups),
        },
        "numbers": {
            "candidates": sorted(set(candidates)),
            "allowlist": sorted(allowed),
        },
        "structure": structure,
        "structure_ok": structure_ok,
        "forbidden_claim_hits": forbidden_hits,
    }


def verdict_for(rule_hits, coverage, warn_count, daily=False):
    if rule_hits:
        return "BLOCK", "规则层命中硬阻断词"
    if not daily and coverage["forbidden_claim_hits"]:
        return "BLOCK", "命中 brief 禁用宣称"
    if not coverage["structure_ok"]:
        return "BLOCK", "结构不完整（缺字段或锚点）"
    if not daily and coverage["selling_points"]["count"] <= coverage["selling_points"]["total"] - 2:
        return "BLOCK", "核心卖点覆盖不足"
    if warn_count or (not daily and coverage["selling_points"]["count"] == coverage["selling_points"]["total"] - 1):
        return "WARN", "有需确认项"
    return "PASS", "规则层与结构层均通过" if daily else "规则层与覆盖层均通过"


def extract_version(text, version):
    marker = f"### {version}｜"
    if marker not in text:
        return None
    block = text.split(marker, 1)[1]
    for cut in ["\n### ", "\n## "]:
        if cut in block:
            block = block.split(cut, 1)[0]
    return marker + block


def main():
    parser = argparse.ArgumentParser(description="脚本质检器（规则层 + 覆盖层）")
    parser.add_argument("--file", help="待检脚本文件")
    parser.add_argument("--text", help="待检文本")
    parser.add_argument("--version", help="只检指定版本（V1/V2/V3），需配合 --file")
    parser.add_argument("--brief", default=str(DEFAULT_BRIEF), help="营销事实卡 JSON")
    parser.add_argument("--daily", action="store_true", help="日常创作：无 brief，跳过卖点覆盖与事实对照")
    args = parser.parse_args()

    if not args.file and not args.text:
        parser.error("需要 --file 或 --text")

    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
        if args.version:
            extracted = extract_version(text, args.version)
            if not extracted:
                parser.error(f"文件里没有找到版本 {args.version}")
            text = extracted
    else:
        text = args.text
    brief = load_brief(args.brief)

    # 锚点编号（B1/P1/V1/T3）不是正文，替换成等长空格，避免「T3 天」拼成「3 天」
    scan_text = re.sub(r"\b[BPVT]\d+\b", lambda m: " " * len(m.group(0)), text)

    rule_hits, warnings = rule_layer(scan_text, json.dumps(brief, ensure_ascii=False))
    coverage = coverage_layer(text, brief, daily=args.daily)
    verdict, reason = verdict_for(rule_hits, coverage, len(warnings), daily=args.daily)

    result = {
        "version": args.version,
        "verdict": verdict,
        "reason": reason,
        "rule_layer": {"hard_hits": rule_hits, "warnings": warnings},
        "coverage_layer": coverage,
        "semantic_layer": "未执行（需模型判断）",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n--- 摘要 ---")
    print(f"结论：{verdict}（{reason}）")
    print(f"规则层：硬阻断 {len(rule_hits)} 处，需确认 {len(warnings)} 处")
    if args.daily:
        print(
            "覆盖层：日常创作，不校验 brief 卖点；结构 {structure}".format(
                structure="完整" if coverage["structure_ok"] else "不完整"
            )
        )
    else:
        print(
            "覆盖层：卖点 {count}/{total}（缺：{missing}）；结构 {structure}；数字待核 {numbers}".format(
                count=coverage["selling_points"]["count"],
                total=coverage["selling_points"]["total"],
                missing="、".join(coverage["selling_points"]["missing"]) or "无",
                structure="完整" if coverage["structure_ok"] else "不完整",
                numbers="、".join(coverage["numbers"]["candidates"]) or "无",
            )
        )


if __name__ == "__main__":
    main()
