import os
import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.core.database import get_db
from backend.core.deps import get_current_tenant
from backend.core.config import settings
from backend.models.models import Channel, Tenant

router = APIRouter()

NICHES = [
    "motivasi", "edukasi", "humor", "fakta", "tutorial",
    "lifestyle", "finance", "kesehatan", "teknologi", "lainnya"
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
    youtube_channel_id: Optional[str]
    subscriber_count: int
    created_at: datetime

    class Config:
        from_attributes = True


def _channel_out(c: Channel) -> dict:
    return {
        "id": c.id,
        "channel_name": c.channel_name,
        "niche": c.niche,
        "is_active": c.is_active,
        "has_youtube_auth": c.youtube_credentials is not None,
        "youtube_channel_id": c.youtube_channel_id,
        "subscriber_count": c.subscriber_count or 0,
        "created_at": c.created_at,
    }


@router.get("")
def list_channels(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    channels = db.query(Channel).filter(Channel.tenant_id == tenant.id).all()
    return {"channels": [_channel_out(c) for c in channels]}


@router.post("", status_code=201)
def create_channel(data: ChannelCreate, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    if data.niche not in NICHES:
        raise HTTPException(400, f"Niche tidak valid. Pilih: {', '.join(NICHES)}")
    channel = Channel(
        id=str(uuid.uuid4()),
        tenant_id=tenant.id,
        channel_name=data.channel_name,
        niche=data.niche,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return _channel_out(channel)


@router.delete("/{channel_id}", status_code=204)
def delete_channel(channel_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id, Channel.tenant_id == tenant.id).first()
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan")
    db.delete(ch)
    db.commit()


@router.get("/{channel_id}/oauth-url")
def get_oauth_url(channel_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id, Channel.tenant_id == tenant.id).first()
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan")

    client_id = os.getenv("YOUTUBE_CLIENT_ID", "")
    redirect_uri = os.getenv("YOUTUBE_REDIRECT_URI", "")
    if not client_id or not redirect_uri:
        raise HTTPException(400, "YOUTUBE_CLIENT_ID dan YOUTUBE_REDIRECT_URI belum dikonfigurasi")

    scopes = " ".join([
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/youtube",
    ])
    url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scopes}"
        f"&access_type=offline"
        f"&prompt=consent"
        f"&state={channel_id}"
    )
    return {"auth_url": url}


@router.post("/{channel_id}/oauth-callback")
def oauth_callback(
    channel_id: str,
    body: dict,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    ch = db.query(Channel).filter(Channel.id == channel_id, Channel.tenant_id == tenant.id).first()
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan")

    code = body.get("code")
    if not code:
        raise HTTPException(400, "Parameter 'code' diperlukan")

    try:
        from backend.modules.youtube_uploader.uploader import exchange_code_for_token
        credentials = exchange_code_for_token(code)
        ch.youtube_credentials = credentials
        db.commit()
        return {"success": True, "message": "YouTube terhubung"}
    except Exception as e:
        raise HTTPException(400, f"Gagal tukar kode OAuth: {str(e)}")


@router.get("/{channel_id}/best-hours")
def best_hours(channel_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id, Channel.tenant_id == tenant.id).first()
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan")
    hours = ch.best_upload_hours or [7, 12, 19, 21]
    return {"channel_id": channel_id, "hours": hours, "source": "analytics" if ch.best_upload_hours else "default"}
