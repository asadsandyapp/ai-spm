import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import jwt

from ai_spm.config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def generate_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_admin_access_token(
    user_id: str,
    org_id: str,
    role: str,
    permissions: list[str] | None = None,
) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": user_id,
        "org_id": org_id,
        "role": role,
        "permissions": permissions or _role_permissions(role),
        "exp": expire,
        "type": "admin",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_platform_access_token(
    user_id: str,
    role: str,
    permissions: list[str] | None = None,
) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.platform_jwt_expire_minutes)
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "permissions": permissions or _platform_role_permissions(role),
        "exp": expire,
        "type": "platform",
    }
    return jwt.encode(
        payload, settings.platform_jwt_secret_key, algorithm=settings.platform_jwt_algorithm
    )


def _role_permissions(role: str) -> list[str]:
    mapping = {
        "super_admin": [
            "dashboard:read",
            "threats:read",
            "agents:*",
            "policies:*",
            "audit:read",
            "audit:export",
            "users:*",
            "settings:*",
            "llm:*",
        ],
        "security_admin": [
            "dashboard:read",
            "threats:read",
            "agents:read",
            "agents:write",
            "policies:*",
            "audit:read",
            "llm:read",
        ],
        "auditor": [
            "dashboard:read",
            "threats:read",
            "agents:read",
            "audit:read",
            "audit:export",
        ],
        "viewer": ["dashboard:read", "threats:read", "agents:read", "audit:read"],
    }
    return mapping.get(role, ["audit:read"])


def _platform_role_permissions(role: str) -> list[str]:
    mapping = {
        "platform_super": ["tenants:*", "billing:read", "billing:write"],
        "platform_support": ["tenants:read", "tenants:suspend", "tenants:activate"],
        "platform_billing": ["billing:*", "tenants:read", "tenants:activate"],
    }
    return mapping.get(role, ["tenants:read"])
