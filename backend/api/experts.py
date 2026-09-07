# 专家中心 API（P5 registry-center AD-04，url_prefix=/api）。
# 形态与 model_prompt 域一致：POST→201、DELETE→{"ok":true}、AppError 收敛。
from flask import Blueprint, request

from ..services import expert_profile, registry_expert
from ..services.errors import AppError

experts_bp = Blueprint("experts", __name__, url_prefix="/api")


@experts_bp.errorhandler(AppError)
def _handle_app_error(error: AppError):
    return {"message": error.message}, error.status


def _body() -> dict:
    return request.get_json(silent=True) or {}


@experts_bp.get("/experts")
def list_experts():
    return registry_expert.list_experts()


@experts_bp.post("/experts")
def create_expert():
    body = _body()
    return registry_expert.create_expert(
        name=body.get("name"),
        description=body.get("description"),
        system_prompt=body.get("system_prompt"),
        role=body.get("role"),
        preset_skills=body.get("preset_skills"),
        preset_mcp=body.get("preset_mcp"),
        preset_kb=body.get("preset_kb"),
        preset_library=body.get("preset_library"),
        default_provider_id=body.get("default_provider_id"),
        default_model_name=body.get("default_model_name"),
        composed_of=body.get("composed_of"),
        enabled=body.get("enabled"),
    ), 201


@experts_bp.get("/experts/<int:eid>")
def get_expert(eid: int):
    return registry_expert.get_expert(eid)


@experts_bp.patch("/experts/<int:eid>")
def update_expert(eid: int):
    body = _body()
    keys = (
        "name", "description", "system_prompt", "role",
        "preset_skills", "preset_mcp", "preset_kb", "preset_library",
        "default_provider_id", "default_model_name",
        "composed_of", "enabled",
    )
    fields = {k: body.get(k) for k in keys if k in body}
    return registry_expert.update_expert(eid, **fields)


@experts_bp.delete("/experts/<int:eid>")
def delete_expert(eid: int):
    registry_expert.delete_expert(eid)
    return {"ok": True}


@experts_bp.post("/tasks/<int:task_id>/expert/apply")
def apply_expert(task_id: int):
    """把一份运维专家档案快照装配到任务（人设/预设/资料/默认模型 → 任务自身挂载/绑定）。"""
    body = _body()
    return expert_profile.apply_expert_profile(task_id, body.get("expert_id"))
