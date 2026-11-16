#!/usr/bin/env python3
"""统一技能自测：一条命令验证两分支安装完整性与脚本可用性。

用法：
  python3 scripts/selftest.py

退出码 0 表示全部通过，1 表示有失败项。
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
PY = sys.executable

REQUIRED = [
    "SKILL.md",
    "references/shared/intent-rubric.md",
    "references/shared/brief-extraction.md",
    "references/shared/context-assembly.md",
    "references/shared/compliance.md",
    "references/shared/delivery.md",
    "references/shared/intent-cases.jsonl",
    "references/xhs/script-schema.md",
    "references/xhs/quality-check.md",
    "references/video/video-schema.md",
    "references/video/video-qc.md",
    "references/mock/xhs/mock-brief.md",
    "references/mock/xhs/mock-fact-card.json",
    "references/mock/xhs/mock-profile.json",
    "references/mock/xhs/mock-trends.json",
    "references/mock/video/mock-video-brief.md",
    "references/mock/video/mock-video-fact-card.json",
    "references/mock/video/mock-video-profile.json",
    "references/mock/video/mock-video-trends.json",
    "scripts/intent_score.py",
    "scripts/fetch_context.py",
    "scripts/xhs_qc.py",
    "scripts/video_qc.py",
]

GOOD_XHS = """标题：早八人的咖啡账本
封面：6.9元一杯
B1 7:40，地铁口，我算了笔账。
B2 一天两杯门店咖啡，月底账单不敢细看。
B3 换成山栖冷萃咖啡液，0糖0脂，一条6.9元。
B4 冷水倒进去，3秒化开，口感不比门店差。
B5 现在我常备三条在包里。
B6 你们一个月咖啡预算多少？
标签：#美食 #咖啡 #早八
配图：P1 封面图"""

BAD_XHS = GOOD_XHS.replace(
    "B3 换成山栖冷萃咖啡液，0糖0脂，一条6.9元。",
    "B3 全网最低的咖啡液，加微信领券。",
)

GOOD_VIDEO = """### V1｜口播测评（30 秒）

- **定位**：给早八打工人，用价格与速溶做信任。
- **时长 / 比例**：30s｜9:16 竖屏
- **前 3 秒钩子**：数字——阿梨举杯，「6.9元一条，我囤了三盒。」
- **口播总字数**：92 字（上限 150）
- **卖点落点**：S1 价格 / S2 成分 / S3 速溶

| 镜号 | 时间码 | 时长 | 景别 | 画面 | 台词 / 口播 | 字幕 | 音效 / BGM | 转场 |
|---|---|---|---|---|---|---|---|---|
| S1 | 0-3s | 3s | 近景 | 阿梨举杯对镜头 | 6.9元一条，我囤了三盒。 | 6.9元/条 | 轻快前奏 | 硬切 |
| S2 | 3-6s | 3s | 特写 | 撕开包装，咖啡液倒入冰杯 | 0糖0脂，配料表干净。 | 0糖0脂 | 撕开声 | 硬切 |
| S3 | 6-9s | 3s | 特写 | 冷水冲开，杯内旋涡 | 冷水一冲，3秒化开。 | 3秒速溶 | 倒水声 | 硬切 |
| S4 | 9-12s | 3s | 近景 | 阿梨喝一口 | 口感和门店差不多。 | 顺口不涩 | 吞咽声 | 硬切 |
| S5 | 12-15s | 3s | 特写 | 价格牌与产品盒 | 一盒十条，算下来6.9。 | 69元/盒 | 点击声 | 硬切 |
| S6 | 15-18s | 3s | 中景 | 包里常备三条 | 包里常备三条。 | 随身带 | 拉链声 | 硬切 |
| S7 | 18-21s | 3s | 特写 | 办公桌与键盘 | 下午三点来一条。 | 办公室 | 键盘声 | 硬切 |
| S8 | 21-24s | 3s | 近景 | 阿梨举杯 | 不用排队，也不用等外卖。 | 省时间 | 环境声 | 硬切 |
| S9 | 24-27s | 3s | 特写 | 产品盒与杯并排 | 山栖冷萃咖啡液，69元一盒。 | 山栖｜69元/盒 | 收尾鼓点 | 硬切 |
| S10 | 27-30s | 3s | 中景 | 阿梨举杯对镜头 | 想试的，先看活动期。 | 活动价69 | 收尾 | 淡出 |

- **拍摄清单**：工位、产品盒、冰杯、咖啡液；阿梨出镜。
"""

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

    code, out = run(["scripts/intent_score.py", "--eval", "references/shared/intent-cases.jsonl"])
    ok = code == 0 and "准确率：100.0%" in out and "评测样本：23" in out
    check("意图回归 23/23", ok, out.splitlines()[0] if out else "无输出")

    code, out = run(["scripts/fetch_context.py", "--branch", "xhs", "--compact"])
    check("图文上下文装配", code == 0 and "赛道：美食" in out, out.strip()[:80])

    code, out = run(["scripts/fetch_context.py", "--branch", "video", "--compact"])
    check("视频上下文装配", code == 0 and "平均完播：32%" in out, out.strip()[:80])

    code, out = run(["scripts/fetch_context.py", "--branch", "xhs", "--compact", "--fail", "profile"])
    check("图文画像降级", code == 0 and "未使用" in out and "降级" in out, out.strip().splitlines()[-1] if out.strip() else "无输出")

    code, out = run(["scripts/fetch_context.py", "--branch", "video", "--compact", "--fail", "trends"])
    check("视频热点降级", code == 0 and "未使用" in out and "降级" in out, out.strip().splitlines()[-1] if out.strip() else "无输出")

    code, out = run(["scripts/xhs_qc.py", "--text", GOOD_XHS])
    try:
        verdict = json.loads(out.split("--- 摘要 ---")[0])["verdict"]
    except Exception:  # noqa: BLE001
        verdict = "解析失败"
    check("图文质检·合格 PASS", verdict == "PASS", f"verdict={verdict}")

    code, out = run(["scripts/xhs_qc.py", "--text", BAD_XHS])
    try:
        payload = json.loads(out.split("--- 摘要 ---")[0])
        bad_verdict = payload["verdict"]
        hits = len(payload["rule_layer"]["hard_hits"])
    except Exception:  # noqa: BLE001
        bad_verdict, hits = "解析失败", 0
    check("图文质检·违规 BLOCK", bad_verdict == "BLOCK" and hits > 0, f"verdict={bad_verdict}，硬阻断 {hits} 处")

    with tempfile.TemporaryDirectory() as tmp:
        storyboard = Path(tmp) / "storyboard.md"
        storyboard.write_text(GOOD_VIDEO, encoding="utf-8")
        code, out = run(
            [
                "scripts/video_qc.py",
                "--file",
                str(storyboard),
                "--version",
                "V1",
                "--brief",
                "references/mock/video/mock-video-fact-card.json",
            ]
        )
    ok = code == 0 and "V1 质检：PASS" in out
    detail = [line for line in out.splitlines() if line.startswith("V1 质检：")] or ["无输出"]
    check("视频质检·合格 PASS", ok, detail[0])

    width = max(len(r["name"]) for r in results) + 2
    print("\n统一技能自测")
    print("-" * (width + 46))
    for item in results:
        flag = "✓" if item["ok"] else "✗"
        print(f"{flag}  {item['name']:<{width}}{item['detail']}")
    print("-" * (width + 46))

    failed = [r["name"] for r in results if not r["ok"]]
    if failed:
        print(f"结果：{len(failed)} 项失败 → {'、'.join(failed)}")
        sys.exit(1)
    print(f"结果：{len(results)} 项全部通过")


if __name__ == "__main__":
    main()
