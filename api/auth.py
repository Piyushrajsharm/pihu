"""
Pihu SaaS — Authentication & Authorization
JWT-based auth with granular permission scopes, API key support,
and environment-gated demo mode.
"""

import os
import jwt
import json
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from fastapi import HTTPException, Request
from logger import get_logger

log = get_logger("AUTH_ENGINE")

PIHU_ENV = os.getenv("PIHU_ENV", "development")
JWT_SECRET = os.getenv("JWT_SECRET_KEY", "pihu-dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))
DEMO_MODE_ENABLED = PIHU_ENV != "production" and os.getenv("PIHU_DEMO_MODE", "0") == "1"

if PIHU_ENV == "production" and JWT_SECRET == "pihu-dev-secret-change-in-production":
    raise RuntimeError("JWT_SECRET_KEY must be set to a strong secret in production")

# ──────────────────────────────────────────
# PERMISSION DEFINITIONS
# ──────────────────────────────────────────

# All available permission scopes
ALL_PERMISSIONS = ["read", "write", "execute", "predict", "admin"]

# Default permissions per role
ROLE_PERMISSIONS = {
    "owner":   ["read", "write", "execute", "predict", "admin"],
    "admin":   ["read", "write", "execute", "predict", "admin"],
    "member":  ["read", "write", "execute", "predict"],
    "service": ["read", "execute"],   # Service accounts — limited scope
    "viewer":  ["read"],
}


# ──────────────────────────────────────────
# JWT TOKEN CREATION
# ──────────────────────────────────────────

def create_jwt_token(
    user_id: str,
    org_id: str,
    role: str = "member",
    permissions: Optional[list] = None,
) -> str:
    """Create a JWT token with embedded identity, role, and permission scopes."""
    if permissions is None:
        permissions = ROLE_PERMISSIONS.get(role, ["read"])

    payload = {
        "sub": user_id,
        "org_id": org_id,
        "role": role,
        "permissions": permissions,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
        "env": PIHU_ENV,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    log.info("JWT issued for user=%s org=%s role=%s perms=%s", user_id, org_id, role, permissions)
    return token


# ──────────────────────────────────────────
# JWT TOKEN VALIDATION
# ──────────────────────────────────────────

def validate_jwt_token(token: str) -> dict:
    """Validate and decode a JWT token. Returns the claims dict."""
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return claims
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired. Please re-authenticate.")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


# ──────────────────────────────────────────
# PERMISSION CHECKING
# ──────────────────────────────────────────

def require_permission(claims: dict, required: str):
    """Check if the token holder has a specific permission scope."""
    user_perms = claims.get("permissions", [])
    role = claims.get("role", "member")

    # Owner and admin bypass
    if role in ("owner", "admin"):
        return True

    if required not in user_perms:
        log.warning(
            "Permission denied: user=%s required=%s has=%s",
            claims.get("sub"), required, user_perms
        )
        raise HTTPException(
            status_code=403,
            detail=f"Forbidden: '{required}' permission required. Your scopes: {user_perms}"
        )
    return True


def require_role(claims: dict, min_role: str):
    """Check if the token holder has at least the given role level."""
    role_hierarchy = {"viewer": 0, "member": 1, "service": 1, "admin": 2, "owner": 3}
    user_role = claims.get("role", "member")
    user_level = role_hierarchy.get(user_role, 0)
    required_level = role_hierarchy.get(min_role, 0)

    if user_level < required_level:
        raise HTTPException(
            status_code=403,
            detail=f"Forbidden: '{min_role}' role or higher required. Your role: {user_role}"
        )
    return True


# ──────────────────────────────────────────
# REQUEST AUTHENTICATION (Universal)
# ──────────────────────────────────────────

async def authenticate_request(request: Request) -> dict:
    """
    Authenticate a request via JWT token OR API key.
    Returns a claims dict with user_id, org_id, role, permissions.
    """
    auth_header = request.headers.get("Authorization", "")

    # 1. Try API key (pk_test_... or pk_live_...)
    if auth_header.startswith("Bearer pk_"):
        return await _authenticate_api_key(auth_header.replace("Bearer ", ""))

    # 2. Try JWT token
    if auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
        return validate_jwt_token(token)

    # 3. Explicit demo mode bypass (disabled by default and always disabled in production)
    if DEMO_MODE_ENABLED and auth_header.replace("Bearer ", "") == "dev-token":
        log.warning("⚠️ Demo mode active (PIHU_ENV=%s). This is disabled in production.", PIHU_ENV)
        return {
            "sub": "demo_user",
            "user_id": "demo_user",
            "org_id": "demo_org",
            "role": "admin",
            "permissions": ALL_PERMISSIONS,
            "env": PIHU_ENV,
            "auth_method": "demo_bypass",
        }

    raise HTTPException(status_code=401, detail="Authentication required. Provide JWT or API key.")


async def _authenticate_api_key(raw_key: str) -> dict:
    """Authenticate via API key by checking hash against database."""
    try:
        from api.database import AsyncSessionLocal
        from api.tenant_manager import tenant_manager

        async with AsyncSessionLocal() as db:
            identity = await tenant_manager.verify_api_key(raw_key, db)
            if identity:
                return identity
    except Exception as e:
        log.error("API key verification failed: %s", e)

    raise HTTPException(status_code=401, detail="Invalid API key")


# ──────────────────────────────────────────
# LOGIN ENDPOINT LOGIC
# ──────────────────────────────────────────

async def handle_login(email: str, password: str) -> dict:
    """
    Authenticate user credentials and return JWT.
    Production/admin bootstrap credentials are supplied via environment variables:
    PIHU_ADMIN_EMAIL and PIHU_ADMIN_PASSWORD_SHA256.
    """
    email = (email or "").strip().lower()
    password = password or ""

    if not email or not password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if DEMO_MODE_ENABLED and email == "demo@pihu.local":
        token = create_jwt_token(
            user_id="demo_user",
            org_id="demo_org",
            role="admin",
        )
        return {"token": token, "tenant_id": "demo_user", "org_id": "demo_org", "role": "admin"}

    admin_email = (os.getenv("PIHU_ADMIN_EMAIL") or "").strip().lower()
    admin_password_hash = (os.getenv("PIHU_ADMIN_PASSWORD_SHA256") or "").strip().lower()
    org_id = os.getenv("PIHU_ADMIN_ORG_ID", "org_default")

    if not admin_email or not admin_password_hash:
        log.error("Admin login attempted before PIHU_ADMIN_EMAIL/PIHU_ADMIN_PASSWORD_SHA256 were configured")
        raise HTTPException(status_code=503, detail="Authentication is not configured")

    submitted_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    email_ok = hmac.compare_digest(email, admin_email)
    password_ok = hmac.compare_digest(submitted_hash, admin_password_hash)

    if email_ok and password_ok:
        tenant_id = f"tenant_{email.split('@')[0]}"
        token = create_jwt_token(
            user_id=tenant_id,
            org_id=org_id,
            role="admin",
        )
        return {"token": token, "tenant_id": tenant_id, "org_id": org_id, "role": "admin"}

    raise HTTPException(status_code=401, detail="Invalid credentials")


# ──────────────────────────────────────────
# FASTAPI DEPENDENCY WRAPPERS
# ──────────────────────────────────────────

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Depends

_bearer_scheme = HTTPBearer(auto_error=False)


async def verify_jwt_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict:
    """FastAPI dependency: extracts JWT from Authorization header, validates it,
    and returns the decoded claims dict."""
    if credentials is None:
        # Check for explicitly enabled demo mode
        if DEMO_MODE_ENABLED:
            log.warning("⚠️ No credentials — falling back to demo identity (PIHU_ENV=%s)", PIHU_ENV)
            return {
                "user_id": "demo_user",
                "org_id": "demo_org",
                "role": "admin",
                "permissions": ALL_PERMISSIONS,
                "auth_method": "demo_bypass",
            }
        raise HTTPException(status_code=401, detail="Authentication required")

    if DEMO_MODE_ENABLED and credentials.credentials == "dev-token":
        log.warning("⚠️ Demo token accepted (PIHU_ENV=%s)", PIHU_ENV)
        return {
            "user_id": "demo_user",
            "org_id": "demo_org",
            "role": "admin",
            "permissions": ALL_PERMISSIONS,
            "auth_method": "demo_bypass",
        }

    claims = validate_jwt_token(credentials.credentials)
    # Normalize: ensure "user_id" key exists (JWT uses "sub")
    claims["user_id"] = claims.get("user_id", claims.get("sub", "unknown"))
    return claims


async def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict:
    """FastAPI dependency: verifies admin-level access."""
    claims = await verify_jwt_token(credentials)
    require_role(claims, "admin")
    return claims
