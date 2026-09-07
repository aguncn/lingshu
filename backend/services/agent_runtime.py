# Agent 运行时装配服务（P8 agentscope-runtime，design D3）：把「任务 + 已绑定模型 + 挂载能力」组装成一个可对话的 Agent。
# build() 是纯同步装配（不连网、不 spawn、不碰模型输入）；唯一落盘副作用 = 建任务沙箱目录（C2）：
#   - 读任务与空间上下文 → 按序拼 system_prompt：专家人设（单专家，覆盖默认角色）或基础运维人设
#     → 当前任务上下文 + 工作目录（技能不再常驻注入——skill-kb-callable 改为只读工具按需取用）；
#   - Toolkit = 内置工具（Bash/Read/Write/Edit/Glob/Grep；Windows 加 PowerShell）
#     + 每个「挂载且启用且 skill_md 非空」的技能一个只读 skill_<slug> 工具
#     + 一只读 knowledge_search 检索工具（覆盖任务挂载且 ready 的知识库，跨库关键词检索）
#     + 挂载且「可用」的 MCP：http 无状态客户端直接进 Toolkit，stdio（须 stateful、需异步 connect）
#     归为 deferred 由会话 worker 连接后 attach（mcp_client.attach_to_toolkit）；
#   - 停用/未就绪的挂载实体一律跳过，绝不让某个坏挂载阻断整次装配。
# 模型解析失败（无绑定/无密钥）直接抛可读 AppError——由端点在 SSE 首事件转为 error。
import re as _re
import sys

from . import capability, mcp_client, model_factory
from .task_service import get_task_or_raise

# 基础运维助手人设。仅当任务未挂载可用运维专家时使用；挂载了专家则其 system_prompt 覆盖本段角色
#（design D3「专家优先于基础人设的角色部分」，任务上下文段仍保留在后；技能不注入提示，见下）。
BASE_SYSTEM_PROMPT = (
    "你是「灵枢」IT 运维智能体。在运维场景中协助排查故障、执行变更、核对日志与配置。"
    "回答保持简洁、步骤可执行；涉及系统改动或写文件前先说明影响。你只能使用提供的工具完成操作。"
)

# 内置工具（agentscope.tool）。Bash/Write/Edit 属写/执行类，二次确认接法见任务组 5。
_BUILTIN_TOOL_NAMES = ("Bash", "Read", "Write", "Edit", "Glob", "Grep")

# —— task-permission-modes：任务级权限模式 ↔ AgentScope PermissionMode/规则 ——
# 三种任务的取值白名单在 models.TASK_PERMISSION_MODES 集中；Agent 装配在此按任务值选档：
#   strict   严格：全部写/执行类二次确认（对应 DEFAULT，与旧行为逐字一致）
#   limited  有限：只读与一般命令自动放行，仅「Write/Edit 修改 + 命令里的删除/覆盖」仍需确认
#   trusted  完全信任：全程无人工确认（BYPASS）
# 为什么 limited/trusted 用 BYPASS 而非「DEFAULT+allow 规则」：要表达「一般命令自动放行」只能反向
#   枚举「少数危险的需确认」，无法正向穷举安全命令；BYPASS 恰好默认全放、仅命中的 ask 规则才确认。
# 由此带来的边界（记录于此并同步到前端文案/spec）：BYPASS 会跳过工具自带的 bypass-immune 安全 ASK
#   （如 Bash 的 rm -rf /、写 ~/.bashrc、命令注入特征），故这两档以「信任模型行为」为前提；写库/越权等
#   兜底由系统提示约束承担，不逐条打断。仍保留：工具自身 DENY、用户 ask/deny 规则（本表即 ask 规则）。
# limited 档「删除/覆盖」靠命令子串判定（见下表），无法命中 Bash 的内联改写（echo > file、curl -o 等）
#   与 PowerShell 的大小写/别名等价写法，属启发式边界而非精确分类——命中则多问一次（安全向），漏判则少问一次。
_LIMITED_DANGEROUS_SUBSTRINGS: dict[str, tuple[str, ...]] = {
    # Bash：匹配规则=子串（Bash.match_rule 无通配即 substring）；含删除与覆盖常用命令。
    "Bash": ("rm ", "rmdir ", "unlink ", "shred ", "mv ", "cp ", "sed -i"),
    # PowerShell：仅当工具具备子串 match_rule 时才命中（见 _builtin_tools 内 _AskablePowerShell 子类）
    "PowerShell": (
        "remove-item", "remove-", "remove ", "del ", "erase ", "rd ", "rmdir ",
        "move-item", "copy-item", "set-content", "clear-content", "out-file", "ren ",
    ),
}


def _permission_context_for(mode_key: str | None):
    """按任务 permission_mode 构造 AgentState 用的 PermissionContext（纯函数，可单测）。

    strict/未知值兜底 DEFAULT（最严，逐字对齐旧行为）；trusted=BYPASS 全放；
    limited=BYPASS + 少量 ask 规则（Write/Edit 全量 + 命令工具的删除/覆盖子串）。"""
    from agentscope.permission import (
        PermissionBehavior,
        PermissionContext,
        PermissionMode,
        PermissionRule,
    )

    key = (mode_key or "strict").strip()
    if key == "trusted":
        return PermissionContext(mode=PermissionMode.BYPASS)
    if key == "limited":
        ctx = PermissionContext(mode=PermissionMode.BYPASS)

        def _ask(tool: str, content: str | None) -> None:
            rule = PermissionRule(
                tool_name=tool,
                rule_content=content,
                behavior=PermissionBehavior.ASK,
                source="task-permission-mode",
            )
            ctx.ask_rules.setdefault(tool, []).append(rule)

        # 修改/新建本地文件：Write/Edit 走工具级确认（rule_content="" 在引擎短路匹配一切）
        _ask("Write", "")
        _ask("Edit", "")
        # 命令工具的删除/覆盖类：逐条子串 ask（匹配逻辑委托各工具的 match_rule）
        for tool, subs in _LIMITED_DANGEROUS_SUBSTRINGS.items():
            for sub in subs:
                _ask(tool, sub)
        return ctx
    return PermissionContext(mode=PermissionMode.DEFAULT)


# PowerShell 的「命令内容可确认」最小子类，惰性建类并缓存（避免模块顶层拉 agentscope.tool）：
# 原 PowerShell 不实现 match_rule（基类只支持工具名级，见 _AskablePowerShell.match_rule 覆写），
# limited 档的「删除命令确认」规则若按工具名匹配会误伤所有命令，按命令内容则无法命中——故补子串匹配。
_ASKABLE_POWERSHELL_CLS = None


def _askable_powershell_cls():
    """取回（必要时惰性构造）_AskablePowerShell 类；_builtin_tools 与单测共用。"""
    global _ASKABLE_POWERSHELL_CLS
    if _ASKABLE_POWERSHELL_CLS is None:
        from agentscope.tool import PowerShell

        class _AskablePowerShell(PowerShell):
            async def match_rule(self, rule_content, tool_input):  # noqa: D102 —— 覆写以支持命令内容规则
                if not rule_content:
                    return True
                command = (tool_input or {}).get("command", "") or ""
                return rule_content.lower() in str(command).lower()

        _ASKABLE_POWERSHELL_CLS = _AskablePowerShell
    return _ASKABLE_POWERSHELL_CLS


def _builtin_tools(cwd=None) -> list:
    """装配内置工具实例；Windows 运行环境追加 PowerShell（Bash 未必存在，双写类等价可用）。

    cwd：任务沙箱工作目录（C2）。传给 Bash/PowerShell 使其命令进程在该目录下执行，
    相对路径即相对工作目录；Read/Write/Edit 仍要求绝对路径，不随 cwd 改变（软沙箱），
    越界写仍由 permission_mode 的二次确认闸门兜底。None = 回落进程 cwd（旧行为）。
    """
    from agentscope.tool import Bash, Edit, Glob, Grep, Read, Write

    tools = [Bash(cwd=cwd), Read(), Write(), Edit(), Glob(), Grep()]
    if sys.platform.startswith("win"):
        tools.append(_askable_powershell_cls()(cwd=cwd))
    return tools


def _task_context_block(task, workdir: str | None = None) -> str:
    """任务上下文段：标题/空间/类型 + 工作目录，让 Agent 明白正在为哪个任务工作、
    生成文件的落盘根在哪（C2 沙箱）。workdir 传任务目录绝对路径；缺失则不注入该段。
    """
    space_name = None
    try:
        space = getattr(task, "space", None)
        space_name = space.name if space is not None else None
    except Exception:  # noqa: BLE001 —— 空间信息缺失不阻断装配（仅上下文里少一行）
        pass
    lines = [f"- 标题：{task.title}", f"- 类型：{task.task_type}"]
    if space_name:
        lines.append(f"- 所属空间：{space_name}")
    block = "## 当前任务\n" + "\n".join(lines)
    if workdir:
        block += (
            f"\n- 工作目录：{workdir}"
            "\n\n请把本任务生成或修改的文件都放到上述工作目录里：用 Read/Write/Edit 时给出其中的绝对路径；"
            "Bash/PowerShell 命令已在该目录下执行，相对路径即相对工作目录。"
        )
    return block


# —— skill-kb-callable：技能由「常驻指令注入」改「按需取用的只读技能工具」——
# 技能名是人类可读串（中文/含空格），不能直接作工具名（工具名须 [A-Za-z0-9_-]）。
# 归一化：ASCII 小写 + 非法字符折叠为单下划线；空/与已用名冲突 → 回退 `skill_<id>` 保证唯一合法。
_SLUG_KEEP = _re.compile(r"[^a-z0-9_-]+")
_SLUG_COLLAPSE = _re.compile(r"_+")
_SLUG_MAX = 40  # slug 截断上限（保证工具名不至于过长）
_SKILL_TOOL_PREFIX = "skill_"
_KB_SEARCH_TOOL = "knowledge_search"
_KB_TOP_K_DEFAULT = 5
_KB_TOP_K_MAX = 10


def _skill_slug(name: str) -> str:
    """技能名 → ASCII 小写 slug（仅作工具名基座；空串表示无法归一化）。"""
    s = _SLUG_KEEP.sub("_", (name or "").strip().lower())
    return _SLUG_COLLAPSE.sub("_", s).strip("_")[:_SLUG_MAX]


def _skill_tool_name(skill_id: int, skill_name: str, reserved: set) -> str:
    """生成唯一合法技能工具名：slug 归一化成功且未占用则用，否则回退 skill_<id>。"""
    base = _skill_slug(skill_name)
    candidate = f"{_SKILL_TOOL_PREFIX}{base}" if base else ""
    if candidate and candidate not in reserved:
        return candidate
    return f"{_SKILL_TOOL_PREFIX}{skill_id}"


def _usable_skills(skills) -> list:
    """装配判据（沿用既有门控）：挂载 且 技能 enabled 且 skill_md 非空。"""
    return [s for s in skills if s.enabled and (s.skill_md or "").strip()]


def _skill_tool(skill, tool_name: str):
    """一个可用技能 = 一只读 FunctionTool：调用返回完整分步指令文本。

    描述含人类可读技能名与用途——这是模型「发现面」：技能不再常驻系统提示，
    由 Agent 判断任务相关时调用取回指令再执行（spec 任务挂载能力注入 R4）。
    只读标记是权限闸门：漏标会在 strict 档触发二次确认（test 1.2 有回归护栏）。
    """
    from agentscope.tool import FunctionTool

    purpose = (skill.description or "").strip() or "该技能提供某类运维任务的分步操作指引"
    doc = (skill.skill_md or "").strip()

    def _fetch() -> str:
        return doc

    return FunctionTool(
        _fetch,
        name=tool_name,
        description=f"技能「{skill.name}」：{purpose}。调用返回该技能完整分步操作指引，供你按步骤执行。",
        input_schema={"type": "object", "properties": {}},
        is_read_only=True,
    )


def _kb_search_tool(kb_ids: list):
    """知识库检索只读工具：闭包快照「任务挂载且 ready」的库 id（build 时定格，见 D5 装配快照）。

    检索复用 registry_kb 既有关键词计分（search_kbs 跨库归并），不引向量库；结果带来源
    （库/文件 第n块 得分）供模型引用。无 query / 无可用库 / 无命中 → 明确文本，绝不抛错。
    """
    from agentscope.tool import FunctionTool

    from . import registry_kb

    snapshot = [int(kid) for kid in kb_ids]

    def _search(query: str = "", top_k: int = None) -> str:
        q = (query or "").strip()
        if not q:
            return "未提供检索关键词：请给出要检索的问题或关键词（query）。"
        if not snapshot:
            return "本任务未挂载可用的知识库，无法检索（可在任务能力中挂载已就绪知识库）。"
        # top_k 越界收敛到 [1, 10]，非法值回落默认 5（服务端既有口径同源）
        try:
            limit = int(top_k) if top_k is not None else _KB_TOP_K_DEFAULT
        except (TypeError, ValueError):
            limit = _KB_TOP_K_DEFAULT
        limit = max(1, min(limit, _KB_TOP_K_MAX))
        hits = registry_kb.search_kbs(snapshot, q, limit)
        if not hits:
            return "在已挂载知识库中未命中相关内容。"
        lines = []
        for h in hits:
            kb_name = h.get("kb_name") or f"库{h.get('kb_id')}"
            filename = h.get("filename") or "-"
            chunk_index = h.get("chunk_index")
            block_no = (chunk_index + 1) if isinstance(chunk_index, int) else chunk_index
            lines.append(
                f"[来源: {kb_name}/{filename} 第{block_no}块 得分{h.get('score')}] "
                f"{h.get('content') or ''}"
            )
        return "\n\n".join(lines)

    return FunctionTool(
        _search,
        name=_KB_SEARCH_TOOL,
        description=(
            "在「当前任务已挂载且可用的知识库」中做关键词检索（覆盖任务挂载的全部可用库）。"
            "入参 query 必填（自然语言问题或关键词）；top_k 可选，默认 5、上限 10。"
            "返回带来源（库/文件名/块序/得分）的文本块；引用资料时请标注其来源。"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "要检索的问题或关键词"},
                "top_k": {
                    "type": "integer", "description": "返回条数（1-10，默认 5）",
                },
            },
            "required": ["query"],
        },
        is_read_only=True,
    )


def _persona_text(expert, snapshot) -> str | None:
    """单个挂载专家的人设文本：挂载快照优先，无快照回退实时档案（旧行兼容）。

    快照语义（C5）：挂载动作已把该专家的人设定格到 task_expert.persona_snapshot，
    此后改/停用档案不影响已建任务——故只要快照非空就采快照，不再看实时 enabled/system_prompt。
    快照为空（0010 之前挂载的旧行，或挂载时专家即停用/空人设 → 落库为 NULL）才回退实时判定，
    且回退仍须 enabled+非空（停用专家不得借回退漏进来，维持旧 disabled 过滤语义）。
    """
    if snapshot:
        return snapshot
    if expert.enabled and (expert.system_prompt or "").strip():
        return expert.system_prompt.strip()
    return None


def _compose_system_prompt(task, experts, workdir=None, personas=None) -> tuple[str, list]:
    """按序拼 system_prompt，返回 (prompt, 使用的专家名)。

    skill-kb-callable：技能不再常驻注入（原技能指令段移除）——技能改以只读工具形态按需取用
    （见 _skill_tool / build），故系统提示只含 角色（挂载的运维专家/基础人设）+ 任务上下文，
    技能指令不进提示。模板注入已随 C5 移除：不再有模板提示词前置或统一约束收尾，
    人设来源 = 任务挂载的运维专家（personas 快照命中者优先，第一个有人设者胜出），无则回退 BASE。
    """
    personas = personas or {}
    chosen = None
    used_experts: list = []
    for e in experts:
        text = _persona_text(e, personas.get(e.id))
        if text:
            chosen, used_experts = text, [e.name]
            break

    parts = [
        chosen if chosen is not None else BASE_SYSTEM_PROMPT,
        "",
        _task_context_block(task, workdir),
    ]
    prompt = "\n".join(parts)
    return prompt, used_experts


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


def _task_workdir(task) -> str:
    """任务沙箱工作目录（C2）= data/spaces/<space>/<task>/ 的绝对路径，不存在则幂等创建。

    build 恒在应用上下文内被调（ChatSession.create 于请求线程，测试各有 app ctx），
    current_app 必可用。建目录失败是真实 IO 错误，向上抛由端点转 SSE error——而非静默
    回落到进程 cwd 继续在仓库根制造散落文件（正是本改动要消除的现象）。"""
    from . import file_store

    return str(file_store.ensure_task_dir(task.space_id, task.id))


def _persona_snapshots(task_id: int) -> dict:
    """读任务挂载专家的 persona_snapshot → {expert_id: text}（C5 快照语义）。

    仅收录快照非空的行：0010 前挂载的旧行或挂载时即停用/空人设（落库 NULL）不在此映射，
    交由 _compose_system_prompt 的实时 enabled 回退判定，两类场景语义一致。
    """
    from sqlalchemy import select

    from ..extensions import db
    from ..models import TaskExpert

    rows = db.session.execute(
        select(TaskExpert).where(TaskExpert.task_id == task_id)
    ).scalars()
    return {
        te.expert_id: te.persona_snapshot.strip()
        for te in rows
        if te.expert_id is not None
        and te.persona_snapshot is not None
        and te.persona_snapshot.strip()
    }


def build(task_id: int, *, clients=None) -> tuple:
    """组一个可对话 Agent：返回 (agent, 描述 dict)。clients 可注入（测试打桩 MCP 用）。

    描述 dict 供审计/会话/测试断言：含模型展示标签（无密钥）、装配快照的技能（human 名）/
    技能工具清单 skill_tools / 检索工具是否装配、专家名、MCP 客户端元信息（name/transport +
    所处状态 live|deferred|skipped，密钥值永不出现）、沙箱工作目录 workdir。
    带下划线前缀的键（_deferred）内嵌待连接客户端对象，仅供内部会话消费，不属于对外序列化面。
    """
    from agentscope.agent import Agent
    from agentscope.state import AgentState
    from agentscope.tool import Toolkit

    task = get_task_or_raise(task_id)  # 任务不存在 → 404（可读）
    # C2 沙箱：先建任务工作目录并取绝对路径——Bash/PowerShell 进程 cwd 收敛其中、提示注入声明。
    workdir = _task_workdir(task)
    model, label = model_factory.resolve_model(task_id)  # 无绑定/无密钥 → 可读错

    mounted = capability.load_mounted(task.id)  # {skills,mcps,kbs,experts} ORM 对象
    # 人设 = 任务挂载运维专家（挂载快照 persona_snapshot 优先，旧行回退实时档案）；
    # 无挂载/带空人设回退 BASE（模板注入已随 C5 移除）。
    system_prompt, expert_names = _compose_system_prompt(
        task,
        mounted["experts"],
        workdir=workdir,
        personas=_persona_snapshots(task.id),
    )

    # MCP：默认按挂载+可用门控从库装配；测试可注入整块 mock 客户端（task 3.2 允许）
    if clients is None:
        clients = mcp_client.build_clients(mounted["mcps"])
    connectable, deferred = _split_mcp(clients)

    # skill-kb-callable：可用技能 → 只读 skill_<slug> 工具；就绪知识库 → 只读 knowledge_search 工具。
    # 装配即快照（design D5）：tools 与检索语料闭包在 build 时定格，运行中改挂载只影响之后新 run。
    # reserved 收敛工具名：内置工具名 + 已占用技能 slug + 检索工具名，冲突技能回退 skill_<id> 保证唯一合法。
    reserved = set(_BUILTIN_TOOL_NAMES) | {_KB_SEARCH_TOOL}
    if sys.platform.startswith("win"):
        reserved.add("PowerShell")
    reserved |= {c.name for c in connectable}
    usable = _usable_skills(mounted["skills"])
    skill_tools = []
    skill_tool_names = []
    for skill in usable:
        tool_name = _skill_tool_name(skill.id, skill.name, reserved)
        reserved.add(tool_name)
        skill_tools.append(_skill_tool(skill, tool_name))
        skill_tool_names.append({"name": tool_name, "skill_name": skill.name})
    # 知识库：挂载且 status=='ready' 视为可用 → 进检索语料快照；draft/disabled/不存在不阻塞装配
    ready_kb_ids = [
        kb.id for kb in mounted["kbs"] if kb.status == "ready"
    ]
    kb_tool = _kb_search_tool(ready_kb_ids)

    toolkit = Toolkit(
        tools=_builtin_tools(cwd=workdir) + skill_tools + [kb_tool],
        mcps=connectable,
    )
    # 危险工具二次确认（task 5.1/5.2 + task-permission-modes）：按任务 permission_mode 选档构造上下文。
    # DEFAULT（strict）下内置写/执行类工具被请求即产 RequireUserConfirmEvent、未放行绝不执行；
    # limited/trusted 映射到 BYPASS+规则（见 _permission_context_for）。显式传 state 而非靠 Agent 默认，
    # 防 AgentScope 默认漂移；每次 chat 重新 build，故运行中改档只影响后续运行。
    state = AgentState(permission_context=_permission_context_for(task.permission_mode))
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
        "workdir": workdir,  # C2 沙箱目录绝对路径（该次运行的进程 cwd 与提示声明）
        "permission_mode": task.permission_mode,  # 本次运行生效的权限档（装配即快照）
        "model": label,  # {provider_id/provider/model/base_url}，无 api_key
        # skill-kb-callable：技能不再注入提示，skills=可调用技能 human 名清单（装配即快照）；
        # skill_tools=技能工具清单（内部名/技能名）供前端「已装配」弱化标记与调试核对。
        "skills": [s.name for s in usable],
        "skill_tools": skill_tool_names,
        "kb_search": bool(ready_kb_ids),  # knowledge_search 是否携带可用语料（工具始终装配）
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
