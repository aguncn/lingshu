# 骨架冒烟测试：验证应用工厂能组装、健康检查按规格返回。
# 设计上 create_app 可注入配置，这里用临时目录覆盖 data 路径，避免污染默认库。
import pytest

from backend.app import create_app


@pytest.fixture()
def client(tmp_path):
    class _Cfg:  # 本地最小配置：仅覆盖数据目录到临时目录
        DATA_DIR = tmp_path
        SQLITE_PATH = tmp_path / "app.db"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'app.db').as_posix()}"
        CORS_ORIGINS = ["http://localhost:5173"]
        MASTER_KEY = ""

        @classmethod
        def ensure_dirs(cls) -> None:
            cls.DATA_DIR.mkdir(parents=True, exist_ok=True)

    app = create_app(_Cfg)
    app.config.update(TESTING=True)
    return app.test_client()


def test_health_returns_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert "ts" in body


def test_health_needs_no_auth(client):
    # 健康检查不设鉴权，任何客户端可达
    assert client.get("/api/health").status_code == 200
