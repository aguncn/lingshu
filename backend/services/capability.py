# 能力装配服务（P4 capability-mount）：任务↔Skill/MCP/知识库/专家 挂载的校验、覆盖写与读。
# 分层对齐 CLAUDE.md §3：所有校验/事务在 service，API 只转发。只做数据关联，不接 P8 运行时。
# 核心语义（design D3/D5）：
#   - PUT = 全状态覆盖：请求体含 skills/mcps/kbs/experts 四键 id 数组，缺失键视为清空该类；
#   - 写前全量校验（未知键/元素类型/同数组重复/目标实体存在），任一失败即 400 且不改动既有挂载；
#   - 任务删除的关联清理由 DB 级联完成（0003 迁移 ON DELETE CASCADE），本文件不重复处理。
from sqlalchemy import delete, select

from ..extensions import db
from ..models import (
    Expert,
    KnowledgeBase,
    MCPConnector,
    Skill,
    TaskExpert,
    TaskKb,
    TaskMcp,
    TaskSkill,
)
from .errors import ValidationError
from .task_service import get_task_or_raise

# 分类 -> (实体模型, 关联模型, 关联外键列名)。四类同构，收口到一张表驱动增删查。
# 元素顺序即 GET/响应中各类的顺序（skills/mcps/kbs/experts），与 spec 字段约定一致。
_ENTITY_SPEC = {
    "skills": (Skill, TaskSkill, "skill_id"),
    "mcps": (MCPConnector, TaskMcp, "mcp_id"),
    "kbs": (KnowledgeBase, TaskKb, "kb_id"),
    "experts": (Expert, TaskExpert, "expert_id"),
}


def _existing_ids(model, ids: list[int]) -> set[int]:
    """查某实体表中实际存在的 id 集合，用于「目标实体必须存在」校验（防脏引用）。"""
    if not ids:
        return set()
    rows = db.session.execute(select(model.id).where(model.id.in_(ids))).scalars()
    return set(rows)


def parse_caps(payload) -> dict:
    """严格校验并归一化挂载请求体 → {skills:[..], mcps:[..], kbs:[..], experts:[..]}。

    校验规则（design D3，全部在写库前完成）：
      - 未知分类键 → 400；缺失键视为 []（PUT 全状态语义由调用方据此覆盖）。
      - 元素须为非 bool 的正整数 int（str/float/负数/bool → 400）；同数组重复 → 400。
      - 每类目标 id 须在对应实体表存在，否则 400 并指明非法 id。
    """
    if payload is None or not isinstance(payload, dict):
        raise ValidationError("请求体必须为 JSON 对象")

    unknown = set(payload) - set(_ENTITY_SPEC)
    if unknown:
        raise ValidationError(
            f"未知分类键：{sorted(unknown)}（仅支持 {sorted(_ENTITY_SPEC)}）"
        )

    result: dict = {}
    for cat, (model, _, _) in _ENTITY_SPEC.items():
        raw = payload.get(cat, [])
        if not isinstance(raw, list):
            raise ValidationError(f"{cat} 必须为 id 数组")
        ids: list[int] = []
        seen: set[int] = set()
        for elem in raw:
            # bool 是 int 子类、JSON 数字可能解析为 float：一律拒绝非「纯正整数」
            if isinstance(elem, bool) or not isinstance(elem, int):
                raise ValidationError(f"{cat} 元素必须为正整数 id，收到：{elem!r}")
            if elem <= 0:
                raise ValidationError(f"{cat} 元素必须为正整数 id，收到：{elem}")
            if elem in seen:
                raise ValidationError(f"{cat} 内重复挂载同一 id：{elem}")
            seen.add(elem)
            ids.append(elem)
        missing = set(ids) - _existing_ids(model, ids)
        if missing:
            raise ValidationError(f"{cat} 存在不存在的实体 id：{sorted(missing)}")
        result[cat] = ids
    return result


def _caps_dict(task_id: int) -> dict:
    """读该任务四类挂载的 id 清单（升序），返回 GET/响应同构结构。"""
    out: dict = {"task_id": task_id}
    for cat, (_, assoc, fk_attr) in _ENTITY_SPEC.items():
        rows = db.session.execute(
            select(getattr(assoc, fk_attr)).where(assoc.task_id == task_id)
        ).scalars()
        out[cat] = sorted(rows)
    return out


def get_task_caps(task_id: int) -> dict:
    """GET：返回任务当前完整挂载清单；任务不存在 → 404（沿 task_service）。"""
    task = get_task_or_raise(task_id)
    return _caps_dict(task.id)


def _expert_personas(ids: list[int]) -> dict:
    """取将挂载专家 id → persona 快照（=启用时其 system_prompt 文本，停用 → None）。

    快照语义（C5）：挂载动作定格人设；此后改/停用档案不影响已建任务。停用的专家此刻不落快照，
    运行时视为「无可用人设」跳过（与既有 disabled 过滤一致），未来重新启用后仍可正常挂载取到快照。
    """
    if not ids:
        return {}
    rows = db.session.execute(select(Expert).where(Expert.id.in_(ids))).scalars()
    return {
        e.id: ((e.system_prompt or "").strip() or None) if e.enabled else None for e in rows
    }


def set_task_caps(task_id: int, payload) -> dict:
    """PUT 全状态覆盖：先整体校验、后单事务 delete→insert，成功返回最新清单。

    缺键=清空（把缺失分类当 [] 覆盖写）；parse_caps 在所有删除之前完成，天然保证
    「校验失败不改动原挂载」。写失败（理论极少，因校验已前置）整体回滚不半写。
    挂载专家时同步落 persona_snapshot（见 _expert_personas）。
    """
    task = get_task_or_raise(task_id)
    parsed = parse_caps(payload)
    personas = _expert_personas(parsed["experts"])
    try:
        for cat, (_, assoc, _) in _ENTITY_SPEC.items():
            db.session.execute(delete(assoc).where(assoc.task_id == task.id))
        for cat, ids in parsed.items():
            _, assoc, fk_attr = _ENTITY_SPEC[cat]
            for target_id in ids:
                extra = {"persona_snapshot": personas.get(target_id)} if cat == "experts" else {}
                db.session.add(assoc(task_id=task.id, **{fk_attr: target_id}, **extra))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return _caps_dict(task.id)


def load_mounted(task_id: int) -> dict:
    """供 P8 运行时：按任务聚合返回已挂载实体对象（非 REST）。

    返回 {skills:[Skill..], mcps:[...], kbs:[...], experts:[...]}，未挂载分类为空列表；
    反映最近一次成功挂载（enabled/trust 装配期门控归 P8 运行时，本提案不做过滤）。
    """
    task = get_task_or_raise(task_id)
    result: dict = {}
    for cat, (model, assoc, fk_attr) in _ENTITY_SPEC.items():
        result[cat] = (
            db.session.execute(
                select(model)
                .join(assoc, getattr(assoc, fk_attr) == model.id)
                .where(assoc.task_id == task.id)
                .order_by(model.id)
            )
            .scalars()
            .all()
        )
    return result
