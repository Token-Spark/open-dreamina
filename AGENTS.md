# AGENTS.md

> 本文件面向 AI 编码智能体（ChatGPT、Codex、Cursor、Claude 等），提供在本仓库中安全、高效工作的全部必要信息。
> 人类用户请阅读 [README.md](README.md)。

---

## 项目速览

**Open Dreamina** 是一个自托管的 AIGC 创作工具（受即梦启发），以前后端分离 + 任务队列架构运行：

| 组件 | 技术栈 | 目录 | 端口 |
| --- | --- | --- | --- |
| 前端 | React 18 + Vite + TypeScript + Tailwind | `frontend/` | `10131` |
| 后端 API | FastAPI + SQLAlchemy + SQLite | `backend/` | `10130` |
| 任务队列 | Celery + Redis（worker + beat） | `backend/app/worker.py` | — |
| 编排 | Docker Compose（5 个服务） | `docker-compose.yml` | — |

**核心原则：本地部署优先使用 Docker Compose，不要在宿主机直接安装 Python/Node 依赖。**

---

## 环境配置（智能体必读）

### 前置检查与 Docker 安装（按顺序执行）

#### 第一步：检查 Docker 状态

```bash
docker version            # 已安装且守护进程可连接
docker compose version    # Compose 插件可用（v2 语法，非 docker-compose）
```

根据结果分流处理：

| 检查结果 | 动作 |
| --- | --- |
| 两条命令均正常 | 跳到「端口占用检查」 |
| `docker` 命令不存在 | 进入「第二步：安装 Docker」 |
| 命令存在但连不上引擎 | 进入「第三步：修复引擎连接」 |
| 只有 `docker-compose`（带横杠）可用 | 版本过旧，按第二步升级 Docker |

#### 第二步：安装 Docker（按用户平台选择，先确认再执行）

**安装前必须向用户确认平台与方式，涉及系统级安装一律征得用户同意。**

**macOS**（优先 Homebrew，无 brew 则给官方下载链接）：

```bash
# 方式一：Homebrew（推荐，一条命令）
brew install --cask docker
# 安装后必须启动一次：open /Applications/Docker.app
# 等待菜单栏鲸鱼图标稳定（Engine running）

# 方式二：手动下载
# 告知用户访问 https://www.docker.com/products/docker-desktop/ 下载 Mac 版
# 注意区分芯片：Apple Silicon 选 Apple Chip，Intel 选 Intel Chip
uname -m   # arm64 = Apple Silicon，x86_64 = Intel
```

**Windows**：

```powershell
# 方式一：winget（推荐，Windows 10 21H2+ / 11 自带）
winget install -e --id Docker.DockerDesktop

# 方式二：手动下载
# 告知用户访问 https://www.docker.com/products/docker-desktop/ 下载 Windows 版
```

Windows 安装后必须检查：
1. 启动 Docker Desktop，等左下角显示 `Engine running`（首次启动需 1-2 分钟）；
2. 若提示 WSL 2 相关错误，执行 `wsl --update && wsl --shutdown` 后重启 Docker Desktop；
3. 若提示虚拟化未启用，引导用户在 BIOS 开启 VT-x/AMD-V，并启用「Hyper-V」与「虚拟机平台」Windows 功能；
4. **不要**在 WSL 发行版内再装 Docker Engine，会与 Docker Desktop 后端冲突。

**Linux**（识别发行版后给对应命令）：

```bash
# 识别发行版
cat /etc/os-release | grep -E "^ID="

# Ubuntu / Debian：用官方一键脚本（最省事）
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER   # 免 sudo 运行 docker，需重新登录生效

# 其他发行版（Fedora/CentOS/Arch 等）：给用户官方文档链接
# https://docs.docker.com/engine/install/
```

> 安全提示：`curl | sh` 方式需向用户说明脚本来源是 Docker 官方（get.docker.com），征得同意后再执行；介意的话改用各发行版官方仓库安装方式。

### 第三步：修复引擎连接（已安装但连不上）

按顺序尝试，每步后重新执行 `docker version` 验证：

1. **macOS/Windows**：启动 Docker Desktop（`open /Applications/Docker.app` 或开始菜单启动），等待 `Engine running`；
2. **Linux**：`sudo systemctl start docker && sudo systemctl enable docker`；权限拒绝时检查用户是否在 docker 组（`groups | grep docker`），不在则 `sudo usermod -aG docker $USER` 并重新登录；
3. **Windows WSL 2 异常**：`wsl --update && wsl --shutdown`，重启 Docker Desktop；
4. 仍失败：执行 `docker info` 收集错误输出，原样报告给用户，不要继续盲目重试。

#### 端口占用检查

```bash
# 前端 10131 / 后端 10130 必须空闲
lsof -i :10131 -i :10130   # macOS/Linux
netstat -ano | findstr "10131 10130"   # Windows
```

被占用时：报告占用进程，请用户释放端口；**不要**自行 kill 未知进程。

### 一键部署（唯一推荐路径）

```bash
# Linux / macOS
bash deploy.sh

# Windows（推荐 PowerShell 7）
pwsh .\deploy.ps1
# 或 PowerShell 5（脚本需 UTF-8 with BOM）
.\deploy.ps1
```

脚本自动完成：环境检查 → 生成 `.env`（含随机 `ENCRYPTION_KEY`）→ `docker compose up -d --build` → 健康检查（轮询 `http://localhost:10131/api/v1/system/health`，最长 120 秒）。

**不要手动执行 `docker compose up`**：缺少 `.env` 中的 `ENCRYPTION_KEY` 时后端会拒绝启动（compose 文件中 `${ENCRYPTION_KEY:?...}` 强制校验）。

### 部署后验证（必须全部通过才算完成）

```bash
docker compose ps                                        # 5 个服务全部 Up
curl -fsS http://localhost:10131/api/v1/system/health    # 返回 200
curl -fsS http://localhost:10130/docs                    # Swagger UI 可访问
```

全部通过后，告知用户：
- 应用地址：http://localhost:10131
- API 文档：http://localhost:10130/docs
- 数据目录：`./data`（SQLite、生成资产、备份、即梦 CLI 登录态）

---

## 安全红线（不可违反）

1. **绝不提交或打印 `.env`**：`ENCRYPTION_KEY` 用于加密用户的模型 API Key，泄露即等于泄露所有已存密钥。日志输出前检查是否包含该值。
2. **绝不使用示例密钥部署**：`.env.example` 中 `ENCRYPTION_KEY` 留空是有意为之，必须由部署脚本生成随机值。
3. **绝不执行破坏性命令**：`docker compose down -v`（删除 redis 卷）、`rm -rf data/`、`git clean -fdx` 等需用户显式要求才可执行。
4. **绝不修改 `./data` 目录内容**：这是用户数据（数据库、生成图片/视频、备份），只读不写。
5. **依赖安装只在容器内**：宿主机上不要 `pip install` / `npm install` 本项目依赖；本地开发环境搭建见下文「本地开发（可选）」。
6. **API Key 处理**：用户提供的模型 API Key 只通过应用「设置 → 服务管理」页面录入（前端加密存储），不要写入任何文件或环境变量。

---

## 常用命令

### 运维（Docker）

```bash
docker compose ps                      # 服务状态
docker compose logs -f                 # 全部日志
docker compose logs -f backend         # 单服务日志（backend / celery-worker / celery-beat / frontend / redis）
docker compose restart celery-worker   # 改 worker 代码后重启（celery 无热加载）
docker compose up -d --build           # 更新部署（重建镜像）
docker compose down                    # 停止（数据保留在 ./data）
```

### 本地开发（可选，非部署必需）

仅在用户明确要求"本地开发/调试"时执行：

```bash
# 后端（Python 3.11+）
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 10130

# 前端（Node 18+）
cd frontend
npm ci                # 用 ci 而非 install，严格按 lock 文件安装
npm run dev           # Vite dev server
npm run typecheck     # TypeScript 检查
npm run build         # 生产构建（含 tsc -b）
```

注意：本地开发仍需 Redis（可单独 `docker compose up -d redis`），且需自行准备 `.env`。

### 测试与检查

```bash
cd frontend && npm run typecheck    # 前端类型检查（提交前必跑）
cd backend && python perf_test.py   # 后端性能测试脚本（需服务已启动）
```

后端无单元测试套件；验证后端改动以 `docker compose up -d --build` 后健康检查 + 手动调 API 为准。

---

## 代码约定

- **后端**：FastAPI 路由放 `backend/app/routers/`，业务逻辑放 `services/`，模型服务提供商放 `providers/`（继承 `base.py`，经 `factory.py` 注册）。异步任务一律走 Celery，不要在 API 请求线程中执行长任务。
- **前端**：页面在 `frontend/src/pages/`，可复用组件在 `components/ui/`（仿 shadcn 风格），状态用 zustand（`stores/`），服务端数据用 React Query（`hooks/`）。新增模型服务需同步更新 `src/config/modelServices.json`。
- **配置**：所有环境变量经 `backend/app/config.py`（pydantic-settings）读取，不要散落 `os.environ` 调用。
- **注释与提交信息**：使用中文，简洁说明"为什么"而非"是什么"。

---

## 故障排查速查

| 现象 | 首选动作 |
| --- | --- |
| 健康检查超时 | `docker compose logs backend` 看启动错误；查端口占用 |
| `ENCRYPTION_KEY 未设置` 报错 | `.env` 缺失或为空，重跑部署脚本 |
| 改了 `backend/app` 代码不生效 | backend 有 `--reload` 热加载；celery-worker / celery-beat 需 `docker compose restart <服务>` |
| 前端静态资源/模型列表未更新 | 必须 `docker compose up -d --build` 重建 frontend 镜像 |
| Windows 脚本中文乱码 | 改用 PowerShell 7：`pwsh .\deploy.ps1` |
| 未安装 Docker | 按「环境配置」第二步分平台安装（macOS 用 brew、Windows 用 winget、Ubuntu/Debian 用官方脚本） |
| Docker 引擎连不上 | 按「环境配置」第三步顺序修复：启动 Docker Desktop → Linux 起服务/加用户组 → Windows 更新 WSL 2 |
| 容器内访问宿主机服务 | 用 `host.docker.internal`（compose 已配置 host-gateway） |

---

## 智能体行为准则

- **最小干预**：部署只需跑脚本 + 验证，不要"顺手"优化配置、升级依赖或重构代码。
- **失败即报告**：任何检查/命令失败，原样报告错误输出并给出上表对应建议，不要盲目重试超过 2 次。
- **可观测**：每完成一个阶段（检查 → 部署 → 验证），用一句话向用户汇报状态。
- **不臆造**：本文未覆盖的操作（如新增依赖、改架构），先读相关代码再行动，不确定就问用户。
