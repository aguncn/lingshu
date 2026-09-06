# 知识库中心 API（P5 registry-center AD-03，url_prefix=/api）。
# CRUD 形态与 model_prompt 域一致；upload 取 multipart 的 file 字段（缺 file → 400 AppError），
#   search 走 JSON body。上传/检索对不存在库→404、停用库→400 由 service 抛 AppError 统一收敛。
from flask import Blueprint, request

from ..services import registry_kb
from ..services.errors import AppError, ValidationError

kb_bp = Blueprint("kb", __name__, url_prefix="/api")


@kb_bp.errorhandler(AppError)
def _handle_app_error(error: AppError):
    return {"message": error.message}, error.status


def _body() -> dict:
    return request.get_json(silent=True) or {}


@kb_bp.get("/kb")
def list_kbs():
    return registry_kb.list_kbs()


@kb_bp.post("/kb")
def create_kb():
    body = _body()
    return registry_kb.create_kb(
        name=body.get("name"),
        space_id=body.get("space_id"),
        embedding_provider=body.get("embedding_provider"),
        chunk_size=body.get("chunk_size"),
        status=body.get("status"),
    ), 201


@kb_bp.get("/kb/<int:kid>")
def get_kb(kid: int):
    return registry_kb.get_kb(kid)


@kb_bp.patch("/kb/<int:kid>")
def update_kb(kid: int):
    body = _body()
    keys = ("name", "space_id", "embedding_provider", "chunk_size", "status")
    fields = {k: body.get(k) for k in keys if k in body}
    return registry_kb.update_kb(kid, **fields)


@kb_bp.delete("/kb/<int:kid>")
def delete_kb(kid: int):
    registry_kb.delete_kb(kid)
    return {"ok": True}


# ---------- 文档上传 / 关键词检索（AD-03） ----------
@kb_bp.post("/kb/<int:kid>/upload")
def upload_document(kid: int):
    file_storage = request.files.get("file")
    if file_storage is None or not file_storage.filename:
        raise ValidationError("缺少 file 字段（multipart 表单字段名须为 file）")
    data = file_storage.read()
    return registry_kb.upload_document(kid, file_storage.filename, data)


@kb_bp.post("/kb/<int:kid>/search")
def search_kb(kid: int):
    body = _body()
    return registry_kb.search_kb(
        kid,
        query=body.get("query"),
        top_k=body.get("top_k"),
    )
