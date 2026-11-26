#!/usr/bin/env python3
"""M2 选题层（POC）：热点 5 选 1，再出 3 个角度选题供用户选择。

流程（对齐《M2-选题与热点实现方案》）：
  1. 读画像（M1）与热点表 hot_trend；
  2. 硬筛：平台一致、类目命中、批次窗口有效、trend 不为 declining；
  3. 打分：fit_score = 60 × cat + 40 × audience；
  4. 同一话题只留一行（热门榜 / 飙升榜同时命中取高分），按 fit 取前 5；
  5. 从 5 个热点里随机抽 1 个；
  6. 为该热点生成 3 个不同角度的候选选题，交用户选择。

用法：
  python3 scripts/topic_pick.py --branch xhs
  python3 scripts/topic_pick.py --branch video --seed 2026
  python3 scripts/topic_pick.py --branch xhs --list-hot
  python3 scripts/topic_pick.py --branch xhs --select cand_2026112608_002 --seed 2026
"""

import argparse
import json
import random
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
MOCK = SKILL_DIR / "references" / "mock"

BRANCH = {
    "xhs": {
        "platform": "xhs",
        "profile": MOCK / "profile" / "mock-profile-xhs.json",
        "hot": MOCK / "hot" / "mock-hot-trends.json",
        "content_key": "article",
        "form_label": "图文",
    },
    "video": {
        "platform": "dy",
        "profile": MOCK / "profile" / "mock-profile-douyin.json",
        "hot": MOCK / "hot" / "mock-hot-trends.json",
        "content_key": "video",
        "form_label": "视频",
    },
}

TIME_FMT = "%Y-%m-%d %H:%M:%S"

# M4 三方类目映射的最小 POC 版：真实接入时读取品类树映射表
CATEGORY_FAMILY = {"美食", "食品", "餐饮", "食品饮料", "乳制品", "咖啡", "茶饮", "烘焙", "零食", "生鲜"}

AGE_BIN_MAP = {
    "18-23岁": "18-23",
    "19-22岁": "18-23",
    "18-22": "18-23",
    "23-30岁": "24-30",
    "24-30岁": "24-30",
    "23-30": "24-30",
    "26-35岁": "24-30",
    "31-35岁": "31-35",
    "31-40岁": "31-35",
    "36-45岁": "36-45",
    "41-50岁": "36-45",
}

DY_LABEL_MAP = {
    "生活服务": "生活方式",
    "母婴育儿": "母婴",
    "时尚": "生活方式",
    "运动健身": "生活方式",
    "旅游": "生活方式",
    "职场": "职场",
    "美食": "美食",
    "家居": "家居",
}

ANGLE_LABELS = {
    "self_fail": "自曝踩坑",
    "counter_intuition": "反常识",
    "cheap_alternative": "平价替代",
    "scene_test": "场景实测",
    "comparison": "对比测评",
    "tutorial": "教程步骤",
}

ANGLE_FORMS = {
    "cheap_alternative": "list",
    "comparison": "review",
    "tutorial": "tutorial",
    "scene_test": "vlog",
    "counter_intuition": "info",
    "self_fail": "story",
}

ANGLE_RULES = [
    (["早餐", "早八", "通勤", "出门"], ["scene_test", "tutorial", "cheap_alternative"]),
    (["咖啡", "拿铁", "美式", "手冲", "咖啡液"], ["cheap_alternative", "comparison", "tutorial"]),
    (["热饮", "冬日", "暖", "续命"], ["scene_test", "self_fail", "counter_intuition"]),
    (["便利店", "新品", "测评"], ["comparison", "self_fail", "counter_intuition"]),
    (["露营", "户外"], ["scene_test", "tutorial", "comparison"]),
    (["一人食", "午餐", "便当"], ["tutorial", "scene_test", "self_fail"]),
    (["办公", "工位", "下午"], ["scene_test", "counter_intuition", "cheap_alternative"]),
]

TOPIC_TEMPLATES = {
    "self_fail": "{hot}：用自曝踩坑讲清代价",
    "counter_intuition": "{hot}：用反常识拆一个误区",
    "cheap_alternative": "{hot}：用平价替代算一笔账",
    "scene_test": "{hot}：用场景实测看真实体验",
    "comparison": "{hot}：用对比测评挑值得的那款",
    "tutorial": "{hot}：用教程步骤复刻一遍",
}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_time(value):
    return datetime.strptime(value, TIME_FMT)


def profile_track(profile, branch):
    content_key = BRANCH[branch]["content_key"]
    node = profile.get(content_key, {})
    pillars = node.get("topic_pillars", [])
    return {
        "primary": "美食",
        "secondary": [p["pillar"] for p in pillars[:2]],
        "categories": [c["l2"] for c in profile.get("categories", [])],
    }


def pct(value):
    """把 '31.62' / 0.3162 / 31.62 统一成 0–1 小数。"""
    number = float(value)
    return number / 100 if number > 1 else number


def category_score(hot, profile):
    if hot.get("hot_scope") == "all" and not hot.get("category"):
        # hot_scope=all 时跳过类目命中，给同父层分
        return 0.6, "全网热点，按同父类目承接"
    category = (hot.get("category") or "").strip()
    if category in CATEGORY_FAMILY:
        return 1.0, f"类目命中：{category} → 美食"
    return 0.0, "类目未命中"


def audience_detail(profile, hot, branch):
    hot_profile = hot.get("profile") or {}
    common = profile.get("common", {}).get("audience_profile", {})
    genders = {g["name"]: pct(g.get("numRate", 0)) for g in hot_profile.get("gender", [])}
    ages = hot_profile.get("age", [])
    labels = hot_profile.get("eight_labels", [])

    if branches_is_xhs(branch):
        if not genders and not ages:
            return 0.5, {"reason": "话题画像缺失，按 0.5 关联"}
        female_share = pct(common.get("gender", {}).get("female", 0))
        male_share = pct(common.get("gender", {}).get("male", 0))
        gender_overlap = min(female_share, genders.get("女", 0)) + min(male_share, genders.get("男", 0))

        creator_age = {row["tier"]: pct(row["pct"]) for row in common.get("age", [])}
        hot_age = {}
        for row in ages:
            tier = AGE_BIN_MAP.get(row["name"])
            if tier:
                hot_age[tier] = hot_age.get(tier, 0) + pct(row["numRate"])
        age_overlap = sum(min(hot_age.get(t, 0), creator_age.get(t, 0)) for t in creator_age)

        score = round(0.5 * gender_overlap + 0.5 * age_overlap, 3)
        top_tier = max(creator_age.items(), key=lambda kv: hot_age.get(kv[0], 0))[0] if creator_age else ""
        top_share = hot_age.get(top_tier, 0)
        return score, {
            "gender_overlap": round(gender_overlap, 3),
            "age_overlap": round(age_overlap, 3),
            "top_tier": top_tier,
            "top_tier_share": top_share,
        }

    if not labels:
        return 0.5, {"reason": "话题画像缺失，按 0.5 关联"}
    creator_interests = {row["name"]: pct(row["pct"]) for row in common.get("interests", [])}
    hot_labels = {}
    for row in labels:
        name = DY_LABEL_MAP.get(row["name"], row["name"])
        hot_labels[name] = hot_labels.get(name, 0) + pct(row["numRate"])
    overlap = sum(min(hot_labels.get(n, 0), creator_interests[n]) for n in creator_interests)
    top_label = max(creator_interests.items(), key=lambda kv: hot_labels.get(kv[0], 0))[0] if creator_interests else ""
    return round(overlap, 3), {
        "label_overlap": round(overlap, 3),
        "top_label": top_label,
        "top_label_share": hot_labels.get(top_label, 0),
    }


def branches_is_xhs(branch):
    return branch == "xhs"


def hard_filter(hot, profile, branch, now):
    reasons = []
    begin, end = parse_time(hot["begin_time"]), parse_time(hot["end_time"])
    if not (begin <= now <= end):
        reasons.append(f"窗口失效（{hot['begin_time']} ~ {hot['end_time']}）")
    if hot.get("trend") == "declining":
        reasons.append("趋势衰退")
    cat_score, cat_reason = category_score(hot, profile)
    if cat_score == 0:
        reasons.append(cat_reason)
    return (not reasons), reasons, cat_score, cat_reason


def score_hot(hot, profile, branch, now):
    ok, reasons, cat_score, cat_reason = hard_filter(hot, profile, branch, now)
    if not ok:
        return None, reasons
    audience, detail = audience_detail(profile, hot, branch)
    fit = round(60 * cat_score + 40 * audience, 1)
    return {
        "hot_id": hot["hot_id"],
        "batch_id": hot["batch_id"],
        "hot_topic": hot["hot_topic"],
        "plate_type": hot["plate_type"],
        "source_type": hot["source_type"],
        "hot_list_type": hot["hot_list_type"],
        "hot_scope": hot.get("hot_scope"),
        "category": hot.get("category"),
        "hot_type": hot.get("hot_type"),
        "rank": hot["rank"],
        "index_value": hot.get("index_value"),
        "trend": hot.get("trend"),
        "saturation": hot.get("saturation"),
        "begin_time": hot["begin_time"],
        "end_time": hot["end_time"],
        "fit_score": fit,
        "fit_detail": {
            "cat": cat_score,
            "cat_reason": cat_reason,
            "audience": audience,
            **detail,
        },
        "raw": hot,
    }, []


def top_hotspots(profile, branch, now, limit=5):
    records = []
    skipped = []
    for hot in load_json(BRANCH[branch]["hot"])["records"]:
        if hot.get("plate_type") != BRANCH[branch]["platform"]:
            continue
        scored, reasons = score_hot(hot, profile, branch, now)
        if scored:
            records.append(scored)
        else:
            skipped.append({"hot_topic": hot["hot_topic"], "hot_id": hot["hot_id"], "reasons": reasons})

    # 同一话题只留一行：热门榜 / 飙升榜同时命中时取分高的那条；同分优先飙升榜
    best = {}
    for row in records:
        key = row["hot_topic"]
        current = best.get(key)
        if current is None:
            best[key] = row
            continue
        if row["fit_score"] > current["fit_score"]:
            best[key] = row
        elif row["fit_score"] == current["fit_score"] and row["hot_list_type"] == "rising" and current["hot_list_type"] != "rising":
            best[key] = row
    ranked = sorted(best.values(), key=lambda r: (-r["fit_score"], r["rank"]))
    return ranked[:limit], skipped


def angle_pool(topic, history):
    allowed = set()
    for keywords, angles in ANGLE_RULES:
        if any(word in topic for word in keywords):
            allowed.update(angles)
    pool = [a for a in ANGLE_LABELS if a in allowed and a in history]
    for angle in history:
        if angle not in pool:
            pool.append(angle)
    for angle in allowed:
        if angle not in pool:
            pool.append(angle)
    for angle in ANGLE_LABELS:
        if angle not in pool:
            pool.append(angle)
    return pool[:6]


def history_forms(profile, branch):
    content_key = BRANCH[branch]["content_key"]
    dist = profile.get("mock_ext", {}).get("content_form_dist", {})
    if dist:
        return {k: v for k, v in dist.items() if v > 0}
    return {}


def pick_reason(row, profile, branch, angle):
    list_label = "热门榜" if row["hot_list_type"] == "hot" else "飙升榜"
    parts = [f"{list_label}第{row['rank']}"]
    detail = row["fit_detail"]
    if branches_is_xhs(branch):
        if detail.get("top_tier"):
            parts.append(f"粉丝{int(round(detail['top_tier_share'] * 100))}%在{detail['top_tier']}岁")
    else:
        if detail.get("top_label"):
            parts.append(f"兴趣{int(round(detail['top_label_share'] * 100))}%{detail['top_label']}")
    forms = history_forms(profile, branch)
    form = ANGLE_FORMS.get(angle)
    weight = forms.get(form)
    if weight is None:
        form = max(forms, key=forms.get) if forms else ""
        weight = forms.get(form, 0)
    form_cn = {"list": "清单", "review": "测评", "tutorial": "教程", "vlog": "记录", "story": "剧情", "info": "科普"}.get(form, form)
    if weight:
        parts.append(f"{form_cn}占历史{int(round(weight * 100))}%")
    reason = "；".join(parts)
    return reason[:40]


def build_candidates(row, profile, branch, history_angles, count=3):
    pool = angle_pool(row["hot_topic"], history_angles)
    candidates = []
    for index, angle in enumerate(pool[:count], 1):
        line = TOPIC_TEMPLATES[angle].format(hot=row["hot_topic"])
        candidates.append({
            "candidate_id": f"cand_{row['batch_id']}_{row['hot_id'].split('_')[-1]}_{index:03d}",
            "hot_id": row["hot_id"],
            "batch_id": row["batch_id"],
            "hot_topic": row["hot_topic"],
            "angle": angle,
            "angle_cn": ANGLE_LABELS[angle],
            "topic_line": line,
            "fit_score": row["fit_score"],
            "fit_detail": row["fit_detail"],
            "pick_reason": pick_reason(row, profile, branch, angle),
            "valid_to": row["end_time"],
            "state": "candidate",
            "platform": row["plate_type"],
        })
    return candidates


def build_pool(branch, seed=None, now_override=None):
    cfg = BRANCH[branch]
    profile = load_json(cfg["profile"])
    hot_file = load_json(cfg["hot"])
    now = parse_time(now_override) if now_override else parse_time(hot_file["mock_batch_now"])

    top, skipped = top_hotspots(profile, branch, now)
    if not top:
        return {
            "branch": branch,
            "platform": cfg["platform"],
            "batch_id": hot_file["batch_id"],
            "now": now.strftime(TIME_FMT),
            "hot_count": 0,
            "error": "无可用热点（硬筛后为空）",
            "skipped": skipped,
        }

    rng = random.Random(seed)
    picked = rng.choice(top)
    history_angles = profile.get("mock_ext", {}).get("history_angles", list(ANGLE_LABELS))
    candidates = build_candidates(picked, profile, branch, history_angles)

    return {
        "branch": branch,
        "mode_label": cfg["form_label"],
        "platform": cfg["platform"],
        "batch_id": hot_file["batch_id"],
        "now": now.strftime(TIME_FMT),
        "seed": seed,
        "track": profile_track(profile, branch),
        "profile_ref": {
            "resource_id": profile["resource_id"],
            "account_nickname": profile["account_nickname"],
            "fans_num": profile["fans_num"],
        },
        "hot_count": len(top),
        "hot_list": [
            {
                "hot_topic": r["hot_topic"],
                "hot_list_type": r["hot_list_type"],
                "source_type": r["source_type"],
                "rank": r["rank"],
                "fit_score": r["fit_score"],
                "fit_detail": {"cat": r["fit_detail"]["cat"], "audience": r["fit_detail"]["audience"]},
                "end_time": r["end_time"],
            }
            for r in top
        ],
        "picked_hot": {key: picked[key] for key in (
            "hot_id", "hot_topic", "hot_list_type", "source_type", "rank", "index_value",
            "trend", "saturation", "begin_time", "end_time", "category", "fit_score",
        )},
        "saturation_warnings": hot_file.get("saturation_warnings", []),
        "candidates": candidates,
        "skipped": skipped,
        "next_step": "把 3 个候选原样给用户选；用户选定后运行 topic_pick.py --select <candidate_id> --seed <seed>",
    }


def main():
    parser = argparse.ArgumentParser(description="M2 选题层（POC）")
    parser.add_argument("--branch", choices=["xhs", "video"], required=True)
    parser.add_argument("--seed", type=int, default=None, help="随机种子；不传则随机并回写")
    parser.add_argument("--now", default=None, help="覆盖当前时间（yyyy-MM-dd HH:mm:ss），默认取 Mock 批次时间")
    parser.add_argument("--list-hot", action="store_true", help="只看硬筛后的 5 条热点，不抽题")
    parser.add_argument("--select", default=None, help="选定候选 ID（需同时传 --seed）")
    args = parser.parse_args()

    if args.list_hot:
        cfg = BRANCH[args.branch]
        profile = load_json(cfg["profile"])
        hot_file = load_json(cfg["hot"])
        now = parse_time(args.now) if args.now else parse_time(hot_file["mock_batch_now"])
        top, skipped = top_hotspots(profile, args.branch, now)
        print(json.dumps({
            "branch": args.branch,
            "now": now.strftime(TIME_FMT),
            "hot_count": len(top),
            "hot_list": [
                {
                    "hot_topic": r["hot_topic"],
                    "hot_list_type": r["hot_list_type"],
                    "rank": r["rank"],
                    "fit_score": r["fit_score"],
                    "fit_detail": r["fit_detail"],
                    "end_time": r["end_time"],
                }
                for r in top
            ],
            "skipped": skipped,
        }, ensure_ascii=False, indent=2))
        return

    if args.select:
        if args.seed is None:
            parser.error("--select 需要同时传 --seed（从上一次输出里取 seed）")
        pool = build_pool(args.branch, seed=args.seed, now_override=args.now)
        hit = next((c for c in pool.get("candidates", []) if c["candidate_id"] == args.select), None)
        if not hit:
            print(json.dumps({"error": f"候选 {args.select} 不存在", "seed": args.seed}, ensure_ascii=False, indent=2))
            raise SystemExit(1)
        print(json.dumps({
            "branch": args.branch,
            "selected": hit,
            "picked_hot": pool["picked_hot"],
            "next_step": f"运行 skeleton_pick.py --branch {args.branch} --topic \"{hit['topic_line']}\" --angle {hit['angle']}",
        }, ensure_ascii=False, indent=2))
        return

    seed = args.seed
    if seed is None:
        seed = random.SystemRandom().randint(100000, 999999)
    pool = build_pool(args.branch, seed=seed, now_override=args.now)
    print(json.dumps(pool, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
