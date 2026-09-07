# 专家中心服务（P5 registry-center AD-04）：/api/experts 的校验、增删改查与多专家组合。
# 语义要点（design D7/D8）：name 唯一(400)；role 白名单默认 general；composed_of 写时校验
#   （元素正整数/表中存在/≠自身/去重）；单条 GET 额外出口 composed=[{id,name,role}] 供组合展示；
#   DELETE 被其它专家 composed_of 引用→400（引用完整性，防悬空组合）；嵌套/环由 P8 编排校验。
from sqlalchemy import select

from ..extensions import db
from ..models import (
    EXPERT_ROLES,
    Expert,
    KnowledgeBase,
    LibraryFile,
    MCPConnector,
    ModelProvider,
    Skill,
)
from .errors import NotFoundError, ValidationError

# 档案预设 id 数组 → 目标实体模型（C5）：create/update 写库前校验存在性，避免悬空引用。
_PRESET_SPEC = {
    "preset_skills": Skill,
    "preset_mcp": MCPConnector,
    "preset_kb": KnowledgeBase,
    "preset_library": LibraryFile,
}


def _clean_required(value, field: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValidationError(f"{field} 不能为空")
    return cleaned


def _as_bool(value, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationError(f"{field} 必须为布尔值")
    return value


def _get_or_raise(expert_id: int) -> Expert:
    expert = db.session.get(Expert, expert_id)
    if expert is None:
        raise NotFoundError("专家不存在")
    return expert


def _name_taken(name: str, exclude_id: int | None = None) -> bool:
    row = db.session.execute(
        select(Expert).where(Expert.name == name)
    ).scalar_one_or_none()
    return row is not None and (exclude_id is None or row.id != exclude_id)


def _parse_composed(value, exclude_id: int | None = None) -> list[int]:
    """校验并归一 composed_of → 升序？不——保持请求顺序去重；None/空=单专家。

    写库前校验（design D7）：须为数组、元素纯正整数、同数组不重复、
    每个 id 在专家表存在、且不等于自身 exclude_id（新建时无自身可防，仅比对存在）。
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationError("composed_of 必须为专家 id 数组")
    seen: set[int] = set()
    ids: list[int] = []
    for elem in value:
        if isinstance(elem, bool) or not isinstance(elem, int):
            raise ValidationError(f"composed_of 元素必须为正整数 id，收到：{elem!r}")
        if elem <= 0:
            raise ValidationError(f"composed_of 元素必须为正整数 id，收到：{elem}")
        if exclude_id is not None and elem == exclude_id:
            raise ValidationError("专家不能把自己加入 composed_of（防自引用）")
        if elem in seen:
            raise ValidationError(f"composed_of 内重复 id：{elem}")
        seen.add(elem)
        ids.append(elem)
    if ids:
        existing = set(
            db.session.execute(select(Expert.id).where(Expert.id.in_(ids))).scalars()
        )
        missing = set(ids) - existing
        if missing:
            raise ValidationError(f"composed_of 存在不存在的专家 id：{sorted(missing)}")
    return ids


def _parse_preset_ids(value, field: str) -> list[int]:
    """校验并归一档案预设 id 数组 → 保持请求顺序去重；None/空 = 无该维预设。

    与 _parse_composed 同构但不涉及「排除自身」：元素须为正整数、同数组不重复、
    每个 id 在对应实体表存在（_PRESET_SPEC 决定表）。全部通过才返回，任一非法即抛 400。
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationError(f"{field} 必须为 id 数组")
    seen: set[int] = set()
    ids: list[int] = []
    for elem in value:
        if isinstance(elem, bool) or not isinstance(elem, int):
            raise ValidationError(f"{field} 元素必须为正整数 id，收到：{elem!r}")
        if elem <= 0:
            raise ValidationError(f"{field} 元素必须为正整数 id，收到：{elem}")
        if elem in seen:
            raise ValidationError(f"{field} 内重复 id：{elem}")
        seen.add(elem)
        ids.append(elem)
    if ids:
        model = _PRESET_SPEC[field]
        existing = set(
            db.session.execute(select(model.id).where(model.id.in_(ids))).scalars()
        )
        missing = set(ids) - existing
        if missing:
            raise ValidationError(f"{field} 存在不存在的实体 id：{sorted(missing)}")
    return ids


def _clean_provider_id(value, field: str):
    """校验可选默认模型供应商 id：None/空 → None；否则须为现存供应商正整数 id。"""
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValidationError(f"{field} 必须为正整数供应商 id，收到：{value!r}")
    exists = db.session.get(ModelProvider, value)
    if exists is None:
        raise ValidationError(f"{field} 指向不存在的供应商 id：{value}")
    return value


def _resolve_children(composed: list[int]) -> list[dict]:
    """把子专家 id 列表解析为 {id,name,role}，保持原顺序（detail 出口用）。"""
    if not composed:
        return []
    by_id = {
        e.id: e
        for e in db.session.execute(select(Expert).where(Expert.id.in_(composed))).scalars()
    }
    return [
        {"id": cid, "name": by_id[cid].name, "role": by_id[cid].role}
        for cid in composed
        if cid in by_id
    ]


def list_experts() -> list[dict]:
    rows = db.session.execute(select(Expert).order_by(Expert.id.desc())).scalars()
    return [e.to_dict() for e in rows]


def get_expert(expert_id: int) -> dict:
    """单条读取：基础字段 + composed=[{id,name,role}]（design D7 组合展示）。"""
    expert = _get_or_raise(expert_id)
    out = expert.to_dict()
    out["composed"] = _resolve_children(expert.composed_of or [])
    return out


def create_expert(
    name=None,
    description=None,
    system_prompt=None,
    role=None,
    preset_skills=None,
    preset_mcp=None,
    preset_kb=None,
    preset_library=None,
    default_provider_id=None,
    default_model_name=None,
    composed_of=None,
    enabled=None,
) -> dict:
    cleaned_name = _clean_required(name, "name")
    if _name_taken(cleaned_name):
        raise ValidationError(f"name 已存在：{cleaned_name}")
    cleaned_role = (role or "").strip() or "general"
    if cleaned_role not in EXPERT_ROLES:
        raise ValidationError(
            f"role 取值非法：{cleaned_role}（应为 {sorted(EXPERT_ROLES)} 之一）"
        )
    expert = Expert(
        name=cleaned_name,
        description=(description or "").strip() or None,
        system_prompt=(system_prompt or "").strip() or None,
        role=cleaned_role,
        preset_skills=_parse_preset_ids(preset_skills, "preset_skills"),
        preset_mcp=_parse_preset_ids(preset_mcp, "preset_mcp"),
        preset_kb=_parse_preset_ids(preset_kb, "preset_kb"),
        preset_library=_parse_preset_ids(preset_library, "preset_library"),
        default_provider_id=_clean_provider_id(default_provider_id, "default_provider_id"),
        default_model_name=(default_model_name or "").strip() or None,
        composed_of=_parse_composed(composed_of),
        enabled=True if enabled is None else _as_bool(enabled, "enabled"),
    )
    db.session.add(expert)
    db.session.commit()
    return get_expert(expert.id)


def update_expert(expert_id: int, **fields) -> dict:
    """部分更新：只应用请求中出现的字段；composed_of 整体替换，未提供保持不变。"""
    expert = _get_or_raise(expert_id)
    if not fields:
        raise ValidationError("没有可更新的字段")
    unknown = set(fields) - {
        "name", "description", "system_prompt", "role",
        "preset_skills", "preset_mcp", "preset_kb", "preset_library",
        "default_provider_id", "default_model_name",
        "composed_of", "enabled",
    }
    if unknown:
        raise ValidationError(f"未知字段：{sorted(unknown)}")

    if "name" in fields:
        new_name = _clean_required(fields["name"], "name")
        if _name_taken(new_name, exclude_id=expert.id):
            raise ValidationError(f"name 已存在：{new_name}")
        expert.name = new_name
    if "description" in fields:
        expert.description = (fields["description"] or "").strip() or None
    if "system_prompt" in fields:
        expert.system_prompt = (fields["system_prompt"] or "").strip() or None
    if "role" in fields:
        cleaned_role = (fields["role"] or "").strip() or "general"
        if cleaned_role not in EXPERT_ROLES:
            raise ValidationError(
                f"role 取值非法：{cleaned_role}（应为 {sorted(EXPERT_ROLES)} 之一）"
            )
        expert.role = cleaned_role
    for preset in ("preset_skills", "preset_mcp", "preset_kb", "preset_library"):
        if preset in fields:
            setattr(expert, preset, _parse_preset_ids(fields[preset], preset))
    if "default_provider_id" in fields:
        expert.default_provider_id = _clean_provider_id(
            fields["default_provider_id"], "default_provider_id"
        )
    if "default_model_name" in fields:
        expert.default_model_name = (fields["default_model_name"] or "").strip() or None
    if "composed_of" in fields:
        expert.composed_of = _parse_composed(fields["composed_of"], exclude_id=expert.id)
    if "enabled" in fields:
        expert.enabled = _as_bool(fields["enabled"], "enabled")

    db.session.commit()
    return get_expert(expert.id)


def delete_expert(expert_id: int) -> None:
    """删除前查引用完整性：仍被其它专家 composed_of 引用则 400（design D7）。"""
    expert = _get_or_raise(expert_id)
    for other in db.session.execute(select(Expert)).scalars():
        ids = other.composed_of or []
        if expert_id in ids:
            raise ValidationError(
                f"该专家仍被专家「{other.name}」(id={other.id}) 引用，无法删除"
            )
    db.session.delete(expert)
    db.session.commit()
