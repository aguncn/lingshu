# skill-kb-callable：技能/知识库可调用化单测。
# 覆盖 tasks 1.x~5.x 的核心验收：
#   - 1.1/1.2：FunctionTool 只读同步函数注册即被既有 _map_event 当普通工具流转；
#     strict/limited/trusted 三档只读工具都不弹二次确认（引擎只读快速通道先行），
#     非只读工具在 strict 仍要确认（is_read_only=True 是免确认闸门，漏标即回归）。
#   - 2.x：build() 按需挂 skill_<slug> 只读工具（可用→可调用返回 skill_md、停用/空 md→不出现、无技能→不装配），
#     系统提示不再含技能指令全文；desc.skill_tools 反映装配快照。
#   - 3.x：knowledge_search 只读检索工具（跨挂载库归并、带来源；无可用库给明确文本不报错）。
#   - 5.x：会话级验证调用进入 SSE tool_call/tool_result 与助手回合 trace。
# 复用 test_runtime_services 驱动打桩（_DriverFakeModel/_tcb/_collect_session），不真连模型/网络。
import asyncio

import pytest

from backend.app import create_app
from backend.tests.test_registry import _upload  # noqa: E402
from backend.tests.test_runtime_services import (  # noqa: E402
    _DriverFakeModel,
    _bind_config,
    _built_and_model,
    _built_with_mode,
    _collect_session,
    _disable_skill,
    _make_expert,
    _make_provider,
    _make_session_ready,
    _make_skill,
    _make_task,
    _mount,
    _plain_text,
    _schema_names,
    _tcb,
)


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
    """直接调 service（db.session）需应用上下文，非仅 HTTP 驱动。"""
    with app.app_context():
        yield


# ============================================================
# 1.1 FunctionTool 只读同步函数 → 沿既有事件通道流转
# ============================================================

def _readonly_tool(name: str, doc: str):
    """构造探针用只读 FunctionTool（同步、零入参，返回分步文本）。"""
    from agentscope.tool import FunctionTool

    def _fetch() -> str:
        return f"{doc}\n第1步：核对；第2步：处理。"

    return FunctionTool(_fetch, name=name, description=doc, is_read_only=True)


def test_skill_readonly_functiontool_flows_as_regular_tool(app, client):
    """1.1：模型调用只读技能工具 → 免确认直执行 → SSE tool_call/tool_result(ok) + 审计 + trace 步骤。"""
    from backend.models import AuditLog
    from backend.extensions import db
    from sqlalchemy import select

    tid = _built_with_mode(client, "strict")  # 最严档：证明只读免确认在 strict 也成立
    sess = None
    from backend.services import agent_session

    sess = agent_session.ChatSession.create(app, tid, "用技能排查")
    # 手动把技能工具挂进 basic 组（装配层挂载在 2.2 测）；证明它走普通工具执行路径
    asyncio.run(sess.agent.toolkit.add_tool(_readonly_tool("skill_netcheck", "技能「网络排查」")))

    def script():
        def first(messages, tools):
            return _plain_text("我来取用技能。") + [_tcb("skill_netcheck", {})]

        def second(messages, tools):
            return _plain_text("已按技能处理。")

        return [first, second]

    sess.agent.model = _DriverFakeModel(script())
    sess.start()
    events = []
    for frame in sess.events():
        import json as _json
        data = _json.loads(frame[6:-2])
        events.append(data)
        if data.get("type") == "done":
            break
    # 免确认：无 confirm_request；工具被调用并成功返回
    assert not any(e["type"] == "confirm_request" for e in events)
    call = next(e for e in events if e["type"] == "tool_call")
    assert call["name"] == "skill_netcheck"
    res = next(e for e in events if e["type"] == "tool_result")
    assert res["ok"] is True and "第1步" in res["summary"]
    assert events[-1]["type"] == "done"
    # 审计 tool_call(success)；trace 助手回合含 tool_call→tool_result 步骤
    rows = list(db.session.execute(
        select(AuditLog).where(AuditLog.task_id == tid)
    ).scalars())
    assert ("runtime", "tool_call", "success", "skill_netcheck") in {
        (r.actor, r.action, r.result, r.target) for r in rows
    }
    from backend.services import message as msg_svc
    msgs = msg_svc.list_messages(tid)
    assistant = [m for m in msgs if m["role"] == "assistant"][-1]
    kinds = [s["kind"] for s in assistant["trace"]]
    assert "tool_call" in kinds and "tool_result" in kinds


# ============================================================
# 1.2 权限探针：只读工具三档免确认；漏标 is_read_only 即回归
# ============================================================

@pytest.mark.parametrize("mode", ["strict", "limited", "trusted"])
def test_readonly_tools_never_ask_all_modes(client, mode):
    """1.2：技能取用/知识库检索只读工具在三档下均 ALLOW（引擎只读快速通道先于工具自身 ASK）。"""
    from agentscope.permission import PermissionBehavior, PermissionEngine
    from backend.services import agent_runtime

    tid = _built_with_mode(client, mode)
    agent, _ = agent_runtime.build(tid)
    engine = PermissionEngine(agent.state.permission_context)
    tools = {
        "skill_alarm": _readonly_tool("skill_alarm", "技能「告警」"),
        "knowledge_search": _readonly_tool("knowledge_search", "知识库检索"),
    }

    async def run():
        for name, tool in tools.items():
            decision = await engine.check_permission(tool, {})
            assert decision.behavior == PermissionBehavior.ALLOW, (
                f"{mode} 档 {name} 应免确认，实为 {decision.behavior}"
            )

    asyncio.run(run())


def test_non_readonly_functiontool_asks_under_strict(client):
    """1.2 回归护栏：FunctionTool 若漏标 is_read_only，strict(DEFAULT) 下会被问确认——
    证明免确认来自只读标记，而非工具是 FunctionTool 本身。"""
    from agentscope.permission import PermissionBehavior, PermissionEngine
    from agentscope.tool import FunctionTool
    from backend.services import agent_runtime

    def _fetch() -> str:
        return "should require confirm if not read-only"

    leaked = FunctionTool(_fetch, name="skill_leaked", description="漏标只读")

    tid = _built_with_mode(client, "strict")
    agent, _ = agent_runtime.build(tid)
    engine = PermissionEngine(agent.state.permission_context)

    async def run():
        decision = await engine.check_permission(leaked, {})
        assert decision.behavior == PermissionBehavior.ASK

    asyncio.run(run())


# ============================================================
# 1.3 slug 工具名归一化
# ============================================================

def test_skill_slug_normalization_ascii_lower_and_clean():
    """技能名 → ASCII 小写 slug：非 [a-z0-9_-] 字符（含中文/空格/符号）折叠为下划线。"""
    from backend.services import agent_runtime as rt

    assert rt._skill_slug("网络排查") == ""          # 纯中文 → 无法归一化（回退 skill_<id>）
    assert rt._skill_slug("Net 排查!V2") == "net_v2"  # 连续非法字符折叠为单个下划线
    assert rt._skill_slug("Alarm SOP v1") == "alarm_sop_v1"
    assert rt._skill_slug("") == ""
    assert rt._skill_slug("  ") == ""


def test_skill_tool_name_unique_and_fallback():
    """slug 冲突或无法归一化 → 回退 skill_<id>，保证同名技能/内置名不重复。"""
    from backend.services import agent_runtime as rt

    reserved = set(rt._BUILTIN_TOOL_NAMES)
    # 正常：slug 归一化成功且未占用
    assert rt._skill_tool_name(1, "网络排查", set()) == "skill_1"  # 空 slug → id 兜底
    assert rt._skill_tool_name(2, "Alarm SOP", set()) == "skill_alarm_sop"
    # 冲突（已占用 skill_alarm）→ 回退 id；两次取同名技能第二次回退 id → 依旧唯一
    reserved.add("skill_alarm_sop")
    assert rt._skill_tool_name(3, "Alarm SOP", reserved) == "skill_3"
    # 与内置工具名不冲突：skill_read 前缀隔离于内置 Read
    assert rt._skill_tool_name(4, "read", set(rt._BUILTIN_TOOL_NAMES)) == "skill_read"


# ============================================================
# 2.3 build：技能工具装配面（可用/停用/空 md/无技能）+ 会话级取用
# ============================================================

def _tool_by_name(agent, name):
    for g in agent.toolkit.tool_groups:
        for t in g.tools:
            if t.name == name:
                return t
    return None


def _make_kb(client, name="kb", status=None) -> int:
    body = {"name": name}
    if status:
        body["status"] = status
    r = client.post("/api/kb", json=body)
    assert r.status_code == 201, r.get_json()
    return r.get_json()["id"]


def _mount_kb(client, tid: int, kb_ids) -> None:
    body = {"skills": [], "mcps": [], "kbs": list(kb_ids), "experts": []}
    assert client.put(f"/api/tasks/{tid}/caps", json=body).status_code == 200


def test_build_skill_tool_available_empty_disabled(client):
    """2.3：仅「挂载+启用+非空 md」的技能成为工具；空 md / 停用技能不出现；技能指令不进系统提示。"""
    from backend.services import agent_runtime

    good = _make_skill(client, name="网络排查", skill_md="先登录堡垒机再核对告警窗口。")
    empty = _make_skill(client, name="空技能", skill_md="   ")  # 无指令文本
    off = _make_skill(client, name="停用技能", skill_md="不该出现")
    _disable_skill(client, off)
    tid = _built_and_model(client)
    _mount(client, tid, skills=[good, empty, off])

    agent, desc = agent_runtime.build(tid)
    # 纯中文技能名 slug 为空 → 回退 skill_<id>；停用/空 md 不出现
    assert desc["skills"] == ["网络排查"]
    tool_name = f"skill_{good}"
    assert desc["skill_tools"] == [{"name": tool_name, "skill_name": "网络排查"}]
    names = _schema_names(agent.toolkit)
    assert tool_name in names and "skill_空技能" not in names and "skill_停用技能" not in names
    # 技能指令不进系统提示
    assert "登录堡垒机" not in agent._system_prompt

    async def run():
        tool = _tool_by_name(agent, tool_name)
        assert tool is not None and tool.is_read_only is True
        chunk = await tool.call()
        text = chunk.content[0].text if chunk.content else ""
        assert "先登录堡垒机再核对告警窗口" in text  # 调用即取回技能完整指令文本

    asyncio.run(run())


def test_session_skill_tool_via_build_called_and_traced(app, client):
    """2.3 会话级：build 挂载的真实技能工具被模型调用 → 取回 skill_md 全文并进 SSE/trace（免确认）。"""
    import json as _json

    from backend.services import agent_runtime
    from backend.services import message as msg_svc

    skill_md = "第1步：拉取当前告警；第2步：按严重级别排序并给出处理建议。"
    sid = _make_skill(client, name="告警处置", skill_md=skill_md)
    tid = _built_with_mode(client, "strict")
    _mount(client, tid, skills=[sid])

    # build 快照 → 技能工具名（纯中文 → skill_<id>）
    agent, desc = agent_runtime.build(tid)
    tool_name = desc["skill_tools"][0]["name"]

    from backend.services import agent_session
    sess = agent_session.ChatSession.create(app, tid, "按技能处置告警")
    sess.agent.model = _DriverFakeModel([
        lambda m, t: _plain_text("我来调用技能。") + [_tcb(tool_name, {})],
        lambda m, t: _plain_text("已按技能处置。"),
    ])
    sess.start()
    events = []
    for frame in sess.events():
        data = _json.loads(frame[6:-2])
        events.append(data)
        if data.get("type") == "done":
            break
    assert not any(e["type"] == "confirm_request" for e in events)
    res = next(e for e in events if e["type"] == "tool_result")
    assert res["name"] == tool_name and res["ok"] is True
    assert "拉取当前告警" in res["summary"]
    # 助手回合 trace 含该技能调用步骤
    msgs = msg_svc.list_messages(tid)
    assistant = [m for m in msgs if m["role"] == "assistant"][-1]
    assert any(s["kind"] == "tool_call" and s["name"] == tool_name for s in assistant["trace"])


# ============================================================
# 3.1 registry_kb.search_kbs：跨库归并关键词检索
# ============================================================

def _search_kbs(client, query, kb_ids, top_k=None):
    from backend.services import registry_kb
    body = {"query": query}
    if top_k is not None:
        body["top_k"] = top_k
    return registry_kb.search_kbs(kb_ids, query, top_k)


def test_search_kbs_merges_across_kbs_with_source(client):
    kid_a = _make_kb(client, name="db手册")
    kid_b = _make_kb(client, name="网络手册")
    _upload(client, kid_a, "sql.txt", "MySQL 慢查询优化：开启慢查询日志并分析执行计划。")
    _upload(client, kid_b, "net.txt", "网络延迟排查：先 ping 网关再检查丢包率与慢查询无关。")
    hits = _search_kbs(client, "慢查询", [kid_a, kid_b], top_k=5)
    assert hits, "应在挂载库上命中"
    names = {h["kb_name"] for h in hits}
    assert names == {"db手册", "网络手册"}
    # 来源字段齐全（供工具组装 [来源: 库/文件 第n块 得分]）
    for h in hits:
        assert h["filename"] and isinstance(h["chunk_index"], int) and h["score"] > 0
    # 全局归并按得分降序
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_search_kbs_empty_no_hit_and_skips_nonready(client):
    kid = _make_kb(client, name="db手册")
    _upload(client, kid, "sql.txt", "MySQL 慢查询优化建议。")
    no_hit = _search_kbs(client, "绝无此词xyz", [kid])
    assert no_hit == []
    # 停用/不存在库被静默跳过（不报错），空库亦返回 []
    assert client.patch(f"/api/kb/{kid}", json={"status": "disabled"}).status_code == 200
    assert _search_kbs(client, "MySQL", [kid, 999999]) == []


# ============================================================
# 3.2/3.3 knowledge_search 装配与空库降级
# ============================================================

def test_build_knowledge_search_tool_with_ready_snapshot(client):
    """3.2：build 把挂载且 ready 的库做语料快照；工具只读、schema 出现、desc.kb_search=True。"""
    from backend.services import agent_runtime

    kid_a = _make_kb(client, name="db手册")
    kid_draft = _make_kb(client, name="草稿库", status="draft")  # 非 ready → 不进语料
    tid = _built_and_model(client)
    _mount_kb(client, tid, [kid_a, kid_draft])

    agent, desc = agent_runtime.build(tid)
    assert desc["kb_search"] is True  # 至少一个 ready 库
    names = _schema_names(agent.toolkit)
    assert "knowledge_search" in names

    async def run():
        tool = _tool_by_name(agent, "knowledge_search")
        assert tool.is_read_only is True
        # 未就绪库不在语料：查草稿库独有内容 → 空结果文本而非报错
        chunk = await tool.call(query="仅草稿库内容")
        text = chunk.content[0].text if chunk.content else ""
        assert "未命中" in text or "未挂载" in text

    asyncio.run(run())


def test_build_no_ready_kb_tool_still_assembled(client):
    """3.3：无可用库（未挂载/仅 draft/disabled）→ knowledge_search 仍装配、返回明确文本、desc.kb_search=False。"""
    from backend.services import agent_runtime

    # 情形 A：完全未挂载知识库
    tid = _built_and_model(client)
    agent, desc = agent_runtime.build(tid)
    assert desc["kb_search"] is False
    assert "knowledge_search" in _schema_names(agent.toolkit)

    async def run_a():
        tool = _tool_by_name(agent, "knowledge_search")
        chunk = await tool.call(query="anything")
        assert "未挂载可用的知识库" in chunk.content[0].text

    asyncio.run(run_a())
    # 情形 B：挂载了 disabled 库 → 同样视作无可用语料（独立任务避免 provider 名重复）
    kid = _make_kb(client, name="停用库", status="disabled")
    pid2 = _make_provider(client, name="deepseek-kb-disabled", api_key="sk-stored")
    tid2 = _make_task(client)
    _bind_config(client, tid2, pid2, model_name="deepseek-chat")
    _mount_kb(client, tid2, [kid])
    _agent2, desc2 = agent_runtime.build(tid2)
    assert desc2["kb_search"] is False

    async def run_b():
        tool = _tool_by_name(_agent2, "knowledge_search")
        chunk = await tool.call(query="anything")
        assert "未挂载可用的知识库" in chunk.content[0].text

    asyncio.run(run_b())
    # query 为空：明确提示不报错
    async def run_c():
        tool = _tool_by_name(agent, "knowledge_search")
        chunk = await tool.call(query="   ")
        assert "未提供检索关键词" in chunk.content[0].text

    asyncio.run(run_c())


def test_remount_affects_subsequent_build_only(client):
    """装配即快照：运行中改挂载（新增技能）只作用于之后新发起的 build，已在跑的 agent 工具集不变。"""
    from backend.services import agent_runtime

    a = _make_skill(client, name="告警", skill_md="告警处置步骤。")
    b = _make_skill(client, name="日志分析", skill_md="日志分析步骤。")
    tid = _built_and_model(client)
    _mount(client, tid, skills=[a])
    agent_a, desc_a = agent_runtime.build(tid)
    ta = desc_a["skill_tools"][0]["name"]

    # 运行中新增技能 → 新 build 反映；旧 agent 按原快照不受影响
    _mount(client, tid, skills=[a, b])
    agent_b, desc_b = agent_runtime.build(tid)
    names_b = {s["name"] for s in desc_b["skill_tools"]}
    tb = (names_b - {ta}).pop()
    assert len(desc_b["skill_tools"]) == 2
    assert _tool_by_name(agent_b, tb) is not None  # 新 run 有新增技能工具
    assert _tool_by_name(agent_a, tb) is None      # 已在跑的 agent 仍只有原装配（无新技能）


def test_session_knowledge_search_called_sourced_and_traced(app, client):
    """3.2 会话级：模型调用 knowledge_search → 返回带 [来源: 库/文件 第n块 得分] 的文本、免确认进 trace。"""
    import json as _json

    from backend.services import message as msg_svc

    kid = _make_kb(client, name="db手册")
    _upload(client, kid, "sql.txt", "MySQL 慢查询优化：开启慢查询日志定位耗时 SQL。")
    tid = _built_with_mode(client, "strict")
    _mount_kb(client, tid, [kid])

    from backend.services import agent_session
    sess = agent_session.ChatSession.create(app, tid, "查资料")
    sess.agent.model = _DriverFakeModel([
        lambda m, t: _plain_text("我来检索。") + [_tcb("knowledge_search", {"query": "慢查询"})],
        lambda m, t: _plain_text("已查得资料。"),
    ])
    sess.start()
    events = []
    for frame in sess.events():
        data = _json.loads(frame[6:-2])
        events.append(data)
        if data.get("type") == "done":
            break
    assert not any(e["type"] == "confirm_request" for e in events)
    res = next(e for e in events if e["type"] == "tool_result")
    assert res["ok"] is True and "[来源: db手册/sql.txt" in res["summary"]
    assert "得分" in res["summary"]
    msgs = msg_svc.list_messages(tid)
    assistant = [m for m in msgs if m["role"] == "assistant"][-1]
    assert any(s["kind"] == "tool_call" and s["name"] == "knowledge_search" for s in assistant["trace"])
