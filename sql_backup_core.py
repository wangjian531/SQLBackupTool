#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL Server 备份核心逻辑
支持：本地、共享文件夹、网盘
"""

import os
import sys
import json
import subprocess
import datetime
import shutil
import re
import logging
from pathlib import Path

# 尝试导入 pymssql / pyodbc
try:
    import pymssql
    DB_DRIVER = "pymssql"
except ImportError:
    pymssql = None
    try:
        import pyodbc
        DB_DRIVER = "pyodbc"
    except ImportError:
        pyodbc = None
        DB_DRIVER = None

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("sql_backup.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("SQLBackup")


def load_config(config_path="config.json"):
    """加载配置文件"""
    if not os.path.exists(config_path):
        logger.warning(f"配置文件 {config_path} 不存在，使用默认配置")
        return None
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_connection(server, port, username, password, database="master"):
    """获取 SQL Server 连接"""
    if DB_DRIVER == "pymssql":
        conn = pymssql.connect(
            server=server,
            port=port,
            user=username,
            password=password,
            database=database,
            timeout=10
        )
        return conn
    elif DB_DRIVER == "pyodbc":
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={server},{port};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            f"Connection Timeout=10;"
        )
        conn = pyodbc.connect(conn_str)
        return conn
    else:
        raise RuntimeError("未安装 pymssql 或 pyodbc，请执行: pip install pymssql")


def get_databases(conn, databases_filter=None):
    """获取数据库列表"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name FROM sys.databases
        WHERE name NOT IN ('master', 'tempdb', 'model', 'msdb')
          AND state = 0
        ORDER BY name
    """)
    all_dbs = [row[0] for row in cursor.fetchall()]
    cursor.close()

    if not databases_filter or databases_filter == ["*"]:
        return all_dbs

    # 支持通配符
    matched = []
    for pattern in databases_filter:
        pattern = pattern.replace("*", ".*").replace("?", ".")
        for db in all_dbs:
            if re.match(f"^{pattern}$", db, re.IGNORECASE):
                matched.append(db)
    return list(set(matched))


def get_backup_dir(server, database, base_output, backup_type):
    """生成备份目录路径"""
    server_name = server.replace(".", "_").replace(":", "_")
    now = datetime.datetime.now()

    if base_output.startswith("\\\\") or ":" in base_output:
        # 共享文件夹或绝对路径
        output_dir = os.path.join(base_output, server_name, database, backup_type)
    else:
        output_dir = os.path.join(base_output, server_name, database, backup_type)

    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def backup_database(conn, database, backup_type, output_path):
    """执行 SQL Server 备份"""
    cursor = conn.cursor()

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = {"full": "FULL", "diff": "DIFF", "log": "LOG"}.get(backup_type, "FULL")
    filename = f"{database}_{suffix}_{timestamp}.bak"
    full_path = os.path.join(output_path, filename)

    if backup_type == "full":
        sql = f"""
            BACKUP DATABASE [{database}]
            TO DISK = N'{full_path}'
            WITH INIT, COMPRESSION, STATS = 10,
            NAME = N'{database}-{suffix}-{timestamp}'
        """
    elif backup_type == "diff":
        sql = f"""
            BACKUP DATABASE [{database}]
            TO DISK = N'{full_path}'
            WITH DIFFERENTIAL, INIT, COMPRESSION, STATS = 10,
            NAME = N'{database}-{suffix}-{timestamp}'
        """
    elif backup_type == "log":
        sql = f"""
            BACKUP LOG [{database}]
            TO DISK = N'{full_path}'
            WITH INIT, COMPRESSION, STATS = 10,
            NAME = N'{database}-{suffix}-{timestamp}'
        """
    else:
        raise ValueError(f"不支持的备份类型: {backup_type}")

    logger.info(f"开始备份 [{database}] -> {full_path}")
    cursor.execute(sql)

    # 读取输出
    if DB_DRIVER == "pymssql":
        while cursor.nextset():
            pass
    else:
        rows = cursor.fetchall()
        for row in rows:
            logger.info(f"  {row[0]}" if row else "")

    cursor.close()
    logger.info(f"✅ 备份完成: {full_path}")
    return full_path, filename


def compress_backup(file_path, delete_original=True):
    """使用 7z 压缩备份文件"""
    compressed_path = file_path + ".7z"
    seven_zip = shutil.which("7z") or shutil.which("7za") or "C:\\Program Files\\7-Zip\\7z.exe"

    cmd = [seven_zip, "a", "-mx=5", compressed_path, file_path]
    logger.info(f"压缩备份: {file_path}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode == 0:
        logger.info(f"✅ 压缩完成: {compressed_path}")
        if delete_original:
            os.remove(file_path)
            logger.info(f"已删除原始备份: {file_path}")
        return compressed_path
    else:
        logger.warning(f"压缩失败: {result.stderr}")
        return file_path


def clean_old_backups(output_path, retention_days):
    """清理过期备份"""
    if retention_days <= 0:
        return

    cutoff = datetime.datetime.now() - datetime.timedelta(days=retention_days)
    cleaned = 0

    for f in os.listdir(output_path):
        file_path = os.path.join(output_path, f)
        if not os.path.isfile(file_path):
            continue
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
        if mtime < cutoff:
            os.remove(file_path)
            cleaned += 1
            logger.info(f"🧹 清理过期备份: {f}")

    if cleaned > 0:
        logger.info(f"共清理 {cleaned} 个过期文件")


def verify_backup(conn, backup_file):
    """验证备份文件"""
    cursor = conn.cursor()
    sql = f"RESTORE VERIFYONLY FROM DISK = N'{backup_file}'"
    try:
        cursor.execute(sql)
        if DB_DRIVER == "pymssql":
            while cursor.nextset():
                pass
        else:
            cursor.fetchall()
        cursor.close()
        logger.info(f"✅ 备份验证通过: {backup_file}")
        return True
    except Exception as e:
        logger.error(f"❌ 备份验证失败: {e}")
        cursor.close()
        return False


def do_backup(server_info, config=None):
    """
    执行备份任务

    server_info: {
        "name": "服务器名称",
        "server": "127.0.0.1",
        "port": 1433,
        "username": "sa",
        "password": "",
        "databases": ["*"],
        "backup_type": "full",
        "output": "D:\\Backup",
        "compress": False,
        "retention_days": 7,
        "cloud": None
    }
    """
    results = []

    try:
        conn = get_connection(
            server_info["server"],
            server_info.get("port", 1433),
            server_info["username"],
            server_info["password"]
        )
    except Exception as e:
        logger.error(f"❌ 连接服务器 {server_info['server']} 失败: {e}")
        return [{"server": server_info.get("name", server_info["server"]), "status": "error", "error": str(e)}]

    databases = get_databases(conn, server_info.get("databases", ["*"]))
    logger.info(f"服务器 {server_info['server']} 找到数据库: {databases}")

    for db in databases:
        try:
            output_dir = get_backup_dir(
                server_info["server"],
                db,
                server_info["output"],
                server_info.get("backup_type", "full")
            )

            # 执行备份
            backup_file, filename = backup_database(
                conn, db,
                server_info.get("backup_type", "full"),
                output_dir
            )

            # 验证备份
            verify_backup(conn, backup_file)

            # 压缩
            if server_info.get("compress"):
                backup_file = compress_backup(backup_file)

            # 清理过期
            clean_old_backups(output_dir, server_info.get("retention_days", 0))

            results.append({
                "server": server_info.get("name", server_info["server"]),
                "database": db,
                "status": "success",
                "file": backup_file,
                "type": server_info.get("backup_type", "full")
            })

        except Exception as e:
            logger.error(f"❌ 备份 {db} 失败: {e}")
            results.append({
                "server": server_info.get("name", server_info["server"]),
                "database": db,
                "status": "error",
                "error": str(e)
            })

    conn.close()
    return results


def send_email_notification(config, results):
    """发送邮件通知"""
    if not config or "email" not in config:
        return

    email_cfg = config["email"]
    if not email_cfg.get("smtp_server") or not email_cfg.get("sender"):
        return

    success_count = sum(1 for r in results if r["status"] == "success")
    error_count = sum(1 for r in results if r["status"] == "error")

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"[SQL备份] {'成功' if error_count == 0 else '部分失败'} | {success_count}成功 {error_count}失败"
    body_lines = [
        f"备份时间: {now}",
        f"成功: {success_count}  失败: {error_count}",
        "",
        "=== 备份详情 ==="
    ]
    for r in results:
        if r["status"] == "success":
            body_lines.append(f"✅ {r['server']}/{r['database']} -> {r['file']}")
        else:
            body_lines.append(f"❌ {r['server']}/{r['database']}: {r.get('error', '未知错误')}")

    body = "\n".join(body_lines)

    import smtplib
    from email.mime.text import MIMEText

    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = email_cfg["sender"]
        msg["To"] = ",".join(email_cfg["receivers"])

        if email_cfg.get("smtp_port") == 465:
            server = smtplib.SMTP_SSL(email_cfg["smtp_server"], email_cfg["smtp_port"])
        else:
            server = smtplib.SMTP(email_cfg["smtp_server"], email_cfg.get("smtp_port", 587))
            server.starttls()

        server.login(email_cfg["sender"], email_cfg["password"])
        server.sendmail(email_cfg["sender"], email_cfg["receivers"], msg.as_string())
        server.quit()
        logger.info(f"📧 邮件通知已发送")
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")


if __name__ == "__main__":
    # 测试：加载配置并备份所有服务器
    cfg = load_config()
    if cfg and cfg.get("servers"):
        all_results = []
        for srv in cfg["servers"]:
            logger.info(f"=" * 50)
            logger.info(f"开始备份服务器: {srv.get('name', srv['server'])}")
            results = do_backup(srv, cfg)
            all_results.extend(results)

        # 发送通知
        send_email_notification(cfg, all_results)
    else:
        logger.info("请在 config.json 中配置服务器信息")