# 运行时服务层单测（P8 agentscope-runtime，任务组 1/2/3/4 的数据与装配面）。
# 覆盖：Message/AuditLog 记录与读取（task 1.3）、Audit 脱敏/截断、model_factory 密钥解析
#   （task 2.2）、mcp_client 装配（task 3.2）、agent_runtime.build（task 4.2）。
# 判据对齐 specs/agentscope-runtime：消息历史升序/空历史/任务不存在、审计字段白名单与
#   无密钥明文、模型 env 覆盖优先、MCP 注册不真拉起、build 组装含技能/专家/内置+MCP 工具。
import json

import pytest
from sqlalchemy import select

from backend.app import create_app  # noqa: E402
from backend import crypto  # noqa: E402


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
    """本文件大量直接调 service（db.session 需应用上下文），非仅 HTTP 驱动。"""
    with app.app_context():
        yield


def _make_space(client) -> int:
    return client.post("/api/spaces", json={"name": "sp"}).get_json()["id"]


def _make_task(client, sid: int = None) -> int:
    sid = sid or _make_space(client)
    return client.post(
        f"/api/spaces/{sid}/tasks", json={"title": "t", "task_type": "fault"}
    ).get_json()["id"]


def _make_provider(client, name="p", base_url="https://x/v1", **kw) -> int:
    body = {"name": name, "type": "deepseek", "base_url": base_url, **kw}
    return client.post("/api/model-providers", json=body).get_json()["id"]


def _bind_config(client, tid: int, pid: int, model_name="deepseek-chat", **kw) -> None:
    body = {"provider_id": pid}
    if model_name:
        body["model_name"] = model_name
    body.update(kw)
    assert client.post(f"/api/tasks/{tid}/model-config", json=body).status_code in (200, 201)


# ============================================================
# 任务 1.3：对话历史 message 服务
# ============================================================

def test_message_add_and_list_ascending(client):
    tid = _make_task(client)
    run_id = "run_abc"
    from backend.services import message as msg_svc

    # 空历史 → []（服务层判据；HTTP 端点属 7.1 集成测试）
    assert msg_svc.list_messages(tid) == []
    # 用户消息在收到请求即记录；助手文本在 done 时记录（带 run_id/model）
    msg_svc.add_user_message(tid, "帮我看看连接池", run_id=run_id, model="deepseek-chat")
    msg_svc.add_assistant_message(tid, "先查活跃连接数。", run_id=run_id, model="deepseek-chat")
    rows = msg_svc.list_messages(tid)
    assert [r["role"] for r in rows] == ["user", "assistant"]  # 升序
    assert rows[0]["content"] == "帮我看看连接池"
    assert rows[1]["content"] == "先查活跃连接数。"
    assert rows[0]["run_id"] == run_id and rows[1]["model"] == "deepseek-chat"


def test_message_task_missing_and_bad_role(client):
    from backend.services import message as msg_svc
    from backend.services.errors import NotFoundError, ValidationError

    with pytest.raises(NotFoundError):
        msg_svc.list_messages(999999)
    with pytest.raises(ValidationError):
        msg_svc.add_user_message(_make_task(client), "   ")  # 空内容 → 400
    with pytest.raises(ValidationError):
        msg_svc.add_message(_make_task(client), "system", "x")  # role 越界 → 400


# ============================================================
# 任务 1.3：审计 audit 服务（含脱敏/截断）
# ============================================================

def test_audit_record_model_tool_confirm(client):
    tid = _make_task(client)
    from backend.services import audit as audit_svc

    audit_svc.record(task_id=tid, run_id="run1", actor="user", action="confirm_decision",
                     target="confirm_1", result="allow", detail="放行 Write")
    audit_svc.record(task_id=tid, run_id="run1", actor="runtime", action="tool_call",
                     target="Write", result="success", detail="Write /tmp/a.txt")
    audit_svc.record(task_id=tid, run_id="run1", actor="runtime", action="model_call",
                     target="deepseek/deepseek-chat", result="success", detail="in=12 out=30")
    from backend.models import AuditLog
    from backend.extensions import db

    rows = db.session.execute(
        select(AuditLog).where(AuditLog.task_id == tid).order_by(AuditLog.id)
    ).scalars()
    acts = [(r.action, r.target, r.result, r.actor) for r in rows]
    assert ("model_call", "deepseek/deepseek-chat", "success", "runtime") in acts
    assert ("confirm_decision", "confirm_1", "allow", "user") in acts
    assert ("tool_call", "Write", "success", "runtime") in acts
    assert all(r.run_id == "run1" for r in rows)


def test_audit_scrubs_fernet_and_truncates(client):
    from backend.services import audit as audit_svc
    from backend.models import AuditLog
    from backend.extensions import db

    # 故意把密文塞进 detail：record 必须整体脱敏，绝不明文落库
    secret_token = crypto.encrypt("sk-very-secret-value")
    detail = f"tool env 误带 {secret_token} 其余普通文本"
    audit_svc.record(task_id=_make_task(client), run_id="r", action="tool_call",
                     target="Bash", result="error", detail=detail)
    stored = db.session.execute(select(AuditLog)).scalars().first()
    assert "sk-very-secret-value" not in stored.detail
    assert "[redacted]" in stored.detail
    # 超长 detail 截断
    audit_svc.record(action="tool_call", target="Read", result="error",
                     detail="长" * 5000)
    tail = db.session.execute(select(AuditLog)).scalars().all()[-1]
    assert len(tail.detail) == 2000 + len("…(截断)")  # 前缀截到上限 + 截断标记
    assert tail.detail.endswith("(截断)")


def test_audit_bad_whitelist(client):
    from backend.services import audit as audit_svc
    from backend.services.errors import ValidationError

    with pytest.raises(ValidationError):
        audit_svc.record(action="nonsense")
    with pytest.raises(ValidationError):
        audit_svc.record(actor="hacker")
    with pytest.raises(ValidationError):
        audit_svc.record(result="maybe")


def test_audit_survives_task_delete_set_null(client):
    tid = _make_task(client)
    from backend.services import audit as audit_svc

    audit_svc.record(task_id=tid, run_id="r", action="model_call", target="m",
                     result="success", detail="d")
    assert client.delete(f"/api/tasks/{tid}").status_code == 200
    from backend.models import AuditLog
    from backend.extensions import db

    row = db.session.execute(select(AuditLog)).scalars().first()
    assert row is not None and row.task_id is None  # SET NULL，审计不随任务消失


# ============================================================
# 任务 2.2：model_factory 密钥/参数解析
# ============================================================

def test_model_factory_decrypts_stored_key_and_no_leak(client, monkeypatch):
    # 本测试前提是「无 env 覆盖时解库内密文」；开发 .env 已配 LINGSHU_DEEPSEEK_API_KEY
    # （backend/__init__.py load_dotenv 会灌进 pytest 进程），显式删掉以还原前提
    monkeypatch.delenv("LINGSHU_DEEPSEEK_API_KEY", raising=False)
    pid = _make_provider(client, name="deepseek", api_key="sk-stored-value-xyz")
    tid = _make_task(client)
    _bind_config(client, tid, pid, model_name="deepseek-chat")
    from backend.services import model_factory

    model, label = model_factory.resolve_model(tid)
    assert model.credential.api_key.get_secret_value() == "sk-stored-value-xyz"
    assert model.model == "deepseek-chat"
    assert label["provider"] == "deepseek" and label["model"] == "deepseek-chat"
    # 出口不含密钥明文：label 无 key 字段、str(model) 已由 SecretStr 脱敏
    assert "api_key" not in label and "sk-stored-value-xyz" not in str(label)
    assert "sk-stored-value-xyz" not in str(model)


def test_model_factory_env_override_wins(client, monkeypatch):
    pid = _make_provider(client, name="deepseek", api_key="sk-stored-value")
    tid = _make_task(client)
    _bind_config(client, tid, pid, model_name="deepseek-chat")
    monkeypatch.setenv("LINGSHU_DEEPSEEK_API_KEY", "sk-env-override")
    from backend.services import model_factory

    model, _ = model_factory.resolve_model(tid)
    assert model.credential.api_key.get_secret_value() == "sk-env-override"


def test_model_factory_no_key_readable_error(client):
    pid = _make_provider(client, name="nokey")  # 不带 api_key
    tid = _make_task(client)
    _bind_config(client, tid, pid, model_name="some-model")
    from backend.services import model_factory
    from backend.services.errors import ValidationError

    with pytest.raises(ValidationError) as ei:
        model_factory.resolve_model(tid)
    assert "密钥" in str(ei.value)


def test_model_factory_parameters_injected(client):
    pid = _make_provider(client, name="deepseek", api_key="sk")
    tid = _make_task(client)
    _bind_config(client, tid, pid, model_name="deepseek-chat", temperature=0.2, max_tokens=500)
    from backend.services import model_factory

    model, _ = model_factory.resolve_model(tid)
    assert model.parameters is not None
    assert model.parameters.temperature == 0.2
    assert model.parameters.max_tokens == 500


def test_model_factory_unbound_task_error(client):
    from backend.services import model_factory
    from backend.services.errors import NotFoundError

    with pytest.raises(NotFoundError) as ei:
        model_factory.resolve_model(_make_task(client))
    assert "模型" in str(ei.value) or "绑定" in str(ei.value)


# ============================================================
# 任务 3.2：mcp_client 装配（注册不真拉起 / 停用未信任跳过 / http 字段）
# ============================================================

def _make_conn(name: str, transport: str = "stdio", **kw):
    """经 registry_mcp service 建连接器行，返回 ORM 对象（供 build_client 消费）。"""
    from backend.services import registry_mcp
    from backend.models import MCPConnector
    from backend.extensions import db

    d = registry_mcp.create_mcp(name=name, transport=transport, **kw)
    return db.session.get(MCPConnector, d["id"])


def test_mcp_stdio_nonexistent_register_no_spawn(client):
    """指向不存在命令的 stdio 配置：注册（构造）不崩溃、不真拉起进程——连接留在会话期。"""
    from backend.services import mcp_client

    conn = _make_conn(name="stdio1", transport="stdio",
                      command="definitely-not-exist-cmd-xyz",
                      args=["-a"], env={"TOKEN": "sk-secret-env"})
    conn.trust = True
    from backend.extensions import db
    db.session.commit()

    cli = mcp_client.build_client(conn)  # 纯配置构造：不 connect、无 spawn
    assert cli is not None
    assert cli.is_stateful is True  # stdio 强制 stateful（pydantic 校验）
    assert cli.mcp_config.command == "definitely-not-exist-cmd-xyz"
    assert cli.mcp_config.args == ["-a"]
    assert cli.mcp_config.env == {"TOKEN": "sk-secret-env"}  # 密文已解密注入，仅供运行使用
    # 关键判据：命令不存在仍注册成功且未抛错——证明构造期零副作用（真正拉起只发生在 connect）
    assert cli.name == "stdio1"


def test_mcp_skip_untrusted_and_disabled(client):
    """停用（enabled=false）或未信任（trust=false）连接器一律跳过，不进入可用工具集。"""
    from backend.services import mcp_client
    from backend.extensions import db

    untrusted = _make_conn(name="u1", transport="stdio", command="x")  # trust=False
    disabled = _make_conn(name="d1", transport="stdio", command="x")
    disabled.trust, disabled.enabled = True, False
    ok = _make_conn(name="ok1", transport="stdio", command="x")
    ok.trust = True
    db.session.commit()

    assert mcp_client.build_client(untrusted) is None
    assert mcp_client.build_client(disabled) is None
    assert mcp_client.build_client(ok) is not None
    # 批量：仅 enabled+trust 者被实例化（名字对得上即证明门控生效）
    assert [c.name for c in mcp_client.build_clients([untrusted, disabled, ok])] == ["ok1"]


def test_mcp_http_config_fields_correct(client):
    """http 连接器 → 无状态 HttpMCPConfig；url/headers（解密后）正确注入。"""
    from agentscope.mcp import HttpMCPConfig
    from backend.services import mcp_client
    from backend.extensions import db

    conn = _make_conn(name="http1", transport="http",
                      url="http://127.0.0.1:1/mcp",
                      headers={"Authorization": "Bearer tok123"})
    conn.trust = True
    db.session.commit()

    cli = mcp_client.build_client(conn)
    assert cli.is_stateful is False  # http 无状态：connect 空操作、宕机自撤
    assert isinstance(cli.mcp_config, HttpMCPConfig)
    assert cli.mcp_config.url == "http://127.0.0.1:1/mcp"
    assert cli.mcp_config.headers == {"Authorization": "Bearer tok123"}
    assert cli.mcp_config.timeout == 30.0  # 默认超时


def test_mcp_connect_filters_failures_close_lifo(client):
    """连接期：失败客户端被撤下不阻断；teardown 按 LIFO close（整块 mock 客户端，不真连）。"""
    import asyncio

    from backend.services import mcp_client

    closed: list[str] = []

    class _FakeClient:
        def __init__(self, name, stateful, ok=True):
            self.name, self.is_stateful, self._ok = name, stateful, ok

        async def connect(self):
            if not self._ok:
                raise RuntimeError("server down")

        async def close(self):
            closed.append(f"close:{self.name}")

    bad = _FakeClient("s2", stateful=True, ok=False)
    stateless = _FakeClient("http1", stateful=False)
    good = _FakeClient("s1", stateful=True, ok=True)

    async def scenario():
        ready = await mcp_client.connect_clients([bad, stateless, good])
        await mcp_client.close_clients(ready)
        return sorted(c.name for c in ready)

    assert asyncio.run(scenario()) == ["http1", "s1"]  # 坏掉的 stdio 被撤下
    assert closed == ["close:s1", "close:http1"]  # LIFO：后连的先关


# ============================================================
# 任务 4.2：agent_runtime.build 组装（FakeModel 打桩不联网）
# ============================================================

def _make_skill(client, name="sk", skill_md="默认技能文本") -> int:
    r = client.post("/api/skills", json={"name": name, "skill_md": skill_md})
    assert r.status_code == 201
    return r.get_json()["id"]


def _make_expert(client, name="exp", system_prompt="默认专家人设") -> int:
    r = client.post("/api/experts", json={"name": name, "system_prompt": system_prompt})
    assert r.status_code == 201
    return r.get_json()["id"]


def _disable_skill(client, sid: int) -> None:
    assert client.patch(f"/api/skills/{sid}", json={"enabled": False}).status_code == 200


def _disable_expert(client, eid: int) -> None:
    assert client.patch(f"/api/experts/{eid}", json={"enabled": False}).status_code == 200


def _trust_mcp(client, cid: int) -> None:
    assert client.patch(f"/api/mcp/{cid}", json={"trust": True}).status_code == 200


def _mount(client, tid: int, *, skills=(), mcps=(), experts=()):
    body = {"skills": list(skills), "mcps": list(mcps), "experts": list(experts)}
    assert client.put(f"/api/tasks/{tid}/caps", json=body).status_code == 200


def _built_and_model(client) -> int:
    """组一个已绑定可用模型的任务（build 会 resolve_model，但只构造不调用模型）。"""
    pid = _make_provider(client, name="deepseek", api_key="sk-stored")
    tid = _make_task(client)
    _bind_config(client, tid, pid, model_name="deepseek-chat")
    return tid


def _schema_names(toolkit) -> set:
    import asyncio

    schemas = asyncio.run(toolkit.get_tool_schemas())
    return {s["function"]["name"] for s in schemas}


def test_build_skill_becomes_readonly_tool_expert_in_prompt(client):
    """skill-kb-callable：技能不再注入系统提示——可用技能=skill_<slug> 只读工具（可离线列出），
    专家人设照旧参与角色塑造；desc 出 skill_tools 装配快照。"""
    from backend.services import agent_runtime

    sid = _make_skill(client, name="alarm", skill_md="先核对告警时间窗，再按 SOP 处理。")
    eid = _make_expert(client, name="dba", system_prompt="你是资深数据库专家，关注慢查询与连接池。")
    tid = _built_and_model(client)
    _mount(client, tid, skills=[sid], experts=[eid])

    agent, desc = agent_runtime.build(tid)
    assert desc["skills"] == ["alarm"]
    assert desc["skill_tools"] == [{"name": "skill_alarm", "skill_name": "alarm"}]
    assert desc["experts"] == ["dba"]
    assert desc["model"]["model"] == "deepseek-chat"
    prompt = agent._system_prompt
    names = _schema_names(agent.toolkit)
    # 技能指令只经工具按需取用：不进系统提示、但出现在可用工具集（工具即「已装配」）
    assert "你是资深数据库专家" in prompt and "标题" in prompt
    assert "skill_alarm" in names
    assert "先核对告警时间窗" not in prompt and "alarm" not in prompt


def test_build_skips_disabled_skill_and_expert(client):
    from backend.services import agent_runtime

    sid = _make_skill(client, name="off_skill", skill_md="不该出现的指令")
    eid = _make_expert(client, name="off_exp", system_prompt="不该出现的人设")
    _disable_skill(client, sid)
    _disable_expert(client, eid)
    tid = _built_and_model(client)
    _mount(client, tid, skills=[sid], experts=[eid])

    agent, desc = agent_runtime.build(tid)
    assert desc["skills"] == [] and desc["experts"] == []
    assert desc["skill_tools"] == []
    names = _schema_names(agent.toolkit)
    assert "skill_off_skill" not in names  # 停用技能不出现为工具
    prompt = agent._system_prompt
    assert "不该出现的指令" not in prompt and "不该出现的人设" not in prompt


def test_build_plain_agent_no_mounts(client):
    """无任何挂载：仍可组普通 Agent，toolkit 含内置工具（可离线列出 schema）。"""
    from backend.services import agent_runtime

    tid = _built_and_model(client)
    agent, desc = agent_runtime.build(tid)
    assert "灵枢" in agent._system_prompt  # 基础运维人设兜底
    names = _schema_names(agent.toolkit)
    assert {"Bash", "Read", "Write", "Edit", "Glob", "Grep"} <= names
    assert desc["mcps"] == [] and desc["_deferred"] == []


def test_build_mcp_live_deferred_and_skipped_partition(client):
    """http→live 直接进 Toolkit；stdio→deferred 待会话连接；停用/未信任→skipped 不出现。"""
    from backend.services import agent_runtime, mcp_client

    # http 可用连接器（live）
    ch = client.post("/api/mcp", json={
        "name": "http_ok", "transport": "http", "url": "http://127.0.0.1:1/mcp",
    }).get_json()["id"]
    _trust_mcp(client, ch)
    # stdio 可用连接器（deferred：须异步 connect 才能进 Toolkit）
    cs = client.post("/api/mcp", json={
        "name": "stdio_ok", "transport": "stdio", "command": "definitely-not-exist-cmd",
    }).get_json()["id"]
    _trust_mcp(client, cs)
    # 停用连接器（skipped）
    cd = client.post("/api/mcp", json={
        "name": "stdio_off", "transport": "stdio", "command": "x",
    }).get_json()["id"]  # trust 默认 false → 未信任亦 skipped
    tid = _built_and_model(client)
    _mount(client, tid, mcps=[ch, cs, cd])

    agent, desc = agent_runtime.build(tid)
    states = {(m["name"], m["state"]) for m in desc["mcps"]}
    assert ("http_ok", "live") in states
    assert ("stdio_ok", "deferred") in states
    assert ("stdio_off", "skipped") in states

    # live 的 http 客户端确实注册在 Toolkit basic 组；deferred 的 stdio 由其取回待连接
    group_names = [c.name for c in agent.toolkit.tool_groups[0].mcps]
    assert "http_ok" in group_names and "stdio_ok" not in group_names
    deferred = agent_runtime.require_deferred_clients(desc)
    assert [c.name for c in deferred] == ["stdio_ok"]
    assert all(c.is_stateful for c in deferred)
    # 即便 live 的 http 指向宕机端口，schema 列表不崩（宕机 MCP 自撤），内置工具仍在
    names = _schema_names(agent.toolkit)
    assert "Bash" in names


def test_build_mcp_tool_appears_in_toolkit_with_fake_client(client):
    """注入整块 mock 客户端（task 3.2 允许）：其工具经挂载路径出现在 schema 列表（离线证明）。"""
    from agentscope.tool import FunctionTool
    from backend.services import agent_runtime

    def fs_read_dir(path: str) -> str:
        """读取目录条目。"""
        return "a.txt\nb.txt"

    fake_tool = FunctionTool(fs_read_dir)
    assert fake_tool.name == "fs_read_dir"

    class _FakeMCP:
        name = "fake_mcp"
        is_stateful = False  # 无状态 → Toolkit 构造期通过（等效 http）
        is_connected = False

        async def list_tools(self):
            return [fake_tool]

    tid = _built_and_model(client)
    agent, desc = agent_runtime.build(tid, clients=[_FakeMCP()])
    names = _schema_names(agent.toolkit)
    assert "fs_read_dir" in names  # 挂载 MCP 的工具名出现在可用工具集
    assert "Bash" in names  # 内置工具不受影响


def test_build_agent_confirm_default_mode(client):
    """任务组 5：build 出来的 Agent 显式处于 DEFAULT 权限模式——Bash/Write/Edit 被请求即二次确认。"""
    from agentscope.permission import PermissionMode
    from backend.services import agent_runtime

    tid = _built_and_model(client)
    agent, _ = agent_runtime.build(tid)
    assert agent.state.permission_context.mode == PermissionMode.DEFAULT


def _built_with_mode(client, mode: str) -> int:
    """建「已绑可用模型 + 指定权限档」的任务并返回 task_id（权限装配单测，每例独立建任务隔离）。"""
    pid = _make_provider(client, name=f"deepseek-{mode}", api_key="sk-stored")
    sid = _make_space(client)
    tid = client.post(
        f"/api/spaces/{sid}/tasks",
        json={"title": "t", "task_type": "fault", "permission_mode": mode},
    ).get_json()["id"]
    _bind_config(client, tid, pid, model_name="deepseek-chat")
    return tid


def test_build_permission_modes_map_to_agentscope(client):
    """任务三种权限档 → 装配出对应 PermissionContext 与描述：strict=DEFAULT（最严，与旧行为逐字一致）、
    trusted=BYPASS 且零规则（全程无人工确认）、limited=BYPASS+仅危险规则 ask（写/删类要确认）。"""
    from agentscope.permission import PermissionBehavior, PermissionMode
    from backend.services import agent_runtime

    # strict：装配快照显式落档；上下文最严
    agent, desc = agent_runtime.build(_built_with_mode(client, "strict"))
    assert desc["permission_mode"] == "strict"
    ctx = agent.state.permission_context
    assert ctx.mode == PermissionMode.DEFAULT

    # trusted：BYPASS，无任何规则 → 全程不问
    agent, desc = agent_runtime.build(_built_with_mode(client, "trusted"))
    assert desc["permission_mode"] == "trusted"
    ctx = agent.state.permission_context
    assert ctx.mode == PermissionMode.BYPASS
    assert not ctx.ask_rules and not ctx.deny_rules and not ctx.allow_rules

    # limited：BYPASS + 少量 ask（文件修改全量 + 命令删除/覆盖子串）
    agent, desc = agent_runtime.build(_built_with_mode(client, "limited"))
    ctx = agent.state.permission_context
    assert desc["permission_mode"] == "limited"
    assert ctx.mode == PermissionMode.BYPASS
    ask = {tool: [r.rule_content for r in rules] for tool, rules in ctx.ask_rules.items()}
    assert "" in ask.get("Write", []) and "" in ask.get("Edit", [])  # 空内容=匹配一切（文件修改都确认）
    assert any(r and "rm" in r for r in ask.get("Bash", []))  # 删除类命令子串规则已注册
    assert "Read" not in ask and "Glob" not in ask and "Grep" not in ask  # 只读工具不打扰
    assert all(
        r.behavior == PermissionBehavior.ASK
        for rules in ctx.ask_rules.values() for r in rules
    )

    # 非法档被 API/service 白名单拒绝（create 即 400）
    bad = client.post(
        f"/api/spaces/{_make_space(client)}/tasks",
        json={"title": "t", "task_type": "fault", "permission_mode": "nope"},
    )
    assert bad.status_code == 400


def test_limited_engine_read_and_general_auto_allow_only_dangerous_ask(client):
    """limited 语义（真实装配的 PermissionContext 跑 PermissionEngine，不真执行）：
    只读/一般命令自动放行；文件写入与删除类命令需确认。"""
    import asyncio

    from agentscope.permission import PermissionBehavior, PermissionEngine
    from agentscope.tool import Bash, Read, Write
    from backend.services import agent_runtime

    agent, _ = agent_runtime.build(_built_with_mode(client, "limited"))
    engine = PermissionEngine(agent.state.permission_context)
    bash, rd, wr = Bash(), Read(), Write()

    async def run():
        assert (await engine.check_permission(bash, {"command": "ls -la"})).behavior == PermissionBehavior.ALLOW
        # 一般命令（内联改写不属于删除子串）自动放行——启发式边界：漏判则少问一次（安全权衡记录于代码注释）
        assert (await engine.check_permission(bash, {"command": "echo hi > /tmp/x.txt"})).behavior == PermissionBehavior.ALLOW
        assert (await engine.check_permission(bash, {"command": "rm -rf /tmp/x"})).behavior == PermissionBehavior.ASK
        assert (await engine.check_permission(rd, {"path": "/x/a.txt"})).behavior == PermissionBehavior.ALLOW
        assert (await engine.check_permission(wr, {"file_path": "/x/o.txt", "content": "hi"})).behavior == PermissionBehavior.ASK

    asyncio.run(run())


def test_askable_power_shell_rule_matches_case_insensitive(client):
    """AskablePowerShell.match_rule：命令内容的删除/覆盖子串大小写不敏感命中；空内容命中一切。"""
    import asyncio

    from backend.services import agent_runtime

    ps = agent_runtime._askable_powershell_cls()()  # noqa: SLF001 —— 单测触及内部装配细节
    async def run():
        assert await ps.match_rule("remove-item", {"command": "Remove-Item C:/x -Recurse -Force"}) is True
        assert await ps.match_rule("Move-Item", {"command": "move-item a.txt b.txt"}) is True  # 规则与命令任意大小写
        assert await ps.match_rule("remove-item", {"command": "Get-ChildItem"}) is False  # 不相关命令不命中
        assert await ps.match_rule("", {"command": "Get-Process"}) is True  # 空规则内容 = 工具级命中一切

    asyncio.run(run())


def test_limited_engine_power_shell_general_allowed_deletion_ask(client):
    """Windows：limited 档经 engine 校验 PowerShell 一般命令 ALLOW、删除/覆盖命令 ASK
    （PowerShell 原生每次返回 ASK 的实现不影响 BYPASS 下的自动放行，靠 ask 子串规则兜底危险命令）。"""
    import asyncio
    import sys

    import pytest

    from agentscope.permission import PermissionBehavior, PermissionEngine
    from backend.services import agent_runtime

    if not sys.platform.startswith("win"):
        pytest.skip("PowerShell 仅内置在 Windows 装配")

    agent, _ = agent_runtime.build(_built_with_mode(client, "limited"))
    engine = PermissionEngine(agent.state.permission_context)
    ps = agent_runtime._askable_powershell_cls()()  # noqa: SLF001 —— 与 _builtin_tools 挂载的同类同实现

    async def run():
        assert (await engine.check_permission(ps, {"command": "Get-Process"})).behavior == PermissionBehavior.ALLOW
        assert (await engine.check_permission(ps, {"command": "Remove-Item C:/x -Force"})).behavior == PermissionBehavior.ASK
        assert (await engine.check_permission(ps, {"command": "Move-Item a.txt b.txt"})).behavior == PermissionBehavior.ASK

    asyncio.run(run())


def test_build_task_without_model_readable_error(client):
    """任务无有效模型绑定 → build 抛可读错（端点将转为 SSE 首事件 error）。"""
    from backend.services import agent_runtime
    from backend.services.errors import NotFoundError

    tid = _make_task(client)  # 未绑定模型
    with pytest.raises(NotFoundError) as ei:
        agent_runtime.build(tid)
    assert "模型" in str(ei.value) or "绑定" in str(ei.value)


# ============================================================
# 任务 6.3：会话驱动（ChatSession + 真实 Agent/Toolkit + 打桩模型，线程内跑真 loop）
# ============================================================

class _DriverFakeModel:
    """驱动级打桩模型：脚本化回复队列，绝不联网。需替换 agent.model 后 start。"""

    def __init__(self, script, model="fake-driver"):
        import types

        self.model = model
        self.context_size = 32768
        self._script = list(script)
        self.formatter = types.SimpleNamespace(supported_input_media_types=[])

    async def count_tokens(self, messages, tools=None):
        return 16

    async def __call__(self, messages, tools=None, tool_choice=None, **kw):
        from agentscope.model import ChatResponse, FinishedReason

        factory = self._script.pop(0)
        content = factory(messages, tools) if callable(factory) else factory
        return ChatResponse(
            content=content, is_last=True, finished_reason=FinishedReason.COMPLETED
        )


def _tcb(name, tool_input):
    """构造模型下发的工具调用块（id 必填、input 为 JSON 字符串）。"""
    import json as _json
    import uuid as _uuid

    from agentscope.message._block import ToolCallBlock

    return ToolCallBlock(
        id=f"tc_{_uuid.uuid4().hex[:12]}",
        name=name,
        input=_json.dumps(tool_input),
    )


def _plain_text(text):
    from agentscope.message._block import TextBlock

    return [TextBlock(text=text)]


def _make_session_ready(app, client, monkeypatch=None) -> int:
    """建已绑定模型的干净任务，返回 task_id（会话测试每例独立建任务保证隔离）。"""
    pid = _make_provider(client, name="deepseek", api_key="sk-stored")
    tid = _make_task(client)
    _bind_config(client, tid, pid, model_name="deepseek-chat")
    return tid


def _collect_session(app, tid: int, user_text: str, script, decide=None, tmp=None):
    """建 Session（agent 换成打桩模型）→ start → 读 SSE 事件（遇 confirm_request 依 decide 回执）。

    返回 (事件 dict 列表, session)。decide: callable(confirm_event) -> allow 布尔；None 表示不放行也不拒绝
    （仅用于并发/中断场景手动驱动）。
    """
    import json as _json

    from backend.services import agent_session, message as msg_svc

    sess = agent_session.ChatSession.create(app, tid, user_text)
    sess.agent.model = _DriverFakeModel(script)  # 打桩替换，绝不联网
    # 用户消息由端点收到请求即记（spec R1），此处以同一 service 镜像端点前置步骤，
    # 使驱动级断言能看到 user→assistant 的完整历史形状（真实接线在 7.2 集成测试）
    msg_svc.add_user_message(tid, user_text, run_id=sess.run_id)
    sess.start()
    events = []
    for frame in sess.events():
        data = _json.loads(frame[6:-2])
        events.append(data)
        if data.get("type") == "confirm_request" and decide is not None:
            sess.submit_decision(data["confirm_id"], allow=decide(data))
    return events, sess


def test_session_text_delta_then_done_persists_messages(app, client):
    """打字机事件序：text_delta(们) → done；user+assistant 落库、assistant 与 SSE 文本一致。"""
    from backend.services import message as msg_svc

    tid = _make_session_ready(app, client)
    run_events, sess = _collect_session(
        app, tid, "你好",
        [lambda m, t: _plain_text("收到，先看日志。"), lambda m, t: _plain_text("暂无异常。")],
    )
    assert run_events[-1]["type"] == "done"
    deltas = [e["delta"] for e in run_events if e["type"] == "text_delta"]
    assert deltas  # 至少一条文本
    assert all(e.get("run_id") == sess.run_id for e in run_events if "run_id" in e)
    # 历史落库：user 即时记、assistant 以 SSE 文本拼接
    rows = msg_svc.list_messages(tid)
    assert [r["role"] for r in rows] == ["user", "assistant"]
    assert rows[0]["content"] == "你好"
    assert rows[1]["content"] == "".join(deltas).strip()
    assert rows[1]["run_id"] == sess.run_id


def test_session_confirm_allow_executes_and_continues(app, client, tmp_path):
    """confirm_request → 放行：Write 真执行（tool_result success）+ 续跑到 done + 审计 allow。"""
    from backend.models import AuditLog
    from backend.extensions import db
    from sqlalchemy import select

    tid = _make_session_ready(app, client)
    target = tmp_path / "out.txt"

    def script():
        def first(messages, tools):
            return _plain_text("准备写入。") + [
                _tcb("Write", {"file_path": str(target), "content": "hi from driver"})
            ]

        def second(messages, tools):
            return _plain_text("已写入完成。")

        return [first, second]

    events, sess = _collect_session(
        app, tid, "写文件",
        script(),
        decide=lambda d: True,
    )
    # 确认请求携带 run_id/confirm_id/name；放行后工具真执行
    confirm = next(e for e in events if e["type"] == "confirm_request")
    assert confirm["name"] == "Write" and confirm["confirm_id"] and confirm["run_id"] == sess.run_id
    assert any(e["type"] == "tool_result" and e.get("ok") for e in events)
    assert target.exists() and target.read_text() == "hi from driver"
    assert events[-1]["type"] == "done"
    # 审计：confirm_decision(allow, actor=user) + tool_call(success) + model_call
    # 先物化为 list：scalars() 结果只可迭代一次，避免后续断言命中已耗尽游标
    rows = list(db.session.execute(select(AuditLog).where(AuditLog.task_id == tid)).scalars())
    acts = {(r.actor, r.action, r.result, r.target) for r in rows}
    assert ("user", "confirm_decision", "allow", confirm["confirm_id"]) in acts
    assert ("runtime", "tool_call", "success", "Write") in acts
    # 一轮放行运行 = 2 次模型调用（park 前 + 续跑后）→ 2 条 model_call，均关联本次 run
    mce = [r for r in rows if r.action == "model_call"]
    assert len(mce) == 2 and all(r.run_id == sess.run_id for r in mce)


def test_session_confirm_deny_never_executes(app, client, tmp_path):
    """confirm_request → 拒绝：Write 绝不执行（无副作用）+ 续跑至 done + 审计 deny。"""
    from backend.models import AuditLog
    from backend.extensions import db
    from sqlalchemy import select

    tid = _make_session_ready(app, client)
    target = tmp_path / "should_not_exist.txt"

    def script():
        def first(messages, tools):
            return _plain_text("我会尝试写入。") + [
                _tcb("Write", {"file_path": str(target), "content": "must not write"})
            ]

        def second(messages, tools):
            return _plain_text("好的，我不写入。")

        return [first, second]

    events, sess = _collect_session(
        app, tid, "写文件", script(), decide=lambda d: False,
    )
    confirm = next(e for e in events if e["type"] == "confirm_request")
    assert not target.exists(), "拒绝路径绝不能产生副作用"
    assert events[-1]["type"] == "done"
    rows = db.session.execute(select(AuditLog).where(AuditLog.task_id == tid)).scalars()
    acts = {(r.actor, r.action, r.result, r.target) for r in rows}
    assert ("user", "confirm_decision", "deny", confirm["confirm_id"]) in acts


def test_session_single_confirm_single_use_and_free_slot(app, client):
    """同一 confirm_id 只可回执一次（消费后失效）；会话结束后任务槽位释放可再次发起。"""
    from backend.services import agent_session

    tid = _make_session_ready(app, client)

    def script():
        def first(messages, tools):
            return _plain_text("请求确认。") + [
                _tcb("Read", {"path": __file__})
            ]

        def second(messages, tools):
            return _plain_text("读完了。")

        return [first, second]

    sess = None
    allow = []
    holder = {}

    def decide(d):
        holder["cid"] = d["confirm_id"]
        allow.append(True)
        return True

    # 手动驱动以便在回执前断言 pending 语义
    import json as _json
    sess = agent_session.ChatSession.create(app, tid, "读文件")
    sess.agent.model = _DriverFakeModel(script())
    assert sess.submit_decision("unknown-confirm", True) is False  # 未注册 → 拒绝（端点 404）
    sess.start()
    for frame in sess.events():
        data = _json.loads(frame[6:-2])
        if data.get("type") == "confirm_request":
            assert sess.submit_decision(data["confirm_id"], True) is True
            assert sess.submit_decision(data["confirm_id"], True) is False  # single-use
        if data.get("type") == "done":
            break
    # 会话自然结束后：注册表槽位可再次被新会话占用（模拟「结束后可再次发起」）
    from backend.services import agent_session as agent_session2
    assert agent_session2.register(tid, sess) is True
    agent_session2.unregister(tid)
    assert agent_session2.register(tid, sess) is True
    agent_session2.unregister(tid)


def test_session_registry_rejects_concurrent_and_frees_on_dispose(app, client):
    """每任务单活动：register 重复 → False（端点 409 依据）；dispose 后槽位释放。"""
    from backend.services import agent_session

    tid = _make_session_ready(app, client)
    s1 = agent_session.ChatSession.create(app, tid, "x")
    s2 = agent_session.ChatSession.create(app, tid, "y")
    assert agent_session.register(tid, s1) is True
    assert agent_session.register(tid, s2) is False  # 已有活动会话 → 409
    # 断开/收尾：cancel+dispose 收掉 worker；注册表槽位由端点 unregister 释放（dispose 不动注册表）
    s1.cancel()
    s1.dispose()
    assert agent_session.unregister(tid) is None
    assert agent_session.register(tid, s2) is True  # 槽位释放 → 新会话可再次发起
    agent_session.unregister(tid)


# ============================================================
# 任务 7.2 / 8.2：对话端点集成测试（真实 HTTP + 打桩 resolve_model，离线）
# ============================================================

def _stub_resolve(monkeypatch, script_factory, model="deepseek-chat"):
    """把 model_factory.resolve_model 换成每次调用新建一个打桩模型的工厂（绝无网络）。

    resolve_model 每次 chat 调用一次（build 组装 Agent 时）；工厂化保证并发/重启等多次
    chat 各得一份独立脚本，互不污染。
    """
    from backend.services import model_factory

    def _fake(_task_id):
        return (
            _DriverFakeModel(script_factory()),
            {"provider": "deepseek", "model": model},
        )

    monkeypatch.setattr(model_factory, "resolve_model", _fake)


def _parse_sse(text: str) -> list:
    """把一整段 SSE 文本解析成事件 list（本实现每帧一行 `data: {...}` + 空行）。"""
    events = []
    for part in text.split("\n\n"):
        part = part.strip()
        if part.startswith("data: "):
            events.append(json.loads(part[len("data: "):]))
    return events


def _stream_frames(resp):
    """增量消费 buffered=False 的 SSE 响应：按 `\n\n` 切帧，跨 chunk 缓冲。

    供确认流程使用：读到 confirm_request 后可发 /decision 再继续取帧，无需整响应读完。
    """
    buf = ""
    for chunk in resp.response:
        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8")
        buf += chunk
        while "\n\n" in buf:
            frame, buf = buf.split("\n\n", 1)
            frame = frame.strip()
            if frame.startswith("data: "):
                yield json.loads(frame[len("data: "):])


def test_chat_validation_400_and_missing_task_404(client):
    """请求非法（缺/空 message）→ 400 JSON；任务不存在 → 404 JSON；均不建会话。"""
    tid = _make_task(client)
    assert client.post(f"/api/tasks/{tid}/chat", json={}).status_code == 400
    assert client.post(f"/api/tasks/{tid}/chat", json={"message": "   "}).status_code == 400
    # 任务不存在 → 404 JSON
    assert client.post("/api/tasks/999999/chat", json={"message": "hi"}).status_code == 404
    # decision 非法体 → 400；无活动会话的 run → 404
    assert client.post(f"/api/tasks/{tid}/chat/decision", json={"run_id": "r", "confirm_id": "c", "allow": "yes"}).status_code == 400
    assert client.post(f"/api/tasks/{tid}/chat/decision", json={"run_id": "r", "confirm_id": "c", "allow": True}).status_code == 404


def test_chat_model_error_first_sse_and_no_side_effect(client):
    """无可用模型：SSE 首事件 error（可读原因）后即结束；不落任何消息/审计（spec R1/R5）。"""
    tid = _make_task(client)  # 未绑定模型
    r = client.post(f"/api/tasks/{tid}/chat", json={"message": "hi"})
    assert r.content_type.startswith("text/event-stream")
    evts = _parse_sse(r.get_data(as_text=True))
    assert len(evts) == 1 and evts[0]["type"] == "error" and evts[0]["run_id"]
    assert "模型" in evts[0]["message"] or "绑定" in evts[0]["message"]
    # 零副作用：该任务无任何消息记录（连用户消息都不写）
    body = client.get(f"/api/tasks/{tid}/messages").get_json()
    assert body["messages"] == []


def test_chat_streams_text_done_and_history(app, client, monkeypatch):
    """正常对话：SSE text_delta → done；history 含 user+assistant 且助手与流文本一致（7.2 场景一）。"""
    tid = _make_task(client)
    _stub_resolve(monkeypatch, lambda: [_plain_text("正在检查连接池，稍候。")])

    r = client.post(f"/api/tasks/{tid}/chat", json={"message": "帮我看看连接池"})
    assert r.content_type.startswith("text/event-stream")
    evts = _parse_sse(r.get_data(as_text=True))
    assert evts[-1]["type"] == "done"
    assert any(e["type"] == "text_delta" for e in evts)
    run_ids = {e["run_id"] for e in evts if "run_id" in e}
    assert len(run_ids) == 1  # 全程同一 run_id
    run_id = next(iter(run_ids))

    body = client.get(f"/api/tasks/{tid}/messages").get_json()
    rows = body["messages"]
    assert [m["role"] for m in rows] == ["user", "assistant"]
    assert rows[0]["content"] == "帮我看看连接池"
    assert rows[0]["run_id"] == run_id
    joined = "".join(e["delta"] for e in evts if e["type"] == "text_delta").strip()
    assert rows[1]["content"] == joined
    assert rows[1]["model"] == "deepseek-chat"  # 助手消息带模型标识（无密钥）


def test_chat_confirm_allow_runs_to_done_history_and_audit(app, client, monkeypatch, tmp_path):
    """放行：SSE confirm_request → 回执 allow=true → tool 真执行 + 续跑至 done；
    history/审计可关联该 task/run 且无密钥明文（7.2 场景 + task 8.2）。"""
    tid = _make_task(client)
    target = tmp_path / "out.txt"

    def script():
        def first(messages, tools):
            return _plain_text("准备写入。") + [
                _tcb("Write", {"file_path": str(target), "content": "hi via http"})
            ]

        def second(messages, tools):
            return _plain_text("写入完成。")

        return [first, second]

    _stub_resolve(monkeypatch, script)

    resp = client.post(f"/api/tasks/{tid}/chat", json={"message": "写文件到目标"}, buffered=False)
    assert resp.status_code == 200 and resp.content_type.startswith("text/event-stream")

    run_id = confirm_id = None
    decided = False
    events = []
    for evt in _stream_frames(resp):
        events.append(evt)
        if evt["type"] == "confirm_request" and not decided:
            decided = True
            run_id, confirm_id = evt["run_id"], evt["confirm_id"]
            assert evt["name"] == "Write" and evt["action"]
            dr = client.post(f"/api/tasks/{tid}/chat/decision",
                             json={"run_id": run_id, "confirm_id": confirm_id, "allow": True})
            assert dr.status_code == 200 and dr.get_json()["ok"] is True
    assert decided
    assert events[-1]["type"] == "done"
    assert target.exists() and target.read_text() == "hi via http"  # 放行 → 真执行
    assert any(e["type"] == "tool_result" and e.get("ok") for e in events)
    assert all(e["run_id"] == run_id for e in events if "run_id" in e)

    # single-use：同一 confirm_id 再回执 → 404（已消费；此时会话多半已结束）
    dup = client.post(f"/api/tasks/{tid}/chat/decision",
                      json={"run_id": run_id, "confirm_id": confirm_id, "allow": True})
    assert dup.status_code == 404

    # 历史：user + assistant 拼接文本，run_id 关联
    rows = client.get(f"/api/tasks/{tid}/messages").get_json()["messages"]
    assert [m["role"] for m in rows] == ["user", "assistant"]
    joined = "".join(e["delta"] for e in events if e["type"] == "text_delta").strip()
    assert rows[1]["content"] == joined

    # 审计（task 8.2）：三类记录可关联 task/run、无密钥明文
    from backend.models import AuditLog
    from backend.extensions import db

    logs = list(db.session.execute(
        select(AuditLog).where(AuditLog.task_id == tid).order_by(AuditLog.id)
    ).scalars())
    actions = {(a.actor, a.action, a.result, a.target) for a in logs}
    assert ("runtime", "model_call", "success", "deepseek/deepseek-chat") in actions
    assert ("user", "confirm_decision", "allow", confirm_id) in actions
    assert ("runtime", "tool_call", "success", "Write") in actions
    assert logs and all(a.run_id == run_id for a in logs)
    assert all("sk-" not in (a.detail or "") for a in logs)  # 无密钥明文/密文


def test_chat_confirm_deny_no_side_effect(app, client, monkeypatch, tmp_path):
    """拒绝：Bash 类请求回执 allow=false → 工具绝不执行，Agent 收到拒绝并续跑至 done。"""
    tid = _make_task(client)
    target = tmp_path / "nope.sh"

    def script():
        def first(messages, tools):
            # Bash（非只读：重定向写文件）触发二次确认；schema 参数为 command 字符串
            return _plain_text("我将执行命令。") + [
                _tcb("Bash", {"command": f"echo boom >> {target}"})
            ]

        def second(messages, tools):
            return _plain_text("已取消执行。")

        return [first, second]

    _stub_resolve(monkeypatch, script)

    resp = client.post(f"/api/tasks/{tid}/chat", json={"message": "执行命令"}, buffered=False)
    run_id = confirm_id = None
    decided = False
    events = []
    for evt in _stream_frames(resp):
        events.append(evt)
        if evt["type"] == "confirm_request" and not decided:
            decided = True
            run_id, confirm_id = evt["run_id"], evt["confirm_id"]
            assert evt["name"] == "Bash"
            dr = client.post(f"/api/tasks/{tid}/chat/decision",
                             json={"run_id": run_id, "confirm_id": confirm_id, "allow": False})
            assert dr.status_code == 200
    assert decided and events[-1]["type"] == "done"
    assert not target.exists(), "拒绝路径绝不能产生任何副作用"
    # 审计含 user deny
    from backend.models import AuditLog
    from backend.extensions import db

    denies = [a for a in db.session.execute(
        select(AuditLog).where(AuditLog.task_id == tid)).scalars()
        if a.action == "confirm_decision"]
    assert any((a.result, a.target) == ("deny", confirm_id) for a in denies)


def test_chat_concurrent_409_then_restart_after_consumed(app, client, monkeypatch, tmp_path):
    """并发互斥（保活语义以「run 真在跑」为界）：停驻中的活动会话再次 chat → 409 JSON（原会话不受影响）；
    回执放行、run 结束后可再次发起（7.2 场景）。快脚本瞬间结束即释放槽位——这正是消除「永久 409」的关键。"""
    tid = _make_task(client)
    target = tmp_path / "conc.txt"

    def script():
        def first(messages, tools):
            return _plain_text("第一轮，请求确认。") + [
                _tcb("Write", {"file_path": str(target), "content": "x"})
            ]

        def second(messages, tools):
            return _plain_text("第一轮完成。")

        return [first, second]

    _stub_resolve(monkeypatch, script)

    # 第一次 chat：读到 confirm_request 即停读 —— run 停驻在活动会话上（未回执仍注册）
    resp1 = client.post(f"/api/tasks/{tid}/chat", json={"message": "第一轮"}, buffered=False)
    assert resp1.status_code == 200
    run_id = confirm_id = None
    for evt in _stream_frames(resp1):
        if evt["type"] == "confirm_request":
            run_id, confirm_id = evt["run_id"], evt["confirm_id"]
            break
    assert confirm_id is not None
    # run 停驻 → 会话仍活动 → 再次 chat → 409（原会话不受影响）
    dup = client.post(f"/api/tasks/{tid}/chat", json={"message": "第二轮"})
    assert dup.status_code == 409 and "运行" in dup.get_json()["message"]
    # 回执放行 → 第一轮流自然收尾（done）
    dr = client.post(f"/api/tasks/{tid}/chat/decision",
                     json={"run_id": run_id, "confirm_id": confirm_id, "allow": True})
    assert dr.status_code == 200
    tail = list(_stream_frames(resp1))
    assert tail[-1]["type"] == "done"
    assert target.exists()  # 放行 → 真执行
    # run 结束后任务可再次发起（每次 resolve 生成新打桩模型）；新脚本同样 park，验「可发起」即停
    resp3 = client.post(f"/api/tasks/{tid}/chat", json={"message": "第三轮"}, buffered=False)
    assert resp3.status_code == 200
    assert client.post(f"/api/tasks/{tid}/chat/stop").get_json()["ok"] is True
    for _e in _stream_frames(resp3):
        pass


# ============================================================
# 保活/确认可恢复/回收（session-keepalive，task 6）：SSE 断开≠取消
# ============================================================

def test_session_detach_keeps_run_parked_and_decision_recovers(app, client, tmp_path):
    """保活核心（回归最初卡死场景）：消费端读到 confirm 后「脱离」（不再迭代 events）≠ 取消 run——
    worker 仍驻留待确认；经 status/decision 恢复后跑至 done，worker 自注销、槽位随之释放。"""
    import json as _json
    import time as _time

    from backend.services import agent_session, message as msg_svc

    tid = _make_session_ready(app, client)
    target = tmp_path / "recover.txt"

    def script():
        def first(messages, tools):
            return _plain_text("写入前确认。") + [
                _tcb("Write", {"file_path": str(target), "content": "recovered"})
            ]

        def second(messages, tools):
            return _plain_text("写入完成。")

        return [first, second]

    sess = agent_session.ChatSession.create(app, tid, "写文件")
    sess.agent.model = _DriverFakeModel(script())
    msg_svc.add_user_message(tid, "写文件", run_id=sess.run_id)
    assert agent_session.register(tid, sess) is True  # 镜像 chat 端点的注册前置步骤
    sess.start()

    # 第一段：读到 confirm_request 即 close 生成器 —— 模拟前端切走、SSE 连接断开（消费端脱离）
    gen = sess.events()
    confirm = None
    for frame in gen:
        data = _json.loads(frame[6:-2])
        if data["type"] == "confirm_request":
            confirm = data
            break
    gen.close()
    assert confirm is not None
    # 脱离 ≠ 取消：run 仍注册、停驻待确认（这是旧实现会 cancel 掉、从而永久 409 的关键差异）
    assert not sess._cancelled.is_set()
    assert agent_session.active_session(tid) is sess
    assert sess.is_parked()
    # 「用户回来」经 status 采纳（摘要一致）+ decision 回执恢复
    info = sess.current_confirm()
    assert info["confirm_id"] == confirm["confirm_id"] and info["name"] == "Write" and info["reason"]
    sess.touch()
    assert sess.submit_decision(confirm["confirm_id"], allow=True) is True

    # 重新接入读余流：worker 续跑至 done，放行的写文件真发生
    tail = []
    for frame in sess.events():
        data = _json.loads(frame[6:-2])
        tail.append(data)
        if data["type"] == "done":
            break
    assert tail[-1]["type"] == "done"
    assert target.exists() and target.read_text() == "recovered"
    # worker 自注销（无任何端点在 generate 里 unregister 的情况下）：任务槽位空闲
    deadline = _time.monotonic() + 3.0
    while agent_session.active_session(tid) is not None and _time.monotonic() < deadline:
        _time.sleep(0.02)
    assert agent_session.active_session(tid) is None


def test_chat_status_and_stop_release_parked_slot(app, client, monkeypatch, tmp_path):
    """保活端点：运行中 /chat/status 暴露 active/run_id/waiting/confirm 摘要；
    /chat/stop 真取消（区别于 SSE 脱离）→ 槽位释放、无副作用、可立即再发起。"""
    tid = _make_task(client)
    target = tmp_path / "stopme.txt"

    def script():
        def first(messages, tools):
            return _plain_text("请求确认。") + [
                _tcb("Write", {"file_path": str(target), "content": "x"})
            ]

        def second(messages, tools):
            return _plain_text("继续。")

        return [first, second]

    _stub_resolve(monkeypatch, script)
    resp = client.post(f"/api/tasks/{tid}/chat", json={"message": "写文件"}, buffered=False)
    run_id = confirm_id = None
    for evt in _stream_frames(resp):
        if evt["type"] == "confirm_request":
            run_id, confirm_id = evt["run_id"], evt["confirm_id"]
            break

    # 运行中状态：active/waiting + confirm 摘要（reason 与事件文案一致）
    st = client.get(f"/api/tasks/{tid}/chat/status").get_json()
    assert st["active"] is True and st["run_id"] == run_id and st["waiting"] is True
    assert st["confirm"]["confirm_id"] == confirm_id and st["confirm"]["name"] == "Write"
    assert st["confirm"]["reason"]

    # stop：真取消 + 释放槽位；无副作用（未放行的 Write 不执行）
    assert client.post(f"/api/tasks/{tid}/chat/stop").get_json()["ok"] is True
    assert client.get(f"/api/tasks/{tid}/chat/status").get_json()["active"] is False
    assert not target.exists()
    # 已停止 → 再 stop 幂等 ok；任务不存在 → status/stop 均 404
    assert client.post(f"/api/tasks/{tid}/chat/stop").get_json()["ok"] is True
    assert client.post("/api/tasks/999999/chat/stop").status_code == 404
    assert client.get("/api/tasks/999999/chat/status").status_code == 404
    # 原 SSE 流随 stop 自然收尾（event loop 见 cancelled 退出）
    for _evt in _stream_frames(resp):
        pass

    # 槽位已释放 → 可立即再发起（旧实现的永久 409 在此应成为可恢复）；脚本同样会 park，
    # 这里仅验「能再次发起(200)」，随即显式 stop 并排空，避免遗留活动会话。
    resp2 = client.post(f"/api/tasks/{tid}/chat", json={"message": "再来一轮"}, buffered=False)
    assert resp2.status_code == 200
    assert client.post(f"/api/tasks/{tid}/chat/stop").get_json()["ok"] is True
    for _evt in _stream_frames(resp2):
        pass


def test_reaper_reclaims_orphan_parked_session(app, client, monkeypatch, tmp_path):
    """孤儿回收（防永久 409 泄漏）：停驻待确认且消费端长期无 beat 的会话被 _reap_once 取消 →
    worker 自注销 → 槽位释放，之后立即可被新会话占用。"""
    import json as _json
    import time as _time

    from backend.services import agent_session

    tid = _make_session_ready(app, client)
    monkeypatch.setattr(agent_session, "_CONSUMER_TTL", 0.0)  # 任何「无近期 beat」的 park 都算孤儿
    target = tmp_path / "orphan.txt"  # Write 会二次确认（Read 走只读快路径不 park）

    def script():
        def first(messages, tools):
            return _plain_text("请求确认。") + [
                _tcb("Write", {"file_path": str(target), "content": "x"})
            ]

        def second(messages, tools):
            return _plain_text("写完了。")

        return [first, second]

    sess = agent_session.ChatSession.create(app, tid, "写文件")
    sess.agent.model = _DriverFakeModel(script())
    sess.start()
    gen = sess.events()
    confirm = None
    for frame in gen:
        data = _json.loads(frame[6:-2])
        if data["type"] == "confirm_request":
            confirm = data
            break
    gen.close()  # 模拟消费端脱离
    assert confirm is not None and sess.is_parked()
    sess._last_consumer_seen = 0.0  # 人为让 beat 过期 → 孤儿

    agent_session._reap_once()  # 回收一次：cancel → worker 醒来自注销
    deadline = _time.monotonic() + 3.0
    while agent_session.active_session(tid) is not None and _time.monotonic() < deadline:
        _time.sleep(0.02)
    assert agent_session.active_session(tid) is None
    # 槽位已释放：原「卡死对话」终点不再是永久 409，新会话可立即占用
    assert agent_session.register(tid, sess) is True
    agent_session.unregister(tid)
