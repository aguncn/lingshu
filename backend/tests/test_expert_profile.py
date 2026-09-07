# C5 运维专家档案（expert-profile）验收：档案预设 CRUD + 快照装配到任务 + 人设快照冻结。
# 判据对齐 spec registry-center（Expert=自包含档案）与 capability-mount（快照装配语义）：
#   - 档案可带 preset_skills/preset_mcp/preset_kb/preset_library（JSON id 数组，写时校验存在）
#     与 default_provider_id/default_model_name（可选默认模型）；
#   - POST /api/tasks/<id>/expert/apply = 快照装配：caps 四类全量覆盖（experts=[档案自身]，
#     预设按「现存且可用」过滤、失效进 skipped）、预设资料库补挂（幂等、只增）、
#     档案给了 provider 才落任务模型绑定（model_name 空回退 provider.default_model）；
#   - 人设 = task_expert.persona_snapshot（挂载时快照）——此后改/停用档案不影响已建任务。
import io

import pytest
from sqlalchemy import select

from backend.app import create_app  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import FileRecord  # noqa: E402


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
    """部分用例直接查 ORM（FileRecord/TaskExpert），需应用上下文。"""
    with app.app_context():
        yield


# ---------- 建资源小助手（全部走 HTTP，与既有测试风格一致） ----------
def _make_space(client) -> int:
    return client.post("/api/spaces", json={"name": "sp"}).get_json()["id"]


def _make_task(client) -> int:
    sid = _make_space(client)
    return client.post(
        f"/api/spaces/{sid}/tasks", json={"title": "t", "task_type": "fault"}
    ).get_json()["id"]


def _make_provider(client, name="dp", default_model="default-m", **kw) -> int:
    body = {
        "name": name,
        "type": "deepseek",
        "base_url": "https://x/v1",
        "default_model": default_model,
        **kw,
    }
    return client.post("/api/model-providers", json=body).get_json()["id"]


def _bind_model(client, tid: int, pid: int, model_name="deepseek-chat") -> None:
    body = {"provider_id": pid, "model_name": model_name}
    assert client.post(f"/api/tasks/{tid}/model-config", json=body).status_code in (200, 201)


def _make_skill(client, name="sk", enabled=True) -> int:
    r = client.post(
        "/api/skills", json={"name": name, "skill_md": "# 文本", "enabled": enabled}
    )
    assert r.status_code == 201
    return r.get_json()["id"]


def _make_mcp(client, name="mcp", enabled=True) -> int:
    r = client.post(
        "/api/mcp", json={"name": name, "transport": "http", "url": "http://x:9", "enabled": enabled}
    )
    assert r.status_code == 201
    return r.get_json()["id"]


def _make_kb(client, name="kb", status="ready") -> int:
    r = client.post("/api/kb", json={"name": name, "status": status})
    assert r.status_code == 201
    return r.get_json()["id"]


def _upload_lib(client, filename="a.txt", text="资料内容") -> int:
    data = {"file": (io.BytesIO(text.encode("utf-8")), filename)}
    r = client.post("/api/library", data=data, content_type="multipart/form-data")
    assert r.status_code == 201
    return r.get_json()["id"]


def _make_expert(client, name="exp", system_prompt="档案人设", **fields) -> dict:
    body = {"name": name, "system_prompt": system_prompt, **fields}
    r = client.post("/api/experts", json=body)
    assert r.status_code == 201
    return r.get_json()


def _apply(client, tid: int, eid: int):
    return client.post(f"/api/tasks/{tid}/expert/apply", json={"expert_id": eid})


def _caps(client, tid: int) -> dict:
    return client.get(f"/api/tasks/{tid}/caps").get_json()


def _lib_refs(task_id: int) -> list[int]:
    rows = db.session.execute(
        select(FileRecord.library_file_id).where(FileRecord.task_id == task_id)
    ).scalars()
    return sorted(rows)


# ============================================================
# 档案预设 CRUD（registry-center：Expert = 自包含档案）
# ============================================================

def test_expert_preset_crud_and_validation(client):
    """档案可带四类预设 id 数组与默认模型字段；GET 读回、PATCH 整体替换；非法引用/重复 → 400。"""
    sid, mid, kid = _make_skill(client, "s"), _make_mcp(client, "m"), _make_kb(client, "k")
    pid = _make_provider(client, default_model="base-m")

    expert = _make_expert(
        client,
        name="档案A",
        system_prompt="人设A",
        preset_skills=[sid],
        preset_mcp=[mid],
        preset_kb=[kid],
        default_provider_id=pid,
        default_model_name="  ",
    )
    assert expert["preset_skills"] == [sid]
    assert expert["preset_mcp"] == [mid]
    assert expert["preset_kb"] == [kid]
    assert expert["preset_library"] == []
    assert expert["default_provider_id"] == pid
    assert expert["default_model_name"] is None  # 全空白 → None

    # PATCH 整体替换某维预设（[]=清空该维）
    patched = client.patch(
        f"/api/experts/{expert['id']}",
        json={"preset_skills": [], "preset_kb": [kid], "default_model_name": "glm-4"},
    )
    assert patched.status_code == 200
    got = patched.get_json()
    assert got["preset_skills"] == []
    assert got["preset_kb"] == [kid]
    assert got["default_model_name"] == "glm-4"

    # 非法：指向不存在实体的 id → 400
    r = client.post(
        "/api/experts",
        json={"name": "坏档案", "preset_skills": [sid, 999999]},
    )
    assert r.status_code == 400
    # 非法：同数组重复 → 400
    r = client.post(
        "/api/experts",
        json={"name": "坏档案2", "preset_skills": [sid, sid]},
    )
    assert r.status_code == 400
    # 非法：default_provider_id 指向不存在供应商 → 400
    r = client.post(
        "/api/experts", json={"name": "坏档案3", "default_provider_id": 999999}
    )
    assert r.status_code == 400


# ============================================================
# 快照装配（capability-mount：apply = 档案 → 任务）
# ============================================================

def test_apply_overwrites_caps_and_filters_inactive(client):
    """套档案：experts=[档案自身]、四类 caps 被档案接管；预设按「现存且可用」过滤，失效进 skipped。"""
    good_s, off_s = _make_skill(client, "good"), _make_skill(client, "off", enabled=False)
    good_m, off_m = _make_mcp(client, "gm"), _make_mcp(client, "om", enabled=False)
    ready_k, draft_k = _make_kb(client, "ready"), _make_kb(client, "draft", status="draft")

    # 任务先手工挂载过别的技能/专家 → 应被档案接管覆盖
    other_s = _make_skill(client, "other")
    other_e = _make_expert(client, "otherE", "别人")["id"]
    tid = _make_task(client)
    assert client.put(
        f"/api/tasks/{tid}/caps",
        json={"skills": [other_s], "experts": [other_e], "mcps": [], "kbs": []},
    ).status_code == 200

    # 预设含：有效技能、停用技能、停用 MCP、就绪 KB、草稿 KB、以及一个「建档案后再删」的 id。
    # 顺序说明：create_expert 写库前校验预设 id 须存在，故须先带 ghost_s 建档案，apply 前再删 ghost_s，
    #   才能验证 apply 期的「实体已删除 → skipped」路径（而非 create 期 400）。
    ghost_s = _make_skill(client, "ghost")
    expert = _make_expert(
        client,
        name="接管者",
        system_prompt="我是接管者",
        preset_skills=[good_s, off_s, ghost_s],
        preset_mcp=[good_m, off_m],
        preset_kb=[ready_k, draft_k],
    )
    assert client.delete(f"/api/skills/{ghost_s}").status_code == 200
    r = _apply(client, tid, expert["id"])
    assert r.status_code == 200
    body = r.get_json()
    assert body["mounted"]["experts"] == [expert["id"]]
    assert body["mounted"]["skills"] == [good_s]  # off/ghost 被跳过
    assert body["mounted"]["mcps"] == [good_m]
    assert body["mounted"]["kbs"] == [ready_k]

    skipped = {(s["category"], s["id"]): s["reason"] for s in body["skipped"]}
    assert skipped[("skills", off_s)] == "实体已停用"
    assert skipped[("skills", ghost_s)] == "实体已删除"
    assert skipped[("mcps", off_m)] == "实体已停用"
    assert skipped[("kbs", draft_k)] == "知识库未就绪"

    # 任务挂载确被档案接管（手工挂的其它技能/专家被覆盖）
    caps = _caps(client, tid)
    assert caps["skills"] == [good_s]
    assert caps["experts"] == [expert["id"]]


def test_apply_without_presets_mounts_expert_alone(client):
    """档案无任何预设：只挂专家本人，四类 caps 其它维清空、library/model 不动作。"""
    eid = _make_expert(client, "纯人设", "只当角色")["id"]
    tid = _make_task(client)
    # 先给任务一个显式模型绑定（档案无 provider → 不得抢走）
    pid = _make_provider(client)
    _bind_model(client, tid, pid, "显式模型")

    r = _apply(client, tid, eid)
    assert r.status_code == 200
    body = r.get_json()
    assert body["mounted"]["experts"] == [eid]
    assert body["mounted"]["skills"] == [] and body["mounted"]["mcps"] == [] and body["mounted"]["kbs"] == []
    assert body["library"] == {"added": [], "existing": [], "skipped": []}
    assert body["model"] is None  # 未抢显式绑定
    config = client.get(f"/api/tasks/{tid}/model-config").get_json()
    assert config["provider_id"] == pid and config["model_name"] == "显式模型"


def test_apply_library_attach_is_additive_and_idempotent(client):
    """预设资料库补挂任务引用：只增不拆（手工引用保留、预设去重），二次 apply 不重复挂。"""
    lib1, lib2 = _upload_lib(client, "one.txt"), _upload_lib(client, "two.txt")
    manual = _upload_lib(client, "manual.txt")
    tid = _make_task(client)
    # 手工引用 lib1 + manual（不在档案预设里）——套用后必须原样保留
    for lid in (lib1, manual):
        assert client.post(
            f"/api/tasks/{tid}/library-files", json={"library_file_id": lid}
        ).status_code == 201

    eid = _make_expert(client, "带资料", "人设", preset_library=[lib1, lib2])["id"]

    r = _apply(client, tid, eid)
    assert r.status_code == 200
    lib = r.get_json()["library"]
    assert lib["existing"] == [lib1]   # 已引用 → 不重复挂
    assert lib["added"] == [lib2]
    assert sorted(_lib_refs(tid)) == sorted([lib1, lib2, manual])  # 手工引用未被拆

    # 二次 apply：全在 already → added 为空（幂等）
    r2 = _apply(client, tid, eid)
    assert r2.status_code == 200
    assert r2.get_json()["library"]["added"] == []
    assert sorted(_lib_refs(tid)) == sorted([lib1, lib2, manual])


def test_apply_binds_default_model_when_provider_given(client):
    """档案给了 default_provider_id → 任务模型绑定落该供应商；model_name 空回退 provider.default_model。"""
    pid = _make_provider(client, name="p", default_model="default-m")

    # 子用例 A：档案显式给了 model_name
    eid_a = _make_expert(
        client, "A", "人设A", default_provider_id=pid, default_model_name="glm-4"
    )["id"]
    tid_a = _make_task(client)
    assert _apply(client, tid_a, eid_a).status_code == 200
    cfg = client.get(f"/api/tasks/{tid_a}/model-config").get_json()
    assert cfg["provider_id"] == pid and cfg["model_name"] == "glm-4"

    # 子用例 B：档案 model_name 空 → 取供应商 default_model
    eid_b = _make_expert(client, "B", "人设B", default_provider_id=pid)["id"]
    tid_b = _make_task(client)
    assert _apply(client, tid_b, eid_b).status_code == 200
    cfg = client.get(f"/api/tasks/{tid_b}/model-config").get_json()
    assert cfg["provider_id"] == pid and cfg["model_name"] == "default-m"


def test_apply_validation_errors(client):
    """档案停用 → 400；档案/任务不存在 → 404；全部零副作用。"""
    eid = _make_expert(client, "停用", "人设")["id"]
    tid = _make_task(client)
    assert client.patch(f"/api/experts/{eid}", json={"enabled": False}).status_code == 200
    r = _apply(client, tid, eid)
    assert r.status_code == 400
    assert "停用" in r.get_json()["message"]
    assert _caps(client, tid)["experts"] == []  # 未产生任何挂载

    assert _apply(client, tid, 999999).status_code == 404        # 档案不存在
    assert _apply(client, 999999, eid).status_code == 404        # 任务不存在


# ============================================================
# 人设快照冻结（C5 快照语义：改/停用档案不影响已建任务）
# ============================================================

def test_apply_snapshots_persona_archive_edit_does_not_change_task(client):
    """挂载快照定格人设：apply 后改档案 system_prompt 甚至停用档案 → 任务组出的 Agent 人设不变。"""
    from backend.services import agent_runtime

    tid = _make_task(client)
    pid = _make_provider(client, api_key="sk-1")
    _bind_model(client, tid, pid, "deepseek-chat")
    eid = _make_expert(client, "SRE", "原版人设：你按 假设-验证 闭环工作。")["id"]
    assert _apply(client, tid, eid).status_code == 200

    def _prompt() -> str:
        agent, desc = agent_runtime.build(tid)
        assert desc["experts"] == ["SRE"]
        return agent._system_prompt

    before = _prompt()
    assert "原版人设" in before

    # 改档案人设（仍在档案上生效，任务不跟随）
    assert client.patch(
        f"/api/experts/{eid}", json={"system_prompt": "新版人设：完全不同。"}
    ).status_code == 200
    assert "原版人设" in _prompt()
    assert "新版人设" not in _prompt()

    # 停用档案：任务人设仍由快照供给（冻结），desc 专家名照旧
    assert client.patch(f"/api/experts/{eid}", json={"enabled": False}).status_code == 200
    assert "原版人设" in _prompt()

    # 重新 apply 才刷新快照 → 任务跟随到新版人设
    assert _apply(client, tid, eid).status_code == 400  # 已停用不可再套
    assert client.patch(f"/api/experts/{eid}", json={"enabled": True}).status_code == 200
    assert _apply(client, tid, eid).status_code == 200
    assert "新版人设" in _prompt()
