# MCP 客户端装配服务（P8 agentscope-runtime，design D3/D7）：挂载且「可用」的 MCPConnector → AgentScope MCPClient。
# 契约对齐 spec「任务挂载能力注入」：
#   - 只实例化 enabled 且 trust 的连接器（停用 enabled=false、未信任 trust=false 均视为「未就绪」跳过——
#     信任前置语义自 P5 归入 P8 运行时门控，见 registry-center 归档 design 决策 A）；
#   - stdio 传输 → 必须 stateful 的 StdioMCPConfig（command/args/env），http → 无状态 HttpMCPConfig（url/headers）；
#   - env/headers 为 Fernet 整段密文，经 registry_mcp.env_dict/headers_dict 解密后注入运行配置，
#     密钥值只进 pydantic 配置、绝不落日志/事件/出口（本模块不做任何 repr/打印）。
#   - 构造（build_client）是纯配置组装：不 spawn 进程、不连网。stdio 的真实连接发生在会话 worker
#     （connect_client/connect_clients，group 6），连接失败只撤下该连接器、不阻断对话。
from ..models import MCPConnector
from .errors import ValidationError
from .registry_mcp import env_dict, headers_dict

# stdio 服务端必须由 MCPClient 以 stateful 连接持有（pydantic 校验强制），http 可无状态（每次调用独立会话，
# 服务端宕机时列表工具自撤、不拖垮整次对话——由 Toolkit 的 list_tools 容错承接）。
_TRANSPORT_STATEFUL = {"stdio": True, "http": False}


def is_mountable(conn: MCPConnector) -> bool:
    """运行门控：连接器须同时 enabled 与 trust 才算「可用」；否则归为停用/未就绪跳过。"""
    return bool(conn.enabled) and bool(conn.trust)


def build_client(conn: MCPConnector):
    """按一个（已通过 is_mountable 门控的）连接器配置构造 MCPClient（纯配置，无任何进程/网络副作用）。

    name 沿用连接器名（registry 已保证全局唯一）；env/headers 解密值直接喂给传输配置，
    调用方不得把返回对象打印进日志（env 在对象内，repr 可能外泄，审计事件只记名称/传输）。
    """
    if not is_mountable(conn):
        return None

    # 懒 import：agentscope 仅在真正装配运行时才需要，避免管理面进程（迁移/种子）背上重依赖。
    # 两个 Config 均为 pydantic 模型，此处只做字段装配；type 字段有默认值可不显式传。
    from agentscope.mcp import HttpMCPConfig, MCPClient, StdioMCPConfig

    transport = (conn.transport or "stdio").strip()
    if transport not in _TRANSPORT_STATEFUL:
        # 数据面已按白名单写入，此处防脏行误入运行时
        raise ValidationError(f"MCP 连接器「{conn.name}」传输类型非法：{transport!r}")

    env = env_dict(conn)  # 解密后的 {NAME: value}；空 → None（无环境变量则不带）
    if transport == "stdio":
        if not (conn.command or "").strip():
            raise ValidationError(f"MCP 连接器「{conn.name}」stdio 缺少 command")
        mcp_config = StdioMCPConfig(
            command=conn.command,
            args=list(conn.args or []),
            env=env or None,
        )
    else:  # http
        if not (conn.url or "").strip():
            raise ValidationError(f"MCP 连接器「{conn.name}」http 缺少 url")
        mcp_config = HttpMCPConfig(
            url=conn.url,
            headers=headers_dict(conn) or None,
        )

    return MCPClient(
        name=conn.name,
        is_stateful=_TRANSPORT_STATEFUL[transport],
        mcp_config=mcp_config,
    )


def build_clients(connectors: list[MCPConnector]) -> list:
    """批量构造：跳过停用/未信任（is_mountable=False）与构造失败的连接器，不抛错、不真拉起。

    供 build() 对 capability.load_mounted(task_id)['mcps'] 使用。
    """
    clients: list = []
    for conn in connectors:
        try:
            client = build_client(conn)
        except Exception:
            # 脏行/未知异常：撤下该连接器而非让整次对话不可用（与 Toolkit 对宕机 MCP 的容错一致）
            continue
        if client is not None:
            clients.append(client)
    return clients


async def connect_clients(clients: list) -> list:
    """连接 stateful（stdio）客户端；无状态（http）无需 connect 直接视为可用。

    返回真正连通的子集：任一连接失败（命令不存在/服务端拒连）只撤下该客户端并记 warning，
    绝不让单个坏连接器阻断运行。调用方把返回值接入 Toolkit。
    """
    import logging

    logger = logging.getLogger(__name__)
    ready: list = []
    for client in clients:
        if not client.is_stateful:
            ready.append(client)
            continue
        try:
            await client.connect()
            ready.append(client)
        except Exception as e:  # noqa: BLE001 —— 连接失败属预期分支（不存在命令/端口不通）
            logger.warning("MCP 连接器「%s」连接失败，本次运行撤下：%s", client.name, e)
    return ready


async def attach_to_toolkit(toolkit, client) -> None:
    """把已连接的 MCP 客户端挂进 Toolkit 的 basic 组，使后续 get_tool_schemas 能列出其工具。

    为什么需要这一步而不是在构造 Toolkit 时直接传 mcps：AgentScope 的 Toolkit.__init__ 强制要求
    stateful（stdio）客户端已连接（未连接直接 ValueError），而连接是异步、只能在会话 worker 做，
    故 build() 阶段无法把 stdio 客户端塞进 Toolkit——由会话在 connect_clients 后统一 attach。
    Toolkit.get_tool_schemas 每次调用实时遍历 group.mcps，run 首个模型输入之前 attach 即生效。
    """
    toolkit.tool_groups[0].mcps.append(client)


async def close_clients(clients: list) -> None:
    """teardown：按 LIFO 顺序 close 已连接客户端（先连的后关），单点失败不阻断后续关闭。"""
    for client in reversed(clients):
        try:
            await client.close()
        except Exception:  # noqa: BLE001 —— 清理路径尽力而为，失败只影响本次会话不复用
            pass
