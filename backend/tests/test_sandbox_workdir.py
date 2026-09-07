# C2 沙箱（task 工作空间收敛）：单测覆盖 agent_runtime 的 cwd 注入与提示声明。
# 判据：内置 Bash/PowerShell 收到任务目录 cwd（_cwd）；_task_context_block 注入「工作目录」段与
#   落盘引导（缺 workdir 时不注入）；build() 幂等建出 data/spaces/<space>/<task>/、desc.workdir 指向
#   该目录、其 Bash 工具 _cwd 即工作目录、system_prompt 含工作目录——生成文件不再散落仓库根。
import os

import pytest

from backend.app import create_app  # noqa: E402
from backend.tests.test_runtime_services import (  # noqa: E402
    _bind_config,
    _make_provider,
    _make_space,
    _make_task,
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
    """直接调 service（db.session / build 的 current_app）需应用上下文，非仅 HTTP 驱动。"""
    with app.app_context():
        yield


def _model_task(client):
    """建一个绑好模型的任务，返回 (space_id, task_id)。api_key 走 Fernet 存储（不真连网）。"""
    sid = _make_space(client)
    tid = _make_task(client, sid=sid)
    pid = _make_provider(client, api_key="sk-stored")
    _bind_config(client, tid, pid)
    return sid, tid


def _bash_of(toolkit, name="Bash"):
    """从装配好的 Toolkit 取首个指定名字的工具实例（tool_groups[0].tools 为实例列表）。"""
    for group in toolkit.tool_groups:
        for tool in group.tools:
            if getattr(tool, "name", None) == name:
                return tool
    return None


def test_builtin_tools_wire_cwd(app):
    """C2：_builtin_tools(cwd=…) 把工作目录传给 Bash/PowerShell（进程级沙箱载体）。"""
    from backend.services import agent_runtime

    workdir = str(app.config["DATA_DIR"] / "spaces" / "7" / "8")
    tools = agent_runtime._builtin_tools(cwd=workdir)
    bash = next(t for t in tools if t.name == "Bash")
    assert bash._cwd == workdir  # noqa: SLF001
    if any(t.name == "PowerShell" for t in tools):
        ps = next(t for t in tools if t.name == "PowerShell")
        assert ps._cwd == workdir  # noqa: SLF001

    # 无参回落旧行为（None = 进程 cwd），既有用法不受影响
    default = agent_runtime._builtin_tools()
    assert next(t for t in default if t.name == "Bash")._cwd is None  # noqa: SLF001


def test_task_context_block_mentions_workdir(client):
    """C2：任务上下文带 workdir 时注入「工作目录」与落盘引导；缺省不带该段。"""
    from backend.services import agent_runtime
    from backend.services.task_service import get_task_or_raise

    _, tid = _model_task(client)
    task = get_task_or_raise(tid)
    workdir = r"D:\data\spaces\1\2"

    block = agent_runtime._task_context_block(task, workdir=workdir)
    assert "## 当前任务" in block
    assert "工作目录" in block and workdir in block
    assert "绝对路径" in block  # 引导模型用工作目录内绝对路径读写
    assert task.title in block

    bare = agent_runtime._task_context_block(task)
    assert "工作目录" not in bare  # 无沙箱信息不注入，保持旧提示形态


def test_build_creates_and_wires_sandbox(app, client):
    """C2 端到端：build() 幂等建任务目录；desc.workdir 指向它；装配的 Bash 以其为 cwd；
    system_prompt 声明工作目录（软沙箱的提示层兜底）。"""
    from backend.services import agent_runtime

    sid, tid = _model_task(client)
    agent, desc = agent_runtime.build(tid)

    expected = str(app.config["DATA_DIR"] / "spaces" / str(sid) / str(tid))
    assert desc["workdir"] == expected
    assert os.path.isdir(expected)  # 目录已建（幂等）
    assert os.path.basename(os.path.dirname(expected)) == str(sid)

    bash = _bash_of(agent.toolkit, "Bash")
    assert bash is not None
    assert bash._cwd == expected  # noqa: SLF001

    assert expected in agent._system_prompt
    assert "工作目录" in agent._system_prompt

    # 重复 build（多轮装配/会话复用）幂等不炸，仍是同一目录
    agent2, desc2 = agent_runtime.build(tid)
    assert desc2["workdir"] == expected
