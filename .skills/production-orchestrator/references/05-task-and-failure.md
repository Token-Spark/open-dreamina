# 任务队列、失败处理与镜头重设计

> 对应 SKILL.md 索引中的 `references/05-task-and-failure.md`。
> 管理任务 / 处理失败时加载。包含：任务队列、失败处理、镜头重设计。

## 1. 任务队列（Task Queue）

优先级：

```text
URGENT（紧急）
HIGH（高）
NORMAL（普通）
LOW（低）
```

默认优先级：

```text
Hero / Hook 镜头       HIGH
重大揭示（Major Reveal） HIGH
悬念（Cliffhanger）     HIGH
角色资产（Character Asset） HIGH
场景资产（Location Asset）  HIGH
常规镜头（Normal Shot） NORMAL
插入镜头（Insert）       LOW
背景镜头（Background）   LOW
```

**依赖未解决的任务保持 `BLOCKED`。**

## 2. 失败处理（Failure Handling）

**绝不盲目重试。**

对每次失败：

1. 诊断失败（diagnose）。
2. 分类（classify）。
3. 应用最小且恰当的修正。
4. 重试（retry）。
5. 记录结果（record）。

失败类别：

```text
IDENTITY（身份）
ANATOMY（解剖/肢体）
COMPOSITION（构图）
MOTION（运动）
CONTINUITY（连续性）
PROMPT（Prompt 问题）
MODEL（模型问题）
REFERENCE（参考问题）
TECHNICAL（技术问题）
```

默认恢复序列：

```text
Retry 1 → 参数调整
Retry 2 → Prompt 简化
Retry 3 → 参考调整
Retry 4 → 换模型
Retry 5 → 镜头重设计
```

超过重试上限后：

```text
HUMAN_REVIEW（转人工审查）
```

**绝不无限生成。**

## 3. 镜头重设计（Shot Redesign）

镜头反复失败时，重设计生产方案，而非无休止重试。

转换方式：

```text
复杂镜头（Complex Shot）
    ↓
简单镜头 A（Simple Shot A）
简单镜头 B（Simple Shot B）
简单镜头 C（Simple Shot C）
    ↓
剪辑（Edit）
```

**保留导演的戏剧意图，同时降低生成复杂度。**

简化示例：

* 更少角色
* 更少同时进行的动作
* 更短时长
* 更简单的摄影机运动
* 静态摄影机代替复杂运动
* 图生视频代替文生视频
* 插入镜头代替复杂互动
