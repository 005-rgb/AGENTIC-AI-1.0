"""
Trend Scout — generate topik trending per niche menggunakan Gemini.
Cache hasil 6 jam di memory untuk hemat kuota.
"""
import json
import re
import time
from datetime import date
from typing import Optional

from backend.core.gemini_pool import get_genai_client

_cache: dict[str, tuple[float, list]] = {}   # key → (timestamp, data)
CACHE_TTL = 6 * 3600  # 6 jam


PROMPT = """
Hari ini {today}. Kamu adalah analis konten YouTube Shorts Indonesia.

Buat daftar {limit} topik trending untuk niche "{niche}" yang berpotensi viral di Indonesia saat ini.

Untuk setiap topik berikan:
- topic: judul topik singkat (maks 60 karakter)
- score: skor viralitas 0-100 (100 = sangat viral)
- suggested_hook: kalimat pembuka yang kuat (maks 15 kata)
- why_trending: alasan 1 kalimat kenapa ini trending sekarang

Output HARUS berupa JSON array valid:
[
  {{"topic": "...", "score": 95, "suggested_hook": "...", "why_trending": "..."}},
  ...
]
Urutkan dari skor tertinggi ke terendah.
""".strip()


class TrendScout:
    def get_trends(self, tenant_id: str, niche: str, limit: int = 10) -> list:
        cache_key = f"{niche}:{limit}"
        now = time.time()

        if cache_key in _cache:
            ts, data = _cache[cache_key]
            if now - ts < CACHE_TTL:
                return data

        prompt = PROMPT.format(
            today=date.today().strftime("%d %B %Y"),
            niche=niche,
            limit=limit,
        )

        from backend.core.gemini_pool import generate_with_retry
        response = generate_with_retry(tenant_id, "gemini-2.0-flash", prompt)
        raw = response.text.strip()

        data = self._parse(raw)
        _cache[cache_key] = (now, data)
        return data

    def _parse(self, raw: str) -> list:
        match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
        if match:
            raw = match.group(1)
        else:
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start != -1 and end > start:
                raw = raw[start:end]

        try:
            return json.loads(raw)
        except Exception:
            return []
