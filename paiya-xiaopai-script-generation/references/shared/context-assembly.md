# 画像与热点装配（图文 / 视频共用）

画像严格按《红人画像建模字段字典 v2.1》的 27 字段结构读取（主键 `resource_id`，平台账号粒度），热点按《M2-选题与热点实现方案》的 `hot_trend` 表读取。POC 用 MOCK 数据，真实接入时只替换 `scripts/fetch_context.py` 里的 `load_profile` / `load_trends`，返回结构不变。

## 1. 命令

```bash
python3 scripts/fetch_context.py --branch xhs --compact
python3 scripts/fetch_context.py --branch video --compact
python3 scripts/fetch_context.py --branch xhs --compact --fail profile
python3 scripts/fetch_context.py --branch video --compact --fail trends
```

- `--branch xhs`：读 `references/mock/profile/mock-profile-xhs.json`（article 子树）+ `references/mock/hot/mock-hot-trends.json`。
- `--branch video`：读 `references/mock/profile/mock-profile-douyin.json`（video 子树）+ 同一份热点表（按 `plate_type=dy` 过滤）。
- `--fail`：模拟接口超时，验证降级。

## 2. 画像字段怎么用（27 字段字典）

一级字段（身份归属）与 common 两段，两分支都读：

| 字段 | 用途 |
|---|---|
| `self_pitch` | 人设锚点，写进装配摘要；与 `persona_line` 分歧时视为转型信号 |
| `categories` | 赛道判定的第一依据，也是 M2 类目硬筛的对照物 |
| `fans_num` | 只用于量级判断，不写进脚本 |
| `common.audience_profile` | 人群对齐：性别、年龄、地域、兴趣；M2 的 audience 打分直接用这张表 |
| `common.recent_median_views` | 效果基线：判断“代表作”和“篇幅/时长是否可执行”，不写进脚本 |

图文分支（article 子树）：

| 字段 | 用途 |
|---|---|
| `topic_pillars` | 三版骨架必须落在 2–4 个支柱内，防账号跑偏 |
| `content_topics` | 选题池的历史题材来源 |
| `series_structures` | 有系列时优先套系列模板 |
| `cover_habits` | 封面文案与样式，写进 `C` 锚点 |
| `style_evolution.current_dominant` | 当前主导风格，避免用过时结构 |
| `flop_topics` | 事前降权，M2 生成角度时直接排除 |
| `audience_questions` | 人群需求缺口的真实来源，用于痛点段与 CTA |
| `note_style` | 标题公式、正文结构、emoji 密度、标签习惯 |
| `image_style` | 配图风格（构图 / 亮度 / 道具），写进 `P` 锚点 |
| `promo_style` | 卖点表达偏好：硬广 / 软植入 / 测评对比 |

视频分支（video 子树）：

| 字段 | 用途 |
|---|---|
| `persona_line` | 人设一句话，决定口吻基线 |
| `tone_words` | 三个口吻词，prompt 高密度约束 |
| `speech_features.speech_rate` | 字/秒，换算口播字数与段长 |
| `catchphrases` | 一致性闸门：允许化用，不整句搬运 |
| `hook_patterns` | 前 3 秒钩子的历史分布，M3 打分用 |
| `style_sentences` | few-shot 语气锚点，只借语气不抄内容 |
| `expression_rules` | 禁用 / 必用表达，逐条校验 |
| `on_camera` | 出镜意愿，M3 改造清单的第一项 |
| `video_duration` | 个人 / 商单时长中位数，M3 硬筛用 |
| `topic_pillars` / `content_topics` | 同图文 |
| `flop_topics` | 同图文 |
| `audience_questions` | 同图文 |

**边界**：画像只提供“怎么说、说什么方向”，不提供产品事实。价格、成分、认证只能来自 brief。

## 3. 热点字段怎么用（M2 hot_trend）

`fetch_context.py` 只做窗口过滤与平台过滤，选题决策在 `topic_pick.py` 里完成。

| 字段 | 用途 |
|---|---|
| `hot_id` / `batch_id` | 候选选题的追溯键 |
| `hot_topic` | 唯一进入生成侧的热点字段之一 |
| `plate_type` | 与达人主平台一致才进池 |
| `source_type` | 话题榜 / 搜索词，用于解释“为什么现在说” |
| `hot_list_type` | 热门榜看体量、飙升榜看增速；同题两榜并存时取高分那行 |
| `category` | 类目硬筛，经 M4 映射表落到达人主赛道 |
| `hot_type` / `begin_time` / `end_time` | 窗口判断；候选有效期直接抄 `end_time` |
| `index_value` / `rank` | 只进 `pick_reason`，不进正文 |
| `trend` / `saturation` | `declining` 不进池；饱和过高时提示换角度 |

**注入生成侧只给三个值**：`hot_topic`、`angle`、`topic_line`。热度分、画像分布、饱和值都不进 prompt，否则模型会去解释数据而不是写内容。

## 4. 装配摘要

写一段 ≤200 字的摘要，包含：

- 赛道与 2–4 个内容支柱；
- 人设与口吻；
- 人群画像与需求缺口；
- 可用的骨架方向（形态、钩子、节奏）；
- 必须避开的失败选题与饱和选题；
- 本次是否使用画像 / 热点，未使用写明原因。

示例：

> 美食赛道，快手早餐 / 平价咖啡测评；人设「替打工人试错的早八食堂」，口吻像同事聊天；粉丝 78% 女性、57% 在 24–30 岁，需求缺口是「一盒能喝多久 / 冷水能不能化开」；可用测评、清单、教程三类骨架，钩子以算账和冲突为主；避开探店、露营装备；本次热点「10 元内自制拿铁」。

## 5. 降级

| 场景 | 处理 |
|---|---|
| 画像接口不可用 | 用 brief 自带人群替代，成品卡标注「本次未使用画像」 |
| 热点接口不可用 | 标注「无热点参考，按画像结构生成」 |
| 两者都不可用 | 仅按 brief 生成，标注降级；不假装参考过 |
| 画像字段缺失 | 允许 NULL，不造默认值；缺哪个字段就在成品卡写哪个字段未用 |
| 热点池为空 | 按不可用处理，不编热点 |
