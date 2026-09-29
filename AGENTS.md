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

## 短剧项目制作（opendreamina drama 子命令）

仓库内置短剧制作工具链（`drama/` 包，纯标准库零依赖），把《代号奥林匹斯》实战项目
（40 集 × 90 秒 / 724 镜头 / 1 人 3 天）验证过的制作方法提炼为 9 个命令，全部输出
JSON 供智能体解析。**`drama` 子命令纯本地执行，不需要后端在线**（`qc` 依赖 ffprobe/ffmpeg，缺失时如实降级）。

```bash
opendreamina drama init ./data/review_sources/我的短剧 --title "剧名" --episodes 40   # 建项目骨架（幂等）
opendreamina drama list --project ./我的短剧          # 全部集的状态概览
opendreamina drama lint EP01 --project ./我的短剧      # 分镜规范校验（errors=0 才能生成）
opendreamina drama compile EP01 --project ./我的短剧   # 中文分镜 → Seedance 英文提示词
opendreamina drama spec EP01 --project ./我的短剧 --write   # 生成分集执行规格
opendreamina drama assets EP01 --project ./我的短剧    # 资产引用审计（杜绝无参考生成）
opendreamina drama manifest --project ./我的短剧       # manifest 校验
opendreamina drama qc EP01 --project ./我的短剧        # 成片技术验收（画幅/时长/音轨）
opendreamina drama parse EP01 --shot S01               # 分镜结构化预览
```

要点：

- 项目根解析：`--project` > 环境变量 `DRAMA_PROJECT_ROOT` > 当前目录。
- 中英词库：`{项目根}/tools/maps.py`（init 自动生成模板；lint 会列出未命中词，回填后重跑）。
- 标准目录见 [drama/README.md](drama/README.md)；项目放入 `data/review_sources/` 后即被审阅中心零配置扫描（素材审阅 + 镜头审片）。
- 工具链对项目目录**只读**（`init`/`spec --write` 除外），不触碰 `data/` 下任何现有文件。

### 短剧智能体技能链

`.skills/` 内置六技能覆盖短剧全流程（`SKILL.md` 加载给 AI 助手即用）：

```
drama-production-playbook（制作手册/编排，新开项目从这里进）
  → short-drama-creator（剧本创作，<80 分自动重写）
  → ai-video-director（剧本拆分镜，产出 shots.md）
  → production-orchestrator（批量生成执行，消费 episode_spec）
  → shot-reviewer（镜头初审打分，回写审片中心）
  → prompt-optimizer（单点提示词优化与直执行）
```

各技能均含短剧管线专章（references/drama-*.md），与 `opendreamina drama`
命令、审阅中心数据契约对齐。

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

## 审阅中心（素材审阅 + 镜头审片）

**统一入口**：侧边栏「审阅中心」（路由 `/review`），页内 Tab 切换「素材审阅」与「镜头审片」两种模式（镜头审片为 `/review?mode=shot`）；旧路由 `/shot-review` 自动重定向到 `/review?mode=shot`。前端为一个页面（两模式各自记住选中的会话），后端仍是两套独立 API 与数据表。

### 素材审阅（外部素材审核）

审核外部文件夹中批量生成的素材，支持标记审核状态（待审/通过/需修改/驳回）与编辑修改意见。外部目录通过 `.env` 只读挂载进容器：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `REVIEW_SOURCES_HOST_PATH` | `./data/review_sources` | 宿主机素材目录绝对路径，**必须用正斜杠**（如 `C:/Users/me/项目素材库`） |
| `REVIEW_SOURCE_ROOTS` | `/app/external_sources` | 容器内允许扫描的根目录，逗号分隔可配多个 |

要点：

- API 前缀：`/api/v1/reviews`（页面入口见「审阅中心」）。
- **只读挂载**：容器内以 `:ro` 挂载外部目录，扫描过程不写入、不修改用户原始素材。
  镜头审片功能对（默认同一）素材目录另有可写挂载用于删除废弃视频，见下一节；制片人审阅自身始终只读。
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

### 镜头审片（剧集镜头视频审核）

审核剧集分镜生成的镜头视频：按「集 → 镜」组织、0–100 打分（≥70 通过 / 60–69 需重生成 / <60 需重新设计）、编辑修改意见与精修提示词。

**同镜号多版本合并为同一栏目**：同一镜号的多个视频（不同批次/模型的生成结果）合并在一个栏目内并排比较，可打开同步对比弹窗；为每镜「选定保留版本」（组内互斥），其余版本可一键删除，便于及时清理废弃镜头视频。

镜头审片支持**物理删除**废弃视频文件，因此使用独立的可写挂载（默认与制片人审阅同一宿主机目录）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SHOT_REVIEW_SOURCES_HOST_PATH` | 同 `REVIEW_SOURCES_HOST_PATH` | 宿主机镜头视频目录绝对路径，**必须用正斜杠**；挂载到容器 `/app/shot_sources`（`rw`） |
| `SHOT_REVIEW_SOURCE_ROOTS` | `/app/shot_sources` | 容器内允许扫描/删除的根目录，逗号分隔可配多个 |

要点：

- API 前缀：`/api/v1/shot-reviews`（页面入口见「审阅中心」；旧路由 `/shot-review` 自动重定向）。
- 视图：「栏目分组」（默认，同镜号合并）与「平铺列表」可切换；分组视图有「多版本镜头」筛选，快速定位需清理的镜号。
- **删除分两级**：「仅移出列表」只删审片条目；「删除文件」同时从磁盘永久删除视频（确认框中列出文件与可释放空间）。
- 路径安全（删除双重校验）：会话根目录必须在 `SHOT_REVIEW_SOURCE_ROOTS` 之下，且文件路径必须仍在会话根目录内；越界一律拒绝。
- 只读挂载下「删除文件」会失败并提示改为可写挂载（`SHOT_REVIEW_SOURCES_HOST_PATH`）或到宿主机手动删除后重新扫描；「仅移出列表」不受影响。
- 选定标记存库（`shot_review_items.selected`），评分汇总中含「多版本镜头 / 已选定」计数。

**审阅数据自动归档（markdown 沉淀）**：审阅动作（打分 / 修改意见 / 精修提示词 / 删除废弃版本 / 标记完成）在审阅人无感的情况下自动写入归档目录，按「会话 → 集 → 镜号」组织为纯 markdown + 媒体副本（无数据库表），记录每个镜号「原内容 → 原提示词 → 评分 → 存在的问题 → 修改指引 → 修改后内容 → 修改后提示词」的完整迭代链，供优化 AI 工作流参考：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SHOT_REVIEW_ARCHIVE_ENABLED` | `true` | 总开关；关闭后不写任何档案文件 |
| `SHOT_REVIEW_ARCHIVE_DIR` | `./data/review_archive` | 归档根目录（随 `./data` 一起备份/迁移） |
| `SHOT_REVIEW_ARCHIVE_COPY_MEDIA` | `true` | 是否复制视频副本（删前抢救废弃版本 + 完成时归档每镜首末版本）；关闭后仅写路径引用 |

要点：

- 归档结构：`INDEX.md`（全局索引）→ `{会话文件夹}/session.md`（会话概览 + 镜号索引表）→ `{集}/{镜号}/entry.md`（版本链档案）与 `media/`（媒体副本）。
- **删前抢救**：物理删除废弃视频前自动把文件复制进 `media/`，废弃版本（负样本）数据不丢失；「仅移出列表」只标记状态不复制。
- entry.md 末尾有 HTML 注释形式的机器缓存，保存已离开数据库的历史版本元数据；人和 AI 阅读不可见。
- 所有归档写入失败只记 backend 日志（`审片归档`前缀），绝不影响审片 API 响应。
- 删除审片**会话**时归档文件夹保留（沉淀数据不随会话删除），`INDEX.md` 中标记「会话已删除，档案保留」。

验证：

```bash
curl -fsS http://localhost:10130/api/v1/shot-reviews/folders    # 列出可扫描目录
curl -fsS http://localhost:10130/api/v1/shot-reviews/sessions   # 已有审片会话及汇总
```

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
