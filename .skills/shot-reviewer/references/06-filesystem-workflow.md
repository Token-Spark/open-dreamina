# 离线文件审片（Filesystem Workflow）

> 对应 SKILL.md 索引中的 `references/06-filesystem-workflow.md`。
> 用户直接给视频目录、或后端不可用时加载。包含：目录约定、shots.md 解析、看片与抽帧、报告输出。
> 解析规则与后端 `backend/app/services/shot_script_meta.py` 对齐——你解析出的元数据应与审片中心的条目一致。

## 1. 剧集目录约定（真实结构）

```text
<剧集根>/
├── 00_分镜总索引.md
├── review_brief.md              ← 剧目审片规范（references/03；可能有）
├── EP01/
│   ├── shots.md                 ← 分镜脚本（「应有」的唯一权威来源）
│   └── video_renders/
│       ├── S01_seedance20/      ← 同镜一版（目录名常含模型名 → 版本标识）
│       │   └── <uuid>_0.mp4
│       └── S01_klingv2/         ← 同镜另一版 → 多版本镜头
├── EP02/ …
```

* 视频可在任意层级，**递归收集** `.mp4 .mov .webm .mkv .avi .flv`。
* **跳过 `_` 开头目录**（`_model_compare`、`_superseded_*` 等辅助产物）——与后端扫描口径一致。
* 集号/镜号解析：路径或文件名中 `EP(\d+)[-_]S(\d+)`（优先）或裸 `S(\d+)`；镜号归一化为 `S01` 两位数字形态。
* 解析不到镜号的视频仍要审，shot_id 记 `S??` 并注明。

## 2. shots.md 解析要点

只提取真实存在的字段，缺失一律记 None，绝不臆造（与后端同一原则）。

**头部（剧目级素材，喂给 brief 定制，见 03 第 5 节）**：

* `> 集时长目标：90s（±10%…）｜总镜头数：…` —— 时长基准
* `画幅：…｜语言：…｜质感：…` —— 技术与风格基准
* `硬性约束：无背景音乐；无字幕；无 Logo…` —— 直接转为剧目红线
* `AESTHETIC / MEDIUM / AUDIO / NEGATIVE = …` 全局风格常量 —— 精修提示词必须原样保留

**总览表**（列序固定）：

```text
| EP01-S01 | 4 | wide | high-angle | slow-tilt-down | … |
   镜号       时长  景别     角度          运镜
```

**镜小节** `## EP01-S01` 下的字段行：

`**镜头功能：**`、`**人物：**`、`**场景描述：**`、`**秒级动作拆解：**`（bullet 行是动作与运镜的逐秒依据）、`**台词同步：**`（含 `台词："…"` 引文）、`**光感：**`、`**色调：**`、`**构图：**`、`**细节：**`、`**音效设计：**`。

提示词底稿 = 人物/场景描述/台词同步/光感/色调/构图/细节 + 秒级动作拆解的原文拼接（即后端 `source_prompt` 的构成）；写精修提示词时以它为底稿。

## 3. 建立「应有 vs 实际」对照清单

```text
for 每个 EP 目录:
    meta = parse(shots.md)                    # {S01: {镜头功能, 时长, 景别, 运镜, 台词, 提示词底稿}}
    videos = collect(EP/**/*.{mp4,…}, skip _*)
    for video: 按 Sxx 归组 → 对照清单 {episode, shot_id, 版本(子目录名), file, 应有: meta[Sxx]}
```

生成报告文件名（`generation_report*.json` / `production_manifest.json`，在 `video_renders/` 下）可补充 `render_status / model / render_duration_s`；没有就跳过。

## 4. 看片方法

### 方式 A：直接读视频（优先）

执行环境支持视频输入时（如 ZCode 的 Read 工具可直接读 mp4），**直接读原文件看片**；多版本镜头逐版本读。这是证据质量最高的方式。

### 方式 B：ffmpeg 抽帧（环境不支持视频输入 / 需要精确定位时）

```bash
# 技术元数据（分辨率/时长/帧率/音轨）——一次拿全
ffprobe -v quiet -print_format json -show_format -show_streams "<video>"

# 抽帧（缩到 640 宽足够辨瑕疵，控制上下文体积）
T=$(mktemp -d)
ffmpeg -loglevel error -ss 0.2    -i "<video>" -frames:v 1 -vf scale=640:-1 "$T/f_first.jpg"
ffmpeg -loglevel error -ss <dur/2> -i "<video>" -frames:v 1 -vf scale=640:-1 "$T/f_mid.jpg"
ffmpeg -loglevel error -sseof -0.3 -i "<video>" -frames:v 1 -vf scale=640:-1 "$T/f_last.jpg"
# 动作/闪烁类问题按每 1–2s 采样补帧；台词镜、手部动作镜加密采样

# 音轨检查（brief 有音频要求时）
ffprobe -v quiet -select_streams a -show_entries stream=codec_name,channels "<video>"
ffmpeg -i "<video>" -af volumedetect -f null - 2>&1 | grep -E "mean_volume|max_volume"
```

抽帧纪律（强制规则 2）：帧图放 `mktemp -d` 系统临时目录；审完即弃；**绝不写进素材目录**。

### 采样密度

| 镜头类型 | 最低采样 |
|---|---|
| 静态/慢镜头 | 首/中/尾 3 帧 |
| 动作镜 | 每 1–2s 一帧 + 首/中/尾 |
| 台词镜 | 每 1s 一帧（盯口型与面部稳定） |
| 多版本对比 | 各版本同密度，重点帧对齐同一时间点 |

## 5. 结果输出

输出目录：素材目录**之外**（默认 `./shot-review-output/<剧名>-<YYYYMMDD>/`，用户可指定）。两个产物：

### `shot-review-results.json`（机器可读）

```json
{
  "brief": {"path": "review_brief.md", "version": "v1", "source": "user-provided"},
  "generated_at": "2026-09-28T12:00:00",
  "source_root": "/abs/path/to/剧集根",
  "items": [
    {
      "episode": "EP01", "shot_id": "S01", "version": "seedance20",
      "file_path": "EP01/video_renders/S01_seedance20/xxx_0.mp4",
      "score": 72, "verdict": "pass",
      "dimensions": {"D1": 80, "D2": 90, "D3": 70, "D4": 60, "D5": 65, "D6": 70},
      "weights_used": {"D1": 25, "D2": 20, "D3": 15, "D4": 15, "D5": 15, "D6": 10},
      "feedback": "【通过】…", "revised_prompt": null,
      "recommend_keep": true, "needs_human_review": false
    }
  ],
  "summary": {"pass": 0, "revise": 0, "redesign": 0, "pending": 0, "average_score": null},
  "notes": ["无对照降级说明", "规范应用说明"]
}
```

> `weights_used` 必须落盘：让复现者知道这次用了哪把尺子。无对照维度从 `dimensions` 中省略并写入 notes。

### `shot-review-report.md`（人读）

按 `references/04-scoring-and-feedback.md` 第 5 节的汇总格式输出。

## 6. 降级与边界

* 无 shots.md → 无对照审片（01 第 2 节），D1/D6 摊权，notes 注明。
* 视频损坏/抽帧全黑 → 该镜 pending，feedback 写 `【无法审片】原因`。
* 目录混入非剧集素材（无 EP/S 结构）→ 先与用户确认审片范围，不要硬解析。
* 素材目录只读纪律：全程不写、不删、不改名（强制规则 8/10）。
