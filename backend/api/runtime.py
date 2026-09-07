# 智能体运行时 API（P8 agentscope-runtime，url_prefix=/api，design D4/D5/D7；保活见 session-keepalive）。
# 端点对应 spec「会话发起与任务模型解析 / 流式对话事件契约与会话生命周期 /
# 危险工具二次确认 / 对话历史持久化与读取」：
#   POST /tasks/<id>/chat        —— SSE 流式对话（每任务单活动会话）
#   POST /tasks/<id>/chat/decision —— 二次确认回执（跨请求唤醒 worker）
#   GET  /tasks/<id>/chat/status —— 运行状态查询（保活采纳：active/run_id/park 及待回执确认摘要）
#   POST /tasks/<id>/chat/stop   —— 显式停止当前 run（真正取消：cancel+join+释放槽位）
#   GET  /tasks/<id>/messages    —— 升序读该任务全部消息
# 错误收敛与其它域一致：service 抛 AppError → errorhandler 转 {"message"}+状态码。
# SSE 语义要点（保活版）：
#   - 任务不存在 / 请求非法 → 404/400 JSON（不建会话、不写任何记录）；
#   - 模型不可用（build 在 create 阶段即失败）→ 以 text/event-stream 先发一条 error
#     后结束，零副作用（spec R1 场景，先于会话注册与落用户消息）；
#   - 会话成功建立才注册（并发 chat → 409，原会话不受影响）并落用户消息（R5 契约）；
#   - 连接断开（GeneratorExit/异常）=「脱离」≠ 取消：worker 继续后台把 run 跑完并自注销（见
#     agent_session._worker），返回可经 /chat/status 采纳/重显确认；真正停止走 /chat/stop；
#   - 仅当读到终端帧（done/error）自然结束，generate finally 才幂等 unregister——保证结束后
#     立即可再发起 chat，且不误释放仍在后台跑的 run；MCP 关闭由 worker finally 收敛（driver 责任）。
import json
import uuid

from flask import Blueprint, Response, current_app, request

from ..services import agent_session, message as message_svc
from ..services.errors import AppError, NotFoundError, ValidationError
from ..services.task_service import get_task_or_raise

runtime_bp = Blueprint("runtime", __name__, url_prefix="/api")


@runtime_bp.errorhandler(AppError)
def _handle_app_error(error: AppError):
    return {"message": error.message}, error.status


def _body() -> dict:
    return request.get_json(silent=True) or {}


def _sse_response(gen) -> Response:
    """SSE 响应外壳：text/event-stream，禁缓冲（X-Accel-Buffering 防网关吞流）。"""
    return Response(
        gen,
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@runtime_bp.post("/tasks/<int:task_id>/chat")
def chat(task_id: int):
    """发起一次智能体对话（SSE 流）。请求体 JSON: {"message": str}。
    模型在 create 阶段解析失败 → 先发 error 事件即结束，不写任何消息/审计。"""
    body = _body()
    message = body.get("message")
    if not isinstance(message, str) or not message.strip():
        # 任务不存在/请求非法属纯校验：404/400 JSON，不建立会话、不写记录（spec 场景）
        raise ValidationError("message 必填且不能为空")
    get_task_or_raise(task_id)  # 先于模型解析暴露 404 JSON（与 SSE error 区分）

    # create 阶段即组 Agent + 解析模型：AppError（无绑定/无密钥/装配失败）→ SSE error
    try:
        sess = agent_session.ChatSession.create(
            current_app._get_current_object(), task_id, message
        )
    except AppError as e:
        return _error_sse(f"发起对话失败：{e.message}")

    # 单任务单活动会话：已有运行中 → 409，原会话不受影响
    if not agent_session.register(task_id, sess):
        sess.dispose()  # 未启动 worker，dispose 仅为清理已装配对象
        return {"message": "该任务已有对话正在运行，请等待结束或断开后再试"}, 409

    # 会话注册成功才算一次「收到请求」：此刻落用户消息（spec R5），带 run_id 供关联
    message_svc.add_user_message(task_id, message, run_id=sess.run_id)
    sess.start()

    def generate():
        try:
            for frame in sess.events():
                yield frame
        finally:
            # 断开≠取消（保活核心）：此处绝不 cancel/dispose。连接被 close/异常 = 只「脱离」本次
            # SSE，run 继续在 worker 后台跑完，由 worker finally 自注销；用户可经 /chat/status 采纳、
            # 重显待回执确认，或显式 /chat/stop 真停止。
            # 仅当本流「读到终端帧(done/error)自然结束」才幂等释放注册表槽位：保证结束后立即可再发起
            # chat，且不依赖 worker 线程调度时序（worker 若已先自注销，此处 pop 为空操作，无副作用）。
            if sess.done_consumed:
                agent_session.unregister(task_id)

    return _sse_response(generate())


def _error_sse(reason: str) -> Response:
    """模型不可用等「流内前置失败」：以 SSE 发一条 error 事件后即结束（spec R1）。"""
    payload = {
        "type": "error",
        "run_id": uuid.uuid4().hex,  # 每次事件契约要求带 run_id；失败态无真实运行亦给唯一 id
        "message": reason,
    }
    body = "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
    return _sse_response([body])


@runtime_bp.post("/tasks/<int:task_id>/chat/decision")
def chat_decision(task_id: int):
    """危险工具二次确认回执（跨请求唤醒 worker，无需重开 chat）。
    请求体 JSON: {"run_id": str, "confirm_id": str, "allow": bool}。
    run 不存在/已结束、confirm_id 不存在或已消费（single-use）→ 404 JSON。"""
    body = _body()
    run_id = body.get("run_id")
    confirm_id = body.get("confirm_id")
    allow = body.get("allow")
    if not isinstance(run_id, str) or not run_id:
        raise ValidationError("run_id 必填")
    if not isinstance(confirm_id, str) or not confirm_id:
        raise ValidationError("confirm_id 必填")
    if not isinstance(allow, bool):
        raise ValidationError("allow 必须为布尔值")

    sess = agent_session.active_session(task_id)
    if sess is None or sess.run_id != run_id:
        raise NotFoundError("该 run 不存在或已结束（无对应活动会话）")
    if confirm_id not in sess.pending:
        raise NotFoundError("该 confirm_id 不存在或已被回执")  # 失效/已消费 → 404
    if not sess.submit_decision(confirm_id, allow):
        raise NotFoundError("该 confirm_id 已被回执")  # 竞态兜底
    return {"ok": True}


@runtime_bp.get("/tasks/<int:task_id>/chat/status")
def chat_status(task_id: int):
    """运行状态查询（保活采纳/前端回屏轮询用）。无活动会话 → {"active": false}；
    运行中 → active/run_id/waiting；停留「待用户回执」时附 confirm 摘要，供前端重显确认卡片。"""
    get_task_or_raise(task_id)  # 任务不存在 → 404 JSON
    sess = agent_session.active_session(task_id)
    if sess is None:
        return {"active": False}
    sess.touch()  # 轮询即「有人在看」：刷新孤儿回收判据，避免被 reaper 误回收
    body = {"active": True, "run_id": sess.run_id, "waiting": bool(sess.pending)}
    confirm = sess.current_confirm()
    if confirm is not None:
        body["confirm"] = confirm
    return body


@runtime_bp.post("/tasks/<int:task_id>/chat/stop")
def chat_stop(task_id: int):
    """显式停止当前 run（前端「停止」→ 真取消，区别于 SSE 脱离）。
    无活动会话亦幂等返回 ok；任务不存在 → 404 JSON。"""
    get_task_or_raise(task_id)
    sess = agent_session.active_session(task_id)
    if sess is None:
        return {"ok": True}
    sess.cancel()
    sess.dispose()  # join worker（最长 8s）；worker finally 自注销
    agent_session.unregister(task_id)  # join 超时兜底：确保槽位立即释放、可再发起
    return {"ok": True}


@runtime_bp.get("/tasks/<int:task_id>/messages")
def list_messages(task_id: int):
    """按时间升序返回该任务全部消息；无历史 → 空数组；任务不存在 → 404。"""
    task = get_task_or_raise(task_id)
    return {"task_id": task.id, "messages": message_svc.list_messages(task.id)}
