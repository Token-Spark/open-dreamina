# 03 · 参数建议与 MCP 直接执行

> 本文件描述如何把优化后的提示词**直接落成生成任务**。
> 服务安装、客户端配置、环境变量见仓库的 `mcp/README.md`。

## 1. 工具选择

| 场景 | 工具 | 必填 |
| --- | --- | --- |
| 文生图 / 图生图 | `generate_image` | `provider`、`prompt` |
| 文生视频 / 图生视频 | `generate_video` | `provider`、`prompt` |
| 上传本地参考图 | `upload_asset` | `file_path` |
| 等待出结果 | `wait_task` | `task_id` |
| 查状态 / 列表 | `get_task` / `list_tasks` | `task_id` / — |
| 新建对话分组 | `create_conversation` | — |
| 查服务与能力 | `list_providers` / `list_models` | — |
| 查模板 | `list_templates` | — |
| 查环境 | `get_health` | — |
| 失败重试 / 取消 | `retry_task` / `cancel_task` | `task_id` |

传了参考素材（`reference_asset_ids` 或 `reference_paths`）时，任务类型会**自动**从
`text2img` 切到 `img2img`、`text2video` 切到 `img2video`，无需手动指定。

## 2. 参数表

### 2.1 通用

| 参数 | 含义 | 说明 |
| --- | --- | --- |
| `provider` | 模型服务 | 服务 slug，如 `seedream`、`seedance-2-5`、`openai`；用 `list_providers` 确认 |
| `model_id` | 模型 id | 省略则用服务默认模型；用 `list_models` 查看 |
| `prompt` | 正向提示词 | 优化结果填入此处 |
| `negative_prompt` | 负面提示词 | 独立填写，不要与正向重复 |
| `aspect_ratio` | 画面比例 | 见第 3 节 |
| `resolution` | 分辨率档位 | 见第 3 节 |
| `width` / `height` | 像素宽高 | 两者同时给出时忽略比例与分辨率 |
| `seed` | 随机种子 | 固定可复现；想微调画面时先固定 seed 改提示词 |
| `conversation_id` | 对话分组 | 省略则后端自动新建，返回值中给出 |

### 2.2 图片专有

| 参数 | 范围 | 默认 | 说明 |
| --- | --- | --- | --- |
| `count` | 1~4 | 1 | 一次生成张数；首轮建议 1~2，选中方向后再加量 |
| `steps` | 1~80 | 模型默认 | 采样步数；提高不一定更好，30 左右通常足够 |
| `guidance_scale` | 1~20 | 7 | 提示词权重；**后端字段名是 `guidance_scale`，不是 `guidance`** |
| `strength` | 0~1 | 0.7 | 图生图重绘强度；越高越偏离原图，仅带参考图时生效 |

### 2.3 视频专有

| 参数 | 取值 | 默认 | 说明 |
| --- | --- | --- | --- |
| `duration` | 秒 | 5 | Seedance 2.5 支持 4~30；Fast/Mini 与 2.0 支持 4~15 |
| `frame_mode` | `first` / `first_last` / `reference` | — | 首帧 / 首尾帧（需 2 张参考图）/ 内容参考 |

> 白名单外的参数会被后端忽略：`negative_prompt`、`width`、`height`、`steps`、`guidance_scale`、
> `seed`、`duration`、`strength`、`resolution`、`count`。

## 3. 尺寸换算

优先只给「比例 + 分辨率」，由 MCP 服务换算成像素宽高。

| 模式 | 比例 | 分辨率 |
| --- | --- | --- |
| 图片 | `auto`、`21:9`、`16:9`、`3:2`、`4:3`、`1:1`、`3:4`、`2:3`、`9:16` | `1K`、`2K`、`3K`、`4K` |
| 视频 | `auto`、`21:9`、`16:9`、`4:3`、`1:1`、`3:4`、`9:16` | `480p`、`720p`、`1080p`、`2160p` |

默认值：图片 `1:1` + `2K`；视频 `16:9` + `720p` + 5 秒。

选型建议：

- 横版叙事 / 风景 → `16:9`；竖版短视频 / 手机壁纸 → `9:16`；头像 / 产品主图 → `1:1`。
- 草稿试方向 → `1K`（图片）/ `480p`（视频）；定稿 → `2K` 及以上 / `1080p`。

**模型能力有差异**，给参数前建议先核对：

```text
list_models {mode:"video", model_id:"doubao-seedance-2-5"}
→ capability.duration = {min:4, max:30}, resolutions = ["480p","720p","1080p"]
```

超出范围会被 MCP 提前拦下并返回「哪个模型、范围是多少、实际传了多少」。

## 4. 参考素材

两种传法，效果等价：

```text
方式 A（本地文件，工具自动上传）
generate_video { ..., reference_paths: ["D:/refs/frame.png"], frame_mode: "first" }

方式 B（先上传再复用 asset_id）
upload_asset {file_path:"D:/refs/frame.png"} → asset_id
generate_video { ..., reference_asset_ids: ["<asset_id>"], frame_mode: "first" }
```

同一素材要在多次生成中复用时用方式 B，避免重复上传。

## 5. 执行序列

```text
STEP 1  list_providers                    → 确认 provider 已配置（configured: true）
STEP 2  get_health                        → 确认 worker = ok，否则任务会卡在 pending
STEP 3  list_models {mode, model_id}      → 校验 duration / resolution 是否在能力内
STEP 4  generate_image / generate_video   → 立即返回 task_id（不阻塞）
STEP 5  wait_task {task_id, timeout_seconds: 600}
        → 终态后读取 result_urls_absolute（可直接下载的绝对地址）
```

视频建议 `timeout_seconds ≥ 600`；图片可短一些。`wait_task` 超时**不算失败**，
返回 `timed_out: true`，可再次调用继续等待。

## 6. 结果与失败处理

| 情况 | 表现 | 处理 |
| --- | --- | --- |
| 成功 | `status: completed`，`result_urls_absolute` 有值 | 回报结果地址；需要分组时用 `conversation_id` |
| 未完成 | 仍为 `pending` / `queued` / `running` | 再调 `wait_task`；长期 pending 查 `get_health` 的 `worker` |
| 失败 | `status: failed`，读 `error_msg` | 先判断是**环境问题**（未配置 Key、worker 离线）还是**提示词问题**，前者修环境、后者按 04 改词，再用 `retry_task` 或新建任务 |
| 已终态想取消 | `cancel_task` 报 400 | 只有 pending / queued / running 可取消 |

## 7. 边界

- 用户**未明确要求生成**时，只输出提示词与参数，不调用生成工具（见 SKILL.md 强制规则 8）。
- 会话中已有 `conversation_id` 时，后续生成默认沿用，便于用户在界面里成组查看。
- 不在终端打印任何 API Key；Provider 凭据只经 Web 界面录入。
