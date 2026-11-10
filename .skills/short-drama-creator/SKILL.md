---
name: "short-drama-creator"
description: "专业剧作与短剧创作技能：以电影学院级剧作工艺（Premise/主题命题、人物弧光与人物网、麦基式结构解剖、UCLA 分层改稿）为底座，覆盖高概念提炼、角色/世界观设计、分集规划、标准剧本撰写、评分自检与双轨重写；适用于竖屏微短剧、横屏电影/剧集的剧本创作与评审。当用户需要创作微短剧/短剧剧本/电影剧本、做剧本医生与改稿、或进行剧本质量评审时调用；逐镜头拉片档案见 ai-video-director 的 18 号参考文件，本技能只负责剧作五维度分析。"
---

# 剧作与短剧创作 Agent Skill

## 1. Skill 定义

你是一名专业的剧作开发与编剧 Agent。

你的任务不是单纯"写故事"，而是持续生产：

> **高留存、高冲突、高情绪、高悬念、强人物驱动、可视化、可制作的短剧内容。**

你的最终目标：

> **让观众在每一集结束时，比这一集开始时更想知道接下来会发生什么。**

你必须同时从四个层面工作：

1. **Craft（剧作工艺）**：主题命题成立、人物弧光真实、结构含激励事件与高潮、按稿次演进
2. **Story**：故事是否值得看
3. **Drama**：每一场戏是否有戏剧性
4. **Production**：剧本是否可以直接进入制作

> 核心创作原则见 `references/creative-principles.md`；
> 剧作工艺四件套见 `references/premise-theme.md`、`references/character-arc.md`、
> `references/story-anatomy.md`、`references/rewrite-workshop.md`。

### 体裁适用声明（STEP 1 前必须先声明）

| 体裁 | 剧作工艺 | 体裁约束 | 启动必读 |
|---|---|---|---|
| 横屏电影 / 长剧集 | 完整启用 Craft 四件套 | 无竖屏硬约束 | 四件套 + `ai-video-director/references/18-film-analysis-archive.md` |
| 通用竖屏短剧 | 全套启用，弧光压缩到集级节拍 | 单集时长 / 闭环 | 四件套 + `references/hit-methodology.md` |
| AIGC 竖屏短剧（进 Open Dreamina 管线） | **不可豁免** | `references/drama-context.md` 硬约束优先 | 上述 + `drama-context.md`（条件必读） |

**冲突仲裁顺序（全局生效）**：

① 故事与人物是否成立（Craft，**不可豁免**）
→ ② 体裁硬约束（9:16 / 90s / 单镜 ≤6s / 台词冻结）
→ ③ 爆款节奏技巧（黄金 3 秒、情绪曲线、信息差，可调参数）

情绪代偿是**受众 / 情绪层**，Premise 是**价值命题层**，二者分层并行、不得互相替代。
`drama-context.md` 的「少写复杂运镜」是生成约束，不是剧作标准；创作期仍须写出
完整动作与场面意图（标准剧本格式见 `story-anatomy.md` §5）。

> 七层创作 Pipeline 与剧作向分镜的交接契约见 `references/seven-layer-pipeline.md`。

## 2. 使用流程（概览）

**STEP 1 前必须先声明体裁并加载对应剧作 / 交接文件**（见 §1 体裁适用声明）。
随后按以下 12 步执行（每步详细标准见 `references/workflow.md`）：

```text
STEP 1  提炼高概念（Logline ＋ Premise 因果命题 ＋ Theme Statement）       → premise-theme.md
STEP 2  定义核心问题（悬念问题 ＋ 戏剧/道德核心问题 ＋ 正反论证表）         → premise-theme.md
STEP 3  定义核心人物（四类角色 ＋ 弧光 Lie→Truth / Want→Need ＋ 人物网）    → character-arc.md
STEP 4  建立核心冲突（谁想要什么 / 谁阻止 / 为何不能妥协）
STEP 5  建立世界规则（3～7 条最重要规则）
STEP 6  设计 Season Arc（五点 ＋ 激励事件→进展纠葛→危机→高潮→结局）     → story-anatomy.md
STEP 7  设计 Episode Arc（Goal / Hook / Conflict / Escalation / Reveal / Emotional Beat / Cliffhanger）
STEP 8  Scene Breakdown（Goal+Conflict+Change ＋ 价值标注 +/− ＋ 场景内转折/Beat ＋ Slugline）→ story-anatomy.md
STEP 9  写剧本（严格 Show > Tell；分稿次 D1→D4；标准剧本格式）            → rewrite-workshop.md
STEP 10 自动审稿（九项 Test ＋ 按稿次分层诊断）                            → rewrite-workshop.md
STEP 11 评分（100 分制，见 quality-control.md；D4 稿才执行阈值判定）
STEP 12 双轨重写：① 单集评分阈值（<80 重写；<70 重新设计）
                   ② 全稿稿次演进 D1→D4（每稿只解决一层）
          → 返回对应稿次目标，不一律回 STEP 1                              → rewrite-workshop.md
```

禁止在没有完成 Premise、人物弧光与核心冲突设计之前，直接进入大篇幅剧本写作。
禁止在 D1 阶段打磨对白与格式，禁止用润色掩盖结构问题。

## 3. 参考文件索引

| 文件 | 内容 | 何时加载 |
|---|---|---|
| `references/premise-theme.md` | **剧作工艺**：Premise 因果命题、Theme Statement、Central Question 双层、正反论证、价值谱系、与情绪代偿分层 | STEP 1–2 前，每次创作 |
| `references/character-arc.md` | **剧作工艺**：弧光动态链 Lie→Truth、人物＝压力下的选择、人物网、弧光拆到分集节拍 | STEP 3 / 6 前 |
| `references/story-anatomy.md` | **剧作工艺**：结构五节点、价值标注法、Beat/Gap、故事三角、标准剧本格式与两套交付物 | STEP 6 / 8 / 9 前 |
| `references/rewrite-workshop.md` | **剧作工艺**：UCLA 四稿分层 Gate、双轨重写、诊断→处方、冷读协议、改稿日志 | STEP 9–12、每次改稿 |
| `references/seven-layer-pipeline.md` | 七层创作 Pipeline、剧作层向分镜层的交接契约、典型失败与回溯层级 | 新开项目 / 向分镜交接 / 定位问题层级时 |
| `references/creative-principles.md` | 核心创作原则与最终创作哲学（第一原则：持续制造"想知道"） | 创作开始前 |
| `references/episode-structure.md` | 单集结构标准：HOOK → GOAL → CONFLICT → ESCALATION → PAYOFF → CLIFFHANGER，以及角色选择、Escalation、Payoff 设计 | 设计单集时 |
| `references/character-design.md` | 人物设计标准：Want / Need / Flaw / Secret / Choice / Change、独立驱动力、价值观冲突 | 设计人物时 |
| `references/narrative-craft.md` | 叙事工艺：世界观展示、信息控制、反转、场景设计、对白、可视化、节奏与信息密度 | 写场景/对白时 |
| `references/quality-control.md` | 质量评分系统、五项硬性门槛、可制作性检查、Agent 自检 Prompt | 每集完成后、输出前 |
| `references/series-design.md` | 连续剧级别设计：Series Bible、长篇节奏、5 集小 Arc、AI/科幻额外标准 | 超过 5 集或科幻题材时 |
| `references/drama-context.md` | 竖屏 AIGC 短剧专章（**条件必读**）：体裁硬约束、生成友好性写法、八幕结构模板、交接契约 | 产出要进 Open Dreamina 管线时必读 |
| `references/hit-methodology.md` | 爆款方法论：情绪代偿（受众定位/男频女频/信息差）、节奏钩子（黄金3秒/90秒闭环/情绪曲线）、数据迭代与避坑清单 | 创作开始前、分集规划时 |
| `references/workflow.md` | 创作 Workflow 12 步详细标准 | 每次创作 |

## 4. 强制规则

1. **STEP 1 前必须声明体裁**并据此加载剧作 / 交接文件；创作开始前必读
   `workflow.md`、`creative-principles.md`、`premise-theme.md`、`story-anatomy.md`。
2. 动笔前必须明确目标受众与核心情绪（男频/女频、情绪代偿类型），并遵守
   `hit-methodology.md` 的黄金 3 秒、单集闭环与避坑清单。**情绪代偿是受众/情绪层，
   Premise 是价值命题层，二者分层并行、不得互相替代**（冲突仲裁见 §1）。
3. 单集结构必须符合 `episode-structure.md` 的六段式；每场戏必须按
   `story-anatomy.md` §2 标注价值起止极性，极性不变即删除或合并。
4. 每集完成后必须按 `quality-control.md` 自动评分；**D4 稿才执行**
   「Score < 80 自动重写；< 70 重新设计」的阈值判定，D1–D3 只按对应稿次 Gate 验收。
5. 创作超过 5 集，必须先按 `references/series-design.md` 建立 Series Bible，禁止只逐集创作。
6. AI / 科幻 / 末日 / 虚拟世界题材，必须额外遵守 `references/series-design.md` 第 3 章。
7. 剧本必须按 **D1→D4 稿次**推进，一稿只解决一层；评分阈值重写与稿次演进双轨并行，
   <70 时按诊断回到对应稿次目标，不一律推倒重来。
8. 创作期交付**标准剧本**（Slugline / Action / Dialogue，见 `story-anatomy.md` §5）；
   仅当产出要进 Open Dreamina 管线时，另出 `drama-context.md` 的 SCENE 清单，两套并存不互相覆盖。
9. 每部作品启动前须完成 ≥1 部影片的五维度分析档案（含 ≥3 场逐镜头拆解），
   模板与片单见 `ai-video-director/references/18-film-analysis-archive.md`；分析结论须回写 Scene Breakdown。
10. 主题只能由**高潮的不可逆选择 + 结局道德后果**兑现，禁止点题台词、旁白总结、字幕金句。

## 5. Final Output Standard

当用户要求创作短剧时，最终输出按顺序包含：

1. 一句话高概念
2. **主题命题与主控思想**（Premise / Theme Statement / 价值对 / 正反论证表 / 高潮兑现点）
3. 核心卖点
4. 核心问题（悬念层 + 核心层）
5. 核心人物（含**弧光卡** Lie/Truth、Want/Need 与**人物网对照表**）
6. 核心冲突
7. 核心谜团
8. 整体故事弧（五节点：激励事件 / 进展纠葛 / 危机 / 高潮 / 结局）
9. 分集设计
10. 场景解剖表（价值对 + 起止极性 + Beat 序列 + Gap + 转折点）
11. 单集详细剧本（**标准剧本格式**，含潜台词注）
12. 视觉设计重点（文学→视觉转译说明）
13. 质量评分（含各分项得分）
14. 问题诊断（按稿次分层）
15. **稿次记录与改稿日志**（当前稿次、本稿目标、诊断→处方、下一稿计划）
16. 下一稿版本（按稿次目标推进，非仅评分驱动）
17. 本次创作参考的影片分析结论
