#!/usr/bin/env python3
"""M3 爆款骨架层（POC）：按达人画像 + 已选选题，取 3 条可执行骨架。

对齐《M3-爆款骨架字段设计（图文 / 视频）》5.2 匹配流程：
  1. 召回：平台、类目、形态、近 90 天；
  2. 硬筛：历史有该 content_form、篇幅不超过中位数两倍、语速差不超过一档；
  3. 打分：类目 40 / 形态 25 / 节奏 20 / 钩子 15；
  4. 取前三条：同分时发布时间新的优先；三版互斥优先不同形态与不同钩子；
  5. 改造清单：出镜、口播、语速、手部演示、场景数、剪辑难度、篇幅；
  6. 注入结构块：只给段序、每段职责与三项硬约束，不抄样本段数 / 秒数 / 字数。

用法：
  python3 scripts/skeleton_pick.py --branch xhs
  python3 scripts/skeleton_pick.py --branch video --topic "咖啡液平价替代：用平价替代算一笔账" --angle cheap_alternative
  python3 scripts/skeleton_pick.py --branch xhs --all
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
MOCK = SKILL_DIR / "references" / "mock"

BRANCH = {
    "xhs": {
        "platform": "xhs",
        "profile": MOCK / "profile" / "mock-profile-xhs.json",
        "skeleton": MOCK / "skeleton" / "mock-skeleton-xhs.json",
        "hot": MOCK / "hot" / "mock-hot-trends.json",
        "content_key": "article",
    },
    "video": {
        "platform": "dy",
        "profile": MOCK / "profile" / "mock-profile-douyin.json",
        "skeleton": MOCK / "skeleton" / "mock-skeleton-video.json",
        "hot": MOCK / "hot" / "mock-hot-trends.json",
        "content_key": "video",
    },
}

FORM_CN = {"list": "清单", "tutorial": "教程", "review": "测评", "vlog": "记录", "story": "剧情", "info": "科普"}
HOOK_CN = {
    "conclusion_first": "结论前置",
    "question": "提问",
    "conflict": "冲突",
    "number": "数字",
    "scene_entry": "场景代入",
}
ENDING_CN = {
    "product_shot": "成品展示",
    "result_compare": "效果对比",
    "cta": "行动号召",
    "list_end": "清单收口",
    "loop": "首尾呼应",
    "none": "无收尾",
}
PACE_CN = {"front_loaded": "前重", "even": "均匀", "build_up": "后段递进"}
BAND_ORDER = {"slow": 0, "medium": 1, "fast": 2}
FAMILY = {"美食", "食品", "餐饮", "食品饮料", "乳制品", "咖啡", "茶饮", "烘焙", "零食", "生鲜"}

TIME_FMT = "%Y-%m-%d %H:%M:%S"


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_time(value):
    return datetime.strptime(value, TIME_FMT)


def category_score(category, profile):
    """同主类目 1，同父类目 0.6，跨类目 0。"""
    if not category:
        return 0.0
    family = category.split("-")[0]
    creator_family = profile["categories"][0]["l1"]
    if family == creator_family or (family in FAMILY and creator_family in FAMILY):
        return 1.0
    return 0.0


def speech_band(rate_per_sec):
    per_min = rate_per_sec * 60
    if per_min < 150:
        return "slow"
    if per_min <= 220:
        return "medium"
    return "fast"


def creator_context(profile, branch):
    content_key = BRANCH[branch]["content_key"]
    node = profile.get(content_key, {})
    ext = profile.get("mock_ext", {})
    forms = {k: v for k, v in ext.get("content_form_dist", {}).items() if v > 0}
    if branch == "xhs":
        on_camera = profile.get("expression", {}).get("on_camera", {}).get("on_camera", None)
        median = ext.get("text_len_median") or 380
        return {
            "forms": forms,
            "pace_mode": ext.get("pace_shape_mode"),
            "pace_seen": ext.get("pace_shape_seen", []),
            "hook_mode": ext.get("hook_type_mode"),
            "hook_seen": ext.get("hook_types_seen", []),
            "on_camera": on_camera,
            "text_len_median": median,
            "speech_band": None,
            "duration_median": None,
            "skill_level": "mid",
        }
    vp = node.get("video_duration", {}) or {}
    personal = vp.get("personal", {})
    rate = (node.get("speech_features", {}) or {}).get("speech_rate", 4.0)
    return {
        "forms": forms,
        "pace_mode": ext.get("pace_shape_mode"),
        "pace_seen": ext.get("pace_shape_seen", []),
        "hook_mode": ext.get("hook_type_mode"),
        "hook_seen": ext.get("hook_types_seen", []),
        "on_camera": (node.get("on_camera", {}) or {}).get("on_camera", None),
        "text_len_median": None,
        "speech_band": speech_band(rate),
        "speech_rate": rate,
        "duration_median": personal.get("median"),
        "skill_level": "mid",
    }


def skeleton_duration(record):
    beats = record.get("beat_roles", [])
    return beats[-1]["end_sec"] if beats else 0


def recall_and_filter(record, profile, ctx, branch, now):
    reasons = []
    if record.get("platform") != BRANCH[branch]["platform"]:
        reasons.append("平台不一致")
    cat = category_score(record.get("category"), profile)
    if cat == 0:
        reasons.append("类目不相邻")
    try:
        if parse_time(record["publish_time"]) < now - timedelta(days=90):
            reasons.append("发布时间超过 90 天")
    except Exception:  # noqa: BLE001
        reasons.append("发布时间缺失")
    if record.get("content_form") not in ctx["forms"]:
        reasons.append(f"达人历史没有 {record.get('content_form')} 形态")
    if branch == "xhs":
        if record.get("text_len_total", 0) > 2 * ctx["text_len_median"]:
            reasons.append("篇幅超过达人篇幅中位数两倍")
    else:
        if ctx["duration_median"] and skeleton_duration(record) > 2 * ctx["duration_median"]:
            reasons.append("时长超过达人中位数两倍")
        band = record.get("creator_req", {}).get("speech_rate_band")
        if band and ctx["speech_band"] and abs(BAND_ORDER[band] - BAND_ORDER[ctx["speech_band"]]) > 1:
            reasons.append(f"语速差超过一档（样本 {band} / 达人 {ctx['speech_band']}）")
    if reasons:
        return None, reasons
    return {"cat": cat}, []


def score_record(record, cat, ctx, branch):
    form = record.get("content_form")
    form_score = 1.0 if form in ctx["forms"] else 0.0
    pace = record.get("pace_shape")
    pace_score = 1.0 if pace == ctx["pace_mode"] else 0.5 if pace in ctx["pace_seen"] else 0.0
    hook = record.get("hook_type")
    hook_score = 1.0 if hook == ctx["hook_mode"] else 0.5 if hook in ctx["hook_seen"] else 0.0

    total = 40 * cat["cat"] + 25 * form_score + 20 * pace_score + 15 * hook_score
    return round(total, 1), {
        "cat": round(40 * cat["cat"], 1),
        "form": round(25 * form_score, 1),
        "pace": round(20 * pace_score, 1),
        "hook": round(15 * hook_score, 1),
    }


def migration_list(record, ctx, branch):
    items = []
    diff_count = 0
    req = record.get("creator_req", {}) or {}

    def add(text):
        nonlocal diff_count
        diff_count += 1
        items.append(text)

    if branch == "xhs":
        if req.get("on_camera") and ctx["on_camera"] is False:
            add("需真人出镜，达人不常出镜：改为手部 + 桌面视角")
        if req.get("text_heavy"):
            add("文字为主：需 3–6 张信息图承载分点")
        if req.get("scene_cnt", 1) > 2:
            add(f"样本要 {req['scene_cnt']} 个场景：合并为 2 个，或全程固定桌面")
        if req.get("skill_level") == "high" and ctx["skill_level"] != "high":
            add("制作难度 high：拆成两次拍，先拍主体再补空镜")
        total = record.get("text_len_total", 0)
        if total > 1.5 * ctx["text_len_median"]:
            add(f"样本 {total} 字，超过本人中位数 1.5 倍：压到 {int(ctx['text_len_median'])} 字上下")
    else:
        if req.get("on_camera") and ctx["on_camera"] is False:
            add("需真人出镜，达人不常出镜：改为手部演示 + 画外音")
        if req.get("speech_rate_band") and req["speech_rate_band"] != ctx["speech_band"]:
            direction = "提" if BAND_ORDER[req["speech_rate_band"]] > BAND_ORDER[ctx["speech_band"]] else "降"
            add(f"语速需{direction}一档：台词按 {ctx['speech_rate']} 字/秒现算，不抄样本秒数")
        if req.get("demo_hands"):
            add("需要手部演示：备桌面俯拍机位（撕开 / 倒水 / 搅拌）")
        if req.get("scene_cnt", 1) > 2:
            add(f"样本要 {req['scene_cnt']} 个场景：合并为 2 个")
        if req.get("cut_skill") == "high" and ctx["skill_level"] != "high":
            add("剪辑难度 high：降低切镜率，前 3 秒保留 1 次切镜")
        duration = skeleton_duration(record)
        if ctx["duration_median"] and duration > 1.5 * ctx["duration_median"]:
            add(f"样本 {duration:.1f}s，超过本人中位数 1.5 倍：按本次 30s 重排段长")

    if not items:
        items.append("无需改造，按本人语气直接套用")
    return items, diff_count


def structure_block(record, branch, ctx):
    roles = [r["role"] for r in (record.get("page_roles") or record.get("beat_roles") or [])]
    if branch == "xhs":
        seq = " → ".join(f"{i + 1} {role}" for i, role in enumerate(roles))
        return {
            "layout": f"{len(roles)} 页：{seq}",
            "hard": [
                f"钩子类型命中 {record['hook_type']}（{HOOK_CN.get(record['hook_type'], record['hook_type'])}）",
                "product_in 不晚于第 3 页（前 40%）",
                f"收尾类型命中 {record['ending_type']}（{ENDING_CN.get(record['ending_type'], record['ending_type'])}）",
            ],
            "soft": [
                "中段 role 顺序可合并，段落可增删 1 页",
                f"页数按达人图文习惯（3–6 页）；篇幅按本人中位数现算，不抄样本 {record.get('text_len_total')} 字",
            ],
        }
    seq = " → ".join(role for role in roles)
    return {
        "layout": f"{len(roles)} 段：{seq}",
        "hard": [
            f"钩子类型命中 {record['hook_type']}（{HOOK_CN.get(record['hook_type'], record['hook_type'])}）",
            "product_in 不晚于 40% 时长（30s 档即 12s）",
            f"收尾类型命中 {record['ending_type']}（{ENDING_CN.get(record['ending_type'], record['ending_type'])}）",
        ],
        "soft": [
            "可合并相邻同角色段，段数 4–8 段",
            f"秒数与口播字数按本次 30s、画像 {ctx.get('speech_rate', 4.2)} 字/秒现算，不抄样本时间码",
        ],
    }


def version_rows(chosen):
    return [f"V{i + 1} ← {c['content_id']}（{c['content_form_cn']}·{c['hook_cn']}·{c['ending_cn']}）" for i, c in enumerate(chosen)]


def pick(branch, limit=3, show_all=False):
    cfg = BRANCH[branch]
    profile = load_json(cfg["profile"])
    skeleton_file = load_json(cfg["skeleton"])
    now = parse_time(load_json(cfg["hot"])["mock_batch_now"])
    ctx = creator_context(profile, branch)

    considered, excluded, scored = [], [], []
    for record in skeleton_file["records"]:
        ok, reasons = recall_and_filter(record, profile, ctx, branch, now)
        if not ok:
            excluded.append({"content_id": record["content_id"], "content_form": record.get("content_form"), "reasons": reasons})
            continue
        score, detail = score_record(record, ok, ctx, branch)
        migrations, diff_count = migration_list(record, ctx, branch)
        if diff_count > 2:
            excluded.append({
                "content_id": record["content_id"],
                "content_form": record.get("content_form"),
                "reasons": [f"改造项 {diff_count} 项 > 2，降级为参照，不进注入"],
                "migration": migrations,
            })
            continue
        row = {
            "content_id": record["content_id"],
            "content_form": record.get("content_form"),
            "content_form_cn": FORM_CN.get(record.get("content_form"), record.get("content_form")),
            "hook_type": record.get("hook_type"),
            "hook_cn": HOOK_CN.get(record.get("hook_type"), record.get("hook_type")),
            "ending_type": record.get("ending_type"),
            "ending_cn": ENDING_CN.get(record.get("ending_type"), record.get("ending_type")),
            "hook_sync": record.get("hook_sync"),
            "pace_shape": record.get("pace_shape"),
            "pace_cn": PACE_CN.get(record.get("pace_shape"), record.get("pace_shape")),
            "text_len_total": record.get("text_len_total"),
            "duration_sec": skeleton_duration(record) if branch == "video" else None,
            "cut_rate_3s": record.get("cut_rate_3s"),
            "score": score,
            "score_detail": detail,
            "publish_time": record.get("publish_time"),
            "source_board": record.get("source_board"),
            "source_rank": record.get("source_rank"),
            "creator_req": record.get("creator_req"),
            "migration": migrations,
            "migration_count": diff_count,
            "degrade_reference": diff_count > 2,
            "structure": structure_block(record, branch, ctx),
        }
        scored.append(row)
        considered.append(record["content_id"])

    # 同分时发布时间新的优先
    scored.sort(key=lambda r: (r["score"], r["publish_time"]), reverse=True)

    chosen = []
    if not show_all:
        forms_used, hooks_used = set(), set()
        for r in scored:
            if len(chosen) >= limit:
                break
            if r["content_form"] in forms_used or r["hook_type"] in hooks_used:
                continue
            chosen.append(r)
            forms_used.add(r["content_form"])
            hooks_used.add(r["hook_type"])
        if len(chosen) < limit:
            for r in scored:
                if r in chosen or r["hook_type"] in hooks_used:
                    continue
                chosen.append(r)
                hooks_used.add(r["hook_type"])
                if len(chosen) >= limit:
                    break
        if len(chosen) < limit:
            for r in scored:
                if r not in chosen:
                    chosen.append(r)
                if len(chosen) >= limit:
                    break
    else:
        chosen = scored

    return {
        "branch": branch,
        "platform": cfg["platform"],
        "now": now.strftime(TIME_FMT),
        "profile": {
            "resource_id": profile["resource_id"],
            "account_nickname": profile["account_nickname"],
            "content_form_dist": ctx["forms"],
            "pace_mode": ctx["pace_mode"],
            "hook_mode": ctx["hook_mode"],
            "on_camera": ctx["on_camera"],
            "speech_band": ctx["speech_band"],
            "text_len_median": ctx["text_len_median"],
            "duration_median": ctx["duration_median"],
        },
        "considered": len(considered),
        "chosen": chosen if show_all else chosen[:limit],
        "version_map": version_rows(chosen[:limit]) if not show_all else [],
        "excluded": excluded,
        "injection_note": "只注入段序、职责与三项硬约束；段数、秒数、每段字数一律按本次时长与达人语速现算",
    }


def main():
    parser = argparse.ArgumentParser(description="M3 骨架匹配（POC）")
    parser.add_argument("--branch", choices=["xhs", "video"], required=True)
    parser.add_argument("--topic", default=None, help="已选选题（仅回显，便于成品卡留痕）")
    parser.add_argument("--angle", default=None, help="已选角度（仅回显）")
    parser.add_argument("--all", action="store_true", help="输出全部评分候选，不只前三条")
    args = parser.parse_args()

    result = pick(args.branch, show_all=args.all)
    result["topic"] = args.topic
    result["angle"] = args.angle
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
