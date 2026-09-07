# 运维专家档案种子（C5 expert-profile）：在应用初始化（create_app 建表/迁移后）幂等装载。
# 职责：
#   1) 确保少数「真实可挂载」的示例能力实体存在（MCP 示例连接器 + 巡检报告技能；
#      safe-shell/sql-analysis 技能、ops-knowledge 知识库已在 0003 迁移落库，按 name 复用）；
#   2) 确保一份开箱「SRE 值班专家」档案存在（role=ops-sme、原 SRE 人设、preset 指向上述示例），
#      新建任务对话框/运维专家页立即有可套用的样例。
# 为什么示例实体放 seed 而非写死迁移 SQL：注册中心实体是运行期动态 CRUD 数据（P5 已立），
# seed 只负责首落示例；用户可经 /api/experts|skills|mcps|kb 增删改，套用对失效引用按跳过处理。
# 收敛而非覆盖：档案行若已存在（早期旧版专家种子可能建过同名「SRE 值班专家」），只在预设
# 仍为空时回填规范值，绝不覆盖用户后续人工调整（沿用旧种子既有语义）。
from sqlalchemy import select

from ..extensions import db
from ..models import Expert, KnowledgeBase, MCPConnector, Skill

# 档案里引用但迁移/示例实体缺省时，seed 需确保的最小示例集合。url 为占位地址，仅示例。
# （safe-shell/sql-analysis 技能、ops-knowledge 知识库由 0003 迁移提供，无需在此再造。）
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


def _example_ids() -> dict:
    """幂等确保示例实体存在，返回 {skills:[..], mcps:[..], kbs:[..]} 供档案预设引用。"""
    skill_report = _ensure_entity(
        Skill,
        "巡检报告生成",
        description="把巡检指标与异常整理成结构化巡检报告",
        skill_md=(
            "# 巡检报告生成\n"
            "将巡检结果整理为结构化报告：巡检范围 → 指标概况 → 异常与疑似项 → 处置建议。\n"
            "异常项必须标注时间点与来源指标；未采集的指标如实标注「未采集」，不得编造。"
        ),
    )
    safe_shell = db.session.execute(
        select(Skill).where(Skill.name == "safe-shell")
    ).scalar_one_or_none()
    mcp_prom = _ensure_entity(
        MCPConnector,
        "prometheus-mcp",
        transport="http",
        url="http://prometheus:9090",  # 占位地址：仅示例，实际环境请改 url
        trust=True,
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
    kb_inspect = _ensure_entity(
        KnowledgeBase, "巡检规范库", status="ready"  # ready=可检索
    )
    kb_ops = db.session.execute(
        select(KnowledgeBase).where(KnowledgeBase.name == "ops-knowledge")
    ).scalar_one_or_none()
    return {
        "skills": [s.id for s in (skill_report, safe_shell) if s is not None],
        "mcps": [mcp_prom.id, mcp_log.id, mcp_trace.id],
        "kbs": [k.id for k in (kb_inspect, kb_ops) if k is not None],
    }


def run_profile_seed() -> None:
    """装载开箱 SRE 值班专家档案 + 其预设引用的示例实体。幂等：缺失才建、已存在仅回填空预设。"""
    ids = _example_ids()  # 先确保示例实体存在并拿 id（preset 引用需要）
    expert = db.session.execute(
        select(Expert).where(Expert.name == "SRE 值班专家")
    ).scalar_one_or_none()
    if expert is None:
        db.session.add(
            Expert(
                name="SRE 值班专家",
                description="重大故障指挥与根因定位（示例档案）",
                system_prompt=(
                    "你是「灵枢」的 SRE 值班专家，负责重大故障的指挥与根因定位。"
                    "以假设-验证闭环推进：先形成可证伪的假设，再用日志/指标/链路证据逐一验证或排除；"
                    "结论给出影响面、根因与处置建议；证据不足时如实标注不确定性，绝不臆断。"
                ),
                role="ops-sme",
                preset_skills=ids["skills"],
                preset_mcp=ids["mcps"],
                preset_kb=ids["kbs"],
                preset_library=[],
                enabled=True,
            )
        )
    else:
        # 已存在（早期旧版专家种子可能建过同名行）：仅当档案预设仍为空才回填规范值，
        # 已有人工调整的预设绝不覆盖（保持幂等 + 尊重用户）。
        if not (expert.preset_skills or []):
            expert.preset_skills = ids["skills"]
        if not (expert.preset_mcp or []):
            expert.preset_mcp = ids["mcps"]
        if not (expert.preset_kb or []):
            expert.preset_kb = ids["kbs"]
        if expert.preset_library is None:
            expert.preset_library = []
    db.session.commit()
