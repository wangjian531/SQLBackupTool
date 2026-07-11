#!/bin/bash
# SQL Server 备份工具 - Linux 打包脚本

set -e

TOOL_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$TOOL_DIR/dist"
PYINSTALLER="/vol1/@apphome/trim.openclaw/data/home/.local/bin/pyinstaller"

export PATH="$PATH:/vol1/@apphome/trim.openclaw/data/home/.local/bin"

echo "============================================"
echo "  SQL Server 备份工具 - 打包脚本"
echo "============================================"
echo ""

# 检查 pyinstaller
if [ ! -f "$PYINSTALLER" ]; then
    echo "❌ 未找到 pyinstaller，请先安装: pip install pyinstaller"
    exit 1
fi

echo "📦 打包图形界面版 (GUI) ..."
"$PYINSTALLER" --onefile --windowed \
    --name "SQLBackup_GUI" \
    --add-data "$TOOL_DIR/config.json:." \
    --hidden-import pymssql \
    --hidden-import pyodbc \
    --hidden-import schedule \
    --distpath "$BUILD_DIR" \
    --clean \
    "$TOOL_DIR/sql_backup_gui.py" 2>&1 | tail -5

echo ""
echo "📦 打包命令行版 (CLI) ..."
"$PYINSTALLER" --onefile --console \
    --name "SQLBackup_CLI" \
    --add-data "$TOOL_DIR/config.json:." \
    --hidden-import pymssql \
    --hidden-import pyodbc \
    --hidden-import schedule \
    --distpath "$BUILD_DIR" \
    --clean \
    "$TOOL_DIR/sql_backup_cli.py" 2>&1 | tail -5

echo ""
echo "📦 打包定时调度器版 ..."
"$PYINSTALLER" --onefile --console \
    --name "SQLBackup_Scheduler" \
    --add-data "$TOOL_DIR/config.json:." \
    --hidden-import pymssql \
    --hidden-import pyodbc \
    --hidden-import schedule \
    --distpath "$BUILD_DIR" \
    --clean \
    "$TOOL_DIR/sql_backup_scheduler.py" 2>&1 | tail -5

echo ""
echo "============================================"
echo "  ✅ 打包完成！"
echo ""
echo "  输出目录: $BUILD_DIR"
echo ""
ls -lh "$BUILD_DIR"/*.exe "$BUILD_DIR"/* 2>/dev/null || ls -lh "$BUILD_DIR"/
echo "============================================"