"""
TikTok Content Posting API v2 — upload video ke TikTok.
Docs: https://developers.tiktok.com/doc/content-posting-api-get-started/

Flow:
1. POST /v2/post/publish/video/init/  → dapat upload_url & publish_id
2. PUT chunks ke upload_url
3. GET /v2/post/publish/status/fetch/ → polling status
"""
import logging
import math
import os
import time
from typing import Optional

import requests

log = logging.getLogger(__name__)

TIKTOK_API_BASE = "https://open.tiktokapis.com"
CHUNK_SIZE = 10 * 1024 * 1024   # 10 MB per chunk


def _auth_headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }


def init_video_upload(
    access_token: str,
    video_size: int,
    title: str,
    disable_comment: bool = False,
    disable_duet: bool = False,
    disable_stitch: bool = False,
) -> tuple[str, str, int]:
    """
    Inisiasi upload. Returns (publish_id, upload_url, chunk_size).
    """
    chunk_count = math.ceil(video_size / CHUNK_SIZE)
    payload = {
        "post_info": {
            "title": title[:2200],
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "disable_comment": disable_comment,
            "disable_duet": disable_duet,
            "disable_stitch": disable_stitch,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": CHUNK_SIZE,
            "total_chunk_count": chunk_count,
        },
    }
    resp = requests.post(
        f"{TIKTOK_API_BASE}/v2/post/publish/video/init/",
        headers=_auth_headers(access_token),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("error", {}).get("code") != "ok":
        raise RuntimeError(f"TikTok init error: {data.get('error')}")

    upload_url = data["data"]["upload_url"]
    publish_id = data["data"]["publish_id"]
    return publish_id, upload_url, CHUNK_SIZE


def upload_chunks(upload_url: str, video_path: str) -> None:
    """Upload file dalam chunks ke TikTok upload URL."""
    video_size = os.path.getsize(video_path)
    chunk_count = math.ceil(video_size / CHUNK_SIZE)

    with open(video_path, "rb") as f:
        for i in range(chunk_count):
            start = i * CHUNK_SIZE
            end = min(start + CHUNK_SIZE, video_size) - 1
            chunk = f.read(CHUNK_SIZE)

            headers = {
                "Content-Range": f"bytes {start}-{end}/{video_size}",
                "Content-Type": "video/mp4",
                "Content-Length": str(len(chunk)),
            }
            resp = requests.put(upload_url, headers=headers, data=chunk, timeout=120)
            if resp.status_code not in (200, 201, 206):
                raise RuntimeError(
                    f"TikTok chunk upload gagal chunk {i+1}/{chunk_count}: "
                    f"HTTP {resp.status_code} — {resp.text[:200]}"
                )
            log.info(f"TikTok chunk {i+1}/{chunk_count} uploaded")


def poll_publish_status(access_token: str, publish_id: str, max_wait: int = 300) -> str:
    """Poll status sampai PUBLISH_COMPLETE atau timeout. Returns final video_id."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        resp = requests.post(
            f"{TIKTOK_API_BASE}/v2/post/publish/status/fetch/",
            headers=_auth_headers(access_token),
            json={"publish_id": publish_id},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        status = data.get("data", {}).get("status", "")
        if status == "PUBLISH_COMPLETE":
            video_id = data["data"].get("publicaly_available_post_id", [None])[0]
            log.info(f"TikTok publish complete: video_id={video_id}")
            return str(video_id) if video_id else publish_id
        elif status in ("FAILED", "PUBLISH_FAILED"):
            reason = data.get("data", {}).get("fail_reason", "unknown")
            raise RuntimeError(f"TikTok publish gagal: {reason}")
        log.debug(f"TikTok status={status}, tunggu 10s...")
        time.sleep(10)
    raise TimeoutError(f"TikTok publish timeout setelah {max_wait}s")


def upload_video_to_tiktok(
    access_token: str,
    video_path: str,
    title: str,
    description: str = "",
) -> Optional[str]:
    """
    Full upload flow ke TikTok. Returns TikTok video_id.
    Raises RuntimeError jika gagal.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video tidak ditemukan: {video_path}")

    video_size = os.path.getsize(video_path)
    # TikTok max 4GB, min 1 frame
    if video_size > 4 * 1024 * 1024 * 1024:
        raise ValueError("Video terlalu besar untuk TikTok (maks 4GB)")

    # Gunakan title + description (TikTok hanya punya 1 text field)
    caption = title
    if description:
        caption = f"{title}\n{description}"

    log.info(f"TikTok upload mulai: {os.path.basename(video_path)} ({video_size} bytes)")
    publish_id, upload_url, _ = init_video_upload(access_token, video_size, caption)
    upload_chunks(upload_url, video_path)
    video_id = poll_publish_status(access_token, publish_id)
    log.info(f"TikTok upload selesai: video_id={video_id}")
    return video_id


def get_tiktok_oauth_url(redirect_uri: str, state: str = "") -> str:
    """Generate TikTok OAuth2 authorization URL."""
    client_key = os.getenv("TIKTOK_CLIENT_KEY", "")
    if not client_key:
        raise ValueError("TIKTOK_CLIENT_KEY belum dikonfigurasi")
    scopes = "user.info.basic,video.publish,video.upload"
    url = (
        f"https://www.tiktok.com/v2/auth/authorize/"
        f"?client_key={client_key}"
        f"&scope={scopes}"
        f"&response_type=code"
        f"&redirect_uri={redirect_uri}"
        f"&state={state}"
    )
    return url


def exchange_tiktok_code(code: str, redirect_uri: str) -> dict:
    """Exchange authorization code untuk access_token."""
    client_key = os.getenv("TIKTOK_CLIENT_KEY", "")
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET", "")
    resp = requests.post(
        f"{TIKTOK_API_BASE}/v2/oauth/token/",
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"TikTok OAuth error: {data}")
    return data


def refresh_tiktok_token(refresh_token: str) -> dict:
    """Refresh access token."""
    client_key = os.getenv("TIKTOK_CLIENT_KEY", "")
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET", "")
    resp = requests.post(
        f"{TIKTOK_API_BASE}/v2/oauth/token/",
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
