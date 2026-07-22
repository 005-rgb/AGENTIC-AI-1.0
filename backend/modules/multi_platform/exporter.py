"""
MultiPlatformExporter — export & upload video ke berbagai platform.
Phase 3: TikTok & Meta APIs diimplementasi penuh.
Saat ini: YouTube sudah live, TikTok/IG/FB returning stub (API keys belum dikonfigurasi).
"""
import os
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

PLATFORM_SPECS = {
    "youtube": {
        "resolution": "1080x1920",
        "max_duration": 60,
        "aspect": "9:16",
        "format": "mp4",
        "vcodec": "libx264",
        "acodec": "aac",
    },
    "tiktok": {
        "resolution": "1080x1920",
        "max_duration": 60,
        "aspect": "9:16",
        "format": "mp4",
        "vcodec": "libx264",
        "acodec": "aac",
    },
    "instagram": {
        "resolution": "1080x1920",
        "max_duration": 90,
        "aspect": "9:16",
        "format": "mp4",
        "vcodec": "libx264",
        "acodec": "aac",
    },
    "facebook": {
        "resolution": "1080x1920",
        "max_duration": 60,
        "aspect": "9:16",
        "format": "mp4",
        "vcodec": "libx264",
        "acodec": "aac",
    },
}


class MultiPlatformExporter:
    def __init__(self, tenant_id: str, output_base: str):
        self.tenant_id = tenant_id
        self.output_base = output_base

    def export_for_platform(self, source_path: str, platform: str) -> Optional[str]:
        """Re-encode video for specific platform spec."""
        if platform not in PLATFORM_SPECS:
            logger.warning(f"Unknown platform: {platform}")
            return None

        spec = PLATFORM_SPECS[platform]
        platform_dir = os.path.join(self.output_base, "platforms", platform)
        os.makedirs(platform_dir, exist_ok=True)

        filename = os.path.basename(source_path)
        output_path = os.path.join(platform_dir, filename)

        # If source is already correct spec, just copy
        w, h = spec["resolution"].split("x")
        cmd = [
            "ffmpeg", "-y",
            "-i", source_path,
            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
            "-t", str(spec["max_duration"]),
            "-c:v", spec["vcodec"],
            "-c:a", spec["acodec"],
            "-b:v", "4M",
            "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                logger.info(f"Exported {platform}: {output_path}")
                return output_path
            else:
                logger.error(f"FFmpeg error for {platform}: {result.stderr[-500:]}")
                return None
        except Exception as e:
            logger.error(f"Export error for {platform}: {e}")
            return None

    def export_all(self, source_path: str, platforms: list) -> dict:
        """Export video for all requested platforms."""
        results = {}
        for platform in platforms:
            if platform == "youtube":
                # YouTube uses the main output directly
                results["youtube"] = source_path
            else:
                path = self.export_for_platform(source_path, platform)
                results[platform] = path
        return results

    def upload_tiktok(self, video_path: str, title: str, description: str = "") -> Optional[str]:
        """Upload to TikTok via Content Posting API — requires TIKTOK_CLIENT_KEY."""
        tiktok_key = os.getenv("TIKTOK_CLIENT_KEY")
        if not tiktok_key:
            logger.warning("TIKTOK_CLIENT_KEY not configured — skipping TikTok upload")
            return None

        # TODO: Implement TikTok Content Posting API (Phase 3)
        # Requires OAuth2 flow per-user + file upload
        logger.info("TikTok upload: API integration pending (Phase 3)")
        return None

    def upload_instagram_reels(self, video_path: str, caption: str = "") -> Optional[str]:
        """Upload Instagram Reels via Meta Graph API — requires META_APP_ID."""
        meta_app_id = os.getenv("META_APP_ID")
        if not meta_app_id:
            logger.warning("META_APP_ID not configured — skipping Instagram upload")
            return None

        # TODO: Implement Meta Graph API Reels upload (Phase 3)
        logger.info("Instagram Reels upload: API integration pending (Phase 3)")
        return None

    def upload_facebook_reels(self, video_path: str, caption: str = "") -> Optional[str]:
        """Upload Facebook Reels via Meta Graph API — requires META_APP_ID."""
        meta_app_id = os.getenv("META_APP_ID")
        if not meta_app_id:
            logger.warning("META_APP_ID not configured — skipping Facebook upload")
            return None

        # TODO: Implement Meta Graph API Facebook Reels upload (Phase 3)
        logger.info("Facebook Reels upload: API integration pending (Phase 3)")
        return None
