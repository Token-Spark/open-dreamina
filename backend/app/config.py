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

    # 素材审核：Spark Hub 需要可公网访问的素材 URL（形如 http://host/api/v1/assets/{id}/file）。
    # 部署时需配置为外部可访问的地址，否则无法提交 Seedance 参考素材审核。
    public_base_url: str = ""

    # 七牛云对象存储：为 Seedance 参考素材提供公网临时 URL（14 天自动过期）。
    # 配置后优先使用七牛云上传；未配置时回退到 public_base_url 指向本服务的地址。
    qiniu_access_key: str = ""
    qiniu_secret_key: str = ""
    qiniu_bucket: str = ""
    qiniu_domain: str = ""
    # 临时文件保留天数，到期由七牛云生命周期规则自动删除
    qiniu_audit_expire_days: int = 14

    # 团队资产同步签名密钥（HMAC）。不设置时复用 QINIU_SECRET_KEY：
    # 能访问同一云存储的成员天然共享该密钥，manifest 签名即可互验。
    team_secret: str = ""

    # 加密（必须显式配置，无默认值；deploy 脚本会自动生成随机值写入 .env）
    # 未设置时启动即报错，避免使用弱默认值导致 API Key 加密形同虚设
    encryption_key: str

    # CORS
    cors_origins: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:10131",
            "http://127.0.0.1:10131",
        ]
    )

    # 任务队列
    # 注意：Spark Hub 生视频为异步任务，单次轮询最长等待 _POLL_TIMEOUT=600s，
    # 加上结果下载/落盘，总耗时可能超过 600s。因此软/硬超时必须显著大于 600s，
    # 否则长视频生成会被 Celery 以 SoftTimeLimitExceeded 杀掉（表现为"一直生成中"后失败）。
    # 软超时 1200s（20 分钟），硬超时需大于软超时。
    task_time_limit: int = 1260
    task_soft_time_limit: int = 1200
    max_concurrent_tasks: int = 2

    # SSE
    sse_heartbeat_interval: int = 15

    # 3D 导演台：iframe 嵌入地址（二创协议见 docs/embed-contract.md）。
    # 默认指向 GitHub Pages 在线版；离线/自托管时改为本地部署地址。
    director_desk_url: str = "https://xiaozangao.github.io/3d-director-desk/"

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
