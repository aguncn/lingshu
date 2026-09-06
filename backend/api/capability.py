# 能力装配 API（P4 capability-mount，url_prefix=/api，design D6）。
# 与既有 blueprints 并存：/tasks/<id>/caps 是 /tasks 下独立子路径，与 /files、/model-config 不冲突。
# 错误收敛与 P2/P3 一致：service 抛 AppError → 本域 errorhandler 统一转 {"message":..} + 状态码。
from flask import Blueprint, request

from ..services import capability
from ..services.errors import AppError

capability_bp = Blueprint("capability", __name__, url_prefix="/api")


@capability_bp.errorhandler(AppError)
def _handle_app_error(error: AppError):
    return {"message": error.message}, error.status


def _body() -> dict:
    return request.get_json(silent=True) or {}


# ---------- 任务能力挂载（CAP-01~04） ----------
@capability_bp.put("/tasks/<int:task_id>/caps")
def replace_task_caps(task_id: int):
    """全量覆盖式更新任务的能力挂载（PUT 全状态语义）。

    请求体: {"skills": [int], "mcps": [int], "kbs": [int], "experts": [int]}
      - 四键任一缺省视为清空该分类；元素须为对应实体表中已存在的正整数 id。
      - 校验失败 → 400 且不改变既有挂载：未知分类键 / 元素非正整数(bool/str/float/负数)
        / 同数组重复 / 目标实体不存在（均整体拒绝，无部分写入）。
      - 任务不存在 → 404。
    成功响应 200: {"task_id": int, "skills": [...], "mcps": [...], "kbs": [...], "experts": [...]}
      （各类 id 升序）。
    """
    return capability.set_task_caps(task_id, _body())


@capability_bp.get("/tasks/<int:task_id>/caps")
def read_task_caps(task_id: int):
    """读取任务当前的能力挂载清单。

    成功响应 200: {"task_id": int, "skills": [...], "mcps": [...], "kbs": [...], "experts": [...]}
      （各类 id 升序；新建未挂载任务四类均为空数组）。
    任务不存在 → 404。
    """
    return capability.get_task_caps(task_id)
