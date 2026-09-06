# 扩展单例集中声明，避免循环 import。
# 后续 models.py 在此之上定义实体，app.py 在 create_app 里 db.init_app(app)。
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
