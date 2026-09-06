# 运行时审计服务（P8 agentscope-runtime）：model_call / tool_call / confirm_decision → AuditLog。
# 契约对齐 spec「运行时审计」：每类事件一条记录、字段含任务/动作/目标/时间戳与可读结果、
#   detail 截断且任何记录不含密钥明文/敏感密文值（本文件集中做脱敏，调用方不各自处理）。
# 为什么列保持通用（action/target/result/detail 自由文本）：兼容 P10 全量写操作审计扩列，
#   本提案只记运行事件（model_call/tool_call/confirm_decision），P10 再记 spaces/tasks 写操作。
from ..extensions import db
from ..models import AuditLog
from .errors import ValidationError

MAX_DETAIL = 2000  # detail 截断上限（字符），防超长工具参数/输出撑爆审计行
# Fernet token 是单段 urlsafe base64 blob（payload||hmac 一体、尾可带 = 补齐），
# 误入 detail 的密文（env/headers/api_key_enc）按「≥60 位长 base64 段」整体替换，绝不明文外泄
_FERNET_TOKEN = r"[A-Za-z0-9_\-]{60,}={0,2}"

# action/actor/result 字段白名单：拼写收敛、防脏值入库（审计本身要可信）
ACTIONS = {"model_call", "tool_call", "confirm_decision"}
ACTORS = {"user", "runtime", "system"}
RESULTS = {"success", "error", "denied", "allow", "deny", "interrupted"}


def _scrub_detail(detail: str | None) -> str | None:
    """detail 脱敏：替换 Fernet 密文形态的子串并截断超长。"""
    if not detail:
        return None
    import re

    cleaned = re.sub(_FERNET_TOKEN, "[redacted]", detail)
    if len(cleaned) > MAX_DETAIL:
        cleaned = cleaned[:MAX_DETAIL] + "…(截断)"
    return cleaned


def record(
    task_id=None,
    run_id=None,
    actor="runtime",
    action="tool_call",
    target=None,
    result=None,
    detail=None,
) -> dict:
    """写一条审计并落库。task_id 可空（如非任务级系统事件）；action/actor 越界 → 400。

    detail 一律经 _scrub_detail（Fernet 密文替换 + 截断）；调用方把「模型名/工具名/摘要」
    放 target/detail，永远不把 env/headers/API key 明文传进来。
    """
    if action not in ACTIONS:
        raise ValidationError(f"action 取值非法：{action!r}（应为 {sorted(ACTIONS)} 之一）")
    if actor not in ACTORS:
        raise ValidationError(f"actor 取值非法：{actor!r}（应为 {sorted(ACTORS)} 之一）")
    if result is not None and result not in RESULTS:
        raise ValidationError(f"result 取值非法：{result!r}（应为 {sorted(RESULTS)} 之一）")

    entry = AuditLog(
        task_id=task_id,
        run_id=(run_id or None) and str(run_id),
        actor=actor,
        action=action,
        target=(target or None) and str(target)[:256],
        result=result,
        detail=_scrub_detail(detail),
    )
    db.session.add(entry)
    db.session.commit()
    return entry.to_dict()
