#!/usr/bin/env bash
# Open Dreamina 开发模式启动脚本（Linux / macOS）
# 用法: bash dev.sh
#
# 特性：
#   - 前端：Vite HMR 热更新，保存即刷新
#   - 后端：uvicorn --reload，API 代码改动自动重载
#   - Celery：watchmedo 自动重启 worker / beat
set -euo pipefail

cd "$(dirname "$0")"

# 颜色输出
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# 1. 检查 Docker
if ! command -v docker >/dev/null 2>&1; then
  error "未检测到 Docker，请先安装 Docker：https://docs.docker.com/get-docker/"
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  error "未检测到 docker compose 插件，请升级 Docker 或安装 compose 插件。"
  exit 1
fi

# 2. 生成 .env（首次运行）
if [ ! -f .env ]; then
  info "未发现 .env，正在生成（含随机 ENCRYPTION_KEY）..."
  KEY=$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')
  cat > .env <<EOF
# 用于加密 API Key 的密钥（首次运行自动生成，请妥善保管，勿泄露）
ENCRYPTION_KEY=${KEY}
EOF
  info ".env 已生成"
fi

# 3. 构建并启动开发环境
info "正在构建并启动开发环境（前后端热加载）..."
echo -e "${CYAN}==============================================${NC}"
echo -e "${CYAN}  开发模式启动中...${NC}"
echo -e "${CYAN}  前端 HMR:  http://localhost:10131${NC}"
echo -e "${CYAN}  API 文档:  http://localhost:10130/docs${NC}"
echo -e "${CYAN}  热加载范围:${NC}"
echo -e "${CYAN}    前端 frontend/src → Vite HMR 自动刷新${NC}"
echo -e "${CYAN}    后端 backend/app  → uvicorn 自动重载${NC}"
echo -e "${CYAN}    Celery tasks     → watchmedo 自动重启${NC}"
echo -e "${CYAN}==============================================${NC}"
echo

# 前台运行，直接查看日志（Ctrl+C 停止所有服务）
exec docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
