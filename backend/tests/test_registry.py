# 注册中心（P5 registry-center）验收：四中心 CRUD + 密钥保护 + MCP 连通测试 + KB 上传/检索 + 专家组合。
# 判据对齐 spec registry-center 各 Requirement/Scenario。全部走 HTTP 建资源（registry 是管理面本体），
# 实体引用/挂载沿既有 /api/tasks/<id>/caps。MCP「成功」连通用 fixtures/mcp_fake_server.py 离线驱动
# （command=sys.executable），与外部 npx 无关、可离线复现。
import io
from pathlib import Path

import pytest
from sqlalchemy import func, select

from backend.app import create_app  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import KnowledgeChunk, TaskExpert, TaskKb, TaskMcp, TaskSkill  # noqa: E402

FAKE_MCP = Path(__file__).resolve().parent / "fixtures" / "mcp_fake_server.py"


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


def _make_task(client) -> int:
    """建空间+任务，返回 task id（registry 挂载级联判据用）。"""
    sid = client.post("/api/spaces", json={"name": "sp"}).get_json()["id"]
    return client.post(
        f"/api/spaces/{sid}/tasks", json={"title": "t", "task_type": "fault"}
    ).get_json()["id"]


def _mount(client, task_id: int, **caps) -> None:
    payload = {"skills": [], "mcps": [], "kbs": [], "experts": []}
    payload.update(caps)
    assert client.put(f"/api/tasks/{task_id}/caps", json=payload).status_code == 200


def _upload(client, kb_id: int, filename: str, text: str):
    """multipart 上传一个 UTF-8 文本文件。"""
    data = {"file": (io.BytesIO(text.encode("utf-8")), filename)}
    return client.post(
        f"/api/kb/{kb_id}/upload", data=data, content_type="multipart/form-data"
    )


# ============================================================
# 技能中心（AD-01）
# ============================================================

def test_skill_create_edit_version_enabled(client):
    resp = client.post("/api/skills", json={
        "name": "s1", "description": "d", "skill_md": "# v1",
    })
    assert resp.status_code == 201
    sid = resp.get_json()["id"]
    assert resp.get_json()["version"] == 1
    assert resp.get_json()["enabled"] is True
    # 编辑 skill_md → version+1
    r = client.patch(f"/api/skills/{sid}", json={"skill_md": "# v2 指令"})
    assert r.status_code == 200
    assert r.get_json()["version"] == 2
    assert r.get_json()["skill_md"] == "# v2 指令"
    # 启停
    r = client.patch(f"/api/skills/{sid}", json={"enabled": False})
    assert r.get_json()["enabled"] is False
    assert client.get(f"/api/skills/{sid}").get_json()["enabled"] is False


def test_skill_duplicate_name_400(client):
    assert client.post("/api/skills", json={"name": "dup"}).status_code == 201
    assert client.post("/api/skills", json={"name": "dup"}).status_code == 400


def test_skill_delete_cascades_mounts(app, client):
    sid = client.post("/api/skills", json={"name": "to-del"}).get_json()["id"]
    tid = _make_task(client)
    _mount(client, tid, skills=[sid])
    assert client.delete(f"/api/skills/{sid}").status_code == 200
    assert client.get(f"/api/skills/{sid}").status_code == 404
    caps = client.get(f"/api/tasks/{tid}/caps").get_json()
    assert caps["skills"] == []
    with app.app_context():
        left = db.session.execute(
            select(func.count()).select_from(TaskSkill).where(TaskSkill.task_id == tid)
        ).scalar()
        assert left == 0


# ============================================================
# MCP 连接器中心（AD-02）
# ============================================================

def test_mcp_transport_required_fields(client):
    # http 缺 url / stdio 缺 command → 400
    assert client.post("/api/mcp", json={
        "name": "h", "transport": "http", "command": "x",
    }).status_code == 400
    assert client.post("/api/mcp", json={
        "name": "s", "transport": "stdio",
    }).status_code == 400
    # transport 非法 → 400
    assert client.post("/api/mcp", json={
        "name": "bad", "transport": "carrier-pigeon",
    }).status_code == 400


def test_mcp_secrets_not_in_output(client):
    resp = client.post("/api/mcp", json={
        "name": "sec",
        "transport": "http",
        "url": "http://localhost:9999/mcp",
        "env": {"DB_PASS": "hunter2secret", "A": "b"},
        "headers": {"Authorization": "Bearer topsecret"},
    })
    assert resp.status_code == 201
    mid = resp.get_json()["id"]
    body = client.get(f"/api/mcp/{mid}")
    assert body.status_code == 200
    # 键名可见、值永不出现在任何出口（明文/密文都不该含该子串）
    data = body.get_data(as_text=True)
    assert "hunter2secret" not in data and "topsecret" not in data
    assert body.get_json()["env_keys"] == ["A", "DB_PASS"]
    assert body.get_json()["headers_keys"] == ["Authorization"]
    # 列表出口同样不含值
    assert "hunter2secret" not in client.get("/api/mcp").get_data(as_text=True)


def test_mcp_env_headers_replace_clear(client):
    # 用不易与 url/时间戳撞车的长 token 作旧值，便于断言「替换/清除后不再出口」
    cid = client.post("/api/mcp", json={
        "name": "swap", "transport": "http", "url": "http://localhost:9999",
        "env": {"OLD": "OLD_ENV_SECRET_ABC"}, "headers": {"H": "HDR_AUTH_TOKEN_XYZ"},
    }).get_json()["id"]
    r = client.patch(f"/api/mcp/{cid}", json={"env": {"NEW": "NEW_ENV_SECRET_DEF"}, "headers": None})
    assert r.status_code == 200
    got = r.get_json()
    assert got["env_keys"] == ["NEW"]
    assert got["headers_keys"] == []
    text = client.get(f"/api/mcp/{cid}").get_data(as_text=True)
    assert "OLD_ENV_SECRET_ABC" not in text and "HDR_AUTH_TOKEN_XYZ" not in text


# ============================================================
# MCP 连通性测试（AD-02）
# ============================================================

def test_mcp_test_unknown_404(client):
    assert client.post("/api/mcp/99999/test").status_code == 404


def test_mcp_test_stdio_success(client):
    # 用 sys.executable 驱动假服务端（离线、可复现），command 必须为可执行文件路径
    import sys
    mid = client.post("/api/mcp", json={
        "name": "fake2",
        "transport": "stdio",
        "command": sys.executable,
        "args": [str(FAKE_MCP)],
    }).get_json()["id"]
    r = client.post(f"/api/mcp/{mid}/test")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    assert r.get_json()["tool_count"] == 2
    names = r.get_json()["tools"]
    assert "fake_metrics_query" in names and "fake_log_tail" in names


def test_mcp_test_unavailable_command(client):
    mid = client.post("/api/mcp", json={
        "name": "gone",
        "transport": "stdio",
        "command": "definitely-not-a-real-cmd-xyz-123",
    }).get_json()["id"]
    r = client.post(f"/api/mcp/{mid}/test")
    assert r.status_code == 200
    assert r.get_json()["ok"] is False
    assert "无法启动" in r.get_json()["reason"]


# ============================================================
# 知识库中心（AD-03）
# ============================================================

def test_kb_defaults_and_disabled_gate(client):
    r = client.post("/api/kb", json={"name": "kb1"})
    assert r.status_code == 201
    kid = r.get_json()["id"]
    assert r.get_json()["status"] == "ready"
    assert r.get_json()["chunk_size"] == 400
    # 停用后 upload/search 都拒绝
    assert client.patch(f"/api/kb/{kid}", json={"status": "disabled"}).status_code == 200
    assert _upload(client, kid, "a.md", "hello").status_code == 400
    assert client.post(f"/api/kb/{kid}/search", json={"query": "hello"}).status_code == 400
    # 恢复 ready → 可用
    assert client.patch(f"/api/kb/{kid}", json={"status": "ready"}).status_code == 200
    assert _upload(client, kid, "a.md", "hello 世界").status_code == 200


def test_kb_duplicate_name_400(client):
    assert client.post("/api/kb", json={"name": "kbdup"}).status_code == 201
    assert client.post("/api/kb", json={"name": "kbdup"}).status_code == 400


def test_kb_delete_cascades_chunks_and_mounts(app, client):
    kid = client.post("/api/kb", json={"name": "kb-del", "chunk_size": 5}).get_json()["id"]
    assert _upload(client, kid, "doc.md", "一二三四五六七八九十").status_code == 200
    tid = _make_task(client)
    _mount(client, tid, kbs=[kid])
    assert client.delete(f"/api/kb/{kid}").status_code == 200
    assert client.get(f"/api/kb/{kid}").status_code == 404
    assert client.get(f"/api/tasks/{tid}/caps").get_json()["kbs"] == []
    with app.app_context():
        chunks = db.session.execute(
            select(func.count()).select_from(KnowledgeChunk).where(KnowledgeChunk.kb_id == kid)
        ).scalar()
        assert chunks == 0


def test_kb_upload_unsupported_type(client):
    kid = client.post("/api/kb", json={"name": "kb-pdf"}).get_json()["id"]
    pdf = client.post(
        f"/api/kb/{kid}/upload",
        data={"file": (io.BytesIO(b"%PDF-1.4 fake"), "guide.pdf")},
        content_type="multipart/form-data",
    )
    assert pdf.status_code == 400
    assert "暂不支持" in pdf.get_json()["message"]
    docx = client.post(
        f"/api/kb/{kid}/upload",
        data={"file": (io.BytesIO(b"PK fake"), "guide.docx")},
        content_type="multipart/form-data",
    )
    assert docx.status_code == 400


def test_kb_upload_same_name_replaces_other_kept(app, client):
    kid = client.post("/api/kb", json={"name": "kb-mix", "chunk_size": 3}).get_json()["id"]
    # a.md 长文本（chunk 数 > 1），b.md 短文本
    assert _upload(client, kid, "a.md", "123456789").get_json()["chunk_count"] == 3
    assert _upload(client, kid, "b.md", "xyz").get_json()["chunk_count"] == 1
    # 同名重传更短内容：a.md 块整体替换，b.md 保留
    r = _upload(client, kid, "a.md", "ab")
    assert r.get_json()["chunk_count"] == 1
    assert r.status_code == 200
    with app.app_context():
        rows = db.session.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.kb_id == kid)
        ).scalars().all()
        from collections import Counter
        by_name = Counter((c.meta or {}).get("filename") for c in rows)
        assert by_name["a.md"] == 1 and by_name["b.md"] == 1
        assert all((c.meta or {}).get("chunk_index") == 0 for c in rows)


def test_kb_search_hits_and_empty(client):
    kid = client.post("/api/kb", json={"name": "kb-search", "chunk_size": 200}).get_json()["id"]
    md = ("# 排障手册\n\n"
          "当数据库连接池打满时，先查看 max_connections 与活跃连接，"
          "再决定是否扩容连接池或排查慢查询。慢查询是常见诱因。")
    assert _upload(client, kid, "guide.md", md).status_code == 200
    r = client.post(f"/api/kb/{kid}/search", json={"query": "慢查询"})
    assert r.status_code == 200
    hits = r.get_json()
    assert hits and hits[0]["score"] > 0
    assert hits[0]["filename"] == "guide.md"
    assert "慢查询" in hits[0]["content"]
    # 无命中 → 200 空数组
    assert client.post(f"/api/kb/{kid}/search", json={"query": "绝无此词xyz"}).get_json() == []
    # 空 query → 400
    assert client.post(f"/api/kb/{kid}/search", json={"query": "  "}).status_code == 400
    # top_k 上限收敛（cap 20）
    big = client.post(f"/api/kb/{kid}/search", json={"query": "连接", "top_k": 999})
    assert big.status_code == 200 and len(big.get_json()) <= 20


# ============================================================
# 专家中心（AD-04）
# ============================================================

def test_expert_compose_readback_children(client):
    a = client.post("/api/experts", json={
        "name": "ops-a", "role": "ops-sme", "system_prompt": "你负责数据库",
    })
    assert a.status_code == 201
    aid = a.get_json()["id"]
    b = client.post("/api/experts", json={
        "name": "ops-b", "composed_of": [aid],
    })
    assert b.status_code == 201
    bid = b.get_json()["id"]
    detail = client.get(f"/api/experts/{bid}").get_json()
    assert detail["composed_of"] == [aid]
    assert detail["composed"] == [{"id": aid, "name": "ops-a", "role": "ops-sme"}]


def test_expert_invalid_composed_400(client):
    a = client.post("/api/experts", json={"name": "x-a"}).get_json()["id"]
    # 自引用（PATCH 到自身）
    r = client.patch(f"/api/experts/{a}", json={"composed_of": [a]})
    assert r.status_code == 400
    # 不存在的 id
    assert client.post("/api/experts", json={
        "name": "x-b", "composed_of": [99999],
    }).status_code == 400
    # 重复 id
    assert client.post("/api/experts", json={
        "name": "x-c", "composed_of": [a, a],
    }).status_code == 400


def test_expert_delete_referenced_400_and_role_validate(client):
    a = client.post("/api/experts", json={"name": "r-a"}).get_json()["id"]
    client.post("/api/experts", json={"name": "r-b", "composed_of": [a]})
    # 被引用不可删
    assert client.delete(f"/api/experts/{a}").status_code == 400
    # 非法 role
    assert client.post("/api/experts", json={
        "name": "r-c", "role": "not-a-role",
    }).status_code == 400
    # 未被引用可删
    c = client.post("/api/experts", json={"name": "r-d"}).get_json()["id"]
    assert client.delete(f"/api/experts/{c}").status_code == 200
