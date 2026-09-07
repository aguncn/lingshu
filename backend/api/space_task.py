# 空间/任务/文件 API（TR 域，单 blueprint 承载，见 design D5）。
# 空间、任务、嵌套任务与文件路由都需在 /api 下且互相嵌套，拆两个 blueprint
# 会因前缀冲突而别扭，故集中于此；后续能力域再各建 blueprint。
from flask import Blueprint, request, send_file

from ..services import file_store, library_service, space_service, task_service
from ..services.errors import AppError

space_task_bp = Blueprint("space_task", __name__, url_prefix="/api")


@space_task_bp.errorhandler(AppError)
def _handle_app_error(error: AppError):
    # service 抛出的校验/不存在错误统一转 {"message":..} + 状态码（design D6）
    return {"message": error.message}, error.status


def _body() -> dict:
    """取 JSON 请求体，缺省空 dict（GET/DELETE 免 body）。"""
    return request.get_json(silent=True) or {}


# ---------- 空间 ----------
@space_task_bp.get("/spaces")
def list_spaces():
    return space_service.list_spaces()


@space_task_bp.post("/spaces")
def create_space():
    body = _body()
    space = space_service.create_space(
        name=body.get("name"),
        description=body.get("description"),
        visibility=body.get("visibility"),
    )
    return space, 201


@space_task_bp.patch("/spaces/<int:sid>")
def update_space(sid: int):
    body = _body()
    space = space_service.update_space(
        sid,
        name=body.get("name"),
        description=body.get("description"),
        visibility=body.get("visibility"),
    )
    return space


@space_task_bp.delete("/spaces/<int:sid>")
def delete_space(sid: int):
    space_service.delete_space(sid)
    return {"ok": True}


# ---------- 任务（嵌套在空间下） ----------
@space_task_bp.get("/spaces/<int:sid>/tasks")
def list_tasks(sid: int):
    return task_service.list_tasks(sid)


@space_task_bp.post("/spaces/<int:sid>/tasks")
def create_task(sid: int):
    body = _body()
    task = task_service.create_task(
        sid,
        title=body.get("title"),
        task_type=body.get("task_type"),
        visibility=body.get("visibility"),
        model_config_id=body.get("model_config_id"),
        permission_mode=body.get("permission_mode"),
    )
    return task, 201


# ---------- 任务（单条） ----------
@space_task_bp.get("/tasks/<int:task_id>")
def get_task(task_id: int):
    return task_service.get_task(task_id)


@space_task_bp.patch("/tasks/<int:task_id>")
def update_task(task_id: int):
    body = _body()
    # 仅透传请求里出现的可更新字段，未出现则不改（部分更新）
    keys = (
        "title", "task_type", "status", "visibility",
        "model_config_id", "permission_mode",
    )
    fields = {k: body.get(k) for k in keys if k in body}
    return task_service.update_task(task_id, **fields)


@space_task_bp.delete("/tasks/<int:task_id>")
def delete_task(task_id: int):
    task_service.delete_task(task_id)
    return {"ok": True}


# ---------- 任务工作空间文件（含资料库引用合并，见 space-task-mgmt MODIFIED / library design D8） ----------
@space_task_bp.get("/tasks/<int:task_id>/files")
def list_task_files(task_id: int):
    task = task_service.get_task_or_raise(task_id)
    return library_service.merge_task_files(task)


# P7 工作台文件预览所需：内联返回任务工作空间内某文件的字节（只读，不落库）。
# 文本/图片可被前端 <pre>/<img> 直接渲染；其余类型前端仅展示元信息。
@space_task_bp.get("/tasks/<int:task_id>/files/<path:filename>")
def get_task_file(task_id: int, filename: str):
    task = task_service.get_task_or_raise(task_id)
    path = file_store.resolve_task_file(task.space_id, task.id, filename)
    # send_file 按扩展名推断 mimetype；max_age=0 让 dev 侧改文件后能看到新内容
    return send_file(path, as_attachment=False, max_age=0, conditional=True)
