# drama —— 短剧制作工具链

从《代号奥林匹斯》实战项目（1 人 3 天完成 40 集 · 724 镜头竖屏短剧）提炼的通用
制作工具链。**纯 Python 标准库、零第三方依赖**，全部能力通过
`opendreamina drama <action>` 子命令暴露，输出统一 JSON，智能体可直接解析。

## 子命令一览

| 命令 | 作用 | 关键输出 |
|---|---|---|
| `drama init <路径>` | 初始化标准项目骨架 | 创建目录树 + 模板文件（幂等，可重复执行补齐） |
| `drama list` | 项目全部集与状态 | 每集镜头数 / 时长 / 渲染文件数 / 规格状态 |
| `drama parse <EP>` | 解析分镜脚本 | `shots.md` → 结构化镜头数据（锚点逐字保留） |
| `drama compile <EP>` | 编译提示词 | 中文结构化描述 → Seedance-ready 英文提示词 |
| `drama lint <EP>` | 分镜规范校验 | errors（硬性违规）/ warnings（质量建议） |
| `drama spec <EP>` | 生成分集执行规格 | 分镜 + manifest + 注册表 → `tools/episode_specs/EPxx.json` |
| `drama assets <EP...>` | 资产引用审计 | 引用的资产是否登记、文件是否存在、有无平台 asset_id |
| `drama manifest` | 项目 manifest 校验 | assets_manifest / voice_manifest 完整性 |
| `drama qc <EP>` | 成片技术验收 | 逐镜画幅 / 时长 / 音轨（需 ffprobe，缺失时如实降级） |
| `drama review-import` | 把分镜与生成结果导入审片中心 | 逐镜审片任务卡片（分镜「应有」+ 生成任务「实际」） |

通用参数：

- `--project <根目录>`：项目根；缺省依次取 `$DRAMA_PROJECT_ROOT`、当前目录。
- `--maps <文件>`：项目级中英映射表；缺省取 `{项目根}/tools/maps.py`。
- 退出码：`0` 成功 / `1` 校验未通过 / `2` 用法或环境错误。

## 快速上手

```bash
# 1. 建项目骨架
opendreamina drama init ./我的短剧 --title "我的短剧" --episodes 24

# 2. 写分镜（分镜脚本/EP01/shots.md，规范见生成的 _SPEC_分镜模板规范.md）
opendreamina drama lint EP01 --project ./我的短剧          # 机器检查

# 3. 编译英文提示词（先在 tools/maps.py 填充中英词库）
opendreamina drama compile EP01 --project ./我的短剧

# 4. 生成分集执行规格（写入 tools/episode_specs/EP01.json）
opendreamina drama spec EP01 --project ./我的短剧 --write

# 5. 核对资产引用（避免无参考生成）
opendreamina drama assets EP01 --project ./我的短剧

# 6. 生成视频后技术验收
opendreamina drama qc EP01 --project ./我的短剧
```

## 标准项目目录

```
{项目根}/
├── 目标设定.md                    # 项目目标与制作要求
├── 工作流程和注意事项.md          # 流程规范 + 实战注意事项
├── 剧本大纲.md                    # 第1级：八幕骨架（人工确认）
├── 分集剧本/                      # 第2级：场次级剧本（人工确认）
├── 分镜脚本/                      # 第3级：逐镜头（机器检查）
│   ├── _SPEC_分镜模板规范.md      #   格式规范（`_` 前缀，审阅扫描跳过）
│   └── EPxx/
│       ├── shots.md               #   分镜脚本（唯一权威数据源）
│       └── video_renders/         #   生成结果（按镜号子目录）
│           └── _superseded_*/     #   废弃版本（`_` 前缀，审阅扫描跳过）
├── 素材库/
│   ├── 01_characters/{角色}/      #   anchor-portrait / turnaround / halfbody / anchor-voice
│   ├── 02_scenes/{场景}/          #   PRIMARY_exterior / interior
│   ├── 03_props/props/            #   PROP_*.png
│   ├── 04_iconic_scenes/          #   名场面 EPxx_*.png
│   ├── 05_index/                  #   primary_asset_ids.json / generation_report.json
│   ├── 06_bgm/                    #   背景音乐（后期铺设，生成环节禁 BGM）
│   └── 06_voiceover/              #   画外音
├── 参考素材/                      # 画风参考
├── 成片/                          # EPxx.mp4
├── qc_frames/                     # 质检抽帧
└── tools/
    ├── maps.py                    # 项目级中英映射表（parse/compile/lint 自动加载）
    ├── assets_manifest.json       # 资产权威清单（prompt/seed/一致性策略/全局风格）
    ├── voice_manifest.json        # 音色选角
    ├── asset_registry.json        # 平台 asset_id 注册表
    └── episode_specs/EPxx.json    # 分集执行规格（数据/机制分离）
```

**与审阅中心零配置对接**：把项目根放到 `data/review_sources/` 下即可——
素材审阅扫描 `素材库/`，镜头审片扫描 `分镜脚本/EPxx/video_renders/`
（`shots.md` 自动关联为审片底稿提示词、同镜号多版本自动合并对比）。

**镜头审片只收已标识镜头**：媒体必须能从路径与文件名唯一定位到 `EPxx-Sxx`。
`downloads/` 连拍母版、无镜号的整段样片、只有镜号没有集号的分段剪片一律不进列表；
`_` 前缀目录（`_takes` / `_superseded_*` 等历史版本）同样跳过；文件名同时标注
多个镜号的跨镜共用素材（如 `ep01_s08_s12_backdrop.png` 背景板）也不收，避免与正式
镜头拼成假的「同镜多版本」。重新扫描会顺带移出库里残留的这类空壳卡片，
已打分与已写意见不受影响。

**项目不在审阅根目录下时的导入路径**：`drama review-import` 读分镜表与生产状态，
把已成片的镜头连同「应有 vs 实际」直接建成审片任务卡片，不依赖目录被扫描：

```bash
opendreamina drama review-import --project ./我的短剧 --title "我的短剧 · 全季审片" \
    --episodes EP01,EP02          # 缺省导入全部有成片的集
```

- 卡片内容：分镜的秒数 / 景别 / 运镜 / 画面动作 / 台词，加上该镜所属生成任务的
  提示词、模型与实测时长；时长偏差、景别不符在卡片上直接对照。
- 幂等：按（集号, 镜号, 文件路径）去重，重复导入只刷新事实，不覆盖已打的分数与意见。
- 镜头缺文件、分镜有而没生成（如某集末尾几镜）都会如实列出，便于定位缺口。
- `--dry-run` 只解析不写入；`--no-prompt` 跳过生成任务提示词拉取。

## 映射表（tools/maps.py）

编译器把中文视觉描述翻译为英文：算法骨架通用，词库按项目填充。
`drama init` 生成带注释的空模板；`drama lint` 会列出未命中的词，命中后回填：

- `LABEL_ZH_EN`：角色/配角称谓 → 英文名（`"维纳斯": "Venus"`）
- `CHARACTER_ALIASES`：素材 ID 角色标识 → 角色别名（`"venus": ("venus", "aphrodite")`）
- `EXPRESSION_MAP` / `LIGHT_MAP` / `COLOR_MAP` / `ENV_MAP` / `ACTION_FRAGMENTS`：
  表情 / 光感 / 色调 / 环境 / 动作词库（最长键优先匹配）
- `TONE_MAP`：台词语气短语 → 英文 delivery 指令（写在台词行「语气：」段，、分隔；
  例 `"声音沙哑": "hoarse voice"`）——缺失或未命中时台词会被模型平读，念白平淡
- `STYLE`：全局风格常量兜底（AESTHETIC / MEDIUM / AUDIO / NEGATIVE；
  优先读 assets_manifest.json 的 `style` 字段）

设计取向：**宁可少一个英文词，也绝不让中文泄漏进英文提示词**——
未命中的词原样丢弃并在 stderr 告警，`lint` 会汇总列出。

## 模块结构

```
drama/
├── paths.py          项目路径解析与集号归一
├── lexicon.py        共享中英清洗工具 + 项目映射注入
├── cli.py            opendreamina drama 子命令分发器
├── parser/           shots.md 解析（总览表 / 资产绑定 / 人物锚点 / 台词）
├── compiler/         提示词编译骨架 + 映射表模板
├── manifest/         assets_manifest / voice_manifest / episode_spec
├── qc/               成片技术验收 / 资产引用审计 / 台词同步校验
├── lint/             分镜格式规范校验
├── review_import.py  分镜表 + 生产状态 → 审片中心导入清单（只读解析）
└── scaffold/         init 脚手架与模板
```

核心约定（承接奥林匹斯验证过的实践）：

- **shots.md 是唯一权威数据源**，其余数据（spec / manifest / registry）从它派生或登记；
- **三视图优先**：角色槽只保留 `*_turnaround` 资产进入视频参考；
- **数据/机制分离**：episode_spec 只描述「生成什么」，生成器只负责「怎么调平台」；
- **废弃版本放 `_` 前缀目录**，可追溯且不干扰审阅扫描与验收。
