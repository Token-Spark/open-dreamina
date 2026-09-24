# Open Dreamina 命令行工具（opendreamina CLI）

把 Open Dreamina 平台的**图片 / 视频生成能力**打包成命令行工具，供 AI 智能体（agent）与自动化脚本直接调用。

- **纯 Python 标准库实现，零第三方依赖**：只用 `argparse` / `json` / `urllib`，宿主机无需 `pip install`。
- **复用 `mcp/` 包**：与 MCP 服务、前端模型目录共用同一份事实来源（`frontend/src/config/modelServices.json`），不重复维护。
- **对智能体友好**：所有输出均为 UTF-8 JSON，可直接解析；错误信息走 stderr，不污染 stdout。
- **自动模式选择 / 自动模型选择 / 元素引用 / 进度查询**：一条命令完成「生成 → 等待 → 取结果」闭环。
- **参数设计参考即梦创作 CLI**：子命令命名（`text2image` / `image2video` / `frames2video` 等）、`--poll` 有限等待、`--download-dir` 下载、`query_result` 跟进等均与即梦 CLI 对齐，降低智能体迁移成本。

> 与 MCP 服务的关系：MCP（`mcp/server.py`）面向 IDE / 客户端以 JSON-RPC stdio 方式接入；本 CLI 面向命令行 / 智能体以子命令方式接入。两者底层调用同一套 handler，能力等价，按场景选用。

---

## 1. 前置条件

1. **后端已启动**（容器内 10130 端口可访问）：
   ```bash
   ./deploy.sh          # Linux / macOS
   ./deploy.ps1         # Windows PowerShell
   ```
2. **至少配置一个 Provider**：在 Web 界面「设置 → 服务管理」录入 Base URL 与 API Key。
   未配置的 slug 生成会失败，但 `models` / `providers` / `health` 等查询命令仍可用。
3. **本机有 Python 3.9+**（仅标准库，无需任何依赖）。

---

## 1.5 安装到 PATH（可选，便于智能体直接调用 `opendreamina`）

安装脚本只在用户 PATH 目录创建一个调用 `python cli/opendreamina.py` 的 wrapper（约三五行），不安装任何依赖、不需要管理员权限：

```bash
bash cli/install.sh     # Linux / macOS（安装到 ~/.local/bin）
pwsh cli/install.ps1    # Windows（安装到 %USERPROFILE%\bin 并写入用户 PATH）
```

> `install.sh` 若提示 `~/.local/bin` 不在 PATH，按提示加进 `~/.bashrc` / `~/.zshrc`；`install.ps1` 写入用户 PATH 后需新开终端生效。仓库移动后重跑对应脚本刷新 wrapper。下文示例统一用 `opendreamina`（已安装）或 `python cli/opendreamina.py`（未安装）均可。

---

## 2. 快速开始

```bash
# 0. 自检环境（不需后端在线也能跑 models / providers / health 之外需后端）
python cli/opendreamina.py --help
python cli/opendreamina.py health
python cli/opendreamina.py providers
python cli/opendreamina.py models --mode video

# 1. 生成图片（全自动：自动选 provider / model，并等待出图 + 下载）
python cli/opendreamina.py text2image "一只橘猫坐在窗台上，清晨柔光，写实照片" \
    --auto-provider --auto-model --aspect-ratio 16:9 --resolution 2K \
    --poll 600 --download-dir ./out

# 2. 只查询进度（不等待）
python cli/opendreamina.py progress <task_id>

# 3. 等待直到终态并下载结果
python cli/opendreamina.py query_result <task_id> --wait --download-dir ./out
```

也可用包方式启动（需在仓库根目录）：

```bash
python -m cli.opendreamina --help
```

输出统一为 JSON，例如生成成功后的关键字段：

```json
{
  "task_id": "fb389650-73c7-4826-b0c1-58ecaf5d442d",
  "status": "completed",
  "result_urls_absolute": ["http://localhost:10130/api/v1/.../image.png"],
  "terminal": true,
  "waited_seconds": 12.3
}
```

---

## 3. 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `OPEN_DREAMINA_API_BASE` | `http://localhost:10130/api/v1` | 后端 API 基地址 |
| `OPEN_DREAMINA_API_TIMEOUT` | `60` | 单次 HTTP 请求超时秒数（上传自动放宽到 ≥120） |

连接远程后端时：

```bash
OPEN_DREAMINA_API_BASE=http://192.168.1.10:10130/api/v1 python cli/opendreamina.py health
```

---

## 4. 命令总览

| 命令 | 作用 | 必填参数 |
| --- | --- | --- |
| `generate` | 生成图片 / 视频（自动推断模式） | `prompt` |
| `text2image` | 文生图（命名对齐即梦 CLI） | `prompt` |
| `image2image` | 图生图（需参考素材） | `prompt` + 参考 |
| `text2video` | 文生视频 | `prompt` |
| `image2video` | 图生视频（需参考素材） | `prompt` + 参考 |
| `frames2video` | 首尾帧驱动视频（2 张参考图 + first_last） | `prompt` + 2 张参考 |
| `create-task` | 通用任务创建（自定义 type / params） | `--type`、`prompt` |
| `progress` | 查询任务进度（`--wait` 等待终态） | `task_id` |
| `query_result` | 查询异步结果（`--download-dir` 下载，对齐即梦 CLI） | `task_id` |
| `tasks` | 分页查询任务列表 | — |
| `cancel` | 取消未完成任务 | `task_id` |
| `retry` | 重试失败任务 | `task_id` |
| `upload` | 上传本地文件为参考素材 | `file_path` |
| `audit` | 提交/查询参考素材审核（仅 Spark Hub Seedance 生视频需要） | `asset_id`、`--provider` |
| `models` | 列出模型目录（slug / 模型 / 能力） | — |
| `providers` | 列出已配置 Provider 与可接入 slug | — |
| `templates` | 列出提示词模板 | — |
| `health` | 检查后端 / DB / Redis / worker | — |
| `conversations` | 对话的增删改查 | `action` |

---

## 5. 命令详解

### 5.1 `generate` —— 生成图片 / 视频

```text
opendreamina generate <prompt> [options]
```

**模式选择（mode-select）**

- 显式指定：`--mode image` 或 `--mode video`。
- 自动推断：省略 `--mode` 时按提示词内容推断（含「视频/video/动画」等关键词走视频，否则走图片）。
- 带参考素材（`--reference` / `--reference-asset`）时自动从 `text2img` / `text2video` 切换为 `img2img` / `img2video`。

**模型选择（model-select）**

- 显式指定：`--provider seedream --model doubao-seedream-5-0-pro-260628`。
- 自动选 provider：`--auto-provider` 选首个已配置且支持该 mode 的 provider。
- 自动选 model：`--auto-model` 在未显式给 `--model` 时取该 provider 的默认模型。
- 推荐组合：`--auto-provider --auto-model`，一行完成「选服务 → 选模型 → 生成」。

**元素引用（参考素材）**

- 本地路径：`--reference D:/refs/a.png --reference D:/refs/b.png`（自动上传后引用）。
- 已有素材：`--reference-asset <asset_id>`（可多次传，避免重复上传）。
- 视频首帧 / 首尾帧 / 内容参考：用 `--frame-mode first|first_last|reference`（`first_last` 需 2 张参考图）。

**进度查询与下载**

- 生成命令本身只返回 `task_id`，不阻塞。
- `--auto-wait`：生成后自动轮询到终态（completed/failed/cancelled）或超时，结果一并打印。
- `--poll N`：生成后等待终态最多 N 秒（对应即梦 CLI 的 `--poll`），与 `--auto-wait` 等价，二者任选其一。
- `--download-dir <dir>`：终态成功时把 `result_urls_absolute` 下载到该目录，返回中追加 `downloaded` 清单（对应即梦 CLI 的 `--download_dir`）。
- 也可后续用 `progress <task_id> --wait` 或 `query_result <task_id> --wait --download-dir <dir>` 单独等待 / 下载。

**任务类型子命令**（命名对齐即梦 CLI）

`generate` 之外，还提供与即梦 CLI 同名的子命令，语义更直白、参数完全复用 `generate`：

| 子命令 | 等价于 | 说明 |
| --- | --- | --- |
| `text2image` | `generate --mode image`（无参考素材） | 文生图 |
| `image2image` | `generate --mode image`（强制带参考素材） | 图生图 |
| `text2video` | `generate --mode video`（无参考素材） | 文生视频 |
| `image2video` | `generate --mode video`（强制带参考素材） | 图生视频 |
| `frames2video` | `generate --mode video --frame-mode first_last`（强制 2 张参考图） | 首尾帧驱动视频 |

**图片专用参数**

| 参数 | 说明 |
| --- | --- |
| `--count N` | 生成张数（1~4，默认 1） |
| `--steps N` | 采样步数（1~80） |
| `--guidance-scale F` | 提示词权重（1~20，默认 7）。注意后端字段名为 `guidance_scale` |
| `--seed N` | 随机种子；显式指定可复现 |
| `--strength F` | 图生图重绘强度（0~1，默认 0.7），仅带参考素材时生效 |

**视频专用参数**

| 参数 | 说明 |
| --- | --- |
| `--duration N` | 时长（秒）。Seedance 2.5 支持 4~30；Fast/Mini 与 2.0 支持 4~15，默认 5 |
| `--frame-mode` | `first` / `first_last`（需 2 张）/ `reference` |

**尺寸参数**（优先传「比例 + 分辨率」，由工具换算像素；也可直接传 `--width` + `--height`）

| 内容 | `--aspect-ratio` | `--resolution` | 默认 |
| --- | --- | --- | --- |
| 图片 | auto、21:9、16:9、3:2、4:3、1:1、3:4、2:3、9:16 | 1K、2K、3K、4K | 1:1 + 2K |
| 视频 | auto、21:9、16:9、4:3、1:1、3:4、9:16 | 480p、720p、1080p、2160p | 16:9 + 720p |

**示例**

```bash
# 文生图（全自动 + 自动等待 + 下载）—— 也可用 text2image 子命令
opendreamina text2image "赛博朋克城市夜景，霓虹灯，电影感" \
    --auto-provider --auto-model --aspect-ratio 16:9 --resolution 2K \
    --poll 600 --download-dir D:/out

# 图生图（带本地参考图，指定重绘强度）—— 也可用 image2image
opendreamina image2image "把背景换成雪山" \
    --provider seedream --auto-model \
    --reference D:/refs/subject.png --strength 0.6 --auto-wait

# 图生视频（首帧驱动）—— 也可用 image2video
opendreamina image2video "镜头缓慢推进，人物微笑" \
    --provider seedance-2-5 --auto-model \
    --reference D:/refs/first_frame.png --frame-mode first \
    --duration 5 --resolution 1080p --auto-wait

# 首尾帧驱动视频（强制 first_last，需 2 张参考图）
opendreamina frames2video "镜头从城市推向雪山" \
    --provider seedance-2-5 --auto-model \
    --reference D:/refs/first.png --reference D:/refs/last.png \
    --duration 5 --poll 600

# 仅提交不等待，拿到 task_id 后再用 query_result 跟进
opendreamina text2image "..." --auto-provider --auto-model
opendreamina query_result <task_id> --wait --download-dir D:/out
```

### 5.2 `create-task` —— 通用任务创建

用于 `generate` 未覆盖的场景（需完全自定义 `type` 或 `params`）。常规图片 / 视频生成请优先用 `generate`。

```bash
opendreamina create-task --type text2img --provider seedream "prompt..." \
    --params '{"steps":30,"guidance_scale":7.5}'
```

- `--type`（必填）：`text2img` / `img2img` / `text2video` / `img2video`。
- `--params`：JSON 字符串，直接透传给后端。参数白名单见 `mcp/catalog.py`（`negative_prompt`、`width`、`height`、`steps`、`guidance_scale`、`seed`、`duration`、`strength`、`resolution`、`count`），白名单外字段后端会忽略。

### 5.3 `progress` —— 进度查询与等待

```bash
opendreamina progress <task_id>            # 查询当前状态
opendreamina progress <task_id> --wait      # 轮询到终态或超时
opendreamina progress <task_id> --wait --timeout 1200 --interval 5
```

- 超时不等于失败：返回 `timed_out: true`，可再次调用继续等待。
- 终态：`completed` / `failed` / `cancelled`（`terminal: true`）。
- 关键返回字段：`task_id`、`status`、`progress`、`result_urls_absolute`（可直接下载）、`error_msg`。

### 5.3a `query_result` —— 异步结果查询（对齐即梦 CLI）

```bash
opendreamina query_result <task_id>                                  # 查询当前状态
opendreamina query_result <task_id> --wait                           # 轮询到终态
opendreamina query_result <task_id> --wait --download-dir D:/out      # 等待 + 下载结果
```

- 命名对齐即梦 CLI 的 `query_result`；`task_id` 等价于即梦的 `submit_id`。
- `--download-dir`：终态成功时把结果下载到该目录，返回中追加 `downloaded` 清单（含 `url`、`ok`、`path`）。
- 异步语义：`status` 为 `completed` 才算终态成功；`pending` / `queued` / `running` 仍可继续查询。

### 5.4 `tasks` —— 任务列表

```bash
opendreamina tasks                              # 默认第 1 页，每页 20 条
opendreamina tasks --status failed,running      # 按状态筛选（逗号分隔）
opendreamina tasks --type img2video --page 2 --page-size 50
```

### 5.5 `cancel` / `retry`

```bash
opendreamina cancel <task_id>     # 仅 pending / queued / running 可取消
opendreamina retry <task_id>      # 仅 failed 可重试，返回重新入队的任务
```

### 5.6 `upload` —— 上传参考素材

```bash
opendreamina upload D:/refs/frame.png
# → {"asset_id": "...", "file_url": "..."}
# 把 asset_id 传给 generate --reference-asset
```

也可跳过本命令，直接用 `generate --reference <本地路径>`，工具会自动上传再引用。

> **Spark Hub Seedance 自动审核**：图生视频（`image2video` / `frames2video`）使用 Spark Hub Seedance 渠道时，CLI 会**自动**完成参考素材审核——上传后检测素材审核状态，未审核的自动提交审核并等待通过（`active`），全程在 stderr 打印进度，无需手动调用 `audit`。直接用 `--reference <本地路径>` 即可一条命令走完「上传 → 审核 → 生成视频」。
>
> 如需**复用同一素材**生成多次（避免重复上传 + 审核），可先 `upload` 上传一次，再用 `--reference-asset <asset_id>` 引用——已审核通过的素材会跳过审核。
>
> **审核范围仅 Image / Video**：提审接口只接受图片与视频素材，音频等类型不在提审范围内。CLI 会按素材类型分流——图片 / 视频走「提交审核 → 等待通过」，音频等类型原样透传参与生成（后端路由到 `audio_urls`），不会被送进提审接口。

### 5.6a `audit` —— 参考素材审核（仅 Spark Hub Seedance 生视频需要）

Spark Hub Seedance 渠道的图生视频要求参考素材先通过审核（`audit_status=active`）。**图生视频命令已自动处理审核**（见上方说明），本命令用于手动提交 / 查询审核状态（例如复用素材前确认状态、排查审核失败原因）。

```bash
# 提交审核并等待通过（手动场景）
opendreamina audit <asset_id> --provider sparkhub-seedance --wait

# 只提交不等待
opendreamina audit <asset_id> --provider sparkhub-seedance

# 只查询当前状态（不提交）
opendreamina audit <asset_id> --provider sparkhub-seedance --query-only
```

- `--provider`（必填）：Spark Hub Seedance Provider slug（如 `sparkhub-seedance`）。
- `--wait`：提交后轮询直到终态（`active` / `failed`）或超时；终态时只输出一个 JSON。
- `--query-only`：只查询不提交（仅调用 GET）。
- **仅 Image / Video 可提审**：音频等类型的素材不在提审范围内，提交会返回 400。这类素材无需审核，直接作为参考素材参与生成即可。
- 审核状态：`pending`（审核中）→ `active`（通过，可用于生成）/ `failed`（失败，需更换素材重新上传）。
- 通过后用 `image2video` / `frames2video` 的 `--reference-asset <asset_id>` 引用，即可生成视频。

### 5.7 `models` —— 模型目录

```bash
opendreamina models                    # 列出全部模型（图片 + 视频）
opendreamina models --mode video       # 只看视频模型
opendreamina models --mode video --model-id doubao-seedance-2-5-250928   # 查该模型精确的分辨率 / 时长能力
```

返回每个服务的 `slug`、`models`（id / label / types）、是否已配置（`configured`），以及该 mode 下可用的比例 / 分辨率 / 时长（`capability` / `size_options`）。不确定用哪个模型或参数时先调用本命令。

### 5.8 `providers` —— 已配置 Provider

```bash
opendreamina providers
```

返回已配置 Provider（含 `slug`、`is_active`、`base_url`、`api_key_masked`、支持的 `modes`）与全部可接入 slug（含是否已配置）。生成前先用它确认 `--provider` 取值。

### 5.9 `templates` —— 提示词模板

```bash
opendreamina templates                 # 全部
opendreamina templates --category video
```

返回模板的 `prompt_text` / `negative_prompt` / `params`，供「按模板优化提示词」时取用。

### 5.10 `health` —— 健康检查

```bash
opendreamina health
# {"status":"ok","database":"ok","redis":"ok","worker":"ok","warnings":[]}
```

任务长期停留在 `pending` 时先调用本命令：`worker != ok` 会附 warning。

### 5.11 `conversations` —— 对话管理

把多个生成任务按对话分组，便于多轮迭代与追溯。

```bash
opendreamina conversations list                              # 列出全部
opendreamina conversations create --title "产品海报 A 版"     # 新建
opendreamina conversations get --id <conversation_id>         # 详情（默认含任务列表）
opendreamina conversations rename --id <id> --title "新标题"  # 重命名
opendreamina conversations delete --id <id>                  # 删除分组（任务与素材保留）
```

生成时用 `--conversation-id <id>` 把任务归入对话；不传则后端自动新建对话，返回值中给出 `conversation_id`。

---

## 6. 典型工作流

### 6.1 文生图三步闭环

```bash
# 1. 确认环境与服务
opendreamina health
opendreamina providers

# 2. 生成 + 自动等待出图
opendreamina generate "一只橘猫坐在窗台上，清晨柔光" \
    --provider seedream --auto-model \
    --aspect-ratio 16:9 --resolution 2K --auto-wait
# → result_urls_absolute 即为可下载的图片地址

# 3.（或手动等待）分两步
opendreamina generate "..." --provider seedream --auto-model
opendreamina progress <task_id> --wait
```

### 6.2 图生图 / 图生视频（参考素材）

```bash
# 方式 A：直接传本地路径，自动上传
opendreamina generate "把背景换成雪山" \
    --provider seedream --auto-model \
    --reference D:/refs/subject.png --strength 0.6 --auto-wait

# 方式 B：先 upload 拿 asset_id，再引用（适合复用同一素材）
opendreamina upload D:/refs/subject.png   # → asset_id
opendreamina generate "..." --provider seedream --auto-model \
    --reference-asset <asset_id> --auto-wait

# 图生视频（首帧驱动）
opendreamina generate "镜头缓慢推进，人物微笑" \
    --provider seedance-2-5 --auto-model \
    --reference D:/refs/first.png --frame-mode first \
    --duration 5 --resolution 1080p --auto-wait
```

- `--frame-mode`：`first`（首帧）｜`first_last`（首尾帧，需 2 张）｜`reference`（内容参考）。
- 传了参考素材时，任务类型自动从 `text2img` / `text2video` 切到 `img2img` / `img2video`。

### 6.2a Spark Hub Seedance 图生视频（自动审核，对用户透明）

Spark Hub 渠道的 Seedance 要求参考素材先通过审核。CLI 在图生视频命令中**自动处理审核**：用 `--reference <本地路径>` 时自动「上传 → 提交审核 → 等待通过 → 生成视频」，用户无需手动调 `audit`。

```bash
# 推荐：一条命令完成上传 → 审核 → 生成视频 → 下载（对用户透明）
opendreamina image2video "镜头缓慢推进，人物微笑" \
    --provider sparkhub-seedance --model doubao_seedance_2 \
    --reference D:/refs/first.png --frame-mode first \
    --duration 5 --resolution 1080p --poll 600 --download-dir D:/out
```

执行时 stderr 会打印透明进度（不污染 stdout 的 JSON）：
```
[opendreamina] 已上传参考素材 D:/refs/first.png → asset_id=...
[opendreamina] 素材 ... 未审核，自动提交审核...
[opendreamina] 素材 ... 审核通过。
[opendreamina] 已入队 task_id=...，等待完成（最多 600s）...
```

如需**复用同一素材**生成多次（避免重复上传 + 审核），可先上传一次，后续用 `--reference-asset`：

```bash
# 1. 上传一次（拿到 asset_id）
ASSET=$(opendreamina upload D:/refs/first.png \
    | python -c "import sys,json;print(json.load(sys.stdin)['asset_id'])")
# 2. 后续多次生成复用同一素材（已审核通过的会自动跳过审核）
opendreamina image2video "..." --provider sparkhub-seedance \
    --reference-asset "$ASSET" --frame-mode first --poll 600
```


### 6.3 多对话分组

```bash
CID=$(opendreamina conversations create --title "产品海报 A 版" \
    | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
opendreamina generate "..." --conversation-id "$CID" --auto-wait
opendreamina conversations get --id "$CID"   # 回顾该对话下的任务
```

### 6.4 失败重试

```bash
opendreamina progress <task_id>     # status: failed，读 error_msg
opendreamina health                 # 若 worker != ok，先修环境
opendreamina retry <task_id>        # 重新入队
opendreamina progress <task_id> --wait
```

---

## 7. 退出码

| 码 | 含义 |
| --- | --- |
| `0` | 成功（含后端返回的业务失败，此时 stdout 是带 `error` 字段的 JSON，stderr 有可读提示） |
| `1` | 参数错误 / 工具未找到等本地校验失败 |
| `2` | 后端调用失败（HTTP 非 2xx / 网络不可达 / 响应无法解析） |
| `3` | 工具执行异常（实现缺陷，请反馈维护者） |

成功 / 业务失败均会在 stdout 输出可解析的 JSON；网络与系统错误会把人类可读信息打到 stderr。

---

## 8. 排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 无法连接后端 | 服务未启动 / 端口不通 | 先跑 `deploy.sh` / `deploy.ps1`，或用 `OPEN_DREAMINA_API_BASE` 指向正确地址 |
| 任务长期 `pending` | Celery worker 未就绪 | `health` 查看 `worker` 字段，检查 worker 容器 |
| 生成立即 `failed` | Provider 未配置 / Key 无效 | `providers` 看 `configured`，在 Web 界面补录 API Key |
| 时长 / 分辨率被拒 | 超出该模型能力 | `models --model-id <id>` 查精确区间后重试 |
| `frame_mode` 报错 | 未提供参考素材 / 张数不对 | 用 `--reference` 提供图片；`first_last` 需 2 张 |
| Spark Hub Seedance 图生视频报「尚未通过审核」 | 素材审核未通过 / 超时未确认 | 图生视频已自动审核；若仍报错，用 `audit <asset_id> --query-only` 查状态，`failed` 则更换素材重新上传 |
| 缺少 `--provider` | 未传且未开 `--auto-provider` | 加 `--auto-provider`，或显式 `--provider <slug>` |

所有后端错误都会被包装成「发生了什么 + 上下文 + 修复建议」的文本，在 stderr 与 stdout 的 JSON `error` 字段中给出。

---

## 9. 设计约束

- **单一事实来源**：模型服务目录直接读取 `frontend/src/config/modelServices.json`，前端新增服务后 CLI 自动生效，不存在两份清单漂移。
- **复用 mcp/ 包**：CLI 与 MCP 服务共用 `mcp/handlers.py`、`mcp/client.py`、`mcp/catalog.py`、`mcp/sizes.py`，能力等价，按场景（命令行 / JSON-RPC）选用。
- **纯标准库**：不引入任何第三方依赖，宿主机无需 `pip install`（与 `AGENTS.md` 第 5 条安全红线一致）。
- **协议纯净**：stdout 只输出 JSON 结果，日志与异常栈一律走 stderr。

### 目录结构

```text
cli/
├── opendreamina.py # 命令行入口（argparse 子命令）
├── __init__.py     # 包定义
└── README.md       # 本文件
```

### 与 MCP 服务的对应关系

| CLI 命令 | 对应 MCP 工具 |
| --- | --- |
| `generate` / `text2image` / `image2image` / `text2video` / `image2video` / `frames2video` | `generate_image` / `generate_video`（按 mode 与参考素材选择） |
| `create-task` | `create_task` |
| `progress`（无 `--wait`） / `query_result`（无 `--wait`） | `get_task` |
| `progress --wait` / `query_result --wait` | `wait_task` |
| `tasks` | `list_tasks` |
| `cancel` | `cancel_task` |
| `retry` | `retry_task` |
| `upload` | `upload_asset` |
| `models` | `list_models` |
| `providers` | `list_providers` |
| `templates` | `list_templates` |
| `health` | `get_health` |
| `conversations` | `create_conversation` / `list_conversations` / `get_conversation` / `update_conversation` / `delete_conversation` |

