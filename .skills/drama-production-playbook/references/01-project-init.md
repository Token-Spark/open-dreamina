# 01 项目初始化

## 一键初始化

```bash
opendreamina drama init ./data/review_sources/短剧我的项目 \
    --title "我的项目正式名" \
    --code "我的项目" \
    --episodes 40 \
    --duration 90 \
    --language "英语"
```

脚本生成标准目录树与全部模板文件（幂等：已存在的文件跳过，可重复执行补齐）：

- `目标设定.md`——目标 / 体裁设定 / 规模 / 制作要求（占位符已按参数填充）
- `工作流程和注意事项.md`——流程规范 + 实战注意事项 + 提示词格式参考
- `剧本大纲.md`——八幕结构骨架表（Logline / 核心人物 / 分幕事件）
- `分镜脚本/_SPEC_分镜模板规范.md`——shots.md 格式规范（`_` 前缀不被审阅扫描）
- `分镜脚本/EP01/shots.md`——分镜模板（总览表 15 列 + 单镜 15 行示例）
- `tools/maps.py`——项目级中英映射表（带填充注释）
- `tools/assets_manifest.json`——资产清单骨架（含一致性策略与 style 四常量）
- `tools/voice_manifest.json` / `tools/asset_registry.json`——音色与平台注册表骨架
- `素材库/01~06/`、`参考素材/`、`成片/`、`qc_frames/`、`分集剧本/`、`tools/episode_specs/`

## 初始化后必填三件事

1. **目标设定.md**：题材 / 受众 / 画风基调定稿（影响后续全部提示词风格）。
2. **tools/assets_manifest.json 的 style 字段**：全局风格四常量（英文，逐字进入每条提示词）：
   - `aesthetic`：美学基调（如 "ethereal Greek mythological aesthetic, ..."）
   - `medium`：媒介质感（如 "1990s television drama production still, film grain, ..."）
   - `audio`：音频约定（生成禁 BGM 的标准句式，模板已内置）
   - `negative`：负面词（text, watermark, logo, subtitles, background music, ...）
3. **provider / model**：素材生成渠道（如 sparkhub-seedream + doubao_seedream_5_pro）。

## 环境自检

```bash
opendreamina --version            # CLI 就绪
opendreamina health               # 后端 / worker（生成环节才需要）
opendreamina drama list --project ./我的短剧   # 骨架可被工具链识别
```

注意：`drama` 子命令为纯本地工具，**不需要后端在线**；只有真正调用生成
（opendreamina generate / MCP 工具）时才需要后端与 worker 就绪。
