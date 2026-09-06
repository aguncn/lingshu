# 集中配置。所有取值先读环境变量（backend/__init__.py 已加载根 .env），再回落默认值。
# 后续模型/密钥/上传目录等都会从 Config 取，避免散落在各模块里。
from __future__ import annotations

import os
from pathlib import Path

# 仓库根 = backend/config.py 的上两级（backend/ -> 仓库根）
BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    # 数据目录：sqlite + 落盘文件统一放这里（.gitignore 已排除），可用 LINGSHU_DATA_DIR 覆盖
    # 注意：空字符串也要回落默认值——os.getenv 对「存在但为空」的变量仍返回 ""，
    # 若直接 Path("") 会解析成当前目录，导致迁移落 ./app.db 而 ORM 却走 Flask 默认
    # instance/app.db（两处库不一致 → 启动后每张表都 no such table → 500）。
    _DATA_DIR_ENV = os.getenv("LINGSHU_DATA_DIR", "").strip()
    DATA_DIR = Path(_DATA_DIR_ENV) if _DATA_DIR_ENV else BASE_DIR / "backend" / "data"

    # SQLite 单文件库绝对路径（技术方案 §9：backend/data/app.db）
    SQLITE_PATH = DATA_DIR / "app.db"

    # SQLAlchemy 引擎 URI：Windows 下用正斜杠绝对路径，避免按 cwd 漂移
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{SQLITE_PATH.as_posix()}"

    # CORS 允许来源（逗号分隔）。开发态放行 Vite 的 5173（含 127.0.0.1）
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if origin.strip()
    ]

    # Fernet 主密钥。本期仅占位约定读取方式，不落库不加密业务数据（见 P10 security-audit）
    MASTER_KEY = os.getenv("LINGSHU_MASTER_KEY", "")

    @classmethod
    def ensure_dirs(cls) -> None:
        """确保数据目录存在。

        为什么这里主动 mkdir：若依赖 SQLAlchemy 首次建连才建目录，
        data/ 不存在时 sqlite 会直接报错，且目录相对 cwd 会漂移。
        """
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
