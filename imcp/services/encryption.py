"""Fernet-based encryption helpers for sensitive service credentials."""
from __future__ import annotations

import base64
import hashlib
import json

from cryptography.fernet import Fernet
from django.conf import settings


def _fernet() -> Fernet:
    raw = settings.SECRET_KEY.encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)


def encrypt_json(data: dict) -> str:
    """Encrypt a dict to a Fernet token string."""
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_json(token: str) -> dict:
    """Decrypt a Fernet token string back to a dict."""
    return json.loads(_fernet().decrypt(token.encode()))
