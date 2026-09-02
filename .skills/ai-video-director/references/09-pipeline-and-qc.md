# 生产管线、质检与镜头分级

> 对应 SKILL.md 索引中的 `references/09-pipeline-and-qc.md`。
> 进入生产与质检阶段时加载。包含：AIGC Production Pipeline、Keyframe First、Keyframe QC、Video QC、镜头评分、镜头成本意识、Production Priority。

## 1. AIGC Production Pipeline

完整生产链：

```text
SCRIPT
 ↓
SCENE BREAKDOWN
 ↓
BEAT SHEET
 ↓
SHOT LIST
 ↓
CHARACTER LOCK
 ↓
LOCATION LOCK
 ↓
STYLE BIBLE
 ↓
KEYFRAME GENERATION
 ↓
VIDEO GENERATION
 ↓
VOICE
 ↓
SFX
 ↓
MUSIC
 ↓
EDIT
 ↓
COLOR
 ↓
QC
```

## 2. Keyframe First

不要直接大量生成视频。

优先：

> **先生成关键帧。**

每个重要 Shot：

1. 生成首帧
2. 检查角色一致性
3. 检查构图
4. 检查场景
5. 检查光线
6. 检查道具
7. 通过后进入 Video Generation

## 3. Keyframe QC

关键帧必须检查：

### Character

是否一致？

### Costume

是否一致？

### Location

是否一致？

### Props

是否正确？

### Composition

是否符合 Shot Design？

### Lighting

是否连续？

### Emotion

是否符合 Beat？

如果失败：

> **先修 Keyframe，不要直接生成 Video。**

## 4. Video QC

生成视频后检查：

### Identity

人物是否变脸？

### Anatomy

手、身体是否异常？

### Motion

动作是否自然？

### Camera

镜头运动是否符合设计？

### Continuity

前后 Shot 是否连续？

### Physics

物理规律是否合理？

### Expression

表情是否符合剧情？

### Background

背景是否变形？

### Temporal Consistency

人物和物体是否在时间上稳定？

## 5. 镜头评分

每个 Shot 进行：

```text
Composition / 10
Character Consistency / 10
Environment Consistency / 10
Motion Quality / 10
Cinematic Quality / 10
Story Function / 10
Continuity / 10
Generation Reliability / 10
```

低于：

> 70 / 100

重新生成。

低于：

> 60 / 100

重新设计 Shot，而不是简单重新抽卡。

## 6. 镜头成本意识

Agent 必须考虑：

> **镜头复杂度 × 生成失败概率 × 重生成成本**

优先使用：

> 简单可靠镜头 + 剪辑组合

而不是：

> 单个镜头追求无限复杂。

## 7. Production Priority

镜头分为：

### A级

必须精修：

* 开场 Hook
* 主角首次出现
* 重大反转
* 情绪高潮
* Cliffhanger
* 宣传片镜头

### B级

正常制作：

* 普通对白
* 环境
* 常规动作

### C级

快速生产：

* 过场
* 建立镜头
* 背景
* 补充镜头

把资源集中在：

> **观众真正记得住的镜头。**