# 空间服务：list/create/update/delete + 建空间即写 Owner Membership。
# 逻辑集中在 service（对齐 CLAUDE.md §3），API 只做参数取用与序列化。
from sqlalchemy import desc, select

from ..extensions import db
from ..models import MEMBERSHIP_ROLES, VISIBILITIES, Membership, Space, User
from . import file_store
from .errors import NotFoundError, ValidationError


def get_admin() -> User:
    """取内置管理员（迁移 0001 种子）。单人模式默认归属人。"""
    admin = db.session.execute(
        select(User).where(User.username == "admin")
    ).scalar_one_or_none()
    if admin is None:
        raise NotFoundError("内置管理员不存在，请确认已执行迁移 0001")
    return admin


def get_space_or_raise(space_id: int) -> Space:
    space = db.session.get(Space, space_id)
    if space is None:
        raise NotFoundError("空间不存在")
    return space


def _clean_visibility(visibility: str | None, default: str = "private") -> str:
    value = (visibility or default).strip()
    if value not in VISIBILITIES:
        raise ValidationError(
            f"visibility 取值非法：{value}（应为 {sorted(VISIBILITIES)} 之一）"
        )
    return value


def list_spaces() -> list[dict]:
    rows = db.session.execute(
        select(Space).order_by(desc(Space.created_at), desc(Space.id))
    ).scalars()
    return [s.to_dict() for s in rows]


def create_space(
    name: str | None,
    description: str | None = None,
    visibility: str | None = None,
) -> dict:
    cleaned_name = (name or "").strip()
    if not cleaned_name:
        raise ValidationError("name 不能为空")
    vis = _clean_visibility(visibility)
    admin = get_admin()

    space = Space(
        name=cleaned_name,
        description=(description or "").strip() or None,
        owner_id=admin.id,
        visibility=vis,
    )
    db.session.add(space)
    db.session.flush()  # 先拿到 space.id 再写成员关系
    db.session.add(Membership(space_id=space.id, user_id=admin.id, role="Owner"))
    db.session.commit()
    return space.to_dict()


def update_space(space_id: int, name=None, description=None, visibility=None) -> dict:
    space = get_space_or_raise(space_id)
    updates: dict = {}

    if name is not None:
        cleaned = (name or "").strip()
        if not cleaned:
            raise ValidationError("name 不能为空")
        updates["name"] = cleaned
    if description is not None:
        updates["description"] = (description or "").strip() or None
    if visibility is not None:
        updates["visibility"] = _clean_visibility(visibility)

    if not updates:
        raise ValidationError("没有可更新的字段")

    for key, value in updates.items():
        setattr(space, key, value)
    db.session.commit()
    return space.to_dict()


def delete_space(space_id: int) -> None:
    space = get_space_or_raise(space_id)
    dir_path = file_store.space_dir(space.id)
    # 依赖 DB 的 ON DELETE CASCADE 清 memberships/tasks/file_records
    #（SQLite FK 已由 app.py 开启 PRAGMA）。先提交成功再物理删目录，
    # 避免事务失败时文件已删、记录还在的半程态。
    db.session.delete(space)
    db.session.commit()
    file_store.delete_dir(dir_path)
