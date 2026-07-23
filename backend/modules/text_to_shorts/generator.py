"""
Text-to-Shorts Generator — buat video slide dari teks menggunakan Pillow + gTTS.
Tidak butuh footage video sama sekali.
"""
import os
import json
import re
import subprocess
from datetime import date
from typing import Optional

from backend.core.gemini_pool import get_genai_client
from backend.models.models import VideoJob


SLIDE_PROMPT = """
Hari ini {today}. Buat storyboard YouTube Shorts untuk topik: "{topic}" (niche: {niche}).

Buat 6-8 slide dengan struktur:
- Slide 1: type="hook" — judul besar yang memancing klik
- Slide 2-N: type="content" — poin-poin singkat dan impactful
- Slide terakhir: type="cta" — ajak subscribe/follow

Output JSON:
{{
  "slides": [
    {{"type": "hook", "heading": "...", "body": "..."}},
    {{"type": "content", "heading": "...", "body": "..."}},
    {{"type": "cta", "heading": "...", "body": ""}}
  ],
  "background_style": "dark_gradient",
  "accent_color": "#FF6B6B",
  "narration": ["narasi slide 1", "narasi slide 2", ...]
}}

background_style pilihan: dark_gradient | blue_gradient | green_gradient | purple_gradient | red_gradient
Teks dalam Bahasa Indonesia yang natural dan energik.
""".strip()

GRADIENT_STYLES = {
    "dark_gradient":   [(30, 30, 30), (60, 60, 60)],
    "blue_gradient":   [(10, 30, 80), (20, 80, 180)],
    "green_gradient":  [(10, 60, 30), (20, 140, 70)],
    "purple_gradient": [(50, 10, 80), (120, 30, 160)],
    "red_gradient":    [(100, 10, 10), (200, 40, 40)],
}


class TextToShortsGenerator:
    def generate(self, job: VideoJob) -> str:
        """Generate a video from text and return the path to the output file."""
        tid = job.tenant_id
        jid = job.id
        topic = job.hook_text or "Konten Menarik"
        niche = job.niche or "lainnya"

        temp_dir = f"storage/{tid}/temp/{jid}_slides"
        os.makedirs(temp_dir, exist_ok=True)

        # Step 1: Generate slide structure from Gemini
        storyboard = self._generate_storyboard(job.tenant_id, topic, niche)
        slides = storyboard.get("slides", [])
        narrations = storyboard.get("narration", [])
        bg_style = storyboard.get("background_style", "dark_gradient")
        accent = storyboard.get("accent_color", "#FF6B6B")

        # Step 2: Create slide images
        slide_paths = []
        for i, slide in enumerate(slides):
            img_path = f"{temp_dir}/slide_{i:02d}.png"
            self._create_slide_image(slide, img_path, bg_style, accent)
            slide_paths.append(img_path)

        # Step 3: Generate TTS audio per slide
        audio_paths = []
        for i, narration in enumerate(narrations[:len(slide_paths)]):
            audio_path = f"{temp_dir}/audio_{i:02d}.mp3"
            self._generate_tts(narration, audio_path)
            audio_paths.append(audio_path)

        # Pad audio list if shorter than slides
        while len(audio_paths) < len(slide_paths):
            audio_paths.append(None)

        # Step 4: Combine slide + audio into video clips, then concat
        out_path = f"storage/{tid}/downloads/{jid}.mp4"
        os.makedirs(f"storage/{tid}/downloads", exist_ok=True)
        self._build_video(slide_paths, audio_paths, out_path)

        # Save script to job
        if slides:
            full_script = " ".join(
                f"{s.get('heading', '')} {s.get('body', '')}" for s in slides
            ).strip()
            job.script = full_script
            from backend.core.database import SessionLocal
            db = SessionLocal()
            try:
                from backend.models.models import VideoJob as VJ
                j = db.query(VJ).filter(VJ.id == jid).first()
                if j:
                    j.script = full_script
                    db.commit()
            finally:
                db.close()

        return out_path

    def _generate_storyboard(self, tenant_id: str, topic: str, niche: str) -> dict:
        prompt = SLIDE_PROMPT.format(
            today=date.today().strftime("%d %B %Y"),
            topic=topic,
            niche=niche,
        )
        from backend.core.gemini_pool import generate_with_retry
        response = generate_with_retry(tenant_id, "gemini-2.0-flash", prompt)
        raw = response.text.strip()

        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if match:
            raw = match.group(1)
        else:
            start, end = raw.find("{"), raw.rfind("}") + 1
            if start != -1:
                raw = raw[start:end]

        try:
            return json.loads(raw)
        except Exception:
            return {
                "slides": [
                    {"type": "hook", "heading": topic, "body": ""},
                    {"type": "cta", "heading": "Follow untuk lebih banyak!", "body": ""},
                ],
                "background_style": "dark_gradient",
                "accent_color": "#FF6B6B",
                "narration": [topic, "Follow untuk lebih banyak konten menarik!"],
            }

    def _create_slide_image(self, slide: dict, out_path: str, bg_style: str, accent: str):
        """Create a 1080x1920 slide image using Pillow — visually rich layout."""
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            self._ffmpeg_slide(slide, out_path, bg_style)
            return

        W, H = 1080, 1920
        colors = GRADIENT_STYLES.get(bg_style, GRADIENT_STYLES["dark_gradient"])
        img = Image.new("RGB", (W, H))
        draw = ImageDraw.Draw(img)

        # ── Gradient background (diagonal feel via two passes) ──────────
        for y in range(H):
            t = y / H
            r = int(colors[0][0] + (colors[1][0] - colors[0][0]) * t)
            g = int(colors[0][1] + (colors[1][1] - colors[0][1]) * t)
            b = int(colors[0][2] + (colors[1][2] - colors[0][2]) * t)
            draw.line([(0, y), (W, y)], fill=(r, g, b))

        # ── Accent color ─────────────────────────────────────────────────
        try:
            ar, ag, ab = int(accent[1:3], 16), int(accent[3:5], 16), int(accent[5:7], 16)
        except Exception:
            ar, ag, ab = 255, 107, 107
        ac = (ar, ag, ab)

        # ── Decorative circles (background detail) ───────────────────────
        draw.ellipse([750, -100, 1180, 330], fill=(ar, ag, ab, 30) if hasattr(draw, '_image') else tuple([min(c+30, 255) for c in colors[1]]))
        draw.ellipse([-100, 1600, 400, 2100], fill=tuple([max(c-10, 0) for c in colors[0]]))

        # ── Top decorative bar ────────────────────────────────────────────
        draw.rectangle([0, 0, W, 12], fill=ac)

        # ── Fonts ────────────────────────────────────────────────────────
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ]
        font_body_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ]

        def load_font(paths, size):
            for p in paths:
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    continue
            return ImageFont.load_default()

        stype = slide.get("type", "content")
        heading = slide.get("heading", "")
        body = slide.get("body", "")

        font_badge = load_font(font_paths, 40)
        font_h     = load_font(font_paths, 80 if stype == "hook" else 68)
        font_b     = load_font(font_body_paths, 50)
        font_num   = load_font(font_paths, 200)

        # ── Badge (slide type) ────────────────────────────────────────────
        badge_labels = {"hook": "▶ HOOK", "cta": "★ FOLLOW", "content": "●"}
        badge_text = badge_labels.get(stype, "●")
        bx1, by1, bx2, by2 = 60, 60, 60 + len(badge_text) * 22 + 40, 120
        draw.rounded_rectangle([bx1, by1, bx2, by2], radius=30, fill=ac)
        draw.text((bx1 + 20, by1 + 10), badge_text, fill=(255, 255, 255), font=font_badge)

        # ── Large decorative number for content slides ────────────────────
        if stype == "content" and body:
            draw.text((W - 220, H // 2 - 160), "»", fill=(*ac, 60) if False else ac, font=font_num)

        # ── Accent horizontal bar ─────────────────────────────────────────
        bar_y = H // 2 - 20
        draw.rectangle([60, bar_y, W - 60, bar_y + 8], fill=ac)

        # ── Heading text ─────────────────────────────────────────────────
        self._draw_text_wrapped(draw, heading, font_h, W, bar_y + 40, (255, 255, 255), max_width=W - 120)

        # ── Body text ────────────────────────────────────────────────────
        if body:
            body_y = bar_y + 180 if stype != "hook" else bar_y + 220
            self._draw_text_wrapped(draw, body, font_b, W, body_y, (210, 215, 230), max_width=W - 140)

        # ── CTA slide extra: subscribe prompt ────────────────────────────
        if stype == "cta":
            draw.rounded_rectangle([160, H - 320, W - 160, H - 220], radius=50, fill=ac)
            cta_font = load_font(font_paths, 52)
            draw.text((W // 2, H - 283), "SUBSCRIBE SEKARANG !", fill=(255, 255, 255), font=cta_font, anchor="mm")

        # ── Bottom brand strip ────────────────────────────────────────────
        draw.rectangle([0, H - 80, W, H], fill=tuple([max(c - 20, 0) for c in colors[0]]))
        brand_font = load_font(font_body_paths, 34)
        draw.text((W // 2, H - 44), "Shorts Factory  ✦  AI Generated", fill=(180, 180, 180), font=brand_font, anchor="mm")

        img.save(out_path, "PNG")

    def _draw_text_wrapped(self, draw, text, font, canvas_w, y_start, color, max_width):
        words = text.split()
        lines, line = [], ""
        for word in words:
            test = f"{line} {word}".strip()
            try:
                bbox = draw.textbbox((0, 0), test, font=font)
                w = bbox[2] - bbox[0]
            except Exception:
                w = len(test) * 20
            if w > max_width and line:
                lines.append(line)
                line = word
            else:
                line = test
        if line:
            lines.append(line)

        y = y_start
        for ln in lines:
            try:
                bbox = draw.textbbox((0, 0), ln, font=font)
                tw = bbox[2] - bbox[0]
            except Exception:
                tw = len(ln) * 20
            x = (canvas_w - tw) // 2
            draw.text((x, y), ln, fill=color, font=font)
            try:
                lh = bbox[3] - bbox[1] + 12
            except Exception:
                lh = 60
            y += lh

    def _ffmpeg_slide(self, slide: dict, out_path: str, bg_style: str):
        """Fallback: create plain colored image using FFmpeg."""
        colors = GRADIENT_STYLES.get(bg_style, [(30, 30, 30), (60, 60, 60)])
        r, g, b = colors[0]
        text = slide.get("heading", "Shorts Factory")[:60]
        safe = text.replace("'", "").replace(":", " ")
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=#{r:02x}{g:02x}{b:02x}:size=1080x1920:rate=1",
            "-frames:v", "1",
            "-vf", f"drawtext=text='{safe}':fontcolor=white:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2",
            out_path,
        ], capture_output=True)

    def _generate_tts(self, text: str, out_path: str):
        """Generate TTS audio using edge-tts (Microsoft, natural voice).
        Falls back to gTTS then silent audio if both fail."""
        # edge-tts produces .mp3 natively; out_path already .mp3
        try:
            import asyncio
            import edge_tts

            async def _run_edge():
                communicate = edge_tts.Communicate(text, voice="id-ID-GadisNeural")
                await communicate.save(out_path)

            asyncio.run(_run_edge())
            if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
                return
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("edge-tts failed (%s), falling back to gTTS", e)

        # Fallback 1: gTTS
        try:
            from gtts import gTTS
            tts = gTTS(text=text, lang="id", slow=False)
            tts.save(out_path)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
                return
        except Exception:
            pass

        # Fallback 2: silent audio
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=stereo",
            "-t", "3", out_path,
        ], capture_output=True)

    def _build_video(self, slide_paths: list, audio_paths: list, out_path: str):
        """Combine slides + audio into final video."""
        clips = []
        temp_clips = []

        for i, (img, aud) in enumerate(zip(slide_paths, audio_paths)):
            clip_path = img.replace(".png", "_clip.mp4")
            temp_clips.append(clip_path)

            # Get audio duration
            duration = 3.0
            if aud and os.path.exists(aud):
                r = subprocess.run(
                    ["ffprobe", "-v", "quiet", "-print_format", "json",
                     "-show_format", aud],
                    capture_output=True, text=True,
                )
                try:
                    import json
                    d = json.loads(r.stdout)
                    duration = float(d.get("format", {}).get("duration", 3))
                    duration = max(2.0, min(duration + 0.5, 8.0))
                except Exception:
                    pass

            if aud and os.path.exists(aud):
                subprocess.run([
                    "ffmpeg", "-y",
                    "-loop", "1", "-i", img,
                    "-i", aud,
                    "-c:v", "libx264", "-c:a", "aac",
                    "-b:a", "128k",
                    "-t", str(duration),
                    "-pix_fmt", "yuv420p",
                    "-shortest",
                    clip_path,
                ], capture_output=True)
            else:
                subprocess.run([
                    "ffmpeg", "-y",
                    "-loop", "1", "-i", img,
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-c:v", "libx264", "-c:a", "aac",
                    "-t", str(duration),
                    "-pix_fmt", "yuv420p",
                    clip_path,
                ], capture_output=True)

            clips.append(clip_path)

        # Concat all clips
        if not clips:
            raise RuntimeError("Tidak ada slide yang berhasil dibuat")

        concat_list = out_path.replace(".mp4", "_list.txt")
        with open(concat_list, "w") as f:
            for c in clips:
                f.write(f"file '{os.path.abspath(c)}'\n")

        subprocess.run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c", "copy",
            out_path,
        ], check=True, capture_output=True)

        # Cleanup
        for c in temp_clips:
            if os.path.exists(c):
                os.remove(c)
        if os.path.exists(concat_list):
            os.remove(concat_list)
