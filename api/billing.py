"""
Pihu SaaS — Billing & Subscription Lifecycle
Subscription tiers with token limits, overage handling (soft + hard limits),
failed payment state tracking, credits/refunds, Stripe webhook processing,
and billing portal redirect.
"""

import os
import json
import hmac
import hashlib
from datetime import datetime
from typing import Optional
from fastapi import HTTPException, Request
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from logger import get_logger

log = get_logger("BILLING_ENGINE")

PIHU_ENV = os.getenv("PIHU_ENV", "development")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# Stripe is optional — import only if available
try:
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY
    STRIPE_AVAILABLE = bool(STRIPE_SECRET_KEY and STRIPE_SECRET_KEY != "sk_test_mockkey")
except ImportError:
    STRIPE_AVAILABLE = False
    log.warning("Stripe SDK not installed — billing runs in ledger-only mode")


# ──────────────────────────────────────────
# SUBSCRIPTION TIER DEFINITIONS
# ──────────────────────────────────────────

TIER_CONFIG = {
    "free": {
        "token_limit": 50_000,
        "rate_limit_rpm": 30,
        "max_concurrent_tasks": 2,
        "prediction_limit_daily": 5,
        "price_usd_monthly": 0,
        "overage_allowed": False,
    },
    "pro": {
        "token_limit": 500_000,
        "rate_limit_rpm": 120,
        "max_concurrent_tasks": 10,
        "prediction_limit_daily": 100,
        "price_usd_monthly": 29,
        "overage_allowed": True,
        "overage_rate_per_1k_tokens": 0.002,
    },
    "enterprise": {
        "token_limit": 5_000_000,
        "rate_limit_rpm": 600,
        "max_concurrent_tasks": 50,
        "prediction_limit_daily": -1,  # Unlimited
        "price_usd_monthly": 199,
        "overage_allowed": True,
        "overage_rate_per_1k_tokens": 0.001,
    },
}


class BillingEngine:
    """Full subscription lifecycle: quota enforcement, overage handling,
    payment state tracking, credits, and Stripe webhook processing."""

    # ──────────────────────────────────────────
    # QUOTA ENFORCEMENT
    # ──────────────────────────────────────────

    async def verify_funding(self, tenant_id: str, org_id: str, db: AsyncSession) -> dict:
        """
        Check tenant's token usage against their org's subscription tier.
        Returns usage summary. Raises 402 if quota exhausted.
        """
        from api.database import Organization, TransactionLog

        # Get org subscription
        result = await db.execute(select(Organization).filter_by(id=org_id))
        org = result.scalar_one_or_none()

        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        # Check payment status
        if org.payment_status == "canceled":
            raise HTTPException(
                status_code=402,
                detail="Subscription canceled. Please reactivate to continue."
            )

        if org.payment_status == "past_due":
            log.warning("Org '%s' has past_due payment — allowing grace period", org_id)

        tier = org.subscription_tier or "free"
        tier_config = TIER_CONFIG.get(tier, TIER_CONFIG["free"])
        token_limit = tier_config["token_limit"]
        overage_allowed = tier_config.get("overage_allowed", False)

        # Calculate total usage
        result = await db.execute(
            select(TransactionLog.token_cost).filter_by(org_id=org_id)
        )
        costs = result.scalars().all()
        total_used = sum(costs)

        usage_pct = (total_used / token_limit * 100) if token_limit > 0 else 0

        # Soft limit warning at 80%
        if usage_pct >= 80 and usage_pct < 100:
            log.warning(
                "Org '%s' at %.1f%% of %s tier token limit (%d/%d)",
                org_id, usage_pct, tier, total_used, token_limit
            )

        # Hard limit enforcement
        if total_used >= token_limit:
            if not overage_allowed:
                raise HTTPException(
                    status_code=402,
                    detail=f"Token quota exhausted ({total_used:,}/{token_limit:,}). "
                           f"Upgrade from '{tier}' tier to continue."
                )
            else:
                overage = total_used - token_limit
                rate = tier_config.get("overage_rate_per_1k_tokens", 0.002)
                overage_cost = (overage / 1000) * rate
                log.info(
                    "Org '%s' in overage: %d tokens over limit, est. cost $%.4f",
                    org_id, overage, overage_cost
                )

        return {
            "org_id": org_id,
            "tier": tier,
            "token_limit": token_limit,
            "tokens_used": total_used,
            "usage_percent": round(usage_pct, 1),
            "payment_status": org.payment_status,
            "overage_allowed": overage_allowed,
        }

    # ──────────────────────────────────────────
    # TRANSACTION LOGGING
    # ──────────────────────────────────────────

    async def log_transaction(
        self, tenant_id: str, org_id: str, action: str,
        cost: int, db: AsyncSession, trace_id: str = None
    ):
        """Record a token consumption event to the billing ledger."""
        try:
            from api.database import TransactionLog, Organization

            entry = TransactionLog(
                tenant_id=tenant_id,
                org_id=org_id,
                action_type=action,
                token_cost=cost,
                trace_id=trace_id,
            )
            db.add(entry)

            # Update org running total
            result = await db.execute(select(Organization).filter_by(id=org_id))
            org = result.scalar_one_or_none()
            if org:
                org.tokens_used = (org.tokens_used or 0) + cost

            await db.commit()
        except Exception as e:
            log.error("Failed to log transaction for %s/%s: %s", tenant_id, org_id, e)

    # ──────────────────────────────────────────
    # SUBSCRIPTION MANAGEMENT
    # ──────────────────────────────────────────

    async def upgrade_tier(self, org_id: str, new_tier: str, db: AsyncSession) -> dict:
        """Upgrade (or downgrade) an org's subscription tier."""
        from api.database import Organization

        if new_tier not in TIER_CONFIG:
            raise HTTPException(status_code=400, detail=f"Invalid tier: {new_tier}")

        result = await db.execute(select(Organization).filter_by(id=org_id))
        org = result.scalar_one_or_none()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        old_tier = org.subscription_tier
        org.subscription_tier = new_tier
        org.token_limit = TIER_CONFIG[new_tier]["token_limit"]
        await db.commit()

        log.info("📦 Org '%s' tier changed: %s → %s", org_id, old_tier, new_tier)
        return {"org_id": org_id, "old_tier": old_tier, "new_tier": new_tier}

    async def apply_credit(
        self, org_id: str, tokens: int, reason: str, db: AsyncSession
    ) -> dict:
        """Apply a token credit (negative transaction) to an org's ledger."""
        from api.database import TransactionLog

        credit = TransactionLog(
            tenant_id="system",
            org_id=org_id,
            action_type=f"credit:{reason}",
            token_cost=-abs(tokens),
            trace_id=f"credit-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        )
        db.add(credit)
        await db.commit()

        log.info("💰 Credit applied to org '%s': %d tokens (reason: %s)", org_id, tokens, reason)
        return {"org_id": org_id, "credited_tokens": tokens, "reason": reason}

    # ──────────────────────────────────────────
    # STRIPE WEBHOOK PROCESSING
    # ──────────────────────────────────────────

    async def handle_stripe_webhook(self, request: Request, db: AsyncSession) -> dict:
        """
        Process Stripe webhook events for subscription lifecycle management.
        Verifies webhook signature in production.
        """
        body = await request.body()

        # Signature verification is mandatory in production.
        if PIHU_ENV == "production":
            if not STRIPE_WEBHOOK_SECRET:
                log.critical("STRIPE_WEBHOOK_SECRET is missing in production")
                raise HTTPException(status_code=500, detail="Stripe webhook verification is not configured")
            sig_header = request.headers.get("Stripe-Signature", "")
            if not self._verify_webhook_signature(body, sig_header):
                raise HTTPException(status_code=400, detail="Invalid webhook signature")

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        event_type = payload.get("type", "")
        data = payload.get("data", {}).get("object", {})

        log.info("📩 Stripe webhook: %s", event_type)

        handler = {
            "customer.subscription.created": self._on_subscription_created,
            "customer.subscription.updated": self._on_subscription_updated,
            "customer.subscription.deleted": self._on_subscription_canceled,
            "invoice.payment_succeeded": self._on_payment_succeeded,
            "invoice.payment_failed": self._on_payment_failed,
        }.get(event_type)

        if handler:
            return await handler(data, db)

        return {"status": "ignored", "event": event_type}

    def _verify_webhook_signature(self, body: bytes, sig_header: str) -> bool:
        """Verify Stripe webhook signature using HMAC-SHA256."""
        if not STRIPE_WEBHOOK_SECRET or not sig_header:
            return False
        try:
            if STRIPE_AVAILABLE:
                stripe.Webhook.construct_event(body, sig_header, STRIPE_WEBHOOK_SECRET)
                return True
            # Manual verification fallback
            elements = dict(item.split("=", 1) for item in sig_header.split(","))
            timestamp = elements.get("t", "")
            signature = elements.get("v1", "")
            signed_payload = f"{timestamp}.{body.decode()}"
            expected = hmac.new(
                STRIPE_WEBHOOK_SECRET.encode(), signed_payload.encode(), hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(expected, signature)
        except Exception as e:
            log.error("Webhook signature verification failed: %s", e)
            return False

    async def _on_subscription_created(self, data: dict, db: AsyncSession) -> dict:
        from api.database import Organization
        customer_id = data.get("customer", "")
        result = await db.execute(
            select(Organization).filter_by(stripe_customer_id=customer_id)
        )
        org = result.scalar_one_or_none()
        if org:
            org.stripe_subscription_id = data.get("id")
            org.payment_status = "active"
            await db.commit()
            log.info("✅ Subscription created for org '%s'", org.id)
        return {"status": "processed", "event": "subscription.created"}

    async def _on_subscription_updated(self, data: dict, db: AsyncSession) -> dict:
        from api.database import Organization
        customer_id = data.get("customer", "")
        result = await db.execute(
            select(Organization).filter_by(stripe_customer_id=customer_id)
        )
        org = result.scalar_one_or_none()
        if org:
            status = data.get("status", "active")
            org.payment_status = "past_due" if status == "past_due" else "active"
            await db.commit()
        return {"status": "processed", "event": "subscription.updated"}

    async def _on_subscription_canceled(self, data: dict, db: AsyncSession) -> dict:
        from api.database import Organization
        customer_id = data.get("customer", "")
        result = await db.execute(
            select(Organization).filter_by(stripe_customer_id=customer_id)
        )
        org = result.scalar_one_or_none()
        if org:
            org.payment_status = "canceled"
            await db.commit()
            log.warning("❌ Subscription canceled for org '%s'", org.id)
        return {"status": "processed", "event": "subscription.canceled"}

    async def _on_payment_succeeded(self, data: dict, db: AsyncSession) -> dict:
        from api.database import Organization
        customer_id = data.get("customer", "")
        result = await db.execute(
            select(Organization).filter_by(stripe_customer_id=customer_id)
        )
        org = result.scalar_one_or_none()
        if org:
            org.payment_status = "active"
            await db.commit()
        return {"status": "processed", "event": "payment.succeeded"}

    async def _on_payment_failed(self, data: dict, db: AsyncSession) -> dict:
        from api.database import Organization
        customer_id = data.get("customer", "")
        result = await db.execute(
            select(Organization).filter_by(stripe_customer_id=customer_id)
        )
        org = result.scalar_one_or_none()
        if org:
            org.payment_status = "past_due"
            await db.commit()
            log.warning("⚠️ Payment failed for org '%s' — entering grace period", org.id)
        return {"status": "processed", "event": "payment.failed"}

    # ──────────────────────────────────────────
    # USAGE SUMMARY
    # ──────────────────────────────────────────

    async def get_usage_summary(self, org_id: str, db: AsyncSession) -> dict:
        """Get detailed usage breakdown for an organization."""
        from api.database import Organization, TransactionLog

        result = await db.execute(select(Organization).filter_by(id=org_id))
        org = result.scalar_one_or_none()
        if not org:
            return {"error": "Organization not found"}

        tier = org.subscription_tier or "free"
        tier_config = TIER_CONFIG.get(tier, TIER_CONFIG["free"])

        # Transaction breakdown by action type
        result = await db.execute(
            select(TransactionLog).filter_by(org_id=org_id)
        )
        transactions = result.scalars().all()

        by_action = {}
        total_tokens = 0
        for txn in transactions:
            action = txn.action_type or "unknown"
            by_action[action] = by_action.get(action, 0) + (txn.token_cost or 0)
            total_tokens += (txn.token_cost or 0)

        token_limit = tier_config["token_limit"]
        overage = max(0, total_tokens - token_limit)

        return {
            "org_id": org_id,
            "tier": tier,
            "tier_config": tier_config,
            "tokens_used": total_tokens,
            "token_limit": token_limit,
            "usage_percent": round((total_tokens / token_limit * 100) if token_limit > 0 else 0, 1),
            "overage_tokens": overage,
            "payment_status": org.payment_status,
            "breakdown_by_action": by_action,
            "transaction_count": len(transactions),
        }

    # ──────────────────────────────────────────
    # BILLING PORTAL
    # ──────────────────────────────────────────

    async def create_portal_session(self, org_id: str, db: AsyncSession, return_url: str = None) -> dict:
        """Create a Stripe billing portal session for the org admin."""
        from api.database import Organization

        result = await db.execute(select(Organization).filter_by(id=org_id))
        org = result.scalar_one_or_none()

        if not org or not org.stripe_customer_id:
            raise HTTPException(
                status_code=400,
                detail="No Stripe customer linked to this organization"
            )

        if not STRIPE_AVAILABLE:
            return {
                "url": f"https://billing.stripe.com/p/login/test_{org_id}",
                "warning": "Stripe not configured — returning mock portal URL"
            }

        session = stripe.billing_portal.Session.create(
            customer=org.stripe_customer_id,
            return_url=return_url or "http://localhost:5173/dashboard",
        )
        return {"url": session.url}


billing_engine = BillingEngine()
