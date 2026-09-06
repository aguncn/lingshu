# 能力装配（P4 capability-mount）验收：挂载→读取回显→覆盖改→缺键清空→各类校验 400/404
# → 删任务级联清除 → load_mounted 聚合。实体经 ORM 在 tmp 库自建拿真实 id（design D8，
# 不依赖 seed id 恒定）；任务经 API 建，覆盖整条 PUT/GET 链路。
import pytest
from sqlalchemy import func, select

from backend.app import create_app  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import (  # noqa: E402
    Expert,
    KnowledgeBase,
    MCPConnector,
    Skill,
    TaskExpert,
    TaskKb,
    TaskMcp,
    TaskSkill,
)
from backend.services.capability import load_mounted  # noqa: E402
from backend.services.errors import NotFoundError  # noqa: E402


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


# ---------- 测试内建实体 / 任务（拿真实 id，不依赖 seed） ----------

def _make_entity(app, model, **fields) -> int:
    with app.app_context():
        obj = model(**fields)
        db.session.add(obj)
        db.session.commit()
        return obj.id


def _make_task(client, title="t") -> int:
    sid = client.post("/api/spaces", json={"name": "sp"}).get_json()["id"]
    tid = client.post(
        f"/api/spaces/{sid}/tasks", json={"title": title, "task_type": "fault"}
    ).get_json()["id"]
    return tid


def _make_all_entities(app):
    """四类各建一条，返回 (skill_id, mcp_id, kb_id, expert_id)。"""
    sid = _make_entity(app, Skill, name="t-skill", description="d", skill_md="# t")
    mid = _make_entity(app, MCPConnector, name="t-mcp")
    kid = _make_entity(app, KnowledgeBase, name="t-kb")
    eid = _make_entity(app, Expert, name="t-expert", role="ops-sme")
    return sid, mid, kid, eid


# ---------- 读取：空挂载 / 读回一致 / 排序 ----------

def test_empty_mount_reads_empty(client):
    tid = _make_task(client)
    body = client.get(f"/api/tasks/{tid}/caps").get_json()
    assert body["task_id"] == tid
    assert body == {"task_id": tid, "skills": [], "mcps": [], "kbs": [], "experts": []}


def test_put_then_get_matches(app, client):
    sid, mid, kid, eid = _make_all_entities(app)
    tid = _make_task(client)
    payload = {"skills": [sid], "mcps": [mid], "kbs": [kid], "experts": [eid]}
    resp = client.put(f"/api/tasks/{tid}/caps", json=payload)
    assert resp.status_code == 200
    assert resp.get_json() == {"task_id": tid, **payload}
    # 随后 GET 与最近一次成功 PUT 完全一致
    assert client.get(f"/api/tasks/{tid}/caps").get_json() == {"task_id": tid, **payload}


def test_get_caps_sorted_ascending(app, client):
    ids = [_make_entity(app, Skill, name=f"t-skill-{i}", skill_md="# x") for i in range(3)]
    tid = _make_task(client)
    # 乱序挂载，GET 须按 id 升序回
    assert client.put(f"/api/tasks/{tid}/caps", json={"skills": [ids[2], ids[0], ids[1]]}).status_code == 200
    assert client.get(f"/api/tasks/{tid}/caps").get_json()["skills"] == sorted(ids)


# ---------- 覆盖写：替换旧值 / 缺键清空 ----------

def test_put_replaces_old_mounts(app, client):
    old1 = _make_entity(app, Skill, name="t-old", skill_md="# x")
    keep = _make_entity(app, Skill, name="t-keep", skill_md="# x")
    added = _make_entity(app, Skill, name="t-added", skill_md="# x")
    tid = _make_task(client)
    assert client.put(f"/api/tasks/{tid}/caps", json={"skills": [old1, keep]}).status_code == 200
    # 覆盖：old1 旧关联被清，只保留 keep + 新增 added
    resp = client.put(f"/api/tasks/{tid}/caps", json={"skills": [keep, added]})
    assert resp.status_code == 200
    assert resp.get_json()["skills"] == [keep, added]


def test_missing_key_clears_that_category(app, client):
    mid = _make_entity(app, MCPConnector, name="t-mcp")
    sid = _make_entity(app, Skill, name="t-skill", skill_md="# x")
    tid = _make_task(client)
    # 先只挂 mcp（其余键缺省→本就不挂）
    assert client.put(f"/api/tasks/{tid}/caps", json={"mcps": [mid]}).status_code == 200
    # 再 PUT 仅含 skills 键：缺省分类一并清空 → mcp 也没了
    resp = client.put(f"/api/tasks/{tid}/caps", json={"skills": [sid]})
    assert resp.status_code == 200
    got = resp.get_json()
    assert got["skills"] == [sid] and got["mcps"] == []
    assert got["kbs"] == [] and got["experts"] == []


# ---------- 校验 400 / 404（失败不改动原挂载） ----------

def test_mount_missing_target_400_keeps_original(app, client):
    sid = _make_entity(app, Skill, name="t-skill", skill_md="# x")
    tid = _make_task(client)
    assert client.put(f"/api/tasks/{tid}/caps", json={"skills": [sid]}).status_code == 200
    # 混入不存在 id → 400，且原挂载 skill 保持
    resp = client.put(f"/api/tasks/{tid}/caps", json={"skills": [sid, 99999]})
    assert resp.status_code == 400
    assert "99999" in resp.get_json()["message"]
    assert client.get(f"/api/tasks/{tid}/caps").get_json()["skills"] == [sid]


def test_invalid_element_types_400(app, client):
    sid = _make_entity(app, Skill, name="t-skill", skill_md="# x")
    tid = _make_task(client)
    # 元素须为纯正整数 int：字符串 / 负数 / 浮点 / 布尔 均拒
    for bad in (["x"], [-1], [1.0], [True]):
        resp = client.put(f"/api/tasks/{tid}/caps", json={"skills": bad})
        assert resp.status_code == 400, f"应拒绝：{bad!r}"
    # 非数组（对象/数字）也拒
    for bad in (1, {"a": 1}):
        resp = client.put(f"/api/tasks/{tid}/caps", json={"skills": bad})
        assert resp.status_code == 400, f"应拒绝：{bad!r}"
    # 校验失败零写入
    assert client.get(f"/api/tasks/{tid}/caps").get_json()["skills"] == []
    # 合法 int 通过（同库真 id），排除「全部误拒」
    assert client.put(f"/api/tasks/{tid}/caps", json={"skills": [sid]}).status_code == 200


def test_duplicate_id_in_same_category_400(app, client):
    sid = _make_entity(app, Skill, name="t-skill", skill_md="# x")
    tid = _make_task(client)
    resp = client.put(f"/api/tasks/{tid}/caps", json={"skills": [sid, sid]})
    assert resp.status_code == 400
    assert client.get(f"/api/tasks/{tid}/caps").get_json()["skills"] == []


def test_unknown_category_key_400(app, client):
    sid = _make_entity(app, Skill, name="t-skill", skill_md="# x")
    tid = _make_task(client)
    resp = client.put(f"/api/tasks/{tid}/caps", json={"skillss": [sid]})
    assert resp.status_code == 400
    # 既有挂载不受未知键请求影响
    assert client.get(f"/api/tasks/{tid}/caps").get_json()["skills"] == []


def test_task_not_found_404(client):
    assert client.get("/api/tasks/99999/caps").status_code == 404
    assert client.put("/api/tasks/99999/caps", json={"skills": []}).status_code == 404


# ---------- 删任务级联清理（2.4 判据） ----------

def test_delete_task_cascades_mounts(app, client):
    sid, mid, kid, eid = _make_all_entities(app)
    tid = _make_task(client)
    assert client.put(
        f"/api/tasks/{tid}/caps", json={"skills": [sid], "mcps": [mid], "kbs": [kid], "experts": [eid]}
    ).status_code == 200
    assert client.delete(f"/api/tasks/{tid}").status_code == 200
    # 任务已删 → GET caps 404
    assert client.get(f"/api/tasks/{tid}/caps").status_code == 404
    # 关联表无该任务遗留行（DB 级联生效）
    with app.app_context():
        for assoc in (TaskSkill, TaskMcp, TaskKb, TaskExpert):
            remaining = db.session.execute(
                select(func.count())
                .select_from(assoc)
                .where(assoc.task_id == tid)
            ).scalar()
            assert remaining == 0


# ---------- load_mounted 聚合（3.2，供 P8） ----------

def test_load_mounted_aggregates_mounted_entities(app, client):
    sid = _make_entity(app, Skill, name="agg-skill", skill_md="# 分析")
    kid = _make_entity(app, KnowledgeBase, name="agg-kb", chunk_size=400)
    tid = _make_task(client)
    assert client.put(f"/api/tasks/{tid}/caps", json={"skills": [sid], "kbs": [kid]}).status_code == 200
    with app.app_context():
        loaded = load_mounted(tid)
    # 挂载的技能/知识库有实体回显，未挂载分类为空
    assert [s.id for s in loaded["skills"]] == [sid]
    assert loaded["skills"][0].name == "agg-skill"
    assert [kb.id for kb in loaded["kbs"]] == [kid]
    assert loaded["mcps"] == [] and loaded["experts"] == []


def test_load_mounted_after_task_delete_raises(app, client):
    sid = _make_entity(app, Skill, name="gone-skill", skill_md="# x")
    tid = _make_task(client)
    assert client.put(f"/api/tasks/{tid}/caps", json={"skills": [sid]}).status_code == 200
    assert client.delete(f"/api/tasks/{tid}").status_code == 200
    with app.app_context():
        with pytest.raises(NotFoundError):
            load_mounted(tid)
