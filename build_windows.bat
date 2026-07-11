@echo off
chcp 65001 >nul
title SQL Server 备份工具 - 打包脚本

echo ============================================
echo   SQL Server 备份工具 - 打包脚本
echo ============================================
echo.

:: 获取当前目录
set TOOL_DIR=%~dp0
set TOOL_DIR=%TOOL_DIR:~0,-1%

echo 📂 当前目录: %TOOL_DIR%
echo.

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

:: 安装 pyinstaller
echo 📦 安装 PyInstaller ...
pip install pyinstaller -q

:: 安装依赖
echo 📦 安装项目依赖 ...
pip install pymssql schedule requests -q

echo.
echo 🔨 开始打包 ...

:: 1. 打包 GUI 版
echo [1/3] 打包图形界面版 (SQLBackup_GUI.exe) ...
pyinstaller --onefile --windowed ^
    --name "SQLBackup_GUI" ^
    --add-data "%TOOL_DIR%\config.json;." ^
    --hidden-import pymssql ^
    --hidden-import pyodbc ^
    --hidden-import schedule ^
    --distpath "%TOOL_DIR%\dist" ^
    --clean ^
    "%TOOL_DIR%\sql_backup_gui.py"

:: 2. 打包 CLI 版
echo [2/3] 打包命令行版 (SQLBackup_CLI.exe) ...
pyinstaller --onefile --console ^
    --name "SQLBackup_CLI" ^
    --add-data "%TOOL_DIR%\config.json;." ^
    --hidden-import pymssql ^
    --hidden-import pyodbc ^
    --hidden-import schedule ^
    --distpath "%TOOL_DIR%\dist" ^
    --clean ^
    "%TOOL_DIR%\sql_backup_cli.py"

:: 3. 打包调度器版
echo [3/3] 打包定时调度器版 (SQLBackup_Scheduler.exe) ...
pyinstaller --onefile --console ^
    --name "SQLBackup_Scheduler" ^
    --add-data "%TOOL_DIR%\config.json;." ^
    --hidden-import pymssql ^
    --hidden-import pyodbc ^
    --hidden-import schedule ^
    --distpath "%TOOL_DIR%\dist" ^
    --clean ^
    "%TOOL_DIR%\sql_backup_scheduler.py"

:: 清理临时文件
echo.
echo 🧹 清理临时文件 ...
rmdir /s /q "%TOOL_DIR%\build" >nul 2>&1
del /q "%TOOL_DIR%\*.spec" >nul 2>&1

echo.
echo ============================================
echo   ✅ 打包完成！
echo.
echo   输出目录: %TOOL_DIR%\dist\
echo.
echo   文件列表：
dir /b "%TOOL_DIR%\dist\"
echo.
echo   使用方法：
echo     SQLBackup_GUI.exe       - 双击运行图形界面
echo     SQLBackup_CLI.exe       - 命令行执行备份
echo     SQLBackup_Scheduler.exe - 定时任务调度
echo ============================================
echo.
pause