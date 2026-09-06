# 模型/提示词（P3）验收核心：供应商密钥加密脱敏 → 任务绑模型回读一致+指针同步
# → 提示词版本链正确 → 引用删除保护 → 预设种子可取。
import os

import pytest
from cryptography.fernet import Fernet

# crypto 惰性取主密钥：保证测试在固定 key 下可重复（避免写根 .env / 进程漂移）
os.environ.setdefault("LINGSHU_MASTER_KEY", Fernet.generate_key().decode())

from backend import crypto, models  # noqa: E402
from backend.app import create_app  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import PRESET_TASK_NAMES, ModelProvider, Task  # noqa: E402


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


def _make_provider(client, name="deepseek", api_key="sk-abc12345", **extra):
    resp = client.post(
        "/api/model-providers",
        json={"name": name, "type": "deepseek", "base_url": "https://api.example.com/v1", "api_key": api_key, **extra},
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def _make_space_task(client):
    sid = client.post("/api/spaces", json={"name": "s"}).get_json()["id"]
    tid = client.post(f"/api/spaces/{sid}/tasks", json={"title": "t", "task_type": "fault"}).get_json()["id"]
    return sid, tid


# ---------- 供应商：加密 / 掩码 / CRUD ----------

def test_provider_create_masks_and_encrypts(app, client):
    body = _make_provider(client, api_key="sk-abc12345")
    assert body["api_key"] == "****2345"  # 出口只出掩码
    assert "sk-abc12345" not in str(body)
    with app.app_context():
        provider = db.session.get(ModelProvider, body["id"])
        assert provider.api_key_enc != "sk-abc12345"  # DB 为密文
        assert crypto.decrypt(provider.api_key_enc) == "sk-abc12345"  # 可解回


def test_provider_validation_and_dup(client):
    assert client.post("/api/model-providers", json={"type": "openai", "base_url": "u"}).status_code == 400  # 缺 name
    assert client.post("/api/model-providers", json={"name": "x", "type": "nope", "base_url": "u"}).status_code == 400  # type 非法
    _make_provider(client, name="dup")
    assert client.post("/api/model-providers", json={"name": "dup", "type": "openai", "base_url": "u"}).status_code == 400  # 重名


def test_provider_list_masked_and_single_404(client):
    _make_provider(client)
    listed = client.get("/api/model-providers").get_json()
    assert len(listed) == 1
    assert listed[0]["api_key"] == "****2345"
    assert client.get("/api/model-providers/9999").status_code == 404


def test_provider_update_keeps_then_reencrypts(app, client):
    pid = _make_provider(client, api_key="old-key-777")["id"]
    resp = client.patch(f"/api/model-providers/{pid}", json={"base_url": "https://new.example.com"})
    assert resp.status_code == 200 and resp.get_json()["base_url"].endswith("new.example.com")
    with app.app_context():
        assert crypto.decrypt(db.session.get(ModelProvider, pid).api_key_enc) == "old-key-777"  # 未覆盖
    resp = client.patch(f"/api/model-providers/{pid}", json={"api_key": "new-key-888"})
    assert resp.get_json()["api_key"] == f"****{'new-key-888'[-4:]}"
    with app.app_context():
        assert crypto.decrypt(db.session.get(ModelProvider, pid).api_key_enc) == "new-key-888"


def test_provider_delete_unreferenced_ok_but_referenced_refused(app, client):
    # 未引用可删
    pid = _make_provider(client, name="discard", api_key="k")["id"]
    assert client.delete(f"/api/model-providers/{pid}").status_code == 200
    assert client.get(f"/api/model-providers/{pid}").status_code == 404
    # 被任务绑定的供应商拒绝删除
    provider = _make_provider(client, name="used")
    _, tid = _make_space_task(client)
    assert client.post(f"/api/tasks/{tid}/model-config", json={"provider_id": provider["id"]}).status_code == 201
    assert client.delete(f"/api/model-providers/{provider['id']}").status_code == 400


# ---------- 任务绑模型（MD-01） ----------

def test_bind_readback_and_pointer_sync(app, client):
    provider = _make_provider(client, default_model="deepseek-v4-flash")
    _, tid = _make_space_task(client)
    # 未绑定 GET → 404
    assert client.get(f"/api/tasks/{tid}/model-config").status_code == 404
    resp = client.post(f"/api/tasks/{tid}/model-config", json={"provider_id": provider["id"], "temperature": 0.7})
    assert resp.status_code == 201
    config = resp.get_json()
    assert config["model_name"] == "deepseek-v4-flash"  # 缺省取 provider.default_model
    assert config["temperature"] == 0.7 and config["timeout"] == 60
    # 指针同步
    with app.app_context():
        assert db.session.get(Task, tid).model_config_id == config["id"]
    # 回读一致
    got = client.get(f"/api/tasks/{tid}/model-config").get_json()
    assert got["id"] == config["id"] and got["temperature"] == 0.7
    # POST 替换 → 200、仍唯一、temperature 更新
    resp = client.post(f"/api/tasks/{tid}/model-config", json={"provider_id": provider["id"], "temperature": 1.2})
    assert resp.status_code == 200 and resp.get_json()["id"] == config["id"]
    assert resp.get_json()["temperature"] == 1.2
    # PATCH 部分调参
    resp = client.patch(f"/api/tasks/{tid}/model-config", json={"max_tokens": 2048})
    assert resp.status_code == 200 and resp.get_json()["max_tokens"] == 2048


def test_bind_validation_and_404(app, client):
    provider = _make_provider(client)
    _, tid = _make_space_task(client)
    assert client.post(f"/api/tasks/{tid}/model-config", json={"provider_id": 99999}).status_code == 400  # provider 不存在
    assert client.post(f"/api/tasks/{tid}/model-config", json={"provider_id": provider["id"], "temperature": 5}).status_code == 400  # 越界
    assert client.post("/api/tasks/99999/model-config", json={"provider_id": provider["id"]}).status_code == 404  # 任务不存在
    assert client.get("/api/tasks/99999/model-config").status_code == 404


# ---------- 提示词库（MD-03）：版本链 ----------

def test_prompt_version_chain_head_and_historical(client):
    # v1
    resp = client.post("/api/prompts", json={"name": "排障SOP", "category": "ops", "domain": "ts", "content": "v1"})
    assert resp.status_code == 201
    id1 = resp.get_json()["id"]
    assert resp.get_json()["version"] == 1 and resp.get_json()["parent_id"] is None
    # 同名再保存 → v2, parent=id1
    resp = client.post("/api/prompts", json={"name": "排障SOP", "category": "ops", "content": "v2"})
    id2 = resp.get_json()["id"]
    assert resp.get_json()["version"] == 2 and resp.get_json()["parent_id"] == id1
    # 列表只回链头
    listed = client.get("/api/prompts?name=排障SOP").get_json()
    assert len(listed) == 1 and listed[0]["id"] == id2 and listed[0]["version"] == 2
    # 历史版仍可按 id 取回
    assert client.get(f"/api/prompts/{id1}").get_json()["content"] == "v1"
    # PATCH 链头 → 生成 v3 (parent=id2)
    resp = client.patch(f"/api/prompts/{id2}", json={"content": "v3"})
    id3 = resp.get_json()["id"]
    assert resp.get_json()["version"] == 3 and resp.get_json()["parent_id"] == id2
    # 对非链头（id1）再保存 → 400 防分叉
    assert client.patch(f"/api/prompts/{id1}", json={"content": "branch"}).status_code == 400
    # 缺 content → 400
    assert client.post("/api/prompts", json={"name": "n", "category": "c"}).status_code == 400
    # 删除链头行 → 再取 404
    assert client.delete(f"/api/prompts/{id3}").status_code == 200
    assert client.get(f"/api/prompts/{id3}").status_code == 404


def test_prompt_presets_seeded(client):
    presets = client.get("/api/prompts?category=task-preset").get_json()
    names = {p["name"] for p in presets}
    assert names == set(PRESET_TASK_NAMES)  # 写文档/写代码/数据分析/排障
    assert all(p["version"] == 1 for p in presets)
    assert all(p["content"].strip() for p in presets)
