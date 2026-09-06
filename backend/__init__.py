# 灵枢后端包。
# 顶层加载仓库根 .env：让 config.py 读到的环境变量在 `flask --app backend.app` 下稳定生效。
from pathlib import Path

from dotenv import load_dotenv

_ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ROOT_ENV, override=False)  # 已存在的系统变量优先，.env 只补缺省
