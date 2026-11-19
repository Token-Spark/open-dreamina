# 工作模式、输出格式与上下游接口

> 对应 SKILL.md 索引中的 `references/10-workflows-and-output.md`。
> 准备最终交付物或切换工作模式时加载。包含：导演台输出格式、每个 Shot 的最终生成卡、Agent 工作模式、与 Short Drama Creator 的接口。

## 1. 导演台输出格式

最终必须输出一个结构化 Shot Table：

| ID     | Scene | Beat | 镜头功能     | 景别 | 机位       | 运镜       | 人物动作 | 时长 | 台词    | 音效         | 生成        |
| ------ | ----- | ---- | ------------ | ---- | ---------- | ---------- | -------- | ---: | ------- | ------------ | ----------- |
| S01-01 | 01    | 01   | Establishing | ELS  | High Angle | Slow Push  | 城市运行 | 3s   | —       | 城市环境声   | Image+Video |
| S01-02 | 01    | 02   | 对白         | MCU  | Eye Level  | Static     | 女主抬头 | 4s   | "什么？" | 呼吸声       | Image+Video |
| S01-03 | 01    | 03   | 插入         | ECU  | Eye Level  | Static     | 手机亮起 | 2s   | —       | Notification | Image+Video |

> 本表是**导演台阅读视图**（给人快速核对镜头序列），列名语义固定：
> 镜头功能 / 景别 / 机位 / 运镜 / 人物动作，不要互相串列。
> 进入 Open Dreamina 管线时以 `drama-shotlist-spec.md` 的 15 列总览表为唯一机器口径，
> 字段投影关系见 `references/17-storyboard-vs-shotlist-dual-output.md` §4。

## 2. 每个 Shot 的最终生成卡

> `VIDEO PROMPT` 段按 `prompt-optimizer/references/02-prompt-templates.md` §3.4 九行模板写；
> 卡片其余字段（PURPOSE / COMPOSITION / LIGHTING / SFX / EDIT …）是导演内部阅读项，
> **不进入生成提示词**，也不许塞进九行模板当自创字段。

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
镜头功能：极特写，固定镜头
人物：CHAR-A(@char_a_ep01_turnaround，@voice_a)
场景描述：场景 loc_city_night（@scene_city_primary），道具(@prop_phone)
秒级动作拆解:
-[0-2s]手机屏幕突然亮起，冷光打亮周围；视线落在屏幕上
台词同步
-[0-2s]无
音效设计：无背景音乐；
基础环境音：远处交通低频；手机震动与屏幕亮度变化在 0.5s 处起
画面风格：（`--with-style` 时留空，由编译器追加全局常量）
特效音：通知提示音

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