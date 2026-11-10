# Drama Execution — 短剧项目制片执行专章

> 本文件是 production-orchestrator 技能的短剧专章：当生产对象是 Open Dreamina
> 短剧管线中的剧集时，执行层复用管线工具链与数据契约，不再自建登记表。

## 数据契约（管线已定义，直接消费）

| 数据 | 位置 | 说明 |
|---|---|---|
| 分镜脚本 | `分镜脚本/EPxx/shots.md` | 唯一权威数据源（导演产出，lint 已通过） |
| 资产清单 | `tools/assets_manifest.json` | 资产 prompt/seed/一致性策略/全局风格 |
| 音色清单 | `tools/voice_manifest.json` | 角色 → 生成期同期台词的音色参考（画外音 TTS 选角同用，不做台词后期配音） |
| 平台注册表 | `tools/asset_registry.json` | 资产 id → 平台 asset_id |
| 分集规格 | `tools/episode_specs/EPxx.json` | 每集的生成执行输入（本技能维护） |
| 项目映射表 | `tools/maps.py` | 中英词库（编译器消费） |

## 命令路径（替代手写登记脚本）

```bash
# 1. 分镜守门（导演交付后第一步）
opendreamina drama lint EPxx --project .          # errors=0 才继续

# 2. 资产落位：清单缺口 → 素材生产 → 上传注册
opendreamina drama assets EPxx --project .        # 缺平台 asset_id 的资产即缺口
opendreamina upload <素材文件>                     # → asset_id，回写 asset_registry
opendreamina audit <asset_id> --provider sparkhub-seedance   # 需要时提审

# 3. 提示词编译（映射表 + 锚点逐字复用）
opendreamina drama compile EPxx --project . --with-style

# 4. 分集规格落盘（数据/机制分离：spec 描述「生成什么」）
opendreamina drama spec EPxx --project . --write --force

# 5. 批量生成（按 spec 逐镜）
#    refs（图片+音色）→ --reference；prompt + style → --prompt
#    --frame-mode reference 必须显式传：不传会落回首帧模式，只用第一张图
opendreamina image2video --provider sparkhub-seedance \
    --reference <三视图> --reference <场景图> --reference <音色> \
    --frame-mode reference \
    --prompt "<spec prompt + 风格常量>" --aspect-ratio 9:16 --auto-wait \
    --download-dir "分镜脚本/EPxx/video_renders/S01_seedance20/"

> **锚点类资产不在 spec refs 里**：`rel_*` / `loc_*` 被资产 ID 白名单静默过滤，
> `drama spec` / `drama assets` 看不到它们。编排层须按 `shot-design.md` sidecar
> 手工追加 `--reference-asset <asset_id>`；代码事实与完整命令见
> `ai-video-director/references/19-relationship-keyframe.md` §8。

# 6. 技术验收
opendreamina drama qc EPxx --project .
```

**编组执行**：sidecar 里排了连拍组（`TG01 = S01–S03`）时，上面对 spec 的逐镜调用合并成**一次**，
`--duration` 用组总长，`--prompt` 用镜段式结构（`Shot 1 (0-6s)… HARD CUT Shot 2…`），
`--download-dir` 指到 `video_renders/_takes/`；拿到母版后按时间码裁成 S01/S02/S03 三个文件再落各自目录。
提示词拼装见 `ai-video-director/references/23-take-group-multi-shot.md` §4，裁切见 §7。

## 生成参数基线（Seedance）

- provider/model：项目 manifest 的 `provider`/`model`（如 sparkhub-seedance + doubao_seedance_2）
- 720p / 9:16 / `--frame-mode reference`（默认且必须显式传）；单镜创作建议 ≤6s、lint 硬区间 2–8s（见 `ai-video-director/references/drama-shotlist-spec.md`），4–8s 仅为 Seedance 参数窗口，不是创作约束
- **任务粒度：先合组，再逐镜**。同场同时段的连续镜头按 sidecar 连拍组表合并为一次生成
  （Seedance 2.5 单任务 ≤30s，组内 2–4 镜，推荐 12–20s）；`--duration` 显式给**组总长**
  （= 各镜时长之和），不传会落默认 5s。判据与提示词结构见
  `ai-video-director/references/23-take-group-multi-shot.md`；`episode_spec` 结构不变（仍逐镜 `shots[]`），
  编组是执行层的合并调用，不是 spec 变更
- 参考绑定纪律：人物 = `*_turnaround`（本集妆造版），场景 = primary/interior 或 `scene_*_ep{xx}_{状态}`，音色 = anchor-voice；锚点 = `rel_*` / `loc_*` 的 asset_id（走 sidecar 手工追加，不进 spec refs）。**组内整组共用同一版本参考**
- **模式纪律**：默认全能参考 `reference`；`first` 非必要不用，用了须在 sidecar 写「首帧理由」；`first_last` 基本不用。
  不传 `frame_mode` 的缺省行为按 provider 分叉：直连 `seedance-2-x` 落回首帧、只取第一张图；`sparkhub-seedance`
  落多模态 `image_urls[]`。统一显式传 `reference`，不要依赖缺省。
  判定与例外见 `drama-production-playbook/references/03-seedance-best-practices.md` 规则 5
- 音色参考被拒时降级为仅图片重试（`frame_mode` 仍为 `reference`）
- 长任务轮询：30s 组任务的等待时间远超单镜，`--poll` / `timeout_seconds` 按 ≥1200s 放宽，超时不等于失败
- 失败处理：先诊断（审核拒绝/参数越界/内容拦截），再最小修正重试，禁盲目重试

## 产物落位与版本纪律

- 成片：`分镜脚本/EPxx/video_renders/{镜号}_seedance20/{镜号}_seedance20_reference_*.mp4`
- 连拍组母版：`分镜脚本/EPxx/video_renders/_takes/EPxx_TGxx_{总长}s_master.mp4`（`_` 前缀不被审阅扫描），
  按切点裁成逐镜文件后落各镜目录（ffmpeg 命令见 `ai-video-director/references/23-take-group-multi-shot.md` §7）
- 断点恢复：重跑前跳过已有成片的镜号（`drama qc` 的"存在 N 份成片"提示多版本）；
  编组过的镜按「整组」跳过——组内已有母版就整组不要再抽，避免组内混版
- 废弃版本：移入 `_superseded_{原因}/`；或交审片中心删除（自动归档抢救）
- 渲染报告 / production_manifest 写在 `video_renders/` 下（`_` 前缀目录可选），须记录连拍组表（组号 / 含镜号 / 时间码 / 母版名）

## 与其他技能的接口

- 上游 ai-video-director：shots.md（lint 通过）+ 本集资产需求
- 下游 shot-reviewer：video_renders + spec/ shots.md 元数据（初审打分）
- 终审：审阅中心镜头审片（人工），返修单回到本技能执行
