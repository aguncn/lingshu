# MCP 连通性测试服务（P5 registry-center AD-02）：POST /api/mcp/<id>/test 的后端实现。
# 设计取向（design D6）：一次性最小握手即可达成「测真连通」意图，用标准库实现、零新依赖，
#   不在 Flask 同步路径里为单次测试桥接 AgentScope 异步 client。
#   - stdio：以 command+args（合并解密 env）起子进程，按 MCP stdio 换行 JSON-RPC 一次性发
#     initialize → notifications/initialized → tools/list，解析 tools/list 响应统计工具；
#     超时/启动失败/无工具响应 → 200 + {ok:false, reason}（含 stderr 摘要），绝不 5xx。
#   - http：向 url（携带解密 headers）POST initialize 探测，能收到可解析 JSON-RPC 即连通；
#     真实 http MCP server 本期罕见，详细工具握手留 P2 真连接器（见 design Risk）。
import json
import os
import re
import subprocess
import urllib.error
import urllib.request

from ..extensions import db
from ..models import MCPConnector
from . import registry_mcp
from .errors import NotFoundError

_TIMEOUT = 10  # 单次连通测试超时（秒），进程必回收


def _jsonrpc(method: str, msg_id: int | None = None, params: dict | None = None) -> dict:
    msg = {"jsonrpc": "2.0", "method": method}
    if msg_id is not None:
        msg["id"] = msg_id
    if params is not None:
        msg["params"] = params
    return msg


def _stdio_payload() -> str:
    """一次性写入 stdin 的三条消息：initialize(id1) → initialized(通知) → tools/list(id2)。

    服务端通常逐行处理；对「测连通」一次性灌入足够——目标只是能否完成握手并取到工具表。
    """
    init = _jsonrpc(
        "initialize", 1,
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "lingshu-registry-test", "version": "0.1.0"},
        },
    )
    notif = _jsonrpc("notifications/initialized")
    tools = _jsonrpc("tools/list", 2, {})
    return "\n".join(json.dumps(m) for m in (init, notif, tools)) + "\n"


def _parse_stdio_tools(out: str):
    """从 stdout 逐行找 id==2 的 tools/list 响应，收集工具名。

    返回工具名列表；若根本没收到 id==2 响应返回 None（区别于「取到空表」）。
    """
    names: list[str] = []
    saw_tools_response = False
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if not isinstance(msg, dict):
            continue
        if msg.get("id") == 2 and isinstance(msg.get("result"), dict):
            saw_tools_response = True
            tools = msg["result"].get("tools")
            if isinstance(tools, list):
                names.extend(
                    t.get("name") for t in tools if isinstance(t, dict) and t.get("name")
                )
    return names if saw_tools_response else None


def _error_hint(err: str, out: str) -> str:
    """失败 reason 的摘要：优先 stderr 最后非空行，其次 stdout 尾行，截断防爆。"""
    for source in (err, out):
        lines = [ln.strip() for ln in source.splitlines() if ln.strip()]
        if lines:
            hint = lines[-1]
            return hint[:200]
    return "服务端未返回工具列表"


def _test_stdio(conn: MCPConnector) -> dict:
    command = (conn.command or "").strip()
    if not command:
        return {"ok": False, "reason": "stdio 传输缺少 command，无法测试"}
    args = conn.args or []
    env = dict(os.environ)
    env.update(registry_mcp.env_dict(conn))  # 合并解密后的自定义环境变量

    try:
        proc = subprocess.Popen(
            [command, *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except FileNotFoundError:
        return {"ok": False, "reason": f"无法启动命令：{command}（本机未找到该可执行文件）"}

    try:
        out, err = proc.communicate(input=_stdio_payload(), timeout=_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.communicate(timeout=2)  # 回收管道，避免僵尸
        except subprocess.TimeoutExpired:
            pass
        return {"ok": False, "reason": f"连接超时（>{_TIMEOUT}s），服务端未响应 tools/list"}
    finally:
        if proc.poll() is None:
            proc.kill()

    names = _parse_stdio_tools(out)
    if names is not None:
        return {"ok": True, "tools": names, "tool_count": len(names)}
    return {"ok": False, "reason": f"MCP 握手未取到工具列表：{_error_hint(err, out)}"}


def _first_json(text: str):
    """尽力从 HTTP 响应体取首个 JSON 文档（兼容 SSE 的 data: 行与纯 JSON 两种形态）。"""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            line = line[len("data:"):].strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except ValueError:
            continue
    return None


def _test_http(conn: MCPConnector) -> dict:
    url = (conn.url or "").strip()
    if not url:
        return {"ok": False, "reason": "http 传输缺少 url，无法测试"}
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    headers.update(registry_mcp.headers_dict(conn))

    init = _jsonrpc("initialize", 1, {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "lingshu-registry-test", "version": "0.1.0"},
    })
    try:
        req = urllib.request.Request(
            url, data=json.dumps(init).encode(), headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", "replace")
            session = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
            status = resp.status
    except urllib.error.HTTPError as exc:
        return {"ok": False, "reason": f"HTTP 探测失败：{exc.code} {exc.reason}"}
    except urllib.error.URLError as exc:
        return {"ok": False, "reason": f"HTTP 探测失败：{exc.reason}"}
    except OSError as exc:
        return {"ok": False, "reason": f"HTTP 探测失败：{exc}"}

    init_msg = _first_json(body)
    if init_msg is None:
        return {"ok": False, "reason": f"HTTP 返回 {status}，但响应不是可解析的 JSON-RPC"}

    # 拿到 session 再试一次 tools/list，尽力取工具表（失败不致命：http 只验证连通）
    tools: list[str] = []
    if session:
        headers = dict(headers)
        headers["Mcp-Session-Id"] = session
        try:
            tools_req = urllib.request.Request(
                url,
                data=json.dumps(_jsonrpc("tools/list", 2, {})).encode(),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(tools_req, timeout=_TIMEOUT) as resp:
                tools_msg = _first_json(resp.read().decode("utf-8", "replace"))
                if isinstance(tools_msg, dict):
                    result = tools_msg.get("result") or {}
                    if isinstance(result.get("tools"), list):
                        tools = [t.get("name") for t in result["tools"] if isinstance(t, dict) and t.get("name")]
        except (urllib.error.URLError, urllib.error.HTTPError, OSError):
            pass  # tools/list 拿不到不回退为失败——http 判连通即可
    return {"ok": True, "tools": tools, "tool_count": len(tools)}


def test_connector(mcp_id: int) -> dict:
    """入口：连接器不存在 → 404；按 transport 分支测试。失败一律 ok=false 业务结果，不 5xx。"""
    conn = db.session.get(MCPConnector, mcp_id)
    if conn is None:
        raise NotFoundError("MCP 连接器不存在")
    if conn.transport == "http":
        return _test_http(conn)
    return _test_stdio(conn)
