#!/usr/bin/env python3
"""统一装配红人画像（27 字段字典）与赛道热点（M2 hot_trend 表）。

POC 阶段读 references/mock 下的脱敏数据；真实接入时只替换 load_profile / load_trends，
返回结构保持不变。

  python3 fetch_context.py --branch xhs --compact
  python3 fetch_context.py --branch video --compact
  python3 fetch_context.py --branch video --fail profile
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
MOCK = SKILL_DIR / "references" / "mock"

PATHS = {
    "xhs": {
        "platform": "xhs",
        "profile": MOCK / "profile" / "mock-profile-xhs.json",
        "hot": MOCK / "hot" / "mock-hot-trends.json",
        "content_key": "article",
    },
    "video": {
        "platform": "dy",
        "profile": MOCK / "profile" / "mock-profile-douyin.json",
        "hot": MOCK / "hot" / "mock-hot-trends.json",
        "content_key": "video",
    },
}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def pct(value):
    number = float(value)
    return number / 100 if number > 1 else number


def load_profile(branch, red_id=None):
    """真实接入时替换为：GET /v1/red/profile/offline?red_id=xxx"""
    data = load_json(PATHS[branch]["profile"])
    return {
        "resource_id": data.get("resource_id"),
        "platform": data.get("platform"),
        "account_nickname": data.get("account_nickname"),
        "self_pitch": data.get("self_pitch"),
        "categories": data.get("categories"),
        "fans_num": data.get("fans_num"),
        "content_key": PATHS[branch]["content_key"],
        "content": data.get(PATHS[branch]["content_key"], {}),
        "common": data.get("common", {}),
        "expression": data.get("expression", {}),
        "commercial_rules": data.get("commercial_rules", {}),
        "mock_ext": data.get("mock_ext", {}),
        "source": data.get("source", "mock"),
        "fetched_at": data.get("fetched_at"),
    }


def load_trends(branch, track=None):
    """真实接入时替换为：GET /v1/track/trends/offline?track=美食"""
    data = load_json(PATHS[branch]["hot"])
    platform = PATHS[branch]["platform"]
    records = [row for row in data.get("records", []) if row.get("plate_type") == platform]
    now = data.get("mock_batch_now")
    valid = []
    for row in records:
        try:
            begin = datetime.strptime(row["begin_time"], "%Y-%m-%d %H:%M:%S")
            end = datetime.strptime(row["end_time"], "%Y-%m-%d %H:%M:%S")
            current = datetime.strptime(now, "%Y-%m-%d %H:%M:%S")
            if begin <= current <= end and row.get("trend") != "declining":
                valid.append(row)
        except (KeyError, ValueError):
            continue
    return {
        "batch_id": data.get("batch_id"),
        "mock_batch_now": now,
        "track": data.get("track"),
        "records": valid,
        "saturation_warnings": data.get("saturation_warnings", []),
        "usage_rules": data.get("usage_rules"),
        "source": data.get("source", "mock"),
    }


def build(branch, profile_fail=False, trends_fail=False, red_id=None, track=None):
    result = {"branch": branch, "profile": None, "trends": None, "degradation": [], "source": "mock"}
    try:
        if profile_fail:
            raise TimeoutError(f"{branch} profile endpoint timeout")
        result["profile"] = load_profile(branch, red_id)
    except Exception as exc:  # noqa: BLE001
        result["degradation"].append(
            {"target": "profile", "reason": str(exc), "fallback": "使用 brief 自带人群描述，标注本次未使用画像"}
        )

    try:
        if trends_fail:
            raise TimeoutError(f"{branch} trends endpoint timeout")
        result["trends"] = load_trends(branch, track)
    except Exception as exc:  # noqa: BLE001
        result["degradation"].append(
            {"target": "trends", "reason": str(exc), "fallback": "标注无热点参考，按通用结构生成"}
        )
    return result


def audience_summary(common, branch):
    ap = common.get("audience_profile", {})
    parts = []
    female = ap.get("gender", {}).get("female")
    if female is not None:
        parts.append(f"女 {int(round(pct(female) * 100))}%")
    ages = ap.get("age", [])
    if ages:
        top = max(ages, key=lambda row: pct(row["pct"]))
        parts.append(f"{top['tier']} 岁 {int(round(pct(top['pct']) * 100))}%")
    return "、".join(parts)


def top_questions(content):
    questions = content.get("audience_questions", [])
    return [q["question"] for q in questions[:2]]


def top_flops(content):
    return [row["topic"] for row in content.get("flop_topics", [])[:2]]


def compact_xhs(context):
    parts = []
    profile = context.get("profile")
    if profile:
        content = profile.get("content", {})
        categories = profile.get("categories", [])
        secondary = [c["l2"] for c in categories if c.get("l2")]
        parts.append(f"赛道：美食（{'/'.join(secondary[:2])}）")
        if profile.get("self_pitch"):
            parts.append("人设：" + profile["self_pitch"])
        tone = (profile.get("expression", {}) or {}).get("tone")
        if tone:
            parts.append("口吻：" + tone)
        pillars = content.get("topic_pillars", [])
        if pillars:
            parts.append(
                "内容支柱：" + "、".join(f"{p['pillar']}{int(round(p['weight'] * 100))}%" for p in pillars[:3])
            )
        topics = content.get("content_topics", [])
        if topics:
            parts.append("常拍：" + "、".join(t["topic"] for t in topics[:3]))
        formulas = (content.get("note_style", {}) or {}).get("title_formulas", {})
        if formulas:
            top = max(formulas.items(), key=lambda kv: kv[1])
            parts.append(f"标题公式：{top[0]}为主")
        evolution = content.get("style_evolution", {}) or {}
        if evolution.get("current_dominant"):
            parts.append("当前风格：" + evolution["current_dominant"])
        median = profile.get("mock_ext", {}).get("text_len_median")
        if median:
            parts.append(f"篇幅中位数：{median} 字")
        parts.append("人群：" + audience_summary(profile.get("common", {}), "xhs"))
        questions = top_questions(content)
        if questions:
            parts.append("需求缺口：" + "、".join(questions))
        flops = top_flops(content)
        if flops:
            parts.append("失败选题：" + "、".join(flops))
    else:
        parts.append("画像：本次未使用（接口不可用）")

    trends = context.get("trends")
    if trends:
        seen, topics = set(), []
        for row in trends.get("records", []):
            if row["hot_topic"] in seen:
                continue
            seen.add(row["hot_topic"])
            topics.append(row["hot_topic"])
            if len(topics) >= 5:
                break
        if topics:
            parts.append("热点：" + "、".join(topics))
    else:
        parts.append("热点：本次未使用（接口不可用）")
    return "；".join(parts)


def compact_video(context):
    parts = []
    profile = context.get("profile")
    if profile:
        content = profile.get("content", {})
        categories = profile.get("categories", [])
        secondary = [c["l2"] for c in categories if c.get("l2")]
        parts.append(f"赛道：美食（{'/'.join(secondary[:2])}）")
        if content.get("persona_line"):
            parts.append("人设：" + content["persona_line"])
        tone_words = content.get("tone_words")
        if tone_words:
            parts.append("口吻：" + "/".join(tone_words))
        speech = content.get("speech_features", {}) or {}
        if speech.get("speech_rate"):
            per_min = int(round(speech["speech_rate"] * 60))
            parts.append(f"语速：{speech['speech_rate']} 字/秒（{per_min} 字/分）")
        hooks = (content.get("hook_patterns", {}) or {}).get("dist", {})
        if hooks:
            top_hook = max(hooks.items(), key=lambda kv: kv[1])
            parts.append(f"钩子：{top_hook[0]}占{int(round(top_hook[1] * 100))}%")
        pace = profile.get("mock_ext", {}).get("pace_shape_mode")
        if pace:
            parts.append("节奏形状：" + {"front_loaded": "前重", "even": "均匀", "build_up": "后段递进"}.get(pace, pace))
        duration = (content.get("video_duration", {}) or {}).get("personal", {})
        if duration.get("median"):
            parts.append(f"时长中位数：{duration['median']}s")
        forms = profile.get("mock_ext", {}).get("content_form_dist", {})
        if forms:
            cn = {"list": "清单", "tutorial": "教程", "review": "测评", "vlog": "记录", "story": "剧情", "info": "科普"}
            top_forms = sorted(forms.items(), key=lambda kv: -kv[1])[:2]
            parts.append("形态：" + "、".join(f"{cn.get(k, k)}{int(round(v * 100))}%" for k, v in top_forms))
        parts.append("人群：" + audience_summary(profile.get("common", {}), "video"))
        questions = top_questions(content)
        if questions:
            parts.append("需求缺口：" + "、".join(questions))
        flops = top_flops(content)
        if flops:
            parts.append("失败选题：" + "、".join(flops))
    else:
        parts.append("画像：本次未使用（接口不可用）")

    trends = context.get("trends")
    if trends:
        seen, topics = set(), []
        for row in trends.get("records", []):
            if row["hot_topic"] in seen:
                continue
            seen.add(row["hot_topic"])
            topics.append(row["hot_topic"])
            if len(topics) >= 5:
                break
        if topics:
            parts.append("热点：" + "、".join(topics))
    else:
        parts.append("热点：本次未使用（接口不可用）")
    return "；".join(parts)


def compact(context):
    return compact_xhs(context) if context["branch"] == "xhs" else compact_video(context)


def main():
    parser = argparse.ArgumentParser(description="统一画像与热点装配（POC）")
    parser.add_argument("--branch", choices=["xhs", "video"], default="xhs", help="分支：xhs / video")
    parser.add_argument("--red-id", default=None, help="红人 ID（POC 默认读 mock 画像）")
    parser.add_argument("--track", default="美食", help="赛道（POC 默认美食）")
    parser.add_argument("--compact", action="store_true", help="只输出装配摘要")
    parser.add_argument("--fail", choices=["profile", "trends"], help="模拟指定接口失败")
    args = parser.parse_args()

    context = build(
        args.branch,
        profile_fail=args.fail == "profile",
        trends_fail=args.fail == "trends",
        red_id=args.red_id,
        track=args.track,
    )

    if args.compact:
        print(compact(context))
        if context["degradation"]:
            print("降级：" + "；".join(d["target"] + " 不可用" for d in context["degradation"]))
    else:
        print(json.dumps(context, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
