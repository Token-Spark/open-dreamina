# Drama Execution — 短剧项目制片执行专章

> 本文件是 production-orchestrator 技能的短剧专章：当生产对象是 Open Dreamina
> 短剧管线中的剧集时，执行层复用管线工具链与数据契约，不再自建登记表。

## 数据契约（管线已定义，直接消费）

| 数据 | 位置 | 说明 |
|---|---|---|
| 分镜脚本 | `分镜脚本/EPxx/shots.md` | 唯一权威数据源（导演产出，lint 已通过） |
| 资产清单 | `tools/assets_manifest.json` | 资产 prompt/seed/一致性策略/全局风格 |
| 音色清单 | `tools/voice_manifest.json` | 角色 → TTS 音色选角 |
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
opendreamina image2video --provider sparkhub-seedance \
    --reference <三视图> --reference <场景图> --reference <音色> \
    --prompt "<spec prompt + 风格常量>" --aspect-ratio 9:16 --auto-wait \
    --download-dir "分镜脚本/EPxx/video_renders/S01_seedance20/"

# 6. 技术验收
opendreamina drama qc EPxx --project .
```

## 生成参数基线（Seedance）

- provider/model：项目 manifest 的 `provider`/`model`（如 sparkhub-seedance + doubao_seedance_2）
- 720p / 9:16 / 全能参考（`--frame-mode reference`）/ 单镜 4-8s
- 参考绑定纪律：人物 = `*_turnaround`，场景 = primary/interior，音色 = anchor-voice
- 首尾帧模式慎用；音色参考被拒时降级为仅图片重试
- 失败处理：先诊断（审核拒绝/参数越界/内容拦截），再最小修正重试，禁盲目重试

## 产物落位与版本纪律

- 成片：`分镜脚本/EPxx/video_renders/{镜号}_seedance20/{镜号}_seedance20_reference_*.mp4`
- 断点恢复：重跑前跳过已有成片的镜号（`drama qc` 的"存在 N 份成片"提示多版本）
- 废弃版本：移入 `_superseded_{原因}/`；或交审片中心删除（自动归档抢救）
- 渲染报告 / production_manifest 写在 `video_renders/` 下（`_` 前缀目录可选）

## 与其他技能的接口

- 上游 ai-video-director：shots.md（lint 通过）+ 本集资产需求
- 下游 shot-reviewer：video_renders + spec/ shots.md 元数据（初审打分）
- 终审：审阅中心镜头审片（人工），返修单回到本技能执行
