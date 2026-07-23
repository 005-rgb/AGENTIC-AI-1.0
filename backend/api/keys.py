from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import uuid

from backend.core.database import get_db
from backend.core.deps import get_current_tenant
from backend.core.ai_pool import load_from_db, PROVIDER_ORDER
from backend.models.models import GeminiKey, Tenant

router = APIRouter()

VALID_PROVIDERS = {"gemini", "groq"}

PROVIDER_LABELS = {
    "gemini": "Gemini (Google)",
    "groq":   "Groq (LLaMA)",
}


def mask_key(key: str) -> str:
    return key[:8] + "***" if len(key) > 8 else "***"


class KeyOut(BaseModel):
    id: str
    label: str
    api_key: str
    provider: str
    is_active: bool
    usage_count: int
    last_used_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class KeyCreate(BaseModel):
    api_key: str
    label: str = ""
    provider: str = "gemini"


class KeyBulkItem(BaseModel):
    api_key: str
    label: str = ""
    provider: str = "gemini"


class KeyBulkCreate(BaseModel):
    keys: List[KeyBulkItem]


class KeyTest(BaseModel):
    api_key: str
    provider: str = "gemini"


def _key_out(k: GeminiKey) -> KeyOut:
    return KeyOut(
        id=k.id,
        label=k.label or "",
        api_key=mask_key(k.api_key),
        provider=getattr(k, "provider", "gemini") or "gemini",
        is_active=k.is_active,
        usage_count=k.usage_count or 0,
        last_used_at=k.last_used_at,
        created_at=k.created_at,
    )


def _pool_summary(tenant_id: str) -> dict:
    from backend.core.ai_pool import ai_manager
    return ai_manager.summary(tenant_id)


@router.get("")
def list_keys(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    keys = db.query(GeminiKey).filter(GeminiKey.tenant_id == tenant.id).order_by(GeminiKey.created_at).all()
    active_count = sum(1 for k in keys if k.is_active)
    return {
        "keys": [_key_out(k) for k in keys],
        "total": len(keys),
        "pool_size": active_count,
        "pool_by_provider": _pool_summary(tenant.id),
        "providers": PROVIDER_LABELS,
    }


@router.post("", status_code=201)
def add_key(data: KeyCreate, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    if data.provider not in VALID_PROVIDERS:
        raise HTTPException(400, f"Provider tidak valid. Pilihan: {', '.join(VALID_PROVIDERS)}")
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
        provider=data.provider,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    load_from_db(db, tenant.id)
    return _key_out(key)


@router.post("/bulk", status_code=201)
def add_keys_bulk(data: KeyBulkCreate, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    """Import banyak API key sekaligus. Duplikat dilewati."""
    added, skipped, errors = [], [], []

    existing_keys = {
        k.api_key for k in db.query(GeminiKey).filter(GeminiKey.tenant_id == tenant.id).all()
    }

    for item in data.keys:
        raw = item.api_key.strip()
        if not raw:
            continue
        provider = item.provider if item.provider in VALID_PROVIDERS else "gemini"

        if raw in existing_keys:
            skipped.append(raw[:8] + "***")
            continue

        try:
            key = GeminiKey(
                id=str(uuid.uuid4()),
                tenant_id=tenant.id,
                api_key=raw,
                label=item.label or "",
                provider=provider,
            )
            db.add(key)
            existing_keys.add(raw)
            added.append(raw[:8] + "***")
        except Exception as e:
            errors.append({"key": raw[:8] + "***", "error": str(e)})

    db.commit()
    load_from_db(db, tenant.id)
    return {"added": len(added), "skipped": len(skipped), "errors": errors}


@router.delete("/{key_id}", status_code=204)
def delete_key(key_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    key = db.query(GeminiKey).filter(GeminiKey.id == key_id, GeminiKey.tenant_id == tenant.id).first()
    if not key:
        raise HTTPException(404, "Key tidak ditemukan")
    db.delete(key)
    db.commit()
    load_from_db(db, tenant.id)


@router.post("/{key_id}/toggle")
def toggle_key(key_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    key = db.query(GeminiKey).filter(GeminiKey.id == key_id, GeminiKey.tenant_id == tenant.id).first()
    if not key:
        raise HTTPException(404, "Key tidak ditemukan")
    key.is_active = not key.is_active
    db.commit()
    db.refresh(key)
    load_from_db(db, tenant.id)
    return {"id": key.id, "is_active": key.is_active}


@router.post("/test")
def test_key(data: KeyTest):
    """Test apakah API key valid untuk provider tertentu."""
    provider = data.provider if data.provider in VALID_PROVIDERS else "gemini"
    try:
        if provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=data.api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")
            resp = model.generate_content("Say OK in one word")
            if resp.text:
                return {"valid": True, "provider": "gemini", "model": "gemini-2.0-flash"}
            return {"valid": False, "provider": "gemini", "error": "Tidak ada respons dari model"}

        elif provider == "groq":
            from groq import Groq
            client = Groq(api_key=data.api_key)
            chat = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": "Say OK"}],
                max_tokens=5,
            )
            if chat.choices[0].message.content:
                return {"valid": True, "provider": "groq", "model": "llama-3.3-70b-versatile"}
            return {"valid": False, "provider": "groq", "error": "Tidak ada respons dari model"}

    except Exception as e:
        return {"valid": False, "provider": provider, "error": str(e)}
