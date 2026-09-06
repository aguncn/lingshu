# 健康检查接口：给前端/监控确认后端进程与基本运行时可用。
# 仅做无副作用的探测，不碰数据库、不写日志，保证任何时刻都能稳定响应。
from datetime import datetime, timezone

from flask import Blueprint

health_bp = Blueprint("health", __name__, url_prefix="/api")


@health_bp.get("/health")
def health():
    return {"ok": True, "ts": datetime.now(timezone.utc).isoformat()}
