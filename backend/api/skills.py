# 技能中心 API（P5 registry-center AD-01，url_prefix=/api）。
# 错误收敛与 model_prompt 域一致：service 抛 AppError → 本域 errorhandler 统一转 {"message":..}。
# GET /api/skills/<id> 出口含 skill_md 全文：供前端「预览」渲染数据（渲染本身归前端提案）。
from flask import Blueprint, request

from ..services import registry_skill
from ..services.errors import AppError

skills_bp = Blueprint("skills", __name__, url_prefix="/api")


@skills_bp.errorhandler(AppError)
def _handle_app_error(error: AppError):
    return {"message": error.message}, error.status


def _body() -> dict:
    return request.get_json(silent=True) or {}


@skills_bp.get("/skills")
def list_skills():
    return registry_skill.list_skills()


@skills_bp.post("/skills")
def create_skill():
    body = _body()
    return registry_skill.create_skill(
        name=body.get("name"),
        description=body.get("description"),
        skill_md=body.get("skill_md"),
        enabled=body.get("enabled"),
    ), 201


@skills_bp.get("/skills/<int:sid>")
def get_skill(sid: int):
    return registry_skill.get_skill(sid)


@skills_bp.patch("/skills/<int:sid>")
def update_skill(sid: int):
    body = _body()
    keys = ("name", "description", "skill_md", "enabled")
    fields = {k: body.get(k) for k in keys if k in body}
    return registry_skill.update_skill(sid, **fields)


@skills_bp.delete("/skills/<int:sid>")
def delete_skill(sid: int):
    registry_skill.delete_skill(sid)
    return {"ok": True}
