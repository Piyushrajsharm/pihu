"""
Pihu SaaS — Async PostgreSQL Database Configuration
Row-level tenant isolation, org model, API keys, and AES-256 encrypted preferences.
"""

import os
import json
import hashlib
import secrets as stdlib_secrets
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float, ForeignKey, Enum as SAEnum
from cryptography.fernet import Fernet
import enum

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://pihu_user:pihu_password@localhost:5432/pihu_saas"
)
if os.getenv("PIHU_ENV") == "production" and "pihu_password" in DATABASE_URL:
    raise RuntimeError("DATABASE_URL must not use the default development password in production")

SYNC_DATABASE_URL = os.getenv("SYNC_DATABASE_URL", DATABASE_URL.replace("+asyncpg", ""))

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

sync_engine = create_engine(SYNC_DATABASE_URL, echo=False)
SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)

Base = declarative_base()

# ──────────────────────────────────────────
# ENCRYPTION (Production: load from KMS/Vault)
# ──────────────────────────────────────────
_encryption_key = os.getenv("DB_ENCRYPTION_KEY")
if os.getenv("PIHU_ENV") == "production" and not _encryption_key:
    raise RuntimeError("DB_ENCRYPTION_KEY must be set in production")
ENCRYPTION_KEY = (_encryption_key or "A-H3C8nKJhG5R6pL2T0yF1_x9QbMwZVc-7NkXrJpV4s=").encode()
fernet = Fernet(ENCRYPTION_KEY)


# ──────────────────────────────────────────
# ENUMS
# ──────────────────────────────────────────

class OrgRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    SERVICE = "service"    # Non-human service account


class Permission(str, enum.Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    PREDICT = "predict"
    ADMIN = "admin"


class SubscriptionTier(str, enum.Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class APIKeyStatus(str, enum.Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


# ──────────────────────────────────────────
# ORM MODELS
# ──────────────────────────────────────────

class Organization(Base):
    """Top-level entity. All data is scoped to an organization."""
    __tablename__ = "organizations"

    id = Column(String(100), primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    subscription_tier = Column(String(20), default=SubscriptionTier.FREE.value)
    token_limit = Column(Integer, default=50_000)           # Total token budget
    tokens_used = Column(Integer, default=0)                # Running total
    stripe_customer_id = Column(String(100), nullable=True) # Stripe customer ID
    stripe_subscription_id = Column(String(100), nullable=True)
    payment_status = Column(String(20), default="active")   # active|past_due|canceled
    is_active = Column(Boolean, default=True)
    settings = Column(Text, nullable=True)                  # Encrypted org-level config


class Tenant(Base):
    """Individual user within an organization."""
    __tablename__ = "tenants"

    tenant_id = Column(String(100), primary_key=True, index=True)
    org_id = Column(String(100), ForeignKey("organizations.id"), nullable=False, index=True)
    role = Column(String(20), default=OrgRole.MEMBER.value)
    permissions = Column(Text, default='["read","write","execute","predict"]')  # JSON array
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    active_goal = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True)
    encrypted_preferences = Column(Text, nullable=True)

    @property
    def preferences(self):
        if not self.encrypted_preferences:
            return {}
        decrypted = fernet.decrypt(self.encrypted_preferences.encode()).decode("utf-8")
        return json.loads(decrypted)

    @preferences.setter
    def preferences(self, value: dict):
        json_data = json.dumps(value)
        self.encrypted_preferences = fernet.encrypt(json_data.encode("utf-8")).decode()

    @property
    def permission_list(self) -> list:
        try:
            return json.loads(self.permissions or "[]")
        except json.JSONDecodeError:
            return []

    def has_permission(self, perm: str) -> bool:
        if self.role == OrgRole.OWNER.value or self.role == OrgRole.ADMIN.value:
            return True
        return perm in self.permission_list


class APIKey(Base):
    """Per-tenant or per-org API keys for non-human access."""
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_hash = Column(String(128), unique=True, index=True, nullable=False)  # SHA-256 of key
    key_prefix = Column(String(12), nullable=False)  # First 8 chars for identification
    tenant_id = Column(String(100), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    org_id = Column(String(100), ForeignKey("organizations.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)       # Human-readable label
    permissions = Column(Text, default='["read"]')    # Scoped permissions for this key
    status = Column(String(20), default=APIKeyStatus.ACTIVE.value)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)


class TransactionLog(Base):
    """Billing ledger — all token consumption is recorded per-tenant, per-org."""
    __tablename__ = "transaction_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(100), ForeignKey("tenants.tenant_id"), index=True)
    org_id = Column(String(100), ForeignKey("organizations.id"), index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    action_type = Column(String(50))
    token_cost = Column(Integer, default=0)
    trace_id = Column(String(64), nullable=True)     # Correlation ID for tracing


class TaskRecord(Base):
    """Persistent task results — survives Redis failures."""
    __tablename__ = "task_records"

    id = Column(String(64), primary_key=True)        # Celery task ID
    tenant_id = Column(String(100), ForeignKey("tenants.tenant_id"), index=True)
    org_id = Column(String(100), ForeignKey("organizations.id"), index=True)
    status = Column(String(20), default=TaskStatus.PENDING.value)
    input_text = Column(Text, nullable=True)
    result_text = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class GovernancePolicy(Base):
    """Versioned governance policies per organization."""
    __tablename__ = "governance_policies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(String(100), ForeignKey("organizations.id"), index=True)
    version = Column(Integer, default=1)
    policy_data = Column(Text, nullable=False)  # JSON policy config
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)


class AuditEntry(Base):
    """Tamper-evident audit entries stored in DB (in addition to file log)."""
    __tablename__ = "audit_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(100), index=True)
    org_id = Column(String(100), index=True)
    event_type = Column(String(50), nullable=False)
    details = Column(Text, nullable=True)
    trace_id = Column(String(64), nullable=True)
    prev_hash = Column(String(64), nullable=True)
    entry_hash = Column(String(64), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


# ──────────────────────────────────────────
# INITIALIZATION
# ──────────────────────────────────────────
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db_session():
    async with AsyncSessionLocal() as session:
        yield session


# ──────────────────────────────────────────
# ROW-LEVEL SECURITY HELPERS
# ──────────────────────────────────────────
def tenant_filter(query, model, tenant_id: str):
    """Apply row-level tenant isolation to any query.
    Every data access MUST pass through this filter.
    """
    if hasattr(model, "tenant_id"):
        return query.filter(model.tenant_id == tenant_id)
    if hasattr(model, "org_id"):
        return query.filter(model.org_id == tenant_id)
    return query


def org_filter(query, model, org_id: str):
    """Apply org-level isolation to any query."""
    if hasattr(model, "org_id"):
        return query.filter(model.org_id == org_id)
    return query
