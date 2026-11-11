#!/usr/bin/env python3
"""离线上下文装配器（POC）。

模拟第三方接口：红人画像 + 赛道热点。
真实接入时只替换 load_* 两个函数，输出结构保持不变。

用法：
  python3 fetch_context.py                     # 输出完整 JSON
  python3 fetch_context.py --compact           # 输出装配摘要（≤200 字）
  python3 fetch_context.py --fail profile      # 模拟画像接口超时
  python3 fetch_context.py --fail trends       # 模拟热点接口超时
"""

import argparse
import json
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
MOCK_DIR = SKILL_DIR / "references" / "mock"
PROFILE_PATH = MOCK_DIR / "mock-profile.json"
TRENDS_PATH = MOCK_DIR / "mock-trends.json"


def load_profile(path=PROFILE_PATH):
    """真实接入时替换为：GET /v1/red/profile/offline?red_id=xxx"""
    data = json.loads(path.read_text(encoding="utf-8"))
    whitelist = data.get("whitelist_fields_used", [])
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
    return {
        "red_id": data.get("red_id"),
        "nickname": data.get("nickname"),
        "track": data.get("track"),
        "fields": filtered,
        "source": data.get("source", "mock"),
        "fetched_at": data.get("fetched_at"),
    }


def load_trends(path=TRENDS_PATH):
    """真实接入时替换为：GET /v1/track/trends/offline?track=美食"""
    data = json.loads(path.read_text(encoding="utf-8"))
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


def build(profile_fail=False, trends_fail=False):
    result = {"profile": None, "trends": None, "degradation": [], "source": "mock"}
    try:
        if profile_fail:
            raise TimeoutError("profile endpoint timeout")
        result["profile"] = load_profile()
    except Exception as exc:  # noqa: BLE001 - POC 需要把任何失败降级为可用状态
        result["degradation"].append(
            {
                "target": "profile",
                "reason": str(exc),
                "fallback": "使用 brief 自带人群描述，标注本次未使用画像",
            }
        )

    try:
        if trends_fail:
            raise TimeoutError("trends endpoint timeout")
        result["trends"] = load_trends()
    except Exception as exc:  # noqa: BLE001
        result["degradation"].append(
            {
                "target": "trends",
                "reason": str(exc),
                "fallback": "标注无热点参考，按通用结构生成",
            }
        )
    return result


def compact(context):
    parts = []
    profile = context.get("profile")
    if profile:
        fields = profile.get("fields", {})
        track = profile.get("track", {}) or {}
        parts.append(
            f"赛道：{track.get('primary', '未知')}"
            f"（{'/'.join(track.get('secondary', []))}）"
        )
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


def main():
    parser = argparse.ArgumentParser(description="离线画像与热点装配（POC）")
    parser.add_argument("--compact", action="store_true", help="只输出装配摘要")
    parser.add_argument("--fail", choices=["profile", "trends"], help="模拟指定接口失败")
    args = parser.parse_args()

    context = build(
        profile_fail=args.fail == "profile",
        trends_fail=args.fail == "trends",
    )

    if args.compact:
        print(compact(context))
        if context["degradation"]:
            print("降级：" + "；".join(d["target"] + " 不可用" for d in context["degradation"]))
    else:
        print(json.dumps(context, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
