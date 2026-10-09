"""Authentication module for HL-Manager.

Provides username/password verification and HMAC-SHA256 JWT access tokens.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any, Optional

SECRET_KEY = (
    os.environ.get("APP_SECRET_KEY")
    or "hl-secret-key-eval-2026-very-secure-jwt-key"
)

# Configurable accounts
DEFAULT_USERS = {
    "lahmandi": os.environ.get("APP_PASSWORD", "admin2026"),
    "admin": os.environ.get("ADMIN_PASSWORD", "admin2026"),
}


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64_decode(data: str) -> bytes:
    padding = 4 - (len(data) % 4)
    if padding and padding < 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data.encode("utf-8"))


def create_access_token(
    username: str, expires_delta_seconds: int = 86400
) -> str:
    """Create a signed JWT-compatible token valid for 24h by default."""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": username,
        "role": "RH Manager",
        "iat": now,
        "exp": now + expires_delta_seconds,
    }
    h_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    p_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    msg = f"{_b64_encode(h_bytes)}.{_b64_encode(p_bytes)}".encode("utf-8")
    sig = hmac.new(SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).digest()
    return f"{msg.decode('utf-8')}.{_b64_encode(sig)}"


def verify_token(token: str) -> Optional[dict[str, Any]]:
    """Verify signature and expiry of access token."""
    try:
        if not token:
            return None
        parts = token.split(".")
        if len(parts) != 3:
            return None
        msg = f"{parts[0]}.{parts[1]}".encode("utf-8")
        expected_sig = hmac.new(
            SECRET_KEY.encode("utf-8"), msg, hashlib.sha256
        ).digest()
        actual_sig = _b64_decode(parts[2])
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(_b64_decode(parts[1]).decode("utf-8"))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def authenticate_user(username: str, password: str) -> bool:
    """Verify username and password."""
    u = username.lower().strip()
    expected_pw = DEFAULT_USERS.get(u)
    if not expected_pw:
        return False
    return secrets.compare_digest(expected_pw, password.strip())
