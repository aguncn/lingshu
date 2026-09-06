# 空间/任务/文件 冒烟（P2 验收核心）：
# 建空间→建任务→列文件→删任务清目录 全流程 + 校验/404/级联删除断言。
import pytest
from sqlalchemy import func, select

from backend import models
from backend.app import create_app
from backend.extensions import db
from backend.services import file_store


@pytest.fixture()
def app(tmp_path):
    # 复用 scaffold 的模式：注入临时 DATA_DIR，让迁移与服务都落在 tmp 里，不污染默认库
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


def _count(model_cls) -> int:
    return db.session.execute(
        select(func.count()).select_from(model_cls)
    ).scalar()


def _make_space(client, name="demo", visibility="private", **extra):
    resp = client.post("/api/spaces", json={"name": name, "visibility": visibility, **extra})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def _make_task(client, sid, **payload):
    resp = client.post(f"/api/spaces/{sid}/tasks", json=payload)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def test_space_create_list_and_validation(client):
    space = _make_space(client, name="demo", visibility="private")
    sid = space["id"]
    body = client.get("/api/spaces").get_json()
    assert [s["id"] for s in body] == [sid]
    # 缺 name / visibility 非法 → 400
    assert client.post("/api/spaces", json={"visibility": "private"}).status_code == 400
    assert client.post("/api/spaces", json={"name": "x", "visibility": "foo"}).status_code == 400


def test_space_creates_owner_membership(app, client):
    sid = _make_space(client, name="team1")["id"]
    with app.app_context():
        memberships = db.session.execute(
            select(models.Membership).where(models.Membership.space_id == sid)
        ).scalars().all()
    assert len(memberships) == 1
    assert memberships[0].role == "Owner"


def test_space_update_and_not_found(client):
    sid = _make_space(client, name="old")["id"]
    resp = client.patch(f"/api/spaces/{sid}", json={"name": "new", "visibility": "public"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["name"] == "new" and body["visibility"] == "public"
    assert client.patch("/api/spaces/9999", json={"name": "n"}).status_code == 404
    assert client.delete("/api/spaces/9999").status_code == 404


def test_task_create_list_validation(client):
    sid = _make_space(client)["id"]
    task = _make_task(client, sid, title="排查订单延迟", task_type="fault")
    # 属于该空间，默认状态/可见性正确
    assert task["space_id"] == sid
    assert task["status"] == "open" and task["visibility"] == "private"
    # 列表仅含本空间任务
    listed = client.get(f"/api/spaces/{sid}/tasks").get_json()
    assert [t["id"] for t in listed] == [task["id"]]
    # 缺 title / task_type 非法 / 空间不存在
    assert client.post(f"/api/spaces/{sid}/tasks", json={"task_type": "fault"}).status_code == 400
    assert client.post(f"/api/spaces/{sid}/tasks", json={"title": "t", "task_type": "nope"}).status_code == 400
    assert client.post("/api/spaces/9999/tasks", json={"title": "t", "task_type": "fault"}).status_code == 404


def test_task_get_rename_keeps_folder(app, client, tmp_path):
    sid = _make_space(client)["id"]
    tid = _make_task(client, sid, title="before", task_type="general")["id"]
    task_dir = tmp_path / "spaces" / str(sid) / str(tid)
    # GET files 会按需建目录
    assert client.get(f"/api/tasks/{tid}/files").status_code == 200
    assert task_dir.is_dir()
    # 重命名 → 标题变化、目录名（按 id）不变
    resp = client.patch(f"/api/tasks/{tid}", json={"title": "after"})
    assert resp.status_code == 200 and resp.get_json()["title"] == "after"
    assert task_dir.is_dir()
    assert client.get("/api/tasks/9999").status_code == 404


def test_files_listing_empty_then_with_file(client, tmp_path):
    sid = _make_space(client)["id"]
    tid = _make_task(client, sid, title="t", task_type="fault")["id"]
    assert client.get(f"/api/tasks/{tid}/files").get_json() == []
    # 物理放入文件 → 列表出现该文件元数据
    task_dir = tmp_path / "spaces" / str(sid) / str(tid)
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "report.txt").write_bytes(b"hello")
    body = client.get(f"/api/tasks/{tid}/files").get_json()
    assert len(body) == 1
    # P6 合并清单：实体文件标 kind=file（库引用为 kind=ref，见 library design D8）
    assert body[0]["kind"] == "file"
    assert body[0]["filename"] == "report.txt"
    assert body[0]["size"] == 5


def test_file_content_endpoint_read_and_guard(client, tmp_path):
    # P7 工作台预览端点：GET /api/tasks/<id>/files/<name> 内联返回文件字节
    sid = _make_space(client)["id"]
    tid = _make_task(client, sid, title="t", task_type="general")["id"]
    task_dir = tmp_path / "spaces" / str(sid) / str(tid)
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "report.txt").write_bytes(b"hello-workbench")
    # 正常读取 → 200 且字节一致、mime 按扩展名推断
    resp = client.get(f"/api/tasks/{tid}/files/report.txt")
    assert resp.status_code == 200
    assert resp.data == b"hello-workbench"
    assert resp.mimetype == "text/plain"
    # 不存在的文件 → 404
    assert client.get(f"/api/tasks/{tid}/files/nope.txt").status_code == 404
    # 任务不存在 → 404
    assert client.get("/api/tasks/9999/files/report.txt").status_code == 404
    # 路径穿越（文件名带 / ）→ 400，绝不允许读到任务目录外
    assert client.get(f"/api/tasks/{tid}/files/..%2F..%2F..%2Fapp.py").status_code == 400


def test_delete_task_cleans_dir_and_records(app, client, tmp_path):
    sid = _make_space(client)["id"]
    tid = _make_task(client, sid, title="del-me", task_type="alert")["id"]
    task_dir = tmp_path / "spaces" / str(sid) / str(tid)
    task_dir.mkdir(parents=True, exist_ok=True)
    with app.app_context():
        # 落盘一条 FileRecord（模拟文件已记录），验证删除任务时级联清掉
        file_store.record(sid, tid, "a.txt", "a.txt", "text/plain", 3)
    resp = client.delete(f"/api/tasks/{tid}")
    assert resp.status_code == 200
    assert not task_dir.exists()  # 目录连同文件被清理
    with app.app_context():
        assert _count(models.Task) == 0
        assert _count(models.FileRecord) == 0


def test_delete_space_cascades_and_cleans_dir(app, client, tmp_path):
    sid = _make_space(client, name="to-delete")["id"]
    _make_task(client, sid, title="t", task_type="general")
    space_dir = tmp_path / "spaces" / str(sid)
    (space_dir / "1").mkdir(parents=True, exist_ok=True)  # 模拟已有任务目录
    assert client.delete(f"/api/spaces/{sid}").status_code == 200
    assert not space_dir.exists()
    with app.app_context():
        assert _count(models.Space) == 0
        assert _count(models.Membership) == 0
        assert _count(models.Task) == 0
        assert _count(models.FileRecord) == 0
