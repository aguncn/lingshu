# 十二运维场景域种子（P9 scenario-templates，design D1/D3/D6）。
# 在应用初始化（create_app 建表后）幂等装载，职责三件：
#   1) 从 backend/prompts/scenarios/<domain>.md 装载十二域 ScenarioTemplate 行——只插入缺失域，
#      绝不覆盖既有行（.md 是唯一来源，改版走本文件 reseed() 显式比对覆盖，见 prompts/README.md）；
#   2) 以 (type,name) 幂等建少量「真实可挂载」的示例注册中心实体，供监控巡检/故障诊断两域 preset 引用；
#   3) 在「首次插入域行」时写入 preset_*（含示例 id），后续运行不触碰 preset（可能已被人为调整）。
# 为什么示例实体用 seed 而非写死迁移 SQL：注册中心实体是运行期动态 CRUD 数据（P5 已立），
# seed 只负责首落示例；用户可经 /api/mcp|skills|kb|experts 增删改，apply 对失效引用按跳过处理（design D3）。
from pathlib import Path

from sqlalchemy import select

from ..extensions import db
from ..models import (
    SCENARIO_DOMAINS,
    Expert,
    KnowledgeBase,
    MCPConnector,
    ScenarioTemplate,
    Skill,
)

# prompts/scenarios 目录：相对本模块定位（与运行 cwd 无关，避免迁移/测试在不同工作目录下漂移）
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "scenarios"


def _prompt_text(domain: str) -> str:
    """读该域 .md 原文并 strip；缺文件返回空串（调用方据此跳过该域，不插空模板）。"""
    path = _PROMPTS_DIR / f"{domain}.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _default_task_template(label: str) -> str:
    """最小任务引导：建任务/套用域时的预填文本，具体内容由用户在会话里澄清。"""
    return (
        f"围绕「{label}」场景开启一次运维任务：先澄清本次目标，"
        "再按该域准则推进并输出结构化结论。"
    )


def _ensure_entity(model, name: str, **fields):
    """按唯一 name 幂等取/建实体；flush 拿自增 id（不单独 commit，由调用方收口一次提交）。"""
    row = db.session.execute(
        select(model).where(model.name == name)
    ).scalar_one_or_none()
    if row is not None:
        return row
    obj = model(name=name, **fields)
    db.session.add(obj)
    db.session.flush()
    return obj


def _sample_ids() -> dict:
    """幂等建两域示例实体，返回 {domain: {"preset_*": [id,...]}} 供首次装载的域行引用。

    例：监控巡检 = 监控 MCP 连接器 + 巡检规范库 KB + 巡检报告 Skill；
        故障诊断 = SRE 专家 + 监控/日志/链路 三类 MCP 连接器。
    （实现决定：故障诊断预设除 design D6 的链路/日志外补挂监控连接器——按产品验收
    「监控+日志+链路 MCP + SRE 专家」；两域共用同一条 prometheus 示例连接器，preset 可跨域复用。）
    连接器均 http + trust=True：apply 判 enabled 即可挂载，trust 使示例能直接进 P8 运行时工具集。
    url 是占位地址，说明里已标注「按实际环境修改」。
    """
    skill_report = _ensure_entity(
        Skill,
        "巡检报告生成",
        description="把巡检指标与异常整理成结构化巡检报告",
        skill_md=(
            "# 巡检报告生成\n"
            "将监控巡检结果整理为结构化报告：巡检范围 → 指标概况 → 异常与疑似项 → 处置建议。\n"
            "异常项必须标注时间点与来源指标；未采集的指标如实标注「未采集」，不得编造。"
        ),
    )
    kb_inspect = _ensure_entity(
        KnowledgeBase,
        "巡检规范库",
        status="ready",  # ready=可检索；模型无 description 列，语义写进 name 已够
    )
    mcp_prom = _ensure_entity(
        MCPConnector,
        "prometheus-mcp",
        transport="http",
        url="http://prometheus:9090",  # 占位地址：仅示例，实际环境请改 url（模型无 description 列）
        trust=True,
    )
    expert_sre = _ensure_entity(
        Expert,
        "SRE值班专家",
        description="重大故障指挥与根因定位（示例）",
        role="ops-sme",
        system_prompt=(
            "你是「灵枢」的 SRE 值班专家，负责重大故障的指挥与根因定位。"
            "以假设-验证闭环推进：先形成可证伪的假设，再用日志/指标/链路证据逐一验证或排除；"
            "结论给出影响面、根因与处置建议；证据不足时如实标注不确定性，绝不臆断。"
        ),
    )
    mcp_trace = _ensure_entity(
        MCPConnector,
        "trace-mcp",
        transport="http",
        url="http://tracing:9411",  # 占位地址：调用链查询服务示例
        trust=True,
    )
    mcp_log = _ensure_entity(
        MCPConnector,
        "log-mcp",
        transport="http",
        url="http://log-aggregator:8080",  # 占位地址：集中日志检索服务示例
        trust=True,
    )
    return {
        "monitor-inspection": {
            "preset_skills": [skill_report.id],
            "preset_mcp": [mcp_prom.id],
            "preset_kb": [kb_inspect.id],
            "preset_expert": [],
        },
        "fault-diagnosis": {
            "preset_skills": [],
            # 监控/日志/链路 三连接器（监控 = prometheus-mcp，与监控巡检域共用示例）
            "preset_mcp": [mcp_prom.id, mcp_log.id, mcp_trace.id],
            "preset_kb": [],
            "preset_expert": [expert_sre.id],
        },
    }


def run_scenario_seed() -> None:
    """装载十二域 + 两域示例 preset。幂等：域行/实体缺失才插入，已存在一律跳过。"""
    sample = _sample_ids()  # 先确保示例实体存在并拿 id（preset 引用需要）
    for key, label in SCENARIO_DOMAINS:
        exists = db.session.execute(
            select(ScenarioTemplate).where(ScenarioTemplate.domain == key)
        ).scalar_one_or_none()
        if exists is not None:
            continue  # 已装载：绝不覆盖既有行（.md 改版走 reseed 显式流程）
        text = _prompt_text(key)
        if not text:
            continue  # 缺 .md（异常态）：跳过该域，避免落一条空 system_prompt
        presets = sample.get(key, {})
        db.session.add(
            ScenarioTemplate(
                domain=key,
                name=label,
                system_prompt=text,
                task_template=_default_task_template(label),
                preset_skills=presets.get("preset_skills", []),
                preset_mcp=presets.get("preset_mcp", []),
                preset_kb=presets.get("preset_kb", []),
                preset_expert=presets.get("preset_expert", []),
            )
        )
    db.session.commit()


def reseed(domains: list[str] | None = None) -> list[str]:
    """显式改版流程（prompts/scenarios/README.md）：用 .md 覆盖指定域（缺省=全部）的模板文本。

    只覆盖 system_prompt 与展示名，**不触碰 preset_***（可能已被人为调整）。返回被覆盖的域键。
    """
    label_by_key = {k: label for k, label in SCENARIO_DOMAINS}
    targets = domains or list(label_by_key)
    updated: list[str] = []
    for key in targets:
        row = db.session.execute(
            select(ScenarioTemplate).where(ScenarioTemplate.domain == key)
        ).scalar_one_or_none()
        if row is None:
            continue
        text = _prompt_text(key)
        if not text:
            continue
        row.system_prompt = text
        if key in label_by_key:
            row.name = label_by_key[key]
        updated.append(key)
    db.session.commit()
    return updated
