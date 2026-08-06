<div align="center">
  <img src="frontend/src/static/logo.jpg" alt="Open Dreamina Logo" width="120" />

  <h1>Open Dreamina</h1>

  <p><strong>简单够用的 AIGC 创作工具</strong></p>

  <p>
    受 <a href="https://jimeng.jianying.com/">即梦</a> 启发而设计开发，以浏览器应用的形式提供服务。
  </p>

  <p>
    <img src="https://img.shields.io/badge/license-Apache%202.0-blue" alt="License" />
    <img src="https://img.shields.io/badge/docker-compose-green" alt="Docker Compose" />
    <img src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey" alt="Platform" />
  </p>
</div>

---

## ✨ 产品特点

- 🧹 **干净无广告** —— 专注创作，没有干扰
- 🚀 **免注册开箱即用** —— 无需注册即可使用
- 💾 **数据本地保存** —— 数据保存在本地，无需二次下载
- 🎯 **设计克制** —— 谨慎增加按钮和确认环节
- 📦 **一键部署** —— 支持 Windows / Linux / macOS，一键启动
- 🔌 **模型灵活接入** —— 自由选择 AIGC 模型服务，提供 API 调用记录统计与分析
- ⚡ **性能与体验领先** —— 核心功能的性能和使用体验达到同类产品领先水平（排除模型服务带来的差异）

---

## 🚀 快速开始

服务通过 Docker Compose 编排，包含前端、后端、Celery 任务队列与 Redis。首次部署只需一条命令，脚本会自动完成：

> 环境检查 → 生成 `.env`（含随机加密密钥）→ 构建镜像 → 启动服务 → 健康检查

### 环境要求

- 已安装 [Docker](https://docs.docker.com/get-docker/)（Windows / macOS 使用 Docker Desktop，Linux 使用 Docker Engine）
- Docker Compose 插件（Docker Desktop 与新版 Docker Engine 已内置）
- 端口 `10131`（前端）、`10130`（后端）未被占用

### 一键部署

**Linux / macOS**

```bash
bash deploy.sh
```

**Windows**

在项目根目录打开 PowerShell，执行：

```powershell
.\deploy.ps1
```

> 💡 若提示脚本被禁止执行，先运行 `Set-ExecutionPolicy -Scope Process Bypass` 再执行。

### 部署完成后

| 操作 | 命令 / 地址 |
| --- | --- |
| 访问应用 | <http://localhost:10131> |
| API 文档 | <http://localhost:10130/docs> |
| 查看日志 | `docker compose logs -f` |
| 停止服务 | `docker compose down` |
| 更新服务 | 重新执行部署脚本（`--build` 会重建镜像，确保前端静态资源为最新） |

### 常用运维命令

```bash
# 查看各服务状态
docker compose ps

# 重启某个服务（如 celery-worker 改代码后）
docker compose restart celery-worker

# 查看某个服务日志
docker compose logs -f backend

# 停止并删除容器（数据保留在 ./data 目录）
docker compose down
```

---

## 📖 使用引导

### 1️⃣ 首次使用

打开 <http://localhost:10131> 即可直接使用，无需注册登录。所有数据（对话、生成记录、API Key）均保存在本地 `./data` 目录。

### 2️⃣ 配置模型服务

进入「设置 → 服务管理」，选择并激活你使用的 AIGC 模型服务（如即梦、通义万相、可灵、Stability 等），填入对应的 API Key。API Key 会使用 `.env` 中的 `ENCRYPTION_KEY` 加密后存储。

### 3️⃣ 即梦 CLI（可选）

若使用即梦 CLI 作为模型服务，需在运行 `celery-worker` 的机器上安装 CLI 并完成登录：

1. 进入「设置 → 服务管理 → 即梦 CLI」，点击「安装」；
2. 安装完成后点击「登录」，按页面提示完成授权；
3. 登录态保存在 `./data/dreamina-home`，容器重建后不丢失。

> ⚠️ 注意：CLI 需安装在 celery-worker 所在机器上，且 `dreamina login` 需手动完成授权（自动发起的登录链接可能存在兼容问题）。

### 4️⃣ 数据备份

进入「设置」可手动触发数据库备份，备份文件保存在 `./data/backups`（默认保留最近 3 份）。

---

## 💬 社区交流

<div align="center">
  <p>扫描下方二维码，加入飞书话题群，获取使用帮助与最新动态：</p>
  <img src="frontend/src/static/lark-group-qrcode.png" alt="飞书群二维码" width="280" />
</div>
