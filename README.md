# SQL Server 备份工具

支持将 SQL Server 数据库备份到本地、共享文件夹、网盘（阿里云盘 / 百度网盘）。

## 功能特点

- ✅ 支持 SQL Server 2008+ / 2012 / 2014 / 2016 / 2017 / 2019 / 2022
- ✅ 备份到 **本地磁盘**
- ✅ 备份到 **共享文件夹**（SMB / NAS）
- ✅ 备份到 **网盘**（阿里云盘 / 百度网盘）
- ✅ **全量备份 / 差异备份 / 事务日志备份**
- ✅ **压缩备份**（使用 7z / zip）
- ✅ **自动清理过期备份**
- ✅ **定时任务**（内置调度器）
- ✅ **邮件通知**（备份成功/失败）
- ✅ **图形界面**（Tkinter）
- ✅ **命令行模式**（支持静默运行）

## 安装

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 2. 安装 7-Zip（可选，用于压缩备份）

- Windows: 下载安装 https://www.7-zip.org/
- Linux: `apt install p7zip-full`

### 3. 网盘支持（可选）

- **阿里云盘**: 首次使用需扫码登录
- **百度网盘**: 需配置 App Key / Secret

## 使用方法

### 图形界面模式

```bash
python sql_backup_gui.py
```

### 命令行模式

```bash
# 全量备份
python sql_backup_cli.py --server 127.0.0.1 --database MyDB --user sa --pass 123456 --type full

# 备份到共享文件夹
python sql_backup_cli.py --server 127.0.0.1 --database MyDB --output \\NAS\Backup --type full

# 备份并压缩
python sql_backup_cli.py --server 127.0.0.1 --database MyDB --compress --type full

# 备份到网盘
python sql_backup_cli.py --server 127.0.0.1 --database MyDB --cloud aliyun --type full
```

### 定时任务

```bash
python sql_backup_scheduler.py
```

## 配置文件

编辑 `config.json`:

```json
{
  "servers": [
    {
      "name": "正式库",
      "server": "127.0.0.1",
      "port": 1433,
      "username": "sa",
      "password": "密码",
      "databases": ["MyDB1", "MyDB2"],
      "backup_type": "full",
      "output": "D:\\Backup",
      "compress": true,
      "retention_days": 7,
      "cloud": null,
      "schedule": "daily 02:00"
    }
  ],
  "cloud": {
    "aliyun": {
      "refresh_token": "xxx",
      "drive_id": "xxx"
    },
    "baidu": {
      "app_key": "xxx",
      "app_secret": "xxx",
      "access_token": "xxx"
    }
  },
  "email": {
    "smtp_server": "smtp.qq.com",
    "smtp_port": 465,
    "sender": "your@qq.com",
    "password": "授权码",
    "receivers": ["admin@company.com"]
  }
}
```

## 项目结构

```
SQLBackupTool/
├── sql_backup_gui.py       # 图形界面
├── sql_backup_cli.py       # 命令行
├── sql_backup_core.py      # 核心备份逻辑
├── sql_backup_scheduler.py # 定时调度
├── cloud_uploader.py       # 网盘上传
├── config.json             # 配置文件
├── requirements.txt        # Python依赖
└── README.md               # 说明文档
```