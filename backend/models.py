# 全部业务实体的 SQLAlchemy 声明（对齐设计 §5.2 字段表 + 迁移 0001_spaces_tasks.sql）。
# 注意：SQLite 建表走 backend/migrations/*.sql（见 CLAUDE.md §3），此处模型只做映射。
# 枚举以字符串列存储，取值白名单在本文件顶部常量集中维护，API/service 层据此校验。
from __future__ import annotations

from datetime import datetime, timezone

from .extensions import db


def _utcnow() -> str:
    """统一 UTC ISO 时间文本（与 schema_version.applied_at / 迁移种子一致）。"""
    return datetime.now(timezone.utc).isoformat()


# —— 受控取值（字符串列白名单）——
VISIBILITIES = {"private", "team", "public"}
MEMBERSHIP_ROLES = {"Owner", "Editor", "Viewer"}
TASK_TYPES = {"fault", "change", "alert", "general"}  # 本期最小白名单，P9 十二域再扩展
TASK_STATUSES = {"open", "in_progress", "done"}
USER_ROLES = {"owner"}
# 模型供应商 type 白名单（§5.2 ModelProvider.type；local=本地/占位，无需密钥）
MODEL_PROVIDER_TYPES = {"openai", "deepseek", "dashscope", "local"}
# 常用任务类型预设（MD-02）：seed 成 PromptTemplate(category=PRESET_CATEGORY)，供建任务/细节栏开箱选用
PRESET_CATEGORY = "task-preset"
PRESET_TASK_NAMES = ("写文档", "写代码", "数据分析", "排障")
# 能力实体取值白名单（P4 仅落 schema，P5 registry-center 在此之上定义并扩充值域）
MCP_TRANSPORTS = {"stdio", "http"}  # §5.2 AD-02：MCP 传输方式二选一
KB_STATUSES = {"draft", "ready", "disabled"}  # AD-03：seed 'ready'=可检索；解析/上架生命周期由 P5 细化
EXPERT_ROLES = {"ops-sme", "general"}  # AD-04：人设领域短标签（单专家 demo，多专家协作 P1 再扩充）
# —— P9 十二运维场景域（设计 §8 表）：受控枚举，(domain 键, 展示名) 有序元组 ——
# 域键即 prompts/scenarios/<domain>.md 文件名与 Task.scenario_domain 取值；此处集中维护，
# models 校验 / scenario api / runtime 注入 / seed 共用同一来源，避免四处硬编码漂移。
# 顺序固定 = 列表接口/前端分类的展示序（对齐 §8 表自上而下）。
SCENARIO_DOMAINS = (
    ("monitor-inspection", "监控巡检"),
    ("log-triage", "日志隐患"),
    ("db-performance", "数据库性能排查"),
    ("middleware-setup", "中间件安装配置"),
    ("alert", "告警"),
    ("fault-diagnosis", "故障诊断"),
    ("change-risk", "变更风险"),
    ("capacity-forecast", "容量预测"),
    ("cmdb-governance", "CMDB 数据治理"),
    ("kb-qa", "知识库问答"),
    ("runbook-generation", "应急预案生成"),
    ("ops-scripting", "运维脚本编写"),
)
SCENARIO_KEYS = {key for key, _label in SCENARIO_DOMAINS}


class TimestampMixin:
    # 不用 DB DEFAULT，由 ORM 写入统一时间源，避免 SQLite 时区/精度漂移
    created_at = db.Column(db.String(32), nullable=False, default=_utcnow)
    updated_at = db.Column(
        db.String(32), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class User(TimestampMixin, db.Model):
    """用户。单人项目至少一个内置管理员（username=admin），迁移种子写入。"""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), nullable=False, unique=True)
    display_name = db.Column(db.String(128))
    role = db.Column(db.String(16), nullable=False, default="owner")

    memberships = db.relationship(
        "Membership", back_populates="user", passive_deletes=True
    )
    owned_spaces = db.relationship(
        "Space", back_populates="owner", passive_deletes=True
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
        }


class Space(TimestampMixin, db.Model):
    """隔离与协作边界。目录：data/spaces/<space_id>/。"""

    __tablename__ = "spaces"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.String(512))
    owner_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    visibility = db.Column(db.String(16), nullable=False, default="private")

    owner = db.relationship("User", back_populates="owned_spaces")
    memberships = db.relationship(
        "Membership", back_populates="space", passive_deletes=True
    )
    tasks = db.relationship("Task", back_populates="space", passive_deletes=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "owner_id": self.owner_id,
            "visibility": self.visibility,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class Membership(TimestampMixin, db.Model):
    """空间成员与角色（Owner/Editor/Viewer），(space,user) 唯一。"""

    __tablename__ = "memberships"
    __table_args__ = (db.UniqueConstraint("space_id", "user_id"),)

    id = db.Column(db.Integer, primary_key=True)
    space_id = db.Column(
        db.Integer,
        db.ForeignKey("spaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role = db.Column(db.String(16), nullable=False, default="Viewer")

    space = db.relationship("Space", back_populates="memberships")
    user = db.relationship("User", back_populates="memberships")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "space_id": self.space_id,
            "user_id": self.user_id,
            "role": self.role,
        }


class Task(TimestampMixin, db.Model):
    """最小运行单元，必属一个空间。目录：data/spaces/<space_id>/<task_id>/（id 命名，见设计 D1）。"""

    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    space_id = db.Column(
        db.Integer, db.ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    title = db.Column(db.String(256), nullable=False)
    task_type = db.Column(db.String(32), nullable=False)
    status = db.Column(db.String(16), nullable=False, default="open")
    scenario_domain = db.Column(db.String(64))  # 十二域占位，值域由 P9 场景模板定义
    visibility = db.Column(db.String(16), nullable=False, default="private")
    # 模型占位：本表对应 P3 的 model_configs 尚未创建，故为普通整数列、无 FK
    model_config_id = db.Column(db.Integer)

    space = db.relationship("Space", back_populates="tasks")
    file_records = db.relationship(
        "FileRecord", back_populates="task", passive_deletes=True
    )
    # 能力挂载关联（P4）：passive_deletes=True 让「删任务」交给 DB 级联清 task_* 行，
    # ORM 不做 load+置空（task_id NOT NULL，ORM 侧处理反而会报错）。
    skill_mounts = db.relationship(
        "TaskSkill", back_populates="task", passive_deletes=True
    )
    mcp_mounts = db.relationship(
        "TaskMcp", back_populates="task", passive_deletes=True
    )
    kb_mounts = db.relationship(
        "TaskKb", back_populates="task", passive_deletes=True
    )
    expert_mounts = db.relationship(
        "TaskExpert", back_populates="task", passive_deletes=True
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "space_id": self.space_id,
            "title": self.title,
            "task_type": self.task_type,
            "status": self.status,
            "scenario_domain": self.scenario_domain,
            "visibility": self.visibility,
            "model_config_id": self.model_config_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class FileRecord(TimestampMixin, db.Model):
    """文件元数据；实体文件落 data/spaces/<space_id>/<task_id>/，path 存任务目录内相对路径。"""

    __tablename__ = "file_records"

    id = db.Column(db.Integer, primary_key=True)
    space_id = db.Column(
        db.Integer, db.ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    task_id = db.Column(
        db.Integer, db.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    filename = db.Column(db.String(256), nullable=False)
    path = db.Column(db.String(512), nullable=False)
    mime = db.Column(db.String(128))
    size = db.Column(db.Integer, nullable=False, default=0)
    # 资料库引用（P6 library LB-01）：非空时该条记录是「指向 LibraryFile 的引用」——
    # 字节归 data/library/、任务目录不落盘，故 path 存空串（DB NOT NULL 兼容，见 0005）；
    # 不加 FK 不强绑（沿 knowledge_chunks.file_id 先例），引用完整性由服务层 DELETE 守（design D4/D10）。
    library_file_id = db.Column(db.Integer)

    task = db.relationship("Task", back_populates="file_records")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "space_id": self.space_id,
            "task_id": self.task_id,
            "filename": self.filename,
            "path": self.path,
            "mime": self.mime,
            "size": self.size,
            "library_file_id": self.library_file_id,
        }


class LibraryFile(TimestampMixin, db.Model):
    """资料库文件（P6 library LB-01，0005 建表）：跨任务可复用的集中文件资产。

    space_id 可空 = 全局库；实体落 data/library/<path>（path 存 uuid 存储键，任何 API
    出口都不外泄）；shared 仅作分享标记，其可见性门控语义归 P8（有鉴权后再定谁能见）。
    本表与任务/知识库无 FK 强绑：任务只经 FileRecord.library_file_id 引用（字节不复制）；
    知识库切块 file_id 回填也归 P8，本提案保持解耦。
    """

    __tablename__ = "library_files"

    id = db.Column(db.Integer, primary_key=True)
    space_id = db.Column(
        db.Integer,
        # 删空间 → 库文件自动降级为全局（SET NULL），磁盘不动、不悬空其它空间任务引用
        db.ForeignKey("spaces.id", ondelete="SET NULL"),
        nullable=True,
    )
    filename = db.Column(db.String(256), nullable=False)
    path = db.Column(db.String(64), nullable=False)  # data/library 内存储键（uuid hex）
    mime = db.Column(db.String(128))
    size = db.Column(db.Integer, nullable=False, default=0)
    shared = db.Column(db.Boolean, nullable=False, default=False)
    shared_at = db.Column(db.String(32))  # 最近一次置 true 的时刻；置 false 不清空（保留追溯）

    def to_dict(self) -> dict:
        # 注意：绝不外泄存储键 path，只给展示/下载所需的元数据
        return {
            "id": self.id,
            "space_id": self.space_id,
            "filename": self.filename,
            "size": self.size,
            "mime": self.mime,
            "shared": self.shared,
            "shared_at": self.shared_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ModelProvider(TimestampMixin, db.Model):
    """模型供应商（OpenAI 兼容端点）。api_key_enc 存 Fernet 密文，模型层不透明文。"""

    __tablename__ = "model_providers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    type = db.Column(db.String(32), nullable=False, default="openai")
    base_url = db.Column(db.String(512), nullable=False)
    default_model = db.Column(db.String(128))
    api_key_enc = db.Column(db.String(1024))  # Fernet 密文；local 或未配置时为空

    def to_dict(self) -> dict:
        # 刻意不含 api_key_enc / 解密值：掩码由 service 出口组装（design D2）
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "base_url": self.base_url,
            "default_model": self.default_model,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ModelConfig(TimestampMixin, db.Model):
    """任务级绑模型参数。task_id 唯一=每任务至多一份配置（1:1，MD-01）。"""

    __tablename__ = "model_configs"
    __table_args__ = (db.UniqueConstraint("task_id"),)

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(
        db.Integer, db.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True
    )
    provider_id = db.Column(
        db.Integer,
        db.ForeignKey("model_providers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    model_name = db.Column(db.String(128))
    temperature = db.Column(db.Float, default=1.0)
    max_tokens = db.Column(db.Integer)  # 空=用供应商/模型默认
    timeout = db.Column(db.Integer, default=60)  # 秒
    is_default = db.Column(db.Boolean, default=False)  # 未来每空间默认模型用，本期恒 False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "provider_id": self.provider_id,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "is_default": self.is_default,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class PromptTemplate(TimestampMixin, db.Model):
    """提示词库。name 为版本链标识，(name,version) 唯一，parent_id 指向上一个版本。"""

    __tablename__ = "prompt_templates"
    __table_args__ = (db.UniqueConstraint("name", "version"),)

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    category = db.Column(db.String(64), nullable=False)
    domain = db.Column(db.String(64))
    content = db.Column(db.Text, nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    parent_id = db.Column(
        db.Integer,
        db.ForeignKey("prompt_templates.id", ondelete="SET NULL"),
        nullable=True,
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "domain": self.domain,
            "content": self.content,
            "version": self.version,
            "parent_id": self.parent_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ============================================================
# P4 能力实体（schema-only，字段对齐 §5.2；不做 CRUD，见 capability-mount design D1）
# ============================================================


class Skill(TimestampMixin, db.Model):
    """技能（CAP-01/AD-01）。skill_md 即 SKILL.md 指令文本，P8 SkillLoader 读取注入运行。"""

    __tablename__ = "skills"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    description = db.Column(db.String(512))
    skill_md = db.Column(db.Text)  # SKILL.md 全文；非空才可被装配（P5 定义编辑约束）
    version = db.Column(db.Integer, nullable=False, default=1)
    enabled = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "skill_md": self.skill_md,
            "version": self.version,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class MCPConnector(TimestampMixin, db.Model):
    """MCP 连接器（CAP-02/AD-02）。

    env/headers 可含密钥，P5 起整体 Fernet 加密：列存「整段 JSON 序列化后加密」的 token
    （与 ModelProvider.api_key_enc 同构），绝不明文入库。to_dict 不吐 env/headers，
    展示由 registry 出口只给键名（env_keys/headers_keys）。SQL 层两列本就是 TEXT，
    db.JSON → db.Text 仅为承载密文，无 DDL 迁移。
    """

    __tablename__ = "mcp_connectors"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    transport = db.Column(db.String(16), nullable=False, default="stdio")
    command = db.Column(db.String(256))  # stdio 启动命令
    args = db.Column(db.JSON)  # stdio 启动参数列表（非敏感，保持 JSON）
    env = db.Column(db.Text)  # 环境变量整段 Fernet 密文（永不出口值）
    url = db.Column(db.String(512))  # http 端点
    headers = db.Column(db.Text)  # http 鉴权头整段 Fernet 密文（永不出口值）
    trust = db.Column(db.Boolean, nullable=False, default=False)  # 信任/只读语义 P5 定义
    enabled = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self) -> dict:
        # 不含 env/headers：它们承载环境变量与鉴权信息，密钥类字段不落出口（沿用 MD provider 先例）
        return {
            "id": self.id,
            "name": self.name,
            "transport": self.transport,
            "command": self.command,
            "args": self.args,
            "url": self.url,
            "trust": self.trust,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class KnowledgeBase(TimestampMixin, db.Model):
    """知识库（CAP-03/AD-03）。space_id 为空=全局库；删空间置空（SET NULL）而非删库。"""

    __tablename__ = "knowledge_bases"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    space_id = db.Column(
        db.Integer,
        db.ForeignKey("spaces.id", ondelete="SET NULL"),
        nullable=True,
    )
    embedding_provider = db.Column(db.String(128))  # 空=默认关键词检索，向量化本期关闭
    chunk_size = db.Column(db.Integer)  # 切块字符数，POST 默认 400，可 PATCH
    status = db.Column(db.String(16), nullable=False, default="ready")

    chunks = db.relationship(
        "KnowledgeChunk", back_populates="kb", passive_deletes=True
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "space_id": self.space_id,
            "embedding_provider": self.embedding_provider,
            "chunk_size": self.chunk_size,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class KnowledgeChunk(TimestampMixin, db.Model):
    """知识库切块（AD-03，0004 建表）。meta 记 {filename, chunk_index, chars} 溯源；
    file_id 本期恒 NULL，预留指向 P6 集中资料库的文件行。embedding 向量本期 NULL。"""

    __tablename__ = "knowledge_chunks"

    id = db.Column(db.Integer, primary_key=True)
    kb_id = db.Column(
        db.Integer,
        db.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_id = db.Column(db.Integer)  # P6 资料库文件行回填前恒 NULL；无 FK 不强绑
    content = db.Column(db.Text, nullable=False)
    meta = db.Column(db.JSON)  # {"filename": str, "chunk_index": int, "chars": int}
    embedding = db.Column(db.LargeBinary)  # 向量化本期关闭，恒 NULL（P1 回填）

    kb = db.relationship("KnowledgeBase", back_populates="chunks")


class Expert(TimestampMixin, db.Model):
    """专家（CAP-04/AD-04）。composed_of 存协作子专家 id 列表（P1 多专家编排用），空=单专家。"""

    __tablename__ = "experts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    description = db.Column(db.String(512))
    system_prompt = db.Column(db.Text)  # 人设与流程；P8 作为系统提示注入
    role = db.Column(db.String(32), nullable=False, default="general")
    composed_of = db.Column(db.JSON)  # 协作子专家 id 列表
    enabled = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "role": self.role,
            "composed_of": self.composed_of,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ============================================================
# P4 任务↔能力关联表（四表同构；(task,目标) 唯一防重复挂载，双向级联，见 design D2）
# ============================================================


class TaskSkill(TimestampMixin, db.Model):
    """任务挂载技能（CAP-01）。删任务或删技能都经 DB 级联清行。"""

    __tablename__ = "task_skill"
    __table_args__ = (db.UniqueConstraint("task_id", "skill_id"),)

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(
        db.Integer, db.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    skill_id = db.Column(
        db.Integer, db.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )

    task = db.relationship("Task", back_populates="skill_mounts")


class TaskMcp(TimestampMixin, db.Model):
    """任务挂载 MCP（CAP-02）。"""

    __tablename__ = "task_mcp"
    __table_args__ = (db.UniqueConstraint("task_id", "mcp_id"),)

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(
        db.Integer, db.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    mcp_id = db.Column(
        db.Integer,
        db.ForeignKey("mcp_connectors.id", ondelete="CASCADE"),
        nullable=False,
    )

    task = db.relationship("Task", back_populates="mcp_mounts")


class TaskKb(TimestampMixin, db.Model):
    """任务挂载知识库（CAP-03）。"""

    __tablename__ = "task_kb"
    __table_args__ = (db.UniqueConstraint("task_id", "kb_id"),)

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(
        db.Integer, db.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    kb_id = db.Column(
        db.Integer,
        db.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )

    task = db.relationship("Task", back_populates="kb_mounts")


class TaskExpert(TimestampMixin, db.Model):
    """任务挂载专家（CAP-04）。"""

    __tablename__ = "task_expert"
    __table_args__ = (db.UniqueConstraint("task_id", "expert_id"),)

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(
        db.Integer, db.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    expert_id = db.Column(
        db.Integer, db.ForeignKey("experts.id", ondelete="CASCADE"), nullable=False
    )

    task = db.relationship("Task", back_populates="expert_mounts")


# ============================================================
# P8 智能体运行时（agentscope-runtime，0006 建表）
# ============================================================


class Message(TimestampMixin, db.Model):
    """单次对话历史消息（agentscope-runtime）：每任务可多条，role 限 user/assistant。

    为什么与 AuditLog 分开：消息是「对话内容」，供前端历史与模型上下文续接读回；
    审计是「运行事件」，供追溯。二者都带 task_id 归属任务、run_id 关联一次完整运行
    （见 spec「流式对话事件契约」）。run_id 空 = 任务预置提示之类非运行消息。
    content 存纯文本（SSE 文本拼接的最终内容），不存 AgentScope block 内部结构。
    """

    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(
        db.Integer,
        db.ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = db.Column(db.String(16), nullable=False)
    content = db.Column(db.Text, nullable=False)
    run_id = db.Column(db.String(64))
    model = db.Column(db.String(256))  # 运行模型展示标识（provider/model），不含密钥

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "role": self.role,
            "content": self.content,
            "run_id": self.run_id,
            "model": self.model,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class AuditLog(db.Model):
    """运行时审计（agentscope-runtime）：一次运行的 model_call/tool_call/confirm_decision。

    为什么 append-only 且只有 created_at 无 updated_at：审计行写入即不可变，
    updated_at 无意义（区别于业务实体）；列通用（action/target/result/detail 均为
    自由文本）以兼容 P10 全量写操作审计扩展——P10 再覆盖 spaces/tasks/… 写操作。
    删任务时 task_id 置空（SET NULL）保留审计追溯，不级联删除。
    """

    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(
        db.Integer,
        db.ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    run_id = db.Column(db.String(64))
    actor = db.Column(db.String(32), nullable=False)  # user / runtime / system
    action = db.Column(db.String(32), nullable=False)  # model_call / tool_call / confirm_decision
    target = db.Column(db.String(256))  # 模型标识 / 工具名 / confirm_id
    result = db.Column(db.String(32))  # success / error / denied / allow / deny ...
    detail = db.Column(db.Text)  # 可读摘要（截断/脱敏由 services/audit.py 守）
    created_at = db.Column(
        db.String(32), nullable=False, default=_utcnow
    )  # 不用 TimestampMixin：审计只记创建时刻

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "result": self.result,
            "detail": self.detail,
            "created_at": self.created_at,
        }


# ============================================================
# P9 十二运维场景域（scenario-templates，0007 建表）
# ============================================================


class ScenarioTemplate(TimestampMixin, db.Model):
    """十二运维场景域模板（P9，design D1/D3）：每域一条，域提示词 + 任务引导 + 预设装配。

    system_prompt 以 backend/prompts/scenarios/<domain>.md 为唯一来源（seed 幂等装载，
    默认不覆盖人工改动，见 scenario design D1）；preset_* 存四类能力实体 id 数组——
    注册中心实体是动态 CRUD，引用允许随时间漂移，apply 时交现存+可用实体集合并跳过失效项
    （design D3）。列用 db.JSON（SQL 层 TEXT，沿用 args/composed_of 先例），可空 = 无装配。
    """

    __tablename__ = "scenario_templates"

    id = db.Column(db.Integer, primary_key=True)
    domain = db.Column(db.String(64), nullable=False, unique=True)
    name = db.Column(db.String(64), nullable=False)  # 中文展示名（§8 表 label）
    system_prompt = db.Column(db.Text, nullable=False)  # 领域系统提示（唯一来源 .md）
    task_template = db.Column(db.Text)  # 任务引导/建任务预填文本；可空
    preset_skills = db.Column(db.JSON, nullable=False, default=list)
    preset_mcp = db.Column(db.JSON, nullable=False, default=list)
    preset_kb = db.Column(db.JSON, nullable=False, default=list)
    preset_expert = db.Column(db.JSON, nullable=False, default=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "domain": self.domain,
            "name": self.name,
            "system_prompt": self.system_prompt,
            "task_template": self.task_template,
            "preset_skills": self.preset_skills or [],
            "preset_mcp": self.preset_mcp or [],
            "preset_kb": self.preset_kb or [],
            "preset_expert": self.preset_expert or [],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
