# Olympus 素材库

将短剧《维纳斯崛起》的全部素材（角色 / 场景 / 道具 / 名场面）上传至 Open Dreamina 素材库，
以 **Olympus** 标签形式存储为云端共享项目，便于跨机器协作。

## 当前状态

| 项 | 值 |
| --- | --- |
| 项目标签 | `Olympus` |
| 素材总数 | **99 条**（角色 54 / 场景 27 / 道具 10 / 名场面 8） |
| 含音色素材 | 11 条（角色基准肖像 + 5 秒音色采样） |
| 云端对象 | 309 个（99 图 + 11 音 + 198 版本清单 + 1 项目元数据） |
| 自动同步 | 已开启（Celery Beat 每 2 分钟推送 + 拉取） |
| 上传报告 | `olympus_upload_report.json` |

## 源目录结构

脚本针对以下结构设计（`--source` 指向其根目录）：

```
素材库/
├── 01_characters/<group>/<GROUP>_PRIMARY_anchor-portrait.png   ← 基准肖像
│                        └ <GROUP>_PRIMARY_anchor-voice.wav    ← 配对音色
│                        └ <GROUP>_<variant>_{halfbody,turnaround}.png
├── 02_scenes/<group>/<SCENE>_{PRIMARY_wide,interior,exterior}.png
├── 03_props/props/PROP_<name>.png
├── 04_iconic_scenes/iconic/EP<nn>_<slug>.png
├── 05_index/{generation_report,voice_generation_report}.json   ← 中文名元数据
└── _pilot_style/、*_superseded_*/                              ← 自动跳过
```

**自动跳过**：`_pilot_style/`（画风试片）与任何含 `_superseded` 的目录（废弃版本）。

## 使用方法

```bash
# 预览上传计划（不上传）
python upload_to_olympus.py --source "<素材库绝对路径>" --dry-run

# 正式上传（打 Olympus 标签 + 自动同步云端）
python upload_to_olympus.py --source "<素材库绝对路径>"

# 仅上传到本地，跳过云端同步
python upload_to_olympus.py --source "<素材库绝对路径>" --skip-sync

# 调试：只传前 N 条
python upload_to_olympus.py --source "<素材库绝对路径>" --limit 5
```

脚本**幂等**：同名素材已存在时自动跳过，可安全重复执行。

## 分类与标签

| 源目录 | 素材库分类 | 附加标签 |
| --- | --- | --- |
| `01_characters` | `character` | 角色分组名（如 `apollo`） |
| `02_scenes` | `scene` | 场景分组名（如 `olympus_hall`） |
| `03_props` | `prop` | `props` |
| `04_iconic_scenes` | `keyframe` | `iconic` |

每条素材的标签形如 `["Olympus", "character", "apollo"]`，
因此可按分类或分组在素材库页面精确筛选。

素材名称取自 `05_index/generation_report.json` 的中文名字段（如「宙斯·基准肖像」），
描述字段记录来源相对路径，便于溯源。

## 云端布局

```
team-assets/Olympus/
├── project.json                                  项目元数据 + 成员名册
└── <owner_id>/<asset_id>/
    ├── manifest.N.json                           版本链（append-only）
    ├── manifest.json                             最新指针
    ├── image.<sha12>.png                         内容寻址媒体（不可变）
    └── audio.<sha12>.wav
```

## 跨机器协作

其他机器拉取（需配置同一七牛云 `QINIU_*`）：

```bash
curl -X POST http://localhost:10130/api/v1/creation-assets/pull \
  -H "Content-Type: application/json" -d '{"tag": "Olympus"}'
```

或在前端「素材库」页面点击「拉取」。

也可在本机开启全自动同步：

```bash
curl -X PUT http://localhost:10130/api/v1/creation-assets/auto-sync \
  -H "Content-Type: application/json" -d '{"enabled": true, "tag": "Olympus"}'
```

## 同步语义

- **推送**：CAS 乐观锁，云端版本必须等于本地基线才允许推 `v+1`，绝不盲覆盖。
- **拉取**：三方合并；本地未改则快进，两边都改则云端版导入为副本（保两份）。
- **签名**：manifest 以团队共享密钥（`TEAM_SECRET` 或七牛密钥）做 HMAC，防伪造。
- 仅同步**图片 / 音频**轻量资产（视频不同步）。

## 注意事项

- 素材库为**可信团队模型**：能访问同一云存储的成员均可编辑。
- 删除素材只清理本地记录，云端历史版本对象不会被自动删除。
