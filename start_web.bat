@echo off
chcp 65001 >nul
title SQL Server 备份工具 - Web 版启动器

echo ============================================
echo   SQL Server 备份工具 - Web 版
echo ============================================
echo.

:: 获取当前目录
set TOOL_DIR=%~dp0
set TOOL_DIR=%TOOL_DIR:~0,-1%

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 未找到 Python，请安装 Python 3.8+
    pause
    exit /b 1
)

:: 安装 Flask
echo 📦 检查依赖...
pip install flask -q

:: 启动
echo.
echo 🚀 启动服务中...
echo.
echo 🌐 请打开浏览器访问: http://localhost:5000
echo 🌐 局域网访问: http://<本机IP>:5000
echo.
echo ⏹ 按 Ctrl+C 停止服务
echo ============================================
echo.

python "%TOOL_DIR%\sql_backup_web.py"

pause