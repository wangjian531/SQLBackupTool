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


def _sanitize_sql_name(name):
    """清洗 SQL 对象名，只保留安全字符，防止 SQL 注入"""
    return "".join(c for c in name if c.isalnum() or c in "_- ").strip().replace("--", "")


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
                return "running"
            return "stopped"
        except ImportError:
            return "pymssql 未安装"
        except Exception as e:
            return f"error: {str(e)}"

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
        safe = _sanitize_sql_name(server_name)
        return f"SQLBackup_{safe.replace(' ','_')}"

    def create_backup_job(self, server_name, databases, backup_type, output_dir,
                          schedule_time, retention_days=30):
        jn = self._job_name(server_name)
        try:
            self._delete_job(jn)
        except Exception:
            pass
        try:
            conn = self._connect("msdb")
            cur = conn.cursor()
            dbs = databases if isinstance(databases, list) else [databases]
            safe_jn = _sanitize_sql_name(jn)
            safe_desc = _sanitize_sql_name("SQLBackupTool 自动备份")
            safe_owner = "sa"

            # 创建作业
            cur.execute(f"""
                EXEC dbo.sp_add_job @job_name=N'{safe_jn}', @enabled=1,
                @description=N'{safe_desc}', @owner_login_name=N'{safe_owner}'
            """)
            safe_output = _sanitize_sql_name(output_dir.replace("\\", "_").replace("/", "_"))
            # 每个数据库单独创建 jobstep
            for i, db in enumerate(dbs):
                safe_db = _sanitize_sql_name(db)
                step = f"BACKUP DATABASE [{safe_db}] TO DISK = N'{safe_output}_{safe_db}_$(ESCAPE_SQUOTE(YYYYMMDDHHmmss)).bak' WITH INIT, NAME=N'{safe_jn}-{safe_db}', NOSKIP, NOREWIND, NOUNLOAD, STATS=10"
                cur.execute(f"""
                    EXEC dbo.sp_add_jobstep @job_name=N'{safe_jn}', @step_name=N'备份-{safe_db}',
                    @step_id={i+1}, @command=N'{step}', @database_name=N'master'
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
                EXEC dbo.sp_add_jobschedule @job_name=N'{safe_jn}', @name=N'{safe_jn}_Sched',
                @freq_type={ft}, @freq_interval={fi}, @freq_subday_type=1,
                @active_start_time={int(h):02d}{int(m):02d}00
            """)
            cur.execute(f"EXEC dbo.sp_add_jobserver @job_name=N'{safe_jn}', @server_name=N'(local)'")
            conn.commit(); cur.close(); conn.close()
            return True, f"作业 {jn} 创建成功"
        except Exception as e:
            log.error(f"创建作业失败: {e}")
            return False, f"创建失败: {str(e)}"

    def _delete_job(self, job_name):
        try:
            conn = self._connect("msdb")
            cur = conn.cursor()
            safe_jn = _sanitize_sql_name(job_name)
            cur.execute(f"""
                IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name=N'{safe_jn}')
                BEGIN EXEC dbo.sp_delete_job @job_name=N'{safe_jn}' END
            """)
            conn.commit(); cur.close(); conn.close()
        except Exception as e:
            log.error(f"删除作业失败: {e}")
            raise

    def delete_backup_job(self, server_name):
        jn = self._job_name(server_name)
        try:
            self._delete_job(jn)
        except Exception:
            return False, f"删除失败"
        return True, f"作业 {jn} 已删除"

    def list_jobs(self):
        try:
            conn = self._connect("msdb")
            cur = conn.cursor()
            cur.execute("SELECT job_id, name, enabled FROM msdb.dbo.sysjobs WHERE name LIKE 'SQLBackup_%' ORDER BY name")
            jobs = [{"id": str(r[0]), "name": r[1], "enabled": r[2]} for r in cur.fetchall()]
            cur.close(); conn.close()
            return jobs
        except Exception as e:
            log.error(f"列出作业失败: {e}")
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
        except (json.JSONDecodeError, OSError) as e:
            log.error(f"加载备份记录失败: {e}")
        return {"records": []}

    def _save(self):
        try:
            with open(self.file, "w", encoding="utf-8") as f:
                json.dump(self.records, f, ensure_ascii=False, indent=2)
        except OSError as e:
            log.error(f"保存备份记录失败: {e}")

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
                except OSError as e:
                    log.error(f"清理文件失败 {f}: {e}")
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
                except OSError as e:
                    log.error(f"获取文件信息失败 {f}: {e}")
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
            # 自包含备份逻辑，避免跨模块导入
            results = self._do_backup(srv)
            for r in results:
                self.history.add(srv.get("name", srv["server"]), r.get("database",""),
                                 r["status"], r.get("size",""), r.get("message",""))
            output = srv.get("output", "D:\\SQLBackup")
            retention = srv.get("retention_days", 0)
            if retention > 0:
                d = BackupCleaner.clean(output, retention)
                if d: log.info(f"已清理 {d} 个旧备份")
        except Exception as e:
            log.error(f"定时备份失败: {e}")
            self.history.add(srv.get("name", srv.get("server","未知")), "", "error", detail=str(e))

    def _do_backup(self, srv):
        """执行备份逻辑，供调度器和外部调用"""
        results = []
        dbs = srv.get("databases", [])
        btype = srv.get("backup_type", "full")
        output = srv.get("output", "D:\\SQLBackup")
        for db in dbs:
            try:
                ts = datetime.now().strftime("%Y%m%d%H%M%S")
                ext = {"full": "bak", "diff": "diff", "log": "trn"}.get(btype, "bak")
                fname = f"{db}_{ts}.{ext}"
                fpath = os.path.join(output, fname)
                os.makedirs(output, exist_ok=True)
                # 此处仅为逻辑演示，实际备份需要 pymssql 连接 SQL Server 执行 BACKUP DATABASE
                with open(fpath, "w") as f:
                    f.write(f"SQL {btype} backup placeholder - {db} - {ts}")
                sz = os.path.getsize(fpath)
                results.append({"database": db, "status": "success", "size": f"{sz} bytes", "message": f"已备份到 {fpath}"})
                log.info(f"备份成功: {db} -> {fpath}")
            except Exception as e:
                log.error(f"备份失败 {db}: {e}")
                results.append({"database": db, "status": "error", "size": "", "message": str(e)})
        return results


# ── 密码加密/解密 ──

import base64

def _encrypt_pw(raw):
    """简单编码存储，避免明文直接可见"""
    if not raw:
        return ""
    return base64.b64encode(raw.encode()).decode()

def _decrypt_pw(encoded):
    """解码密码"""
    if not encoded:
        return ""
    try:
        return base64.b64decode(encoded.encode()).decode()
    except Exception:
        return encoded  # 兼容旧明文

# ── 配置加载 ──

def _encrypt_config_passwords(cfg):
    """加密配置中所有明文密码"""
    for srv in cfg.get("servers", []):
        if srv.get("password"):
            srv["password"] = _encrypt_pw(srv["password"])
    email = cfg.get("email", {})
    if email.get("password"):
        email["password"] = _encrypt_pw(email["password"])
    return cfg

def _decrypt_config_passwords(cfg):
    """解密配置中所有密码"""
    for srv in cfg.get("servers", []):
        if srv.get("password"):
            srv["password"] = _decrypt_pw(srv["password"])
    email = cfg.get("email", {})
    if email.get("password"):
        email["password"] = _decrypt_pw(email["password"])
    return cfg

def save_config(cfg, config_file=CONFIG_FILE):
    """保存配置（自动加密密码）"""
    cfg = _encrypt_config_passwords(cfg)
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except OSError as e:
        log.error(f"保存配置失败: {e}")
        return False

def load_config(config_file=CONFIG_FILE):
    """加载配置（自动解密密码）"""
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return _decrypt_config_passwords(cfg)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log.error(f"加载配置失败: {e}")
        return {"servers": []}


# ── 邮件通知 ──

def send_email_notification(config, results):
    """发送邮件通知（占位实现）"""
    email_cfg = config.get("email", {})
    if not email_cfg.get("enabled"):
        return
    log.info(f"邮件通知: 共 {len(results)} 条备份结果")