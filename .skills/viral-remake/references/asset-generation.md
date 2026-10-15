# 素材生产与组装对接（即梦管线）

执行 STEP 6–8 的具体做法。所有生成动作通过 `dreamina-canvas` CLI 完成——**执行前先读该技能的 SKILL.md，用 `schema` / `model list` / `voice list` 拿实时事实，禁止凭记忆编 flag 或模型名**。

## 1. 各系统的生产手段

| 系统 | 首选 | 备选 | 要点 |
|---|---|---|---|
| A-roll | **多模态参考视频**（参考片段作运动/构图参考）+ 新主体提示词 | 文生视频（首尾帧控制转场） | 复刻运镜的首选；参考片段仅作运动参考，画面内容全部换新，规避版权 |
| B-roll | 文生图（2K）→ 图生视频（3–5s） | 直接文生视频 | 静帧先行，先过审再动起来，省成本 |
| 人像 | anchor-portrait（复用 drama 素材库规范） | 用户照片作参考图 | 换主体透镜的一致性方案 |
| 配音 | 即梦 TTS 逐句生成，`voice list` 选音色，`--voice-name` 原样传入 | — | **逐句生成**：句音频时长 = 字幕/切镜锚点；语气用 TONE_MAP 思路编译 |
| 音乐 | 即梦音乐生成（model list 选含 music mode 的模型） | 用户自有授权 BGM | 生成前确认授权归属 |
| Caption/Typography | ffmpeg drawtext / ASS 烧录 | — | 时间来自句音频时长；关键词变色用 ASS 内联标签 |
| MG | Pillow/HTML 渲染静帧 + ffmpeg 动效 | 文生图 | 榜单/条图类不必上生成模型 |
| Effects | ffmpeg（zoompan / fade / setpts / 闪白） | — | 代码特效零成本，优先于生成 |

## 2. 生产顺序（省钱且可回滚）

```
配音（全句）→ 校验总时长 vs BRIEF ±15% → 静帧 B-roll 批产 → A-roll 批产 → 组装
```

1. **配音先行**：TTS 最便宜，句时长定下整个时间线的骨架。总时长超差时先改脚本（回 STEP 6），不要先产视频。
2. **静帧过审**：B-roll 与 A-roll 关键帧先出图，用户/Agent 走查风格一致性，再批量图生视频。
3. **A-roll 最后**：最贵，等脚本、音色、风格全部锁死。

## 3. 提示词编译

- 复用 drama 的中英词库模式：项目级映射表（人物/场景/风格/语气），中文结构化描述 → 英文提示词；未命中词条先回填再编译。
- 语气/delivery：复用 TONE_MAP——台词语气标注（急促/低语/上扬…）编译为英文 delivery 指令。
- 全局风格段（透镜 6 的决定）写入项目 assets manifest，每条生成提示词拼接，保证风格一致。

## 4. 组装（ffmpeg）

按 remake_plan 的 timeline 执行，伪流程：

```bash
# 1. 视频轨：按锚点顺序拼接 A-roll/B-roll（每段时长=对应句子音频时长或事件窗长）
ffmpeg -i seg01.mp4 -i seg02.mp4 ... -filter_complex "concat=n=N:v=1:a=0" video_track.mp4
# 2. 音轨：逐句配音 concat + BGM 压低混入
ffmpeg -i voice_full.wav -i bgm.wav -filter_complex "[1:a]volume=0.15[bg];[0:a][bg]amix" audio_track.m4a
# 3. 字幕：句时间码 → SRT/ASS → 烧录（drawtext 逐条或 subtitles=cap.ass）
ffmpeg -i video_track.mp4 -i audio_track.m4a -vf "ass=captions.ass" -c:v libx264 -c:a copy final.mp4
```

- 句时间码生成：由逐句音频实际时长累加（ffprobe 逐句量），偏移零累计误差。
- 成片落 `productions/{slug}/runs/{批号}/final.mp4`；qc 抽帧同目录。
- 组装脚本可复用：同 plan 换素材目录即得变体（这是批量变体的机制基础）。

## 5. 验收与登记

1. **技术验收**：复用 `drama qc` 思路——画幅/时长/音轨逐项核对 plan.target；ffprobe 缺失如实降级并人工抽帧兜底。
2. **内容验收**：每段至少 1 帧走查 + 完整观看（Done means watched）。
3. **登记**：每条素材的 asset_id 回写 remake_plan.assets；无登记的文件视为废稿清理前先问用户。
4. **审阅中心**：项目在 `data/review_sources/` 下即被素材审阅扫描；镜头视频按 drama 的 `分镜脚本/EPxx/video_renders/` 惯例摆放可进镜头审片。
5. **变体批产**：母片过审后，同一 remake_plan 换轴（脚本行/人像参考/B-roll 提示词）批量执行；每变体独立 runs/{批号}，共享配音缓存与参考档案。
