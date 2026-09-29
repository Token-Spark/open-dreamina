# Drama Shotlist Spec — 竖屏短剧分镜模板规范

> 本文件是 ai-video-director 技能的短剧专章：当分镜产出要进入 Open Dreamina
> 短剧制作管线（drama-production-playbook / `opendreamina drama` 工具链）时，
> 分镜必须按本模板书写——它是机器可解析的（`drama lint` 校验、`drama parse` 消费）。

## 输出位置与文件结构

每集一个文件：`{项目根}/分镜脚本/EPxx/shots.md`：

1. 一级标题：`# EPxx · 集名`（含时长 / 镜头数 / 画幅 / 场景 / 核心情绪）
2. 生产说明：全局风格常量（从 manifest style 引用，禁止自创）+ 音频约定
3. 总览表（15 列，时长合计 = 90s）
4. 逐镜头块：每镜一个 `## EPxx-SNN`
5. 质检清单

## 总览表（15 列，顺序固定）

```markdown
| 镜号 | 时长 | 景别 | 机位 | 运镜 | 构图 | 动作 | 表情 | 灯光 | 色调 | 环境 | 声音 | 台词 | 特效 | 衔接 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EP05-S01 | 4 | wide | high-angle | slow-tilt-down | 对称失衡 | 俯瞰… | 木然 | 单支烛光暖调 | 暖黄+阴影 | 锻造坊 | 远处打铁声 | — | — | 开场建立 |
```

景别/机位/运镜必须用规范枚举（未收录写法编译时被丢弃）：
`wide/medium/close_up/extreme_close_up/full`、`eye-level/low-angle/high-angle/overhead/handheld`、
`static/slow-push/slow-pull/slow-pan/slow-tilt-up/slow-tilt-down/handheld-sway/follow/quick-pan`。

## 单镜 15 行模板（顺序固定，缺行 = lint error）

```markdown
## EP05-S08

**镜头功能：** 对话，固定镜头（对话/反应/建立/POV/反转/插入）
**资产绑定：** 角色：char_venus_s1_turnaround ｜ 场景：scene_forge_interior ｜ 道具：prop_metal_rose ｜ 音色：voice_venus
**人物：** Venus（英文外观锚点逐字写全，绝不写「同上」；不入画角色标注「不入画」）
**场景描述：** 场景锚点："Interior of the same blacksmith forge, ...（英文逐字）"
**秒级动作拆解：**
- 0-4s：动作描述；运镜：缓慢推近
**台词同步：**
- Venus（语速 2.5 字/秒，台词："英文台词逐字引用分集剧本"）
**光感：** 午后金色侧逆光
**色调：** 暖金+暗绿
**构图：** 三分法，人物占画面 75%
**细节：** 手部特写道具
**音效设计：** 无背景音乐
**基础环境音：** 炉火噼啪
**动作触发音：** 金属轻碰
**特效音：** —
```

## 硬性规则（drama lint 校验）

- 镜头数 18（±1）、单镜 2-8s、总览表时长合计 = 目标时长
- 必填行齐全；禁止相对引用；台词写在引号内（解析依赖）
- 每集至少 1 个 POV 主观镜头
- 人物资产只绑 `*_turnaround` 三视图（解析器自动过滤半身照/种子图引用）
- 台词逐字引用分集剧本——导演无权改写台词

## AIGC 生成意识（设计即规避）

- 单镜 ≤6s（多人互动/长台词除外，但要有更高重生成预算）
- 一个镜头一个主要视觉任务；复杂动作拆镜
- 多人镜头必须提供空间参考素材，否则改写为单人正反打
- 心理/说话画面：人物占画面 75% 以上
- 禁止夸张特效与复杂运镜（详见 drama-production-playbook references/03）

## 机器检查与下游

```bash
opendreamina drama lint EPxx   # errors=0 才能交给制片执行
opendreamina drama parse EPxx  # 结构化预览（检查锚点/台词解析结果）
```

分镜通过 lint 后进入 production-orchestrator（spec 生成与批量生成）。
