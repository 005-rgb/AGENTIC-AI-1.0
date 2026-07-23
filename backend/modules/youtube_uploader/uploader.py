"""
YouTube Uploader — OAuth2 flow + resumable video upload.
Credentials disimpan terenkripsi via backend.core.encryption.
"""
import os
import json
import requests
from datetime import datetime, timezone
from time import time
from typing import Optional

from backend.models.models import VideoJob, Channel

YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
YOUTUBE_API_URL    = "https://www.googleapis.com/youtube/v3"


def exchange_code_for_token(code: str) -> dict:
    from backend.core.config import settings
    resp = requests.post(YOUTUBE_TOKEN_URL, data={
        "code": code,
        "client_id": settings.YOUTUBE_CLIENT_ID,
        "client_secret": settings.YOUTUBE_CLIENT_SECRET,
        "redirect_uri": settings.YOUTUBE_REDIRECT_URI,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    data = resp.json()
    # Tambahkan expires_at untuk auto-refresh
    if "expires_in" in data:
        data["expires_at"] = time() + data["expires_in"]
    return data


def _refresh_token(credentials: dict) -> dict:
    from backend.core.config import settings
    resp = requests.post(YOUTUBE_TOKEN_URL, data={
        "refresh_token": credentials.get("refresh_token"),
        "client_id": settings.YOUTUBE_CLIENT_ID,
        "client_secret": settings.YOUTUBE_CLIENT_SECRET,
        "grant_type": "refresh_token",
    })
    resp.raise_for_status()
    data = resp.json()
    credentials["access_token"] = data["access_token"]
    if "expires_in" in data:
        credentials["expires_at"] = time() + data["expires_in"]
    return credentials


def _get_access_token(channel: Channel, db) -> str:
    """Decrypt credentials, refresh jika perlu, return access_token."""
    from backend.core.encryption import decrypt_credentials, encrypt_credentials

    creds = decrypt_credentials(channel.youtube_credentials)
    if not creds:
        raise RuntimeError("YouTube credentials tidak ditemukan")

    expires_at = creds.get("expires_at", 0)
    if expires_at and time() > expires_at - 60:
        creds = _refresh_token(creds)
        channel.youtube_credentials = encrypt_credentials(creds)
        db.commit()

    return creds.get("access_token", "")


def upload_video(job: VideoJob, channel: Channel, db) -> str:
    access_token = _get_access_token(channel, db)
    if not access_token:
        raise RuntimeError("Access token tidak tersedia")

    video_path = f"storage/{job.tenant_id}/output/{job.output_filename}"
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"File output tidak ditemukan: {video_path}")

    title = (job.title or "YouTube Shorts")[:100]
    description = (job.description or "") + "\n\n#Shorts"
    tags = list(job.tags or []) + ["shorts", "ytshorts"]

    metadata = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": [t for t in tags if t][:500],
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": "public",
            "madeForKids": False,
        },
    }

    # Initiate resumable upload
    file_size = os.path.getsize(video_path)
    init_resp = requests.post(
        f"{YOUTUBE_UPLOAD_URL}?uploadType=resumable&part=snippet,status",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(file_size),
        },
        json=metadata,
    )
    init_resp.raise_for_status()
    upload_url = init_resp.headers.get("Location")
    if not upload_url:
        raise RuntimeError("Gagal mendapatkan upload URL dari YouTube")

    # Upload file
    with open(video_path, "rb") as f:
        upload_resp = requests.put(
            upload_url,
            headers={
                "Content-Length": str(file_size),
                "Content-Type": "video/mp4",
            },
            data=f,
        )
    upload_resp.raise_for_status()
    result = upload_resp.json()
    video_id = result.get("id", "")

    job.youtube_video_id = video_id
    job.status = "uploaded"
    job.uploaded_at = datetime.now(timezone.utc)
    db.commit()

    return video_id


def upload_video_variant_b(job: VideoJob, channel: Channel, db) -> str:
    """Upload variant B untuk A/B test — judul berbeda, video sama."""
    access_token = _get_access_token(channel, db)
    if not access_token:
        raise RuntimeError("Access token tidak tersedia")

    video_path = f"storage/{job.tenant_id}/output/{job.output_filename}"
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"File output tidak ditemukan: {video_path}")

    title_b = (job.title_variant_b or f"{job.title} [Ver.2]")[:100]
    description = (job.description or "") + "\n\n#Shorts"

    metadata = {
        "snippet": {
            "title": title_b,
            "description": description,
            "tags": list(job.tags or []) + ["shorts", "ytshorts"],
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": "public",
            "madeForKids": False,
        },
    }

    file_size = os.path.getsize(video_path)
    init_resp = requests.post(
        f"{YOUTUBE_UPLOAD_URL}?uploadType=resumable&part=snippet,status",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(file_size),
        },
        json=metadata,
    )
    init_resp.raise_for_status()
    upload_url = init_resp.headers.get("Location")
    if not upload_url:
        raise RuntimeError("Gagal mendapatkan upload URL dari YouTube (variant B)")

    with open(video_path, "rb") as f:
        upload_resp = requests.put(
            upload_url,
            headers={"Content-Length": str(file_size), "Content-Type": "video/mp4"},
            data=f,
        )
    upload_resp.raise_for_status()
    video_id_b = upload_resp.json().get("id", "")

    job.youtube_video_id_b = video_id_b
    db.commit()
    return video_id_b


def fetch_video_analytics(channel: Channel, video_id: str) -> dict:
    """Fetch basic stats untuk satu video dari YouTube Data API."""
    from backend.core.encryption import decrypt_credentials

    creds = decrypt_credentials(channel.youtube_credentials)
    access_token = creds.get("access_token", "")
    if not access_token:
        return {}

    resp = requests.get(
        f"{YOUTUBE_API_URL}/videos",
        params={"part": "statistics", "id": video_id},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if resp.status_code != 200:
        return {}

    items = resp.json().get("items", [])
    if not items:
        return {}

    stats = items[0].get("statistics", {})
    return {
        "views": int(stats.get("viewCount", 0)),
        "likes": int(stats.get("likeCount", 0)),
        "comments": int(stats.get("commentCount", 0)),
        "ctr": 0.0,  # CTR butuh YouTube Analytics API scope
    }
