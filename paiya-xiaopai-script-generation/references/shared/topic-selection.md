# 选题层：热点 5 选 1，再出 3 个角度（M2）

本文件对齐《M2-选题与热点实现方案》：M2 只回答“说什么、为什么现在说”，产出候选选题池，不写脚本。脚本创作从用户选定一条选题之后才开始。

## 目录

1. 模块定位与输入输出
2. hot_trend 字段
3. 硬筛三条
4. fit 打分
5. 5 → 1 → 3 的抽取规则
6. topic_candidate 字段
7. 对话展示与选择门
8. 状态、过期与补池
9. 注入边界与降级
10. POC 命令与 Mock

---

## 1. 模块定位与输入输出

| 输入 | 内容 | 性质 |
|---|---|---|
| 势 | 平台正在发生什么（话题榜、搜索词） | 公共，天级 / 小时级刷新 |
| 壳 | 这个达人能怎么讲（画像、历史题材） | 私有，月级刷新 |

输出是一份候选选题清单：**一个达人 × 一个热点 × 一个角度 = 一条候选**。只有势没有壳是热点播报，只有壳没有势是重复选题，两者相乘才是候选池。

M2 的终点是“讲什么、从哪个角度讲”。结构怎么组织交给 M3，甲方必讲点交给 brief，语言风格交给画像。

## 2. hot_trend 字段

POC 用 `references/mock/hot/mock-hot-trends.json`，一条记录对应“一个话题在当前批次的状态”。

| 字段 | 取值 | 用途 |
|---|---|---|
| `hot_id` | `md5(plate_type + hot_topic)` 前 12 位 | 跨批次稳定 ID |
| `batch_id` | `yyyyMMddHH` | 批次键，与 hot_id 组成一行 |
| `hot_topic` | 平台话题名或搜索词原文 | 唯一进入生成侧的热点字段 |
| `plate_type` | `xhs` / `dy` | 平台硬筛 |
| `source_type` | `topic` 话题榜 / `search_word` 搜索词 | 解释信号来源，不进正文 |
| `hot_list_type` | `hot` 热门 / `rising` 飙升 | 同题两榜各存一行，不合并 |
| `hot_scope` | `all` 全网 / `industry` 行业电商 | `all` 时跳过类目硬筛 |
| `category` | 平台原始类目名 | 经 M4 映射表落到达人主赛道 |
| `hot_type` | `daily` 日常 / `fixed` 固定周期 | fixed 靠人工维护，如节日、季节 |
| `begin_time` / `end_time` | 批次周期 | 窗口判断；候选有效期抄 `end_time` |
| `index_value` / `rank` | 榜单指数原文 / 排名 | 只进 `pick_reason` |
| `trend` | `rising` / `peak` / `declining` | `declining` 不进池 |
| `saturation` | 近 7 天同题新增 ÷ 类目日均新增 | 过高时提示换角度 |
| `profile` | 话题人群画像 | 小红书 age/gender/二十标签；抖音八大标签 |

## 3. 硬筛三条

任一不满足，不进池：

1. **平台一致**：`hot_trend.plate_type` = 达人主平台；
2. **类目命中**：`category` 经类目映射落在达人主赛道内；`hot_scope=all` 时跳过；
3. **窗口有效**：当前时间在 `begin_time` 与 `end_time` 之间，且 `trend != declining`。

## 4. fit 打分

```text
fit_score = 60 × cat + 40 × audience
```

| 维度 | 口径 |
|---|---|
| `cat` | 类目命中取 1；同父类目取 0.6；跨类目 0 |
| `audience` | 话题画像与粉丝画像的重叠度：小红书年龄、性别各占一半；抖音比八大标签；单侧缺失取 0.5，不判死 |

权重是初始值，上线后按选用率与赞踩校准，不写死在代码里。

## 5. 5 → 1 → 3 的抽取规则

1. **取前 5**：按 `fit_score` 排序取前 5 个热点。同一话题只留一行——热门榜与飙升榜同时命中时取分高的那行；同分优先飙升榜，避免 15 条里出现重复热点。
2. **随机抽 1**：从 5 个热点里随机抽 1 个，作为本轮选题的热点。随机只在“这次给哪 1 个”上生效，卡面顺序仍按 fit 排。
3. **配 3 个角度**：为抽中的热点配 3 个不同角度，角度取自该达人历史题材集合，同一热点下 3 个角度不重复。

角度枚举：

| angle | 中文 | 典型用法 |
|---|---|---|
| `self_fail` | 自曝踩坑 | 先讲自己翻车，再讲怎么避 |
| `counter_intuition` | 反常识 | 拆一个大众误区 |
| `cheap_alternative` | 平价替代 | 算单次成本，对比门店价 |
| `scene_test` | 场景实测 | 早八 / 工位 / 通勤现场 |
| `comparison` | 对比测评 | 多款逐项对比，给结论 |
| `tutorial` | 教程步骤 | 3 步复刻，可跟做 |

角度与形态的默认映射（M3 召回用）：`cheap_alternative→list`、`comparison→review`、`tutorial→tutorial`、`scene_test→vlog`、`counter_intuition→info`、`self_fail→story`。

## 6. topic_candidate 字段

POC 由 `scripts/topic_pick.py` 生成，字段与 M2 表对齐：

| 字段 | 说明 |
|---|---|
| `candidate_id` | `cand_{batch_id}_{hot_id 尾 4 位}_{序号}`，同批次内唯一 |
| `hot_id` / `batch_id` | 引用 hot_trend |
| `hot_topic` | 热点原词 |
| `angle` / `angle_cn` | 切入角度 |
| `topic_line` | 一句话选题，≤25 字，给用户看 |
| `fit_score` / `fit_detail` | 总分与四项明细（cat / audience / 命中原因） |
| `pick_reason` | ≤40 字，必须带具体事实：榜单位次、画像占比、历史形态占比；禁止“很适合你” |
| `valid_to` | 生成时抄 `hot_trend.end_time`，不回查热点表 |
| `state` | `candidate` / `recommended` / `selected` / `skipped` |
| `platform` | 与 hot_trend 一致 |

`topic_line` 模板：

```text
{hot_topic}：用{角度中文}{动作}
平价替代 → 算一笔账 / 对比测评 → 挑值得的那款 / 教程步骤 → 复刻一遍
场景实测 → 看真实体验 / 反常识 → 拆一个误区 / 自曝踩坑 → 讲清代价
```

## 7. 对话展示与选择门

展示顺序固定：**本轮热点 → 3 条候选 → 一句“回复编号即可”**。不要一次把 5 个热点全抛出，也不要替用户选。

```text
【本轮热点】10 元内自制拿铁（飙升榜第 3 · 搜索词 · 有效至 11-26 12:00）

1｜平价替代：10 元内自制拿铁：用平价替代算一笔账
   理由：飙升榜第 3；粉丝 46% 在 24–30 岁；清单占历史 35%
2｜对比测评：10 元内自制拿铁：用对比测评挑值得的那款
   理由：飙升榜第 3；粉丝 46% 在 24–30 岁；测评占历史 30%
3｜教程步骤：10 元内自制拿铁：用教程步骤复刻一遍
   理由：飙升榜第 3；粉丝 46% 在 24–30 岁；教程占历史 20%

回复 1 / 2 / 3，或「选第 2 条」。
```

**可点击选项**：正文之后调用 `interaction.suggest`，把 3 条候选与「换一批」做成 4 个快捷选项（每条 ≤30 字、不带序号、用角度名区分），例如「选自曝踩坑这条 / 选平价替代这条 / 选场景实测这条 / 换一批热点」。点击回传的文本按映射表转 candidate_id，不要求用户再打字。

**选择门**：用户选定后才进 M3 与生成。未选定前不装配骨架、不生成正文。

用户回「1 / 2 / 3」「第 2 条」「就这个」→ 视为选题确认，`intent_score.py --in-flow` 走 `continue`。用户说「都不想要 / 换一批」→ 重新抽热点（换 seed），不重复上一轮的 3 条。

## 8. 状态、过期与补池

| 状态 | 含义 |
|---|---|
| `candidate` | 待推荐，抽样池只取这个状态 |
| `recommended` | 已展示给用户 |
| `selected` | 已选中，不再推荐 |
| `skipped` | 不感兴趣，不再推荐 |

- 过期即出池：只抽 `valid_to` 大于当前时间的候选；过期的既不进池，也不计入“池子耗尽”。
- 池子耗尽：15 条都推荐过且未被选中 → 按最新批次重建一批；同一批次内可把热点扩到 Top 10。
- 混合池逐条判：daily 与 fixed 混在一批时按条判断，不整池作废。

POC 只实现“单轮 5 → 1 → 3 + 选择”，不落库 15 条；状态流转写进成品卡的依据链即可。

## 9. 注入边界与降级

- 生成侧只接收 `hot_topic`、`angle`、`topic_line` 三个值。
- 不传热度分、排名、饱和度、画像分布——这些会诱导模型解释数据。
- 热点只承担“为什么现在说”，不是内容素材；正文里的产品事实仍只来自 brief。
- 热点接口不可用 → 跳过选题门，直接按画像与 brief 生成，标注「无热点参考」。
- 画像不可用 → 只能按 brief 人群生成，标注「本次未使用画像」，且选题的 audience 分按 0.5 处理。

## 10. POC 命令与 Mock

```bash
# 看硬筛后的 5 条热点
python3 scripts/topic_pick.py --branch xhs --list-hot

# 随机抽 1 个热点，出 3 条候选（返回 seed，供复现与 select）
python3 scripts/topic_pick.py --branch xhs
python3 scripts/topic_pick.py --branch video --seed 2026

# 用户选定后确认
python3 scripts/topic_pick.py --branch xhs --select cand_2026112608_2b81d4e6_002 --seed 2026
```

- Mock 批次时间固定为 `2026-11-26 10:00:00`（`mock_batch_now`），避免热点一落盘就过期。
- 小红书榜 5 条、抖音榜 5 条，均按美食赛道与阿梨画像构造；抖音「咖啡液平价替代」同时存热门榜与飙升榜两行，用于验证同题去重。
- 接真实接口时：替换 `topic_pick.py` 里的 `load_json(BRANCH[branch]["hot"])`，保持 hot_trend 字段不变。
