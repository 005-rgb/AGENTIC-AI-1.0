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
from backend.core.encryption import encrypt_credentials, decrypt_credentials
from backend.core.plan_limits import check_channel_limit
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
    has_tiktok_auth: bool
    has_instagram_auth: bool
    has_facebook_auth: bool
    youtube_channel_id: Optional[str]
    subscriber_count: int
    best_upload_hours: Optional[List[int]]
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
        "has_tiktok_auth": c.tiktok_credentials is not None,
        "has_instagram_auth": c.meta_ig_user_id is not None,
        "has_facebook_auth": c.meta_page_id is not None,
        "youtube_channel_id": c.youtube_channel_id,
        "subscriber_count": c.subscriber_count or 0,
        "best_upload_hours": c.best_upload_hours or [7, 12, 19, 21],
        "created_at": c.created_at,
    }


# ─── CRUD ───────────────────────────────────────────────────────────────

@router.get("")
def list_channels(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    channels = db.query(Channel).filter(Channel.tenant_id == tenant.id).all()
    return {"channels": [_channel_out(c) for c in channels]}


@router.post("", status_code=201)
def create_channel(
    data: ChannelCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    if data.niche not in NICHES:
        raise HTTPException(400, f"Niche tidak valid. Pilih: {', '.join(NICHES)}")
    check_channel_limit(tenant, db)
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
def delete_channel(
    channel_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    ch = db.query(Channel).filter(Channel.id == channel_id, Channel.tenant_id == tenant.id).first()
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan")
    db.delete(ch)
    db.commit()


# ─── YouTube OAuth ───────────────────────────────────────────────────────

@router.get("/{channel_id}/oauth-url")
def get_youtube_oauth_url(
    channel_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    ch = db.query(Channel).filter(Channel.id == channel_id, Channel.tenant_id == tenant.id).first()
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan")

    client_id = settings.YOUTUBE_CLIENT_ID
    redirect_uri = settings.YOUTUBE_REDIRECT_URI
    if not client_id or not redirect_uri:
        raise HTTPException(400, "YOUTUBE_CLIENT_ID dan YOUTUBE_REDIRECT_URI belum dikonfigurasi")

    scopes = " ".join([
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
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
def youtube_oauth_callback(
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
        ch.youtube_credentials = encrypt_credentials(credentials)
        db.commit()
        return {"success": True, "message": "YouTube terhubung"}
    except Exception as e:
        raise HTTPException(400, f"Gagal tukar kode OAuth: {str(e)}")


@router.delete("/{channel_id}/youtube-disconnect", status_code=204)
def youtube_disconnect(
    channel_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    ch = db.query(Channel).filter(Channel.id == channel_id, Channel.tenant_id == tenant.id).first()
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan")
    ch.youtube_credentials = None
    ch.youtube_channel_id = None
    db.commit()


# ─── TikTok OAuth ────────────────────────────────────────────────────────

@router.get("/{channel_id}/tiktok-oauth-url")
def get_tiktok_oauth_url(
    channel_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    ch = db.query(Channel).filter(Channel.id == channel_id, Channel.tenant_id == tenant.id).first()
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan")
    if not settings.TIKTOK_CLIENT_KEY:
        raise HTTPException(400, "TIKTOK_CLIENT_KEY belum dikonfigurasi")

    try:
        from backend.modules.tiktok.uploader import get_tiktok_oauth_url
        url = get_tiktok_oauth_url(
            redirect_uri=settings.TIKTOK_REDIRECT_URI,
            state=channel_id,
        )
        return {"auth_url": url}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{channel_id}/tiktok-callback")
def tiktok_oauth_callback(
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
        from backend.modules.tiktok.uploader import exchange_tiktok_code
        data = exchange_tiktok_code(code, settings.TIKTOK_REDIRECT_URI)
        from time import time
        creds = {
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token"),
            "open_id": data.get("open_id"),
            "expires_at": time() + data.get("expires_in", 86400),
        }
        ch.tiktok_credentials = encrypt_credentials(creds)
        ch.tiktok_open_id = data.get("open_id")
        db.commit()
        return {"success": True, "message": "TikTok terhubung", "open_id": creds["open_id"]}
    except Exception as e:
        raise HTTPException(400, f"Gagal OAuth TikTok: {str(e)}")


@router.delete("/{channel_id}/tiktok-disconnect", status_code=204)
def tiktok_disconnect(
    channel_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    ch = db.query(Channel).filter(Channel.id == channel_id, Channel.tenant_id == tenant.id).first()
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan")
    ch.tiktok_credentials = None
    ch.tiktok_open_id = None
    db.commit()


# ─── Meta OAuth (Instagram + Facebook) ──────────────────────────────────

@router.get("/{channel_id}/meta-oauth-url")
def get_meta_oauth_url_endpoint(
    channel_id: str,
    platform: str = "instagram",
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    ch = db.query(Channel).filter(Channel.id == channel_id, Channel.tenant_id == tenant.id).first()
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan")
    if not settings.META_APP_ID:
        raise HTTPException(400, "META_APP_ID belum dikonfigurasi")
    if platform not in ("instagram", "facebook"):
        raise HTTPException(400, "platform harus 'instagram' atau 'facebook'")

    try:
        from backend.modules.meta.uploader import get_meta_oauth_url
        state = f"{channel_id}:{platform}"
        url = get_meta_oauth_url(settings.META_REDIRECT_URI, state=state, platform=platform)
        return {"auth_url": url, "platform": platform}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{channel_id}/meta-callback")
def meta_oauth_callback(
    channel_id: str,
    body: dict,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    ch = db.query(Channel).filter(Channel.id == channel_id, Channel.tenant_id == tenant.id).first()
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan")

    code = body.get("code")
    platform = body.get("platform", "instagram")
    if not code:
        raise HTTPException(400, "Parameter 'code' diperlukan")

    try:
        from backend.modules.meta.uploader import (
            exchange_meta_code, get_user_pages, get_instagram_account_id
        )
        token_data = exchange_meta_code(code, settings.META_REDIRECT_URI)
        access_token = token_data["access_token"]

        pages = get_user_pages(access_token)
        page_id = pages[0]["id"] if pages else None
        page_token = pages[0].get("access_token", access_token) if pages else access_token

        ig_user_id = None
        if platform == "instagram" and page_id:
            ig_user_id = get_instagram_account_id(page_token, page_id)

        creds = {
            "access_token": page_token,
            "user_access_token": access_token,
            "page_id": page_id,
            "ig_user_id": ig_user_id,
        }
        ch.meta_credentials = encrypt_credentials(creds)
        ch.meta_page_id = page_id
        ch.meta_ig_user_id = ig_user_id
        db.commit()

        return {
            "success": True,
            "message": f"Meta ({platform}) terhubung",
            "page_id": page_id,
            "ig_user_id": ig_user_id,
        }
    except Exception as e:
        raise HTTPException(400, f"Gagal OAuth Meta: {str(e)}")


@router.delete("/{channel_id}/meta-disconnect", status_code=204)
def meta_disconnect(
    channel_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    ch = db.query(Channel).filter(Channel.id == channel_id, Channel.tenant_id == tenant.id).first()
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan")
    ch.meta_credentials = None
    ch.meta_page_id = None
    ch.meta_ig_user_id = None
    db.commit()


# ─── Analytics helper ────────────────────────────────────────────────────

@router.get("/{channel_id}/best-hours")
def best_hours(
    channel_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    ch = db.query(Channel).filter(Channel.id == channel_id, Channel.tenant_id == tenant.id).first()
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan")
    hours = ch.best_upload_hours or [7, 12, 19, 21]
    return {
        "channel_id": channel_id,
        "hours": hours,
        "source": "analytics" if ch.best_upload_hours else "default",
    }
