#!/usr/bin/env bash
# 把 opendreamina 命令安装到用户 PATH：在安装目录创建一个调用
# `python cli/opendreamina.py` 的 wrapper 脚本，不安装任何第三方依赖。
#
# 用法：
#   bash cli/install.sh
#   OPENDREAMINA_INSTALL_DIR=/usr/local/bin bash cli/install.sh
#
# 与 AGENTS.md 第 5 条安全红线一致：本脚本不执行 pip install / npm install，
# 仅生成一个几行的 shell wrapper。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$SCRIPT_DIR/opendreamina.py"

if [ ! -f "$TARGET" ]; then
    echo "[install] 未找到目标脚本: $TARGET" >&2
    exit 1
fi

# 选择 python 解释器（opendreamina.py 纯标准库，python3 / python 均可）。
# 注意：Windows 上 `python3` 可能是 Microsoft Store 的占位 stub（command -v 命中但
# 实际不执行 Python），因此必须真正执行一段代码验证，而不能只看是否存在。
pick_python() {
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 \
            && "$candidate" -c 'import sys; sys.exit(0)' >/dev/null 2>&1; then
            printf '%s' "$candidate"
            return 0
        fi
    done
    return 1
}
if PY="$(pick_python)"; then
    :
else
    echo "[install] 未找到可用的 python3 / python，请先安装 Python 3.9+。" >&2
    echo "           （Windows 上 `python3` 可能是 Microsoft Store 占位符，请改用 python 或安装真实解释器）" >&2
    exit 1
fi

# 安装目录：默认 ~/.local/bin（多数发行版默认在 PATH），可用环境变量覆盖。
INSTALL_DIR="${OPENDREAMINA_INSTALL_DIR:-${HOME}/.local/bin}"
mkdir -p "$INSTALL_DIR"

WRAPPER="$INSTALL_DIR/opendreamina"
cat > "$WRAPPER" <<EOF
#!/bin/sh
# 由 cli/install.sh 生成：转发到 opendreamina.py。仓库移动后重跑 install.sh 刷新。
exec "$PY" "$TARGET" "\$@"
EOF
chmod +x "$WRAPPER"

echo "已安装 opendreamina -> $WRAPPER"
echo "调用: $PY \"$TARGET\" \"\$@\""

case ":$PATH:" in
    *":$INSTALL_DIR:"*) ;;
    *)
        echo ""
        echo "[提示] $INSTALL_DIR 不在当前 PATH。把它加入 shell 配置后重开终端："
        echo "  echo 'export PATH=\"$INSTALL_DIR:\$PATH\"' >> ~/.bashrc   # bash"
        echo "  echo 'export PATH=\"$INSTALL_DIR:\$PATH\"' >> ~/.zshrc    # zsh"
        ;;
esac

echo ""
echo "验证: opendreamina --version"
