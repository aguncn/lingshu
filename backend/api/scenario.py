# 场景域 API（P9 scenario-templates，url_prefix=/api，design D7）。
# 错误收敛与 skills 域一致：service 抛 AppError → 本域 errorhandler 统一转 {"message":..}。
# GET 列表/单查供前端「选域分类」展示；POST apply 是「选域套模板」的唯一落点
#（建任务成功后调一次即完成装配，细节栏仍可用 PUT caps 微调，见 design D4）。
from flask import Blueprint, request

from ..services import scenario_service
from ..services.errors import AppError

scenario_bp = Blueprint("scenario", __name__, url_prefix="/api")


@scenario_bp.errorhandler(AppError)
def _handle_app_error(error: AppError):
    return {"message": error.message}, error.status


def _body() -> dict:
    return request.get_json(silent=True) or {}


@scenario_bp.get("/scenarios")
def list_scenarios():
    return scenario_service.list_scenarios()


@scenario_bp.get("/scenarios/<domain>")
def get_scenario(domain: str):
    return scenario_service.get_scenario(domain)


@scenario_bp.post("/tasks/<int:task_id>/scenario/apply")
def apply_scenario(task_id: int):
    # body 必填受控 domain；非法域/任务不存在由 service 分别抛 400/404（均零副作用）
    return scenario_service.apply_scenario(
        task_id, domain=_body().get("domain")
    )
