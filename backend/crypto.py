# 密钥加解密工具（CLAUDE.md §3：密钥永不明文入库，用 cryptography.Fernet）。
# 职责：主密钥解析/自动生成持久化 + encrypt/decrypt/mask。
# 关键点（design D1）：
#   - 密钥只从环境变量 LINGSHU_MASTER_KEY 读（根 .env 已由 backend/__init__.py 加载）；
#   - 两者皆缺时生成一把并追加写根 .env，保证重启后旧密文仍可解；
#   - 惰性初始化：导入本模块不做副作用，首次 encrypt/decrypt 才解析/生成密钥。
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

# 仓库根 = backend/crypto.py 的上两级；根 .env 在 gitignore 内（见设计 D1）
_ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"

_fernet: Fernet | None = None  # 模块级缓存，首次解析后复用


def _load_or_create_key() -> Fernet:
    """取主密钥：LINGSHU_MASTER_KEY → 根 .env → 生成并持久化。"""
    global _fernet
    if _fernet is not None:
        return _fernet

    env_key = os.getenv("LINGSHU_MASTER_KEY", "").strip()
    if env_key:
        _fernet = Fernet(env_key.encode())
        return _fernet

    # 缺主密钥：生成一把并追加写根 .env，让后续进程启动时能读到（否则重启即不可解）
    key = Fernet.generate_key()
    try:
        with open(_ROOT_ENV, "a", encoding="utf-8") as f:
            f.write(f"\nLINGSHU_MASTER_KEY={key.decode()}\n")
    except OSError:
        # 只读环境：退化为进程内临时 key（本地开发通常不会走到）
        print("[crypto] 无法写入 .env，使用进程内临时主密钥，重启后旧密文将不可解")
    _fernet = Fernet(key)
    return _fernet


def encrypt(plain: str) -> str:
    """明文 → Fernet token 文本。"""
    return _load_or_create_key().encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    """Fernet token 文本 → 明文；token 非法时抛出 ValueError。"""
    try:
        return _load_or_create_key().decrypt(token.encode()).decode()
    except InvalidToken:
        raise ValueError("密钥无法解密（可能已更换 LINGSHU_MASTER_KEY）") from None


def mask_key(token_or_none: str | None) -> str | None:
    """出口脱敏：仅展示末 4 位。密文空→None；解密失败→全掩码。"""
    if not token_or_none:
        return None
    try:
        plain = decrypt(token_or_none)
    except ValueError:
        return "****"
    tail = plain[-4:] if len(plain) > 4 else plain
    return f"****{tail}"
