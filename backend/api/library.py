# 资料库 API（P6 library LB-01，url_prefix=/api）。
# CRUD 形态与 model_prompt/kb 域一致：上传取 multipart 的 file + 可选 space_id 表单字段，
#   scope 过滤走 query，download 用 send_file 以原名下载，PATCH 只应用出现字段。
# 跨任务引用路由挂在 /api/tasks/<tid>/library-files（task 子资源，design D9）；
#   任务文件清单的合并改造见 space_task.py（space-task-mgmt MODIFIED）。
from flask import Blueprint, request, send_file

from ..services import library_service
from ..services.errors import AppError, ValidationError

library_bp = Blueprint("library", __name__, url_prefix="/api")


@library_bp.errorhandler(AppError)
def _handle_app_error(error: AppError):
    return {"message": error.message}, error.status


# ---------- 资料库资源 ----------
@library_bp.post("/library")
def upload_library():
    file_storage = request.files.get("file")
    if file_storage is None or not file_storage.filename:
        raise ValidationError("缺少 file 字段（multipart 表单字段名须为 file）")
    space_id = request.form.get("space_id")  # 缺省/空 → 全局；数字 → 指定空间（service 校验存在）
    data = file_storage.read()
    return (
        library_service.create_library(
            space_id=space_id,
            filename=file_storage.filename,
            data=data,
        ),
        201,
    )


@library_bp.get("/library")
def list_library():
    return library_service.list_library(
        scope=request.args.get("scope"),
        space_id=request.args.get("space_id"),
    )


@library_bp.get("/library/<int:lid>/download")
def download_library(lid: int):
    path, filename, mime = library_service.download_file(lid)
    # as_attachment 让浏览器落盘原名；mimetype/mime 来自上传时的类型推断
    return send_file(
        path,
        as_attachment=True,
        download_name=filename,
        mimetype=mime,
        max_age=0,
        conditional=True,
    )


@library_bp.patch("/library/<int:lid>")
def update_library(lid: int):
    body = request.get_json(silent=True) or {}
    fields = {k: body.get(k) for k in ("shared", "filename") if k in body}
    return library_service.update_library(lid, **fields)


@library_bp.delete("/library/<int:lid>")
def delete_library(lid: int):
    library_service.delete_library(lid)
    return {"ok": True}


# ---------- 跨任务引用（task 子资源，design D9） ----------
@library_bp.post("/tasks/<int:tid>/library-files")
def attach_library(tid: int):
    body = request.get_json(silent=True) or {}
    return library_service.attach_library(tid, body.get("library_file_id")), 201


@library_bp.delete("/tasks/<int:tid>/library-files/<int:fid>")
def detach_library(tid: int, fid: int):
    library_service.detach_library(tid, fid)
    return {"ok": True}
