# 模型/提示词服务（design D6）：providers / configs / prompts 三个子区共处一文件。
# 分层对齐 CLAUDE.md §3：校验与业务在 service，API 只转发。子区按任务顺序扩展。
from sqlalchemy import desc, func, select

from .. import crypto
from ..extensions import db
from ..models import (
    MODEL_PROVIDER_TYPES,
    ModelConfig,
    ModelProvider,
    PromptTemplate,
    Task,
)
from .errors import NotFoundError, ValidationError

# ============================================================
# 子区 1：模型供应商（MD-04）
# ============================================================

def _provider_to_out(provider: ModelProvider) -> dict:
    """供应商出口：模型公开字段 + 脱敏 api_key（永不带密文/明文，design D2）。"""
    out = provider.to_dict()
    out["api_key"] = crypto.mask_key(provider.api_key_enc)
    return out


def _clean_required(value: str | None, field: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValidationError(f"{field} 不能为空")
    return cleaned


def list_providers() -> list[dict]:
    rows = db.session.execute(
        select(ModelProvider).order_by(desc(ModelProvider.id))
    ).scalars()
    return [_provider_to_out(p) for p in rows]


def get_provider_or_raise(provider_id: int) -> ModelProvider:
    provider = db.session.get(ModelProvider, provider_id)
    if provider is None:
        raise NotFoundError("模型供应商不存在")
    return provider


def get_provider(provider_id: int) -> dict:
    return _provider_to_out(get_provider_or_raise(provider_id))


def create_provider(
    name: str | None,
    type: str | None,
    base_url: str | None,
    default_model: str | None = None,
    api_key: str | None = None,
) -> dict:
    cleaned_name = _clean_required(name, "name")
    typ = (type or "").strip()
    if typ not in MODEL_PROVIDER_TYPES:
        raise ValidationError(
            f"type 取值非法：{typ}（应为 {sorted(MODEL_PROVIDER_TYPES)} 之一）"
        )
    cleaned_url = _clean_required(base_url, "base_url")

    exists = db.session.execute(
        select(ModelProvider).where(ModelProvider.name == cleaned_name)
    ).scalar_one_or_none()
    if exists is not None:
        raise ValidationError(f"供应商 name 已存在：{cleaned_name}")

    provider = ModelProvider(
        name=cleaned_name,
        type=typ,
        base_url=cleaned_url,
        default_model=(default_model or "").strip() or None,
        # 明文 api_key 仅此处出现一次：立刻加密落库，任何出口只出掩码（design D2）
        api_key_enc=crypto.encrypt(api_key) if (api_key or "").strip() else None,
    )
    db.session.add(provider)
    db.session.commit()
    return _provider_to_out(provider)


def update_provider(
    provider_id: int,
    name=None,
    type=None,
    base_url=None,
    default_model=None,
    api_key=None,
) -> dict:
    """部分更新：仅处理非 None 字段；提供新 api_key 才重加密，否则保留原密文。"""
    provider = get_provider_or_raise(provider_id)
    updates: dict = {}

    if name is not None:
        updates["name"] = _clean_required(name, "name")
    if type is not None:
        typ = (type or "").strip()
        if typ not in MODEL_PROVIDER_TYPES:
            raise ValidationError(
                f"type 取值非法：{typ}（应为 {sorted(MODEL_PROVIDER_TYPES)} 之一）"
            )
        updates["type"] = typ
    if base_url is not None:
        updates["base_url"] = _clean_required(base_url, "base_url")
    if default_model is not None:
        updates["default_model"] = (default_model or "").strip() or None
    if api_key is not None:
        updates["api_key_enc"] = (
            crypto.encrypt(api_key) if (api_key or "").strip() else None
        )

    if not updates:
        raise ValidationError("没有可更新的字段")

    for key, value in updates.items():
        setattr(provider, key, value)
    db.session.commit()
    return _provider_to_out(provider)


def delete_provider(provider_id: int) -> None:
    """删除供应商；被任一 ModelConfig 引用时拒绝（防悬空绑定，DB RESTRICT 兜底）。"""
    provider = get_provider_or_raise(provider_id)
    ref_count = db.session.execute(
        select(func.count())
        .select_from(ModelConfig)
        .where(ModelConfig.provider_id == provider_id)
    ).scalar()
    if ref_count:
        raise ValidationError("该供应商已被任务绑定，无法删除")
    db.session.delete(provider)
    db.session.commit()


# ============================================================
# 子区 2：任务绑模型参数（MD-01）
# ============================================================

def _float_range(value, field: str, lo: float, hi: float) -> float | None:
    """0–2 之类浮点白名单；None=不提供。"""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} 必须为 {lo}–{hi} 的数字") from None
    if not lo <= v <= hi:
        raise ValidationError(f"{field} 必须介于 {lo}–{hi}")
    return v


def _positive_int(value, field: str) -> int | None:
    """正整数白名单（max_tokens/timeout）；None=不提供/用默认。"""
    if value is None:
        return None
    try:
        v = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} 必须为正整数") from None
    if v <= 0:
        raise ValidationError(f"{field} 必须为正整数")
    return v


def _get_task_or_raise(task_id: int) -> Task:
    task = db.session.get(Task, task_id)
    if task is None:
        raise NotFoundError("任务不存在")
    return task


def _resolve_provider(provider_id) -> ModelProvider:
    """绑定时的供应商校验：缺失走 400（spec：provider_id 不存在→400，区别于单查 404）。"""
    provider = db.session.get(ModelProvider, provider_id)
    if provider is None:
        raise ValidationError("provider_id 不存在")
    return provider


def _get_config(task_id: int) -> ModelConfig | None:
    return db.session.execute(
        select(ModelConfig).where(ModelConfig.task_id == task_id)
    ).scalar_one_or_none()


def get_task_config(task_id: int) -> dict:
    task = _get_task_or_raise(task_id)
    config = _get_config(task.id)
    if config is None:
        raise NotFoundError("任务尚未绑定模型配置")
    return config.to_dict()


def set_task_config(
    task_id: int,
    provider_id=None,
    model_name=None,
    temperature=None,
    max_tokens=None,
    timeout=None,
) -> tuple[dict, bool]:
    """POST 语义：为该任务 upsert 一份 ModelConfig（每任务唯一）。

    返回 (dict, created)：首建 created=True（→201），替换已存在 created=False（→200）。
    新配置缺省：model_name 取 provider.default_model、temperature=1.0、timeout=60。
    同时写回 tasks.model_config_id（运行时便捷指针，design D3）——同一事务，杜绝漂移。
    """
    task = _get_task_or_raise(task_id)
    if provider_id is None:
        raise ValidationError("provider_id 必填")
    provider = _resolve_provider(provider_id)

    temp = _float_range(temperature, "temperature", 0.0, 2.0)
    max_tok = _positive_int(max_tokens, "max_tokens")
    to = _positive_int(timeout, "timeout")
    name = (model_name or "").strip() or None

    existing = _get_config(task.id)
    if existing is not None:
        created = False
        config = existing
        config.provider_id = provider.id
        if name is not None:
            config.model_name = name
        if temp is not None:
            config.temperature = temp
        if max_tok is not None:
            config.max_tokens = max_tok
        if to is not None:
            config.timeout = to
    else:
        created = True
        config = ModelConfig(
            task_id=task.id,
            provider_id=provider.id,
            model_name=name or provider.default_model,
            temperature=temp if temp is not None else 1.0,
            max_tokens=max_tok,
            timeout=to if to is not None else 60,
        )
        db.session.add(config)

    db.session.flush()  # 先落 id 再写回任务指针
    task.model_config_id = config.id
    db.session.commit()
    return config.to_dict(), created


def update_task_config(task_id: int, **fields) -> dict:
    """PATCH 语义：仅对已绑定任务做部分调参；未绑定请走 POST。"""
    task = _get_task_or_raise(task_id)
    config = _get_config(task.id)
    if config is None:
        raise ValidationError("任务尚未绑定模型，请用 POST 绑定")

    applied = False
    if "provider_id" in fields and fields["provider_id"] is not None:
        config.provider_id = _resolve_provider(fields["provider_id"]).id
        applied = True
    if "model_name" in fields:
        config.model_name = (fields["model_name"] or "").strip() or None
        applied = True
    if "temperature" in fields and fields["temperature"] is not None:
        config.temperature = _float_range(fields["temperature"], "temperature", 0.0, 2.0)
        applied = True
    if "max_tokens" in fields and fields["max_tokens"] is not None:
        config.max_tokens = _positive_int(fields["max_tokens"], "max_tokens")
        applied = True
    if "timeout" in fields and fields["timeout"] is not None:
        config.timeout = _positive_int(fields["timeout"], "timeout")
        applied = True

    if not applied:
        raise ValidationError("没有可更新的字段")

    task.model_config_id = config.id
    db.session.commit()
    return config.to_dict()


# ============================================================
# 子区 3：提示词库（MD-03，name=版本链标识）
# ============================================================

def _head_for_name(name: str) -> PromptTemplate | None:
    """name 链头 = version 最大的一行。"""
    return db.session.execute(
        select(PromptTemplate)
        .where(PromptTemplate.name == name)
        .order_by(desc(PromptTemplate.version))
        .limit(1)
    ).scalar_one_or_none()


def list_prompts(category=None, domain=None, name=None) -> list[dict]:
    """每个 name 只回链头；支持 category/domain/name 过滤。

    在 Python 侧分组取最大版本：行数小（提示词库），避免 SQL 窗口函数换复杂度。
    """
    stmt = select(PromptTemplate).order_by(PromptTemplate.version.asc())
    if category:
        stmt = stmt.where(PromptTemplate.category == category)
    if domain:
        stmt = stmt.where(PromptTemplate.domain == domain)
    if name:
        stmt = stmt.where(PromptTemplate.name == name)

    heads: dict[str, PromptTemplate] = {}
    for row in db.session.execute(stmt).scalars():
        prev = heads.get(row.name)
        if prev is None or row.version > prev.version:
            heads[row.name] = row
    ordered = sorted(heads.values(), key=lambda r: r.id, reverse=True)
    return [r.to_dict() for r in ordered]


def create_prompt(
    name: str | None,
    category: str | None,
    content: str | None,
    domain: str | None = None,
) -> dict:
    """保存提示词：name 首现 version=1；已存在则以链头为父升一版（design D5）。"""
    cleaned_name = (name or "").strip()
    cleaned_category = (category or "").strip()
    cleaned_content = (content or "").strip()
    if not cleaned_name:
        raise ValidationError("name 不能为空")
    if not cleaned_category:
        raise ValidationError("category 不能为空")
    if not cleaned_content:
        raise ValidationError("content 不能为空")

    head = _head_for_name(cleaned_name)
    prompt = PromptTemplate(
        name=cleaned_name,
        category=cleaned_category,
        domain=(domain or "").strip() or None,
        content=cleaned_content,
        version=(head.version + 1) if head is not None else 1,
        parent_id=head.id if head is not None else None,
    )
    db.session.add(prompt)
    db.session.commit()
    return prompt.to_dict()


def get_prompt(prompt_id: int) -> dict:
    return _get_prompt_or_raise(prompt_id).to_dict()


def _get_prompt_or_raise(prompt_id: int) -> PromptTemplate:
    prompt = db.session.get(PromptTemplate, prompt_id)
    if prompt is None:
        raise NotFoundError("提示词不存在")
    return prompt


def update_prompt(prompt_id: int, **fields) -> dict:
    """对链头「再保存」：以该行为父生成新版本（非链头→400 防分叉，name 不可变）。"""
    if not fields:
        raise ValidationError("没有可更新的字段")
    if "name" in fields:
        raise ValidationError("name 为版本链标识，不可修改")

    row = _get_prompt_or_raise(prompt_id)
    head = _head_for_name(row.name)
    if head is None or head.id != row.id:
        raise ValidationError("只能对最新版本再保存，历史版本请先取回链头")

    # 未提供的字段沿用旧值；domain 显式给 null 视为清除
    content = (fields.get("content", row.content) or "").strip()
    if not content:
        raise ValidationError("content 不能为空")
    category = (fields.get("category", row.category) or "").strip() or row.category
    if "domain" in fields:
        domain = (fields["domain"] or "").strip() or None
    else:
        domain = row.domain

    new_prompt = PromptTemplate(
        name=row.name,
        category=category,
        domain=domain,
        content=content,
        version=row.version + 1,
        parent_id=row.id,
    )
    db.session.add(new_prompt)
    db.session.commit()
    return new_prompt.to_dict()


def delete_prompt(prompt_id: int) -> None:
    """删除单个版本行；后代 parent_id 由 DB ON DELETE SET NULL 置空（design D5 trade-off）。"""
    prompt = _get_prompt_or_raise(prompt_id)
    db.session.delete(prompt)
    db.session.commit()
