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

## 常用运维命令

```bash
docker compose ps                      # 服务状态
docker compose logs -f                 # 全部日志
docker compose logs -f backend         # 单服务日志（backend / celery-worker / celery-beat / frontend / redis）
docker compose restart celery-worker   # 改 worker 代码后重启（celery 无热加载）
docker compose down                    # 停止（数据保留在 ./data）
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
