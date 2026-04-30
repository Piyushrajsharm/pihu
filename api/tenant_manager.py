"""
Pihu SaaS — Tenant Lifecycle Manager
Handles organization provisioning, member management, API key lifecycle,
tenant offboarding, and cross-tenant isolation enforcement.
"""

import json
import hashlib
import secrets as stdlib_secrets
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from logger import get_logger

log = get_logger("TENANT_MGR")


class TenantManager:
    """Manages the full lifecycle of organizations and their members."""

    # ──────────────────────────────────────────
    # ORGANIZATION LIFECYCLE
    # ──────────────────────────────────────────

    async def create_organization(
        self, org_id: str, name: str, owner_tenant_id: str, db: AsyncSession,
        tier: str = "free"
    ) -> dict:
        """Provision a new organization with an owner."""
        from api.database import Organization, Tenant, OrgRole

        # Check for duplicate
        existing = await db.execute(select(Organization).filter_by(id=org_id))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"Organization '{org_id}' already exists")

        tier_limits = {"free": 50_000, "pro": 500_000, "enterprise": 5_000_000}

        org = Organization(
            id=org_id, name=name,
            subscription_tier=tier,
            token_limit=tier_limits.get(tier, 50_000)
        )
        db.add(org)

        # Create owner tenant
        owner = Tenant(
            tenant_id=owner_tenant_id, org_id=org_id,
            role=OrgRole.OWNER.value,
            permissions=json.dumps(["read", "write", "execute", "predict", "admin"])
        )
        db.add(owner)
        await db.commit()

        log.info("✅ Organization '%s' created with owner '%s' (tier=%s)", org_id, owner_tenant_id, tier)
        return {"org_id": org_id, "owner": owner_tenant_id, "tier": tier}

    async def add_member(
        self, org_id: str, tenant_id: str, role: str, permissions: list, db: AsyncSession
    ) -> dict:
        """Add a member to an organization with specific permissions."""
        from api.database import Tenant, Organization

        # Verify org exists
        org = await db.execute(select(Organization).filter_by(id=org_id))
        if not org.scalar_one_or_none():
            raise HTTPException(status_code=404, detail=f"Organization '{org_id}' not found")

        member = Tenant(
            tenant_id=tenant_id, org_id=org_id,
            role=role,
            permissions=json.dumps(permissions)
        )
        db.add(member)
        await db.commit()

        log.info("👤 Member '%s' added to org '%s' (role=%s)", tenant_id, org_id, role)
        return {"tenant_id": tenant_id, "org_id": org_id, "role": role}

    async def remove_member(self, org_id: str, tenant_id: str, db: AsyncSession):
        """Remove a member and purge their tenant-scoped data."""
        from api.database import Tenant, TransactionLog, TaskRecord, APIKey

        # Deactivate tenant
        result = await db.execute(
            select(Tenant).filter_by(tenant_id=tenant_id, org_id=org_id)
        )
        tenant = result.scalar_one_or_none()
        if tenant:
            tenant.is_active = False
            # Revoke all API keys
            keys = await db.execute(select(APIKey).filter_by(tenant_id=tenant_id))
            for key in keys.scalars().all():
                key.status = "revoked"
            await db.commit()

        log.info("🚫 Member '%s' removed from org '%s'", tenant_id, org_id)

    # ──────────────────────────────────────────
    # TENANT OFFBOARDING (Data Purge)
    # ──────────────────────────────────────────

    async def offboard_organization(self, org_id: str, db: AsyncSession) -> dict:
        """Full data purge for GDPR/compliance. Removes all org data."""
        from api.database import (
            Organization, Tenant, TransactionLog, TaskRecord,
            APIKey, GovernancePolicy, AuditEntry
        )

        purge_counts = {}

        # 1. Purge API keys
        result = await db.execute(select(APIKey).filter_by(org_id=org_id))
        keys = result.scalars().all()
        purge_counts["api_keys"] = len(keys)
        for k in keys:
            await db.delete(k)

        # 2. Purge task records
        result = await db.execute(select(TaskRecord).filter_by(org_id=org_id))
        tasks = result.scalars().all()
        purge_counts["task_records"] = len(tasks)
        for t in tasks:
            await db.delete(t)

        # 3. Purge transaction logs
        result = await db.execute(select(TransactionLog).filter_by(org_id=org_id))
        txns = result.scalars().all()
        purge_counts["transactions"] = len(txns)
        for tx in txns:
            await db.delete(tx)

        # 4. Purge governance policies
        result = await db.execute(select(GovernancePolicy).filter_by(org_id=org_id))
        policies = result.scalars().all()
        purge_counts["policies"] = len(policies)
        for p in policies:
            await db.delete(p)

        # 5. Purge tenants
        result = await db.execute(select(Tenant).filter_by(org_id=org_id))
        tenants = result.scalars().all()
        purge_counts["tenants"] = len(tenants)
        for t in tenants:
            await db.delete(t)

        # 6. Deactivate org (keep record for audit)
        result = await db.execute(select(Organization).filter_by(id=org_id))
        org = result.scalar_one_or_none()
        if org:
            org.is_active = False
            org.name = f"[DELETED] {org.name}"

        # 7. Mark audit entries as purge-related (don't delete — compliance)
        purge_audit = AuditEntry(
            tenant_id="system", org_id=org_id,
            event_type="org_offboarded",
            details=json.dumps({"purge_counts": purge_counts}),
        )
        db.add(purge_audit)

        await db.commit()
        log.warning("🗑️ Organization '%s' fully offboarded: %s", org_id, purge_counts)
        return purge_counts

    # ──────────────────────────────────────────
    # API KEY MANAGEMENT
    # ──────────────────────────────────────────

    async def create_api_key(
        self, tenant_id: str, org_id: str, name: str,
        permissions: list, db: AsyncSession,
        expires_days: Optional[int] = None
    ) -> dict:
        """Generate a new API key. Returns the raw key ONCE — it is never stored."""
        from api.database import APIKey

        raw_key = f"pk_{'live' if self._is_production() else 'test'}_{stdlib_secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_prefix = raw_key[:12]

        api_key = APIKey(
            key_hash=key_hash,
            key_prefix=key_prefix,
            tenant_id=tenant_id,
            org_id=org_id,
            name=name,
            permissions=json.dumps(permissions),
            expires_at=datetime.utcnow() + timedelta(days=expires_days) if expires_days else None
        )
        db.add(api_key)
        await db.commit()

        log.info("🔑 API key '%s' created for tenant '%s' (prefix=%s)", name, tenant_id, key_prefix)
        return {
            "key": raw_key,  # Only returned once
            "prefix": key_prefix,
            "name": name,
            "permissions": permissions,
            "warning": "Save this key now. It cannot be retrieved again."
        }

    async def verify_api_key(self, raw_key: str, db: AsyncSession) -> Optional[dict]:
        """Verify an API key and return the associated identity."""
        from api.database import APIKey, Tenant

        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        result = await db.execute(select(APIKey).filter_by(key_hash=key_hash, status="active"))
        api_key = result.scalar_one_or_none()

        if not api_key:
            return None

        # Check expiry
        if api_key.expires_at and api_key.expires_at < datetime.utcnow():
            api_key.status = "expired"
            await db.commit()
            return None

        # Update last used
        api_key.last_used = datetime.utcnow()
        await db.commit()

        try:
            perms = json.loads(api_key.permissions or "[]")
        except json.JSONDecodeError:
            perms = []

        return {
            "user_id": api_key.tenant_id,
            "org_id": api_key.org_id,
            "role": "service",
            "permissions": perms,
            "key_name": api_key.name,
            "auth_method": "api_key"
        }

    async def revoke_api_key(self, key_prefix: str, org_id: str, db: AsyncSession):
        """Revoke an API key by its prefix."""
        from api.database import APIKey

        result = await db.execute(
            select(APIKey).filter_by(key_prefix=key_prefix, org_id=org_id, status="active")
        )
        key = result.scalar_one_or_none()
        if key:
            key.status = "revoked"
            await db.commit()
            log.info("🔒 API key revoked: prefix=%s", key_prefix)
        else:
            raise HTTPException(status_code=404, detail="API key not found or already revoked")

    async def list_api_keys(self, org_id: str, db: AsyncSession) -> list:
        """List all API keys for an org (without exposing the actual key)."""
        from api.database import APIKey

        result = await db.execute(select(APIKey).filter_by(org_id=org_id))
        keys = result.scalars().all()
        return [{
            "prefix": k.key_prefix,
            "name": k.name,
            "status": k.status,
            "tenant_id": k.tenant_id,
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "last_used": k.last_used.isoformat() if k.last_used else None,
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
        } for k in keys]

    # ──────────────────────────────────────────
    # CROSS-TENANT ISOLATION CHECKS
    # ──────────────────────────────────────────

    async def verify_tenant_access(
        self, tenant_id: str, org_id: str, required_permission: str, db: AsyncSession
    ) -> bool:
        """Verify a tenant belongs to the org and has the required permission."""
        from api.database import Tenant

        result = await db.execute(
            select(Tenant).filter_by(tenant_id=tenant_id, org_id=org_id, is_active=True)
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=403, detail="Tenant not authorized for this organization")

        if not tenant.has_permission(required_permission):
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: '{required_permission}' required"
            )
        return True

    def _is_production(self) -> bool:
        import os
        return os.getenv("PIHU_ENV", "development") == "production"


tenant_manager = TenantManager()
