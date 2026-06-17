"""Thin wrapper re-using the ai_core Fernet encryption."""

import os

from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    key = os.environ.get("APP_SECRET_ENCRYPTION_KEY", "")
    if key:
        try:
            return Fernet(key.encode() if isinstance(key, str) else key)
        except Exception:
            pass
    return Fernet(b"EQIRySotqyuQKgivvmjaGP2al_5cPPPR_nCezg1yuzQ=")


def encrypt_key(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_key(encrypted: str) -> str:
    if not encrypted:
        return ""
    try:
        return _get_fernet().decrypt(encrypted.encode()).decode()
    except (InvalidToken, Exception):
        return ""
