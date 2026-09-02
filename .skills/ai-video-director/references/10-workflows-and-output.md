# 工作模式、输出格式与上下游接口

> 对应 SKILL.md 索引中的 `references/10-workflows-and-output.md`。
> 准备最终交付物或切换工作模式时加载。包含：导演台输出格式、每个 Shot 的最终生成卡、Agent 工作模式、与 Short Drama Creator 的接口。

## 1. 导演台输出格式

最终必须输出一个结构化 Shot Table：

| ID     | Scene | Beat | Shot         | 景别        | 镜头        | 动作   | 时长 | 台词           | 音效          | 生成          |
| ------ | ----- | ---- | ------------ | --------- | --------- | ---- | -: | ------------ | ----------- | ----------- |
| S01-01 | 01    | 01   | Establishing | ELS       | Slow Push | 城市运行 | 3s | —            | 城市环境声       | Image+Video |
| S01-02 | 01    | 02   | MCU          | Eye Level | Static    | 女主抬头 | 4s | "什么？"        | 呼吸声         | Image+Video |
| S01-03 | 01    | 03   | ECU          | Static    | 手机亮起      | 2s   |  — | Notification | Image+Video |             |

## 2. 每个 Shot 的最终生成卡

每个镜头最终输出：

```text
SHOT ID:
S01-03

PURPOSE:
Reveal the survival countdown.

CHARACTER:
CHAR-A

LOCATION:
LOC-CITY-01

DURATION:
2 seconds

SHOT:
ECU

COMPOSITION:
Phone fills the frame,
shallow depth of field.

ACTION:
Screen suddenly illuminates.

CAMERA:
Static macro close-up.

LIGHTING:
Dark environment,
cold screen glow.

IMAGE PROMPT:
[完整图片生成 Prompt]

VIDEO PROMPT:
[完整视频生成 Prompt]

NEGATIVE:
[Negative Prompt]

SFX:
Notification ping.

MUSIC:
Music stops.

EDIT:
Smash cut to black.
```

## 3. Agent 工作模式

用户可以调用以下模式：

### MODE A — Script → Storyboard

输入剧本。

输出：

> Scene + Beat + Shot

### MODE B — Storyboard → Image Prompt

输入 Shot List。

输出：

> 每个镜头的 Keyframe Prompt。

### MODE C — Image → Video Prompt

输入 Keyframe。

输出：

> Video Motion Prompt。

### MODE D — Episode → Full Production Plan

输出：

> Scene → Shot → Image → Video → Audio → Edit

### MODE E — Continuity Check

检查：

> 人物 / 场景 / 道具 / 时间 / 光线 / 动作

### MODE F — Shot Optimization

如果某个镜头 AI 很难生成：

> 自动拆分成更可靠的多个 Shot。

## 4. 与 Short Drama Creator 的接口

上游：

```text
short-drama-creator
```

负责：

> Story
> Character
> Conflict
> Emotion
> Suspense
> Episode
> Scene

下游：

```text
ai-video-director
```

负责：

> Beat
> Shot
> Camera
> Composition
> Keyframe
> Motion
> Sound
> Editing
> Generation Prompt
> QC

接口关系：

```text
          STORY
            ↓
   SHORT DRAMA CREATOR
            ↓
      SCREENPLAY
            ↓
    AI VIDEO DIRECTOR
            ↓
      SCENE / BEAT
            ↓
          SHOT
            ↓
        KEYFRAME
            ↓
       VIDEO SHOT
            ↓
       AUDIO / SFX
            ↓
         EDITING
            ↓
       FINAL EPISODE
```