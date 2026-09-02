# Prompt 架构与视频运动设计

> 对应 SKILL.md 索引中的 `references/06-prompt-architecture.md`。
> 为镜头编写生成 Prompt 时加载。包含：Prompt 架构、Image/Video Prompt 分离、Video Motion Design。

## 1. Prompt Architecture

不要直接生成一大段随机 Prompt。

采用：

> **[Style] + [Character] + [Location] + [Composition] + [Action] + [Camera] + [Lighting] + [Atmosphere]**

例如：

```text
STYLE:
cinematic science fiction thriller,
photorealistic,
high-end film production

CHARACTER:
CHAR-A,
young female scientist,
short black hair,
white research coat

LOCATION:
LOC-HOSPITAL-01

COMPOSITION:
medium close-up,
character positioned on right third,
large negative space

ACTION:
she slowly turns toward the emergency door,
eyes widening

CAMERA:
50mm lens,
eye-level,
slow push-in

LIGHT:
cold fluorescent light,
red emergency reflections

ATMOSPHERE:
quiet,
claustrophobic,
ominous,
subtle film grain
```

## 2. Image Prompt 与 Video Prompt 必须分离

### Image Prompt

重点：

> **画面是什么**

包括：

* 人物
* 场景
* 构图
* 光线
* 风格

### Video Prompt

重点：

> **画面如何变化**

包括：

* 人物动作
* 摄影机运动
* 环境变化
* 情绪变化
* 时间变化

禁止简单复制 Image Prompt。

## 3. Video Motion Design

每一个视频 Shot 必须明确：

```text
Initial State
Action
Camera Motion
Environmental Motion
End State
```

例如：

> Initial State:
> 女主站在手术室门前。

> Action:
> 她缓慢抬起右手。

> Camera:
> Camera slowly pushes in.

> Environment:
> 红色警报灯持续闪烁。

> End State:
> 她的手停在门锁上。

这样比：

> "cinematic dramatic movement"

更适合视频模型。