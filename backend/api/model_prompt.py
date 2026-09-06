# 模型/提示词 API 域 blueprint（url_prefix=/api，design D6）。
# 与既有 space_task_bp 并存：/tasks/<id>/model-config 等与 /files 是不同 rule，无路由冲突。
# 错误收敛与 P2 一致：service 抛 AppError → 本域 errorhandler 统一转 {"message":..}。
from flask import Blueprint, request

from ..services import model_service
from ..services.errors import AppError

model_prompt_bp = Blueprint("model_prompt", __name__, url_prefix="/api")


@model_prompt_bp.errorhandler(AppError)
def _handle_app_error(error: AppError):
    return {"message": error.message}, error.status


def _body() -> dict:
    return request.get_json(silent=True) or {}


# ---------- 模型供应商（MD-04，供设置中心） ----------
@model_prompt_bp.get("/model-providers")
def list_providers():
    return model_service.list_providers()


@model_prompt_bp.post("/model-providers")
def create_provider():
    body = _body()
    provider = model_service.create_provider(
        name=body.get("name"),
        type=body.get("type"),
        base_url=body.get("base_url"),
        default_model=body.get("default_model"),
        api_key=body.get("api_key"),
    )
    return provider, 201


@model_prompt_bp.get("/model-providers/<int:pid>")
def get_provider(pid: int):
    return model_service.get_provider(pid)


@model_prompt_bp.patch("/model-providers/<int:pid>")
def update_provider(pid: int):
    body = _body()
    keys = ("name", "type", "base_url", "default_model", "api_key")
    fields = {k: body.get(k) for k in keys if k in body}
    return model_service.update_provider(pid, **fields)


@model_prompt_bp.delete("/model-providers/<int:pid>")
def delete_provider(pid: int):
    model_service.delete_provider(pid)
    return {"ok": True}


# ---------- 任务绑模型（MD-01） ----------
@model_prompt_bp.get("/tasks/<int:task_id>/model-config")
def get_task_config(task_id: int):
    return model_service.get_task_config(task_id)


@model_prompt_bp.post("/tasks/<int:task_id>/model-config")
def set_task_config(task_id: int):
    body = _body()
    config, created = model_service.set_task_config(
        task_id,
        provider_id=body.get("provider_id"),
        model_name=body.get("model_name"),
        temperature=body.get("temperature"),
        max_tokens=body.get("max_tokens"),
        timeout=body.get("timeout"),
    )
    return config, (201 if created else 200)


@model_prompt_bp.patch("/tasks/<int:task_id>/model-config")
def update_task_config(task_id: int):
    body = _body()
    keys = ("provider_id", "model_name", "temperature", "max_tokens", "timeout")
    fields = {k: body.get(k) for k in keys if k in body}
    return model_service.update_task_config(task_id, **fields)


# ---------- 提示词库（MD-03） ----------
@model_prompt_bp.get("/prompts")
def list_prompts():
    return model_service.list_prompts(
        category=request.args.get("category"),
        domain=request.args.get("domain"),
        name=request.args.get("name"),
    )


@model_prompt_bp.post("/prompts")
def create_prompt():
    body = _body()
    prompt = model_service.create_prompt(
        name=body.get("name"),
        category=body.get("category"),
        domain=body.get("domain"),
        content=body.get("content"),
    )
    return prompt, 201


@model_prompt_bp.get("/prompts/<int:pid>")
def get_prompt(pid: int):
    return model_service.get_prompt(pid)


@model_prompt_bp.patch("/prompts/<int:pid>")
def update_prompt(pid: int):
    body = _body()
    keys = ("content", "category", "domain")
    fields = {k: body.get(k) for k in keys if k in body}
    return model_service.update_prompt(pid, **fields)


@model_prompt_bp.delete("/prompts/<int:pid>")
def delete_prompt(pid: int):
    model_service.delete_prompt(pid)
    return {"ok": True}
