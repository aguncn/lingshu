# 文件落盘服务（设计 D1/D2，P6 扩展 library 域）：
#   - 任务工作空间物理根 <DATA_DIR>/spaces，路径 = data/spaces/<space_id>/<task_id>/；
#   - 资料库物理根 <DATA_DIR>/library，路径 = data/library/<uuid-key>（扁平，见 library design D1/D2）；
#   - 全部目录操作经 _resolve_within_root 白名单，杜绝路径穿越；
#   - 提供落盘元数据记录 FileRecord（P6 上传端点复用）。
# 注意 DATA_DIR 取自 app.config（测试注入临时目录），不再写死 Config。
import mimetypes
import os
import re
import shutil
import uuid
from pathlib import Path

from flask import current_app

from ..config import Config
from ..extensions import db
from ..models import FileRecord
from .errors import NotFoundError, ValidationError


def new_library_key() -> str:
    """资料库存储键：uuid4 hex（32 位），全局唯一、免「先 insert 拿 id 再写盘」的次序问题。"""
    return uuid.uuid4().hex


def _require_key(key: str) -> None:
    """存储键白名单：仅 32 位 hex。纵深防御：即便将来误把用户输入当 key 也进不了目录上上级。"""
    if not key or not re.fullmatch(r"[0-9a-f]{32}", key):
        raise ValidationError("非法存储键")


# 目录根会随 app 配置变化（测试用临时 DATA_DIR），故在请求期取 current_app。
def _data_root() -> Path:
    data_dir = current_app.config.get("DATA_DIR") or Config.DATA_DIR
    return Path(data_dir)


def _spaces_root() -> Path:
    return _data_root() / "spaces"


def _library_root() -> Path:
    return _data_root() / "library"


def _resolve_within_root(root: Path, *parts: int | str) -> Path:
    """把 parts 拼到 root 下并校验仍在根内。

    为什么手动 resolve 再判前缀：即使路由已用 <int:...>，仍防将来有人把
    字符串传入；删除是不可逆操作，纵深防御值得（design D2）。
    """
    r = root.resolve()
    target = r.joinpath(*(str(p) for p in parts)).resolve()
    if not target.is_relative_to(r):
        raise ValidationError("非法落盘路径")
    return target


def space_dir(space_id: int) -> Path:
    return _resolve_within_root(_spaces_root(), space_id)


def task_dir(space_id: int, task_id: int) -> Path:
    return _resolve_within_root(_spaces_root(), space_id, task_id)


def ensure_task_dir(space_id: int, task_id: int) -> Path:
    d = task_dir(space_id, task_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_task_file(space_id: int, task_id: int, filename: str) -> Path:
    """任务目录内某文件的内容读取路径（供工作台文件预览，P7 补）。

    为什么放 service：沿用 _resolve_within_root 的白名单解析杜绝路径穿越，
    API 层拿到绝对路径后用 send_file 内联返回；文件名仅允许任务目录顶层文件
    （scan_task_dir 也只列顶层，见 design D7）。
    """
    if not filename or filename != (filename or "").strip() or "/" in filename or "\\" in filename:
        raise ValidationError("文件名非法")
    target = _resolve_within_root(_spaces_root(), space_id, task_id, filename)
    if not target.is_file():
        raise NotFoundError("文件不存在")
    return target


def scan_task_dir(space_id: int, task_id: int) -> list[dict]:
    """列出任务工作空间目录下的现存文件（顶层），返回元数据数组。"""
    d = ensure_task_dir(space_id, task_id)
    result = []
    for entry in sorted(d.iterdir(), key=lambda e: e.name):
        if not entry.is_file():
            continue  # 只列文件，忽略子目录/临时文件
        size = entry.stat().st_size
        mime = mimetypes.guess_type(entry.name)[0] or "application/octet-stream"
        result.append(
            {
                "filename": entry.name,
                "path": entry.name,  # 任务目录内相对路径
                "size": size,
                "mime": mime,
            }
        )
    return result


def delete_dir(path: Path) -> None:
    """递归删除目录（删空间/任务用）。目录可能本就不存在，幂等忽略。"""
    shutil.rmtree(path, ignore_errors=True)


# ---------- 资料库（library）域：data/library/<key> ----------
def write_library_file(key: str, data: bytes) -> Path:
    """资料库原子落盘：先写 <key>.tmp 再 os.replace，杜绝半文件（design D2）。

    key 白名单经 _require_key；同目录内 replace 原子、不跨文件系统。
    """
    _require_key(key)
    root = _library_root()
    target = _resolve_within_root(root, key)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, target)
    return target


def resolve_library_file(key: str) -> Path:
    """取资料库实体文件路径供下载；记录在但磁盘缺 → NotFoundError（spec「文件已丢失」）。"""
    _require_key(key)
    target = _resolve_within_root(_library_root(), key)
    if not target.is_file():
        raise NotFoundError("资料库文件已丢失")
    return target


def delete_library_file(key: str) -> None:
    """幂等删除资料库实体文件（磁盘本就不存在也返回成功，清孤儿行用）。"""
    _require_key(key)
    target = _resolve_within_root(_library_root(), key)
    target.unlink(missing_ok=True)


def record(
    space_id: int, task_id: int, filename: str, path: str, mime: str, size: int
) -> FileRecord:
    """落盘后写一条 FileRecord 元数据（供列表/审计复用）。"""
    record = FileRecord(
        space_id=space_id,
        task_id=task_id,
        filename=filename,
        path=path,
        mime=mime,
        size=size,
    )
    db.session.add(record)
    db.session.commit()
    return record
