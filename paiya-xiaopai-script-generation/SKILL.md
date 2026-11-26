---
name: paiya-xiaopai-script-generation
description: 派芽 MCN「小派」脚本生成统一技能（POC v2）。当用户要求写小红书图文笔记／种草文、写抖音视频脚本／口播稿／分镜／30 秒短视频，或上传产品 brief 要求产出小红书或抖音内容、修改某版标题／段落／镜头／秒数／转场时使用。一个入口先按本轮原话判断图文还是视频：出现小红书／图文／笔记走图文分支，出现抖音／视频／分镜／口播走视频分支；未指定平台或形态时只问一次「要小红书图文笔记，还是视频脚本（抖音）？」。确认分支后：商单先解析 brief 为事实卡 → 按红人画像 27 字段字典装配画像 → 热点 5 选 1 并生成 3 条选题候选等用户选定 → 取 3 条对应分支的爆款骨架（图文 page_roles／视频 beat_roles）→ 生成三版 → xhs_qc.py／video_qc.py 三层质检 → 对话内可复制块 + Markdown 成品卡 → 按锚点／镜号定点改写。
---

# 派芽小派脚本生成统一入口（POC v2）

## 概述

一个入口，两条执行分支：

- **小红书图文**：标题 + 封面 + B1–B6 正文 + 标签 + 配图建议；
- **抖音视频**：30 秒、9:16、8–14 镜的 9 列分镜表。

入口只做三件事：判断要不要写、判断写图文还是视频、把商单 brief 变成事实卡。确认分支后：

**画像（27 字段字典）→ 热点 5 选 1 → 3 条选题候选（用户选 1）→ 3 条爆款骨架 → 3 版脚本 → 三层质检 → 成品卡。**

**POC 边界**：

- 画像、热点、爆款骨架三处为 MOCK（美食赛道），数据在 `references/mock/`，不代表真实接口结果。
- 画像结构严格按《红人画像建模字段字典 v2.1》的 27 字段；热点按《M2-选题与热点实现方案》的 `hot_trend` 表；骨架按《M3-爆款骨架字段设计》的图文 / 视频字段。
- 图文分支只做小红书；视频分支只做抖音。抖音图文、小红书视频不在标准交付范围内，遇到时如实说明。
- 不负责发布、拍摄、剪辑、生成图片，只产出文案、分镜与配图/拍摄建议。
- 旧技能 `paiya-xiaopai-xhs-generation` / `paiya-xiaopai-douyin-video-generation` 暂保留为兼容入口，新任务优先走本技能。

---

## 统一入口：先跑意图脚本

**先跑脚本，不要凭感觉判断。**

```bash
python3 scripts/intent_score.py --text "<用户原话>" [--attachment] [--in-flow] [--commercial]
```

输出：

| 字段 | 含义 |
|---|---|
| `intent` | `generate` / `llm_check` / `rewrite` / `evaluate` / `chat` / `confirm_modality` / `exit` |
| `branch` | `article` / `video` / `null` |
| `modality` | `article` / `video` / `ambiguous` / `unspecified` |
| `platform` | 小红书 / 抖音 / 空 |
| `mode` | 图文 / 视频 / 商单 / 日常 / 待确认 |
| `score` | 0–95 |
| `brief_required` | 商单但还没拿到 brief 时为 true |
| `notes` | 路由说明与降级提示 |

规则全文见 `references/shared/intent-rubric.md`。

### 0.1 五条前置规则（命中即结束）

| 顺序 | 条件 | 动作 |
|---|---|---|
| ① | 已在脚本链路（等选题 / 等补字段 / 等选版 / 改写中） | `--in-flow`，直接续接；选「1/2/3」「第 2 条」= 选题确认，不按改写处理 |
| ② | 显式拒绝（「不用写」「先不生成」） | `exit`，退出技能 |
| ③ | **形态门** | 按本轮原话路由到 `article` / `video`；说不清 → `confirm_modality` |
| ④ | 评估诉求（「帮我看看这篇」「为什么没流量」）且无创作动词 | `evaluate`，只出评估，不生成 |
| ⑤ | 方法论提问（起号、违规词、完播率、几点发） | `chat`，按日常问答 |

### 0.2 形态门（最高优先级）

**只看本轮原话，不继承上下文。**

| 本轮原话 | 路由 |
|---|---|
| 小红书 / 图文 / 笔记（无视频词） | `branch=article` |
| 抖音 / 视频 / 视频脚本 / 短视频 / 分镜 / 口播稿 / 镜头 / 第 N 秒 / S N | `branch=video` |
| 小红书 + 视频词 | `branch=video`，但如实说明「本期视频只覆盖抖音」 |
| 小红书 + 抖音同时出现 | `confirm_modality` |
| 抖音 + 图文 / 笔记 | `confirm_modality`，说明本期只覆盖小红书图文 + 抖音视频 |
| 只有「脚本 / 商单创作 / 生成一篇 / 写篇脚本」等中性词 | `confirm_modality` |
| 视频词 + 图文词、无平台 | `confirm_modality` |

**确认话术只有一句**：

> 要小红书图文笔记，还是视频脚本（抖音）？

同时用 `interaction.suggest` 给两个可点击选项（用户点一下即回传，不用打字）：
- 「写小红书图文笔记」
- 「写抖音视频脚本」

工具不可用时才退回文字回复。

**顺序铁律**：

1. 先问平台，答完再问 brief 与红人。
2. 形态确认前不解析 brief、不装配画像、不抽选题、不生成任何正文或分镜。
3. 不根据产品品类（咖啡 → 图文）、品牌、红人赛道、上一轮选择或会话历史推断。
4. 上一轮刚选过图文，新一轮未指定平台，仍要重新确认。

**强形态例外**：出现「分镜 / 口播稿 / 视频脚本 / 短视频」且有创作动词时，即使没有「抖音」二字，也直接走视频分支。

### 0.3 三层打分与阈值

| 层 | 内容 | 上限 |
|---|---|---|
| 第一层 | 平台词 +20、创作动词 +20、产出对象 +15、brief 附件 +25、商单词 +20、数量/时长 +10、产品实体 +10 | 65 |
| 第二层 | 创作动词族、内容要素词、平台词密度 | 30 |
| 第三层 | 方法论 −25、诊断 −20、寒暄 −40、只有平台词 −10 | — |

- **≥70**：直接触发，不再问「是否要写脚本」。
- **40–69**：LLM 二判（`temperature=0`，只答是/否）；「是」触发，「否」按日常问答。
- **<40**：按日常问答；可补一句「需要的话我可以帮你写成图文或分镜」。
- **例外**：带 brief 商单直接触发；强形态词 + 创作动词直接触发；明确图文创作不被压成闲聊。

### 0.4 走向

| 走向 | 判定 | 处理 |
|---|---|---|
| **商单创作** | 有 brief 附件，或显式「商单 / 合作 / brief / 品牌方」 | 走阶段一解析 brief，再走画像 → 选题 → 骨架 |
| **日常创作** | 无 brief，用户要一篇笔记/视频但无产品信息 | 跳过阶段一，只用画像 + 热点；不得写价格功效事实 |
| **日常聊天** | `chat` / `evaluate` | 退出技能，正常对话或出评估报告 |
| **待确认** | `confirm_modality` | 只问一次图文还是视频，答完立即路由 |

**商单但无 brief**：要求上传或贴文字，给最少信息清单（产品是什么、卖点 1–3 条、卖给谁、图文还是视频、视频多长/是否口播）。不得编产品，也不得静默降级成日常模式。

---

## 分支路由

| `branch` | 读什么 | 产出 |
|---|---|---|
| `article` | `references/xhs/script-schema.md`、`references/xhs/quality-check.md` | 3 版小红书图文笔记 |
| `video` | `references/video/video-schema.md`、`references/video/video-qc.md` | 3 版 30 秒抖音分镜 |

两个分支共用：`references/shared/context-assembly.md`、`references/shared/topic-selection.md`、`references/shared/skeleton-matching.md`。

**确认分支后只读对应分支的 schema 与质检文档**；另一分支不要加载，避免模板串味。选题与骨架两份共用文档两个分支都要读。

---

## 工作流程

| 阶段 | 名称 | 产出 | 确认门 |
|---|---|---|---|
| 零 | 意图与分支判定 | intent / branch / score / notes | 形态不明先问平台；40–69 二判；商单缺 brief 追问 |
| 一 | Brief 解析（仅商单） | 营销事实卡 | 用户确认事实卡 |
| 二 | 画像装配（27 字段） | 装配摘要（≤200 字） | 无（异常时标注降级） |
| 三 | 选题（热点 5 选 1 → 3 条候选） | 3 条 `topic_line` + 理由 | **必须等用户选 1 条** |
| 四 | 骨架匹配（M3） | 3 条骨架 + 改造清单 + 结构块 | 无（不足 3 条如实说明） |
| 五 | 分支生成 | 3 版图文或 3 版分镜，每版绑定骨架 ID | 无 |
| 六 | 三层质检 | 每版结论 + 命中清单 | BLOCK 修复，最多 3 轮 |
| 七 | 展示与成品卡 | 对话内 3 版 + Markdown 成品卡 | 用户选版或提修改 |
| 八 | 定点改写 | 新版本 + 版本链 | 每轮改完复检 |

---

## 阶段一：Brief 解析（仅商单）

完整字段表、追问话术与事实卡结构见 `references/shared/brief-extraction.md`。

1. **读取**：PDF 用 `pdf` Skill，Word 用 `word` Skill，Excel/CSV 用 `sheet` Skill，PPT 用 `ppt` Skill，图片先 OCR，纯文本直接读；链接先判域名。
2. **抽共用字段**：品牌、产品、品类、核心卖点 1–3、目标人群必填；价格、规格成分、场景、竞品禁区、内容要求选填。
3. **抽分支字段**：
   - 图文：平台、形式、篇数、标题/正文/标签/配图要求、报备要求；
   - 视频：时长、比例、口播人、挂车、报备、镜头节奏。
4. **出事实卡**：表格展示，字段 / 值 / 原文片段 / 是否缺失。
5. **确认门**：事实卡确认后才生成；只改被点名字段，不重跑整份解析。
6. **缺失追问**：一次最多 3 项，按影响排序；用户说「你定」→ 图文默认 3 版；视频默认 30s、9:16、真人口播，并标注默认值。
7. **完全无信息**：请用户上传 brief 或贴文字，不生成任何内容。

POC 演练：

- 图文：`references/mock/xhs/mock-brief.md` → `mock-fact-card.json`
- 视频：`references/mock/video/mock-video-brief.md` → `mock-video-fact-card.json`

---

## 阶段二：画像装配（27 字段字典）

```bash
python3 scripts/fetch_context.py --branch xhs --compact
python3 scripts/fetch_context.py --branch video --compact
python3 scripts/fetch_context.py --branch xhs --compact --fail profile
```

- 画像按《红人画像建模字段字典 v2.1》读取：`resource_id`、`platform`、`self_pitch`、`categories`、`fans_num`，内容子树按分支取 `article` 或 `video`，另有 `common.audience_profile` / `recent_median_views`。
- 图文用：内容支柱、常拍选题、系列结构、封面习惯、当前风格、失败选题、需求缺口、`note_style`、`image_style`、`promo_style`。
- 视频用：人设、口吻三词、语速、口头禅、钩子分布、风格原句、表达规则、出镜意愿、时长偏好，以及通用的支柱 / 选题 / 失败选题 / 需求缺口。
- **只借结构与语气**：钩子类型、叙事骨架、节奏、标题公式；不抄标题原句、不抄风格原句、不写粉丝数。
- 字段缺失允许 NULL，不造默认值；成品卡写清哪一项未用。
- 接口失败时显式降级：成品卡写「本次未使用画像」，不假装参考过。

完整字段用途见 `references/shared/context-assembly.md`。

---

## 阶段三：选题（热点 5 选 1 → 3 条候选）

```bash
python3 scripts/topic_pick.py --branch xhs
python3 scripts/topic_pick.py --branch video --seed 2026
python3 scripts/topic_pick.py --branch xhs --select <candidate_id> --seed <seed>
```

规则见 `references/shared/topic-selection.md`，要点：

1. **硬筛**：平台一致、类目命中（同赛道）、批次窗口有效且 `trend != declining`。
2. **fit 打分**：`60 × cat + 40 × audience`；同一话题只留一行（热门榜 / 飙升榜同题取高分）。
3. **取 5**：按 fit 排前 5，本轮只在这 5 个热点里抽。
4. **随机抽 1**：从 5 个里随机抽 1 个作为本轮热点；随机种子回写，便于复现与 `--select`。
5. **出 3 条候选**：为抽中的热点配 3 个不同角度（自曝踩坑 / 反常识 / 平价替代 / 场景实测 / 对比测评 / 教程步骤），每条一句 `topic_line`（≤25 字）+ 一句 `pick_reason`（≤40 字，必须带榜单位次、画像占比或历史形态占比）。

**展示格式（必须按此给用户）**：

```text
【本轮热点】10 元内自制拿铁（飙升榜第 3 · 搜索词 · 有效至 11-26 12:00）

1｜平价替代：10 元内自制拿铁：用平价替代算一笔账
   理由：飙升榜第 3；粉丝 46% 在 24–30 岁；清单占历史 35%
2｜对比测评：10 元内自制拿铁：用对比测评挑值得的那款
   理由：……
3｜教程步骤：10 元内自制拿铁：用教程步骤复刻一遍
   理由：……

回复 1 / 2 / 3，或「选第 2 条」。
```

**可点击选项（默认方式）**：正文发完后调用 `interaction.suggest`，把 3 条候选连同「换一批」做成 4 个快捷选项，每条 ≤30 字、不带序号、互不重复：

```text
选自曝踩坑这条
选平价替代这条
选场景实测这条
换一批热点
```

选项文案与候选的映射写进成品卡（option_text → candidate_id）。用户点击后文本即下一条消息，按映射直接 `--select`，不要再追问编号。工具不可用时保留「回复 1 / 2 / 3」。

**选择门（硬性）**：

- 必须等用户选定 1 条，才进入骨架与生成；未选定不装配骨架、不写正文。
- 用户回「1 / 2 / 3」「第 2 条」「就这个」，或点击快捷选项回传的「选平价替代这条」→ 视为选定；用 `--select` 确认。
- 用户说「你定 / 都行」→ 取第 1 条，并明说「按第 1 条走」。
- 用户说「都不想要 / 换一批」→ 换 seed 重抽热点，不重复上一轮的 3 条。
- 商单且用户明确「直接按 brief 写，不看热点」→ 可跳过选题门，成品卡标注「本次未用热点」。

**注入边界**：生成侧只接收 `hot_topic`、`angle`、`topic_line` 三个值；热度分、排名、饱和度、画像分布都不进 prompt。

---

## 阶段四：骨架匹配（M3）

```bash
python3 scripts/skeleton_pick.py --branch xhs --topic "<topic_line>" --angle <angle>
python3 scripts/skeleton_pick.py --branch video --topic "<topic_line>" --angle <angle>
python3 scripts/skeleton_pick.py --branch xhs --all
```

规则见 `references/shared/skeleton-matching.md`，要点：

1. **召回**：平台相同、类目同主类目或相邻、形态同或相邻、近 90 天。
2. **硬筛**：达人历史有该 `content_form`；篇幅不超过中位数 2 倍；语速差不超过一档。出镜冲突不剔除，记入改造清单。
3. **打分**：类目 40 / 形态 25 / 节奏 20 / 钩子 15；同分时发布时间新的优先。
4. **取 3 条**：优先三条骨架的 `content_form` 与 `hook_type` 都不重复；不足时只保证 `hook_type` 不重复；仍不足按分数补齐，宁少不凑。
5. **改造清单**：逐项比 `creator_req` 与画像（出镜、口播、语速、手部演示、场景数、剪辑难度、篇幅）；**改造项 > 2 项 → 降级为参照，不进注入**。
6. **结构块**：只给段序、每段职责与三项硬约束（钩子类型、product_in 不晚于 40%、收尾类型）；段数、秒数、字数按本次时长与达人语速现算，不抄样本。

**三条骨架 → 三版**：按分数排 `V1 / V2 / V3`，每条负责一版的段序与职责。骨架不足 3 条 → 少出版本并说明，不硬凑。

骨架不可用或不足时，用分支 schema 的降级骨架（图文：痛点共鸣 / 场景种草 / 测评对比；视频：口播测评 / 剧情演绎 / 沉浸式跟拍），成品卡标注「本次未使用爆款骨架」。

---

## 阶段五：分支生成

### 5.1 图文分支

读 `references/xhs/script-schema.md`，每版按骨架的 `page_roles` 落 B 段：

| `role` | 锚点 |
|---|---|
| `hook` | B1（按 `hook_type` 写） |
| `pain` | B2 |
| `product_in` | B3（不晚于第 3 页） |
| `proof` | B4、B5（多条 proof 依次落） |
| `ending` | B6（按 `ending_type` 写） |

硬约束：三版标题无 ≥6 字连续相同；B1 首句无 ≥8 字连续相同；三版 `hook_type` 不重复；`content_form` 尽量不同；`ending_type` 至少两种；每版覆盖 ≥2 个核心卖点且主推不同；正文 350–700 字，单段 ≤120 字，标题 ≤20 字。

### 5.2 视频分支

读 `references/video/video-schema.md`，每版按骨架的 `beat_roles` 拆镜：

- 首段固定 hook、末段固定 ending；一段可拆 1–5 镜，不可把多段并成一镜；
- 单镜 ≤5s，30s 档 8–14 镜，9 列完整；`product_in` 不晚于 40%（12s）；
- `voiceover=0` 的骨架口播压到 ≤10%，用字幕与画面承担信息。

硬约束：三版钩子类型不重复；口播占比分三档；开场连续 6 字不跨版重复；主推卖点不完全相同；结尾不能三版都是「价格 + 下单」。

**两分支共同底线**：价格、成分、工艺、认证、销量只能来自 brief；缺失写 `【待补充】` 或整段不写；功效词一个都不碰；热点只借角度与结构，不抄原句。

---

## 阶段六：三层质检

### 6.1 图文

```bash
python3 scripts/xhs_qc.py --file "<成品卡.md>" --version V1 --brief references/mock/xhs/mock-fact-card.json
python3 scripts/xhs_qc.py --file "<成品卡.md>" --version V1 --daily
```

**必须逐版跑**；日常创作没有 brief 时加 `--daily`，跳过卖点覆盖与事实对照。

### 6.2 视频

```bash
python3 scripts/video_qc.py --file "<成品卡.md>" --version V1 --brief references/mock/video/mock-video-fact-card.json
python3 scripts/video_qc.py --file "<成品卡.md>" --version V1 --daily
```

**必须逐版跑**，整份跑会把版本号、时间码、元信息数字当成事实数字误报。**日常视频（无 brief）加 `--daily`**，跳过产品名 / 价格落地与卖点覆盖，只查规则层与结构层。

| 层 | 图文查什么 | 视频查什么 |
|---|---|---|
| 规则层 | 绝对化、功效、站外引流、违规暗示 | 功效、绝对化、站外引流、贬低竞品、未授权背书 |
| 结构层 | T/C/B1–B6/H/P 完整、字数 | 9 列、时间码连续、总时长 ±2s、单镜 ≤5s、前 3 秒钩子、口播字数、比例、结尾产品与价格 |
| 覆盖层 | 卖点 ≥2、事实越界、人群、brief 禁用项 | 三卖点落地、画面证明、数字白名单、三版互斥 |

- PASS → 可展示；WARN → 展示时带清单；BLOCK → 不展示，修复后重跑，最多 3 轮。
- 3 轮仍 BLOCK → 说明卡在哪条，给两个可选方向，不硬交付。
- 任何一层未执行，成品卡不得写「已质检」，只能写「质检范围：…」。

通用合规词表与认证/价格口径见 `references/shared/compliance.md`。

---

## 阶段七：展示与成品卡

展示顺序：**选题门（已在阶段三完成）→ 对话内三版可复制块 → 需要并排比较时再出卡片页 → Markdown 成品卡留档**。

- 图文：每版一个代码块，卡头写「V1｜骨架 ID｜形态·钩子｜正文 N 字｜主推」，块内为定位、标题（含备选）、封面、B1–B6、标签、配图、质检结论。
- 视频：每版一个代码块，卡头写「V1｜骨架 ID｜形态·钩子｜30s · 9:16 · N 镜 · 口播 N 字｜PASS」，块内一镜两行，末尾附拍摄清单。
- Markdown 成品卡：元信息、选题与骨架（热点 5 选 1、3 条候选与选定、3 条骨架与改造清单）、装配摘要、三版全文、质检报告、版本链、依据链、待补充项。
- 卡片页：需要比较时生成单文件 HTML；不替代对话内展示。
- 选版：三版发完后用 `interaction.suggest` 给「就用 V1 这版 / 就用 V2 这版 / 三版并排对比 / 再来一批选题」，点击即回传，不用打字。

完整格式见 `references/shared/delivery.md`。

---

## 阶段八：定点改写

1. **解析指代**：版本（V1/V2/V3 或「第一个/第二个」）+ 位置（标题/段落/开头/结尾/第 N 秒/S N/转场）+ 改动类型。
2. **图文锚点**：`T` / `C` / `B1–B6` / `H` / `P1–P6`。
3. **视频锚点**：`HOOK` / `COVER` / `S1–Sn` / `CAP`；秒数先按时间码落镜。
4. **只改锚点**：其余逐字保留；需要联动时只压该段/该镜字幕，不重写全篇。
5. **复检**：改完立即跑该版质检，结论写进版本链。
6. **版本链**：`V2 → V2.1（S8 转场改甩镜）→ V2.2（压口播字数）`。
7. **改动骨架职责**（如把产品出场提前到 12s 前）→ 视为换骨架，先重跑 `skeleton_pick.py`，不靠改字糊过去。

**定位不到**（秒数落在空档、版本不存在、指代有歧义）→ 回问一句，不猜。

---

## 异常与降级

| 场景 | 处理 |
|---|---|
| 画像接口不可用 | 用 brief 人群替代，标注「本次未使用画像」，流程继续 |
| 热点接口不可用 | 跳过选题门，按画像 + brief 生成，标注「无热点参考」 |
| 两者都不可用 | 仅按 brief 生成，标注降级；不假装参考过 |
| 热点池抽不出 5 条 | 有多少用多少；少于 1 条按热点不可用处理 |
| 3 条候选都不想选 | 换 seed 重抽热点，不重复上一轮 |
| 骨架不足 3 条 | 有几条用几条，少出版本并说明；0 条走降级骨架 |
| 骨架改造项 > 2 | 降级为参照，不进注入，换下一条候选 |
| brief 解析失败（加密/模糊） | 说明原因，请用户换格式或贴文字，不猜内容 |
| brief 有多个产品 | 列出清单请用户指定，不混写 |
| 三版同质化 | 只重写冲突版，另两版不动 |
| 质检脚本不可用 | 人工按分支质检文档逐条过，成品卡标注「质检为人工执行」 |
| 用户中途改分支 | 回到阶段零重新确认，保留已有版本，不整链重跑 |
| 用户要求抖音图文 | 说明本期只覆盖小红书图文 + 抖音视频，给替代方案 |
| 用户要求小红书视频 | 说明视频分支只覆盖抖音；可按抖音出稿，或转图文分支 |

---

## 自测清单

```bash
python3 scripts/selftest.py
python3 scripts/intent_score.py --eval references/shared/intent-cases.jsonl
```

交付前逐条勾：

- [ ] 意图评测 23/23，形态门与「未指定平台」用例全绿
- [ ] `selftest.py` 全部通过（含选题 5 选 1、骨架取 3）
- [ ] 商单先出事实卡并等确认，未确认不生成
- [ ] 画像按 27 字段读取，装配摘要 ≤200 字，缺失字段标 NULL
- [ ] 先给 5 选 1 的本轮热点 + 3 条候选，用户选定后才继续
- [ ] 骨架取 3 条，`hook_type` 不重复，改造项 > 2 的不进注入
- [ ] 三版互斥：钩子类型、内容形态、收尾类型不同；图文骨架 ≠ 视频分镜
- [ ] 每版都跑了对应质检，结论为 PASS 或有明确 WARN/BLOCK 清单
- [ ] 数字均来自 brief 或可复算；价格口径未写死
- [ ] 无功效词、绝对化、站外引流、未授权认证
- [ ] 对话内先出三版可复制块，再给 Markdown 成品卡
- [ ] 成品卡写了选题、骨架 ID、降级说明与依据链
- [ ] 改写只动被点名锚点，版本链记录了改动与复检结论

---

## 参考索引

| 文件 | 何时读 |
|---|---|
| `references/shared/intent-rubric.md` | 判定触发、形态门、调阈值、看正负例 |
| `references/shared/brief-extraction.md` | 商单解析 brief、字段缺失、冲突处理 |
| `references/shared/context-assembly.md` | 27 字段画像用途、热点字段、装配摘要、降级 |
| `references/shared/topic-selection.md` | 热点 5 选 1、fit 打分、3 角度、选题门、过期 |
| `references/shared/skeleton-matching.md` | 图文/视频骨架字段、匹配七步、改造清单、约束强度 |
| `references/shared/compliance.md` | 违禁词、认证口径、价格口径、替换建议 |
| `references/shared/delivery.md` | 选题门、对话展示、成品卡、版本链、定点改写 |
| `references/xhs/script-schema.md` | 图文结构、锚点、page_roles → B 段、互斥约束 |
| `references/xhs/quality-check.md` | 图文质检、覆盖层、报告格式 |
| `references/video/video-schema.md` | 视频分镜结构、锚点、beat_roles → 镜号、互斥约束 |
| `references/video/video-qc.md` | 视频质检、时间码、口播、覆盖层 |
| `references/mock/profile/` | 27 字段画像 Mock（小红书 / 抖音两份） |
| `references/mock/hot/` | hot_trend 热点 Mock（5+5 条） |
| `references/mock/skeleton/` | 图文 / 视频骨架 Mock（各 7 条） |
| `references/mock/xhs/` | 图文 brief 与事实卡 |
| `references/mock/video/` | 视频 brief 与事实卡 |

**接真实接口时**：

- 画像：替换 `scripts/fetch_context.py` 的 `load_profile`，保持 27 字段结构；
- 热点：替换 `scripts/topic_pick.py` 的 hot 读取，保持 `hot_trend` 字段；
- 骨架：替换 `scripts/skeleton_pick.py` 的骨架读取，保持 M3 字段（`page_roles` / `beat_roles` 等）。

`SKILL.md`、分支 schema 与质检脚本不需要改。

**旧 Mock 说明**：`references/mock/xhs/mock-profile.json`、`mock-trends.json`、`references/mock/video/mock-video-profile.json`、`mock-video-trends.json` 为 v1 遗留文件，新链路不再读取，仅作对照保留。
