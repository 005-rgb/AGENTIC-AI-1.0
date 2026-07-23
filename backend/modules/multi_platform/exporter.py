"""
MultiPlatformExporter — re-encode + upload video ke berbagai platform.
Phase 3: TikTok & Meta APIs diimplementasi penuh.
"""
import logging
import os
import subprocess
from typing import Optional

log = logging.getLogger(__name__)

PLATFORM_SPECS = {
    "youtube": {
        "resolution": "1080x1920",
        "max_duration": 60,
        "vcodec": "libx264",
        "acodec": "aac",
        "bitrate_v": "4M",
        "bitrate_a": "192k",
    },
    "tiktok": {
        "resolution": "1080x1920",
        "max_duration": 60,
        "vcodec": "libx264",
        "acodec": "aac",
        "bitrate_v": "4M",
        "bitrate_a": "192k",
    },
    "instagram": {
        "resolution": "1080x1920",
        "max_duration": 90,
        "vcodec": "libx264",
        "acodec": "aac",
        "bitrate_v": "4M",
        "bitrate_a": "192k",
    },
    "facebook": {
        "resolution": "1080x1920",
        "max_duration": 60,
        "vcodec": "libx264",
        "acodec": "aac",
        "bitrate_v": "4M",
        "bitrate_a": "192k",
    },
}


class MultiPlatformExporter:
    def __init__(self, tenant_id: str, output_base: str):
        self.tenant_id = tenant_id
        self.output_base = output_base

    def export_for_platform(self, source_path: str, platform: str) -> Optional[str]:
        """Re-encode video sesuai spec platform."""
        if platform not in PLATFORM_SPECS:
            log.warning(f"Unknown platform: {platform}")
            return None

        spec = PLATFORM_SPECS[platform]
        platform_dir = os.path.join(self.output_base, "platforms", platform)
        os.makedirs(platform_dir, exist_ok=True)

        filename = os.path.basename(source_path)
        output_path = os.path.join(platform_dir, filename)

        w, h = spec["resolution"].split("x")
        cmd = [
            "ffmpeg", "-y",
            "-i", source_path,
            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                   f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black",
            "-t", str(spec["max_duration"]),
            "-c:v", spec["vcodec"],
            "-c:a", spec["acodec"],
            "-b:v", spec["bitrate_v"],
            "-b:a", spec["bitrate_a"],
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                log.info(f"Exported {platform}: {output_path}")
                return output_path
            else:
                log.error(f"FFmpeg error for {platform}: {result.stderr[-500:]}")
                return None
        except Exception as e:
            log.error(f"Export error for {platform}: {e}")
            return None

    def export_all(self, source_path: str, platforms: list) -> dict:
        """Export + return path per platform."""
        results = {}
        for platform in platforms:
            if platform == "youtube":
                results["youtube"] = source_path
            else:
                path = self.export_for_platform(source_path, platform)
                results[platform] = path
        return results

    def upload_tiktok(
        self,
        video_path: str,
        title: str,
        description: str = "",
        access_token: str = "",
    ) -> Optional[str]:
        """Upload ke TikTok via Content Posting API v2."""
        if not access_token:
            access_token = os.getenv("TIKTOK_ACCESS_TOKEN", "")
        if not access_token:
            log.warning("TikTok access_token tidak tersedia — skip TikTok upload")
            return None

        try:
            from backend.modules.tiktok.uploader import upload_video_to_tiktok
            return upload_video_to_tiktok(access_token, video_path, title, description)
        except Exception as e:
            log.error(f"TikTok upload error: {e}")
            return None

    def upload_instagram_reels(
        self,
        video_path: str,
        caption: str = "",
        access_token: str = "",
        ig_user_id: str = "",
        public_video_url: Optional[str] = None,
    ) -> Optional[str]:
        """Upload Instagram Reels via Meta Graph API."""
        if not access_token or not ig_user_id:
            log.warning("Meta access_token/ig_user_id tidak tersedia — skip Instagram upload")
            return None

        try:
            from backend.modules.meta.uploader import upload_instagram_reels
            return upload_instagram_reels(
                access_token, ig_user_id, video_path, caption, public_video_url
            )
        except Exception as e:
            log.error(f"Instagram upload error: {e}")
            return None

    def upload_facebook_reels(
        self,
        video_path: str,
        description: str = "",
        title: str = "",
        access_token: str = "",
        page_id: str = "",
    ) -> Optional[str]:
        """Upload Facebook Reels via Meta Graph API."""
        if not access_token or not page_id:
            log.warning("Meta access_token/page_id tidak tersedia — skip Facebook upload")
            return None

        try:
            from backend.modules.meta.uploader import upload_facebook_reels
            return upload_facebook_reels(access_token, page_id, video_path, description, title)
        except Exception as e:
            log.error(f"Facebook upload error: {e}")
            return None
