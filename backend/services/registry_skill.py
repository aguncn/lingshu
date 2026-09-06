# 技能中心服务（P5 registry-center AD-01）：/api/skills 的校验、增删改查与版本语义。
# 分层对齐 CLAUDE.md §3：校验与事务在 service，API 只转发。
# 语义要点（design D8）：name 必填唯一(400)；PATCH 只应用出现字段；
#   skill_md 内容变更时 version+1（记录指令文本迭代，供 P8 判断缓存失效）；
#   enabled 经 PATCH 启停；删除技能靠 DB 级联清 task_skill（无手工删关联代码）。
from sqlalchemy import select

from ..extensions import db
from ..models import Skill
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


def _get_or_raise(skill_id: int) -> Skill:
    skill = db.session.get(Skill, skill_id)
    if skill is None:
        raise NotFoundError("技能不存在")
    return skill


def _name_taken(name: str, exclude_id: int | None = None) -> bool:
    row = db.session.execute(
        select(Skill).where(Skill.name == name)
    ).scalar_one_or_none()
    return row is not None and (exclude_id is None or row.id != exclude_id)


def list_skills() -> list[dict]:
    rows = db.session.execute(
        select(Skill).order_by(Skill.id.desc())
    ).scalars()
    return [s.to_dict() for s in rows]


def get_skill(skill_id: int) -> dict:
    return _get_or_raise(skill_id).to_dict()


def create_skill(name=None, description=None, skill_md=None, enabled=None) -> dict:
    cleaned_name = _clean_required(name, "name")
    if _name_taken(cleaned_name):
        raise ValidationError(f"name 已存在：{cleaned_name}")
    skill = Skill(
        name=cleaned_name,
        description=(description or "").strip() or None,
        skill_md=(skill_md or "").strip() or None,
        version=1,
        enabled=True if enabled is None else _as_bool(enabled, "enabled"),
    )
    db.session.add(skill)
    db.session.commit()
    return skill.to_dict()


def update_skill(skill_id: int, **fields) -> dict:
    """部分更新：只应用请求中出现的字段；skill_md 变更→version+1（design D8）。"""
    skill = _get_or_raise(skill_id)
    if not fields:
        raise ValidationError("没有可更新的字段")
    unknown = set(fields) - {"name", "description", "skill_md", "enabled"}
    if unknown:
        raise ValidationError(f"未知字段：{sorted(unknown)}")

    if "name" in fields:
        new_name = _clean_required(fields["name"], "name")
        if _name_taken(new_name, exclude_id=skill.id):
            raise ValidationError(f"name 已存在：{new_name}")
        skill.name = new_name
    if "description" in fields:
        skill.description = (fields["description"] or "").strip() or None
    if "skill_md" in fields:
        new_md = (fields["skill_md"] or "").strip() or None
        if new_md != skill.skill_md:
            skill.skill_md = new_md
            skill.version = (skill.version or 1) + 1
    if "enabled" in fields:
        skill.enabled = _as_bool(fields["enabled"], "enabled")

    db.session.commit()
    return skill.to_dict()


def delete_skill(skill_id: int) -> None:
    skill = _get_or_raise(skill_id)
    db.session.delete(skill)
    db.session.commit()
