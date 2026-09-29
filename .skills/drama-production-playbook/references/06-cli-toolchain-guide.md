# 06 opendreamina drama 工具链指南

> 九个命令的参数、输出与编排。所有命令输出 UTF-8 JSON（stdout），
> 进度与告警走 stderr；退出码 0 成功 / 1 校验未通过 / 2 用法错误。
> 全部命令**纯本地执行，不需要后端在线**（qc 依赖 ffprobe / ffmpeg，缺失时降级）。

## 全局参数与环境变量

| 参数 | 环境变量兜底 | 说明 |
|---|---|---|
| `--project <根>` | `DRAMA_PROJECT_ROOT` | 项目根目录（默认当前目录） |
| `--maps <文件>` | `DRAMA_MAPS` | 映射表文件（默认 `{项目根}/tools/maps.py`，存在才加载） |

集号写法随意：`EP05` / `05` / `5` 等价（内部归一为 EP05）。

## 命令详解

### init — 项目骨架
```bash
opendreamina drama init <路径> [--title ..] [--code ..] [--episodes 40] [--duration 90] [--language 中文]
```
输出 `{project_root, created[], skipped[], next_steps[]}`；幂等可重跑。

### list — 项目概览
```bash
opendreamina drama list [--project .]
```
输出每集 `{episode, shots_md, shots, duration_s, render_files, spec}`。
开工会话的第一条命令：一眼看清哪些集缺分镜、缺渲染、缺规格。

### parse — 分镜解析
```bash
opendreamina drama parse EP05 [--shot S01]
```
输出 `{episode, header, shots:{EP05-S01:{duration, camera, cast[], assets, dialogue[], ...}}}`。
英文锚点/台词逐字保留；中文叙述字段（`*_zh`）原样输出；HTML 注释块自动跳过。

### compile — 提示词编译
```bash
opendreamina drama compile EP05 [--shot S01] [--with-style]
```
输出 `{prompts:{镜号: 英文提示词}}`；`--with-style` 追加 manifest 的风格四常量并附
`negative` 字段。未命中词库的中文会被丢弃并在 stderr 告警——把告警里的词回填
`tools/maps.py` 后重跑。**编译结果是基线**；更高要求时人工/智能体精修后写回 spec。

### lint — 分镜规范校验
```bash
opendreamina drama lint EP05 [--target-duration 90]
```
输出 `{valid, errors[], warnings[], stats}`。errors 清零才能生成；
warnings 必须逐条给出处理结论（处理 or 接受并说明理由）。

### spec — 分集执行规格
```bash
opendreamina drama spec EP05 [--write] [--force]
```
分镜 + manifest + 注册表 → `tools/episode_specs/EPxx.json`
（assets 落路径与平台 asset_id、shots 落 refs/prompt/role_binding/dialogue）。
`valid=false` 时看 `validation_errors`（通常是 prompt 空或参考缺路径）。

### assets — 资产引用审计
```bash
opendreamina drama assets EP05 [EP06 ...] [--all]
```
输出每集引用资产 → manifest 登记 / 文件存在 / 平台 asset_id 三态。
`missing_platform_id` 非空 = 有裸参考生成风险，生成前必须清零。

### manifest — manifest 校验
```bash
opendreamina drama manifest
```
校验 assets_manifest + voice_manifest：必填字段 / 模式 / 参考锚点 /
primary seed / 音色语言。多 primary 锚点为 warning（多时期角色属正常形态）。

### qc — 成片技术验收
```bash
opendreamina drama qc EP05 [--min-duration 4] [--aspect 9:16]
```
逐镜核对 `video_renders/`：文件唯一性 / 画幅 / 时长 / 音轨与电平。
ffprobe 缺失时对应检查项如实降级（`ffprobe_available: false`）；
音量电平依赖 ffmpeg volumedetect。**技术验收不判断是否含 BGM**（需人工试听）。

## 典型智能体编排

```bash
# 修镜返工闭环（单镜）
opendreamina drama lint EP05 && \
opendreamina drama compile EP05 --shot S08 --with-style && \
opendreamina image2video ... --auto-wait && \
opendreamina drama qc EP05
```

⚠️ 项目根放在 `./data/` 下时工具链只读扫描（parse/lint/compile/spec/assets/qc 均只读）；
唯一写操作是 `spec --write`（写项目自己的 tools/ 目录）与 `init`（新目录）。
