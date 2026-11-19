# 导演原则、最终验收与最终目标

> 对应 SKILL.md 索引中的 `references/11-principles-and-acceptance.md`。
> 一集完成后、交付前加载。包含：最重要的导演原则、最终验收、最终目标。

## 1. 最重要的导演原则

始终遵循：

> **Don't generate what you cannot control.**

不要因为 AI 能生成某个东西，就让镜头变得复杂。

优先：

> 可控构图

> 可控动作

> 可控角色

> 可控镜头

> 可控连续性

> 可控剪辑

## 2. 最终验收

一集完成后，必须进行：

### STORY QC

故事是否被正确表达？

### DRAMA QC

戏剧冲突是否清晰？

### VISUAL QC

画面是否有视觉吸引力？

### CHARACTER QC

人物是否一致？

### CONTINUITY QC

镜头之间是否连续？

### MOTION QC

动作是否自然？

### AUDIO QC

声音是否支持情绪？

### EDIT QC

剪辑是否有节奏？

### AIGC QC

是否存在明显 AI 瑕疵？

### RETENTION QC

Hook、高潮、Cliffhanger 是否成立？

最终输出：

```text
Production Score: XX/100

Story: XX
Drama: XX
Visual: XX
Character: XX
Continuity: XX
Motion: XX
Audio: XX
Editing: XX
AIGC Quality: XX
Retention: XX
```

如果：

> Production Score < 80

不得直接进入最终交付。

> 这是**集级**验收：10 维 × 10 = 100。它与 `09` §5 的单镜 8 维自检（满分 80，换算百分制）、
> `shot-reviewer` 的六维初审（PASS=70 / REVISE=60）是三道不同的门，**分数不可互推**：
> 单镜 PASS 不等于整集 ≥80（集级还看故事、剪辑、留存），自检 70 也不等于初审 70。
> 分工见 `09` §5「三把尺」。管线内对外口径只有 `shot-reviewer` 六维。

必须执行：

> Diagnose → Redesign → Regenerate → QC

## 3. 最终目标

这个 Skill 的最终目标不是：

> "生成漂亮的 AI 视频。"

而是：

> **让每一个镜头都服务于故事。**

最终形成：

> **剧本驱动镜头，镜头驱动生成，生成服务剪辑，剪辑服务观众留存。**

整个系统最终应该形成：

```text
          ┌──────────────────┐
          │  SHORT DRAMA     │
          │  CREATOR         │
          └────────┬─────────┘
                   │
                   ▼
             SCREENPLAY
                   │
                   ▼
          ┌──────────────────┐
          │  AI VIDEO        │
          │  DIRECTOR        │
          └────────┬─────────┘
                   │
          ┌────────┼────────┐
          ▼        ▼        ▼
       STORYBOARD  ASSET   SHOT
                   │        │
                   ▼        ▼
              KEYFRAME   PROMPT
                   │        │
                   └────┬───┘
                        ▼
                 VIDEO GENERATION
        （先合组：连拍组一次多镜 ≤30s）
                        │
        AUDIO 随视频同期产出：台词＋环境音＋
        动作触发音；不做后期配音，生成期禁 BGM
                        ▼
              EDIT / BGM 铺设 / 混音 / 字幕
                        ▼
                  FINAL EPISODE
                        ▼
                       QC
              ┌─────────┴─────────┐
              ▼                   ▼
       shot-reviewer           drama qc
       （六维初审，回写          （画幅/时长/音轨
         审片中心）               技术验收）
              └─────────┬─────────┘
                        ▼
                    人工终审
                   ┌────┴────┐
                   ▼         ▼
                PASS       FAIL
                   │         │
                   ▼         ▼
                EXPORT   REDESIGN / 返修
```

**核心理念：**

> **短剧 Agent 负责"为什么拍"。**

> **导演 Agent 负责"拍什么"。**

> **生成 Agent 负责"怎么生成"。**

> **审片 Agent 负责"这条能不能用"。**

> **剪辑 Agent 负责"怎么让它成为一集真正的短剧"。**