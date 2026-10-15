# 翻拍工作流（8 步详细标准）

每一步定义：做什么、产出什么、何时可以进入下一步。

## STEP 1 立项 Brief

**做什么**：与用户对齐翻拍目标，落盘 `productions/{slug}/BRIEF.md`。

必须包含：
- 参考视频来源（链接/文件路径）与目标平台（抖音/快手/视频号/TikTok）
- 画幅与时长硬约束（9:16 / 16:9；参考时长 ±20% 内优先）
- **替换清单**：换什么主体/产品/脚本/语言/品牌（未明确的逐项追问，禁止替用户假设卖点）
- 预算共识：预计生成条数（A-roll/B-roll/人像）与用户确认

**验收**：BRIEF.md 落盘；替换清单每项有明确答案或"沿用参考"标记。

## STEP 2 建参考档案

**做什么**：为参考视频建立 `references/{slug}/` 档案（见 `reference-analysis.md`）。

最低要求：
- `source.mp4` 就位（下载或用户文件复制；记录来源 URL）
- 技术元数据：时长/画幅/帧率/音轨（ffprobe；缺失时如实记录"未知"）
- 证据帧 ≥ 8 张，覆盖开头钩子、每个节奏转折、结尾 CTA
- `transcript.md`：优先用户粘贴/授权转录；没有则先做"无转录降级"（静音分段 + 画面解读，词锚定降级为段锚定，TREATMENT 中注明风险）

**验收**：evidence/ 有帧，transcript.md 与元数据落盘。

## STEP 3 精读分析 → ANALYSIS.md

回答三个问题（写法详见 `reference-analysis.md`）：
1. **钩子**：前 3 秒凭什么让人停下？（冲突/悬念/身份认同/视觉奇观）
2. **论证**：主体怎么展开？（信息顺序、情绪曲线、爆点位置）
3. **系统**：7 大视觉系统（A-roll/B-roll/Caption/Typography/MG/Effects/Sound）各自承担什么功能？

每条结论标注 `[证据]`（附时间码/帧文件名）或 `[解读]`。

**验收**：三大问题有着落；至少 5 条 `[证据]` 级观察。

## STEP 4 编制时间线 → TIMELINE.md

把参考视频切成段落（段界优先取**静音边界与镜头切换**的重合点），每段记录：

| 字段 | 说明 |
|---|---|
| 时间码 | 起止（来自证据，不是估计） |
| 台词锚 | 该段绑定的原词短语（有转录时） |
| 事件 | 镜头切换/字幕出现/特效/B-roll 进出/声音变化 |
| 功能 | 该段在叙事中的角色（钩子/铺垫/爆点/CTA…） |
| 系统 | 涉及哪些视觉系统 |

**验收**：段落连续覆盖全片；每段有功能标注；事件可指到证据帧。

## STEP 5 Treatment（变换透镜过检）

逐项过 `transformation-lenses.md` 的 8 个透镜，落盘 `TREATMENT.md`：
- **保留**：结构骨架、节奏曲线、系统分工、钩子机制
- **替换**：每项透镜的明确决定（换主体/换产品/换脚本/换平台规格…）
- **风险**：词锚定降级（无转录）、参考中受版权保护元素的规避方案

**验收**：8 个透镜每项有"保留/替换"结论；用户确认 TREATMENT 后才进生产。

## STEP 6 新脚本与规格

- 写 `transcript_target.md`：新台词。**句子边界即未来的配音与字幕锚点**，按可独立配音的短句分行；语气标注复用 drama 的 TONE_MAP 思路。
- 写 `remake_plan.json`：机器可执行规格，结构对齐 drama 的 episode_spec 思路（数据与机制分离）：

```jsonc
{
  "target": { "platform": "douyin", "aspect": "9:16", "target_duration_sec": 45 },
  "audio":  { "voice_name": "<voice list 查得>", "lines": [ { "id": "L1", "text": "...", "tone": "..." } ] },
  "timeline": [ { "anchor_line": "L1", "system": "a-roll", "action": "shot-01 进",
                  "asset_ref": "素材库/a_roll/shot_01.mp4", "notes": "" } ],
  "assets": [ { "id": "shot_01", "type": "video", "prompt_zh": "...", "prompt_en": "...",
                "status": "pending", "asset_id": null } ]
}
```

**校验（人工执行，未来由 `remake lint` 承担）**：
- 每个 timeline 事件的 `anchor_line` 存在于 lines
- 每个 `asset_ref` 在 assets 中登记（无登记不引用）
- lines 覆盖 BRIEF 替换清单中的全部新内容
- 预估总时长 = Σ TTS 句时长（生成后回填校验，偏差 >15% 回到 STEP 6 调整）

**验收**：校验全过；用户对脚本签字确认。

## STEP 7 素材生产与组装

按 `asset-generation.md` 执行。要点：
- A-roll 优先用**多模态参考视频**（参考片段保运镜/构图）
- 配音逐句 TTS，**句音频时长回填为字幕与切镜的词锚**（这是无转录词级对齐的替代方案）
- 组装：ffmpeg 按时间线 concat + drawtext 字幕 + amix 混音；成品落 `runs/{批号}/`
- 生成中每条素材登记 asset_id 到 plan 的 assets

**验收**：所有 assets status=done 且有 asset_id；成片产出。

## STEP 8 验收与变体

1. **技术验收**：画幅/时长/音轨（复用 `drama qc` 思路；ffprobe 缺失如实降级）
2. **内容验收**：抽帧走查（每段至少 1 帧）+ 完整看一遍成品（Done means watched）
3. **人工过审**：成片与镜头素材进审阅中心；有修改意见回到 STEP 6/7 对应环节
4. **批量变体（可选，用户明确要求后）**：母片过审后，按透镜换轴（换脚本/换人像/换 B-roll/换语言）批量执行；每变体独立 PROGRESS，共享同一参考档案

## 中断与恢复

任何一步中断，更新 `PROGRESS.md`：当前问题 / 已完成 / 下一步。新会话从 PROGRESS.md 恢复，禁止凭记忆续作。
