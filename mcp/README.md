# Open Dreamina MCP 服务

把 Open Dreamina 的生成能力（图片 / 视频 / 对话）暴露成 **MCP（Model Context Protocol）工具**，
让本地智能体（IDE 助手、命令行 Agent、自动化脚本）可以直接调用，无需理解后端 REST 细节。

**纯 Python 标准库实现，零第三方依赖**——只用 `json` / `urllib` / `sys` / `pathlib`，不需要 `pip install`。

---

## 1. 能做什么

| 能力 | 工具 | 说明 |
| --- | --- | --- |
| 生成图片 | `generate_image` | 文生图 / 图生图（传参考图自动切换） |
| 生成视频 | `generate_video` | 文生视频 / 图生视频（支持首帧、首尾帧、内容参考） |
| 上传参考素材 | `upload_asset` | 本地图片 → `asset_id` |
| 创建多个对话 | `create_conversation` | 把多轮生成任务分组管理 |
| 任务查询 | `get_task` / `list_tasks` / `wait_task` | 轮询状态、等待完成、取结果地址 |
| 任务控制 | `cancel_task` / `retry_task` | 取消未完成任务、重试失败任务 |
| 对话管理 | `list_conversations` / `get_conversation` / `update_conversation` / `delete_conversation` | 列出、查看、重命名、删除 |
| 目录查询 | `list_templates` / `list_providers` / `list_models` / `get_health` | 模板、服务、模型能力、健康检查 |

共 **18 个工具**。不含画布（canvas）与工作流编排能力。

---

## 2. 前置条件

1. 后端已启动（容器内 10130 端口可访问）：

```bash
./deploy.sh          # Linux / macOS
./deploy.ps1         # Windows PowerShell
```

2. 至少配置一个 Provider（Web 界面「设置 → 服务管理」录入 Base URL 与 API Key）。
   未配置的 slug 调用生成会失败，但 `list_models` / `get_health` 等查询工具仍可用。

3. 本机有 Python 3.9+（仅标准库，无需任何依赖）。

---

## 3. 快速开始

### 3.1 启动与自检

```bash
# 打印工具清单（自检，不需要后端在线）
python mcp/server.py --list-tools

# 以 stdio 方式启动 MCP 服务（供客户端连接，正常运行时不会自己打印内容）
python mcp/server.py
```

也可用包方式启动（需在仓库根目录）：

```bash
python -m mcp.server
```

### 3.2 在 MCP 客户端中配置

在客户端（Trae / Claude Desktop / Cursor 等）的 MCP 配置中登记本服务。
`command` 用绝对路径，`args` 指向 `mcp/server.py` 的绝对路径：

```json
{
  "mcpServers": {
    "open-dreamina": {
      "command": "python",
      "args": ["c:/Users/workk/workspace/code-repo/open-dreamina/mcp/server.py"]
    }
  }
}
```

Windows 若 `python` 不在 PATH，可把 `command` 换成解释器绝对路径（如 `C:/Python312/python.exe`）。
需要连接远程后端时，在 `env` 中附加 `OPEN_DREAMINA_API_BASE`。

---

## 4. 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `OPEN_DREAMINA_API_BASE` | `http://localhost:10130/api/v1` | 后端 API 基地址 |
| `OPEN_DREAMINA_API_TIMEOUT` | `60` | 单次 HTTP 请求超时秒数（上传自动放宽到 ≥120） |

---

## 5. 工具速查

### 生成类

| 工具 | 必填 | 常用可选 |
| --- | --- | --- |
| `generate_image` | `provider`、`prompt` | `model_id`、`count`、`steps`、`guidance_scale`、`seed`、`strength`、`aspect_ratio`、`resolution`、`negative_prompt`、`reference_asset_ids`、`reference_paths`、`conversation_id` |
| `generate_video` | `provider`、`prompt` | `model_id`、`duration`、`frame_mode`、`aspect_ratio`、`resolution`、`seed`、`negative_prompt`、`reference_asset_ids`、`reference_paths`、`conversation_id` |
| `create_task` | `type`、`provider` | `model_id`、`prompt`、`params`、与上两者相同的参数（通用兜底入口） |
| `upload_asset` | `file_path` | — |

### 任务类

| 工具 | 必填 | 说明 |
| --- | --- | --- |
| `get_task` | `task_id` | 查询单次状态与结果 |
| `list_tasks` | — | `status`（逗号分隔）、`type`、`page`、`page_size` |
| `wait_task` | `task_id` | `interval_seconds`（默认 3）、`timeout_seconds`（默认 600，上限 1800） |
| `cancel_task` | `task_id` | 仅 pending / queued / running |
| `retry_task` | `task_id` | 仅 failed，返回新入队任务 |

### 对话与目录

| 工具 | 必填 | 说明 |
| --- | --- | --- |
| `create_conversation` | — | `title` 可选，默认「新对话」 |
| `list_conversations` | — | 含消息数、最后提示词、缩略图 |
| `get_conversation` | `conversation_id` | `include_messages` 默认 true |
| `update_conversation` | `conversation_id`、`title` | 重命名 |
| `delete_conversation` | `conversation_id` | 仅删除分组，任务与素材保留 |
| `list_templates` | — | `category` = `image` / `video` |
| `list_providers` | — | 已配置 Provider + 全部可用 slug |
| `list_models` | — | `mode`、`model_id`，含比例 / 分辨率 / 时长能力 |
| `get_health` | — | 后端 / 数据库 / Redis / worker |

---

## 6. 典型工作流

### 6.1 文生图（三步闭环）

```text
1. list_providers                       → 确认 provider slug（如 seedream）
2. generate_image {provider:"seedream", prompt:"...", aspect_ratio:"16:9", resolution:"2K"}
   → 立即返回 task_id（不阻塞）
3. wait_task {task_id, timeout_seconds:600}
   → 终态后读取 result_urls_absolute 下载图片
```

### 6.2 图生图 / 图生视频（参考素材）

```text
generate_video {
  provider: "seedance-2-5",
  prompt: "...",
  reference_paths: ["D:/refs/frame.png"],   // 本地路径会自动上传
  frame_mode: "first",                      // 首帧
  duration: 5,
  resolution: "1080p"
}
```

已有素材时可先 `upload_asset` 拿到 `asset_id`，再用 `reference_asset_ids` 复用，避免重复上传。

- `frame_mode`: `first`（首帧）｜`first_last`（首尾帧，需 2 张图）｜`reference`（内容参考）。
- 传了参考素材时，任务类型自动从 `text2img`/`text2video` 切到 `img2img`/`img2video`。

### 6.3 多对话分组

```text
create_conversation {title: "产品海报 A 版"}
→ 拿到 conversation_id，后续所有 generate_* 都带上它
list_conversations / get_conversation 回顾分组下的任务
```

不传 `conversation_id` 时后端会自动新建对话，并在返回值里给出 `conversation_id`。

### 6.4 失败重试

```text
get_task {task_id}        → status: failed，读 error_msg
get_health {}             → 若 worker != ok，先修环境
retry_task {task_id}      → 重新入队，再 wait_task
```

---

## 7. 尺寸与参数规则

智能体**优先只传「比例 + 分辨率」**，由服务换算成后端使用的像素宽高；也可直接传 `width` + `height`（两者同时给出时忽略比例/分辨率）。

| 模式 | 比例 | 分辨率 |
| --- | --- | --- |
| 图片 | `auto`、`21:9`、`16:9`、`3:2`、`4:3`、`1:1`、`3:4`、`2:3`、`9:16` | `1K`、`2K`、`3K`、`4K` |
| 视频 | `auto`、`21:9`、`16:9`、`4:3`、`1:1`、`3:4`、`9:16` | `480p`、`720p`、`1080p`、`2160p` |

默认值：图片 `1:1` + `2K`；视频 `16:9` + `720p` + 5 秒。

模型实际能力有差异（如 Seedance 2.5 支持 4~30 秒、Fast/Mini 仅 480p/720p），
调用 `list_models {mode:"video", model_id:"..."}` 可拿到精确区间；超出范围会被提前拦下并说明原因。

> 注意后端参数名为 **`guidance_scale`**（Web 界面显示为「提示词权重」，前端内部叫 `guidance`）。
> 参数白名单：`negative_prompt`、`width`、`height`、`steps`、`guidance_scale`、`seed`、`duration`、`strength`、`resolution`、`count`——白名单外的字段后端会忽略。

---

## 8. 任务状态与返回

- 状态机：`pending` → `queued` → `running` → `completed` / `failed` / `cancelled`
- 终态：`completed`、`failed`、`cancelled`（`wait_task` 在此返回）
- 关键返回字段：`task_id`、`status`、`progress`、`conversation_id`、`result_urls_absolute`（可直接下载的绝对地址）、`error_msg`
- 生成类工具**只返回 `task_id`**，不会阻塞等待；请显式调用 `wait_task`

---

## 9. 排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 无法连接后端 | 服务未启动 / 端口不通 | 先跑 `deploy.sh`/`deploy.ps1`，或用 `OPEN_DREAMINA_API_BASE` 指向正确地址 |
| 任务长期 `pending` | Celery worker 未就绪 | `get_health` 查看 `worker` 字段，检查 worker 容器 |
| 生成立即 `failed` | Provider 未配置 / Key 无效 | `list_providers` 看 `configured`，在 Web 界面补录 API Key |
| 提示缺少必填参数 | 参数名写错或漏传 | 错误信息已列出缺失项与正确字段名（注意 `guidance_scale`） |
| 时长/分辨率被拒 | 超出该模型能力 | `list_models {model_id}` 查精确区间后重试 |
| `400` 取消任务失败 | 任务已进入终态 | 用 `get_task` 确认状态；已完成的不能取消 |

所有后端错误都会被包装成「发生了什么 + 上下文 + 修复建议」的文本，工具结果中 `isError: true`。

---

## 10. 设计约束

- **单一事实来源**：模型服务目录直接读取 `frontend/src/config/modelServices.json`，
  前端新增服务后 MCP 自动生效，不存在两份清单漂移。
- **尺寸口径同步**：`mcp/sizes.py` 与 `frontend/src/lib/generation.ts` 的像素表一致，修改前端表格需同步。
- **参数白名单同步**：`mcp/catalog.py` 的 `PARAM_WHITELIST` 与 `backend/app/worker.py` 一致。
- **安全红线**（与 `AGENTS.md` 一致）：不读取、不打印 `.env`；不修改 `./data` 目录；宿主不安装任何依赖。
- **协议纯净**：stdout 只输出 JSON-RPC 报文，日志与异常栈一律走 stderr。

### 目录结构

```text
mcp/
├── server.py          # stdio JSON-RPC 入口（initialize / tools/list / tools/call）
├── tools.py           # 工具注册表：name / description / inputSchema
├── handlers.py        # 工具实现聚合入口（对外仅暴露 HANDLERS）
├── generate.py        # 生成类：generate_image / generate_video / create_task / upload_asset
├── tasks.py           # 任务类：get_task / list_tasks / wait_task / cancel_task / retry_task
├── conversations.py   # 对话类：对话的增删改查
├── discovery.py       # 目录与系统类：模板 / Provider / 模型 / 健康检查
├── payload.py         # 入参构造与边界校验（尺寸换算、参考素材、params 白名单）
├── common.py          # 出参整形（任务精简视图、相对地址补全）
├── client.py          # 后端 REST 客户端（urllib）+ multipart 上传
├── catalog.py         # 模型目录（读前端 modelServices.json）+ 参数白名单
└── sizes.py           # 比例 × 分辨率 → 像素宽高 + 模型能力
```
