#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL Server 备份 - 图形界面 (Tkinter)
"""

import os
import sys
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from datetime import datetime
from sql_backup_core import do_backup, load_config, send_email_notification, logger


class SQLBackupGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("SQL Server 备份工具 v1.0")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        # 配置文件路径
        self.config_file = "config.json"
        self.current_config = load_config(self.config_file) or {
            "servers": [],
            "cloud": {"aliyun": {}, "baidu": {}},
            "email": {}
        }

        self.setup_ui()
        self.load_server_list()

    def setup_ui(self):
        """创建界面"""
        # 菜单栏
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="打开配置", command=self.open_config)
        file_menu.add_command(label="保存配置", command=self.save_config)
        file_menu.add_separator()
        file_menu.add_command(label="导出日志", command=self.export_log)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.quit)
        menubar.add_cascade(label="文件", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="关于", command=self.show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)

        # 主布局 - 左右分栏
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 左侧 - 服务器列表
        left_frame = ttk.LabelFrame(paned, text="服务器列表", width=250)
        paned.add(left_frame, weight=1)

        # 服务器列表框
        list_frame = ttk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.server_listbox = tk.Listbox(list_frame, font=("Consolas", 10))
        self.server_listbox.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.server_listbox.yview)
        scrollbar.pack(fill=tk.Y, side=tk.RIGHT)
        self.server_listbox.config(yscrollcommand=scrollbar.set)
        self.server_listbox.bind("<<ListboxSelect>>", self.on_server_select)

        # 服务器操作按钮
        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(btn_frame, text="➕ 添加", command=self.add_server_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="✏️ 编辑", command=self.edit_server_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="❌ 删除", command=self.delete_server).pack(side=tk.LEFT, padx=2)

        # 右侧 - 详情和执行
        right_frame = ttk.LabelFrame(paned, text="操作面板")
        paned.add(right_frame, weight=3)

        # 服务器详情
        detail_frame = ttk.LabelFrame(right_frame, text="服务器详情")
        detail_frame.pack(fill=tk.X, padx=5, pady=5)

        self.detail_text = tk.Text(detail_frame, height=6, font=("Consolas", 9), state=tk.DISABLED)
        self.detail_text.pack(fill=tk.X, padx=5, pady=5)

        # 备份选项
        opt_frame = ttk.LabelFrame(right_frame, text="备份选项")
        opt_frame.pack(fill=tk.X, padx=5, pady=5)

        opt_inner = ttk.Frame(opt_frame)
        opt_inner.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(opt_inner, text="备份类型:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.backup_type = ttk.Combobox(opt_inner, values=["full", "diff", "log"], state="readonly", width=10)
        self.backup_type.set("full")
        self.backup_type.grid(row=0, column=1, sticky=tk.W, padx=5)

        ttk.Label(opt_inner, text="保留天数:").grid(row=0, column=2, sticky=tk.W, padx=5)
        self.retention_var = tk.StringVar(value="7")
        ttk.Entry(opt_inner, textvariable=self.retention_var, width=8).grid(row=0, column=3, sticky=tk.W, padx=5)

        self.compress_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt_inner, text="7z 压缩", variable=self.compress_var).grid(row=0, column=4, padx=10)

        # 执行按钮
        action_frame = ttk.Frame(right_frame)
        action_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(action_frame, text="▶ 执行备份", command=self.run_backup,
                   style="Accent.TButton").pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="▶ 备份所有服务器",
                   command=self.run_all_backups).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="⏹ 停止", command=self.stop_backup,
                   state=tk.DISABLED).pack(side=tk.LEFT, padx=5)

        # 输出日志
        log_frame = ttk.LabelFrame(right_frame, text="执行日志")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, font=("Consolas", 9), state=tk.DISABLED,
            wrap=tk.WORD, bg="#1e1e1e", fg="#d4d4d4"
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 底部状态栏
        self.status_bar = ttk.Label(self.root, text="就绪", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # 进度条
        self.progress = ttk.Progressbar(self.root, mode="indeterminate")
        self.progress.pack(fill=tk.X, side=tk.BOTTOM, padx=5)

        # 状态
        self.is_running = False
        self.stop_flag = False

    def log(self, message, level="INFO"):
        """向日志区域输出"""
        self.log_text.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")
        color_map = {
            "INFO": "#d4d4d4",
            "WARNING": "#e8bf6a",
            "ERROR": "#f44747",
            "SUCCESS": "#4ec9b0"
        }
        color = color_map.get(level, "#d4d4d4")
        self.log_text.insert(tk.END, f"[{timestamp}] ", "#888888")
        self.log_text.insert(tk.END, f"{message}\n", color)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.root.update_idletasks()

    def set_status(self, text):
        """更新状态栏"""
        self.status_bar.config(text=text)
        self.root.update_idletasks()

    def load_server_list(self):
        """刷新服务器列表"""
        self.server_listbox.delete(0, tk.END)
        for srv in self.current_config.get("servers", []):
            name = srv.get("name", srv["server"])
            dbs = srv.get("databases", ["*"])
            db_str = "*" if dbs == ["*"] else ",".join(dbs[:2])
            display = f"{name} [{db_str}]"
            self.server_listbox.insert(tk.END, display)

    def get_selected_server_index(self):
        """获取选中的服务器索引"""
        sel = self.server_listbox.curselection()
        return sel[0] if sel else -1

    def on_server_select(self, event):
        """选中服务器时显示详情"""
        idx = self.get_selected_server_index()
        if idx < 0:
            return
        srv = self.current_config["servers"][idx]

        detail = (
            f"服务器: {srv['server']}:{srv.get('port', 1433)}\n"
            f"用户名: {srv.get('username', 'sa')}\n"
            f"数据库: {', '.join(srv.get('databases', ['*']))}\n"
            "输出目录: " + srv.get('output', 'D:\\SQLBackup') + "\n"
            f"默认备份类型: {srv.get('backup_type', 'full')}\n"
            f"保留天数: {srv.get('retention_days', 0)}"
        )
        self.detail_text.config(state=tk.NORMAL)
        self.detail_text.delete(1.0, tk.END)
        self.detail_text.insert(1.0, detail)
        self.detail_text.config(state=tk.DISABLED)

    def add_server_dialog(self):
        """添加服务器对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("添加服务器")
        dialog.geometry("450x350")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        fields = {}
        row = 0
        labels = [
            ("名称:", "name", "正式库"),
            ("服务器:", "server", "127.0.0.1"),
            ("端口:", "port", "1433"),
            ("用户名:", "username", "sa"),
            ("密码:", "password", ""),
            ("数据库:", "databases", "* (逗号分隔)"),
            ("输出目录:", "output", "D:\\SQLBackup"),
        ]

        for label, key, default in labels:
            ttk.Label(dialog, text=label).grid(row=row, column=0, sticky=tk.W, padx=10, pady=5)
            entry = ttk.Entry(dialog, width=40)
            entry.insert(0, default)
            entry.grid(row=row, column=1, padx=10, pady=5)
            if key == "password":
                entry.config(show="*")
            fields[key] = entry
            row += 1

        def save():
            server_info = {
                "name": fields["name"].get(),
                "server": fields["server"].get(),
                "port": int(fields["port"].get()),
                "username": fields["username"].get(),
                "password": fields["password"].get(),
                "databases": [d.strip() for d in fields["databases"].get().split(",")],
                "output": fields["output"].get(),
                "backup_type": "full",
                "compress": False,
                "retention_days": 7,
                "cloud": None,
                "schedule": None
            }
            self.current_config.setdefault("servers", []).append(server_info)
            self.save_config()
            self.load_server_list()
            dialog.destroy()
            self.log(f"已添加服务器: {server_info['name']}", "SUCCESS")

        ttk.Button(dialog, text="确定", command=save).grid(row=row, column=0, pady=15)
        ttk.Button(dialog, text="取消", command=dialog.destroy).grid(row=row, column=1, pady=15)

    def edit_server_dialog(self):
        """编辑服务器对话框"""
        idx = self.get_selected_server_index()
        if idx < 0:
            messagebox.showwarning("提示", "请先选择一个服务器")
            return

        srv = self.current_config["servers"][idx]
        dialog = tk.Toplevel(self.root)
        dialog.title("编辑服务器")
        dialog.geometry("450x350")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        fields = {}
        row = 0
        labels = [
            ("名称:", "name", srv.get("name", "")),
            ("服务器:", "server", srv.get("server", "")),
            ("端口:", "port", str(srv.get("port", 1433))),
            ("用户名:", "username", srv.get("username", "sa")),
            ("密码:", "password", srv.get("password", "")),
            ("数据库:", "databases", ",".join(srv.get("databases", ["*"]))),
            ("输出目录:", "output", srv.get("output", "D:\\SQLBackup")),
        ]

        for label, key, default in labels:
            ttk.Label(dialog, text=label).grid(row=row, column=0, sticky=tk.W, padx=10, pady=5)
            entry = ttk.Entry(dialog, width=40)
            entry.insert(0, default)
            entry.grid(row=row, column=1, padx=10, pady=5)
            if key == "password":
                entry.config(show="*")
            fields[key] = entry
            row += 1

        def save():
            self.current_config["servers"][idx] = {
                "name": fields["name"].get(),
                "server": fields["server"].get(),
                "port": int(fields["port"].get()),
                "username": fields["username"].get(),
                "password": fields["password"].get(),
                "databases": [d.strip() for d in fields["databases"].get().split(",")],
                "output": fields["output"].get(),
                "backup_type": srv.get("backup_type", "full"),
                "compress": srv.get("compress", False),
                "retention_days": srv.get("retention_days", 7),
                "cloud": srv.get("cloud"),
                "schedule": srv.get("schedule")
            }
            self.save_config()
            self.load_server_list()
            dialog.destroy()
            self.log(f"已更新服务器: {fields['name'].get()}", "SUCCESS")

        ttk.Button(dialog, text="确定", command=save).grid(row=row, column=0, pady=15)
        ttk.Button(dialog, text="取消", command=dialog.destroy).grid(row=row, column=1, pady=15)

    def delete_server(self):
        """删除服务器"""
        idx = self.get_selected_server_index()
        if idx < 0:
            messagebox.showwarning("提示", "请先选择一个服务器")
            return

        name = self.current_config["servers"][idx].get("name", "")
        if messagebox.askyesno("确认", f"确定删除服务器 [{name}] 吗？"):
            del self.current_config["servers"][idx]
            self.save_config()
            self.load_server_list()
            self.log(f"已删除服务器: {name}", "INFO")

    def run_backup(self):
        """执行选中的服务器备份"""
        idx = self.get_selected_server_index()
        if idx < 0:
            messagebox.showwarning("提示", "请先选择一个服务器")
            return

        if self.is_running:
            messagebox.showwarning("提示", "备份任务正在执行中")
            return

        srv = self.current_config["servers"][idx].copy()
        srv["backup_type"] = self.backup_type.get()
        srv["compress"] = self.compress_var.get()
        srv["retention_days"] = int(self.retention_var.get())

        self.is_running = True
        self.stop_flag = False
        self.progress.start()
        self.set_status(f"正在备份: {srv.get('name', srv['server'])}...")

        def task():
            try:
                results = do_backup(srv, self.current_config)
                success = sum(1 for r in results if r["status"] == "success")
                failed = sum(1 for r in results if r["status"] == "error")

                self.root.after(0, lambda: self.log(
                    f"备份完成: 成功 {success}, 失败 {failed}",
                    "SUCCESS" if failed == 0 else "WARNING"
                ))
                self.root.after(0, lambda: self.set_status(
                    f"备份完成: 成功 {success}, 失败 {failed}"
                ))

                if failed > 0:
                    for r in results:
                        if r["status"] == "error":
                            self.root.after(0, lambda e=r.get("error", ""):
                                self.log(f"  ❌ {e}", "ERROR"))

            except Exception as e:
                self.root.after(0, lambda: self.log(f"备份失败: {e}", "ERROR"))
            finally:
                self.root.after(0, lambda: self.progress.stop())
                self.root.after(0, lambda: self.set_status("就绪"))
                self.root.after(0, lambda: setattr(self, 'is_running', False))

        threading.Thread(target=task, daemon=True).start()

    def run_all_backups(self):
        """备份所有服务器"""
        if not self.current_config.get("servers"):
            messagebox.showwarning("提示", "没有配置任何服务器")
            return

        if self.is_running:
            messagebox.showwarning("提示", "备份任务正在执行中")
            return

        self.is_running = True
        self.stop_flag = False
        self.progress.start()
        self.set_status("正在备份所有服务器...")

        def task():
            all_results = []
            for srv in self.current_config["servers"]:
                if self.stop_flag:
                    break
                si = srv.copy()
                si["backup_type"] = self.backup_type.get()
                si["compress"] = self.compress_var.get()
                si["retention_days"] = int(self.retention_var.get())

                self.root.after(0, lambda n=si.get("name", ""):
                    self.log(f"开始备份: {n}", "INFO"))
                self.root.after(0, lambda n=si.get("name", ""):
                    self.set_status(f"正在备份: {n}..."))

                try:
                    results = do_backup(si, self.current_config)
                    all_results.extend(results)
                except Exception as e:
                    self.root.after(0, lambda e=e: self.log(f"备份失败: {e}", "ERROR"))

            send_email_notification(self.current_config, all_results)

            success = sum(1 for r in all_results if r["status"] == "success")
            failed = sum(1 for r in all_results if r["status"] == "error")
            self.root.after(0, lambda: self.log(
                f"全部完成: 成功 {success}, 失败 {failed}",
                "SUCCESS" if failed == 0 else "WARNING"
            ))
            self.root.after(0, lambda: self.set_status(
                f"全部完成: 成功 {success}, 失败 {failed}"
            ))
            self.root.after(0, lambda: self.progress.stop())
            self.root.after(0, lambda: setattr(self, 'is_running', False))

        threading.Thread(target=task, daemon=True).start()

    def stop_backup(self):
        """停止备份"""
        self.stop_flag = True
        self.log("正在停止备份...", "WARNING")

    def open_config(self):
        """打开配置文件"""
        file_path = filedialog.askopenfilename(
            title="选择配置文件",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        if file_path:
            cfg = load_config(file_path)
            if cfg:
                self.current_config = cfg
                self.config_file = file_path
                self.load_server_list()
                self.log(f"已加载配置: {file_path}", "SUCCESS")
            else:
                messagebox.showerror("错误", "配置文件格式错误")

    def save_config(self):
        """保存配置"""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.current_config, f, ensure_ascii=False, indent=2)
            self.log(f"配置已保存: {self.config_file}", "SUCCESS")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")

    def export_log(self):
        """导出日志"""
        file_path = filedialog.asksaveasfilename(
            title="导出日志",
            defaultextension=".log",
            filetypes=[("日志文件", "*.log"), ("文本文件", "*.txt")]
        )
        if file_path:
            try:
                self.log_text.config(state=tk.NORMAL)
                content = self.log_text.get(1.0, tk.END)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.log_text.config(state=tk.DISABLED)
                self.log(f"日志已导出: {file_path}", "SUCCESS")
            except Exception as e:
                messagebox.showerror("错误", f"导出失败: {e}")

    def show_about(self):
        """关于对话框"""
        messagebox.showinfo(
            "关于 SQL Server 备份工具",
            "SQL Server 备份工具 v1.0\n\n"
            "支持备份到本地、共享文件夹、网盘\n"
            "支持全量/差异/日志备份\n"
            "支持自动压缩和清理\n\n"
            "Python + Tkinter 实现"
        )


def main():
    root = tk.Tk()
    app = SQLBackupGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()