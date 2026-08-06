#!/usr/bin/env bash
# Open Dreamina 一键部署脚本（Linux / macOS）
# 用法: bash deploy.sh
set -euo pipefail

cd "$(dirname "$0")"

# 颜色输出
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# 1. 检查 Docker
if ! command -v docker >/dev/null 2>&1; then
  error "未检测到 Docker，请先安装 Docker：https://docs.docker.com/get-docker/"
  exit 1
fi

# 2. 检查 docker compose 插件
if ! docker compose version >/dev/null 2>&1; then
  error "未检测到 docker compose 插件，请升级 Docker 或安装 compose 插件。"
  exit 1
fi

# 3. 生成 .env（首次部署）
if [ ! -f .env ]; then
  info "未发现 .env，正在生成（含随机 ENCRYPTION_KEY）..."
  KEY=$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')
  cat > .env <<EOF
# 用于加密 API Key 的密钥（首次部署自动生成，请妥善保管，勿泄露）
ENCRYPTION_KEY=${KEY}
EOF
  info ".env 已生成"
else
  info "已存在 .env，跳过生成"
fi

# 4. 构建并启动（--build 确保前端 modelServices.json 等静态资源为最新）
info "正在构建并启动服务（首次构建需下载依赖，请耐心等待）..."
docker compose up -d --build

# 5. 等待健康检查
info "等待服务就绪..."
FRONTEND_PORT=10131
for i in $(seq 1 60); do
  if curl -fsS "http://localhost:${FRONTEND_PORT}/api/v1/system/health" >/dev/null 2>&1; then
    info "服务已就绪！"
    echo
    echo "=============================================="
    echo "  Open Dreamina 已启动"
    echo "  访问地址: http://localhost:${FRONTEND_PORT}"
    echo "  API 文档: http://localhost:10130/docs"
    echo "=============================================="
    exit 0
  fi
  sleep 2
done

warn "健康检查超时，请查看日志：docker compose logs -f"
exit 1
