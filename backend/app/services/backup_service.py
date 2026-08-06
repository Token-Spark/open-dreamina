# Copyright 2026 Open Dreamina Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""数据库备份服务。

使用 SQLite Backup API 在线备份（不锁库），并按保留数量清理旧备份。
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

from ..config import settings


def backup_database(keep_count: int = 7) -> str:
    """执行一次 SQLite 在线备份，返回备份文件绝对路径。

    Args:
        keep_count: 保留最近 N 份备份，多余的自动删除。

    Raises:
        FileNotFoundError: 源数据库文件不存在。
    """
    db_path = settings.sqlite_db_path
    backup_dir = settings.backup_path
    backup_dir.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        raise FileNotFoundError(f"数据库文件不存在: {db_path}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"aigc_studio_{timestamp}.db"

    source = sqlite3.connect(str(db_path))
    dest = sqlite3.connect(str(backup_path))
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()

    # 清理旧备份
    backups = sorted(
        [f for f in os.listdir(backup_dir) if f.endswith(".db") and f.startswith("aigc_studio_")],
    )
    while len(backups) > keep_count:
        old = backups.pop(0)
        try:
            os.remove(backup_dir / old)
        except OSError:
            pass

    return str(backup_path)


def list_backups() -> list[dict]:
    """列出当前所有备份文件元信息（按时间倒序）。"""
    backup_dir = settings.backup_path
    if not backup_dir.exists():
        return []
    items = []
    for f in backup_dir.iterdir():
        if f.is_file() and f.name.endswith(".db") and f.name.startswith("aigc_studio_"):
            stat = f.stat()
            items.append({
                "name": f.name,
                "path": str(f),
                "size": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            })
    items.sort(key=lambda x: x["name"], reverse=True)
    return items
