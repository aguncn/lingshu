# 运维专家档案快照装配（C5 expert-profile）：把一份档案「套用」到一个任务上。
# 语义（沿旧模板「选 preset → 覆盖挂载」路径，归属换到专家档案）：
#   - 四类 caps（skills/mcps/kbs/experts）全量覆盖写：experts=[档案自身]（档案 = 任务人设提供者），
#     其余各类取档案预设中「现存且可用」实体的 id；已删除/停用/未就绪引用进 skipped 不中断。
#   - 档案预设资料库（preset_library → LibraryFile）补挂为任务引用：已引用跳过（幂等）、缺失补挂，
#     只增不拆——不动任务手工加的其它资料引用（attach_library 只有追加、无覆盖语义）。
#   - 默认模型：档案给了 default_provider_id 才把任务模型绑定落成该供应商（default_model_name
#     空则取该供应商 default_model）；否则不碰任务既有绑定，避免套档案抢走用户显式选的模型。
# 复用点：capability.set_task_caps（覆盖写）、library_service.attach_library（资料引用）、
#         model_service.set_task_config（任务模型绑定）、registry_expert 的实体写校验。
from sqlalchemy import select

from ..extensions import db
from ..models import (
    Expert,
    FileRecord,
    KnowledgeBase,
    LibraryFile,
    MCPConnector,
    ModelProvider,
    Skill,
)
from . import capability, library_service, model_service
from .errors import NotFoundError, ValidationError
from .task_service import get_task_or_raise

# 档案预设分类 -> (实体模型, 「可用」谓词)。口径与挂载/注册中心一致：
# skill/mcp 看 enabled；知识库无 enabled、以 status=='ready' 表示可检索。
# experts 走独立门控（档案自身停用 → 400），不在此过滤。
_ACTIVE = {
    "skills": (Skill, lambda e: bool(e.enabled)),
    "mcps": (MCPConnector, lambda e: bool(e.enabled)),
    "kbs": (KnowledgeBase, lambda e: e.status == "ready"),
}


def _resolve_active(expert: Expert) -> tuple[dict, list[dict]]:
    """把档案四类预设解析为「现存且可用」id 清单 + 被跳过引用明细。

    返回 (kept, skipped)：kept 形如 {skills:[..], mcps:[..], kbs:[..]}（experts 单独由调用方加入）；
    已删实体与停用/未就绪实体按 reason 区分，绝不因失效引用中断整份套用（沿用旧模板 apply D3）。
    """
    kept: dict = {}
    skipped: list[dict] = []
    presets = {
        "skills": expert.preset_skills or [],
        "mcps": expert.preset_mcp or [],
        "kbs": expert.preset_kb or [],
    }
    for cat, raw_ids in presets.items():
        model, active = _ACTIVE[cat]
        if not raw_ids:
            kept[cat] = []
            continue
        objects = {
            o.id: o
            for o in db.session.execute(
                select(model).where(model.id.in_(raw_ids))
            ).scalars()
        }
        ids: list[int] = []
        for pid in raw_ids:
            entity = objects.get(pid)
            if entity is None:
                skipped.append({"category": cat, "id": pid, "reason": "实体已删除"})
                continue
            if not active(entity):
                reason = "知识库未就绪" if cat == "kbs" else "实体已停用"
                skipped.append({"category": cat, "id": pid, "reason": reason})
                continue
            ids.append(pid)
        kept[cat] = ids
    return kept, skipped


def _snapshot_library(task_id: int, preset: list[int]) -> dict:
    """补挂档案预设资料库 → 返回 {added:[..], existing:[..], skipped:[...]}。只增不拆。"""
    preset = preset or []
    if not preset:
        return {"added": [], "existing": [], "skipped": []}
    # 现存库文件（预设里被删过的 → skipped deleted）
    existing_lib = set(
        db.session.execute(select(LibraryFile.id).where(LibraryFile.id.in_(preset)))
        .scalars()
    )
    # 任务已引用（幂等：这些不重复挂）
    already = set(
        db.session.execute(
            select(FileRecord.library_file_id)
            .where(
                FileRecord.task_id == task_id,
                FileRecord.library_file_id.in_(preset),
            )
        ).scalars()
    )
    added: list[int] = []
    existing: list[int] = []
    skipped: list[dict] = []
    for lid in preset:
        if lid in already:
            existing.append(lid)
            continue
        if lid not in existing_lib:
            skipped.append({"category": "library", "id": lid, "reason": "资料库文件已删除"})
            continue
        library_service.attach_library(task_id, lid)  # 未引用且文件在 → 补挂（单行 commit）
        added.append(lid)
    return {"added": added, "existing": existing, "skipped": skipped}


def apply_expert_profile(task_id: int, expert_id) -> dict:
    """POST /api/tasks/<id>/expert/apply：把运维专家档案快照装配到任务。

    校验：任务不存在 → 404；档案不存在 → 404；档案停用 → 400（均零副作用）。
    返回 {task_id, expert_id, mounted, skipped, library, model} 供前端提示装配结果。
    """
    get_task_or_raise(task_id)  # 404 语义
    expert = db.session.get(Expert, expert_id)
    if expert is None:
        raise NotFoundError("运维专家不存在")
    if not expert.enabled:
        raise ValidationError(f"运维专家「{expert.name}」已停用，无法套用")

    # 1) 四类 caps 全量覆盖（experts=[档案自身]；各类 preset 只保留可用实体）
    kept, skipped = _resolve_active(expert)
    caps = capability.set_task_caps(
        task_id,
        {
            "skills": kept["skills"],
            "mcps": kept["mcps"],
            "kbs": kept["kbs"],
            "experts": [expert.id],
        },
    )

    # 2) 预设资料库补挂（幂等、只增）
    library = _snapshot_library(task_id, expert.preset_library or [])

    # 3) 默认模型（仅档案显式给了供应商才落绑定）
    model_out = None
    if expert.default_provider_id:
        provider = db.session.get(ModelProvider, expert.default_provider_id)
        if provider is not None:
            name = (expert.default_model_name or "").strip() or provider.default_model
            config, _created = model_service.set_task_config(
                task_id, provider_id=provider.id, model_name=name or None
            )
            model_out = {"provider_id": config["provider_id"], "model_name": config["model_name"]}

    return {
        "task_id": task_id,
        "expert_id": expert.id,
        # mounted 收敛为四类 id（去掉 caps 里冗余的 task_id）
        "mounted": {cat: caps[cat] for cat in ("skills", "mcps", "kbs", "experts")},
        "skipped": skipped,
        "library": library,
        "model": model_out,
    }
