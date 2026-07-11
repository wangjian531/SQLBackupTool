#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL Server 备份 - 命令行工具
"""

import os
import sys
import argparse
import json
from sql_backup_core import (
    load_config, do_backup, send_email_notification, logger
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="SQL Server 备份工具 - 命令行版",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 全量备份
  python sql_backup_cli.py -s 127.0.0.1 -d MyDB -u sa -p 123456

  # 差异备份
  python sql_backup_cli.py -s 127.0.0.1 -d MyDB -u sa -p 123456 -t diff

  # 备份到共享文件夹
  python sql_backup_cli.py -s 127.0.0.1 -d MyDB -u sa -p 123456 -o \\\\NAS\\Backup

  # 备份并压缩
  python sql_backup_cli.py -s 127.0.0.1 -d MyDB -u sa -p 123456 -c

  # 使用配置文件执行
  python sql_backup_cli.py --config config.json
        """
    )

    # 连接参数
    parser.add_argument("-s", "--server", help="SQL Server 地址")
    parser.add_argument("-P", "--port", type=int, default=1433, help="端口 (默认 1433)")
    parser.add_argument("-d", "--database", help="数据库名 (用逗号分隔多个)")
    parser.add_argument("-u", "--user", default="sa", help="用户名 (默认 sa)")
    parser.add_argument("-p", "--password", help="密码")

    # 备份参数
    parser.add_argument("-t", "--type", choices=["full", "diff", "log"],
                        default="full", help="备份类型 (默认 full)")
    parser.add_argument("-o", "--output", default="D:\\SQLBackup",
                        help="输出目录 (默认 D:\\SQLBackup)")
    parser.add_argument("-c", "--compress", action="store_true",
                        help="启用 7z 压缩")
    parser.add_argument("-r", "--retention", type=int, default=0,
                        help="保留天数 (0=不清理)")

    # 网盘
    parser.add_argument("--cloud", choices=["aliyun", "baidu"],
                        help="上传到网盘")

    # 配置文件模式
    parser.add_argument("--config", help="使用配置文件执行")

    return parser.parse_args()


def main():
    args = parse_args()

    if args.config:
        # 配置文件模式
        cfg = load_config(args.config)
        if not cfg or not cfg.get("servers"):
            logger.error("配置文件为空或格式错误")
            sys.exit(1)

        all_results = []
        for srv in cfg["servers"]:
            logger.info(f"=" * 50)
            logger.info(f"开始备份: {srv.get('name', srv['server'])}")
            results = do_backup(srv, cfg)
            all_results.extend(results)

        send_email_notification(cfg, all_results)

        # 统计
        success = sum(1 for r in all_results if r["status"] == "success")
        failed = sum(1 for r in all_results if r["status"] == "error")
        logger.info(f"=" * 50)
        logger.info(f"备份完成: 成功 {success}, 失败 {failed}")
        if failed > 0:
            sys.exit(1)

    else:
        # 命令行模式
        if not args.server or not args.database or not args.password:
            print("错误: 请指定 --server, --database, --password")
            print("使用 --help 查看帮助")
            sys.exit(1)

        server_info = {
            "name": args.server,
            "server": args.server,
            "port": args.port,
            "username": args.user,
            "password": args.password,
            "databases": args.database.split(","),
            "backup_type": args.type,
            "output": args.output,
            "compress": args.compress,
            "retention_days": args.retention,
            "cloud": args.cloud
        }

        results = do_backup(server_info)
        success = sum(1 for r in results if r["status"] == "success")
        failed = sum(1 for r in results if r["status"] == "error")
        logger.info(f"备份完成: 成功 {success}, 失败 {failed}")
        if failed > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()