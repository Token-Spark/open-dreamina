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

## 已接入模型

| 模型名称 | 简介 |
| --- | --- |
| GPT Image 2 | OpenAI 图片生成模型，支持文生图与图生图，可经 OpenRouter 等兼容网关接入。 |
| Seedream 5.0 | 火山引擎豆包文生图模型，支持高质量图像生成与编辑。 |
| Seedance 2.0 | 火山引擎豆包视频生成模型，支持文生视频与图生视频。 |
| Seedance 2.5 | 火山引擎豆包视频生成模型，支持文生视频与图生视频。 |
| 即梦 Seedream（CLI） | 通过本机即梦 CLI 生成图片，复用本机登录态，无需 API Key。 |
| 即梦 Seedance（CLI） | 通过本机即梦 CLI 生成视频，复用本机登录态，无需 API Key。 |
| Seedream（Spark Hub 中转） | 经 Spark Hub 中转站调用 Seedream 生图模型（Seedream 5 / 5 Pro），统一异步任务模式。 |
| Seedance（Spark Hub 中转） | 经 Spark Hub 中转站调用 Seedance 生视频模型（Seedance 2 / 2 Fast / 2 Mini / 2.5），统一异步任务模式。 |
| Stability AI | Stability 图像生成模型服务。 |
| 通义万相 | 阿里云通义万相图像/视频生成模型服务。 |
| 可灵 | 快手可灵视频生成模型服务。 |

---

## 特性

- **干净无广告** —— 专注创作，没有干扰
- **设计克制** —— 谨慎增加按钮和确认环节
- **免注册开箱即用** —— 无需注册即可使用
- **数据本地保存** —— 数据保存在本地，无需二次下载
- **一键部署** —— 支持 Windows / Linux / macOS，一键启动
- **模型灵活接入** —— 自由选择 AIGC 模型服务，提供 API 调用记录统计与分析
- **画布工作流** —— 节点式可视化画布，自由编排图片/视频生成流程，节点间连线传递参考素材
- **3D 导演台** —— 内嵌 3D 角色姿态编辑器，采集镜头画面作为生成参考图
- **内置智能体技能** —— 提供短剧创作、分镜导演、制片编排三套 AI Agent 技能，覆盖从剧本到成片的全流程
- **性能与体验领先** —— 核心功能的性能和使用体验达到同类产品领先水平（排除模型服务带来的差异）

![视频生成示例](frontend/src/static/video-generation-sample-01.png)

---

## 快速开始

### 本地智能体一键部署

> 使用 codex, workbuddy 等 AI 智能体，复制下面这句话发给它，即可自动完成安装部署：
>
> ```text
> 克隆 https://github.com/Token-Spark/open-dreamina 到本地，按照仓库 AGENTS.md 引导完成部署，最后告诉我访问地址。
> ```

### 脚本部署
服务通过 Docker Compose 编排，包含前端、后端、Celery 任务队列与 Redis。首次部署只需一条命令，脚本会自动完成：

> 环境检查 → 生成 `.env`（含随机加密密钥）→ 构建镜像 → 启动服务 → 健康检查

**Linux / macOS 脚本部署**
```bash
bash deploy.sh
```

**Windows 脚本部署（推荐三步走）**

1. **安装/确认 Docker Desktop**：从 [Docker 官网](https://www.docker.com/products/docker-desktop/) 下载安装，启动后等待左下角显示 `Engine running`。
2. **（推荐）安装 PowerShell 7**：避免 Windows 自带 PowerShell 5 的中文编码兼容问题。安装后执行：
   ```powershell
   pwsh .\deploy.ps1
   ```
   下载地址：[https://aka.ms/powershell](https://aka.ms/powershell)
3. **直接部署**：若坚持使用 PowerShell 5，请在项目根目录执行：
   ```powershell
   .\deploy.ps1
   ```

> 首次部署前，可先运行环境检查（不构建镜像）：
> ```powershell
> .\deploy.ps1 -Check
> ```
>
> 若提示脚本被禁止执行，先运行 `Set-ExecutionPolicy -Scope Process Bypass` 再执行。



### 环境要求

- 已安装 [Docker](https://docs.docker.com/get-docker/)（Windows / macOS 使用 Docker Desktop，Linux 使用 Docker Engine）
- Docker Compose 插件（Docker Desktop 与新版 Docker Engine 已内置）
- **Windows 用户**：Docker Desktop 默认使用 WSL 2 后端，请确保：
  - 系统已启用虚拟化（Hyper-V / 虚拟机平台）；
  - WSL 2 内核已更新到最新版（首次安装 Docker Desktop 时通常会提示）；
  - 不建议在 WSL 发行版内部再单独安装 Docker Engine，否则可能与 Docker Desktop 的 WSL 2 后端冲突，导致引擎无法连接。
- 端口 `10131`（前端）、`10130`（后端）未被占用

### Windows 常见问题

| 现象 | 可能原因 | 解决方案 |
| --- | --- | --- |
| 运行 `deploy.ps1` 后出现中文乱码或解析错误 | Windows PowerShell 5 默认按 GBK 代码页读取无 BOM 的 UTF-8 脚本 | 安装 PowerShell 7 后执行 `pwsh .\deploy.ps1`；或确保 `deploy.ps1` 以 UTF-8 with BOM 保存 |
| Docker 已安装，但脚本提示"无法连接到 Docker 引擎" | Docker Desktop 引擎未启动，或 WSL 2 后端异常 | 1. 打开 Docker Desktop 等待左下角显示 `Engine running`；<br>2. 执行 `wsl --update && wsl --shutdown` 后重启 Docker Desktop；<br>3. 若 WSL 内独立安装过 Docker，请卸载或禁用 |
| Docker Desktop 弹出"计算机无法连接到远程计算机" | WSL 2 后端初始化失败或 RemoteApp/RDP 相关组件异常 | 执行 `wsl --update` 更新 WSL 2 内核；确保 Hyper-V 与虚拟机平台功能已启用；必要时重启 Windows |
| 健康检查超时 | 服务首次启动较慢，或端口被占用 | 执行 `docker compose logs -f` 查看具体错误；确认端口 `10131`/`10130` 未被占用 |

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

## 使用引导

### 首次使用

打开 <http://localhost:10131> 即可直接使用，无需注册登录。所有数据（对话、生成记录、API Key）均保存在本地 `./data` 目录。

### 配置模型服务

进入「设置 → 服务管理」，选择并激活你使用的 AIGC 模型服务（如即梦、通义万相、可灵、Stability 等），填入对应的 API Key。API Key 会使用 `.env` 中的 `ENCRYPTION_KEY` 加密后存储。

### 云存储配置（可选）

部分模型服务（如 Seedance）在生成视频时，要求参考素材（真人、虚拟人像等）**先通过上游审核**，审核环节需要提交素材的公网可访问 URL。由于本项目素材默认保存在本地磁盘，为满足审核对公网链接的要求，集成了七牛云对象存储用于临时暴露本地素材：

- **配置 XX 云后**：素材会自动上传到指定存储桶，并设置生命周期规则（默认 14 天后自动删除），审核通过后即可用于视频生成；
- **未配置时**：回退到本服务自身的素材下载端点，需保证部署环境具备公网可达性（适合具备公网 IP/域名的自部署场景）。

在 `.env` 中填写以下配置即可启用（字段均为可选，留空即不启用云存储）：

```bash
QINIU_ACCESS_KEY=你的七牛云 AccessKey
QINIU_SECRET_KEY=你的七牛云 SecretKey
QINIU_BUCKET=你的存储桶名称
QINIU_DOMAIN=https://你的七牛云绑定域名
QINIU_AUDIT_EXPIRE_DAYS=14   # 临时素材保留天数，到期自动删除
```

> 审核状态说明：上传参考素材后会自动发起审核，状态依次为「审核中（pending）」→「已通过（active）」/「未通过（failed）」，仅「已通过」的素材可用于生成。

### 即梦 CLI（可选）

若使用即梦 CLI 作为模型服务，需在运行 `celery-worker` 的机器上安装 CLI 并完成登录：

1. 进入「设置 → 服务管理 → 即梦 CLI」，点击「安装」；
2. 安装完成后点击「登录」，按页面提示完成授权；
3. 登录态保存在 `./data/dreamina-home`，容器重建后不丢失。

> 注意：CLI 需安装在 celery-worker 所在机器上，且 `dreamina login` 需手动完成授权（自动发起的登录链接可能存在兼容问题）。

### 数据备份

进入「设置」可手动触发数据库备份，备份文件保存在 `./data/backups`（默认保留最近 3 份）。

---

## 进阶功能

### 画布工作流

画布是一个节点式的可视化创作空间，你可以在无限画布上自由摆放节点、连线传递素材，编排复杂的生成流程。

**核心能力：**

- **节点类型**：素材节点（图片/视频/音频）、图片生成节点、视频生成节点、备注节点
- **连线传参**：将素材节点的输出端口连接到生成节点的参考输入端口，素材自动作为参考图传递
- **多节点编排**：同时管理多个生成节点，实现"先生成角色图 → 再图生视频"等链式流程
- **模板快速开始**：内置空白画布、单图生成、图生视频、分镜批量等模板
- **自动保存**：编辑过程中每 5 秒自动保存，版本管理防止并发冲突

**简单使用：**

1. 在侧边栏点击「画布」进入画布列表页；
2. 点击「新建画布」，选择模板（如「图生视频」）；
3. 进入画布编辑器后，通过工具栏「添加节点」或**右键空白处**添加节点；
4. 将素材节点右侧输出端口拖拽连线到生成节点左侧输入端口，素材自动传递为参考图；
5. 在生成节点中输入提示词、选择模型，点击生成；
6. 生成结果可直接在节点内预览，也可作为下游节点的输入继续编排。

### 3D 导演台

3D 导演台是一个内嵌的 3D 角色姿态编辑器，可以在 3D 场景中调整角色姿势、机位角度，并采集画面作为 AIGC 生成的参考图。

**核心能力：**

- **3D 角色摆姿**：在 3D 场景中调整角色姿态、表情和镜头角度
- **一键采集**：将当前 3D 画面截图采集为参考图，自动上传并设为素材
- **嵌入式协议**：通过 postMessage 受控协议与宿主应用通信，支持自定义部署地址

**简单使用：**

1. 在画布中添加「素材」节点，点击节点上的场记板图标打开导演台（需后端配置 `director_desk_url`）；
2. 在导演台 3D 场景中调整角色姿态与相机角度；
3. 点击顶部「采集截图」按钮，画面将自动截图并上传为素材；
4. 采集的素材可直接用于后续图片或视频生成的参考图。

> 导演台默认使用在线版本，可在 `backend/app/config.py` 中修改 `director_desk_url` 指向自托管部署地址。

### 内置智能体技能

项目内置三套 AI Agent 技能，覆盖从剧本创作到成片交付的完整 AIGC 影视生产流程。技能定义位于 `.skills/` 目录，可被 AI 编码助手（如 Codex、Trae 等）加载使用。

#### 短剧创作（short-drama-creator）

负责从零开始创作短剧剧本，覆盖高概念提炼、角色设计、分集规划、剧本撰写、自动评分与重写。

**工作流程：** 提炼 Logline → 定义核心人物与冲突 → 建立世界规则 → 设计 Episode Arc → Scene Breakdown → 撰写剧本 → 自动审稿评分（100 分制）→ 低于 80 分自动重写

**使用方式：** 将 `.skills/short-drama-creator/SKILL.md` 加载给 AI 助手，输入创作需求（题材、集数、风格），技能会按 12 步流程输出完整的短剧剧本与质量评分。

#### 分镜导演（ai-video-director）

将已有剧本转化为可执行的视觉生产方案——把"剧本想表达什么"转换成"镜头应该看到什么"。

**工作流程：** 剧本拆 Scene → 每 Scene 拆 Beat → 每 Beat 转 Shot → 选景别与构图 → 建立角色/场景一致性资产 → 编写 Image/Video Prompt → 设计声音与剪辑 → 关键帧 QC → 输出镜头表与逐镜头生成卡

**使用方式：** 将 `.skills/ai-video-director/SKILL.md` 加载给 AI 助手，提供短剧剧本作为输入，技能会输出包含景别、构图、摄影机运动、Prompt 等完整字段的镜头表和生成卡，可直接用于 AIGC 图片/视频生成。

#### 制片编排（production-orchestrator）

将导演的分镜方案转化为可执行、可追踪、可质控的生成任务，负责资产管理、依赖编排、模型路由、质量管控与交付。

**工作流程：** 解析导演分镜 → 建立资产注册表与依赖图 → 锁定关键资产 → 编译 Prompt 与模型路由 → 关键帧门禁 → 视频生成与参考传播 → 失败处理与重试 → 质量管控 → 预算追踪 → 最终交付

**使用方式：** 将 `.skills/production-orchestrator/SKILL.md` 加载给 AI 助手，提供导演台输出的镜头表，技能会输出生产清单（Manifest）、生成任务编排方案和 QC 决策，指导从关键帧到成片的全流程执行。

> 三套技能可串联使用：**短剧创作** 产出剧本 → **分镜导演** 产出镜头表 → **制片编排** 执行生产，形成从创意到成片的完整闭环。

---

## 社区交流

<div align="center">
  <p>扫描下方二维码，加入飞书话题群，获取使用帮助与最新动态：</p>
  <img src="frontend/src/static/lark-group-qrcode.png" alt="飞书群二维码" width="280" />
</div>
