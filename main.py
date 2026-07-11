#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQLBackupTool - SQL Server 备份工具
启动入口
"""
import sys, os

# 确保可以导入同级模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    from sql_backup_tool_gui import App
    app = App()
    app.run()