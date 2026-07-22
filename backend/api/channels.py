"""Channel management (one tenant → many YouTube channels)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from backend.core.database import get_db
from backend.core.deps import get_current_tenant
from backend.models.models import Channel, Tenant

router = APIRouter(prefix="/api/channels", tags=["channels"])

NICHES = [
    "motivasi", "edukasi", "humor", "fakta_unik", "teknologi",
    "bisnis", "kesehatan", "gaming", "travel", "resep_masakan",
    "fashion", "olahraga", "berita", "lifestyle", "sains",
]


class ChannelCreate(BaseModel):
    channel_name: str
    niche: str


class ChannelOut(BaseModel):
    id: str
    channel_name: str
    niche: str
    is_active: bool
    has_youtube_auth: bool

    class Config:
        from_attributes = True


@router.get("/niches")
def get_niches():
    return {"niches": NICHES}


@router.get("/", response_model=list[ChannelOut])
def list_channels(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    channels = db.query(Channel).filter(Channel.tenant_id == tenant.id).all()
    return [
        ChannelOut(
            id=c.id,
            channel_name=c.channel_name,
            niche=c.niche,
            is_active=c.is_active,
            has_youtube_auth=bool(c.youtube_credentials),
        )
        for c in channels
    ]


@router.post("/", status_code=201, response_model=ChannelOut)
def create_channel(body: ChannelCreate, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    if body.niche not in NICHES:
        raise HTTPException(400, f"Invalid niche. Valid options: {NICHES}")
    ch = Channel(tenant_id=tenant.id, channel_name=body.channel_name, niche=body.niche)
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return ChannelOut(id=ch.id, channel_name=ch.channel_name, niche=ch.niche, is_active=ch.is_active, has_youtube_auth=False)


@router.delete("/{channel_id}", status_code=204)
def delete_channel(channel_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id, Channel.tenant_id == tenant.id).first()
    if not ch:
        raise HTTPException(404, "Channel not found")
    db.delete(ch)
    db.commit()
