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

## 全局风格四常量（逐字拼接，禁止改写）

每条镜头提示词尾部追加（`drama compile --with-style` 自动处理）：

- AESTHETIC（美学基调）/ MEDIUM（媒介质感）→ 正向尾部
- AUDIO（禁 BGM 的音频约定句式）
- NEGATIVE → 负面提示词（text, watermark, logo, subtitles, background music, ...）

要调风格 = 改 `tools/assets_manifest.json` 的 `style` 字段一处，先抽 1-2 镜验证再全量。

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
参考 = 三视图 + 场景图 + 音色；先 `opendreamina providers` / `get_health` 确认环境。

## 与通用模式的分工

本技能通用六工位模板（主体/场景/光线/镜头/风格/质感）适用于：
素材级 prompt、管线外的单图/单视频生成。管线内的镜头提示词一律走编译模式。
