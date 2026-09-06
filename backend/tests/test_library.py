# 资料库（P6 library LB-01 + space-task-mgmt MODIFIED）验收。
# 判据对齐 specs/library 各 Requirement/Scenario：上传归属、scope 列表互斥、下载一致、
#   PATCH 分享/改名、删除+引用完整性、跨任务引用 attach/detach、合并文件清单、删任务不动库。
# 全部走 HTTP 建资源；实体文件盘面断言读 app.config DATA_DIR（夹具注入临时目录）。
import io

import pytest
from flask import current_app

from backend.app import create_app  # noqa: E402


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


def _make_space(client) -> int:
    return client.post("/api/spaces", json={"name": "sp"}).get_json()["id"]


def _make_task(client, sid: int) -> int:
    return client.post(
        f"/api/spaces/{sid}/tasks", json={"title": "t", "task_type": "fault"}
    ).get_json()["id"]


def _upload(client, filename: str, text: str, space_id=None):
    data = {"file": (io.BytesIO(text.encode("utf-8")), filename)}
    if space_id is not None:
        data["space_id"] = str(space_id)
    return client.post("/api/library", data=data, content_type="multipart/form-data")


def _names(items) -> list:
    return [i["filename"] for i in items]


# ============================================================
# 上传与 scope 过滤
# ============================================================

def test_upload_global_and_scope_views(app, client):
    # 空库 → all 返回 []
    assert client.get("/api/library").get_json() == []
    r = _upload(client, "a.md", "# hello 资料库")
    assert r.status_code == 201
    body = r.get_json()
    assert body["space_id"] is None
    assert body["shared"] is False and body["size"] > 0
    assert "path" not in body  # 存储键绝不出口
    assert len(client.get("/api/library?scope=global").get_json()) == 1
    assert len(client.get("/api/library").get_json()) == 1  # 默认 all


def test_upload_space_scope_mutual_exclusive(app, client):
    sid = _make_space(client)
    _upload(client, "global.md", "g")
    r = _upload(client, "space.md", "s", space_id=sid)
    assert r.status_code == 201
    assert r.get_json()["space_id"] == sid
    # global 视图不含空间文件；空间视图只含该空间文件
    assert _names(client.get("/api/library?scope=global").get_json()) == ["global.md"]
    got = client.get(f"/api/library?scope=space&space_id={sid}").get_json()
    assert _names(got) == ["space.md"]
    # scope=space 缺 space_id / 空间不存在 / 非法 scope → 400
    assert client.get("/api/library?scope=space").status_code == 400
    assert client.get("/api/library?scope=space&space_id=999999").status_code == 400
    assert client.get("/api/library?scope=bogus").status_code == 400


def test_upload_missing_file_and_bad_space(client):
    assert client.post("/api/library", data={}, content_type="multipart/form-data").status_code == 400
    assert _upload(client, "x.md", "x", space_id=999999).status_code == 400
    assert _upload(client, "../evil.md", "x").status_code == 201  # 剥目录只留 basename


# ============================================================
# 下载
# ============================================================

def test_download_roundtrip_and_404(client):
    text = "排障手册：连接池打满时先看活跃连接。"
    lid = _upload(client, "guide.md", text).get_json()["id"]
    resp = client.get(f"/api/library/{lid}/download")
    assert resp.status_code == 200
    assert resp.get_data(as_text=True) == text
    assert "guide.md" in resp.headers.get("Content-Disposition", "")
    assert client.get("/api/library/999999/download").status_code == 404


# ============================================================
# PATCH 分享标记 / 改名
# ============================================================

def test_patch_shared_and_rename(client):
    lid = _upload(client, "a.md", "x").get_json()["id"]
    r = client.patch(f"/api/library/{lid}", json={"shared": True, "filename": "new.md"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["shared"] is True and body["filename"] == "new.md" and body["shared_at"]
    assert "new.md" in _names(client.get("/api/library?scope=shared").get_json())
    # 非法更新 → 400 且记录不变
    assert client.patch(f"/api/library/{lid}", json={"unknown": 1}).status_code == 400
    assert client.patch(f"/api/library/{lid}", json={"shared": "yes"}).status_code == 400
    assert client.patch(f"/api/library/{lid}", json={"filename": "  "}).status_code == 400
    assert client.patch("/api/library/999999", json={"shared": True}).status_code == 404
    # 关掉分享 → 退出 shared 视图
    assert client.patch(f"/api/library/{lid}", json={"shared": False}).status_code == 200
    assert lid not in [i["id"] for i in client.get("/api/library?scope=shared").get_json()]


# ============================================================
# 删除与引用完整性
# ============================================================

def test_delete_removes_row_and_disk(app, client):
    lid = _upload(client, "del.md", "内容").get_json()["id"]
    assert client.delete(f"/api/library/{lid}").get_json() == {"ok": True}
    assert client.get(f"/api/library/{lid}/download").status_code == 404
    assert lid not in [i["id"] for i in client.get("/api/library").get_json()]
    with app.app_context():
        lib_dir = current_app.config["DATA_DIR"] / "library"
        assert list(lib_dir.iterdir()) == []  # 磁盘实体随删
    assert client.delete(f"/api/library/{lid}").status_code == 404


def test_delete_referenced_400(app, client):
    sid = _make_space(client)
    tid = _make_task(client, sid)
    lid = _upload(client, "ref.md", "y").get_json()["id"]
    assert client.post(f"/api/tasks/{tid}/library-files", json={"library_file_id": lid}).status_code == 201
    r = client.delete(f"/api/library/{lid}")
    assert r.status_code == 400
    assert "引用" in r.get_json()["message"]
    # 原样保留：仍可下载
    assert client.get(f"/api/library/{lid}/download").status_code == 200


# ============================================================
# 跨任务引用：attach / detach / 合并清单 / 删任务不动库
# ============================================================

def test_attach_duplicate_detach_and_merged_list(app, client):
    sid = _make_space(client)
    tid = _make_task(client, sid)
    lid = _upload(client, "kb.md", "kb content").get_json()["id"]
    # attach 成功
    r = client.post(f"/api/tasks/{tid}/library-files", json={"library_file_id": lid})
    assert r.status_code == 201
    ref = r.get_json()
    assert ref["kind"] == "ref" and ref["library_file_id"] == lid and ref["filename"] == "kb.md"
    # 重复 attach → 400；目标不存在/参数非法 → 对应状态
    assert client.post(f"/api/tasks/{tid}/library-files", json={"library_file_id": lid}).status_code == 400
    assert client.post(f"/api/tasks/{tid}/library-files", json={"library_file_id": 999999}).status_code == 404
    assert client.post(f"/api/tasks/{tid}/library-files", json={}).status_code == 400
    assert client.post("/api/tasks/999999/library-files", json={"library_file_id": lid}).status_code == 404
    # 合并清单：任务目录真实文件在前(kind=file)、库引用在后(kind=ref)
    with app.app_context():
        workdir = current_app.config["DATA_DIR"] / "spaces" / str(sid) / str(tid)
        workdir.mkdir(parents=True, exist_ok=True)
        (workdir / "real.txt").write_text("real", encoding="utf-8")
    merged = client.get(f"/api/tasks/{tid}/files").get_json()
    kinds = [m["kind"] for m in merged]
    assert kinds == ["file", "ref"]
    assert merged[1]["library_file_id"] == lid
    # detach 只删引用，库文件仍在
    assert client.delete(f"/api/tasks/{tid}/library-files/{ref['id']}").get_json() == {"ok": True}
    assert [m["kind"] for m in client.get(f"/api/tasks/{tid}/files").get_json()] == ["file"]
    assert lid in [i["id"] for i in client.get("/api/library").get_json()]
    assert client.get(f"/api/library/{lid}/download").status_code == 200
    # 误删别人的/不存在的引用 → 404
    assert client.delete(f"/api/tasks/{tid}/library-files/999999").status_code == 404


def test_task_delete_keeps_library_file(app, client):
    sid = _make_space(client)
    tid = _make_task(client, sid)
    lid = _upload(client, "keep.md", "keep").get_json()["id"]
    assert client.post(f"/api/tasks/{tid}/library-files", json={"library_file_id": lid}).status_code == 201
    assert client.delete(f"/api/tasks/{tid}").get_json() == {"ok": True}  # 级联删引用行
    # 库文件原样保留
    assert lid in [i["id"] for i in client.get("/api/library").get_json()]
    assert client.get(f"/api/library/{lid}/download").status_code == 200
    # 空间删除 → 库文件降级为全局（D3 SET NULL），盘面仍在
    sid2 = _make_space(client)
    lid2 = _upload(client, "space-owned.md", "s", space_id=sid2).get_json()["id"]
    assert client.delete(f"/api/spaces/{sid2}").get_json() == {"ok": True}
    row = client.get("/api/library").get_json()
    target = next(i for i in row if i["id"] == lid2)
    assert target["space_id"] is None
    assert client.get(f"/api/library/{lid2}/download").status_code == 200
