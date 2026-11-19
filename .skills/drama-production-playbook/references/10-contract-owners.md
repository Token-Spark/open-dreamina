# 10 契约归属表（每条事实只有一个 owner）

> 短剧链有 7 个技能，同一份契约会被 4–5 个技能同时引用。引用没问题，
> **各自重新定义**才是问题：数值一改就要改五处，漏一处就变成两套口径。
>
> 本表给每条契约指定**唯一 owner 文件**。owner 之外的任何地方只允许写
> 「见 `X`」，不允许再写一遍具体数值、模板原文或字段清单。

## 1. 契约 → owner

| # | 契约 | 唯一 owner | 谁在消费（只引用） |
|---:|---|---|---|
| 1 | `shots.md` 14 行模板（`## EPxx-SNN` + 13 个标签）/ 15 列列序 / lint 硬规则（18 镜、2–8s、枚举、POV、只绑 `*_turnaround`、声音三行） | `ai-video-director/references/drama-shotlist-spec.md` + 代码 `drama/lint/shots_lint.py` 的 `REQUIRED_BLOCK_LINES`；保护条款 `17` §5 | playbook、orchestrator、reviewer、optimizer |
| 2 | 分镜 12 字段与四向映射（12 字段 ↔ 02 的 19 字段 ↔ 14 行 / 15 列 ↔ 生成卡） | `ai-video-director/references/17-storyboard-vs-shotlist-dual-output.md` §3/§4 | director 内部、orchestrator |
| 3 | 编译 8 段结构 / 全局风格四常量 / 中英映射纪律 | `prompt-optimizer/references/drama-prompt-pattern.md` | playbook、orchestrator、reviewer |
| 4 | 短剧镜头提示词九行模板（镜头功能 / 人物 / 场景描述 / 秒级动作拆解 / 台词同步 / 音效设计 / 基础环境音 / 画面风格 / 特效音）与音乐负面词表 | `prompt-optimizer/references/02-prompt-templates.md` §3.4 / §4.5 | playbook、director、orchestrator、reviewer |
| 5 | 连拍组：合组判据 / 组规模与时长配额 / 镜段式提示词 / 母版裁切 / 组级验收 / 降级路径 | `ai-video-director/references/23-take-group-multi-shot.md` | playbook、orchestrator、optimizer、reviewer |
| 6 | 接续：入场态三条主线 / 英文接续句 / A·B·C 三级 / 接续门禁 / 配对播放 QC | `ai-video-director/references/22-shot-continuity-in-generation.md` | playbook、orchestrator、reviewer |
| 7 | 关系关键帧 `rel_*`：触发条件 / 登记 / 硬门禁 / 相对位置 QC | `ai-video-director/references/19-relationship-keyframe.md` | playbook、orchestrator、optimizer、reviewer |
| 8 | 室内布局与全景锚点 `loc_*`：触发条件 / 朝向映射 / 门禁 / 结构 QC | `ai-video-director/references/20-indoor-layout-anchor.md` | playbook、orchestrator、reviewer |
| 9 | 集内状态锁：妆造与陈设锁定 / 只引用不描述 / 三视图种子纪律 / `*_detail` 不进参考 | `ai-video-director/references/21-episode-state-lock.md` | playbook、orchestrator、optimizer、reviewer |
| 10 | 表演禁忌（禁「倒吸气」类反应）与替代表演写法 | `ai-video-director/references/24-character-performance.md` | optimizer |
| 11 | 帧模式纪律（默认 `reference`、首帧理由、provider 缺省分叉） | `drama-production-playbook/references/03-seedance-best-practices.md` 规则 5 | orchestrator、optimizer、reviewer |
| 12 | 音频纪律（台词同期、生成期禁 BGM、双通道压制、禁整体静音） | `drama-production-playbook/references/03-seedance-best-practices.md` 规则 6 | orchestrator、optimizer、reviewer |
| 13 | 五层锚点一致性策略（风格 / 角色 / 场景 / 关系 / 道具 / 集内状态） | `drama-production-playbook/references/04-consistency-strategy.md` | director、orchestrator |
| 14 | 资产命名、ID 白名单（`char_` `scene_` `prop_` `voice_`）、`rel_*`/`loc_*` 例外 | `drama-production-playbook/references/05-asset-naming-convention.md` | director、orchestrator |
| 15 | 标准目录与审阅中心扫描口径 | `drama/README.md`（`drama init` 生成，代码事实）；设计理由见 playbook `07` | 全链 |
| 16 | 生成前置三查（模板逐字 / 参考装配 / 编组粒度）与 60 秒清单 | `production-orchestrator/references/10-generation-preflight.md` | playbook、optimizer |
| 17 | `episode_spec` 结构与生产状态机（`BLOCKED` / `RETRY` / `HUMAN_REVIEW`） | `production-orchestrator/references/production-schema.md` + `drama-execution.md` | playbook、reviewer |
| 18 | 模型能力与参数窗口（时长上下限、分辨率档位、参考素材上限） | 代码事实：`backend/app/providers/sparkhub_seedance.py` 的 `_MODEL_DURATION_RANGE` / `_MODEL_MAX_RESOLUTION` / `_ref_url_keys` | 全部技能文档 |
| 19 | 单镜自检评分（8 维，满分 80 换算百分制，≥70 通过） | `ai-video-director/references/09-pipeline-and-qc.md` §5 | — （只有导演侧用） |
| 20 | 六维初审与档位判定（PASS=70 / REVISE=60 / 红线 ≤55） | `shot-reviewer/references/02-generic-rules.md` §1、`references/04-scoring-and-feedback.md` §2 | orchestrator（下游交接） |
| 21 | 集级验收 Production Score（10 维，≥80 才可交付） | `ai-video-director/references/11-principles-and-acceptance.md` §2 | — （集级门禁） |
| 22 | 七层创作 pipeline、层级归属与回溯判断 | `short-drama-creator/references/seven-layer-pipeline.md` | 全链 |
| 23 | 角色音色锚点 `anchor-voice.wav`：产物规格（5s / 4–6s、wav 格式、纯人声）、产出三条路径、五项验收、`voice_manifest` 登记、三件套完成定义与 `BLOCKED` 门禁、绑定时序、变声例外、QC 口径 | `drama-production-playbook/references/11-voice-anchor.md` | playbook 02/04/05/07/09、director 05、orchestrator 02/10/drama-execution、reviewer 02、optimizer |
| 24 | 角色设定卡与设定图四件套：卡字段模板（人物属性九字段/辨识特征/着装描述/表情谱/管线绑定）、四件规格与命名（特写/立绘 fullbody/表情九宫格 expressions/三视图）、生成顺序、提示词骨架、素材人工验收、主要角色必备与过场豁免 | `drama-production-playbook/references/12-character-design-sheet.md` | playbook 01/02/04/05/07/SKILL、creator character-design/drama-context/SKILL、director 05/21/24、orchestrator 02/10、optimizer 02、viral-remake asset-generation |

## 2. 允许复述的 6 条（不是例外，是硬纪律）

下面 7 条要求**每个门禁都能独立执行**，所以允许在各技能的强制规则里各写一遍。
但复述时**只能写结论与指针，不得改写数值、模板结构与字段名**；一旦与 owner 不一致，
以 owner 为准，并修消费方那一处：

1. 妆造 / 陈设一经图片锁定，提示词只引用不描述（owner #9）
2. 参考与首帧只用 `*_turnaround`，半身照 / 剧照 / 成片截帧 / 拼贴板不得作种子（owner #9）
3. `frame_mode` 必须显式传 `reference`（owner #11）
4. 先合组再拆镜（owner #5）
5. 生成期禁 BGM、台词同期、禁后期 TTS（owner #12）
6. 多人 / 共现 / 室内多角度必须先批准 `rel_*` / `loc_*`，拆正反打与合组都不免除（owner #7/#8）
7. 角色资产 = 基准肖像 + 三视图 + 音色锚点 wav，缺 wav 的角色未完成、其台词镜 `BLOCKED`（owner #23）

## 3. 三条变更纪律

1. **数值只改一处**：阈值、时长、镜数、权重、时长窗口只写在 owner 文件里。
   别处出现具体数字即视为「复述」，发现不一致时按 owner 修。
2. **新增契约先查本表**：已有 owner → 改 owner；没有 → 先在本表登记一行，再写正文。
3. **改 owner 要留痕**：owner 文件被修改时，在本文末尾「变更记录」追加一行
   （日期 / 文件 / 改了什么 / 受影响的消费方），否则视为未变更。

## 4. 变更记录

| 日期 | 文件 | 改动 | 受影响消费方 |
|---|---|---|---|
| 2026-11-13 | `ai-video-director/17` §4 | 转场字段改为「不承载」，明确衔接列是入场态不是转场术语 | drama-shotlist-spec、playbook 02 |
| 2026-11-13 | `ai-video-director/06` §1 | CHARACTER 段去掉发型/服饰示例，补管线内收口说明 | optimizer drama-prompt-pattern |
| 2026-11-13 | `ai-video-director/09` §5 | 8 维满分 80 的换算与阈值补齐；新增「三把尺的分工」 | reviewer 02/04、11 §2 |
| 2026-11-13 | `ai-video-director/11` §2/§3 | 集级验收与单镜分界说明；流程图去掉 VOICE/SFX/MUSIC 后置阶段，补初审与技术验收 | playbook 02、reviewer |
| 2026-11-13 | `drama-production-playbook/03` | 目录后缀改为「模型代号」；基线模型改 2.5 并说明 15s 硬限 | orchestrator drama-execution、playbook 07/08 |
| 2026-11-13 | `production-orchestrator/drama-execution` | 基线模型 `doubao_seedance_2_5`；命令与产物路径按模型代号 | playbook 03、reviewer 06 |
| 2026-11-13 | `prompt-optimizer/03` §2.3 | `frame_mode` 默认改为「无（必须显式传）」 | optimizer SKILL 规则 15、02 §3.2 |
| 2026-11-13 | `prompt-optimizer/02` §3.4 | **换成用户定稿的九行模板**（新增「画面风格」行、动作触发音并入基础环境音、`//` 工位说明、`@//id/` 占位符），并补 §3.4.1 与 `shots.md` 的对应表 | playbook 03、director 08/23/SKILL 25、orchestrator 10/SKILL、drama-prompt-pattern、drama-shotlist-spec |
| 2026-11-13 | `drama/lint/shots_lint.py` + 文档 | **分镜表声音行四行→三行**：`**动作触发音：**` 移出 `REQUIRED_BLOCK_LINES`（并入基础环境音），新增 `LEGACY_BLOCK_LINES` 只出迁移 warning；逐镜块 15 行→14 行（13 标签 + 标题），全局 28 处措辞同步改名 | drama-shotlist-spec、17、22、23、19、02-breakdown、director/orchestrator/optimizer SKILL、preflight、playbook 01/02/08、AGENTS.md |
| 2026-11-13 | `playbook/11`（新增，契约 #23） | **音色锚点提为角色资产的必备件**：明确 5s wav 规格 / TTS 选角产出 / 五项验收 / `voice_manifest` 登记 / 三件套完成定义与缺 wav 的 `BLOCKED` 门禁 / 无台词镜不绑音色 / 变声例外 / QC 口径 | playbook 02/04/05/07/09/SKILL、director 05、orchestrator 02/10/drama-execution、reviewer 02 |
| 2026-11-13 | `drama/lint/shots_lint.py` | 新增「台词镜资产绑定缺 `voice_*`」warning（只报不改 valid），把 #23 的绑定时序落到机器检查 | playbook 11 §4/§6、orchestrator 10 |
| 2026-11-15 | `playbook/12`（新增，契约 #24） | **角色设定卡与设定图四件套**：卡字段模板（人物属性九字段/辨识特征跨造型不变/着装按造型分节/表情谱）、四件规格命名（特写=基准肖像、立绘 `_fullbody`、表情九宫格 `_expressions`、三视图）、生成顺序与提示词骨架、素材人工验收（主要角色必备/过场豁免立绘与表情格）；三件套 `BLOCKED` 口径（#23）与种子纪律（#9）不变，无代码改动 | playbook 01/02/04/05/07/SKILL、creator character-design/drama-context/SKILL、director 05/21/24、orchestrator 02/10、optimizer 02、viral-remake asset-generation |
