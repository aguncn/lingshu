"""读取 .env / 环境变量里的 OpenObserve 连接配置。

优先级：进程环境变量 > observe-lab/.env > 内置默认值。
脚本统一从这里拿配置，避免各模块各读一遍。
"""
from __future__ import annotations

import os
from pathlib import Path

# observe-lab 根目录（本文件在 observe-lab/o2/ 下）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


def _load_env_file(path: Path) -> dict:
    cfg: dict[str, str] = {}
    if not path.exists():
        return cfg
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


_DEFAULTS = {
    "OO_BASE_URL": "http://localhost:5080",
    "OO_ORG": "default",
    "OO_EMAIL": "",
    "OO_PASSWORD": "",
    "OO_HTTP_TIMEOUT": "30",
    "OO_BATCH_LOGS": "400",
    "OO_VERBOSE": "0",
    # 追踪流名：本版本 OTLP 一律落在 type=traces 的 default 流（与 legacy 同流，
    # 靠 service_name 前缀 ec- 区分）；若未来版本支持 stream-name 头可改成 ec_traces。
    "OO_TRACE_STREAM": "default",
}


def settings() -> dict:
    """合并默认值 + .env + 环境变量，返回 dict。"""
    merged = dict(_DEFAULTS)
    merged.update(_load_env_file(ENV_PATH))
    for k in list(_DEFAULTS):
        if os.environ.get(k):
            merged[k] = os.environ[k]
    return merged


def int_setting(s: dict, key: str) -> int:
    try:
        return int(s.get(key) or _DEFAULTS[key])
    except (TypeError, ValueError):
        return int(_DEFAULTS[key])


def check_credentials(s: dict) -> list[str]:
    """返回缺失/明显错误的配置项中文清单；空列表 = 可用。"""
    missing: list[str] = []
    if not s.get("OO_EMAIL"):
        missing.append("OO_EMAIL（OpenObserve 登录邮箱）")
    if not s.get("OO_PASSWORD"):
        missing.append("OO_PASSWORD（登录密码）")
    if not s.get("OO_ORG"):
        missing.append("OO_ORG（组织名）")
    base = (s.get("OO_BASE_URL") or "").strip()
    if not base.startswith("http://") and not base.startswith("https://"):
        missing.append(f"OO_BASE_URL 格式不对（当前: {base!r}，应含 http://）")
    return missing
