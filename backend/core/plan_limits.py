"""
Plan limits enforcement — Free / Pro / Enterprise.
Dipakai sebagai FastAPI dependency dan di scheduler.
"""
from dataclasses import dataclass
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.deps import get_current_tenant
from backend.models.models import Tenant


@dataclass
class PlanLimits:
    max_channels: int
    max_gemini_keys: int
    max_jobs_per_day: int
    max_sub_tenants: int    # reseller only
    can_use_ab_test: bool
    can_use_multi_platform: bool
    can_use_competitor_spy: bool
    rate_limit_per_minute: int


PLAN_LIMITS: dict[str, PlanLimits] = {
    "free": PlanLimits(
        max_channels=3,
        max_gemini_keys=5,
        max_jobs_per_day=10,
        max_sub_tenants=0,
        can_use_ab_test=False,
        can_use_multi_platform=False,
        can_use_competitor_spy=False,
        rate_limit_per_minute=20,
    ),
    "pro": PlanLimits(
        max_channels=15,
        max_gemini_keys=30,
        max_jobs_per_day=100,
        max_sub_tenants=0,
        can_use_ab_test=True,
        can_use_multi_platform=True,
        can_use_competitor_spy=True,
        rate_limit_per_minute=60,
    ),
    "enterprise": PlanLimits(
        max_channels=9999,
        max_gemini_keys=50,
        max_jobs_per_day=9999,
        max_sub_tenants=100,
        can_use_ab_test=True,
        can_use_multi_platform=True,
        can_use_competitor_spy=True,
        rate_limit_per_minute=300,
    ),
}


def get_limits(tenant: Tenant) -> PlanLimits:
    return PLAN_LIMITS.get(tenant.plan or "free", PLAN_LIMITS["free"])


def check_channel_limit(tenant: Tenant, db: Session):
    from backend.models.models import Channel
    limits = get_limits(tenant)
    if limits.max_channels >= 9999:
        return
    count = db.query(Channel).filter(Channel.tenant_id == tenant.id).count()
    if count >= limits.max_channels:
        raise HTTPException(
            429,
            f"Batas channel plan {tenant.plan}: {limits.max_channels}. "
            "Upgrade plan untuk menambah lebih banyak channel."
        )


def check_gemini_key_limit(tenant: Tenant, db: Session):
    from backend.models.models import GeminiKey
    limits = get_limits(tenant)
    if limits.max_gemini_keys >= 9999:
        return
    count = db.query(GeminiKey).filter(GeminiKey.tenant_id == tenant.id).count()
    if count >= limits.max_gemini_keys:
        raise HTTPException(
            429,
            f"Batas Gemini key plan {tenant.plan}: {limits.max_gemini_keys}. "
            "Upgrade plan untuk menambah lebih banyak key."
        )


def check_daily_job_limit(tenant: Tenant, db: Session):
    from datetime import datetime, timezone, timedelta
    from backend.models.models import VideoJob
    limits = get_limits(tenant)
    if limits.max_jobs_per_day >= 9999:
        return
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    count = (
        db.query(VideoJob)
        .filter(
            VideoJob.tenant_id == tenant.id,
            VideoJob.created_at >= today_start,
        )
        .count()
    )
    if count >= limits.max_jobs_per_day:
        raise HTTPException(
            429,
            f"Batas job harian plan {tenant.plan}: {limits.max_jobs_per_day}. "
            "Coba lagi besok atau upgrade plan."
        )


def require_ab_test(tenant: Tenant = Depends(get_current_tenant)):
    limits = get_limits(tenant)
    if not limits.can_use_ab_test:
        raise HTTPException(403, "Fitur A/B Test hanya tersedia di plan Pro dan Enterprise.")
    return tenant


def require_multi_platform(tenant: Tenant = Depends(get_current_tenant)):
    limits = get_limits(tenant)
    if not limits.can_use_multi_platform:
        raise HTTPException(
            403,
            "Multi-platform upload (TikTok/Instagram/Facebook) hanya tersedia di plan Pro dan Enterprise."
        )
    return tenant


def require_competitor_spy(tenant: Tenant = Depends(get_current_tenant)):
    limits = get_limits(tenant)
    if not limits.can_use_competitor_spy:
        raise HTTPException(403, "Fitur Competitor Spy hanya tersedia di plan Pro dan Enterprise.")
    return tenant
