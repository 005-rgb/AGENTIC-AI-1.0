"""Gemini API key management per tenant."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from backend.core.database import get_db
from backend.core.deps import get_current_tenant
from backend.core.gemini_pool import pool_manager
from backend.models.models import GeminiKey, Tenant

router = APIRouter(prefix="/api/keys", tags=["keys"])


class KeyCreate(BaseModel):
    api_key: str
    label: Optional[str] = ""


class KeyOut(BaseModel):
    id: str
    label: str
    is_active: bool
    usage_count: int
    masked_key: str

    class Config:
        from_attributes = True


def _mask(key: str) -> str:
    return key[:8] + "..." + key[-4:] if len(key) > 12 else "***"


@router.get("/", response_model=list[KeyOut])
def list_keys(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    keys = db.query(GeminiKey).filter(GeminiKey.tenant_id == tenant.id).all()
    return [
        KeyOut(id=k.id, label=k.label or "", is_active=k.is_active, usage_count=k.usage_count, masked_key=_mask(k.api_key))
        for k in keys
    ]


@router.post("/", status_code=201)
def add_key(body: KeyCreate, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    key = GeminiKey(tenant_id=tenant.id, api_key=body.api_key, label=body.label or "")
    db.add(key)
    db.commit()
    db.refresh(key)
    # Update in-memory pool
    pool_manager.add_key(tenant.id, body.api_key)
    return {"id": key.id, "masked_key": _mask(key.api_key), "label": key.label}


@router.delete("/{key_id}", status_code=204)
def delete_key(key_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    key = db.query(GeminiKey).filter(GeminiKey.id == key_id, GeminiKey.tenant_id == tenant.id).first()
    if not key:
        raise HTTPException(404, "Key not found")
    pool_manager.remove_key(tenant.id, key.api_key)
    db.delete(key)
    db.commit()


@router.patch("/{key_id}/toggle")
def toggle_key(key_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    key = db.query(GeminiKey).filter(GeminiKey.id == key_id, GeminiKey.tenant_id == tenant.id).first()
    if not key:
        raise HTTPException(404, "Key not found")
    key.is_active = not key.is_active
    db.commit()
    # Rebuild pool from DB
    from backend.core.gemini_pool import load_tenant_keys_from_db
    load_tenant_keys_from_db(db, tenant.id)
    return {"id": key.id, "is_active": key.is_active}
