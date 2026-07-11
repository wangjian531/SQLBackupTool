#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL Server 备份工具 - Web 管理界面 (Flask)
"""

import os
import sys
import json
import threading
import logging
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file

# 导入核心备份模块
from sql_backup_core import do_backup, load_config, send_email_notification, logger

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

app = Flask(__name__)
app.config["SECRET_KEY"] = "sql-backup-tool-secret-key-2024"

# 全局状态
backup_status = {
    "running": False,
    "current": "",
    "progress": 0,
    "logs": [],
    "results": []
}


def add_log(message, level="info"):
    """添加日志"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    backup_status["logs"].append({
        "time": timestamp,
        "level": level,
        "msg": message
    })
    if len(backup_status["logs"]) > 500:
        backup_status["logs"] = backup_status["logs"][-500:]


@app.route("/")
def index():
    """主页面"""
    cfg = load_config()
    servers = cfg.get("servers", []) if cfg else []
    return render_template("index.html", servers=servers, status=backup_status)


@app.route("/api/status")
def api_status():
    """获取状态"""
    return jsonify(backup_status)


@app.route("/api/servers")
def api_servers():
    """获取服务器列表"""
    cfg = load_config()
    servers = cfg.get("servers", []) if cfg else []
    return jsonify(servers)


@app.route("/api/config", methods=["GET"])
def api_get_config():
    """获取配置"""
    cfg = load_config()
    return jsonify(cfg or {"servers": [], "cloud": {}, "email": {}})


@app.route("/api/config", methods=["POST"])
def api_save_config():
    """保存配置"""
    try:
        data = request.get_json()
        config_path = "config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify({"success": True, "msg": "配置已保存"})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)})


@app.route("/api/backup", methods=["POST"])
def api_start_backup():
    """开始备份"""
    if backup_status["running"]:
        return jsonify({"success": False, "msg": "备份任务正在执行中"})

    data = request.get_json()
    server_index = data.get("server_index", -1)
    backup_type = data.get("backup_type", "full")
    compress = data.get("compress", False)
    retention_days = data.get("retention_days", 7)
    cloud_type = data.get("cloud", None)

    cfg = load_config()
    if not cfg or not cfg.get("servers"):
        return jsonify({"success": False, "msg": "未配置服务器"})

    if server_index == -1:
        # 备份所有服务器
        servers = cfg["servers"]
    else:
        servers = [cfg["servers"][server_index]]

    # 重置状态
    backup_status["running"] = True
    backup_status["current"] = "准备中..."
    backup_status["progress"] = 0
    backup_status["results"] = []
    backup_status["logs"] = []

    def run():
        all_results = []
        total = len(servers)
        try:
            for idx, srv in enumerate(servers):
                si = srv.copy()
                si["backup_type"] = backup_type
                si["compress"] = compress
                si["retention_days"] = retention_days
                if cloud_type:
                    si["cloud"] = cloud_type

                name = si.get("name", si["server"])
                backup_status["current"] = name
                add_log(f"开始备份: {name}", "info")

                results = do_backup(si, cfg)
                all_results.extend(results)

                backup_status["progress"] = int((idx + 1) / total * 100)

                for r in results:
                    if r["status"] == "success":
                        add_log(f"✅ {r['server']}/{r['database']} 备份成功", "success")
                    else:
                        add_log(f"❌ {r['server']}/{r['database']}: {r.get('error', '')}", "error")

            # 发送邮件通知
            send_email_notification(cfg, all_results)

            success = sum(1 for r in all_results if r["status"] == "success")
            failed = sum(1 for r in all_results if r["status"] == "error")
            add_log(f"全部完成: 成功 {success}, 失败 {failed}", "success" if failed == 0 else "warning")

        except Exception as e:
            add_log(f"备份过程异常: {e}", "error")
        finally:
            backup_status["running"] = False
            backup_status["current"] = ""
            backup_status["progress"] = 100
            backup_status["results"] = all_results

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True, "msg": "备份任务已启动"})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """停止备份（标记停止，实际需等待当前任务完成）"""
    backup_status["running"] = False
    add_log("⏹ 已请求停止备份", "warning")
    return jsonify({"success": True})


@app.route("/api/logs")
def api_logs():
    """获取日志"""
    return jsonify(backup_status["logs"])


@app.route("/api/test-connection", methods=["POST"])
def api_test_connection():
    """测试数据库连接"""
    data = request.get_json()
    from sql_backup_core import get_connection

    try:
        conn = get_connection(
            data["server"],
            data.get("port", 1433),
            data["username"],
            data["password"]
        )
        cursor = conn.cursor()
        cursor.execute("SELECT @@VERSION")
        version = cursor.fetchone()[0][:80] + "..."
        cursor.close()
        conn.close()
        return jsonify({"success": True, "msg": f"✅ 连接成功\n{version}"})
    except Exception as e:
        return jsonify({"success": False, "msg": f"❌ 连接失败: {e}"})


def main():
    print("=" * 50)
    print("  SQL Server 备份工具 - Web 管理界面")
    print("=" * 50)
    print()
    print("  🌐 打开浏览器访问:")
    print("     http://localhost:5000")
    print("     http://你的IP:5000  (局域网其他设备)")
    print()
    print("  ⏹  Ctrl+C 停止服务")
    print("=" * 50)
    print()

    # 创建 templates 目录
    os.makedirs(os.path.join(os.path.dirname(__file__), "templates"), exist_ok=True)

    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)


if __name__ == "__main__":
    main()