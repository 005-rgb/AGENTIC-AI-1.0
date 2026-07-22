"""
ResellerManager — sub-tenant management and branding for reseller accounts.
"""
from sqlalchemy.orm import Session
from backend.models.models import Tenant, VideoJob, GeminiKey, Channel


class ResellerManager:
    def __init__(self, db: Session):
        self.db = db

    def get_sub_tenants(self, reseller_id: str) -> list:
        return self.db.query(Tenant).filter(
            Tenant.parent_tenant_id == reseller_id
        ).all()

    def get_stats(self, reseller_id: str) -> dict:
        sub_tenants = self.get_sub_tenants(reseller_id)
        sub_ids = [s.id for s in sub_tenants]

        total_jobs = 0
        total_channels = 0
        total_keys = 0

        if sub_ids:
            total_jobs = self.db.query(VideoJob).filter(
                VideoJob.tenant_id.in_(sub_ids)
            ).count()
            total_channels = self.db.query(Channel).filter(
                Channel.tenant_id.in_(sub_ids)
            ).count()
            total_keys = self.db.query(GeminiKey).filter(
                GeminiKey.tenant_id.in_(sub_ids)
            ).count()

        return {
            "total_sub_tenants": len(sub_tenants),
            "total_jobs": total_jobs,
            "total_channels": total_channels,
            "total_keys": total_keys,
        }

    def update_branding(self, reseller_id: str, brand_name: str = None,
                        brand_logo_url: str = None, brand_color: str = None) -> Tenant:
        """Update reseller branding and propagate to sub-tenants."""
        reseller = self.db.query(Tenant).filter(Tenant.id == reseller_id).first()
        if not reseller:
            return None

        if brand_name is not None:
            reseller.brand_name = brand_name
        if brand_logo_url is not None:
            reseller.brand_logo_url = brand_logo_url
        if brand_color is not None:
            reseller.brand_color = brand_color

        # Propagate branding to sub-tenants
        sub_tenants = self.get_sub_tenants(reseller_id)
        for sub in sub_tenants:
            if brand_name is not None:
                sub.brand_name = brand_name
            if brand_logo_url is not None:
                sub.brand_logo_url = brand_logo_url
            if brand_color is not None:
                sub.brand_color = brand_color

        self.db.commit()
        self.db.refresh(reseller)
        return reseller
