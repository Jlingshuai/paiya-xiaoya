#!/usr/bin/env python3
"""统一装配红人画像与赛道热点（POC，MOCK 数据源）。

真实接入时只替换 load_profile / load_trends，返回结构保持不变。
  python3 fetch_context.py --branch xhs --compact
  python3 fetch_context.py --branch video --compact
  python3 fetch_context.py --branch video --fail profile
"""

import argparse
import json
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
MOCK_DIR = SKILL_DIR / "references" / "mock"

PATHS = {
    "xhs": {
        "profile": MOCK_DIR / "xhs" / "mock-profile.json",
        "trends": MOCK_DIR / "xhs" / "mock-trends.json",
    },
    "video": {
        "profile": MOCK_DIR / "video" / "mock-video-profile.json",
        "trends": MOCK_DIR / "video" / "mock-video-trends.json",
    },
}


def pick_fields(data, whitelist):
    filtered = {}
    for field in whitelist:
        node = data
        for part in field.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                node = None
                break
        if node is not None:
            filtered[field] = node
    return filtered


def load_profile(branch, red_id=None):
    """真实接入时替换为：GET /v1/red/profile/offline?red_id=xxx"""
    data = json.loads(PATHS[branch]["profile"].read_text(encoding="utf-8"))
    if branch == "xhs":
        return {
            "red_id": data.get("red_id"),
            "nickname": data.get("nickname"),
            "track": data.get("track"),
            "fields": pick_fields(data, data.get("whitelist_fields_used", [])),
            "source": data.get("source", "mock"),
            "fetched_at": data.get("fetched_at"),
        }
    return data


def load_trends(branch, track=None):
    """真实接入时替换为：GET /v1/track/trends/offline?track=美食"""
    data = json.loads(PATHS[branch]["trends"].read_text(encoding="utf-8"))
    if branch == "xhs":
        return {
            "track": data.get("track"),
            "window": data.get("window"),
            "keywords": data.get("keywords"),
            "notes": data.get("notes", [])[:4],
            "videos": data.get("videos", [])[:2],
            "saturation_warnings": data.get("saturation_warnings", []),
            "usage_rules": data.get("usage_rules"),
            "source": data.get("source", "mock"),
        }
    return data


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


def compact_xhs(context):
    parts = []
    profile = context.get("profile")
    if profile:
        fields = profile.get("fields", {})
        track = profile.get("track", {}) or {}
        parts.append(f"赛道：{track.get('primary', '未知')}（{'/'.join(track.get('secondary', []))}）")
        if "persona.tone" in fields:
            parts.append(f"语气：{fields['persona.tone']}")
        audience = fields.get("audience.core_needs")
        if audience:
            parts.append("人群需求：" + "、".join(audience))
        structures = fields.get("content.best_performing_structures")
        if structures:
            parts.append("可用结构：" + structures[0])
    else:
        parts.append("画像：本次未使用（接口不可用）")

    trends = context.get("trends")
    if trends:
        keywords = trends.get("keywords", {}).get("rising", [])
        if keywords:
            parts.append("热点词：" + "、".join(keywords[:5]))
        notes = trends.get("notes", [])
        if notes:
            parts.append("参考选题：" + "、".join(n["title"] for n in notes[:3]))
    else:
        parts.append("热点：本次未使用（接口不可用）")
    return "；".join(parts)


def compact_video(context):
    parts = []
    profile = context.get("profile")
    if profile:
        track = profile.get("track", {}) or {}
        vp = profile.get("video_profile", {}) or {}
        persona = profile.get("persona", {}) or {}
        audience = profile.get("audience", {}) or {}
        parts.append(f"赛道：{track.get('primary', '未知')}（{'/'.join(track.get('secondary', []))}）")
        if persona.get("one_liner"):
            parts.append("人设：" + persona["one_liner"])
        if persona.get("tone"):
            parts.append("语气：" + persona["tone"])
        if vp.get("avg_completion_rate") is not None:
            parts.append(f"平均完播：{int(vp['avg_completion_rate'] * 100)}%")
        if vp.get("best_performing_format"):
            parts.append("擅长：" + vp["best_performing_format"])
        if vp.get("speaking_rate"):
            parts.append("语速：" + vp["speaking_rate"])
        if vp.get("shot_rhythm"):
            parts.append("镜头节奏：" + vp["shot_rhythm"])
        if vp.get("hook_preference"):
            parts.append("钩子：" + vp["hook_preference"])
        if audience.get("core_needs"):
            parts.append("人群需求：" + "、".join(audience["core_needs"]))
    else:
        parts.append("画像：本次未使用（接口不可用）")

    trends = context.get("trends")
    if trends:
        videos = trends.get("videos", [])
        if videos:
            parts.append("热点视频：" + "、".join(v["title"] for v in videos[:3]))
        warnings = trends.get("saturation_warnings", [])
        if warnings:
            parts.append("撞车警告：" + warnings[0])
    else:
        parts.append("热点：本次未使用（接口不可用）")
    return "；".join(parts)


def compact(context):
    return compact_xhs(context) if context["branch"] == "xhs" else compact_video(context)


def main():
    parser = argparse.ArgumentParser(description="统一画像与热点装配（POC）")
    parser.add_argument("--branch", choices=["xhs", "video"], default="xhs", help="分支：xhs / video")
    parser.add_argument("--red-id", default=None, help="红人 ID（视频分支默认 R-2048-DY）")
    parser.add_argument("--track", default="美食", help="赛道（视频分支默认 美食）")
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
