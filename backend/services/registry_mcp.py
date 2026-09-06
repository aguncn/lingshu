# MCP 连接器中心服务（P5 registry-center AD-02）：/api/mcp 的校验、增删改查与密钥保护。
# 语义要点（design D2/D8）：
#   - transport ∈ {stdio,http}：stdio 必填 command、http 必填 url（端状态校验，缺→400）；
#   - env/headers 写时「整段 JSON → Fernet 整体加密」落 env/headers 列（db.Text 密文 token），
#     出口只给 env_keys/headers_keys（键名排序，永不含值；解密失败回空不 500）；
#   - args（stdio 启动参数）非敏感维持 db.JSON；trust/enabled 布尔字段可 PATCH。
#   - 删除级联清 task_mcp（DB 外键）；trust 门控语义归 P8（本提案只管理字段）。
import json

from sqlalchemy import select

from .. import crypto
from ..extensions import db
from ..models import MCP_TRANSPORTS, MCPConnector
from .errors import NotFoundError, ValidationError


def _clean_required(value, field: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValidationError(f"{field} 不能为空")
    return cleaned


def _as_bool(value, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationError(f"{field} 必须为布尔值")
    return value


def _transport(value) -> str:
    typ = (value or "").strip() or "stdio"
    if typ not in MCP_TRANSPORTS:
        raise ValidationError(
            f"transport 取值非法：{typ}（应为 {sorted(MCP_TRANSPORTS)} 之一）"
        )
    return typ


def _string_array(value, field: str):
    """args 白名单：None 或字符串数组；非数组/含非字符串元素 → 400。"""
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValidationError(f"{field} 必须为字符串数组（或缺省）")
    return value


def _string_dict(value, field: str):
    """env/headers 白名单：None 或字符串键值对象；否则 400。"""
    if value is None:
        return None
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    ):
        raise ValidationError(f"{field} 必须为字符串键值对象（或缺省）")
    return value


def encrypt_secret(obj: dict) -> str:
    """整段对象 → Fernet 密文 token（与 api_key_enc 同构，design D2）。"""
    return crypto.encrypt(json.dumps(obj or {}, sort_keys=True, ensure_ascii=False))


def decrypt_obj(token) -> dict:
    """密文 token → dict；空/解密失败（如换了 MASTER_KEY）回空 dict，不抛 5xx。"""
    if not token:
        return {}
    try:
        return json.loads(crypto.decrypt(token))
    except (ValueError, json.JSONDecodeError):
        return {}


def env_dict(conn: MCPConnector) -> dict:
    """供连通测试/未来 P8：解密出的环境变量（不落出口，只内部用）。"""
    return decrypt_obj(conn.env)


def headers_dict(conn: MCPConnector) -> dict:
    return decrypt_obj(conn.headers)


def _mcp_out(conn: MCPConnector) -> dict:
    """出口：to_dict 基础字段 + env_keys/headers_keys（键名，不含值）。"""
    out = conn.to_dict()
    out["env_keys"] = sorted(decrypt_obj(conn.env).keys())
    out["headers_keys"] = sorted(decrypt_obj(conn.headers).keys())
    return out


def _get_or_raise(mcp_id: int) -> MCPConnector:
    conn = db.session.get(MCPConnector, mcp_id)
    if conn is None:
        raise NotFoundError("MCP 连接器不存在")
    return conn


def _name_taken(name: str, exclude_id: int | None = None) -> bool:
    row = db.session.execute(
        select(MCPConnector).where(MCPConnector.name == name)
    ).scalar_one_or_none()
    return row is not None and (exclude_id is None or row.id != exclude_id)


def _validate_transport_deps(transport: str, command, url) -> None:
    """端状态校验：stdio 必须有 command，http 必须有 url（design D8）。"""
    if transport == "stdio" and not (command or "").strip():
        raise ValidationError("stdio 传输必须提供 command")
    if transport == "http" and not (url or "").strip():
        raise ValidationError("http 传输必须提供 url")


def list_mcps() -> list[dict]:
    rows = db.session.execute(
        select(MCPConnector).order_by(MCPConnector.id.desc())
    ).scalars()
    return [_mcp_out(c) for c in rows]


def get_mcp(mcp_id: int) -> dict:
    return _mcp_out(_get_or_raise(mcp_id))


def create_mcp(
    name=None,
    transport=None,
    command=None,
    args=None,
    env=None,
    url=None,
    headers=None,
    trust=None,
    enabled=None,
) -> dict:
    cleaned_name = _clean_required(name, "name")
    if _name_taken(cleaned_name):
        raise ValidationError(f"name 已存在：{cleaned_name}")
    typ = _transport(transport)
    cmd = (command or "").strip() or None
    uri = (url or "").strip() or None
    _validate_transport_deps(typ, cmd, uri)
    env_obj = _string_dict(env, "env")
    headers_obj = _string_dict(headers, "headers")
    conn = MCPConnector(
        name=cleaned_name,
        transport=typ,
        command=cmd,
        args=_string_array(args, "args"),
        env=encrypt_secret(env_obj) if env_obj is not None else None,
        url=uri,
        headers=encrypt_secret(headers_obj) if headers_obj is not None else None,
        trust=False if trust is None else _as_bool(trust, "trust"),
        enabled=True if enabled is None else _as_bool(enabled, "enabled"),
    )
    db.session.add(conn)
    db.session.commit()
    return _mcp_out(conn)


def update_mcp(mcp_id: int, **fields) -> dict:
    """部分更新：只应用请求中出现的字段；env/headers 提供对象即整体替换、null 即清除。

    端状态在改动后统一校验：改 transport 或清空 command/url 导致 stdio 无 command /
    http 无 url → 400（未提交，改动随会话回滚，不影响已存数据）。
    """
    conn = _get_or_raise(mcp_id)
    if not fields:
        raise ValidationError("没有可更新的字段")
    unknown = set(fields) - {
        "name", "transport", "command", "args", "env", "url", "headers",
        "trust", "enabled",
    }
    if unknown:
        raise ValidationError(f"未知字段：{sorted(unknown)}")

    if "name" in fields:
        new_name = _clean_required(fields["name"], "name")
        if _name_taken(new_name, exclude_id=conn.id):
            raise ValidationError(f"name 已存在：{new_name}")
        conn.name = new_name
    if "transport" in fields:
        conn.transport = _transport(fields["transport"])
    if "command" in fields:
        conn.command = (fields["command"] or "").strip() or None
    if "url" in fields:
        conn.url = (fields["url"] or "").strip() or None
    if "args" in fields:
        conn.args = _string_array(fields["args"], "args")
    if "env" in fields:
        env_obj = _string_dict(fields["env"], "env")
        conn.env = encrypt_secret(env_obj) if env_obj is not None else None
    if "headers" in fields:
        headers_obj = _string_dict(fields["headers"], "headers")
        conn.headers = encrypt_secret(headers_obj) if headers_obj is not None else None
    if "trust" in fields:
        conn.trust = _as_bool(fields["trust"], "trust")
    if "enabled" in fields:
        conn.enabled = _as_bool(fields["enabled"], "enabled")

    _validate_transport_deps(conn.transport, conn.command, conn.url)
    db.session.commit()
    return _mcp_out(conn)


def delete_mcp(mcp_id: int) -> None:
    conn = _get_or_raise(mcp_id)
    db.session.delete(conn)
    db.session.commit()
