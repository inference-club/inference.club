"""Symmetric encryption for user secrets (external API keys), at rest.

Keys are encrypted with Fernet using a key derived from ``settings.SECRET_KEY``
so there's no extra secret to manage. NOTE: rotating SECRET_KEY invalidates
stored ciphertext (it decrypts to ""), and the user simply re-enters the key.
"""
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    # Fernet needs a 32-byte urlsafe-base64 key; derive a stable one from SECRET_KEY.
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return ""
