# 场景模板（P9 scenario-templates）验收：seed 幂等装载与 .md 一致、GET 列表/单查/未知域 404、
# apply 置域+预设挂载/未知域 400/任务 404/失效实体 skip 仍 200、运行时域提示词注入 + 无域零影响。
# 判据对齐 spec scenario-templates 各 Requirement/Scenario；运行在 tmp 库（每例独立 create_app 自带 seed）。
from pathlib import Path

import pytest
from sqlalchemy import func, select

from backend.app import create_app  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import (  # noqa: E402
    SCENARIO_DOMAINS,
    Expert,
    KnowledgeBase,
    MCPConnector,
    ScenarioTemplate,
    Skill,
    Task,
)
from backend.seed.scenarios import run_scenario_seed  # noqa: E402
from backend.services.agent_runtime import (  # noqa: E402
    UNIFIED_CONSTRAINTS,
    _compose_system_prompt,
)

_DOMAIN_ORDER = [key for key, _label in SCENARIO_DOMAINS]
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "scenarios"


def _read_md(domain: str) -> str:
    return (_PROMPTS_DIR / f"{domain}.md").read_text(encoding="utf-8").strip()


# 分类 -> 实体模型 + 「可用」谓词（与 scenario_service._ACTIVE_FILTER 同口径，仅测试断言用）
_CAT_SPEC = {
    "skills": (Skill, lambda e: e.enabled),
    "mcps": (MCPConnector, lambda e: e.enabled),
    "kbs": (KnowledgeBase, lambda e: e.status == "ready"),
    "experts": (Expert, lambda e: e.enabled),
}


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
    """直接调 service/ORM 的断言需要应用上下文（非仅 HTTP 驱动）。"""
    with app.app_context():
        yield


def _make_task(client) -> int:
    sid = client.post("/api/spaces", json={"name": "sp"}).get_json()["id"]
    return client.post(
        f"/api/spaces/{sid}/tasks", json={"title": "t", "task_type": "fault"}
    ).get_json()["id"]


def _get_template(domain: str) -> ScenarioTemplate:
    return db.session.execute(
        select(ScenarioTemplate).where(ScenarioTemplate.domain == domain)
    ).scalar_one()


# ============================================================
# seed：十二域装载 / 重复 seed 不重复 / 两域真实 preset
# ============================================================

def test_seed_twelve_rows_match_prompt_files(app):
    rows = db.session.execute(select(ScenarioTemplate)).scalars().all()
    assert len(rows) == 12  # 恰十二行
    by_domain = {r.domain: r for r in rows}
    assert set(by_domain) == set(_DOMAIN_ORDER)  # 域键齐且无漂移
    for domain in _DOMAIN_ORDER:
        assert by_domain[domain].system_prompt == _read_md(domain)  # 与 .md 逐字一致

    # 重复 seed：不新增行、不重复（幂等判据）
    run_scenario_seed()
    count = db.session.execute(
        select(func.count()).select_from(ScenarioTemplate)
    ).scalar()
    assert count == 12


def test_two_sample_domains_have_real_presets_others_empty(app):
    for domain in ("monitor-inspection", "fault-diagnosis"):
        row = _get_template(domain)
        presets = {
            "skills": row.preset_skills or [],
            "mcps": row.preset_mcp or [],
            "kbs": row.preset_kb or [],
            "experts": row.preset_expert or [],
        }
        assert any(presets.values()), f"{domain} 应带预设示例"
        # 每个被引用 id 都指向真实存在且可用的实体（可被挂载）
        for cat, ids in presets.items():
            model, active = _CAT_SPEC[cat]
            objects = {
                o.id: o
                for o in db.session.execute(
                    select(model).where(model.id.in_(ids))
                ).scalars()
            }
            for pid in ids:
                assert pid in objects, f"{domain}.{cat}[{pid}] 指向不存在实体"
                assert active(objects[pid]), f"{domain}.{cat}[{pid}] 不可用"
    # 其余十域 preset 全空（待用户自行挂载）
    for domain in _DOMAIN_ORDER:
        if domain in ("monitor-inspection", "fault-diagnosis"):
            continue
        row = _get_template(domain)
        assert (row.preset_skills or []) == []
        assert (row.preset_mcp or []) == []
        assert (row.preset_kb or []) == []
        assert (row.preset_expert or []) == []


# ============================================================
# GET /api/scenarios 列表与单查
# ============================================================

def test_list_scenarios_twelve_fixed_order_with_summary(client):
    body = client.get("/api/scenarios").get_json()
    assert len(body) == 12
    assert [item["domain"] for item in body] == _DOMAIN_ORDER  # 固定域序
    assert all("name" in item and item["name"] for item in body)
    assert all(item["task_template"] for item in body)  # 任务引导概览
    monitor = next(item for item in body if item["domain"] == "monitor-inspection")
    assert monitor["preset"] == {"skills": 1, "mcps": 1, "kbs": 1, "experts": 0}


def test_get_scenario_detail_matches_file_and_unknown_404(client):
    detail = client.get("/api/scenarios/fault-diagnosis").get_json()
    assert detail["domain"] == "fault-diagnosis"
    assert detail["system_prompt"] == _read_md("fault-diagnosis")  # 全文
    assert detail["task_template"]
    assert isinstance(detail["preset_expert"], list) and detail["preset_expert"]
    assert client.get("/api/scenarios/not-a-domain").status_code == 404


# ============================================================
# POST apply：置域 + 预设挂载 / 未知域 400 / 任务 404 / 失效实体 skip
# ============================================================

def test_apply_sets_domain_and_mounts_presets(app, client):
    tid = _make_task(client)
    resp = client.post(
        f"/api/tasks/{tid}/scenario/apply", json={"domain": "monitor-inspection"}
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["task_id"] == tid and body["domain"] == "monitor-inspection"
    assert body["skipped"] == []
    mounted = body["mounted"]
    assert mounted["skills"] and mounted["mcps"] and mounted["kbs"]
    assert mounted["experts"] == []
    # scenario_domain 已持久化；caps 反映成功挂载的预设实体
    assert db.session.get(Task, tid).scenario_domain == "monitor-inspection"
    caps = client.get(f"/api/tasks/{tid}/caps").get_json()
    assert {k: caps[k] for k in ("skills", "mcps", "kbs", "experts")} == mounted


def test_apply_unknown_domain_400_no_side_effect(app, client):
    tid = _make_task(client)
    for bad in ({"domain": "bogus"}, {}, {"domain": None}):
        resp = client.post(f"/api/tasks/{tid}/scenario/apply", json=bad)
        assert resp.status_code == 400, f"应拒绝：{bad!r}"
    assert db.session.get(Task, tid).scenario_domain is None
    caps = client.get(f"/api/tasks/{tid}/caps").get_json()
    assert caps["skills"] == caps["mcps"] == caps["kbs"] == caps["experts"] == []


def test_apply_task_not_found_404(client):
    resp = client.post(
        "/api/tasks/999999/scenario/apply", json={"domain": "monitor-inspection"}
    )
    assert resp.status_code == 404


def test_apply_skips_missing_and_disabled_preset_still_200(app, client):
    # 预置被删（删除 monitor 的预设技能）→ 套用返回 200、mounted 不含它、skipped 报 deleted
    monitor = _get_template("monitor-inspection")
    gone_skill_id = monitor.preset_skills[0]
    db.session.delete(db.session.get(Skill, gone_skill_id))
    # 预置被停用（停用 fault 的 SRE 专家）→ skipped 报 disabled
    fault = _get_template("fault-diagnosis")
    sre_expert_id = fault.preset_expert[0]
    db.session.get(Expert, sre_expert_id).enabled = False
    db.session.commit()

    t1 = _make_task(client)
    r1 = client.post(
        f"/api/tasks/{t1}/scenario/apply", json={"domain": "monitor-inspection"}
    )
    assert r1.status_code == 200
    b1 = r1.get_json()
    assert b1["mounted"]["skills"] == []  # 技能已被删 → 不挂
    assert b1["mounted"]["mcps"] and b1["mounted"]["kbs"]  # 其余预设照常挂
    assert {"category": "skills", "id": gone_skill_id, "reason": "实体已删除"} in b1["skipped"]
    caps1 = client.get(f"/api/tasks/{t1}/caps").get_json()
    assert caps1["skills"] == [] and caps1["kbs"]

    t2 = _make_task(client)
    r2 = client.post(
        f"/api/tasks/{t2}/scenario/apply", json={"domain": "fault-diagnosis"}
    )
    assert r2.status_code == 200
    b2 = r2.get_json()
    assert b2["mounted"]["experts"] == []  # 专家被停用 → 不挂
    assert len(b2["mounted"]["mcps"]) == 3  # 监控/日志/链路 三连接器照常挂
    assert {"category": "experts", "id": sre_expert_id, "reason": "实体已停用"} in b2["skipped"]


# ============================================================
# 运行时：域提示词注入（domain-first + 统一约束收尾）/ 无域零影响
# ============================================================

class _StubTask:
    """_compose_system_prompt 的纯拼装输入（build 之外的轻量断言载体）。"""

    def __init__(self, title="t", task_type="fault", space=None):
        self.title = title
        self.task_type = task_type
        self.space = space


def test_compose_domain_prompt_has_domain_first_and_constraints_last(app):
    row = _get_template("fault-diagnosis")
    prompt, skills, experts = _compose_system_prompt(
        _StubTask(), [], [], scenario=row
    )
    assert prompt.startswith(row.system_prompt)  # 域段最前（与库内全文一致）
    assert "## 当前任务" in prompt  # 既有任务上下文段仍在（居中）
    assert prompt.endswith(UNIFIED_CONSTRAINTS)  # 统一约束段收尾
    for token in ("不臆造", "二次确认", "引用来源", "结构化"):
        assert token in prompt
    assert skills == [] and experts == []


def test_compose_no_domain_unchanged(app):
    # 无域（scenario=None，含「域模板缺失」同一路径）→ 与既有拼装逐字一致、不注入域/约束
    task = _StubTask()
    plain, _, _ = _compose_system_prompt(task, [], [])
    none_again, _, _ = _compose_system_prompt(task, [], [], scenario=None)
    assert plain == none_again
    assert "统一约束" not in plain  # 无域不追加约束段
    assert "## 当前任务" in plain


def test_build_after_apply_injects_domain_and_preset_expert(app, client):
    """全链路：apply(fault) 置域 + 挂 SRE 专家 → build 的 system_prompt 含域段+统一约束，专家注入生效。"""
    # 复用 P8 运行时测试的建模型方式（构造 AgentScope 模型不联网，离线可组）
    pid = client.post("/api/model-providers", json={
        "name": "scn-p", "type": "deepseek", "base_url": "https://x/v1",
        "api_key": "sk-stored",
    }).get_json()["id"]
    tid = _make_task(client)
    bind = client.post(
        f"/api/tasks/{tid}/model-config",
        json={"provider_id": pid, "model_name": "deepseek-chat"},
    )
    assert bind.status_code in (200, 201)
    apply = client.post(
        f"/api/tasks/{tid}/scenario/apply", json={"domain": "fault-diagnosis"}
    )
    assert apply.status_code == 200

    from backend.services import agent_runtime

    agent, desc = agent_runtime.build(tid)
    assert desc["experts"] == ["SRE值班专家"]  # 预设专家经 apply 挂载进运行时
    prompt = agent._system_prompt
    assert prompt.startswith(_read_md("fault-diagnosis"))  # 域段最前
    assert prompt.endswith(UNIFIED_CONSTRAINTS)  # 统一约束收尾
    # 预设的三个 http 连接器为 live（监控/日志/链路，trust=True 的可用 MCP）
    assert {m["name"] for m in desc["mcps"] if m["state"] == "live"} >= {
        "prometheus-mcp", "trace-mcp", "log-mcp",
    }
