# Agent 运行时装配服务（P8 agentscope-runtime，design D3）：把「任务 + 已绑定模型 + 挂载能力」组装成一个可对话的 Agent。
# build() 是纯同步装配（不连网、不 spawn、不碰模型输入）：
#   - 读任务与空间上下文 → 按序拼 system_prompt：专家人设（单专家，覆盖默认角色）或基础运维人设
#     → 当前任务上下文 → 挂载且启用的技能 skill_md 指令段（知识库检索留 P9）；
#   - Toolkit = 内置工具（Bash/Read/Write/Edit/Glob/Grep；Windows 加 PowerShell）
#     + 挂载且「可用」的 MCP：http 无状态客户端直接进 Toolkit，stdio（须 stateful、需异步 connect）
#     归为 deferred 由会话 worker 连接后 attach（mcp_client.attach_to_toolkit）；
#   - 停用/未信任的挂载实体一律跳过，绝不让某个坏挂载阻断整次装配。
# 模型解析失败（无绑定/无密钥）直接抛可读 AppError——由端点在 SSE 首事件转为 error。
import sys

from . import capability, mcp_client, model_factory
from .task_service import get_task_or_raise

# 基础运维助手人设。仅当任务未挂载可用专家时使用；挂载了单专家则其 system_prompt 覆盖本段角色
#（design D3「专家优先于基础人设的角色部分」，任务上下文与技能段仍保留在后）。
BASE_SYSTEM_PROMPT = (
    "你是「灵枢」IT 运维智能体。在运维场景中协助排查故障、执行变更、核对日志与配置。"
    "回答保持简洁、步骤可执行；涉及系统改动或写文件前先说明影响。你只能使用提供的工具完成操作。"
)

# 内置工具（agentscope.tool）。Bash/Write/Edit 属写/执行类，二次确认接法见任务组 5。
_BUILTIN_TOOL_NAMES = ("Bash", "Read", "Write", "Edit", "Glob", "Grep")


def _builtin_tools() -> list:
    """装配内置工具实例；Windows 运行环境追加 PowerShell（Bash 未必存在，双写类等价可用）。"""
    from agentscope.tool import Bash, Edit, Glob, Grep, PowerShell, Read, Write

    tools = [Bash(), Read(), Write(), Edit(), Glob(), Grep()]
    if sys.platform.startswith("win"):
        tools.append(PowerShell())
    return tools


def _task_context_block(task) -> str:
    """任务上下文段：标题/空间/类型，让 Agent 明白正在为哪个任务工作。"""
    space_name = None
    try:
        space = getattr(task, "space", None)
        space_name = space.name if space is not None else None
    except Exception:  # noqa: BLE001 —— 空间信息缺失不阻断装配（仅上下文里少一行）
        pass
    lines = [f"- 标题：{task.title}", f"- 类型：{task.task_type}"]
    if space_name:
        lines.append(f"- 所属空间：{space_name}")
    return "## 当前任务\n" + "\n".join(lines)


def _skills_block(skills) -> str:
    """挂载且启用技能 → 指令段（v0.3 语义：技能=SKILL.md 全文注入，Agent 须遵循）。"""
    blocks = []
    for skill in skills:
        # 只注入 enabled 且有指令文本的技能；停用/空文本视为未就绪跳过
        if not skill.enabled or not (skill.skill_md or "").strip():
            continue
        blocks.append(
            f"<skill name=\"{skill.name}\">\n{skill.skill_md.strip()}\n</skill>"
        )
    if not blocks:
        return ""
    return "## 可遵循技能指令\n" + "\n\n".join(blocks)


def _expert_role(expert) -> str:
    """单专家人设：取第一个挂载且启用、带 system_prompt 的专家作为角色覆盖段。"""
    if expert is None:
        return BASE_SYSTEM_PROMPT
    text = (expert.system_prompt or "").strip()
    return text or BASE_SYSTEM_PROMPT


def _compose_system_prompt(task, skills, experts) -> tuple[str, list, list]:
    """按序拼 system_prompt，返回 (prompt, 注入技能名, 注入专家名)。"""
    expert = next(
        (e for e in experts if e.enabled and (e.system_prompt or "").strip()),
        None,
    )
    used_experts = [expert.name] if expert is not None else []
    skill_texts = [s for s in skills if s.enabled and (s.skill_md or "").strip()]
    used_skills = [s.name for s in skill_texts]

    parts = [
        _expert_role(expert),
        "",
        _task_context_block(task),
    ]
    skills_part = _skills_block(skill_texts)
    if skills_part:
        parts.append(skills_part)
    return "\n".join(parts), used_skills, used_experts


def _split_mcp(clients: list) -> tuple[list, list]:
    """把装配出的 MCP 客户端分为「可直接进 Toolkit」与「deferred（待会话连接）」。

    AgentScope 的 Toolkit.__init__ 强制 stateful（stdio）客户端已连接，未连接直接 ValueError；
    而连接是异步的、只能在会话 worker 做（design D7）。故 http 无状态客户端直接注册进 Toolkit，
    stdio 客户端进入 desc['_deferred']，由会话 connect 成功后 attach（见 group 6 驱动）。
    """
    connectable: list = []
    deferred: list = []
    for client in clients:
        if not client.is_stateful or client.is_connected:
            connectable.append(client)
        else:
            deferred.append(client)
    return connectable, deferred


def build(task_id: int, *, clients=None) -> tuple:
    """组一个可对话 Agent：返回 (agent, 描述 dict)。clients 可注入（测试打桩 MCP 用）。

    描述 dict 供审计/会话/测试断言：含模型展示标签（无密钥）、注入技能/专家名、MCP 客户端
    元信息（name/transport + 所处状态 live|deferred|skipped，密钥值永不出现）。带下划线前缀的
    键（_deferred）内嵌待连接客户端对象，仅供内部会话消费，不属于对外序列化面。
    """
    from agentscope.agent import Agent
    from agentscope.permission import PermissionContext, PermissionMode
    from agentscope.state import AgentState
    from agentscope.tool import Toolkit

    task = get_task_or_raise(task_id)  # 任务不存在 → 404（可读）
    model, label = model_factory.resolve_model(task_id)  # 无绑定/无密钥 → 可读错

    mounted = capability.load_mounted(task.id)  # {skills,mcps,kbs,experts} ORM 对象
    system_prompt, skill_names, expert_names = _compose_system_prompt(
        task, mounted["skills"], mounted["experts"]
    )

    # MCP：默认按挂载+可用门控从库装配；测试可注入整块 mock 客户端（task 3.2 允许）
    if clients is None:
        clients = mcp_client.build_clients(mounted["mcps"])
    connectable, deferred = _split_mcp(clients)

    toolkit = Toolkit(tools=_builtin_tools(), mcps=connectable)
    # 危险工具二次确认（task 5.1/5.2，design D5）：默认置 PermissionMode.DEFAULT ——
    # 该模式下内置写/执行类工具（Bash/Write/Edit）被请求时自动产出 RequireUserConfirmEvent、
    # 未放行绝不执行（拒绝结果由驱动以 UserConfirmResultEvent 喂回 Agent）；只读工具与只读命令走快速通道。
    # 为什么显式传 state 而非靠 Agent 默认：DEFAULT 是当前默认值，显式置位防 AgentScope 默认漂移。
    state = AgentState(permission_context=PermissionContext(mode=PermissionMode.DEFAULT))
    agent = Agent(
        name=f"task-{task.id}",
        system_prompt=system_prompt,
        model=model,
        toolkit=toolkit,
        state=state,
    )

    # 装配面元信息（对外，无密钥）
    mcp_meta = []
    for c in connectable:
        transport = c.mcp_config.type if hasattr(c, "mcp_config") else "http"
        mcp_meta.append({"name": c.name, "transport": transport, "state": "live"})
    for c in deferred:
        transport = c.mcp_config.type if hasattr(c, "mcp_config") else "stdio"
        mcp_meta.append({"name": c.name, "transport": transport, "state": "deferred"})
    # 挂载了但被门控跳过（停用/未信任）的连接器：仅记名，便于核对「停用实体不出现」
    skipped = [
        {"name": c.name, "state": "skipped"}
        for c in mounted["mcps"]
        if not (mcp_client.is_mountable(c))
    ]

    desc = {
        "task_id": task.id,
        "agent": agent.name,
        "model": label,  # {provider_id/provider/model/base_url}，无 api_key
        "skills": skill_names,
        "experts": expert_names,
        "builtin_tools": list(_BUILTIN_TOOL_NAMES)
        + (["PowerShell"] if sys.platform.startswith("win") else []),
        "mcps": mcp_meta + skipped,
        "_deferred": deferred,  # 内部：待会话连接并 attach 的 stdio 客户端（非序列化面）
    }
    return agent, desc


def require_deferred_clients(desc: dict) -> list:
    """从描述 dict 取出待连接的 stdio MCP 客户端（会话 worker 用，隔离下划线键语义）。"""
    return desc.pop("_deferred", [])
