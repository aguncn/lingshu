# 对话历史服务（P8 agentscope-runtime）：Message 的记录与读取。
# 契约对齐 spec「对话历史持久化与读取」：用户消息在收到请求即记、助手文本在 done 时记，
#   GET /messages 按时间升序返回、任务不存在→404、无历史→[]。
# 为什么走独立 service 而非塞 task_service：对话历史是运行时的写面，与任务/空间管理解耦；
#   service 只收「已解析」的字段，角色白名单在此收敛（防脏 role 入库）。
from sqlalchemy import select

from ..extensions import db
from ..models import Message
from .errors import ValidationError
from .task_service import get_task_or_raise

ROLES = {"user", "assistant"}


def _clean_content(content) -> str:
    """content 非空校验（SSE 文本/用户输入都不该为空）。"""
    if not isinstance(content, str) or not content.strip():
        raise ValidationError("消息内容不能为空")
    return content


def _clean_role(role) -> str:
    if role not in ROLES:
        raise ValidationError(f"role 取值非法：{role!r}（应为 {sorted(ROLES)} 之一）")
    return role


def add_message(task_id: int, role: str, content: str, run_id=None, model=None) -> dict:
    """记一条消息并落库；任务不存在 → 404。run_id/model 可空（如任务预置消息）。"""
    task = get_task_or_raise(task_id)  # 防对不存在任务写历史
    msg = Message(
        task_id=task.id,
        role=_clean_role(role),
        content=_clean_content(content),
        run_id=(run_id or None) and str(run_id),
        model=(model or None) and str(model),
    )
    db.session.add(msg)
    db.session.commit()
    return msg.to_dict()


def add_user_message(task_id: int, content: str, run_id=None, model=None) -> dict:
    return add_message(task_id, "user", content, run_id=run_id, model=model)


def add_assistant_message(task_id: int, content: str, run_id=None, model=None) -> dict:
    return add_message(task_id, "assistant", content, run_id=run_id, model=model)


def list_messages(task_id: int) -> list[dict]:
    """按时间升序返回该任务全部消息（对话语义）；任务不存在 → 404；无历史 → []。"""
    task = get_task_or_raise(task_id)
    rows = db.session.execute(
        select(Message)
        .where(Message.task_id == task.id)
        .order_by(Message.id.asc())  # id 单调即时间序，等价 created_at asc 且无同刻歧义
    ).scalars()
    return [m.to_dict() for m in rows]
