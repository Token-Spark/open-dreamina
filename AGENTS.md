# AGENTS.md

> 本文件面向 AI 编码智能体，提供本仓库常用安装与更新操作。人类用户请阅读 [README.md](README.md)。

---

## 项目速览

**Open Dreamina** 是一个自托管的 AIGC 创作工具，以前后端分离 + 任务队列架构运行：

| 组件 | 技术栈 | 目录 | 端口 |
| --- | --- | --- | --- |
| 前端 | React 18 + Vite + TypeScript + Tailwind | `frontend/` | `10131` |
| 后端 API | FastAPI + SQLAlchemy + SQLite | `backend/` | `10130` |
| 任务队列 | Celery + Redis（worker + beat） | `backend/app/worker.py` | — |
| 编排 | Docker Compose（5 个服务） | `docker-compose.yml` | — |

**核心原则：本地部署优先使用 Docker Compose，不要在宿主机直接安装 Python/Node 依赖。**

---

## 首次安装

### 1. 检查 Docker

```bash
docker version            # 已安装且守护进程可连接
docker compose version    # Compose 插件可用（v2 语法）
```

未安装或连不上引擎时，按平台安装 Docker：
- macOS：`brew install --cask docker`，然后 `open /Applications/Docker.app`
- Windows：`winget install -e --id Docker.DockerDesktop`
- Ubuntu/Debian：`curl -fsSL https://get.docker.com | sudo sh`

### 2. 检查端口占用

```bash
lsof -i :10131 -i :10130   # macOS/Linux
netstat -ano | findstr "10131 10130"   # Windows
```

被占用时报告占用进程，请用户释放端口，不要自行 kill 未知进程。

### 3. 一键部署

```bash
bash deploy.sh            # Linux / macOS
pwsh .\deploy.ps1         # Windows
```

脚本自动完成：环境检查 → 生成 `.env`（含随机 `ENCRYPTION_KEY`）→ `docker compose up -d --build` → 健康检查。

**不要手动执行 `docker compose up`**：缺少 `.env` 中的 `ENCRYPTION_KEY` 时后端会拒绝启动。

### 4. 部署后验证

```bash
docker compose ps                                        # 5 个服务全部 Up
curl -fsS http://localhost:10131/api/v1/system/health    # 返回 200
curl -fsS http://localhost:10130/docs                    # Swagger UI 可访问
```

全部通过后告知用户：
- 应用地址：http://localhost:10131
- API 文档：http://localhost:10130/docs
- 数据目录：`./data`（SQLite、生成资产、备份、即梦 CLI 登录态）

---

## 日常更新

```bash
git pull
docker compose up -d --build
```

---

## 本地智能体接入（MCP）

仓库内置 MCP 服务（`mcp/`），把生成图片、生成视频、对话管理等能力暴露为 18 个工具，智能体可直接调用：

```bash
python mcp/server.py --list-tools   # 查看工具清单（自检，不需要后端在线）
python mcp/server.py                # 以 stdio 启动 MCP 服务
```

- **纯 Python 标准库实现，零依赖**：不需要在宿主机 `pip install`（不违反第 5 条安全红线）。
- 需后端已启动且已配置 Provider；`get_health` 工具可查 worker 是否就绪。
- 完整说明（客户端配置、参数、排查）见 [mcp/README.md](mcp/README.md)；提示词优化技能见 `.skills/prompt-optimizer/`。

---

## 命令行接入（opendreamina CLI）

仓库内置命令行工具（`cli/opendreamina.py`），把图片 / 视频生成、任务管理、模型目录等能力暴露为 shell 子命令，外部智能体可直接 `opendreamina ...`，无需写 `python cli/opendreamina.py ...`。

- **纯 Python 标准库实现，零依赖**：与 MCP 服务共用 handler 与目录，宿主机无需 `pip install`（不违反第 5 条安全红线）。
- 完整子命令与参数见 [cli/README.md](cli/README.md)。

### 安装到 PATH

安装脚本只在用户 PATH 目录创建一个调用 `python cli/opendreamina.py` 的 wrapper（约三五行），不安装任何依赖、不需要管理员权限：

```bash
bash cli/install.sh     # Linux / macOS（安装到 ~/.local/bin）
pwsh cli/install.ps1    # Windows（安装到 %USERPROFILE%\bin 并写入用户 PATH）
```

> `install.sh` 若提示 `~/.local/bin` 不在 PATH，按提示把它加进 `~/.bashrc` / `~/.zshrc`；`install.ps1` 写入用户 PATH 后需新开终端生效。仓库移动后重跑对应脚本刷新 wrapper。

### 验证

```bash
opendreamina --version        # 版本自检（不需后端在线）
opendreamina health           # 后端 / DB / Redis / worker 状态
opendreamina providers        # 已配置 Provider
opendreamina models --mode video
```

### 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `OPEN_DREAMINA_API_BASE` | `http://localhost:10130/api/v1` | 后端 API 基地址 |
| `OPEN_DREAMINA_API_TIMEOUT` | `60` | 单次 HTTP 请求超时秒数 |

远程后端：

```bash
OPEN_DREAMINA_API_BASE=http://192.168.1.10:10130/api/v1 opendreamina health
```

### 智能体快速参考

```bash
# 文生图（全自动选服务/模型 + 等待 + 下载）
opendreamina text2image "一只橘猫坐在窗台上，清晨柔光" \
    --auto-provider --auto-model --aspect-ratio 16:9 --resolution 2K \
    --poll 600 --download-dir ./out

# 进度查询 / 异步结果（对齐即梦 CLI）
opendreamina progress <task_id> --wait
opendreamina query_result <task_id> --wait --download-dir ./out
```

> 与 MCP 的关系：MCP（`mcp/server.py`）面向 IDE / 客户端以 JSON-RPC stdio 接入；CLI 面向 shell / 智能体以子命令接入。两者底层调用同一套 handler，能力等价，按场景选用。

---

## 常用运维命令

```bash
docker compose ps                      # 服务状态
docker compose logs -f                 # 全部日志
docker compose logs -f backend         # 单服务日志（backend / celery-worker / celery-beat / frontend / redis）
docker compose restart celery-worker   # 改 worker 代码后重启（celery 无热加载）
docker compose down                    # 停止（数据保留在 ./data）
```

---

## 制片人审阅（外部素材审核）

审核外部文件夹中批量生成的素材，支持标记审核状态（待审/通过/需修改/驳回）与编辑修改意见。外部目录通过 `.env` 只读挂载进容器：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `REVIEW_SOURCES_HOST_PATH` | `./data/review_sources` | 宿主机素材目录绝对路径，**必须用正斜杠**（如 `C:/Users/me/项目素材库`） |
| `REVIEW_SOURCE_ROOTS` | `/app/external_sources` | 容器内允许扫描的根目录，逗号分隔可配多个 |

要点：

- 页面入口：侧边栏「审阅」（路由 `/review`）；API 前缀 `/api/v1/reviews`。
- **只读挂载**：容器内以 `:ro` 挂载外部目录，扫描过程不写入、不修改用户原始素材。
- 缩略图统一生成在 `./data/review_thumbs/`（图片走 Pillow；视频 ffmpeg 抽帧到系统临时目录），**不在素材目录留任何文件**。
- 扫描**递归子目录**，条目 `file_path` 保留相对层级（如 `02_scenes/forge/FORGE_interior.png`）。
- 路径安全：仅允许 `REVIEW_SOURCE_ROOTS` 之下的路径（经 `resolve()` 展开软链接后校验），其余一律拒绝。
- 删除审阅会话只清理审阅记录与缩略图，**不会删除外部素材文件**。

验证：

```bash
curl -fsS http://localhost:10130/api/v1/reviews/folders    # 列出可扫描目录（含两层子目录）
curl -fsS http://localhost:10130/api/v1/reviews/sessions   # 已有审阅会话及汇总
```

> 改 `docker-compose.yml` 的挂载配置后需 `docker compose up -d --build` 重建；只改 `backend/app` 代码时 backend 有 `--reload` 自动生效。

---

## 安全红线

1. **绝不提交或打印 `.env`**：`ENCRYPTION_KEY` 用于加密用户的模型 API Key，泄露即等于泄露所有已存密钥。
2. **绝不使用示例密钥部署**：`.env.example` 中 `ENCRYPTION_KEY` 留空是有意为之，必须由部署脚本生成随机值。
3. **绝不执行破坏性命令**：`docker compose down -v`、`rm -rf data/`、`git clean -fdx` 等需用户显式要求才可执行。
4. **绝不修改 `./data` 目录内容**：这是用户数据，只读不写。
5. **依赖安装只在容器内**：宿主机上不要 `pip install` / `npm install` 本项目依赖。
6. **API Key 处理**：用户提供的模型 API Key 只通过应用「设置 → 服务管理」页面录入，不要写入任何文件或环境变量。

---

## 故障排查速查

| 现象 | 首选动作 |
| --- | --- |
| 健康检查超时 | `docker compose logs backend` 看启动错误；查端口占用 |
| `ENCRYPTION_KEY 未设置` 报错 | `.env` 缺失或为空，重跑部署脚本 |
| 改了 `backend/app` 代码不生效 | backend 有 `--reload` 热加载；celery-worker / celery-beat 需 `docker compose restart <服务>` |
| 前端静态资源/模型列表未更新 | 必须 `docker compose up -d --build` 重建 frontend 镜像 |
| 未安装 Docker | 按「首次安装」分平台安装 |
| Docker 引擎连不上 | 启动 Docker Desktop → Linux 起服务/加用户组 → Windows 更新 WSL 2 |
| 容器内访问宿主机服务 | 用 `host.docker.internal`（compose 已配置 host-gateway） |
