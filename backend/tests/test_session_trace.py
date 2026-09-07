# 会话过程追溯（session-trace-ui）后端单测。
# 覆盖 proposal/spec 验收：
#   - 1.2：message 服务含 trace 落库、round-trip 一致、无 trace 响应省略字段、旧契约字段不变；
#   - 2.1：ChatSession._map_event 按事件完成序累积 thinking(归并)/tool_call/tool_result 步骤，SSE 推送不变；
#   - 2.2：二次确认决策落 trace——allow：tool_call→confirm(allow)→tool_result(ok)；deny：tool_call→confirm(deny)→
#     tool_result(ok=false, denied by user)、绝无写副作用（AgentScope 对拒绝工具仍回 ok=false 结果帧，trace 与 SSE 一致）；
#   - 2.3：成功运行随助手消息落 trace；纯文本回合 trace=None（响应省略）；失败运行无助手消息。
# 复用 test_runtime_services 的驱动打桩（_DriverFakeModel/_tcb/_collect_session 等），不真连模型/网络。
import pytest

from backend.app import create_app
from backend.tests.test_runtime_services import (  # noqa: E402
    _DriverFakeModel,
    _collect_session,
    _make_session_ready,
    _make_task,
    _plain_text,
    _tcb,
)

# 与 test_runtime_services 一致的临时库配置
@pytest.fixture()
def app(tmp_path):
    class Cfg:
        DATA_DIR = tmp_path
        SQLITE_PATH = tmp_path / "app.db"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'app.db').as_posix()}"
        CORS_ORIGINS = ["http://localhost:5173"]
        MASTER_KEY = ""

        @classmethod
        def ensure_dirs(cls) -> None:
            cls.DATA_DIR.mkdir(parents=True, exist_ok=True)

    application = create_app(Cfg)
    application.config.update(TESTING=True)
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _app_ctx(app):
    with app.app_context():
        yield


# ============================================================
# 1.2：message 服务 trace 落库/读取
# ============================================================

def test_message_trace_roundtrip_and_absent_when_none(client):
    from backend.services import message as msg_svc

    steps = [
        {"kind": "tool_call", "name": "Bash", "args": {"command": "echo hi"}},
        {"kind": "tool_result", "name": "Bash", "ok": True, "summary": "hi"},
    ]
    # 带 trace 的助手消息：round-trip 结构与入参一致（list 升序，取 assistant 行）
    tid = _make_task(client)
    msg_svc.add_user_message(tid, "执行", run_id="r1")
    msg_svc.add_assistant_message(tid, "完成", run_id="r1", model="deepseek-chat",
                                  trace=steps)
    rows = msg_svc.list_messages(tid)
    asst = [m for m in rows if m["role"] == "assistant"][0]
    assert asst["trace"] == steps  # JSON 列回读为同构 python 对象
    assert asst["run_id"] == "r1" and asst["content"] == "完成"

    # 纯文本助手消息（无 trace）：响应省略 trace 字段，旧契约字段不变
    tid2 = _make_task(client)
    msg_svc.add_assistant_message(tid2, "纯文本答复", run_id="r2", model="m")
    row = msg_svc.list_messages(tid2)[0]
    assert row["content"] == "纯文本答复" and "trace" not in row
    assert set(row) == {"id", "task_id", "role", "content", "run_id", "model",
                        "created_at", "updated_at"}


# ============================================================
# 2.1：_map_event 步骤累积（fake 事件对象 + 打桩 _event_objs）
# ============================================================

class _Th:
    pass


class _Ts:
    pass


class _Td:
    pass


class _Te:
    pass


class _Rs:
    pass


class _Rd:
    pass


class _Re:
    pass


class _Tx:
    pass


class _Mc:
    pass


def _fake_event(cls, **attrs):
    inst = cls()
    inst.__dict__.update(attrs)
    return inst


def test_map_event_steps_order_thinking_tool(client, monkeypatch):
    from backend.services import agent_session as asvc

    monkeypatch.setattr(asvc, "_event_objs", {
        "ThinkingBlockDeltaEvent": _Th,
        "ToolCallStartEvent": _Ts,
        "ToolCallDeltaEvent": _Td,
        "ToolCallEndEvent": _Te,
        "ToolResultStartEvent": _Rs,
        "ToolResultTextDeltaEvent": _Rd,
        "ToolResultEndEvent": _Re,
        "TextBlockDeltaEvent": _Tx,
        "ModelCallEndEvent": _Mc,
    })
    sess = asvc.ChatSession(None, _make_task(client), "探针")

    # 连续思考分两段 delta → 归并为一块 thinking 步骤
    sess._map_event(_fake_event(_Th, delta="深"))
    sess._map_event(_fake_event(_Th, delta="思中…"))
    # 工具调用：Start(id)→Delta(参数字符串)→End
    sess._map_event(_fake_event(_Ts, tool_call_id="tc1", tool_call_name="Bash"))
    sess._map_event(_fake_event(_Td, tool_call_id="tc1", delta='{"command": "echo hi"}'))
    sess._map_event(_fake_event(_Te, tool_call_id="tc1"))
    # 工具结果：Start→TextDelta→End(success)
    sess._map_event(_fake_event(_Rs, tool_call_id="tc1", tool_call_name="Bash"))
    sess._map_event(_fake_event(_Rd, tool_call_id="tc1", delta="hi"))
    sess._map_event(_fake_event(_Re, tool_call_id="tc1", state="success"))

    assert sess._steps == [
        {"kind": "thinking", "text": "深思中…"},
        {"kind": "tool_call", "name": "Bash", "args": {"command": "echo hi"}},
        {"kind": "tool_result", "name": "Bash", "ok": True, "summary": "hi"},
    ]
    # SSE 推送保持原样（未吞掉任何帧）：thinking_delta×2 + tool_call + tool_result
    assert sess.msg_queue.qsize() == 4


def test_map_event_plain_text_no_steps(client, monkeypatch):
    from backend.services import agent_session as asvc

    monkeypatch.setattr(asvc, "_event_objs", {
        "TextBlockDeltaEvent": _Tx, "ThinkingBlockDeltaEvent": None,
        "ToolCallStartEvent": _Ts, "ToolCallDeltaEvent": _Td, "ToolCallEndEvent": _Te,
        "ToolResultStartEvent": _Rs, "ToolResultTextDeltaEvent": _Rd, "ToolResultEndEvent": _Re,
        "ModelCallEndEvent": _Mc,
    })
    sess = asvc.ChatSession(None, _make_task(client), "探针")
    sess._map_event(_fake_event(_Tx, delta="仅文本"))
    assert sess._steps == []
    assert sess.msg_queue.qsize() == 1  # text_delta 正常推送


def test_record_confirm_writes_decision_and_closes_thinking(client):
    from backend.services import agent_session as asvc

    sess = asvc.ChatSession(None, _make_task(client), "探针")
    sess._thinking = ["先想想"]
    sess._record_confirm("Write", True)
    sess._record_confirm("Bash", False)  # 拒绝：无对应 tool 步骤
    assert sess._steps == [
        {"kind": "thinking", "text": "先想想"},
        {"kind": "confirm", "name": "Write", "decision": "allow"},
        {"kind": "confirm", "name": "Bash", "decision": "deny"},
    ]


# ============================================================
# 2.2 / 2.3：驱动级会话——confirm 决策 + trace 随消息落库
# ============================================================

def test_session_allow_persists_trace_with_confirm_tool_result(app, client, tmp_path):
    from backend.services import message as msg_svc

    tid = _make_session_ready(app, client)
    target = tmp_path / "trace_out.txt"

    def script():
        def first(messages, tools):
            return _plain_text("准备写入。") + [
                _tcb("Write", {"file_path": str(target), "content": "trace"})
            ]

        def second(messages, tools):
            return _plain_text("写入完成。")

        return [first, second]

    events, _sess = _collect_session(app, tid, "写文件", script(), decide=lambda d: True)
    assert events[-1]["type"] == "done"
    assert target.exists()

    assistant = [m for m in msg_svc.list_messages(tid) if m["role"] == "assistant"][-1]
    trace = assistant["trace"]
    assert trace is not None
    kinds = [s["kind"] for s in trace]
    ti, ci, ri = kinds.index("tool_call"), kinds.index("confirm"), kinds.index("tool_result")
    assert ti < ci < ri  # 工具请求(流上)→用户决策→执行结果，与 SSE 事件先后一致
    assert trace[ci]["name"] == "Write" and trace[ci]["decision"] == "allow"
    assert trace[ti]["name"] == "Write" and "args" in trace[ti]
    assert trace[ri]["ok"] is True


def test_session_deny_persists_trace_with_failed_tool_result(app, client, tmp_path):
    from backend.services import message as msg_svc

    tid = _make_session_ready(app, client)
    target = tmp_path / "never_write.txt"

    def script():
        def first(messages, tools):
            return _plain_text("我会尝试写入。") + [
                _tcb("Write", {"file_path": str(target), "content": "must not"})
            ]

        def second(messages, tools):
            return _plain_text("好的，不写入。")

        return [first, second]

    events, _sess = _collect_session(app, tid, "写文件", script(), decide=lambda d: False)
    assert events[-1]["type"] == "done"
    assert not target.exists()  # 拒绝路径绝无写副作用（用户拒绝被真正执行）

    assistant = [m for m in msg_svc.list_messages(tid) if m["role"] == "assistant"][-1]
    trace = assistant["trace"]
    assert trace is not None
    # AgentScope 对拒绝的工具仍回一个 ok=false 的结果帧，trace 与 SSE 一致：
    #   工具请求 → confirm(deny) → tool_result(ok=false, denied by user)
    assert [s["kind"] for s in trace] == ["tool_call", "confirm", "tool_result"]
    confirm = next(s for s in trace if s["kind"] == "confirm")
    result = next(s for s in trace if s["kind"] == "tool_result")
    assert confirm["name"] == "Write" and confirm["decision"] == "deny"
    assert result["ok"] is False


def test_session_plain_text_trace_omitted(app, client):
    from backend.services import message as msg_svc

    tid = _make_session_ready(app, client)
    _collect_session(
        app, tid, "你好",
        [lambda m, t: _plain_text("收到。"), lambda m, t: _plain_text("暂无异常。")],
    )
    assistant = [m for m in msg_svc.list_messages(tid) if m["role"] == "assistant"][-1]
    assert "trace" not in assistant  # 纯文本回合：落 None → 响应省略该字段


def test_session_reply_error_user_only_no_assistant_trace(app, client):
    """模型运行中途抛错：SSE error→done，只留用户消息，绝不落助手消息/trace（2.3 第三分支）。"""
    import json as _json

    from backend.services import agent_session as asvc
    from backend.services import message as msg_svc

    tid = _make_session_ready(app, client)

    class _Boom:
        async def reply_stream(self, inputs):
            raise RuntimeError("server down")
            yield  # pragma: no cover —— 让函数成为 async generator，异常在首迭代抛出

    sess = asvc.ChatSession(app, tid, "触发模型错误")
    sess.agent = _Boom()
    msg_svc.add_user_message(tid, "触发模型错误", run_id=sess.run_id)
    sess.start()
    events = [_json.loads(f[6:-2]) for f in sess.events()]  # events() 遇 error/done 任一终端帧即收
    sess.dispose()
    assert events and events[-1]["type"] == "error"  # 错误即终端，不留伪 done

    rows = msg_svc.list_messages(tid)
    assert [r["role"] for r in rows] == ["user"]  # 错误运行不落助手消息，故无 trace
