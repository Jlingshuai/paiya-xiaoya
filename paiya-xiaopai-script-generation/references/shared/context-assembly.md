# 画像与热点装配（图文 / 视频共用）

通过第三方离线接口获取红人画像与赛道热点。POC 阶段用 MOCK 数据，真实接入时只替换 `scripts/fetch_context.py` 里的 `load_profile` / `load_trends`，返回结构保持不变。

## 1. 命令

```bash
python3 scripts/fetch_context.py --branch xhs --compact
python3 scripts/fetch_context.py --branch video --compact
python3 scripts/fetch_context.py --branch video --fail profile
```

- `--branch xhs`：读 `references/mock/xhs/mock-profile.json` 与 `mock-trends.json`。
- `--branch video`：读 `references/mock/video/mock-video-profile.json` 与 `mock-video-trends.json`。
- `--fail profile` / `--fail trends`：模拟接口超时，验证降级。

## 2. 图文分支取哪些字段

| 字段 | 用途 |
|---|---|
| 赛道 primary / secondary | 定选题与人群 |
| 人设 one_liner、语气 tone | 定口吻，避免广告腔 |
| 人群 core_needs、price_sensitivity | 定痛点与价格表达 |
| 内容 best_performing_structures | 选三版骨架 |
| hook_preference | 定标题与 B1 开头 |
| 商业规则 commercial_rules | 确认接单边界 |

**不把粉丝数、单篇点赞、收藏数写进脚本**，只用于选策略与定语气。

## 3. 视频分支取哪些字段

| 字段 | 用途 |
|---|---|
| 赛道 primary / secondary | 定选题与人群 |
| 人设 one_liner、语气 tone | 定口吻 |
| 平均完播率、擅长形式 | 判断叙事形式是否匹配 |
| 语速（字/秒） | 换算口播字数 |
| 镜头节奏 | 定单镜时长与切镜密度 |
| 钩子偏好 | 定前 3 秒手法 |
| 人群 core_needs | 定痛点与场景 |
| 热点视频的 hook / body / ending 结构 | 只借结构，不抄原句 |
| `saturation_warnings` | 撞车规避，命中的开头必须换 |

## 4. 热点使用边界

**只借结构**：钩子类型、叙事骨架、镜头节奏、字幕信息分工、CTA 形式。

**禁止复用**：原标题原句、原文段落、原视频画面与配乐、他人评论数据、博主个人信息。

**撞车规避**：`saturation_warnings` 命中的开头方式，必须换一种。当前 MOCK 警告包括：

- 「3 秒冲咖啡」动作三连已饱和，禁止复用撕开—倒水—举杯；
- 「同事以为我点外卖」误会式开头已滥用，需换冲突对象或冲突类型；
- 横评类饱和，若走测评结构，对比维度换成单次成本而不是口感。

## 5. 装配摘要

写一段 ≤200 字的摘要，包含：

- 赛道关键词与人群痛点；
- 可用的叙事结构；
- 必须避开的饱和选题；
- 本次是否使用画像 / 热点，若未使用写明原因。

示例：

> 美食赛道，咖啡茶饮 / 快手早餐；人群是早八打工人，痛点「没时间、想省钱、怕热量」；可用「算账式开头 + 三个对比维度 + 提问式 CTA」；避开「3 秒冲咖啡」动作三连与「同事以为我点外卖」误会开头。

## 6. 降级

| 场景 | 处理 |
|---|---|
| 画像接口不可用 | 用 brief 自带人群替代，成品卡标注「本次未使用画像」 |
| 热点接口不可用 | 标注「无热点参考，按通用结构生成」 |
| 两者都不可用 | 仅按 brief 生成，标注降级；不假装参考过 |
| 接口返回空数组 | 按不可用处理，不编造热点 |
