# Flask 应用工厂。
# `uv run flask --app backend.app run` 依赖模块级 `app` 实例；
# 测试则可用 create_app() 注入不同配置。
from flask import Flask
from flask_cors import CORS
from sqlalchemy import event

from .config import Config
from .extensions import db


def _enable_sqlite_foreign_keys(app: Flask) -> None:
    """SQLite 每个连接默认 foreign_keys=OFF。

    这里在连接建立时执行 PRAGMA foreign_keys=ON，让迁移 0001 中的
    ON DELETE CASCADE 真正生效（否则删空间/任务会静默留下孤儿子行）。
    """
    with app.app_context():
        # db.engine 属性会按需创建默认 bind 引擎；get_engine 需引擎已就绪否则 KeyError
        engine = db.engine

        @event.listens_for(engine, "connect")
        def _fk_pragma(dbapi_connection, _connection_record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()


def create_app(config_object: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    # 确保 sqlite/落盘目录先存在（见 Config.ensure_dirs 注释）
    config_object.ensure_dirs()

    # CORS：放行 Vite 开发源，仅作用于 /api/*，业务路由不带跨域心智负担
    CORS(app, resources={r"/api/*": {"origins": config_object.CORS_ORIGINS}})

    # SQLAlchemy 单例挂到应用，并让 FK 级联在 SQLite 下生效
    db.init_app(app)
    _enable_sqlite_foreign_keys(app)

    # 注册 API blueprints
    from .api.health import health_bp
    from .api.space_task import space_task_bp
    from .api.model_prompt import model_prompt_bp
    from .api.capability import capability_bp
    from .api.skills import skills_bp
    from .api.mcp_center import mcp_center_bp
    from .api.kb import kb_bp
    from .api.experts import experts_bp
    from .api.library import library_bp
    from .api.runtime import runtime_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(space_task_bp)
    app.register_blueprint(model_prompt_bp)
    app.register_blueprint(capability_bp)
    app.register_blueprint(skills_bp)
    app.register_blueprint(mcp_center_bp)
    app.register_blueprint(kb_bp)
    app.register_blueprint(experts_bp)
    app.register_blueprint(library_bp)
    app.register_blueprint(runtime_bp)

    # 轻量迁移器：建/升 schema_version 元表并执行未应用的编号迁移
    from .migrate import run_migrations

    run_migrations(config_object.SQLITE_PATH)

    return app


app = create_app()
