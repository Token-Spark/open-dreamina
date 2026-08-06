# Open Dreamina 一键部署脚本（Windows PowerShell）
# 用法: 在项目根目录执行  .\deploy.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Write-Info  { Write-Host "[INFO]  $args" -ForegroundColor Green }
function Write-Warn  { Write-Host "[WARN]  $args" -ForegroundColor Yellow }
function Write-Err   { Write-Host "[ERROR] $args" -ForegroundColor Red }

# 1. 检查 Docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Err "未检测到 Docker，请先安装 Docker Desktop：https://www.docker.com/products/docker-desktop/"
    exit 1
}

# 2. 检查 docker compose 插件
docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Err "未检测到 docker compose 插件，请升级 Docker Desktop。"
    exit 1
}

# 3. 生成 .env（首次部署）
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

# 4. 构建并启动（--build 确保前端 modelServices.json 等静态资源为最新）
Write-Info "正在构建并启动服务（首次构建需下载依赖，请耐心等待）..."
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Write-Err "启动失败，请查看上方日志。"; exit 1 }

# 5. 等待健康检查
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
