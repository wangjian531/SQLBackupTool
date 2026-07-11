#!/bin/bash
# SQL Server 备份工具 - Web 版启动器 (Linux)

TOOL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "============================================"
echo "  SQL Server 备份工具 - Web 版"
echo "============================================"
echo ""

# 安装依赖
echo "📦 检查依赖..."
pip3 install flask --break-system-packages -q 2>/dev/null || true

echo ""
echo "🚀 启动服务中..."
echo ""
echo "🌐 请打开浏览器访问: http://localhost:5000"
echo "🌐 局域网访问: http://<本机IP>:5000"
echo ""
echo "⏹ 按 Ctrl+C 停止服务"
echo "============================================"
echo ""

cd "$TOOL_DIR"
python3 sql_backup_web.py