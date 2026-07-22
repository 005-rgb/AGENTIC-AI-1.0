from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import uuid

from backend.core.database import get_db
from backend.core.deps import get_current_tenant
from backend.models.models import HookLibrary, Tenant

router = APIRouter()


class HookCreate(BaseModel):
    niche: str
    hook_text: str


class HookOut(BaseModel):
    id: str
    niche: str
    hook_text: str
    avg_ctr: Optional[float] = None
    use_count: int
    is_approved: bool
    tenant_id: Optional[str] = None

    class Config:
        from_attributes = True


def _hook_out(h) -> dict:
    return {
        "id": h.id,
        "niche": h.niche,
        "hook_text": h.hook_text,
        "avg_ctr": h.avg_ctr,
        "use_count": h.use_count,
        "is_approved": h.is_approved,
        "tenant_id": h.tenant_id,
    }


@router.get("")
def list_hooks(
    niche: Optional[str] = None,
    limit: int = 20,
    sort: str = "use_count",   # use_count | avg_ctr | created_at
    db: Session = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    """List global approved hooks + tenant's own hooks."""
    query = db.query(HookLibrary).filter(
        (HookLibrary.tenant_id == None) & (HookLibrary.is_approved == True) |
        (HookLibrary.tenant_id == current_tenant.id)
    )
    if niche:
        query = query.filter(HookLibrary.niche == niche)

    if sort == "avg_ctr":
        query = query.order_by(HookLibrary.avg_ctr.desc().nullslast())
    elif sort == "created_at":
        query = query.order_by(HookLibrary.created_at.desc())
    else:
        query = query.order_by(HookLibrary.use_count.desc())

    hooks = query.limit(limit).all()
    return {"hooks": [_hook_out(h) for h in hooks], "total": len(hooks)}


@router.get("/best")
def best_hooks(
    niche: Optional[str] = None,
    db: Session = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    """Top 5 hooks by CTR for a niche."""
    query = db.query(HookLibrary).filter(
        HookLibrary.is_approved == True,
        HookLibrary.avg_ctr != None,
    )
    if niche:
        query = query.filter(HookLibrary.niche == niche)
    hooks = query.order_by(HookLibrary.avg_ctr.desc()).limit(5).all()
    return {"hooks": [_hook_out(h) for h in hooks]}


@router.post("", status_code=201)
def create_hook(
    data: HookCreate,
    db: Session = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    hook = HookLibrary(
        id=str(uuid.uuid4()),
        tenant_id=current_tenant.id,
        niche=data.niche,
        hook_text=data.hook_text,
        is_approved=True,  # tenant hooks are auto-approved
    )
    db.add(hook)
    db.commit()
    db.refresh(hook)
    return _hook_out(hook)


@router.delete("/{hook_id}", status_code=204)
def delete_hook(
    hook_id: str,
    db: Session = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    hook = db.query(HookLibrary).filter(
        HookLibrary.id == hook_id,
        HookLibrary.tenant_id == current_tenant.id,
    ).first()
    if not hook:
        raise HTTPException(404, "Hook tidak ditemukan atau bukan milik Anda")
    db.delete(hook)
    db.commit()


@router.post("/{hook_id}/increment-use")
def increment_use(
    hook_id: str,
    db: Session = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    hook = db.query(HookLibrary).filter(HookLibrary.id == hook_id).first()
    if not hook:
        raise HTTPException(404, "Hook tidak ditemukan")
    hook.use_count = (hook.use_count or 0) + 1
    db.commit()
    return {"use_count": hook.use_count}
