# 场景域服务（P9 scenario-templates，design D2/D4/D7）：列表/单查 + 选域套用预设装配。
# 分层对齐 CLAUDE.md §3：校验与事务在 service，API 只转发。
# 核心语义：
#   - 列表固定按 SCENARIO_DOMAINS 序（§8 表自上而下），只给装配摘要，不给 system_prompt 全文；
#   - 套用 = 校验域 → 置 task.scenario_domain → 把 preset id「求交现存且可用实体」后复用 P4 caps
#     全量覆盖写挂载（PUT /api/tasks/<id>/caps 的既有规则）；失效引用跳过而非失败（design D3），
#     响应给装配汇总（成功挂载分类 + 被跳过引用项）。
#   - 复用 capability.set_task_caps 而非自建写逻辑：保持「模板装配 + PUT caps 人工微调」同一存储面。
from sqlalchemy import select

from ..extensions import db
from ..models import (
    SCENARIO_DOMAINS,
    SCENARIO_KEYS,
    Expert,
    KnowledgeBase,
    MCPConnector,
    ScenarioTemplate,
    Skill,
)
from . import capability
from .errors import NotFoundError, ValidationError
from .task_service import get_task_or_raise

# 预设引用 -> 「现存且可用」的过滤谓词。四类“可用”口径与 P4/注册中心一致：
# skill/mcp/expert 看 enabled，知识库没有 enabled、以 status=='ready' 表示可检索（KB_STATUSES）。
_ACTIVE_FILTER = {
    "skills": (Skill, lambda e: e.enabled),
    "mcps": (MCPConnector, lambda e: e.enabled),
    "kbs": (KnowledgeBase, lambda e: e.status == "ready"),
    "experts": (Expert, lambda e: e.enabled),
}


def list_scenarios() -> list[dict]:
    """GET /api/scenarios：十二域固定序，每项 domain/name/任务引导 + 装配摘要（各类数量）。

    未装载的域（正常不会发生：seed 保证十二域齐）不出现在列表，避免返回空 system_prompt 的假模板。
    """
    rows = db.session.execute(select(ScenarioTemplate)).scalars().all()
    by_domain = {r.domain: r for r in rows}
    out: list[dict] = []
    for key, _label in SCENARIO_DOMAINS:
        row = by_domain.get(key)
        if row is None:
            continue
        out.append(
            {
                "domain": row.domain,
                "name": row.name,
                "task_template": row.task_template,
                # 装配摘要：只给数量（列表轻量）；完整 preset 引用见单查
                "preset": {
                    "skills": len(row.preset_skills or []),
                    "mcps": len(row.preset_mcp or []),
                    "kbs": len(row.preset_kb or []),
                    "experts": len(row.preset_expert or []),
                },
            }
        )
    return out


def get_scenario(domain: str) -> dict:
    """GET /api/scenarios/<domain>：单查详情（system_prompt/task_template/preset_* 全文）。未知域 404。"""
    if domain not in SCENARIO_KEYS:
        raise NotFoundError(f"场景域不存在：{domain}")
    row = _get_by_domain_or_raise(domain)
    return row.to_dict()


def _get_by_domain_or_raise(domain: str) -> ScenarioTemplate:
    row = _get_by_domain(domain)
    if row is None:
        raise NotFoundError(f"场景域尚未装载模板：{domain}")
    return row


def _get_by_domain(domain: str) -> ScenarioTemplate | None:
    """按域键取模板行；查无返回 None（供 apply/runtime 判断「域模板是否已存在」）。"""
    return db.session.execute(
        select(ScenarioTemplate).where(ScenarioTemplate.domain == domain)
    ).scalar_one_or_none()


def get_template(domain) -> ScenarioTemplate | None:
    """供 P8 运行时注入：任务所绑域受控且模板在库 → 模板行；非受控/未装载 → None（不报错）。"""
    if domain not in SCENARIO_KEYS:
        return None
    return _get_by_domain(domain)


def apply_scenario(task_id: int, domain) -> dict:
    """POST /api/tasks/<id>/scenario/apply：置域并把预设解析为可用实体后全量覆盖挂载。

    语义（design D4）：
      - 任务不存在 → 404（get_task_or_raise）；domain 非受控 / 模板未装载 → 400，均零副作用；
      - 预设引用分三类：现存+可用 → 进 mounted 写挂载；已删 → skipped(deleted)；
        停用/未就绪 → skipped(disabled|not_ready)；绝不因失效引用中断本次套用。
      - 返回 {task_id, domain, mounted: 四类成功 id, skipped: [...]}。
    """
    task = get_task_or_raise(task_id)
    if domain is None or domain not in SCENARIO_KEYS:
        raise ValidationError(
            f"domain 取值非法：{domain!r}（应为十二个受控域键之一）"
        )
    row = _get_by_domain(domain)
    if row is None:
        # 受控但缺模板属异常态（正常 seed 保证装载）；按 400 报，避免任务绑上一个无模板的域
        raise ValidationError(f"场景域「{domain}」尚未装载模板，无法套用")

    # 预设 → 交现存且可用实体；未通过者归入 skipped（含具体原因），不进 caps 请求体
    presets = {
        "skills": row.preset_skills or [],
        "mcps": row.preset_mcp or [],
        "kbs": row.preset_kb or [],
        "experts": row.preset_expert or [],
    }
    mounted: dict = {}
    skipped: list[dict] = []
    for cat, ids in presets.items():
        model, active = _ACTIVE_FILTER[cat]
        if not ids:
            mounted[cat] = []
            continue
        objects = {
            o.id: o
            for o in db.session.execute(
                select(model).where(model.id.in_(ids))
            ).scalars()
        }
        kept: list[int] = []
        for pid in ids:
            entity = objects.get(pid)
            if entity is None:
                skipped.append({"category": cat, "id": pid, "reason": "实体已删除"})
                continue
            if not active(entity):
                reason = (
                    "知识库未就绪" if cat == "kbs" else "实体已停用"
                )
                skipped.append({"category": cat, "id": pid, "reason": reason})
                continue
            kept.append(pid)
        mounted[cat] = kept

    # 置域 + 复用 P4 全量覆盖写挂载（set_task_caps 单事务 commit，未提交的 scenario_domain 一并入库）
    task.scenario_domain = domain
    caps = capability.set_task_caps(task.id, mounted)
    # mounted 收敛为四类 id（去掉 caps 里冗余的 task_id），对齐 design D4 响应形状
    mounted_out = {cat: caps[cat] for cat in ("skills", "mcps", "kbs", "experts")}
    return {
        "task_id": task.id,
        "domain": domain,
        "mounted": mounted_out,
        "skipped": skipped,
    }
