# 知识库中心服务（P5 registry-center AD-03）：/api/kb 的 CRUD + 文档上传切块 + 关键词检索。
# 语义要点（design D4/D5/D8）：
#   - name 唯一(400)；chunk_size 正整数默认 400；status ∈ {draft,ready,disabled} 默认 ready；
#   - status=disabled 的库不接受 upload/search（400）；draft/ready 仅标记，装配门控归 P8；
#   - 删库靠 DB 级联清 knowledge_chunks 与 task_kb（无手工删关联代码）；
#   - upload 仅 .txt/.md（UTF-8 严格解码）按 chunk_size 按字符切窗；同名重传整体替换该文件旧块、
#     异名保留（单事务）；meta 记 {filename, chunk_index, chars}；file_id 恒 NULL（P6 回填）；
#   - search 关键词计分：空白切词子串命中 + 整句精确命中加权，按 (-score, chunk_index) 取 top-k。
import os
import re

from sqlalchemy import select

from ..extensions import db
from ..models import KB_STATUSES, KnowledgeBase, KnowledgeChunk, Space
from .errors import NotFoundError, ValidationError

_TXT_EXTENSIONS = {".txt", ".md"}
_TOP_K_CAP = 20


def _clean_required(value, field: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValidationError(f"{field} 不能为空")
    return cleaned


def _positive_int(value, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field} 必须为正整数")
    if value <= 0:
        raise ValidationError(f"{field} 必须为正整数")
    return value


def _get_or_raise(kb_id: int) -> KnowledgeBase:
    kb = db.session.get(KnowledgeBase, kb_id)
    if kb is None:
        raise NotFoundError("知识库不存在")
    return kb


def _name_taken(name: str, exclude_id: int | None = None) -> bool:
    row = db.session.execute(
        select(KnowledgeBase).where(KnowledgeBase.name == name)
    ).scalar_one_or_none()
    return row is not None and (exclude_id is None or row.id != exclude_id)


def _resolve_space(space_id):
    """space_id 非空则须存在于 spaces 表，否则 400（避免 FK IntegrityError → 5xx）。"""
    if space_id is None:
        return None
    space = db.session.get(Space, space_id)
    if space is None:
        raise ValidationError(f"space 不存在：{space_id}")
    return space.id


def list_kbs() -> list[dict]:
    rows = db.session.execute(
        select(KnowledgeBase).order_by(KnowledgeBase.id.desc())
    ).scalars()
    return [kb.to_dict() for kb in rows]


def get_kb(kb_id: int) -> dict:
    return _get_or_raise(kb_id).to_dict()


def create_kb(
    name=None,
    space_id=None,
    embedding_provider=None,
    chunk_size=None,
    status=None,
) -> dict:
    cleaned_name = _clean_required(name, "name")
    if _name_taken(cleaned_name):
        raise ValidationError(f"name 已存在：{cleaned_name}")
    cleaned_status = (status or "").strip() or "ready"
    if cleaned_status not in KB_STATUSES:
        raise ValidationError(
            f"status 取值非法：{cleaned_status}（应为 {sorted(KB_STATUSES)} 之一）"
        )
    kb = KnowledgeBase(
        name=cleaned_name,
        space_id=_resolve_space(space_id),
        embedding_provider=(embedding_provider or "").strip() or None,
        chunk_size=(
            _positive_int(chunk_size, "chunk_size")
            if chunk_size is not None
            else 400
        ),
        status=cleaned_status,
    )
    db.session.add(kb)
    db.session.commit()
    return kb.to_dict()


def update_kb(kb_id: int, **fields) -> dict:
    """部分更新：只应用请求中出现的字段；space_id 显式给 null 视为清除（回全局库）。"""
    kb = _get_or_raise(kb_id)
    if not fields:
        raise ValidationError("没有可更新的字段")
    unknown = set(fields) - {
        "name", "space_id", "embedding_provider", "chunk_size", "status",
    }
    if unknown:
        raise ValidationError(f"未知字段：{sorted(unknown)}")

    if "name" in fields:
        new_name = _clean_required(fields["name"], "name")
        if _name_taken(new_name, exclude_id=kb.id):
            raise ValidationError(f"name 已存在：{new_name}")
        kb.name = new_name
    if "space_id" in fields:
        kb.space_id = _resolve_space(fields["space_id"])
    if "embedding_provider" in fields:
        kb.embedding_provider = (fields["embedding_provider"] or "").strip() or None
    if "chunk_size" in fields:
        if fields["chunk_size"] is None:
            kb.chunk_size = None
        else:
            kb.chunk_size = _positive_int(fields["chunk_size"], "chunk_size")
    if "status" in fields:
        cleaned_status = (fields["status"] or "").strip() or "ready"
        if cleaned_status not in KB_STATUSES:
            raise ValidationError(
                f"status 取值非法：{cleaned_status}（应为 {sorted(KB_STATUSES)} 之一）"
            )
        kb.status = cleaned_status

    db.session.commit()
    return kb.to_dict()


def delete_kb(kb_id: int) -> None:
    kb = _get_or_raise(kb_id)
    db.session.delete(kb)
    db.session.commit()


# ============================================================
# AD-03：文档上传 → 解析 → 切块入 knowledge_chunks
# ============================================================

def _split_chunks(text: str, chunk_size: int) -> list[str]:
    """按字符数贪心切窗（design D4：零依赖、不做词/句边界，语义损失可接受）。"""
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


def upload_document(kb_id: int, filename, data: bytes) -> dict:
    """受理 .txt/.md 并切块写入；同库同名整体替换、异名保留（design D4）。"""
    kb = _get_or_raise(kb_id)
    if kb.status == "disabled":
        raise ValidationError("知识库已停用，无法上传（请先将 status 改回 ready/draft）")

    safe_name = os.path.basename((filename or "").replace("\\", "/")).strip()
    if not safe_name:
        raise ValidationError("文件名缺失")
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in _TXT_EXTENSIONS:
        raise ValidationError(
            f"暂不支持 {ext or '无扩展名'} 类型文件（本期仅支持 .txt/.md；pdf/docx 留待 P1）"
        )
    try:
        # utf-8-sig 解码会自动去掉开头的 UTF-8 BOM（Windows 记事本常带），无需手工 strip
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationError("文件不是有效的 UTF-8 文本，无法解析（请转存为 UTF-8）") from None

    chunk_size = kb.chunk_size or 400
    chunks = _split_chunks(text, chunk_size)

    # 单事务：删掉本库中该文件名的旧切块 → 插入本次全部新切块（其它文件行原样保留）
    old_rows = db.session.execute(
        select(KnowledgeChunk).where(KnowledgeChunk.kb_id == kb.id)
    ).scalars().all()
    for row in old_rows:
        if (row.meta or {}).get("filename") == safe_name:
            db.session.delete(row)
    for idx, content in enumerate(chunks):
        db.session.add(KnowledgeChunk(
            kb_id=kb.id,
            file_id=None,  # P6 资料库文件行回填前恒 NULL
            content=content,
            meta={"filename": safe_name, "chunk_index": idx, "chars": len(content)},
            embedding=None,  # 向量化本期关闭
        ))
    db.session.commit()
    return {
        "kb_id": kb.id,
        "filename": safe_name,
        "chars": len(text),
        "chunk_count": len(chunks),
    }


# ============================================================
# AD-03：关键词检索（默认检索；向量化 P1）
# ============================================================

def _score_kb(kb: KnowledgeBase, q: str) -> list[dict]:
    """对单个知识库全部切块做关键词计分（返回含来源 kb_name/kb_id 的降序命中）。"""
    # 分词：空白切出的词 + 整句各计一次（design D5：中文整句短语也能精确子串命中）
    tokens = list(dict.fromkeys(t for t in re.split(r"\s+", q) if t))
    rows = db.session.execute(
        select(KnowledgeChunk)
        .where(KnowledgeChunk.kb_id == kb.id)
        .order_by(KnowledgeChunk.id.asc())
    ).scalars().all()

    hits: list[dict] = []
    for chunk in rows:
        content = chunk.content or ""
        score = content.count(q) * 2 + sum(content.count(t) for t in tokens)
        if score <= 0:
            continue
        meta = chunk.meta or {}
        hits.append({
            "kb_id": kb.id,
            "kb_name": kb.name,
            "chunk_id": chunk.id,
            "content": content,
            "filename": meta.get("filename"),
            "chunk_index": meta.get("chunk_index"),
            "score": score,
        })
    hits.sort(key=lambda r: (-r["score"], r["chunk_index"] or 0))
    return hits


def _resolve_limit(top_k) -> int:
    """top_k 收敛到 [1, _TOP_K_CAP]（单库/跨库共用同一口径）。"""
    return min(
        _positive_int(top_k, "top_k") if top_k is not None else 5,
        _TOP_K_CAP,
    )


def search_kb(kb_id: int, query=None, top_k=None) -> list[dict]:
    """关键词命中计分 top-k：返回分数降序切块（content + 来源 kb_name/filename + chunk_index + score）。"""
    kb = _get_or_raise(kb_id)
    if kb.status == "disabled":
        raise ValidationError("知识库已停用，无法检索（请先将 status 改回 ready/draft）")

    q = (query or "").strip()
    if not q:
        raise ValidationError("query 不能为空")
    return _score_kb(kb, q)[:_resolve_limit(top_k)]


def search_kbs(kb_ids, query=None, top_k=None) -> list[dict]:
    """skill-kb-callable：跨库归并关键词检索（复用 _score_kb 单库计分，不引向量库）。

    对每个给定库取计分 top（各库候补上界 = 返回上限，保证全局 top 不漏），再按
    (-score, kb_id, chunk_index) 全局归并取 top-k。仅就绪（status='ready'）且存在的库参与；
    停用/不存在库静默跳过（装配面已门控，此为双保险，检索工具永不因此报错）。
    """
    q = (query or "").strip()
    if not q:
        raise ValidationError("query 不能为空")
    limit = _resolve_limit(top_k)

    merged: list[dict] = []
    for kb_id in kb_ids:
        kb = db.session.get(KnowledgeBase, kb_id)
        if kb is None or kb.status != "ready":
            continue
        merged.extend(_score_kb(kb, q)[:limit])
    merged.sort(key=lambda r: (-r["score"], r["kb_id"], r["chunk_index"] or 0))
    return merged[:limit]
