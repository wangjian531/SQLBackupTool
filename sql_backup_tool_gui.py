#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQLBackupTool GUI 主窗口
"""
import os, json, threading, webbrowser, sys
from tkinter import ttk, messagebox, filedialog, scrolledtext
import tkinter as tk

VERSION = "v1.2"
from sql_backup_tool_core import SQLAgentManager, BackupHistory, BackupCleaner, SoftwareScheduler, log
from sql_backup_tool_core import load_config, send_email_notification
from sql_backup_tool_core import SoftwareScheduler as _sched_for_gui

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"SQL Server 备份工具 {VERSION}")
        self.root.geometry("960x720")
        self.root.minsize(800, 600)
        self.config = load_config("config.json") or {"servers": [], "cloud": {}, "email": {}}
        self.history = BackupHistory()
        self.scheduler = SoftwareScheduler(self.config, self.history)
        self.scheduler_running = False
        self.minimize_to_tray = tk.BooleanVar(value=True)
        self._build_menu()
        self._build_tabs()
        self._build_statusbar()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(1000, self._startup_cleanup)

    def run(self): self.root.mainloop()

    def _build_menu(self):
        mb = tk.Menu(self.root); self.root.config(menu=mb)
        fm = tk.Menu(mb, tearoff=0)
        fm.add_command(label="打开配置", command=self._open_config)
        fm.add_command(label="保存配置", command=self._save)
        fm.add_separator(); fm.add_command(label="导出日志", command=self._export_log)
        fm.add_separator(); fm.add_command(label="退出", command=self.root.quit)
        mb.add_cascade(label="文件", menu=fm)
        tm = tk.Menu(mb, tearoff=0)
        tm.add_command(label="开机自启设置", command=self._autostart_dialog)
        tm.add_checkbutton(label="最小化到托盘", variable=self.minimize_to_tray)
        mb.add_cascade(label="工具", menu=tm)
        hm = tk.Menu(mb, tearoff=0)
        hm.add_command(label="关于", command=self._about)
        mb.add_cascade(label="帮助", menu=hm)

    def _build_tabs(self):
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.t1 = ttk.Frame(self.nb); self.nb.add(self.t1, text="📋 服务器管理")
        self.t2 = ttk.Frame(self.nb); self.nb.add(self.t2, text="⏰ 定时调度")
        self.t3 = ttk.Frame(self.nb); self.nb.add(self.t3, text="📜 备份记录")
        self.t4 = ttk.Frame(self.nb); self.nb.add(self.t4, text="💾 存储管理")
        self.t5 = ttk.Frame(self.nb); self.nb.add(self.t5, text="⚙️ 设置")
        self._tab_servers(); self._tab_schedule(); self._tab_history()
        self._tab_storage(); self._tab_settings()

    def _build_statusbar(self):
        self.sb = ttk.Label(self.root, text="就绪", relief=tk.SUNKEN, anchor=tk.W)
        self.sb.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=2)

    # ── 服务器管理 ──
    def _tab_servers(self):
        left = ttk.LabelFrame(self.t1, text="服务器列表", width=280)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=5, pady=5)
        lf = ttk.Frame(left); lf.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.slist = tk.Listbox(lf, font=("Consolas",10))
        self.slist.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        sb = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=self.slist.yview)
        sb.pack(fill=tk.Y, side=tk.RIGHT); self.slist.config(yscrollcommand=sb.set)
        self.slist.bind("<<ListboxSelect>>", self._on_sel)
        bf = ttk.Frame(left); bf.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(bf, text="➕ 添加", command=self._add).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="✏️ 编辑", command=self._edit).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="❌ 删除", command=self._del).pack(side=tk.LEFT, padx=2)
        right = ttk.LabelFrame(self.t1, text="服务器详情")
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.detail = scrolledtext.ScrolledText(right, font=("Consolas",10), width=50, height=20, state=tk.DISABLED)
        self.detail.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        bf2 = ttk.Frame(right); bf2.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(bf2, text="▶ 备份选中", command=self._bkp_sel).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf2, text="▶ 备份全部", command=self._bkp_all).pack(side=tk.LEFT, padx=2)
        self._reload()

    def _reload(self):
        self.slist.delete(0, tk.END)
        for s in self.config.get("servers", []):
            self.slist.insert(tk.END, s.get("name", s["server"]))

    def _on_sel(self, e):
        sel = self.slist.curselection()
        if not sel: return
        idx = sel[0]; srvs = self.config.get("servers",[])
        if idx >= len(srvs): return
        s = srvs[idx]
        d = f"名称: {s.get('name','')}\n服务器: {s['server']}:{s.get('port',1433)}\n"
        d += f"用户名: {s.get('username','sa')}\n"
        d += "输出目录: " + s.get('output','D:\\SQLBackup') + "\n"
        d += f"备份类型: {s.get('backup_type','full')}\n"
        d += f"保留天数: {s.get('retention_days',0)}\n"
        d += f"数据库: {', '.join(s.get('databases',['*']))}\n"
        sc = s.get("schedule",{})
        if sc.get("enabled"):
            d += f"定时: {'每天' if sc.get('type')=='daily' else '每周'}"
            if sc.get("type")=="weekly":
                # 解析多选星期
                days = sc.get('day', sc.get('days', 'MON'))
                # 支持 + 连接的多选格式
                parts = days.replace(":", "+").split("+") if ":" not in days or days.count(":") == 1 else [days.split(":")[0]]
                cn_map = {"MON":"一","TUE":"二","WED":"三","THU":"四","FRI":"五","SAT":"六","SUN":"日"}
                day_names = [cn_map.get(p, p) for p in parts if p in cn_map]
                d += f" 星期{'、'.join(day_names)}"
            d += f" {sc.get('time','02:00')}\n"
        else: d += "定时: 未启用\n"
        self.detail.config(state=tk.NORMAL)
        self.detail.delete(1.0, tk.END); self.detail.insert(1.0, d)
        self.detail.config(state=tk.DISABLED)

    def _dialog(self, title, srv=None):
        d = tk.Toplevel(self.root); d.title(title); d.geometry("500x550")
        d.resizable(False,False); d.transient(self.root); d.grab_set()
        f = ttk.Frame(d, padding=15); f.pack(fill=tk.BOTH, expand=True)
        row = 0
        def mk(label, default="", show=""):
            nonlocal row
            ttk.Label(f, text=label).grid(row=row, column=0, sticky=tk.W, pady=3)
            e = ttk.Entry(f, width=40, show=show)
            e.insert(0, default); e.grid(row=row, column=1, pady=3)
            row += 1; return e
        ttk.Label(f, text="连接信息", font=("",11,"bold")).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5); row+=1
        v = srv or {}
        fn = mk("名称:", v.get("name",""))
        fs = mk("服务器地址:", v.get("server",""))
        fp = mk("端口:", str(v.get("port",1433)))
        fu = mk("用户名:", v.get("username","sa"))
        fpass = mk("密码:", v.get("password",""), show="*")
        ttk.Label(f, text="备份设置", font=("",11,"bold")).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5); row+=1
        ttk.Label(f, text="数据库 (逗号, *=全部):").grid(row=row, column=0, sticky=tk.W, pady=3)
        fd = ttk.Entry(f, width=40); fd.insert(0, ",".join(v.get("databases",["*"])))
        fd.grid(row=row, column=1, pady=3); row+=1
        ttk.Label(f, text="备份类型:").grid(row=row, column=0, sticky=tk.W, pady=3)
        ft = ttk.Combobox(f, values=["full","diff","log"], state="readonly", width=10)
        ft.set(v.get("backup_type","full")); ft.grid(row=row, column=1, sticky=tk.W, pady=3); row+=1
        ttk.Label(f, text="输出目录:").grid(row=row, column=0, sticky=tk.W, pady=3)
        fo = ttk.Entry(f, width=35); fo.insert(0, v.get("output","D:\\SQLBackup"))
        fo.grid(row=row, column=1, pady=3); row+=1
        ttk.Label(f, text="保留天数 (0=不删除):").grid(row=row, column=0, sticky=tk.W, pady=3)
        fr = ttk.Entry(f, width=10); fr.insert(0, str(v.get("retention_days",30)))
        fr.grid(row=row, column=1, sticky=tk.W, pady=3); row+=1
        # 测试连接按钮和结果
        tt = ttk.Frame(f); tt.grid(row=row, column=0, columnspan=2, pady=5, sticky=tk.W); row+=1
        ttk.Button(tt, text="🔗 测试连接", command=lambda: self._test_connect(fs.get(), fp.get(), fu.get(), fpass.get())).pack(side=tk.LEFT)
        self._conn_result = ttk.Label(tt, text="", foreground="gray")
        self._conn_result.pack(side=tk.LEFT, padx=10)
        result = []
        def ok():
            data = {
                "name": fn.get() or fs.get(), "server": fs.get(),
                "port": int(fp.get() or 1433), "username": fu.get() or "sa",
                "password": fpass.get(),
                "databases": [x.strip() for x in fd.get().split(",") if x.strip()],
                "backup_type": ft.get(), "output": fo.get(),
                "retention_days": int(fr.get() or 0), "compress": False,
                "schedule": v.get("schedule", {"enabled":False,"type":"daily","time":"02:00"})
            }
            if not data["server"] or not data["password"]:
                messagebox.showerror("错误", "必填项为空"); return
            result.append(data); d.destroy()
        bf = ttk.Frame(f); bf.grid(row=row, column=0, columnspan=2, pady=15)
        ttk.Button(bf, text="保存", command=ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text="取消", command=d.destroy).pack(side=tk.LEFT, padx=5)
        self.root.wait_window(d)
        return result[0] if result else None

    def _test_connect(self, server, port, username, password):
        """测试SQL Server连接"""
        import socket
        import threading
        port = int(port or 1433)
        server = server.strip()
        if not server or not password:
            self._conn_result.config(text="❌ 服务器地址和密码不能为空", foreground="red")
            return
        self._conn_result.config(text="测试中...", foreground="blue")
        result = [None]
        def check():
            try:
                # 先检查端口是否可达
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((server, port))
                sock.close()
                # 端口通了，尝试mssql连接
                try:
                    import pymssql
                    conn = pymssql.connect(server=server, port=port, user=username, password=password, timeout=5)
                    conn.close()
                    result[0] = True
                except ImportError:
                    result[0] = "port_ok"
                except Exception as e:
                    result[0] = f"mssql_error: {e}"
            except Exception as e:
                result[0] = f"{e}"
        t = threading.Thread(target=check, daemon=True)
        t.start()
        def poll():
            if result[0] is not None:
                if result[0] is True:
                    self._conn_result.config(text="✅ 连接成功", foreground="green")
                elif result[0] == "port_ok":
                    self._conn_result.config(text="✅ 端口可达 (pymssql未安装)", foreground="green")
                else:
                    self._conn_result.config(text=f"❌ {result[0]}", foreground="red")
            else:
                self.root.after(200, poll)
        self.root.after(200, poll)

    def _add(self):
        r = self._dialog("添加服务器")
        if r:
            self.config.setdefault("servers", []).append(r)
            self._save(); self._reload()
            messagebox.showinfo("成功", f"已添加: {r['name']}")

    def _edit(self):
        sel = self.slist.curselection()
        if not sel: messagebox.showwarning("提示","请先选择"); return
        idx = sel[0]; srvs = self.config.get("servers",[])
        if idx >= len(srvs): return
        r = self._dialog("编辑服务器", srvs[idx])
        if r: srvs[idx].update(r); self._save(); self._reload()

    def _del(self):
        sel = self.slist.curselection()
        if not sel: messagebox.showwarning("提示","请先选择"); return
        idx = sel[0]; srvs = self.config.get("servers",[])
        if idx >= len(srvs): return
        s = srvs[idx]
        if messagebox.askyesno("确认", f"删除 {s.get('name',s['server'])}?"):
            del srvs[idx]; self._save(); self._reload()

    def _bkp_sel(self):
        sel = self.slist.curselection()
        if not sel: messagebox.showwarning("提示","请先选择"); return
        idx = sel[0]; srvs = self.config.get("servers",[])
        if idx >= len(srvs): return
        self.sb.config(text=f"正在备份: {srvs[idx].get('name',srvs[idx]['server'])}...")
        threading.Thread(target=self._do, args=(srvs[idx],), daemon=True).start()

    def _bkp_all(self):
        self.sb.config(text="正在备份全部...")
        for s in self.config.get("servers",[]):
            threading.Thread(target=self._do, args=(s,), daemon=True).start()

    def _do(self, srv):
        try:
            results = _sched_for_gui(self.config, BackupHistory())._do_backup(srv)
            for r in results:
                self.history.add(srv.get("name",srv["server"]), r.get("database",""),
                                 r["status"], r.get("size",""), r.get("message",""))
            out = srv.get("output","D:\\SQLBackup"); rt = srv.get("retention_days",0)
            if rt > 0: BackupCleaner.clean(out, rt)
            self.root.after(0, lambda: self.sb.config(text=f"完成: {srv.get('name',srv['server'])}"))
        except Exception as e:
            log.error(f"备份失败: {e}")
            self.history.add(srv.get("name",srv.get("server","未知")),"","error",detail=str(e))
            self.root.after(0, lambda: self.sb.config(text=f"失败: {srv.get('name',srv['server'])}"))

    # ── 定时调度 ──
    def _tab_schedule(self):
        m = ttk.Frame(self.t2, padding=15); m.pack(fill=tk.BOTH, expand=True)
        ttk.Label(m, text="定时调度设置", font=("",14,"bold")).pack(anchor=tk.W, pady=5)
        sf = ttk.LabelFrame(m, text="选择服务器"); sf.pack(fill=tk.X, pady=10)
        self.sc_var = tk.StringVar()
        self.sc_combo = ttk.Combobox(sf, textvariable=self.sc_var, width=50, state="readonly")
        self.sc_combo.pack(padx=10, pady=10)
        self.sc_combo.bind("<<ComboboxSelected>>", lambda e: self._sc_load())
        of = ttk.LabelFrame(m, text="调度设置"); of.pack(fill=tk.X, pady=10)
        rf = ttk.Frame(of); rf.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(rf, text="调度模式:").pack(side=tk.LEFT)
        self.sc_mode = tk.StringVar(value="software")
        ttk.Radiobutton(rf, text="🖥 软件后台", variable=self.sc_mode, value="software", command=self._sc_mode_chg).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(rf, text="🗄 SQL 作业", variable=self.sc_mode, value="sqlagent", command=self._sc_mode_chg).pack(side=tk.LEFT, padx=10)
        tf = ttk.Frame(of); tf.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(tf, text="执行类型:").pack(side=tk.LEFT)
        self.sc_type = tk.StringVar(value="daily")
        ttk.Radiobutton(tf, text="每天", variable=self.sc_type, value="daily").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(tf, text="每周", variable=self.sc_type, value="weekly").pack(side=tk.LEFT, padx=5)
        wf = ttk.Frame(of); wf.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(wf, text="星期:").pack(side=tk.LEFT)
        # 星期多选复选框
        self.sc_wd_vars = {}
        weekdays_cn = [("MON", "一"), ("TUE", "二"), ("WED", "三"), ("THU", "四"), ("FRI", "五"), ("SAT", "六"), ("SUN", "日")]
        self.sc_wd_frame = ttk.Frame(wf)
        self.sc_wd_frame.pack(side=tk.LEFT, padx=5)
        for eng, cn in weekdays_cn:
            v = tk.BooleanVar(value=False)
            self.sc_wd_vars[eng] = v
            ttk.Checkbutton(self.sc_wd_frame, text=cn, variable=v).pack(side=tk.LEFT, padx=2)
        # 每天/每周切换控制星期可选性
        self.sc_type.trace_add("write", lambda *a: self._sc_toggle_weekday())
        self.sc_wd_frame.pack_forget()
        hf = ttk.Frame(of); hf.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(hf, text="执行时间:").pack(side=tk.LEFT)
        self.sc_h = ttk.Combobox(hf, values=[f"{h:02d}" for h in range(24)], state="readonly", width=5)
        self.sc_h.set("02"); self.sc_h.pack(side=tk.LEFT)
        ttk.Label(hf, text=":").pack(side=tk.LEFT)
        self.sc_m = ttk.Combobox(hf, values=[f"{m:02d}" for m in range(60)], state="readonly", width=5)
        self.sc_m.set("00"); self.sc_m.pack(side=tk.LEFT)
        self.sc_agent_st = ttk.Label(of, text=""); self.sc_agent_st.pack(padx=10, pady=5)
        bf = ttk.Frame(m); bf.pack(fill=tk.X, pady=10)
        self.sc_start = ttk.Button(bf, text="▶ 启动调度", command=self._sc_start)
        self.sc_start.pack(side=tk.LEFT, padx=5)
        self.sc_stop = ttk.Button(bf, text="⏹ 停止调度", command=self._sc_stop, state=tk.DISABLED)
        self.sc_stop.pack(side=tk.LEFT, padx=5)
        self.sc_save = ttk.Button(bf, text="💾 保存设置", command=self._sc_save)
        self.sc_save.pack(side=tk.LEFT, padx=5)
        self.sc_st = ttk.Label(m, text="状态: 未启动", font=("",10,"bold"))
        self.sc_st.pack(anchor=tk.W, pady=5)
        self._sc_refresh()

    def _sc_refresh(self):
        names = [s.get("name",s["server"]) for s in self.config.get("servers",[])]
        self.sc_combo["values"] = names
        if names: self.sc_combo.set(names[0])

    def _sc_load(self):
        name = self.sc_var.get()
        for s in self.config.get("servers",[]):
            if s.get("name",s["server"])==name:
                sc = s.get("schedule",{})
                if sc.get("enabled"):
                    self.sc_type.set(sc.get("type","daily"))
                    t = sc.get("time","02:00")
                    p = t.split(":")
                    if len(p)==3: self._set_sc_wd(p[0]); self.sc_h.set(p[1]); self.sc_m.set(p[2])
                    elif len(p)==2: self.sc_h.set(p[0]); self.sc_m.set(p[1])
                break

    def _sc_toggle_weekday(self):
        """每天时星期不可选，每周时可选"""
        self.sc_wd_frame.pack_forget()
        if self.sc_type.get() == "weekly":
            self.sc_wd_frame.pack(side=tk.LEFT, padx=5)

    def _set_sc_wd(self, eng_code):
        for k, v in self.sc_wd_vars.items():
            v.set(k == eng_code)

    def _sc_get_weekdays(self):
        """获取选中的星期列表"""
        selected = [k for k, v in self.sc_wd_vars.items() if v.get()]
        return selected if selected else ["MON"]

    def _sc_mode_chg(self):
        if self.sc_mode.get()=="sqlagent":
            self.sc_agent_st.config(text="检查 Agent...", foreground="blue")
            self.root.after(100, self._sc_check)

    def _sc_check(self):
        name = self.sc_var.get()
        for s in self.config.get("servers",[]):
            if s.get("name",s["server"])==name:
                am = SQLAgentManager(s["server"],s.get("port",1433),s.get("username","sa"),s.get("password",""))
                ok, msg = am.check_agent_status()
                self.sc_agent_st.config(text=f"{'✅' if ok else '❌'} {msg}", foreground="green" if ok else "red")
                break

    def _sc_start(self):
        mode = self.sc_mode.get(); name = self.sc_var.get()
        if not name: messagebox.showwarning("提示","请选择服务器"); return
        if mode=="software":
            ok, msg = self.scheduler.start()
            if ok:
                self.scheduler_running = True
                self.sc_start.config(state=tk.DISABLED); self.sc_stop.config(state=tk.NORMAL)
                self.sc_st.config(text="状态: ✅ 运行中 (软件调度)", foreground="green")
                self.sb.config(text="软件调度已启动")
            else: messagebox.showwarning("提示", msg)
        else:
            for s in self.config.get("servers",[]):
                if s.get("name",s["server"])==name:
                    am = SQLAgentManager(s["server"],s.get("port",1433),s.get("username","sa"),s.get("password",""))
                    ok, _ = am.check_agent_status()
                    if not ok:
                        if messagebox.askyesno("Agent 未运行","是否尝试启动？"):
                            ok2, msg2 = am.start_agent()
                            if not ok2: messagebox.showerror("错误",f"启动失败: {msg2}"); return
                    t = f"{self.sc_h.get()}:{self.sc_m.get()}"
                    if self.sc_type.get()=="weekly": t = "+".join(self._sc_get_weekdays())+":"+t
                    ok3, msg3 = am.create_backup_job(s.get("name",s["server"]),s.get("databases",["*"]),
                        s.get("backup_type","full"),s.get("output","D:\\SQLBackup"),t,s.get("retention_days",30))
                    if ok3:
                        self.sc_st.config(text=f"状态: ✅ {msg3}", foreground="green")
                        self.sb.config(text=msg3)
                    else: messagebox.showerror("错误", msg3)
                    break

    def _sc_stop(self):
        self.scheduler.stop(); self.scheduler_running = False
        self.sc_start.config(state=tk.NORMAL); self.sc_stop.config(state=tk.DISABLED)
        self.sc_st.config(text="状态: ⏹ 已停止", foreground="gray")
        self.sb.config(text="调度已停止")

    def _sc_save(self):
        name = self.sc_var.get()
        if not name: return
        for s in self.config.get("servers",[]):
            if s.get("name",s["server"])==name:
                t = f"{self.sc_h.get()}:{self.sc_m.get()}"
                if self.sc_type.get()=="weekly": t = "+".join(self._sc_get_weekdays())+":"+t
                s["schedule"] = {"enabled":True,"type":self.sc_type.get(),"time":t}
                self._save(); messagebox.showinfo("成功",f"已保存到 {name}"); break

    # ── 备份记录 ──
    def _tab_history(self):
        f = ttk.Frame(self.t3, padding=10); f.pack(fill=tk.BOTH, expand=True)
        bf = ttk.Frame(f); bf.pack(fill=tk.X, pady=5)
        ttk.Button(bf, text="🔄 刷新", command=self._hist_refresh).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="🗑 清空", command=self._hist_clear).pack(side=tk.LEFT, padx=2)
        cols = ("time","server","database","status","size")
        self.ht = ttk.Treeview(f, columns=cols, show="headings", height=20)
        for c in cols:
            self.ht.heading(c, text={"time":"时间","server":"服务器","database":"数据库","status":"状态","size":"大小"}[c])
        self.ht.column("time",width=150); self.ht.column("server",width=150)
        self.ht.column("database",width=120); self.ht.column("status",width=80); self.ht.column("size",width=100)
        sb = ttk.Scrollbar(f, orient=tk.VERTICAL, command=self.ht.yview)
        self.ht.configure(yscrollcommand=sb.set)
        self.ht.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._hist_refresh()

    def _hist_refresh(self):
        for r in self.ht.get_children(): self.ht.delete(r)
        for r in self.history.get_recent():
            self.ht.insert("", tk.END, values=(r["time"],r["server"],r["database"],
                "✅" if r["status"]=="success" else "❌", r["size"]))

    def _hist_clear(self):
        if messagebox.askyesno("确认","清空所有记录？"): self.history.clear(); self._hist_refresh()

    # ── 存储管理 ──
    def _tab_storage(self):
        f = ttk.Frame(self.t4, padding=10); f.pack(fill=tk.BOTH, expand=True)
        # 左半部分：服务器本地备份查看
        left = ttk.Frame(f); left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sf = ttk.LabelFrame(left, text="选择服务器"); sf.pack(fill=tk.X, pady=10)
        self.st_var = tk.StringVar()
        self.st_cb = ttk.Combobox(sf, textvariable=self.st_var, width=50, state="readonly")
        self.st_cb.pack(padx=10, pady=10)
        ttk.Button(sf, text="📂 查看", command=self._st_refresh).pack(pady=5)
        self.st_info = ttk.Label(left, text=""); self.st_info.pack(anchor=tk.W, pady=5)
        cols = ("name","size","mtime")
        self.st_tree = ttk.Treeview(left, columns=cols, show="headings", height=15)
        self.st_tree.heading("name",text="文件名"); self.st_tree.heading("size",text="大小"); self.st_tree.heading("mtime",text="修改时间")
        self.st_tree.column("name",width=300); self.st_tree.column("size",width=100); self.st_tree.column("mtime",width=130)
        sb = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.st_tree.yview)
        self.st_tree.configure(yscrollcommand=sb.set)
        self.st_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); sb.pack(side=tk.RIGHT, fill=tk.Y)
        names = [s.get("name",s["server"]) for s in self.config.get("servers",[])]
        self.st_cb["values"] = names
        if names: self.st_cb.set(names[0])
        # 右半部分：远程存储配置
        right = ttk.Frame(f); right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10)
        rf = ttk.LabelFrame(right, text="远程存储配置 (FTP/SMB/NAS)"); rf.pack(fill=tk.BOTH, expand=True)
        self.rp_type = tk.StringVar(value="local")
        tf = ttk.Frame(rf); tf.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(tf, text="存储类型:").pack(side=tk.LEFT)
        self.rp_cb = ttk.Combobox(tf, textvariable=self.rp_type, values=["local","ftp","smb","webdav"], state="readonly", width=10)
        self.rp_cb.set("local"); self.rp_cb.pack(side=tk.LEFT, padx=5)
        def mkrow(label, key, default="", show=""):
            rf2 = ttk.Frame(rf); rf2.pack(fill=tk.X, padx=10, pady=5)
            ttk.Label(rf2, text=label).pack(side=tk.LEFT)
            e = ttk.Entry(rf2, width=30, show=show)
            e.insert(0, default); e.pack(side=tk.LEFT, padx=5); return e
        self.rp_host = mkrow("主机:", "host", "")
        self.rp_user = mkrow("用户名:", "user", "")
        self.rp_pass = mkrow("密码:", "password", "", show="*")
        self.rp_path = mkrow("远程路径:", "path", "")
        self.st_test_result = ttk.Label(rf, text=""); self.st_test_result.pack(anchor=tk.W, pady=5)
        bf = ttk.Frame(rf); bf.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(bf, text="🔗 连接测试", command=self._st_test).pack(side=tk.LEFT)

    def _st_test(self):
        """测试远程存储连接"""
        mode = self.rp_type.get()
        host = self.rp_host.get()
        user = self.rp_user.get()
        password = self.rp_pass.get()
        path = self.rp_path.get()
        self.st_test_result.config(text="测试中...", foreground="blue")
        if mode == "local":
            import os
            ok = os.path.exists(path)
            msg = f"✅ 本地路径存在" if ok else "❌ 路径不存在"
        elif mode == "ftp":
            try:
                import ftplib
                ftp = ftplib.FTP(host, timeout=10)
                ftp.login(user, password)
                ftp.quit()
                ok = True; msg = "✅ FTP 连接成功"
            except Exception as e:
                ok = False; msg = f"❌ FTP 连接失败: {e}"
        elif mode == "smb":
            try:
                import smbclient
                # 测试连接 - 列出共享目录
                # 兼容新旧版 API：新版用 list_share，旧版用 list_shares
                if hasattr(smbclient, 'list_share'):
                    shares = list(smbclient.list_share(host, username=user, password=password))
                elif hasattr(smbclient, 'list_shares'):
                    raw = smbclient.list_shares(host, username=user, password=password)
                    shares = [s.name if hasattr(s, 'name') else str(s) for s in raw]
                else:
                    raise AttributeError("smbclient 没有 list_share/list_shares 方法")
                # 尝试连接指定路径
                if path:
                    smbclient.list(path, username=user, password=password)
                ok = True; msg = f"✅ SMB 连接成功，共享目录: {' / '.join(shares)}"
            except ImportError:
                ok = False; msg = "❌ 未安装 smbprotocol 库，请先 pip install smbprotocol"
            except Exception as e:
                ok = False; msg = f"❌ SMB 连接失败: {e}"
        elif mode == "webdav":
            try:
                import requests
                r = requests.get(f"http://{host}/{path}", auth=(user, password), timeout=10)
                ok = r.status_code < 400; msg = f"✅ WebDAV 连接成功" if ok else f"❌ WebDAV 返回 {r.status_code}"
            except Exception as e:
                ok = False; msg = f"❌ WebDAV 连接失败: {e}"
        self.st_test_result.config(text=msg, foreground="green" if ok else "red")

    def _st_refresh(self):
        for r in self.st_tree.get_children(): self.st_tree.delete(r)
        name = self.st_var.get()
        for s in self.config.get("servers",[]):
            if s.get("name",s["server"])==name:
                out = s.get("output","D:\\SQLBackup")
                info = BackupCleaner.get_info(out)
                self.st_info.config(text=f"📁 {out}  |  文件: {info['file_count']} 个  |  总大小: {self._fmt(info['total_size'])}")
                for f in info["files"]:
                    storage_type = s.get("storage",{}).get("type", "本地")
                    self.st_tree.insert("", tk.END, values=(f["name"], self._fmt(f["size"]), f["mtime"], storage_type))
                break

    def _fmt(self, b):
        for u in ["B","KB","MB","GB","TB"]:
            if b < 1024: return f"{b:.1f} {u}"
            b /= 1024
        return f"{b:.1f} PB"

    # ── 设置 ──
    def _tab_settings(self):
        f = ttk.Frame(self.t5, padding=15); f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text="邮件通知", font=("",11,"bold")).pack(anchor=tk.W, pady=5)
        gf = ttk.LabelFrame(f, text="SMTP"); gf.pack(fill=tk.X, pady=10)
        def mkrow(label, key, default=""):
            rf = ttk.Frame(gf); rf.pack(fill=tk.X, padx=10, pady=5)
            ttk.Label(rf, text=label).pack(side=tk.LEFT)
            e = ttk.Entry(rf, width=30, show="*" if "密码" in label else "")
            e.insert(0, self.config.get("email",{}).get(key,default))
            e.pack(side=tk.LEFT, padx=5); return e
        self.e_smtp = mkrow("SMTP 服务器:", "smtp_server")
        self.e_port = mkrow("端口:", "smtp_port", "587")
        self.e_from = mkrow("发件邮箱:", "from")
        self.e_pass = mkrow("密码/授权码:", "password")
        self.e_to = mkrow("接收邮箱:", "to")
        ttk.Button(gf, text="💾 保存", command=self._save_email).pack(pady=10)
        ttk.Label(f, text="开机自启", font=("",11,"bold")).pack(anchor=tk.W, pady=(20,5))
        af = ttk.LabelFrame(f); af.pack(fill=tk.X, pady=10)
        ttk.Label(af, text="添加到 Windows 开机启动").pack(padx=10, pady=5)
        ttk.Button(af, text="🔧 设置", command=self._autostart_dialog).pack(pady=5)
        ttk.Label(f, text="关于", font=("",11,"bold")).pack(anchor=tk.W, pady=(20,5))
        aboutf = ttk.LabelFrame(f); aboutf.pack(fill=tk.X, pady=10)
        ttk.Label(aboutf, text=f"SQLBackupTool {VERSION}\nSQL Server 数据库备份工具\n支持 GUI / 软件调度 / SQL Agent 作业").pack(padx=10, pady=10)

    def _save(self):
        with open("config.json","w",encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
        log.info("配置已保存")

    def _save_email(self):
        self.config["email"] = {
            "smtp_server": self.e_smtp.get(), "smtp_port": self.e_port.get(),
            "from": self.e_from.get(), "password": self.e_pass.get(), "to": self.e_to.get()
        }
        self._save(); messagebox.showinfo("成功","邮箱配置已保存")

    def _open_config(self):
        if os.path.exists("config.json"):
            if sys.platform=="win32": os.startfile("config.json")
            else: webbrowser.open("config.json")

    def _export_log(self):
        if os.path.exists("sql_backup_tool.log"):
            t = filedialog.asksaveasfilename(defaultextension=".log", filetypes=[("日志","*.log")])
            if t: import shutil; shutil.copy("sql_backup_tool.log", t); messagebox.showinfo("成功","已导出")

    def _autostart_dialog(self):
        if sys.platform!="win32": messagebox.showinfo("提示","仅支持 Windows"); return
        exe = os.path.abspath(sys.argv[0])
        if not exe.endswith(".exe"): messagebox.showinfo("提示","请先打包成 exe"); return
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(k, "SQLBackupTool", 0, winreg.REG_SZ, exe)
            winreg.CloseKey(k)
            messagebox.showinfo("成功","已添加到开机自启")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _startup_cleanup(self):
        for s in self.config.get("servers",[]):
            out = s.get("output",""); rt = s.get("retention_days",0)
            if out and rt>0 and os.path.exists(out):
                d = BackupCleaner.clean(out, rt)
                if d: log.info(f"启动时清理了 {d} 个旧备份")

    def _about(self):
        messagebox.showinfo("关于", f"SQLBackupTool {VERSION}\nSQL Server 数据库备份工具\n\n功能:\n• 服务器管理 (添加/编辑/删除)\n• 立即备份 (单台/全部)\n• 定时调度 (软件后台 / SQL Agent 作业)\n• 备份记录查看\n• 存储管理 (查看/清理)\n• 邮件通知\n• 开机自启")

    def _on_close(self):
        if self.scheduler_running:
            if not messagebox.askokcancel("确认","调度器正在运行，关闭后定时备份将停止。确定关闭？"):
                return
            self.scheduler.stop()
        self.root.destroy()
