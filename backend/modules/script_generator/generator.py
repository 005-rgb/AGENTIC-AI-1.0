"""
Script Generator — buat skrip Shorts berbasis niche menggunakan Gemini.
"""
import json
import re
from datetime import date

from backend.core.gemini_pool import get_genai_client


NICHE_CONFIG = {
    "motivasi":   {"model": "gemini-2.0-flash", "tone": "inspiratif dan membakar semangat", "points": 3},
    "edukasi":    {"model": "gemini-2.0-flash", "tone": "informatif dan mudah dipahami",    "points": 4},
    "humor":      {"model": "gemini-1.5-flash", "tone": "santai, lucu, dan menghibur",      "points": 3},
    "fakta":      {"model": "gemini-2.0-flash", "tone": "mengejutkan dan penasaran",        "points": 4},
    "tutorial":   {"model": "gemini-2.0-flash", "tone": "jelas step-by-step",              "points": 5},
    "lifestyle":  {"model": "gemini-1.5-flash", "tone": "casual dan relatable",            "points": 3},
    "finance":    {"model": "gemini-2.0-flash", "tone": "serius tapi simpel",              "points": 3},
    "kesehatan":  {"model": "gemini-2.0-flash", "tone": "informatif dan peduli",           "points": 4},
    "teknologi":  {"model": "gemini-2.0-flash", "tone": "exciting dan futuristik",         "points": 3},
    "lainnya":    {"model": "gemini-1.5-flash", "tone": "menarik dan engaging",            "points": 3},
}

PROMPT_TEMPLATE = """
Kamu adalah scriptwriter ahli YouTube Shorts niche {niche}.
Hari ini: {today}.
Buat skrip video berdurasi {duration} detik dengan gaya: {tone}

Topik: {topic}

Struktur WAJIB:
1. HOOK (0-3 detik): kalimat pembuka yang memancing rasa ingin tahu atau emosi kuat, maksimal 15 kata
2. ISI ({points} poin): setiap poin singkat, padat, dan impactful
3. CTA (akhir): ajak subscribe/like/follow, maks 10 kata

Output HARUS berupa JSON valid dengan format persis ini:
{{
  "hook": "...",
  "body": ["poin 1", "poin 2", "poin 3"],
  "cta": "...",
  "full_script": "...",
  "title": "judul menarik maks 80 karakter",
  "title_variant_b": "judul alternatif maks 80 karakter",
  "description": "deskripsi 150 karakter dengan hashtag",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "hook_options": ["hook alternatif 1", "hook alternatif 2", "hook alternatif 3"]
}}

Pastikan full_script adalah gabungan hook + body + cta dalam paragraf yang natural untuk dibacakan.
Semua teks dalam Bahasa Indonesia yang natural.
""".strip()


class ScriptGenerator:
    def generate(
        self,
        tenant_id: str,
        niche: str,
        topic: str,
        duration_seconds: int = 45,
    ) -> dict:
        cfg = NICHE_CONFIG.get(niche, NICHE_CONFIG["lainnya"])
        prompt = PROMPT_TEMPLATE.format(
            niche=niche,
            today=date.today().strftime("%d %B %Y"),
            duration=duration_seconds,
            tone=cfg["tone"],
            topic=topic,
            points=cfg["points"],
        )

        genai = get_genai_client(tenant_id)
        model = genai.GenerativeModel(cfg["model"])
        response = model.generate_content(prompt)
        raw = response.text.strip()

        return self._parse(raw, topic, niche)

    def _parse(self, raw: str, topic: str, niche: str) -> dict:
        # Extract JSON block if wrapped in markdown code fence
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if match:
            raw = match.group(1)
        else:
            # Find first { to last }
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1 and end > start:
                raw = raw[start:end]

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: return minimal structure
            data = {
                "hook": topic,
                "body": [topic],
                "cta": "Follow untuk konten menarik lainnya!",
                "full_script": topic,
                "title": topic[:80],
                "title_variant_b": f"{topic} - Kamu Harus Tahu!",
                "description": f"{topic} #shorts #{niche}",
                "tags": [niche, "shorts", "ytshorts"],
                "hook_options": [topic],
            }

        # Ensure required fields
        data.setdefault("hook_options", [data.get("hook", topic)])
        data.setdefault("title_variant_b", data.get("title", topic))
        data.setdefault("tags", [niche, "shorts"])

        return data
