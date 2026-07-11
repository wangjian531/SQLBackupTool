#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网盘上传模块
支持：阿里云盘、百度网盘
"""

import os
import json
import logging
import requests
import time
from pathlib import Path

logger = logging.getLogger("CloudUploader")


class AliyunDriveUploader:
    """阿里云盘上传"""

    def __init__(self, refresh_token, drive_id=None):
        self.refresh_token = refresh_token
        self.drive_id = drive_id
        self.access_token = None
        self._login()

    def _login(self):
        """登录获取 access_token"""
        url = "https://auth.aliyundrive.com/v2/account/token"
        resp = requests.post(url, json={
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token
        })
        data = resp.json()
        if "access_token" not in data:
            raise RuntimeError(f"阿里云盘登录失败: {data.get('message', '未知错误')}")

        self.access_token = data["access_token"]
        if not self.drive_id:
            self.drive_id = data.get("default_drive_id", "")
        logger.info("✅ 阿里云盘登录成功")

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    def get_file_list(self, parent_id="root"):
        """获取文件列表"""
        url = "https://api.aliyundrive.com/v2/file/list"
        resp = requests.post(url, headers=self._headers(), json={
            "drive_id": self.drive_id,
            "parent_file_id": parent_id,
            "limit": 100
        })
        return resp.json()

    def create_folder(self, name, parent_id="root"):
        """创建文件夹"""
        url = "https://api.aliyundrive.com/v2/file/create"
        resp = requests.post(url, headers=self._headers(), json={
            "drive_id": self.drive_id,
            "parent_file_id": parent_id,
            "name": name,
            "type": "folder"
        })
        data = resp.json()
        return data.get("file_id", "")

    def ensure_folder(self, path):
        """确保文件夹路径存在，返回最后一级 file_id"""
        parts = path.strip("/").split("/")
        parent_id = "root"

        for part in parts:
            # 检查是否已存在
            flist = self.get_file_list(parent_id)
            items = flist.get("items", [])
            found = None
            for item in items:
                if item["name"] == part and item["type"] == "folder":
                    found = item["file_id"]
                    break

            if found:
                parent_id = found
            else:
                parent_id = self.create_folder(part, parent_id)

        return parent_id

    def upload_file(self, local_path, remote_dir="/SQLBackup"):
        """上传文件到阿里云盘"""
        if not os.path.exists(local_path):
            logger.error(f"文件不存在: {local_path}")
            return False

        filename = os.path.basename(local_path)
        file_size = os.path.getsize(local_path)

        # 确保远程目录
        folder_id = self.ensure_folder(remote_dir)

        # 创建上传任务
        url = "https://api.aliyundrive.com/v2/file/create"
        resp = requests.post(url, headers=self._headers(), json={
            "drive_id": self.drive_id,
            "parent_file_id": folder_id,
            "name": filename,
            "type": "file",
            "size": file_size
        })
        data = resp.json()
        upload_url = data.get("part_info_list", [{}])[0].get("upload_url", "")
        file_id = data.get("file_id", "")

        if not upload_url:
            # 可能文件已存在，尝试覆盖
            logger.info(f"文件可能已存在，尝试上传...")
            upload_url = data.get("part_info_list", [{}])[0].get("upload_url", "")

        if not upload_url:
            logger.error("获取上传地址失败")
            return False

        # 上传文件
        logger.info(f"上传中: {filename} ({file_size / 1024 / 1024:.1f} MB)")
        with open(local_path, "rb") as f:
            resp = requests.put(upload_url, data=f)

        if resp.status_code in (200, 201):
            # 完成上传
            complete_url = "https://api.aliyundrive.com/v2/file/complete"
            requests.post(complete_url, headers=self._headers(), json={
                "drive_id": self.drive_id,
                "file_id": file_id
            })
            logger.info(f"✅ 阿里云盘上传完成: {filename}")
            return True
        else:
            logger.error(f"上传失败: HTTP {resp.status_code}")
            return False


class BaiduPanUploader:
    """百度网盘上传"""

    def __init__(self, app_key, app_secret, access_token=None):
        self.app_key = app_key
        self.app_secret = app_secret
        self.access_token = access_token

    def upload_file(self, local_path, remote_dir="/apps/SQLBackup"):
        """上传到百度网盘"""
        if not os.path.exists(local_path):
            logger.error(f"文件不存在: {local_path}")
            return False

        if not self.access_token:
            logger.error("未配置百度网盘 access_token")
            return False

        filename = os.path.basename(local_path)
        file_size = os.path.getsize(local_path)

        # 百度网盘 API 上传
        # 1. 预上传
        precreate_url = "https://pan.baidu.com/rest/2.0/xpan/file?method=precreate"
        params = {
            "access_token": self.access_token,
            "path": f"{remote_dir}/{filename}",
            "size": file_size,
            "isdir": "0",
            "rtype": "3",
            "autoinit": "1"
        }
        resp = requests.get(precreate_url, params=params)
        data = resp.json()

        if data.get("errno") != 0:
            logger.error(f"预上传失败: {data}")
            return False

        upload_id = data.get("uploadid", "")
        block_list = data.get("block_list", [])

        # 2. 分片上传（简化版 - 小文件一次性上传）
        upload_url = "https://d.pcs.baidu.com/rest/2.0/pcs/file?method=upload"
        params = {
            "access_token": self.access_token,
            "path": f"{remote_dir}/{filename}",
            "upload_id": upload_id,
            "partseq": "0"
        }

        with open(local_path, "rb") as f:
            files = {"file": (filename, f, "application/octet-stream")}
            resp = requests.post(upload_url, params=params, files=files)

        if resp.status_code in (200, 201):
            logger.info(f"✅ 百度网盘上传完成: {filename}")
            return True
        else:
            logger.error(f"上传失败: HTTP {resp.status_code}")
            return False


def upload_to_cloud(local_path, cloud_config, cloud_type="aliyun"):
    """
    上传文件到网盘

    cloud_config: 配置文件中的 cloud 部分
    cloud_type: "aliyun" 或 "baidu"
    """
    if not cloud_config:
        logger.warning("未配置网盘信息")
        return False

    if cloud_type == "aliyun":
        cfg = cloud_config.get("aliyun", {})
        if not cfg.get("refresh_token"):
            logger.warning("未配置阿里云盘 refresh_token")
            return False
        uploader = AliyunDriveUploader(
            cfg["refresh_token"],
            cfg.get("drive_id")
        )
        return uploader.upload_file(local_path)

    elif cloud_type == "baidu":
        cfg = cloud_config.get("baidu", {})
        if not cfg.get("access_token"):
            logger.warning("未配置百度网盘 access_token")
            return False
        uploader = BaiduPanUploader(
            cfg.get("app_key", ""),
            cfg.get("app_secret", ""),
            cfg.get("access_token")
        )
        return uploader.upload_file(local_path)

    else:
        logger.error(f"不支持的网盘类型: {cloud_type}")
        return False


if __name__ == "__main__":
    # 测试
    from sql_backup_core import load_config
    cfg = load_config()

    if cfg and cfg.get("cloud"):
        test_file = "test.txt"
        with open(test_file, "w") as f:
            f.write("test")

        upload_to_cloud(test_file, cfg["cloud"], "aliyun")
        os.remove(test_file)
    else:
        print("请先在 config.json 中配置网盘信息")