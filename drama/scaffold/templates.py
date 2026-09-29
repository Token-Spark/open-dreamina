"""脚手架模板文件内容（`opendreamina drama init` 写入新项目）。

模板提炼自《代号奥林匹斯》的目标设定 / 工作流程和注意事项 / 分镜规范，
占位符（如 {{TITLE}}）由 create_project 填充。
"""

from drama.compiler.maps_template import MAPS_TEMPLATE  # noqa: F401

GOAL_TEMPLATE = """# 目标设定

## 目标
制作让观众忍不住想要一直看下去的短剧内容。

## 项目名称：{{TITLE}}

## 项目代号：{{CODE}}

## 体裁设定
- 画幅：9:16 竖屏短剧
- 语言：{{LANGUAGE}}
- 风格：真人
- 画风：{{AESTHETIC}}

## 规模
- 总集数：{{EPISODES}} 集，单集 {{DURATION}} 秒左右
- 面向人群：{{AUDIENCE}}

## 制作要求
- 靠人物对话驱动，对话时单人正面占据画面 75% 以上；
- 加入第一视角画面，增加沉浸感；
- 人物、场景、道具设计精美；
- 画风统一，降低 AI 感。
"""

WORKFLOW_TEMPLATE = """# 工作流程和注意事项

## 短剧制作流程
1. 剧本大纲（需人工检查）；
2. 分集剧本（需人工检查）；
3. 分镜脚本 shots.md（需机器检查：`opendreamina drama lint EP01`）；
4. 生成分镜视频（需人工检查：审阅中心 → 镜头审片）。

## 资产准备
所有素材资产都需要人工确认验收（审阅中心 → 素材审阅）。

### 人物
- 半身正面照片（halfbody）
- 三视图（正面、侧面、背面全身照，turnaround）——**视频生成一律绑三视图**
- 音色音频（WAV 格式，5 秒时长，anchor-voice）

* 单个人物随剧情可能有多套造型资产，按 `<角色>_<集段>_<造型>_<类型>` 命名。

### 场景
- 外观图片（exterior，primary 锚点）
- 内部结构图片（interior，以 primary 重绘派生）

* 单个场景随时间/布置可能有多套图片在产。

### 道具
- 特写图片
- 字体清晰的外观照片（统一 `PROP_` 前缀）

## 注意事项（实战经验）
1. 人物一致性：同一集内穿搭妆造保持一致（衣物款式、污渍位置），可单独生成本集参考素材锁定；
2. 场景一致性：同一集内环境保持一致；引用环境图片时提示词减少环境文字描写，避免冲突；
3. 禁止夸张特效（光柱、火花、3D 渲染、形变），用高度写实画面表现；
4. 杜绝复杂运镜：单人物镜头 + 台词动作推进剧情，减少多人动作互动画面；
5. 用台词和表情展现背景与冲突，每集埋伏笔；
6. 人物素材引用三视图（turnaround），不引用半身照或种子素材；
7. 心理活动/说话画面：人物占画面 75% 以上，减少背景曝光。

## AI 视频生成规范
- 严格排除背景音乐（BGM 后期统一铺设），避免字幕和 Logo；
- 严格绑定人物三视图与音色；
- 优先使用 Seedance 720p + 全能参考模式；谨慎使用首尾帧模式；
- 单镜建议 ≤6 秒；多人镜头易出错，必须提供空间参考素材。

提示词格式参考（完整规范见 分镜脚本/_SPEC_分镜模板规范.md）：

```
镜头功能：对话，固定镜头
人物：venus（@CHAR_venus_s1_turnaround，@voice_venus）
场景描述：

秒级动作拆解：
- 0-4s：侧写，xxxx；运镜：全景跟随
台词同步：0-4s：
- 人物（语速 2.5 字/秒，台词："..."）

画风：{{AESTHETIC}}
构图：
细节：
音效设计：无背景音乐；
基础环境音：
动作触发音：
特效音：
```
"""

OUTLINE_TEMPLATE = """# 剧本大纲：{{TITLE}}

> 第 1 级剧本（八幕骨架）。人工确认后再进入分集剧本（第 2 级）。

## 高概念（Logline）

（一句话：谁 + 想要什么 + 谁阻止 + 为何不能妥协）

## 核心人物
- 主角（Protagonist）：
- 对手（Antagonist）：
- 情感锚点（Emotional Anchor）：
- 变数（Wild Card）：

## 八幕结构（每幕对应 5 集左右）
| 幕 | 集 | 情绪基调 | 关键事件 |
|---|---|---|---|
| 第一幕 | EP01-05 | | |
| 第二幕 | EP06-10 | | |
| 第三幕 | EP11-15 | | |
| 第四幕 | EP16-20 | | |
| 第五幕 | EP21-25 | | |
| 第六幕 | EP26-30 | | |
| 第七幕 | EP31-35 | | |
| 第八幕 | EP36-40 | | |
"""

SHOTS_TEMPLATE = """# {{EP}} · {{TITLE}}

- 集时长：{{DURATION}}s / 镜头数：{{SHOTS}} / 画幅：9:16
- 场景：
- 核心情绪：

## 生产说明

全局风格常量（生成时逐字追加到每条提示词尾部，由 tools/assets_manifest.json 的 style 提供）：

- AESTHETIC：（美学基调英文）
- MEDIUM：（媒介质感英文）
- AUDIO：keep the spoken dialogue and all natural action and environment sound effects audible; absolutely no background music, no musical score, no soundtrack, no music bed
- NEGATIVE：（负面词英文）

音频处理约定：生成环节只剔除 BGM，禁止整体静音（人声 + 动作音效 + 环境音必须保留）。
资产绑定说明：人物一律绑三视图（*_turnaround），音色绑 anchor-voice；禁止相对引用。

## 总览表

| 镜号 | 时长 | 景别 | 机位 | 运镜 | 构图 | 动作 | 表情 | 灯光 | 色调 | 环境 | 声音 | 台词 | 特效 | 衔接 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

> 时长校验：上表时长合计必须 = {{DURATION}}s。

## 逐镜头

<!-- 每镜一块，格式：
## {{EP}}-S01

**镜头功能：**（对话 / 反应 / 建立 / POV / 反转…）
**资产绑定：** 角色：char_xx_turnaround ｜ 场景：scene_xx ｜ 道具：prop_xx ｜ 音色：voice_xx
**人物：** 英文名（英文外观锚点，逐字；不入画角色标注「不入画」）
**场景描述：** 场景锚点："英文场景锚点，逐字"
**秒级动作拆解：**
- 0-4s：动作（含运镜说明）
**台词同步：**
- 说话人（语速 2.5 字/秒，台词："英文台词逐字"）
**光感：** / **色调：** / **构图：** / **细节：**
**音效设计：** 无背景音乐
**基础环境音：** / **动作触发音：** / **特效音：**
-->

## 质检清单
- [ ] 时长合计 = {{DURATION}}s
- [ ] 每镜 2-8s（建议 ≤6s）
- [ ] 至少 1 个 POV 主观镜头
- [ ] 台词逐字引用分集剧本，无改写
- [ ] 资产 ID 与 assets_manifest 一致
- [ ] 无「同上」等相对引用
"""

SPEC_DOC_TEMPLATE = """# _SPEC 分镜模板规范（V1.0）

> 本文件以 `_` 开头：镜头审片扫描会跳过它，供人与 AI 智能体随时查阅。

## 1. 三级剧本体系
| 层级 | 文件 | 检查方式 |
|---|---|---|
| 第1级 剧本大纲 | 剧本大纲.md | 人工确认 |
| 第2级 分集剧本 | 分集剧本/分集剧本_EPxx-xx.md | 人工确认 |
| 第3级 分镜脚本 | 分镜脚本/EPxx/shots.md | 机器检查（opendreamina drama lint）|

## 2. shots.md 固定结构
1. 标题 + 集时长 / 镜头数 / 画幅 / 场景 / 核心情绪
2. 生产说明（全局风格常量 + 音频约定 + 资产绑定说明）
3. 总览表（15 列：镜号/时长/景别/机位/运镜/构图/动作/表情/灯光/色调/环境/声音/台词/特效/衔接）
4. 逐镜头提示词块（每镜一个 `## EPxx-SNN`）
5. 质检清单

## 3. 单镜必填行（顺序即模板）
资产绑定 / 镜头功能 / 人物 / 场景描述 / 秒级动作拆解 / 台词同步 / 光感 / 色调 / 构图 / 细节 / 音效设计 / 基础环境音 / 动作触发音 / 特效音

## 4. 硬性规则
- 镜头数 18（±1），单镜 2-8s（建议 ≤6s），时长总和 = 目标集时长
- 每集至少 1 个 POV 主观镜头
- 台词逐字引用分集剧本，不可改写
- 禁止相对引用（「同上」），外观锚点逐字复用
- 人物资产引用只认三视图（*_turnaround）
- 摄影取值使用规范枚举（wide/medium/close_up、eye-level/high-angle、static/slow-push…），
  未收录写法会被编译器丢弃

## 5. 机器检查

    opendreamina drama lint EP01 --project <项目根>
"""

MANIFEST_TEMPLATE = {
    "version": 1,
    "project": "",
    "provider": "",
    "model": "",
    "style": {
        "aesthetic": "",
        "medium": "",
        "audio": ("keep the spoken dialogue and all natural action and environment sound effects "
                  "audible; absolutely no background music, no musical score, no soundtrack, no music bed"),
        "negative": "",
    },
    "defaults": {"aspect_ratio": "9:16", "resolution": "720p", "poll": 600},
    "consistency_strategy": {
        "layer_1_style": "所有生成注入统一 style 四常量",
        "layer_2_character_anchor": "每角色仅一张 primary 基准（固定 seed），变体以 primary 重绘",
        "layer_3_scene_anchor": "每场景仅一张 primary 外观，内景/变体以 primary 重绘",
        "layer_4_composition": "名场面同时引用角色 primary + 场景 primary",
    },
    "assets": [],
}

VOICE_MANIFEST_TEMPLATE = {
    "version": 1,
    "project": "",
    "provider": "",
    "voices": [],
}

ASSET_REGISTRY_TEMPLATE = {"version": 1, "provider": "", "scope": "project", "assets": {}}
