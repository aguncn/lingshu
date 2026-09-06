# MCP 连接器中心 API（P5 registry-center AD-02，url_prefix=/api）。
# CRUD 形态与 model_prompt 域一致；/mcp/<id>/test 转调 mcp_test service，
#   测试失败属业务结果（200 + ok:false + reason），本路由不制造 5xx。
from flask import Blueprint, request

from ..services import mcp_test, registry_mcp
from ..services.errors import AppError

mcp_center_bp = Blueprint("mcp_center", __name__, url_prefix="/api")


@mcp_center_bp.errorhandler(AppError)
def _handle_app_error(error: AppError):
    return {"message": error.message}, error.status


def _body() -> dict:
    return request.get_json(silent=True) or {}


@mcp_center_bp.get("/mcp")
def list_mcps():
    return registry_mcp.list_mcps()


@mcp_center_bp.post("/mcp")
def create_mcp():
    body = _body()
    return registry_mcp.create_mcp(
        name=body.get("name"),
        transport=body.get("transport"),
        command=body.get("command"),
        args=body.get("args"),
        env=body.get("env"),
        url=body.get("url"),
        headers=body.get("headers"),
        trust=body.get("trust"),
        enabled=body.get("enabled"),
    ), 201


@mcp_center_bp.get("/mcp/<int:cid>")
def get_mcp(cid: int):
    return registry_mcp.get_mcp(cid)


@mcp_center_bp.patch("/mcp/<int:cid>")
def update_mcp(cid: int):
    body = _body()
    keys = (
        "name", "transport", "command", "args", "env", "url", "headers",
        "trust", "enabled",
    )
    fields = {k: body.get(k) for k in keys if k in body}
    return registry_mcp.update_mcp(cid, **fields)


@mcp_center_bp.delete("/mcp/<int:cid>")
def delete_mcp(cid: int):
    registry_mcp.delete_mcp(cid)
    return {"ok": True}


@mcp_center_bp.post("/mcp/<int:cid>/test")
def test_mcp(cid: int):
    """连通性测试：成功 200 {ok:true, tools:[..], tool_count:n}；
    失败 200 {ok:false, reason}；连接器不存在 404。"""
    return mcp_test.test_connector(cid)
