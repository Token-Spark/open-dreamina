"""API Key 加解密（cryptography.fernet 对称加密）。

Fernet 需要 32 字节 base64 编码密钥。配置中的 ENCRYPTION_KEY 可能不是合法的
Fernet 密钥（默认值即为示例），因此用 SHA-256 派生稳定的 Fernet 密钥，
避免本地直接运行时崩溃。
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from ..config import settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key_material = settings.encryption_key.encode("utf-8")
        # 派生 32 字节密钥后 base64 编码，作为 Fernet 合法密钥
        derived = hashlib.sha256(key_material).digest()
        fernet_key = base64.urlsafe_b64encode(derived)
        _fernet = Fernet(fernet_key)
    return _fernet


def encrypt(plaintext: str) -> str:
    """加密明文，返回可存入 DB 的字符串。"""
    if not plaintext:
        return ""
    token = _get_fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt(ciphertext: str) -> str:
    """解密；空串返回空串。失败抛出 ValueError。"""
    if not ciphertext:
        return ""
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("API Key 解密失败：密文无效或加密密钥不匹配") from e


def mask_api_key(api_key: str) -> str:
    """脱敏显示：仅显示前 4 + 后 4，中间以 **** 代替。

    短 key 直接返回 ****。
    """
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "****"
    return f"{api_key[:4]}****{api_key[-4:]}"
