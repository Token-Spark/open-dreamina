# Open Dreamina 一键部署脚本（Windows PowerShell）
# 用法: 在项目根目录执行  .\deploy.ps1
# 重要提示:
#   - Windows PowerShell 5.x 对 UTF-8 无 BOM 脚本的中文解析存在兼容性问题。
#   - 推荐安装 PowerShell 7+ 后执行：pwsh .\deploy.ps1
#   - 若只能使用 PowerShell 5，请确保本文件以 UTF-8 with BOM 保存。
#Requires -Version 5.1

param(
    [switch]$Check
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 设置控制台编码，减少中文输出乱码（PowerShell 5 仍需文件带 BOM 才能正确解析）
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Info  { Write-Host "[INFO]  $args" -ForegroundColor Green }
function Write-Warn  { Write-Host "[WARN]  $args" -ForegroundColor Yellow }
function Write-Err   { Write-Host "[ERROR] $args" -ForegroundColor Red }

# ---------------------------------------------------------------------------
# 前置环境检查
# ---------------------------------------------------------------------------

# 1. PowerShell 版本提示
$psVer = $PSVersionTable.PSVersion
if ($psVer.Major -lt 7) {
    Write-Warn "当前使用 Windows PowerShell $($psVer.Major).$($psVer.Minor)。"
    Write-Warn "如遇中文乱码或解析错误，建议安装 PowerShell 7+ 后执行：pwsh .\deploy.ps1"
    Write-Warn "下载地址: https://aka.ms/powershell"
}

# 2. 检查 Docker 命令是否可用
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Err "未检测到 Docker。"
    Write-Err "请先安装 Docker Desktop：https://www.docker.com/products/docker-desktop/"
    Write-Err "安装完成后重启终端并重新执行本脚本。"
    exit 1
}

# 3. 检查 Docker 守护进程是否响应（避免 Docker Desktop 已安装但引擎未启动的情况）
try {
    $dockerVersion = docker version --format '{{.Server.Version}}' 2>$null
    if ([string]::IsNullOrWhiteSpace($dockerVersion)) { throw "docker version 无返回" }
    Write-Info "Docker 引擎状态正常（版本 $dockerVersion）。"
} catch {
    Write-Err "Docker 命令存在，但无法连接到 Docker 引擎。"
    Write-Err "常见原因:"
    Write-Err "  1. Docker Desktop 尚未启动完成；"
    Write-Err "  2. Docker Desktop 使用 WSL 2 后端时，WSL 2 内核未更新或 WSL 发行版异常；"
    Write-Err "  3. 在 WSL 内部单独安装了 Docker Engine，与 Docker Desktop 的 WSL 2 后端冲突。"
    Write-Err ""
    Write-Err "建议操作（按顺序尝试）:"
    Write-Err "  1. 打开 Docker Desktop，等待左下角显示 Engine running；"
    Write-Err "  2. 更新 WSL 2 内核并重启:"
    Write-Err "       wsl --update"
    Write-Err "       wsl --shutdown"
    Write-Err "     然后重启 Docker Desktop；"
    Write-Err "  3. 若此前在 WSL 内独立安装过 Docker，请在对应 WSL 发行版内卸载或禁用:"
    Write-Err "       wsl -d <DistroName> -u root -- sh -c 'systemctl stop docker || true; apt-get remove -y docker-ce docker-ce-cli containerd.io || true'"
    Write-Err "  4. 仍无法解决请参考: https://docs.docker.com/desktop/troubleshoot/overview/"
    exit 1
}

# 4. 检查 docker compose 插件
docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Err "未检测到 docker compose 插件，请升级 Docker Desktop。"
    exit 1
}

# 5. WSL 2 后端健康提示（仅 Docker Desktop on Windows）
try {
    $wslBackend = docker info --format '{{.DriverStatus}}' 2>$null | Select-String -Pattern "wsl"
    if ($wslBackend) {
        Write-Info "Docker 当前使用 WSL 2 后端。"
    }
} catch { }

# 6. 若仅检查环境，到此结束
if ($Check) {
    Write-Info "环境检查通过，可直接运行 .\deploy.ps1 开始部署。"
    exit 0
}

# ---------------------------------------------------------------------------
# 生成 .env
# ---------------------------------------------------------------------------
if (-not (Test-Path .env)) {
    Write-Info "未发现 .env，正在生成（含随机 ENCRYPTION_KEY）..."
    $key = -join ((48..57) + (97..102) | Get-Random -Count 64 | ForEach-Object { [char]$_ })
    @"
# 用于加密 API Key 的密钥（首次部署自动生成，请妥善保管，勿泄露）
ENCRYPTION_KEY=$key
"@ | Set-Content -Path .env -Encoding UTF8
    Write-Info ".env 已生成"
} else {
    Write-Info "已存在 .env，跳过生成"
}

# ---------------------------------------------------------------------------
# 构建并启动
# ---------------------------------------------------------------------------
Write-Info "正在构建并启动服务（首次构建需下载依赖，请耐心等待）..."
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Err "启动失败，请查看上方日志。"
    Write-Err "常见排查命令:"
    Write-Err "  docker compose logs -f"
    Write-Err "  docker compose build --no-cache"
    exit 1
}

# ---------------------------------------------------------------------------
# 等待健康检查
# ---------------------------------------------------------------------------
Write-Info "等待服务就绪..."
$port = 10131
for ($i = 0; $i -lt 60; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:$port/api/v1/system/health" -UseBasicParsing -TimeoutSec 3
        if ($resp.StatusCode -eq 200) {
            Write-Info "服务已就绪！"
            Write-Host ""
            Write-Host "=============================================="
            Write-Host "  Open Dreamina 已启动"
            Write-Host "  访问地址: http://localhost:$port"
            Write-Host "  API 文档: http://localhost:10130/docs"
            Write-Host "=============================================="
            exit 0
        }
    } catch { }
    Start-Sleep -Seconds 2
}

Write-Warn "健康检查超时，请查看日志：docker compose logs -f"
exit 1
