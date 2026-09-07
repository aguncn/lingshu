# 任务服务：以空间为边界 list/create/get/update/delete。
# 任务必属空间；task_type/status/visibility 走白名单校验；model_config_id 本期为占位整数。
from sqlalchemy import desc, select

from ..extensions import db
from ..models import (
    TASK_PERMISSION_MODES,
    TASK_STATUSES,
    TASK_TYPES,
    VISIBILITIES,
    Space,
    Task,
)
from . import file_store
from .errors import NotFoundError, ValidationError
from .space_service import get_space_or_raise


def _clean(value: str | None, allowed: set[str], field: str, default: str | None) -> str:
    candidate = value if value is not None else default
    candidate = (candidate or "").strip()
    if candidate not in allowed:
        raise ValidationError(
            f"{field} 取值非法：{candidate}（应为 {sorted(allowed)} 之一）"
        )
    return candidate


def _clean_optional_int(value, field: str) -> int | None:
    """model_config_id 占位：可为 None/缺省；非空则须能转整数。"""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} 必须为整数或空") from None


def list_tasks(space_id: int) -> list[dict]:
    get_space_or_raise(space_id)  # 空间不存在提前 404
    rows = db.session.execute(
        select(Task)
        .where(Task.space_id == space_id)
        .order_by(desc(Task.created_at), desc(Task.id))
    ).scalars()
    return [t.to_dict() for t in rows]


def create_task(
    space_id: int,
    title: str | None,
    task_type: str | None,
    visibility: str | None = None,
    model_config_id=None,
    permission_mode: str | None = None,
) -> dict:
    get_space_or_raise(space_id)
    cleaned_title = (title or "").strip()
    if not cleaned_title:
        raise ValidationError("title 不能为空")
    # C5：task_type 已从新建入口移除，请求体不再携带 → 缺省回落 'general'（列保留、徽标仍展示）
    typ = _clean(task_type, TASK_TYPES, "task_type", "general")
    vis = _clean(visibility, VISIBILITIES, "visibility", "private")
    # 权限模式缺省 strict（=现状最严）；白名单校验与其它枚举一致
    perm = _clean(permission_mode, TASK_PERMISSION_MODES, "permission_mode", "strict")

    task = Task(
        space_id=space_id,
        title=cleaned_title,
        task_type=typ,
        visibility=vis,
        model_config_id=_clean_optional_int(model_config_id, "model_config_id"),
        permission_mode=perm,
    )
    db.session.add(task)
    db.session.commit()
    return task.to_dict()


def get_task_or_raise(task_id: int) -> Task:
    task = db.session.get(Task, task_id)
    if task is None:
        raise NotFoundError("任务不存在")
    return task


def get_task(task_id: int) -> dict:
    return get_task_or_raise(task_id).to_dict()


def update_task(task_id: int, **fields) -> dict:
    task = get_task_or_raise(task_id)
    updates: dict = {}

    if "title" in fields and fields["title"] is not None:
        cleaned = (fields["title"] or "").strip()
        if not cleaned:
            raise ValidationError("title 不能为空")
        updates["title"] = cleaned
    if "task_type" in fields:
        updates["task_type"] = _clean(fields["task_type"], TASK_TYPES, "task_type", None)
    if "status" in fields:
        updates["status"] = _clean(fields["status"], TASK_STATUSES, "status", None)
    if "visibility" in fields:
        updates["visibility"] = _clean(fields["visibility"], VISIBILITIES, "visibility", None)
    if "model_config_id" in fields:
        updates["model_config_id"] = _clean_optional_int(fields["model_config_id"], "model_config_id")
    if "permission_mode" in fields:
        # 运行中改档只影响之后装配的运行，不打断已在跑的会话（每次 chat 重新 build）
        updates["permission_mode"] = _clean(fields["permission_mode"], TASK_PERMISSION_MODES, "permission_mode", None)

    if not updates:
        raise ValidationError("没有可更新的字段")

    for key, value in updates.items():
        setattr(task, key, value)
    db.session.commit()
    return task.to_dict()


def delete_task(task_id: int) -> None:
    """删除任务记录并清理其工作空间目录（含 FileRecord，DB 级联）。"""
    task = get_task_or_raise(task_id)
    dir_path = file_store.task_dir(task.space_id, task.id)
    db.session.delete(task)
    db.session.commit()
    file_store.delete_dir(dir_path)
