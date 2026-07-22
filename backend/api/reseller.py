from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import uuid

from backend.core.database import get_db
from backend.core.deps import get_current_tenant
from backend.core.security import hash_password
from backend.models.models import Tenant

router = APIRouter()


class SubTenantCreate(BaseModel):
    email: str
    password: str
    name: str
    plan: str = "free"


class BrandingUpdate(BaseModel):
    brand_name: Optional[str] = None
    brand_logo_url: Optional[str] = None
    brand_color: Optional[str] = None


def _require_reseller(tenant: Tenant):
    if not tenant.is_reseller:
        raise HTTPException(403, "Akses reseller diperlukan. Upgrade ke plan Enterprise.")


def _sub_tenant_out(t) -> dict:
    return {
        "id": t.id,
        "email": t.email,
        "name": t.name,
        "plan": t.plan or "free",
        "is_active": t.is_active,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


@router.get("/sub-tenants")
def list_sub_tenants(
    db: Session = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    _require_reseller(current_tenant)
    sub_tenants = db.query(Tenant).filter(
        Tenant.parent_tenant_id == current_tenant.id
    ).all()
    return {"sub_tenants": [_sub_tenant_out(t) for t in sub_tenants], "total": len(sub_tenants)}


@router.post("/sub-tenants", status_code=201)
def create_sub_tenant(
    data: SubTenantCreate,
    db: Session = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    _require_reseller(current_tenant)

    existing = db.query(Tenant).filter(Tenant.email == data.email).first()
    if existing:
        raise HTTPException(409, "Email sudah terdaftar")

    sub = Tenant(
        id=str(uuid.uuid4()),
        email=data.email,
        hashed_password=hash_password(data.password),
        name=data.name,
        plan=data.plan,
        parent_tenant_id=current_tenant.id,
        # Inherit reseller branding
        brand_name=current_tenant.brand_name,
        brand_logo_url=current_tenant.brand_logo_url,
        brand_color=current_tenant.brand_color,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return _sub_tenant_out(sub)


@router.delete("/sub-tenants/{sub_id}", status_code=204)
def delete_sub_tenant(
    sub_id: str,
    db: Session = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    _require_reseller(current_tenant)
    sub = db.query(Tenant).filter(
        Tenant.id == sub_id,
        Tenant.parent_tenant_id == current_tenant.id,
    ).first()
    if not sub:
        raise HTTPException(404, "Sub-tenant tidak ditemukan")
    db.delete(sub)
    db.commit()


@router.put("/branding")
def update_branding(
    data: BrandingUpdate,
    db: Session = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    _require_reseller(current_tenant)
    tenant = db.query(Tenant).filter(Tenant.id == current_tenant.id).first()
    if data.brand_name is not None:
        tenant.brand_name = data.brand_name
    if data.brand_logo_url is not None:
        tenant.brand_logo_url = data.brand_logo_url
    if data.brand_color is not None:
        tenant.brand_color = data.brand_color
    db.commit()
    db.refresh(tenant)
    return {
        "brand_name": tenant.brand_name,
        "brand_logo_url": tenant.brand_logo_url,
        "brand_color": tenant.brand_color,
    }


@router.get("/branding")
def get_branding(
    current_tenant: Tenant = Depends(get_current_tenant),
):
    return {
        "brand_name": current_tenant.brand_name,
        "brand_logo_url": current_tenant.brand_logo_url,
        "brand_color": current_tenant.brand_color,
    }


@router.get("/stats")
def reseller_stats(
    db: Session = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    _require_reseller(current_tenant)
    from backend.models.models import VideoJob

    sub_tenants = db.query(Tenant).filter(
        Tenant.parent_tenant_id == current_tenant.id
    ).all()
    sub_ids = [s.id for s in sub_tenants]

    total_jobs = 0
    if sub_ids:
        total_jobs = db.query(VideoJob).filter(
            VideoJob.tenant_id.in_(sub_ids)
        ).count()

    return {
        "total_sub_tenants": len(sub_tenants),
        "total_jobs": total_jobs,
        "sub_tenants": [_sub_tenant_out(t) for t in sub_tenants],
    }
