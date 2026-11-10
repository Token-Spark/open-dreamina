# 剧本拆解：Scene → Beat → Shot

> 对应 SKILL.md 索引中的 `references/02-breakdown.md`。
> 拿到剧本后加载。包含：Scene Breakdown、Beat Breakdown、Shot Design（拍摄字段定义）。

## 1. Scene Breakdown

首先将剧本拆成 Scene。

每个 Scene 输出：

```text
Scene ID
Scene Purpose
Location
Time
Characters
Dramatic Goal
Conflict
Emotional State
Visual Motif
Start State
End State
```

特别关注：

> **Scene Start ≠ Scene End**

如果一场戏结束时：

* 人物关系没变
* 信息没变
* 情绪没变
* 风险没变
* 目标没变

优先建议合并或删除。

## 2. Beat Breakdown

每个 Scene 必须进一步拆成 Beat。

例如：

```text
SCENE 03

Beat 1
主角进入医院

Beat 2
发现所有医生已经离开

Beat 3
系统宣布患者生命评分

Beat 4
主角发现妹妹就在手术室

Beat 5
系统拒绝开门

Beat 6
主角决定强行破门
```

每个 Beat 必须产生：

> Information / Emotion / Action / Decision

至少一种变化。

## 3. Shot Design

每一个 Beat 转化成 Shot。

每个 Shot 必须定义：

```text
Shot ID
Purpose
Shot Size
Camera Angle
Camera Position
Lens
Composition
Subject
Action
Expression
Camera Movement
Lighting
Environment
Depth
Duration
Transition
Sound
Dialogue
VFX
```

> **字段口径说明**：上面 19 项是导演设计稿的内部字段。
> 对外交付的**分镜头脚本 12 字段**及其取值规范、以及
> 19 字段 ↔ 12 字段 ↔ drama 15 行 / 15 列 ↔ 生成卡的四向映射表，
> 见 `references/17-storyboard-vs-shotlist-dual-output.md`。
> 进入 Open Dreamina 管线时须经该映射表投影，禁止直接改 `shots.md` 模板。