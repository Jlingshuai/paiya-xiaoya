#!/usr/bin/env python3
"""技能自测：一条命令验证安装完整性与三个脚本是否可用。

用法：
  python3 scripts/selftest.py

退出码 0 表示全部通过，1 表示有失败项。
"""

import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
PY = sys.executable

REQUIRED = [
    "SKILL.md",
    "references/intent-rubric.md",
    "references/script-schema.md",
    "references/brief-extraction.md",
    "references/quality-check.md",
    "references/intent-cases.jsonl",
    "references/mock/mock-brief.md",
    "references/mock/mock-fact-card.json",
    "references/mock/mock-profile.json",
    "references/mock/mock-trends.json",
    "scripts/intent_score.py",
    "scripts/fetch_context.py",
    "scripts/qc_check.py",
]

GOOD_SAMPLE = """标题：早八人的咖啡账本
封面：6.9元一杯
B1 7:40，地铁口，我算了笔账。
B2 一天两杯门店咖啡，月底账单不敢细看。
B3 换成山栖冷萃咖啡液，0糖0脂，一条6.9元。
B4 冷水倒进去，3秒化开，口感不比门店差。
B5 现在我常备三条在包里。
B6 你们一个月咖啡预算多少？
标签：#美食 #咖啡 #早八
配图：P1 封面图"""

BAD_SAMPLE = GOOD_SAMPLE.replace(
    "B3 换成山栖冷萃咖啡液，0糖0脂，一条6.9元。",
    "B3 全网最低的咖啡液，加微信领券。",
)

results = []


def run(args):
    proc = subprocess.run(
        [PY, *args],
        cwd=str(SKILL_DIR),
        capture_output=True,
        text=True,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def check(name, ok, detail=""):
    results.append({"name": name, "ok": bool(ok), "detail": detail.strip().splitlines()[0] if detail.strip() else ""})


def main():
    missing = [f for f in REQUIRED if not (SKILL_DIR / f).exists()]
    check("文件完整性", not missing, "全部就位" if not missing else "缺少：" + "、".join(missing))

    code, out = run(["scripts/intent_score.py", "--eval", "references/intent-cases.jsonl"])
    ok = code == 0 and "准确率：100.0%" in out
    check("意图回归 10/10", ok, out.splitlines()[0] if out else "无输出")

    code, out = run(["scripts/fetch_context.py", "--compact"])
    check("上下文装配", code == 0 and "赛道：美食" in out, out.strip()[:70])

    code, out = run(["scripts/fetch_context.py", "--compact", "--fail", "profile"])
    check("画像降级", code == 0 and "未使用" in out, out.strip().splitlines()[-1] if out.strip() else "无输出")

    code, out = run(["scripts/fetch_context.py", "--compact", "--fail", "trends"])
    check("热点降级", code == 0 and "未使用" in out, out.strip().splitlines()[-1] if out.strip() else "无输出")

    code, out = run(["scripts/qc_check.py", "--text", GOOD_SAMPLE])
    try:
        verdict = json.loads(out.split("--- 摘要 ---")[0])["verdict"]
    except Exception:  # noqa: BLE001
        verdict = "解析失败"
    check("质检·合格样本 PASS", verdict == "PASS", f"verdict={verdict}")

    code, out = run(["scripts/qc_check.py", "--text", BAD_SAMPLE])
    try:
        bad_verdict = json.loads(out.split("--- 摘要 ---")[0])["verdict"]
        hits = len(json.loads(out.split("--- 摘要 ---")[0])["rule_layer"]["hard_hits"])
    except Exception:  # noqa: BLE001
        bad_verdict, hits = "解析失败", 0
    check("质检·违规样本 BLOCK", bad_verdict == "BLOCK" and hits > 0, f"verdict={bad_verdict}，硬阻断 {hits} 处")

    width = max(len(r["name"]) for r in results) + 2
    print("\n技能自测")
    print("-" * (width + 42))
    for item in results:
        flag = "✓" if item["ok"] else "✗"
        print(f"{flag}  {item['name']:<{width}}{item['detail']}")
    print("-" * (width + 42))

    failed = [r["name"] for r in results if not r["ok"]]
    if failed:
        print(f"结果：{len(failed)} 项失败 → {'、'.join(failed)}")
        sys.exit(1)
    print(f"结果：{len(results)} 项全部通过")


if __name__ == "__main__":
    main()
