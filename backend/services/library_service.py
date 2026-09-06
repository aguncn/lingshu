# 资料库服务（P6 library LB-01）：/api/library 资源 + 跨任务引用的校验与事务。
# 分层对齐 CLAUDE.md §3：所有校验/事务在 service，API 只转发。
# 决策对应 library design：D1(扁平 uuid key 落盘) D2(file_store 域) D3(space 归属 + SET NULL)
#   D4(FileRecord.library_file_id + path='' 引用行) D6(上传归属) D7(scope 过滤)
#   D9(attach/detach 不复制字节) D10(删除完整性 400)。
# 知识库(KB)与本能力解耦：knowledge_chunks.file_id 回填归 P8，这里不做任何 file_id 写入。
import mimetypes
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import FileRecord, LibraryFile, Space, Task
from . import file_store
from .errors import NotFoundError, ValidationError
from .task_service import get_task_or_raise

# 列表 scope 白名单（design D7）；all=全部 / global=仅全局 / shared=仅分享 / space=指定空间
SCOPES = {"all", "global", "shared", "space"}
# PATCH 可更新字段白名单
_LIBRARY_UPDATABLE = {"shared", "filename"}


def _utcnow() -> str:
    """统一 UTC ISO 时间文本（与 models._utcnow / schema_version 一致）。"""
    return datetime.now(timezone.utc).isoformat()


# ---------- 共享校验 helper（design D5/D6） ----------
def _clean_filename(raw) -> str:
    """净化上传/改名文件名：剥目录只留 basename、strip、拒空。

    为什么剥目录：库内以 uuid key 落盘，文件名只是展示/下载名，保留任何路径
    都会给 Content-Disposition/下载名注入 "../" 的机会，故一律只留顶层名字。
    """
    if raw is None:
        raise ValidationError("filename 不能为空")
    name = str(raw).strip().replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name:
        raise ValidationError("filename 不能为空")
    return name


def _require_positive_int(value, field: str) -> int:
    """接受 int 或数字字符串（query/form 取到的多为 str），bool 属 int 子类须显式拒绝。"""
    if isinstance(value, bool):
        raise ValidationError(f"{field} 必须为正整数")
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} 必须为正整数")
    if n <= 0:
        raise ValidationError(f"{field} 必须为正整数")
    return n


def _resolve_space(raw) -> int | None:
    """解析可选归属空间：None/空 → 全局（返回 None）；否则须为已存在空间。

    为什么不存在返回 400 而非 404：这是「归属参数非法」层面的校验（对齐 P5 create_kb
    的 _resolve_space 语义），不是对某个资源的 404。
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    sid = _require_positive_int(raw, "space_id")
    if db.session.get(Space, sid) is None:
        raise ValidationError(f"space 不存在：{sid}")
    return sid


def _get_library_or_raise(library_id: int) -> LibraryFile:
    row = db.session.get(LibraryFile, library_id)
    if row is None:
        raise NotFoundError("资料库文件不存在")
    return row


# ---------- 资料库资源（AD 对应 spec library Requirements） ----------
def create_library(space_id=None, filename=None, data: bytes = b"") -> dict:
    """上传：写盘（原子）→ 建行 → commit；失败清理孤儿盘文件（design D6）。

    data 允许空字节（0 字节文档合法），仅文件名不可空；归属经 _resolve_space。
    """
    clean = _clean_filename(filename)
    sid = _resolve_space(space_id)
    key = file_store.new_library_key()
    file_store.write_library_file(key, data)  # 原子落盘，失败抛错不落行
    mime = mimetypes.guess_type(clean)[0] or "application/octet-stream"
    try:
        row = LibraryFile(
            space_id=sid,
            filename=clean,
            path=key,
            mime=mime,
            size=len(data),
        )
        db.session.add(row)
        db.session.commit()
    except Exception:
        db.session.rollback()
        file_store.delete_library_file(key)  # 已写盘未落行 → 清孤儿
        raise
    return row.to_dict()


def list_library(scope=None, space_id=None) -> list[dict]:
    """按 scope 过滤列表（design D7）：元素为元数据、不含存储键；id 升序。"""
    sc = (scope or "all").strip() or "all"
    if sc not in SCOPES:
        raise ValidationError(f"scope 非法：{sc}（可选 {sorted(SCOPES)}）")
    stmt = select(LibraryFile)
    if sc == "global":
        stmt = stmt.where(LibraryFile.space_id.is_(None))
    elif sc == "shared":
        stmt = stmt.where(LibraryFile.shared.is_(True))
    elif sc == "space":
        sid = _resolve_space(space_id)
        if sid is None:
            raise ValidationError("scope=space 需要 space_id 参数")
        stmt = stmt.where(LibraryFile.space_id == sid)
    rows = db.session.execute(stmt.order_by(LibraryFile.id.asc())).scalars()
    return [r.to_dict() for r in rows]


def download_file(library_id: int) -> tuple:
    """下载素材：返回 (磁盘 Path, 展示文件名, mime)。行缺→404；行在盘缺→404「已丢失」。"""
    row = _get_library_or_raise(library_id)
    path = file_store.resolve_library_file(row.path)
    return path, row.filename, row.mime or "application/octet-stream"


def update_library(library_id: int, **fields) -> dict:
    """部分更新：仅应用出现字段——shared 开关（置 true 记时刻）、filename 净化改名。"""
    row = _get_library_or_raise(library_id)
    if not fields:
        raise ValidationError("没有可更新的字段")
    unknown = set(fields) - _LIBRARY_UPDATABLE
    if unknown:
        raise ValidationError(f"未知字段：{sorted(unknown)}")
    if "shared" in fields:
        value = fields["shared"]
        if not isinstance(value, bool):
            raise ValidationError("shared 必须为布尔值")
        if value and not row.shared:
            row.shared_at = _utcnow()  # 由 false→true 才刷新时刻；false 保留最近分享时刻
        row.shared = value
    if "filename" in fields:
        row.filename = _clean_filename(fields["filename"])
    db.session.commit()
    return row.to_dict()


def delete_library(library_id: int) -> None:
    """删除：被任一任务引用 → 400（完整性，design D10）；否则先清盘再删行（幂等）。"""
    row = _get_library_or_raise(library_id)
    refs = db.session.execute(
        select(func.count())
        .select_from(FileRecord)
        .where(FileRecord.library_file_id == library_id)
    ).scalar()
    if refs:
        raise ValidationError(f"该文件仍被 {refs} 个任务引用，请先解除引用")
    key = row.path
    file_store.delete_library_file(key)  # 幂等清盘
    db.session.delete(row)
    db.session.commit()


# ---------- 跨任务引用（spec library Requirement + space-task-mgmt MODIFIED） ----------
def attach_library(task_id: int, library_file_id) -> dict:
    """任务挂载资料库引用：建一条 FileRecord.library_file_id 指向库文件，字节不复制。

    引用行归属任务所在空间/任务；filename/mime/size 抄录自库文件；path 空串（DB NOT NULL
    兼容，design D4）；重复 (task, library) → 400（服务层先查 + 0005 部分唯一索引兜底）。
    """
    task = get_task_or_raise(task_id)  # 任务不存在 → 404
    lib_id = _require_positive_int(library_file_id, "library_file_id")
    lib = _get_library_or_raise(lib_id)  # 库文件不存在 → 404
    dup = db.session.execute(
        select(FileRecord.id).where(
            FileRecord.task_id == task.id,
            FileRecord.library_file_id == lib_id,
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise ValidationError("该任务已引用此资料库文件")
    ref = FileRecord(
        space_id=task.space_id,
        task_id=task.id,
        filename=lib.filename,
        path="",  # 引用行不向任务目录落字节
        mime=lib.mime,
        size=lib.size,
        library_file_id=lib.id,
    )
    db.session.add(ref)
    try:
        db.session.commit()
    except IntegrityError:  # 唯一索引兜底（理论已前置拦截，防并发/绕过）
        db.session.rollback()
        raise ValidationError("该任务已引用此资料库文件")
    return {
        "id": ref.id,
        "task_id": ref.task_id,
        "library_file_id": ref.library_file_id,
        "filename": ref.filename,
        "size": ref.size,
        "mime": ref.mime,
        "kind": "ref",
    }


def detach_library(task_id: int, file_record_id: int) -> None:
    """解除引用：只删该 FileRecord，绝不动资料库实体文件。归属不符/非引用 → 404。"""
    task = get_task_or_raise(task_id)
    ref = db.session.get(FileRecord, file_record_id)
    if ref is None or ref.task_id != task.id or ref.library_file_id is None:
        raise NotFoundError("引用不存在")
    db.session.delete(ref)
    db.session.commit()


def merge_task_files(task: Task) -> list[dict]:
    """合并任务文件清单（space-task-mgmt MODIFIED）：实体文件在前，库引用在后，稳定有序。

    kind 标记区分来源；无引用时仅比原来多 kind 字段（加法扩展）。
    """
    real = file_store.scan_task_dir(task.space_id, task.id)
    for item in real:
        item["kind"] = "file"
    rows = db.session.execute(
        select(FileRecord, LibraryFile)
        .join(LibraryFile, LibraryFile.id == FileRecord.library_file_id)
        .where(FileRecord.task_id == task.id)
        .order_by(FileRecord.id.asc())
    ).all()
    refs = []
    for fr, lib in rows:
        refs.append(
            {
                "kind": "ref",
                "id": fr.id,
                "library_file_id": lib.id,
                "filename": lib.filename,
                "size": lib.size,
                "mime": lib.mime,
                "shared": lib.shared,
            }
        )
    return real + refs
