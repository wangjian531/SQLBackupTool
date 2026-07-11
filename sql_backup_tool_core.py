#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQLBackupTool 核心模块
SQL Server 数据库备份工具 - 调度器 + SQL Agent + 备份记录 + 文件清理
"""

import os, sys, json, time, threading, logging
from datetime import datetime, timedelta

CONFIG_FILE = "config.json"
HISTORY_FILE = "backup_history.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("sql_backup_tool.log", encoding="utf-8"), logging.StreamHandler()]
)
log = logging.getLogger("SQLBackupTool")

# 延迟导入，避免缺少 pymssql 时整个程序崩溃
pymssql = None
try:
    import pymssql
except ImportError:
    pass

# ── SQL Agent 管理 ──

class SQLAgentManager:
    def __init__(self, server, port=1433, username="sa", password=""):
        self.server = server
        self.port = port
        self.username = username
        self.password = password

    def _connect(self, db="msdb"):
        if pymssql is None:
            raise ImportError("pymssql 未安装")
        return pymssql.connect(server=self.server, port=self.port,
                               user=self.username, password=self.password,
                               database=db, timeout=5)

    def check_agent_status(self):
        try:
            conn = self._connect("master")
            cur = conn.cursor()
            cur.execute("""
                SELECT dss.[status] FROM sys.dm_server_services dss
                WHERE dss.[servicename] LIKE N'SQL Server Agent (%'
            """)
            row = cur.fetchone()
            cur.close(); conn.close()
            if row and row[0] == 4:
                return True, "Agent 运行中"
            return False, f"Agent 状态码: {row[0] if row else '未知'}"
        except Exception as e:
            return False, str(e)

    def start_agent(self):
        try:
            conn = self._connect("master")
            cur = conn.cursor()
            cur.execute("EXEC xp_servicecontrol N'START', N'SQLSERVERAGENT'")
            conn.commit(); cur.close(); conn.close()
            return True, "Agent 已启动"
        except Exception as e:
            return False, f"启动失败: {str(e)}"

    def _job_name(self, server_name):
        return f"SQLBackup_{server_name.replace('.','_').replace(' ','_')}"

    def create_backup_job(self, server_name, databases, backup_type, output_dir,
                          schedule_time, retention_days=30):
        jn = self._job_name(server_name)
        self._delete_job(jn)
        try:
            conn = self._connect("msdb")
            cur = conn.cursor()
            db_list = ",".join(databases) if isinstance(databases, list) else databases
            cur.execute(f"""
                EXEC dbo.sp_add_job @job_name=N'{jn}', @enabled=1,
                @description=N'SQLBackupTool 自动备份', @owner_login_name=N'sa'
            """)
            step = f"BACKUP DATABASE [{db_list}] TO DISK = N'{output_dir}\\\\{db_list}_$(ESCAPE_SQUOTE(YYYYMMDDHHmmss)).bak' WITH INIT, NAME=N'{server_name}-备份', NOSKIP, NOREWIND, NOUNLOAD, STATS=10"
            cur.execute(f"""
                EXEC dbo.sp_add_jobstep @job_name=N'{jn}', @step_name=N'执行备份',
                @step_id=1, @command=N'{step}', @database_name=N'master'
            """)
            parts = schedule_time.split(":")
            if len(parts) == 2:
                h, m = parts
                ft, fi = 4, 1
            elif len(parts) == 3:
                wd, h, m = parts
                ft = 8
                wm = {"MON":2,"TUE":3,"WED":4,"THU":5,"FRI":6,"SAT":7,"SUN":1}
                fi = wm.get(wd.upper(), 1)
            else:
                return False, "时间格式错误"
            cur.execute(f"""
                EXEC dbo.sp_add_jobschedule @job_name=N'{jn}', @name=N'{jn}_Sched',
                @freq_type={ft}, @freq_interval={fi}, @freq_subday_type=1,
                @active_start_time={int(h):02d}{int(m):02d}00
            """)
            cur.execute(f"EXEC dbo.sp_add_jobserver @job_name=N'{jn}', @server_name=N'(local)'")
            conn.commit(); cur.close(); conn.close()
            return True, f"作业 {jn} 创建成功"
        except Exception as e:
            return False, f"创建失败: {str(e)}"

    def _delete_job(self, job_name):
        try:
            conn = self._connect("msdb")
            cur = conn.cursor()
            cur.execute(f"""
                IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name=N'{job_name}')
                BEGIN EXEC dbo.sp_delete_job @job_name=N'{job_name}' END
            """)
            conn.commit(); cur.close(); conn.close()
        except:
            pass

    def delete_backup_job(self, server_name):
        jn = self._job_name(server_name)
        self._delete_job(jn)
        return True, f"作业 {jn} 已删除"

    def list_jobs(self):
        try:
            conn = self._connect("msdb")
            cur = conn.cursor()
            cur.execute("SELECT job_id, name, enabled FROM msdb.dbo.sysjobs WHERE name LIKE 'SQLBackup_%' ORDER BY name")
            jobs = [{"id": str(r[0]), "name": r[1], "enabled": r[2]} for r in cur.fetchall()]
            cur.close(); conn.close()
            return jobs
        except:
            return []


# ── 备份记录 ──

class BackupHistory:
    def __init__(self):
        self.file = HISTORY_FILE
        self.records = self._load()

    def _load(self):
        try:
            if os.path.exists(self.file):
                with open(self.file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except:
            pass
        return {"records": []}

    def _save(self):
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(self.records, f, ensure_ascii=False, indent=2)

    def add(self, server, database, status, size="", detail=""):
        self.records["records"].insert(0, {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "server": server, "database": database,
            "status": status, "size": size, "detail": detail
        })
        if len(self.records["records"]) > 1000:
            self.records["records"] = self.records["records"][:1000]
        self._save()

    def get_recent(self, count=100):
        return self.records["records"][:count]

    def clear(self):
        self.records["records"] = []
        self._save()


# ── 备份文件清理 ──

class BackupCleaner:
    EXTENSIONS = (".bak", ".trn", ".diff", ".zip", ".7z")

    @staticmethod
    def clean(output_dir, retention_days):
        if retention_days <= 0 or not os.path.exists(output_dir):
            return 0
        cutoff = datetime.now() - timedelta(days=retention_days)
        deleted = 0
        for f in os.listdir(output_dir):
            if f.lower().endswith(BackupCleaner.EXTENSIONS):
                fp = os.path.join(output_dir, f)
                try:
                    if datetime.fromtimestamp(os.path.getmtime(fp)) < cutoff:
                        os.remove(fp)
                        log.info(f"清理旧备份: {f}")
                        deleted += 1
                except:
                    pass
        return deleted

    @staticmethod
    def get_info(output_dir):
        info = {"total_size": 0, "file_count": 0, "files": []}
        if not os.path.exists(output_dir):
            return info
        for f in os.listdir(output_dir):
            if f.lower().endswith(BackupCleaner.EXTENSIONS):
                fp = os.path.join(output_dir, f)
                try:
                    sz = os.path.getsize(fp)
                    mt = datetime.fromtimestamp(os.path.getmtime(fp))
                    info["files"].append({"name": f, "size": sz, "mtime": mt.strftime("%Y-%m-%d %H:%M")})
                    info["total_size"] += sz
                    info["file_count"] += 1
                except:
                    pass
        info["files"].sort(key=lambda x: x["mtime"], reverse=True)
        return info


# ── 软件后台调度器 ──

class SoftwareScheduler:
    def __init__(self, config, history):
        self.config = config
        self.history = history
        self.running = False
        self.thread = None
        self._stop = threading.Event()

    def start(self):
        if self.running:
            return False, "调度器已在运行"
        self.running = True
        self._stop.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return True, "调度器已启动"

    def stop(self):
        if not self.running:
            return False, "调度器未运行"
        self._stop.set()
        self.running = False
        return True, "调度器已停止"

    def _run(self):
        log.info("软件调度器已启动")
        while not self._stop.is_set():
            try:
                now = datetime.now()
                for srv in self.config.get("servers", []):
                    sc = srv.get("schedule", {})
                    if not sc.get("enabled"):
                        continue
                    stype = sc.get("type", "daily")
                    stime = sc.get("time", "02:00")
                    cur = now.strftime("%H:%M")
                    doit = False
                    if stype == "daily" and cur == stime:
                        doit = True
                    elif stype == "weekly":
                        dm = {"MON":0,"TUE":1,"WED":2,"THU":3,"FRI":4,"SAT":5,"SUN":6}
                        td = dm.get(sc.get("day","MON").upper(), 0)
                        if now.weekday() == td and cur == stime:
                            doit = True
                    if doit:
                        log.info(f"定时触发: {srv.get('name', srv['server'])}")
                        threading.Thread(target=self._exec, args=(srv,), daemon=True).start()
                        time.sleep(61)
                self._stop.wait(60)
            except Exception as e:
                log.error(f"调度器异常: {e}")
                self._stop.wait(60)
        log.info("软件调度器已停止")

    def _exec(self, srv):
        try:
            from sql_backup_core import do_backup, send_email_notification
            results = do_backup(srv, self.config)
            for r in results:
                self.history.add(srv.get("name", srv["server"]), r.get("database",""),
                                 r["status"], r.get("size",""), r.get("message",""))
            output = srv.get("output", "D:\\SQLBackup")
            retention = srv.get("retention_days", 0)
            if retention > 0:
                d = BackupCleaner.clean(output, retention)
                if d: log.info(f"已清理 {d} 个旧备份")
            send_email_notification(self.config, results)
        except Exception as e:
            log.error(f"定时备份失败: {e}")
            self.history.add(srv.get("name", srv.get("server","未知")), "", "error", detail=str(e))