"""
CompetitorSpy — analisis channel YouTube competitor via yt-dlp + Gemini.
"""
import json
import subprocess
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class CompetitorSpy:
    def __init__(self, gemini_client=None):
        self.client = gemini_client

    def _fetch_channel_videos(self, channel_url: str, max_videos: int = 30) -> list:
        """Fetch video metadata from channel using yt-dlp (no download)."""
        try:
            cmd = [
                "yt-dlp",
                "--flat-playlist",
                "--dump-json",
                "--playlist-end", str(max_videos),
                "--no-warnings",
                channel_url,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            videos = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    try:
                        videos.append(json.loads(line))
                    except Exception:
                        pass
            return videos
        except Exception as e:
            logger.error(f"yt-dlp error: {e}")
            return []

    def _analyze_with_gemini(self, channel_url: str, videos: list) -> dict:
        """Use Gemini to analyze patterns and generate recommendations.
        
        self.client is a pre-configured `google.generativeai` module returned by
        get_genai_client(), so we use it directly without re-configuring.
        """
        if not self.client:
            return self._basic_analysis(channel_url, videos)

        video_summaries = []
        for v in videos[:30]:
            video_summaries.append({
                "title": v.get("title", ""),
                "duration": v.get("duration", 0),
                "view_count": v.get("view_count", 0),
                "upload_date": v.get("upload_date", ""),
            })

        prompt = f"""Analisis channel YouTube Shorts berikut berdasarkan data video mereka.

Channel URL: {channel_url}
Data video (30 terakhir):
{json.dumps(video_summaries, ensure_ascii=False, indent=2)}

Berikan analisis dalam format JSON:
{{
  "channel_name": "nama channel",
  "avg_views": <rata-rata views per video>,
  "posting_frequency": "<misal: 2x/hari>",
  "avg_duration_seconds": <rata-rata durasi>,
  "top_niches": ["niche1", "niche2"],
  "common_hooks": ["contoh hook 1", "contoh hook 2", "contoh hook 3"],
  "best_posting_hours": [7, 19],
  "content_style": "<deskripsi singkat gaya konten>",
  "recommendations": [
    "Rekomendasi 1 yang spesifik dan actionable",
    "Rekomendasi 2",
    "Rekomendasi 3",
    "Rekomendasi 4",
    "Rekomendasi 5"
  ],
  "strengths": ["kekuatan 1", "kekuatan 2"],
  "opportunities": ["peluang 1", "peluang 2"]
}}

Hanya balas dengan JSON, tidak ada teks lain."""

        try:
            from backend.core.gemini_pool import generate_with_retry
            tenant_id = getattr(self, "tenant_id", None)
            if tenant_id:
                response = generate_with_retry(tenant_id, "gemini-2.0-flash", prompt)
            else:
                # legacy: use pre-configured client
                model = self.client.GenerativeModel("gemini-2.0-flash")
                response = model.generate_content(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except Exception as e:
            logger.error(f"Gemini analysis error: {e}")
            return self._basic_analysis(channel_url, videos)

    def _basic_analysis(self, channel_url: str, videos: list) -> dict:
        """Fallback basic analysis without Gemini."""
        if not videos:
            return {
                "channel_name": channel_url.split("/")[-1],
                "avg_views": 0,
                "posting_frequency": "Tidak diketahui",
                "avg_duration_seconds": 0,
                "top_niches": [],
                "common_hooks": [],
                "best_posting_hours": [7, 12, 19],
                "content_style": "Tidak dapat dianalisis",
                "recommendations": ["Tidak cukup data untuk analisis. Coba channel yang lebih aktif."],
                "strengths": [],
                "opportunities": [],
            }

        total_views = sum(v.get("view_count", 0) or 0 for v in videos)
        avg_views = total_views // len(videos) if videos else 0
        avg_duration = sum(v.get("duration", 0) or 0 for v in videos) // len(videos) if videos else 0

        return {
            "channel_name": videos[0].get("uploader", channel_url.split("/")[-1]) if videos else "",
            "avg_views": avg_views,
            "posting_frequency": f"{len(videos)}/bulan (estimasi)",
            "avg_duration_seconds": avg_duration,
            "top_niches": ["Tidak terdeteksi — tambahkan Gemini key untuk analisis lengkap"],
            "common_hooks": [],
            "best_posting_hours": [7, 12, 19],
            "content_style": "Analisis dasar — tambahkan Gemini key untuk detail",
            "recommendations": [
                f"Channel ini rata-rata mendapat {avg_views:,} views per video",
                "Tambahkan Gemini API key untuk rekomendasi yang lebih personal dan detail",
            ],
            "strengths": [],
            "opportunities": [],
        }

    def analyze(self, channel_url: str) -> dict:
        """Full competitor analysis pipeline."""
        logger.info(f"Starting competitor spy: {channel_url}")
        videos = self._fetch_channel_videos(channel_url)
        result = self._analyze_with_gemini(channel_url, videos)
        result["channel_url"] = channel_url
        result["videos_analyzed"] = len(videos)
        return result
