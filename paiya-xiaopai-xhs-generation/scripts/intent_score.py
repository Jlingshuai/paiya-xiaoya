#!/usr/bin/env python3
"""小红书脚本意图打分器（POC）。

用法：
  python3 intent_score.py --text "帮我写3篇小红书笔记"
  python3 intent_score.py --text "..." --attachment brief.pdf
  python3 intent_score.py --text "..." --in-flow
  python3 intent_score.py --eval cases.jsonl

规则与阈值见 references/intent-rubric.md，本脚本是该文档的可执行实现。
"""

import argparse
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
FACT_CARD = SKILL_DIR / "references" / "mock" / "mock-fact-card.json"

PLATFORM_TERMS = ["小红书", "红书", "xhs", "图文笔记", "种草文"]
ACTION_PATTERNS = [
    r"写(?!法|作)",
    r"生成",
    r"(?:来|做|出)一篇",
    r"润色",
    r"扩写",
    r"重写",
    r"改(?:一下|改|成|为|下)?",
    r"换(?:个|一|掉)?标题",
]
OBJECT_TERMS = ["标题正文", "笔记", "脚本", "文案", "标题", "三版", "版本"]
COMMERCIAL_TERMS = ["商单", "合作", "推广", "报备", "brief", "Brief", "BRIEF", "品牌方", "甲方"]
SPEC_PATTERNS = [
    r"\d+\s*篇",
    r"\d+\s*版",
    r"\d+\s*个版本",
    r"三个版本",
    r"三版",
    r"带话题",
    r"带标签",
    r"标题加正文",
    r"标题\+正文",
]
L2_VERB_PATTERNS = [
    r"写",
    r"生成",
    r"(?:来|做|出)一篇",
    r"润色",
    r"扩写",
    r"重写",
    r"改",
    r"换",
]
CONTENT_TERMS = ["卖点", "人群", "场景", "成分", "价格", "测评", "开箱", "口感", "性价比", "转化", "种草"]
PLATFORM_DENSITY_GROUPS = [
    ("小红书", ["小红书", "红书"]),
    ("xhs", ["xhs"]),
    ("图文", ["图文"]),
    ("笔记/封面", ["笔记", "封面"]),
    ("话题/标签", ["话题", "标签"]),
]

METHOD_PATTERNS = [
    r"怎么起号", r"如何起号", r"涨粉", r"违规词", r"几点发", r"限流",
    r"怎么运营", r"如何运营", r"平台规则", r"账号权重",
]
EVALUATE_PATTERNS = [
    r"帮我看看", r"看看这篇", r"分析一下", r"诊断", r"复盘", r"为什么没流量",
    r"问题在哪", r"哪里不好", r"给点建议", r"评估",
]
CHAT_PATTERNS = [r"^你好", r"^在吗", r"谢谢", r"天气", r"随便聊", r"哈喽", r"早上好", r"晚安"]
EXIT_PATTERNS = [r"不用写", r"先不生成", r"算了", r"不需要", r"停止生成"]
SCOPE_PATTERNS = [r"抖音", r"视频脚本", r"短视频", r"分镜", r"直播话术", r"口播稿"]
VIDEO_TERMS = ["视频脚本", "短视频", "分镜", "口播稿", "拍摄脚本", "镜头", "竖屏", "成片", "剪辑"]
ARTICLE_TERMS = ["图文", "笔记", "封面", "话题", "标签", "种草文"]
PLATFORM_XHS_TERMS = ["小红书", "红书", "xhs"]
PLATFORM_DOUYIN_TERMS = ["抖音", "douyin", "Douyin"]
REWRITE_MARKERS = [r"改", r"换", r"调整", r"润色", r"加", r"删", r"重写"]
REFERENCE_MARKERS = [r"第一版", r"第二版", r"第三版", r"这版", r"那版", r"刚才", r"上面", r"V1", r"V2", r"V3", r"第[一二三]个"]

HAS_VERB = re.compile(r"写|生成|润色|扩写|重写|改|换标题")


def hits(patterns, text):
    matched = []
    for pat in patterns:
        if re.search(pat, text):
            matched.append(pat)
    return matched


def term_hits(terms, text):
    return [t for t in terms if t in text]


def load_entities():
    entities = []
    if FACT_CARD.exists():
        try:
            card = json.loads(FACT_CARD.read_text(encoding="utf-8"))
            for key in ("brand", "product"):
                value = card.get(key)
                if value:
                    entities.append(value)
            for token in card.get("entity_aliases", []):
                entities.append(token)
        except json.JSONDecodeError:
            pass
    return entities


def score(text, has_attachment=False, in_flow=False, entities=None, force_commercial=False):
    entities = entities or load_entities()
    l1 = {}
    evidence = []

    platform = term_hits(PLATFORM_TERMS, text)
    if platform:
        l1["L1.platform"] = 20
        evidence.append({"signal": "L1.platform", "span": platform[0]})

    action = hits(ACTION_PATTERNS, text)
    if action:
        l1["L1.action"] = 20
        evidence.append({"signal": "L1.action", "span": action[0]})

    obj = term_hits(OBJECT_TERMS, text)
    if obj:
        l1["L1.object"] = 15
        evidence.append({"signal": "L1.object", "span": obj[0]})

    if has_attachment:
        l1["L1.brief"] = 25
        evidence.append({"signal": "L1.brief", "span": "attachment"})

    commercial = term_hits(COMMERCIAL_TERMS, text)
    if commercial or force_commercial:
        l1["L1.commercial"] = 20
        evidence.append({"signal": "L1.commercial", "span": commercial[0] if commercial else "force"})

    spec = hits(SPEC_PATTERNS, text)
    if spec:
        l1["L1.spec"] = 10
        evidence.append({"signal": "L1.spec", "span": spec[0]})

    entity_hit = [e for e in entities if e and e in text]
    if entity_hit:
        l1["L1.entity"] = 10
        evidence.append({"signal": "L1.entity", "span": entity_hit[0]})

    l1_score = min(sum(l1.values()), 65)

    l2 = {}
    verb_hits = hits(L2_VERB_PATTERNS, text)
    if verb_hits:
        l2["L2.verbs"] = min(len(verb_hits) * 8, 16)

    content_hits = term_hits(CONTENT_TERMS, text)
    if len(content_hits) >= 2:
        l2["L2.content"] = min((len(content_hits) // 2) * 3, 9)

    density_groups = [
        name
        for name, variants in PLATFORM_DENSITY_GROUPS
        if any(v in text for v in variants)
    ]
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
    if platform and not action and not obj:
        penalties["P.weak"] = -10

    total = max(0, min(l1_score + l2_score + sum(penalties.values()), 95))

    return {
        "score": total,
        "layers": {
            "l1": l1,
            "l1_score": l1_score,
            "l2": l2,
            "l2_score": l2_score,
            "penalties": penalties,
        },
        "evidence": evidence,
        "has_attachment": has_attachment,
        "has_brief": has_attachment or bool(commercial) or force_commercial,
    }


def detect_modality(text):
    """判断用户要的是图文笔记还是视频脚本，以及是否说不清。"""
    has_douyin = any(k in text for k in PLATFORM_DOUYIN_TERMS)
    has_xhs = any(k in text for k in PLATFORM_XHS_TERMS)
    has_video = any(k in text for k in VIDEO_TERMS)
    has_article = any(k in text for k in ARTICLE_TERMS)

    if has_douyin:
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


def decide(text, result, in_flow=False):
    notes = []
    if in_flow:
        is_rewrite = hits(REWRITE_MARKERS, text) and (
            hits(REFERENCE_MARKERS, text) or len(text) <= 40
        )
        return ("rewrite" if is_rewrite else "continue", "degrade" if False else None, notes)

    if hits(EXIT_PATTERNS, text):
        return "exit", None, ["命中显式拒绝对话"]

    if hits(EVALUATE_PATTERNS, text) and not HAS_VERB.search(text):
        notes.append("评估诉求前置，只做评估")
        return "evaluate", None, notes

    if hits(METHOD_PATTERNS, text):
        notes.append("方法论提问前置，按日常问答")
        return "chat", None, notes

    score = result["score"]
    if score >= 70:
        notes.append("总分 ≥70，直接触发")
        return "generate", None, notes

    if score >= 40:
        if result["has_brief"]:
            notes.append("商单带 brief，40–69 区间仍直接触发")
            return "generate", None, notes
        notes.append("总分 40–69，需 LLM 二判")
        return "llm_check", "是否需要 LLM 二判", notes

    notes.append("总分 <40，按日常问答")
    return "chat", None, notes


def main():
    parser = argparse.ArgumentParser(description="小红书脚本意图打分器")
    parser.add_argument("--text", help="用户输入文本")
    parser.add_argument("--attachment", action="store_true", help="是否带产品资料附件")
    parser.add_argument("--in-flow", action="store_true", help="是否处于脚本链路中")
    parser.add_argument("--commercial", action="store_true", help="是否显式商单")
    parser.add_argument("--entities", default="", help="额外实体，逗号分隔")
    parser.add_argument("--eval", dest="eval_file", help="批量评测 jsonl 文件")
    args = parser.parse_args()

    if args.eval_file:
        run_eval(args.eval_file)
        return

    if not args.text:
        parser.error("需要 --text 或 --eval")

    entities = load_entities()
    if args.entities:
        entities += [e.strip() for e in args.entities.split(",") if e.strip()]

    result = score(
        args.text,
        has_attachment=args.attachment,
        in_flow=args.in_flow,
        entities=entities,
        force_commercial=args.commercial,
    )
    intent, llm_check, notes = decide(args.text, result, in_flow=args.in_flow)
    modality, platform = detect_modality(args.text)

    # 形态路由：只有要「生成/待确认」的请求才需要分图文还是视频
    if intent in ("generate", "llm_check"):
        if modality == "video":
            intent = "handoff_video"
            notes.append(f"识别为视频脚本（{platform or '平台未写明'}），转交抖音视频技能")
        elif modality == "ambiguous":
            intent = "confirm_modality"
            notes.append("图文与视频信号同时出现，需向用户确认走哪条分支")
        elif modality == "unspecified":
            intent = "confirm_modality"
            notes.append("看不出要图文还是视频，需向用户确认一次")

    mode = "商单" if result["has_brief"] else "日常"
    if intent == "handoff_video":
        mode = "视频"
    elif intent == "confirm_modality":
        mode = "待确认"

    output = {
        "text": args.text,
        "intent": intent,
        "mode": mode,
        "modality": modality,
        "platform": platform,
        "score": result["score"],
        "layers": result["layers"],
        "evidence": result["evidence"],
        "llm_check": llm_check,
        "handoff": "paiya-xiaopai-douyin-video-generation" if intent == "handoff_video" and platform != "小红书" else None,
        "brief_required": bool(result["has_brief"] and not args.attachment and intent == "generate" and mode == "商单"),
        "notes": notes,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def run_eval(path):
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        item = json.loads(line)
        result = score(item["text"], has_attachment=item.get("attachment", False))
        predicted, _, _ = decide(item["text"], result, in_flow=item.get("in_flow", False))
        modality, platform = detect_modality(item["text"])
        if predicted in ("generate", "llm_check"):
            if modality == "video":
                predicted = "handoff_video"
            elif modality in ("ambiguous", "unspecified"):
                predicted = "confirm_modality"
        expected = item["expected"]
        ok = predicted == expected
        rows.append((item["text"], expected, predicted, result["score"], ok))

    total = len(rows)
    correct = sum(1 for r in rows if r[4])
    print(f"评测样本：{total}，命中：{correct}，准确率：{correct / total:.1%}" if total else "无样本")
    print(f"{'结果':<6}{'期望':<12}{'预测':<14}{'分数':<6}输入")
    for text, expected, predicted, score_value, ok in rows:
        flag = "✓" if ok else "✗"
        print(f"{flag:<6}{expected:<12}{predicted:<14}{score_value:<6}{text}")


if __name__ == "__main__":
    main()
