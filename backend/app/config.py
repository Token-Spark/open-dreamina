"""应用配置：从环境变量加载，提供本地可直接运行的合理默认值。"""
from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置。优先级：环境变量 > .env 文件 > 默认值。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 服务
    app_host: str = "0.0.0.0"
    app_port: int = 10130
    app_name: str = "Open Dreamina API"

    # 数据库
    database_url: str = "sqlite:///./data/db/aigc_studio.db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # 文件存储
    assets_dir: str = "./data/assets"
    backup_dir: str = "./data/backups"

    # 加密
    encryption_key: str = "d3fault-encryption-key-change-me-please-32b"

    # CORS
    cors_origins: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:10131",
            "http://127.0.0.1:10131",
        ]
    )

    # 任务队列
    task_time_limit: int = 600
    task_soft_time_limit: int = 540
    max_concurrent_tasks: int = 2

    # SSE
    sse_heartbeat_interval: int = 15

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def sqlite_db_path(self) -> Path:
        """从 database_url 解析出 SQLite 文件路径（仅支持 sqlite:/// 前缀）。"""
        url = self.database_url
        if url.startswith("sqlite:///"):
            return Path(url.replace("sqlite:///", "", 1))
        return Path("data/db/aigc_studio.db")

    @property
    def assets_path(self) -> Path:
        return Path(self.assets_dir)

    @property
    def backup_path(self) -> Path:
        return Path(self.backup_dir)

    def ensure_dirs(self) -> None:
        """确保运行时目录存在（db 父目录、assets、backups）。"""
        self.sqlite_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.assets_path.mkdir(parents=True, exist_ok=True)
        self.backup_path.mkdir(parents=True, exist_ok=True)


settings = Settings()
