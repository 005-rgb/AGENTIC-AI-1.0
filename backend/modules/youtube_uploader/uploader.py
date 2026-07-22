"""
YouTube Uploader — OAuth2 flow + resumable video upload.
"""
import os
import json
import requests
from datetime import datetime, timezone
from typing import Optional

from backend.models.models import VideoJob, Channel


YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
YOUTUBE_API_URL    = "https://www.googleapis.com/youtube/v3"


def exchange_code_for_token(code: str) -> dict:
    client_id     = os.getenv("YOUTUBE_CLIENT_ID", "")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET", "")
    redirect_uri  = os.getenv("YOUTUBE_REDIRECT_URI", "")

    resp = requests.post(YOUTUBE_TOKEN_URL, data={
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    return resp.json()


def _refresh_token(credentials: dict) -> dict:
    client_id     = os.getenv("YOUTUBE_CLIENT_ID", "")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET", "")

    resp = requests.post(YOUTUBE_TOKEN_URL, data={
        "refresh_token": credentials.get("refresh_token"),
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
    })
    resp.raise_for_status()
    data = resp.json()
    credentials["access_token"] = data["access_token"]
    if "expires_in" in data:
        from time import time
        credentials["expires_at"] = time() + data["expires_in"]
    return credentials


def _get_access_token(channel: Channel, db) -> str:
    creds = channel.youtube_credentials or {}
    from time import time
    expires_at = creds.get("expires_at", 0)
    if expires_at and time() > expires_at - 60:
        creds = _refresh_token(creds)
        channel.youtube_credentials = creds
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

    # Initiate resumable upload
    metadata = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags[:500],
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": "public",
            "madeForKids": False,
        },
    }

    init_resp = requests.post(
        f"{YOUTUBE_UPLOAD_URL}?uploadType=resumable&part=snippet,status",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
        },
        json=metadata,
    )
    init_resp.raise_for_status()
    upload_url = init_resp.headers.get("Location")
    if not upload_url:
        raise RuntimeError("Gagal mendapatkan upload URL dari YouTube")

    # Upload file
    file_size = os.path.getsize(video_path)
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

    # Update job
    job.youtube_video_id = video_id
    job.status = "uploaded"
    job.uploaded_at = datetime.now(timezone.utc)
    db.commit()

    return video_id


def fetch_video_analytics(channel: Channel, video_id: str) -> dict:
    """Fetch basic stats for a video from YouTube Data API."""
    creds = channel.youtube_credentials or {}
    access_token = creds.get("access_token", "")
    if not access_token:
        return {}

    resp = requests.get(
        f"{YOUTUBE_API_URL}/videos",
        params={
            "part": "statistics",
            "id": video_id,
        },
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
        "ctr": 0.0,  # CTR needs YouTube Analytics API (OAuth scope)
    }
