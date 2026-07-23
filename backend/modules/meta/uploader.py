"""
Meta Graph API — upload video ke Instagram Reels dan Facebook Reels.

Instagram Reels flow:
  1. POST /{ig-user-id}/media  (media_type=REELS, video_url=...)
  2. Poll GET /{creation-id}?fields=status_code
  3. POST /{ig-user-id}/media_publish

Facebook Reels flow:
  1. POST /{page-id}/video_reels (upload_phase=start)
  2. PUT upload_url (binary video)
  3. POST /{page-id}/video_reels (upload_phase=finish)

Docs: https://developers.facebook.com/docs/video-api/reels
"""
import logging
import os
import time
from typing import Optional

import requests

log = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


# ─────────────────────────────────────────────
# Instagram Reels
# ─────────────────────────────────────────────

def upload_instagram_reels(
    access_token: str,
    ig_user_id: str,
    video_path: str,
    caption: str = "",
    public_video_url: Optional[str] = None,
) -> Optional[str]:
    """
    Upload video ke Instagram Reels.
    Returns instagram media_id atau None jika gagal.
    
    Jika public_video_url tersedia, gunakan URL upload (lebih cepat).
    Jika tidak, upload file langsung via resumable upload.
    """
    if not os.path.exists(video_path) and not public_video_url:
        raise FileNotFoundError(f"Video tidak ditemukan: {video_path}")

    log.info(f"Instagram Reels upload mulai untuk ig_user_id={ig_user_id}")

    # Step 1: Create media container
    if public_video_url:
        params = {
            "media_type": "REELS",
            "video_url": public_video_url,
            "caption": caption[:2200],
            "share_to_feed": "true",
            "access_token": access_token,
        }
        resp = requests.post(f"{GRAPH_API_BASE}/{ig_user_id}/media", params=params, timeout=60)
    else:
        # Resumable upload
        file_size = os.path.getsize(video_path)
        # Start upload session
        start_resp = requests.post(
            f"{GRAPH_API_BASE}/{ig_user_id}/media",
            params={
                "media_type": "REELS",
                "upload_type": "resumable",
                "caption": caption[:2200],
                "share_to_feed": "true",
                "access_token": access_token,
            },
            timeout=30,
        )
        start_resp.raise_for_status()
        start_data = start_resp.json()
        upload_url = start_data.get("uri")
        creation_id = start_data.get("id")

        if not upload_url:
            raise RuntimeError(f"Instagram tidak memberi upload URI: {start_data}")

        # Upload file
        with open(video_path, "rb") as f:
            video_data = f.read()
        upload_resp = requests.post(
            upload_url,
            headers={
                "Authorization": f"OAuth {access_token}",
                "offset": "0",
                "file_size": str(file_size),
            },
            data=video_data,
            timeout=300,
        )
        upload_resp.raise_for_status()
        resp = type("R", (), {"json": lambda s: {"id": creation_id}, "raise_for_status": lambda s: None})()

    resp.raise_for_status() if hasattr(resp, "raise_for_status") and callable(resp.raise_for_status) else None
    creation_id = resp.json().get("id")
    if not creation_id:
        raise RuntimeError(f"Instagram create media gagal: {resp.json()}")

    log.info(f"Instagram media container dibuat: creation_id={creation_id}")

    # Step 2: Poll until FINISHED
    _poll_instagram_media(access_token, creation_id)

    # Step 3: Publish
    pub_resp = requests.post(
        f"{GRAPH_API_BASE}/{ig_user_id}/media_publish",
        params={"creation_id": creation_id, "access_token": access_token},
        timeout=30,
    )
    pub_resp.raise_for_status()
    media_id = pub_resp.json().get("id")
    log.info(f"Instagram Reels published: media_id={media_id}")
    return media_id


def _poll_instagram_media(access_token: str, creation_id: str, max_wait: int = 300):
    """Poll status container sampai FINISHED."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        resp = requests.get(
            f"{GRAPH_API_BASE}/{creation_id}",
            params={"fields": "status_code,status", "access_token": access_token},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        status_code = data.get("status_code", "")
        if status_code == "FINISHED":
            return
        elif status_code == "ERROR":
            raise RuntimeError(f"Instagram media processing error: {data.get('status')}")
        log.debug(f"Instagram status={status_code}, tunggu 10s...")
        time.sleep(10)
    raise TimeoutError("Instagram media processing timeout")


# ─────────────────────────────────────────────
# Facebook Reels
# ─────────────────────────────────────────────

def upload_facebook_reels(
    access_token: str,
    page_id: str,
    video_path: str,
    description: str = "",
    title: str = "",
) -> Optional[str]:
    """
    Upload video ke Facebook Reels via page.
    Returns facebook video_id atau None jika gagal.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video tidak ditemukan: {video_path}")

    file_size = os.path.getsize(video_path)
    log.info(f"Facebook Reels upload mulai untuk page_id={page_id}")

    # Step 1: Start upload session
    start_resp = requests.post(
        f"{GRAPH_API_BASE}/{page_id}/video_reels",
        params={
            "upload_phase": "start",
            "access_token": access_token,
        },
        timeout=30,
    )
    start_resp.raise_for_status()
    start_data = start_resp.json()
    video_id = start_data.get("video_id")
    upload_url = start_data.get("upload_url")

    if not video_id or not upload_url:
        raise RuntimeError(f"Facebook Reels start upload gagal: {start_data}")

    log.info(f"Facebook Reels session started: video_id={video_id}")

    # Step 2: Upload binary
    with open(video_path, "rb") as f:
        upload_resp = requests.post(
            upload_url,
            headers={
                "Authorization": f"OAuth {access_token}",
                "offset": "0",
                "file_size": str(file_size),
            },
            data=f,
            timeout=300,
        )
    upload_resp.raise_for_status()
    log.info("Facebook Reels binary uploaded")

    # Step 3: Finish (publish)
    finish_resp = requests.post(
        f"{GRAPH_API_BASE}/{page_id}/video_reels",
        params={
            "upload_phase": "finish",
            "video_id": video_id,
            "access_token": access_token,
            "video_state": "PUBLISHED",
            "description": description[:500],
            "title": title[:255],
        },
        timeout=30,
    )
    finish_resp.raise_for_status()
    log.info(f"Facebook Reels published: video_id={video_id}")
    return video_id


# ─────────────────────────────────────────────
# OAuth helpers
# ─────────────────────────────────────────────

def get_meta_oauth_url(redirect_uri: str, state: str = "", platform: str = "instagram") -> str:
    """Generate Meta OAuth2 authorization URL."""
    app_id = os.getenv("META_APP_ID", "")
    if not app_id:
        raise ValueError("META_APP_ID belum dikonfigurasi")

    if platform == "facebook":
        scopes = "pages_show_list,pages_read_engagement,pages_manage_posts,pages_manage_videos"
    else:
        scopes = "instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement"

    url = (
        f"https://www.facebook.com/v21.0/dialog/oauth"
        f"?client_id={app_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scopes}"
        f"&response_type=code"
        f"&state={state}"
    )
    return url


def exchange_meta_code(code: str, redirect_uri: str) -> dict:
    """Exchange authorization code untuk access_token."""
    app_id = os.getenv("META_APP_ID", "")
    app_secret = os.getenv("META_APP_SECRET", "")
    resp = requests.get(
        f"{GRAPH_API_BASE}/oauth/access_token",
        params={
            "client_id": app_id,
            "client_secret": app_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"Meta OAuth error: {data}")
    # Exchange ke long-lived token
    ll_resp = requests.get(
        f"{GRAPH_API_BASE}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": data["access_token"],
        },
        timeout=30,
    )
    ll_resp.raise_for_status()
    ll_data = ll_resp.json()
    return ll_data if "access_token" in ll_data else data


def get_instagram_account_id(access_token: str, page_id: str) -> Optional[str]:
    """Get Instagram Business account ID yang terhubung ke page."""
    resp = requests.get(
        f"{GRAPH_API_BASE}/{page_id}",
        params={"fields": "instagram_business_account", "access_token": access_token},
        timeout=30,
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    ig = data.get("instagram_business_account")
    return ig.get("id") if ig else None


def get_user_pages(access_token: str) -> list:
    """List semua pages yang bisa diakses user."""
    resp = requests.get(
        f"{GRAPH_API_BASE}/me/accounts",
        params={"access_token": access_token, "fields": "id,name,access_token"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])
