#!/usr/bin/env python3
"""抖音视频脚本意图打分器（POC）。

用法：
  python3 intent_score.py --text "帮我写个30秒抖音口播脚本"
  python3 intent_score.py --text "..." --attachment
  python3 intent_score.py --eval ../references/video-cases.jsonl

与小红书技能的差别：这里的正例是视频形态，识别到图文笔记时反向转交。
"""

import argparse
import json
import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
FACT_CARD = SKILL_DIR / "references" / "mock" / "mock-video-fact-card.json"

VIDEO_TERMS = ["视频脚本", "短视频", "分镜", "口播稿", "拍摄脚本", "镜头", "竖屏", "成片", "剪辑"]
ARTICLE_TERMS = ["图文", "笔记", "封面", "话题", "标签", "种草文"]
PLATFORM_XHS = ["小红书", "红书", "xhs"]
PLATFORM_DY = ["抖音", "douyin"]

ACTION_PATTERNS = [r"写(?!法|作)", r"生成", r"拍(?!摄)", r"(?:来|做|出)一[条个篇]", r"改(?:一下|成|为)?", r"换"]
OBJECT_TERMS = ["视频脚本", "分镜", "口播稿", "短视频", "脚本", "镜头", "文案"]
COMMERCIAL_TERMS = ["商单", "合作", "推广", "报备", "brief", "Brief", "BRIEF", "品牌方", "甲方", "挂车", "小黄车"]
SPEC_PATTERNS = [r"\d+\s*秒", r"\d+\s*s\b", r"\d+\s*条", r"\d+\s*版", r"三版", r"三条", r"15s", r"30s", r"60s"]
L2_VERB_PATTERNS = [r"写", r"生成", r"拍", r"(?:来|做|出)一[条个篇]", r"改", r"换"]
CONTENT_TERMS = ["卖点", "人群", "场景", "成分", "价格", "测评", "开箱", "口感", "性价比", "转化", "种草", "钩子"]
PLATFORM_DENSITY_GROUPS = [("抖音", ["抖音", "douyin"]), ("视频", ["视频", "短视频"]), ("分镜/口播", ["分镜", "口播"])]

METHOD_PATTERNS = [r"怎么起号", r"如何起号", r"涨粉", r"完播", r"几点发", r"限流", r"怎么运营", r"如何运营", r"平台规则", r"账号权重", r"投流"]
EVALUATE_PATTERNS = [r"帮我看看", r"看看这", r"分析一下", r"诊断", r"复盘", r"为什么没流量", r"问题在哪", r"哪里不好", r"给点建议", r"评估"]
CHAT_PATTERNS = [r"^你好", r"^在吗", r"谢谢", r"天气", r"随便聊", r"哈喽", r"早上好", r"晚安"]
EXIT_PATTERNS = [r"不用写", r"先不生成", r"算了", r"不需要", r"停止生成"]

REWRITE_MARKERS = [r"改", r"换", r"调整", r"重写", r"加", r"删"]
REFERENCE_MARKERS = [r"第一版", r"第二版", r"第三版", r"这版", r"那版", r"刚才", r"上面", r"V1", r"V2", r"V3", r"第[一二三]个", r"第\d+秒"]

HAS_VERB = re.compile(r"写|生成|拍|润色|改|换")


def term_hits(terms, text):
    return [t for t in terms if t in text]


def hits(patterns, text):
    return [p for p in patterns if re.search(p, text)]


def detect_modality(text):
    has_dy = any(k in text for k in PLATFORM_DY)
    has_xhs = any(k in text for k in PLATFORM_XHS)
    has_video = any(k in text for k in VIDEO_TERMS)
    has_article = any(k in text for k in ARTICLE_TERMS)

    if has_dy:
        return "video", "抖音"
    if has_xhs and has_video:
        return "video", "小红书"
    if has_xhs:
        return "article", "小红书"
    if has_video and has_article:
        return "ambiguous", ""
    if has_video:
        return "video", "抖音"
    if has_article:
        return "article", "小红书"
    return "unspecified", ""


def score(text, has_attachment=False, force_commercial=False):
    evidence = {}
    l1 = {}

    if any(k in text for k in PLATFORM_DY):
        l1["L1.platform"] = 20
    if hits(ACTION_PATTERNS, text):
        l1["L1.action"] = 20
    obj = term_hits(OBJECT_TERMS, text)
    if obj:
        l1["L1.object"] = 15
    if has_attachment:
        l1["L1.brief"] = 25
    if term_hits(COMMERCIAL_TERMS, text) or force_commercial:
        l1["L1.commercial"] = 20
    if hits(SPEC_PATTERNS, text):
        l1["L1.spec"] = 10

    l1_score = min(sum(l1.values()), 65)
    evidence["l1"] = list(l1.keys())

    l2 = {}
    verb_hits = hits(L2_VERB_PATTERNS, text)
    if verb_hits:
        l2["L2.verbs"] = min(len(verb_hits) * 8, 16)
    content_hits = term_hits(CONTENT_TERMS, text)
    if len(content_hits) >= 2:
        l2["L2.content"] = min((len(content_hits) // 2) * 3, 9)
    density_groups = [name for name, variants in PLATFORM_DENSITY_GROUPS if any(v in text for v in variants)]
    if len(density_groups) >= 2:
        l2["L2.platform_density"] = 5
    l2_score = min(sum(l2.values()), 30)

    penalties = {}
    if hits(METHOD_PATTERNS, text):
        penalties["P.method"] = -25
    if hits(EVALUATE_PATTERNS, text) and not HAS_VERB.search(text):
        penalties["P.evaluate"] = -20
    if hits(CHAT_PATTERNS, text):
        penalties["P.chat"] = -40
    if any(k in text for k in PLATFORM_DY) and not hits(ACTION_PATTERNS, text) and not obj:
        penalties["P.weak"] = -10

    total = max(0, min(l1_score + l2_score + sum(penalties.values()), 95))
    return {
        "score": total,
        "layers": {"l1": l1, "l1_score": l1_score, "l2": l2, "l2_score": l2_score, "penalties": penalties},
        "evidence": evidence,
        "has_attachment": has_attachment,
        "has_brief": has_attachment or bool(term_hits(COMMERCIAL_TERMS, text)) or force_commercial,
    }


def decide(text, result, in_flow=False):
    notes = []
    if in_flow:
        is_rewrite = hits(REWRITE_MARKERS, text) and (hits(REFERENCE_MARKERS, text) or len(text) <= 40)
        return ("rewrite" if is_rewrite else "continue"), None, notes

    if hits(EXIT_PATTERNS, text):
        return "exit", None, ["命中显式拒绝对话"]

    if hits(EVALUATE_PATTERNS, text) and not HAS_VERB.search(text):
        return "evaluate", None, ["评估诉求前置，只做评估"]

    if hits(METHOD_PATTERNS, text):
        return "chat", None, ["方法论提问前置，按日常问答"]

    score_value = result["score"]
    if score_value >= 70:
        return "generate", None, ["总分 ≥70，直接触发"]
    if score_value >= 40:
        if result["has_brief"]:
            return "generate", None, ["商单带 brief，40–69 区间仍直接触发"]
        return "llm_check", "是否需要 LLM 二判", ["总分 40–69，需 LLM 二判"]
    return "chat", None, ["总分 <40，按日常问答"]


def route(intent, modality, text):
    """形态路由：视频技能只接视频，图文反向转交，说不清就确认。"""
    strong_video = any(k in text for k in ["分镜", "口播稿", "视频脚本", "短视频"])
    creation = hits(ACTION_PATTERNS, text) and (
        term_hits(OBJECT_TERMS, text)
        or any(k in text for k in ["笔记", "图文", "种草文", "标题正文"])
    )

    # 「写个分镜」这类强形态词，无需平台词也直接触发
    if modality[0] == "video" and strong_video and creation and intent in ("chat", "llm_check"):
        return "generate"

    if intent in ("generate", "llm_check") or (intent == "chat" and creation):
        if modality[0] == "article":
            return "handoff_article"
        if modality[0] in ("ambiguous", "unspecified"):
            return "confirm_modality"
    return intent


def run_eval(path):
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        item = json.loads(line)
        result = score(item["text"], has_attachment=item.get("attachment", False))
        predicted, _, _ = decide(item["text"], result, in_flow=item.get("in_flow", False))
        predicted = route(predicted, detect_modality(item["text"]), item["text"])
        expected = item["expected"]
        rows.append((item["text"], expected, predicted, result["score"], predicted == expected))

    total = len(rows)
    correct = sum(1 for r in rows if r[4])
    print(f"评测样本：{total}，命中：{correct}，准确率：{correct / total:.1%}" if total else "无样本")
    print(f"{'结果':<6}{'期望':<16}{'预测':<16}{'分数':<6}输入")
    for text, expected, predicted, score_value, ok in rows:
        print(f"{'✓' if ok else '✗':<6}{expected:<16}{predicted:<16}{score_value:<6}{text}")


def main():
    parser = argparse.ArgumentParser(description="抖音视频脚本意图打分器")
    parser.add_argument("--text", help="用户输入文本")
    parser.add_argument("--attachment", action="store_true", help="是否带产品资料附件")
    parser.add_argument("--in-flow", action="store_true", help="是否处于脚本链路中")
    parser.add_argument("--commercial", action="store_true", help="是否显式商单")
    parser.add_argument("--eval", dest="eval_file", help="批量评测 jsonl 文件")
    args = parser.parse_args()

    if args.eval_file:
        run_eval(args.eval_file)
        return
    if not args.text:
        parser.error("需要 --text 或 --eval")

    result = score(args.text, has_attachment=args.attachment, force_commercial=args.commercial)
    intent, llm_check, notes = decide(args.text, result, in_flow=args.in_flow)
    modality, platform = detect_modality(args.text)
    intent = route(intent, (modality, platform), args.text)

    if intent == "handoff_article":
        notes.append("识别为图文笔记，转交 paiya-xiaopai-xhs-generation")
    elif intent == "confirm_modality":
        notes.append("图文与视频说不清，需向用户确认一次")

    output = {
        "text": args.text,
        "intent": intent,
        "mode": "视频" if intent in ("generate", "llm_check") else ("待确认" if intent == "confirm_modality" else "对话"),
        "modality": modality,
        "platform": platform,
        "score": result["score"],
        "layers": result["layers"],
        "evidence": result["evidence"],
        "handoff": "paiya-xiaopai-xhs-generation" if intent == "handoff_article" else None,
        "llm_check": llm_check,
        "notes": notes,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
