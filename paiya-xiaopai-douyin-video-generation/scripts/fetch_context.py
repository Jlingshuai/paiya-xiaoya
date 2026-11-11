#!/usr/bin/env python3
"""装配抖音侧红人画像与赛道热点（POC，MOCK 数据源）。

真实接入时只替换 load_profile / load_trends 两个函数的实现，
返回字段保持与 references/mock/ 下 JSON 一致，其余流程不用改。
"""

import argparse
import json
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
MOCK_DIR = SKILL_DIR / "references" / "mock"


def load_profile(red_id: str):
    """第三方离线画像接口（POC 读本地 MOCK）。"""
    return json.loads((MOCK_DIR / "mock-video-profile.json").read_text(encoding="utf-8"))


def load_trends(track: str):
    """赛道热点接口（POC 读本地 MOCK）。"""
    return json.loads((MOCK_DIR / "mock-video-trends.json").read_text(encoding="utf-8"))


def compact(profile, trends):
    vp = profile.get("video_profile", {})
    return {
        "track": profile.get("track", {}).get("primary"),
        "persona": profile.get("persona", {}).get("one_liner"),
        "tone": profile.get("persona", {}).get("tone"),
        "avg_completion_rate": vp.get("avg_completion_rate"),
        "best_format": vp.get("best_performing_format"),
        "speaking_rate": vp.get("speaking_rate"),
        "shot_rhythm": vp.get("shot_rhythm"),
        "hook_preference": vp.get("hook_preference"),
        "core_needs": profile.get("audience", {}).get("core_needs"),
        "hot_videos": [
            {"id": v["id"], "title": v["title"], "why_hot": v["why_hot"],
             "reusable": v.get("reusable", [])}
            for v in trends.get("videos", [])
        ],
        "saturation_warnings": trends.get("saturation_warnings", []),
    }


def main():
    parser = argparse.ArgumentParser(description="装配抖音画像与热点")
    parser.add_argument("--red-id", default="R-2048-DY")
    parser.add_argument("--track", default="美食")
    parser.add_argument("--compact", action="store_true", help="只输出生成需要的字段")
    parser.add_argument("--fail", choices=["profile", "trends"], help="模拟接口不可用")
    args = parser.parse_args()

    degraded = []
    profile, trends = {}, {}
    try:
        if args.fail == "profile":
            raise RuntimeError("profile endpoint unavailable")
        profile = load_profile(args.red_id)
    except Exception as exc:  # noqa: BLE001
        degraded.append(f"画像接口不可用：{exc}")
    try:
        if args.fail == "trends":
            raise RuntimeError("trends endpoint unavailable")
        trends = load_trends(args.track)
    except Exception as exc:  # noqa: BLE001
        degraded.append(f"热点接口不可用：{exc}")

    if degraded:
        print(json.dumps({"status": "degraded", "degraded": degraded,
                          "profile": profile or None, "trends": trends or None},
                         ensure_ascii=False, indent=2))
        return

    payload = compact(profile, trends) if args.compact else {"profile": profile, "trends": trends}
    payload["_source"] = "mock"
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
