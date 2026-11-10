# Drama Prompt Pattern — 短剧管线提示词模式

> 本文件是 prompt-optimizer 技能的短剧专章：当优化对象是「短剧管线内」的
> 镜头/素材提示词时，遵循管线的编译模式与锚点纪律，而不是通用六工位模板。

## 两种提示词的两套纪律

| 类型 | 来源 | 纪律 |
|---|---|---|
| 素材级提示词 | tools/assets_manifest.json 每资产 prompt | 六工位结构化（本技能通用模板适用）；primary 固定 seed；img2img 必须以 primary 为 ref |
| 镜头级提示词 | shots.md 15 行模板 → 编译 | **锚点逐字 + 中文映射翻译**；不要重新发明结构 |

## 镜头提示词的编译模式（8 段结构）

管线编译器（drama.compiler.prompt_compiler）按固定 8 段组装，人工精修保持同序：

1. 摄影语言（`A wide shot, high angle, slowly tilting down.`）
2. 角色锚点（`Character binding: Venus: <英文锚点逐字>.`）
3. 动作 + 表情（中文经映射表翻译，未命中即丢弃）
4. 场景锚点（`Scene: <英文逐字>. Keep the architecture... identical to the scene reference image.`）
5. 台词（`Spoken dialogue from Venus: "<逐字>"` / `Off-screen voice-over from ...`）
6. 不入画角色说明
7. 光感 + 色调（映射翻译，`colour palette: ...`）
8. 一致性锚句（`Keep the character's face, hair and clothing identical to the reference image.`）

精修原则：**最小化修改**——只改出问题的段，锚点段（2/4/5）逐字不动。

> 段 2 的角色锚点逐字取自 `shots.md` 人物行，所以**人物行只写身份项**（英文名 + 本镜身体 /
> 表演状态），不写服饰、发型、妆容。服饰由集内妆造三视图承载；写进人物行等于在 prompt 里
> 制造第二套事实，与参考图冲突（见下节与 `ai-video-director/references/21-episode-state-lock.md` §5）。

## 集内妆造锁定：只引用，不描述

妆造一经图片锁定（`char_{角色}_ep{xx}_{造型}_turnaround`），提示词**不得再写穿搭**：

| | 写法 |
|---|---|
| ✅ | `Keep the character's face, hair, makeup and costume exactly as in the reference image.` ＋ 本镜动作 |
| ❌ | `wearing a white cotton nightgown with a coffee stain on the left sleeve` |
| ❌ | 「同样的白裙，但更旧一点」——相对修饰同样触发重绘 |

纪律：

- 段 8 的一致性锚句逐字固定，**不追加服饰补语**（`...identical, with a silk scarf` 也算冲突）。
- 场景同理：陈设已由集内状态图锁定 → 只写「延续参考图的陈设与道具在场情况」，不重述「床边有输液架」。
- 唯一可写服饰的情形是本镜内的**变化过程**（撕破 / 染血 / 脱外套）：写「变化」不写「样式」，
  并在同镜或下一镜切到新状态锚点。
- 没有锁定图时不要用堆形容词代替锚点——先补集内妆造三视图。
- 参考与首帧只用 `*_turnaround`；**半身照 / 剧照 / 成片截帧 / 拼贴板不得作种子**。

## 全局风格四常量（逐字拼接，禁止改写）

每条镜头提示词尾部追加（`drama compile --with-style` 自动处理）：

- AESTHETIC（美学基调）/ MEDIUM（媒介质感）→ 正向尾部
- AUDIO（禁 BGM 的音频约定句式；具体四行填法见下方「音轨四行」与 `02-prompt-templates.md` §3.4）
- NEGATIVE → 负面提示词（text, watermark, logo, subtitles, 及 §4.5 音乐禁用词表 background music / score / pad / beat / melody 等）

要调风格 = 改 `tools/assets_manifest.json` 的 `style` 字段一处，先抽 1-2 镜验证再全量。

## 音轨四行（脚本层必补，独立于画面编译 8 段）

编译器 8 段负责摄影 / 角色 / 动作 / 场景 / 台词 / 光感 / 一致性；**声音由分镜表按固定四行逐镜实填**，
再编译为 AUDIO 正向段 + NEGATIVE 音乐词，分工不混写：

| 四行 | 填法 | 编译去向 |
|---|---|---|
| 音效设计 | 恒为「无背景音乐」＋无垫乐 / 旋律 / 节奏床 | AUDIO 正向段前置声明 |
| 基础环境音 | 必须实填（声源、秒段、电平，如暖灯嗡鸣、门缝夜风、远处被墙闷住的脚步） | AUDIO 段 diegetic ambience |
| 动作触发音 | 必须实填并绑定秒段（呼吸、布料、餐具、脚步、物体接触） | AUDIO 段 foley cue |
| 特效音 | 无则写「无」；有也仅限动作触发，不做情绪煽动音效 | 有则进 AUDIO，无则省略 |

纪律：

- **台词同期**：台词逐字进「台词同步」行（含说话人 / 语气 / 语速），由生成模型在同一次生成里出声并咬口型；
  后期只铺 BGM + 混音 + 字幕，**不做 TTS 配音、不做口型重对**。没出声 / 台词错 / 口型不对 → 改 prompt 重出，
  不得后期补。无台词镜写「无」并在负面词排除 `voiceover, dialogue, narration`。
- 生成轨＝台词人声 ＋ 基础环境音 ＋ 动作触发音；原创配乐（MUSIC IN / BUILD / OUT）只进后期轨，禁止回灌进生成 prompt。
- 无台词镜不得出现人声；单人情绪 / 验证片目标为近静音＋呼吸级底噪，仍须实填环境音与动作音，不得整体静音、也不得放配乐。
- 音乐 negative 词表用 `02-prompt-templates.md` §4.5；正向 AUDIO 句式模板用同文件 §3.4；CLI/工具没有选择性禁乐开关（`generate_audio` 只控制整条音轨有无），双通道（正向前置＋负向点名乐种）缺一不可。
- 分镜表既有口径「生成轨＝人声＋基础环境音＋动作触发音，原创配乐只进后期轨」为权威，编译与人工精修均不得违背。

## 中英映射纪律（管线特有）

- 中文视觉描述（表情/光感/色调/环境/动作）必须命中 `tools/maps.py` 词库才进入英文提示词
- 未命中 → 该描述被丢弃（宁缺勿错，绝不机翻污染）
- 优化时发现「情绪没演出」先查：是不是词库未命中？回填词库比重roll有效得多
- 兜底护栏：任何中文不得出现在最终英文提示词中

## 调用工具链而非手写

```bash
opendreamina drama compile EP05 --shot S08 --with-style   # 编译基线
opendreamina drama lint EP05                              # 改分镜后守门
```

单镜重roll 参数基线：Seedance 720p / 9:16 / `--frame-mode reference` /
参考 = 三视图（本集妆造版 `*_ep{xx}_..._turnaround`）+ 场景图（有集内陈设变化时用
`scene_*_ep{xx}_{状态}`）+ 音色；半身照、剧照、成片截帧不得作种子。
先 `opendreamina providers` / `get_health` 确认环境。

## 与通用模式的分工

本技能通用六工位模板（主体/场景/光线/镜头/风格/质感）适用于：
素材级 prompt、管线外的单图/单视频生成。管线内的镜头提示词一律走编译模式。
