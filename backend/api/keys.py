from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import uuid

from backend.core.database import get_db
from backend.core.deps import get_current_tenant
from backend.core.gemini_pool import pool_manager, load_tenant_keys_from_db
from backend.models.models import GeminiKey, Tenant

router = APIRouter()


def mask_key(key: str) -> str:
    return key[:8] + "***masked***" if len(key) > 8 else "***masked***"


class KeyOut(BaseModel):
    id: str
    label: str
    api_key: str
    is_active: bool
    usage_count: int
    last_used_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class KeyCreate(BaseModel):
    api_key: str
    label: str = ""


class KeyTest(BaseModel):
    api_key: str


def _key_out(k: GeminiKey) -> KeyOut:
    return KeyOut(
        id=k.id,
        label=k.label,
        api_key=mask_key(k.api_key),
        is_active=k.is_active,
        usage_count=k.usage_count,
        last_used_at=k.last_used_at,
        created_at=k.created_at,
    )


@router.get("")
def list_keys(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    keys = db.query(GeminiKey).filter(GeminiKey.tenant_id == tenant.id).all()
    active_count = sum(1 for k in keys if k.is_active)
    return {
        "keys": [_key_out(k) for k in keys],
        "total": len(keys),
        "pool_size": active_count,
    }


@router.post("", status_code=201)
def add_key(data: KeyCreate, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    existing = db.query(GeminiKey).filter(
        GeminiKey.tenant_id == tenant.id,
        GeminiKey.api_key == data.api_key,
    ).first()
    if existing:
        raise HTTPException(400, "API key sudah terdaftar")
    key = GeminiKey(
        id=str(uuid.uuid4()),
        tenant_id=tenant.id,
        api_key=data.api_key,
        label=data.label,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    # Resync pool
    load_tenant_keys_from_db(db, tenant.id)
    return _key_out(key)


@router.delete("/{key_id}", status_code=204)
def delete_key(key_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    key = db.query(GeminiKey).filter(GeminiKey.id == key_id, GeminiKey.tenant_id == tenant.id).first()
    if not key:
        raise HTTPException(404, "Key tidak ditemukan")
    db.delete(key)
    db.commit()
    load_tenant_keys_from_db(db, tenant.id)


@router.post("/{key_id}/toggle")
def toggle_key(key_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    key = db.query(GeminiKey).filter(GeminiKey.id == key_id, GeminiKey.tenant_id == tenant.id).first()
    if not key:
        raise HTTPException(404, "Key tidak ditemukan")
    key.is_active = not key.is_active
    db.commit()
    db.refresh(key)
    load_tenant_keys_from_db(db, tenant.id)
    return {"id": key.id, "is_active": key.is_active}


@router.post("/test")
def test_key(data: KeyTest):
    try:
        import google.generativeai as genai
        genai.configure(api_key=data.api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        resp = model.generate_content("Say OK")
        if resp.text:
            return {"valid": True, "model": "gemini-2.0-flash"}
        return {"valid": False, "error": "Tidak ada respons dari model"}
    except Exception as e:
        return {"valid": False, "error": str(e)}
