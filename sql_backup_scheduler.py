#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL Server 备份 - 定时调度器
支持：每天/每周指定时间执行备份
"""

import os
import sys
import json
import time
import threading
import schedule
from datetime import datetime
from sql_backup_core import do_backup, load_config, send_email_notification, logger


def parse_schedule_time(schedule_str):
    """
    解析定时配置
    格式: "daily HH:MM" / "weekly MON:HH:MM"
    返回: (type, cron_parts)
    """
    schedule_str = schedule_str.strip()
    parts = schedule_str.split()

    if len(parts) < 2:
        raise ValueError(f"定时格式错误: {schedule_str}，格式: daily HH:MM 或 weekly MON:HH:MM")

    if parts[0].lower() == "daily":
        return "daily", parts[1]
    elif parts[0].lower() == "weekly":
        if len(parts) < 2:
            raise ValueError(f"周定时需要指定星期: {schedule_str}")
        return "weekly", (parts[1].upper(), parts[2])
    else:
        raise ValueError(f"不支持的定时类型: {parts[0]}")


WEEKDAY_MAP = {
    "MON": schedule.every().monday,
    "TUE": schedule.every().tuesday,
    "WED": schedule.every().wednesday,
    "THU": schedule.every().thursday,
    "FRI": schedule.every().friday,
    "SAT": schedule.every().saturday,
    "SUN": schedule.every().sunday,
}


def run_backup_job(server_info, config):
    """执行定时备份任务"""
    name = server_info.get("name", server_info["server"])
    logger.info(f"=" * 50)
    logger.info(f"[定时任务] 开始备份: {name}")

    try:
        results = do_backup(server_info, config)
        success = sum(1 for r in results if r["status"] == "success")
        failed = sum(1 for r in results if r["status"] == "error")
        logger.info(f"[定时任务] {name}: 成功 {success}, 失败 {failed}")

        send_email_notification(config, results)
    except Exception as e:
        logger.error(f"[定时任务] {name} 执行失败: {e}")


def setup_scheduler(config):
    """设置定时任务"""
    servers = config.get("servers", [])
    if not servers:
        logger.warning("没有配置任何服务器，定时调度器不启动")
        return

    jobs_scheduled = 0

    for srv in servers:
        schedule_str = srv.get("schedule")
        if not schedule_str:
            continue

        try:
            sched_type, sched_value = parse_schedule_time(schedule_str)

            if sched_type == "daily":
                time_str = sched_value
                schedule.every().day.at(time_str).do(
                    run_backup_job, srv, config
                )
                logger.info(f"📅 [{srv.get('name', srv['server'])}] 每日 {time_str} 备份已设置")

            elif sched_type == "weekly":
                weekday, time_str = sched_value
                if weekday not in WEEKDAY_MAP:
                    logger.error(f"星期格式错误: {weekday}")
                    continue
                getattr(schedule.every(), weekday.lower()).at(time_str).do(
                    run_backup_job, srv, config
                )
                logger.info(f"📅 [{srv.get('name', srv['server'])}] 每周{weekday} {time_str} 备份已设置")

            jobs_scheduled += 1

        except Exception as e:
            logger.error(f"设置定时任务失败 [{srv.get('name', '')}]: {e}")

    if jobs_scheduled == 0:
        logger.info("没有配置定时任务")
    else:
        logger.info(f"共设置 {jobs_scheduled} 个定时任务")

    return jobs_scheduled


def run_once(config):
    """立即执行一次所有备份"""
    logger.info("=" * 60)
    logger.info("开始执行所有备份任务...")
    all_results = []

    for srv in config.get("servers", []):
        logger.info(f"-" * 40)
        logger.info(f"备份: {srv.get('name', srv['server'])}")
        try:
            results = do_backup(srv, config)
            all_results.extend(results)
        except Exception as e:
            logger.error(f"备份失败: {e}")

    send_email_notification(config, all_results)

    success = sum(1 for r in all_results if r["status"] == "success")
    failed = sum(1 for r in all_results if r["status"] == "error")
    logger.info(f"全部完成: 成功 {success}, 失败 {failed}")
    return success, failed


def main():
    import argparse
    parser = argparse.ArgumentParser(description="SQL Server 备份 - 定时调度器")
    parser.add_argument("-c", "--config", default="config.json", help="配置文件路径")
    parser.add_argument("--run-once", action="store_true", help="立即执行一次后退出")
    parser.add_argument("--daemon", action="store_true", help="后台运行")
    args = parser.parse_args()

    config = load_config(args.config)
    if not config:
        logger.error(f"无法加载配置文件: {args.config}")
        sys.exit(1)

    if args.run_once:
        success, failed = run_once(config)
        sys.exit(0 if failed == 0 else 1)

    # 设置定时任务
    jobs = setup_scheduler(config)

    if jobs == 0 and not args.daemon:
        logger.info("没有定时任务，退出")
        return

    logger.info("=" * 60)
    logger.info("定时调度器已启动，等待执行...")
    logger.info("=" * 60)

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("调度器已停止")


if __name__ == "__main__":
    main()