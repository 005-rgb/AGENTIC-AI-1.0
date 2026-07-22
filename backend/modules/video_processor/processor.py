"""
Video Processor — crop ke 9:16, subtitle, hook overlay, background music.
"""
import os
import subprocess
import shutil
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session
from backend.models.models import VideoJob


FFMPEG = os.getenv("FFMPEG_PATH", "ffmpeg")
FFPROBE = os.getenv("FFPROBE_PATH", "ffprobe")


def _run(cmd: list[str]):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {result.stderr[-500:]}")
    return result


def _set_progress(db: Session, job: VideoJob, progress: float, status: str = "processing"):
    job.progress = progress
    job.status = status
    job.updated_at = datetime.utcnow()
    db.commit()


class VideoProcessor:
    def __init__(self, db: Session):
        self.db = db

    def run(self, job: VideoJob):
        db = self.db
        tid = job.tenant_id
        jid = job.id

        try:
            _set_progress(db, job, 0, "processing")

            # ── Step 1: Resolve source file ──────────────────────────────
            src = self._resolve_source(job)
            _set_progress(db, job, 10)

            # ── Step 2: Probe ────────────────────────────────────────────
            info = self._probe(src)
            duration = float(info.get("duration", 60))
            _set_progress(db, job, 15)

            # ── Step 3: Generate script / title if missing ───────────────
            if not job.script and job.niche:
                self._generate_script(job, duration)
            _set_progress(db, job, 30)

            # ── Step 4: Crop to 9:16 ────────────────────────────────────
            temp_dir = f"storage/{tid}/temp"
            out_dir  = f"storage/{tid}/output"
            os.makedirs(temp_dir, exist_ok=True)
            os.makedirs(out_dir, exist_ok=True)

            cropped = f"{temp_dir}/{jid}_cropped.mp4"
            self._crop(src, cropped)
            _set_progress(db, job, 50)

            # ── Step 5: Hook text overlay ────────────────────────────────
            hooked = f"{temp_dir}/{jid}_hooked.mp4"
            if job.hook_text:
                self._add_hook(cropped, hooked, job.hook_text)
            else:
                shutil.copy(cropped, hooked)
            _set_progress(db, job, 65)

            # ── Step 6: Subtitles ────────────────────────────────────────
            subbed = f"{temp_dir}/{jid}_subbed.mp4"
            if job.add_subtitles and job.script:
                srt_path = self._write_srt(job, temp_dir, duration)
                self._burn_subtitles(hooked, subbed, srt_path)
            else:
                shutil.copy(hooked, subbed)
            _set_progress(db, job, 80)

            # ── Step 7: Background music ─────────────────────────────────
            final = f"{temp_dir}/{jid}_final.mp4"
            if job.add_music:
                music = self._pick_music()
                if music:
                    self._mix_music(subbed, music, final)
                else:
                    shutil.copy(subbed, final)
            else:
                shutil.copy(subbed, final)
            _set_progress(db, job, 90)

            # ── Step 8: Move to output ───────────────────────────────────
            output_name = f"{jid}.mp4"
            output_path = f"{out_dir}/{output_name}"
            shutil.move(final, output_path)

            # ── Step 9: Thumbnail ────────────────────────────────────────
            thumb_dir = f"storage/{tid}/thumbnails"
            os.makedirs(thumb_dir, exist_ok=True)
            thumb_path = f"{thumb_dir}/{jid}.jpg"
            self._extract_thumbnail(output_path, thumb_path)
            _set_progress(db, job, 95)

            # ── Cleanup temp ─────────────────────────────────────────────
            for f in [cropped, hooked, subbed]:
                if os.path.exists(f):
                    os.remove(f)

            # ── Done ─────────────────────────────────────────────────────
            job.output_filename = output_name
            job.thumbnail_filename = f"{jid}.jpg"
            if job.scheduled_at:
                _set_progress(db, job, 100, "scheduled")
            else:
                _set_progress(db, job, 100, "done")

        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.updated_at = datetime.utcnow()
            db.commit()
            raise

    # ── helpers ───────────────────────────────────────────────────────────

    def _resolve_source(self, job: VideoJob) -> str:
        tid = job.tenant_id
        jid = job.id

        if job.source_type == "upload":
            path = f"storage/{tid}/uploads/{job.source_filename}"
            if not os.path.exists(path):
                raise FileNotFoundError(f"Upload file tidak ditemukan: {path}")
            return path

        if job.source_type == "url":
            dl_dir = f"storage/{tid}/downloads"
            os.makedirs(dl_dir, exist_ok=True)
            out_tmpl = f"{dl_dir}/{jid}.%(ext)s"
            subprocess.run(
                ["yt-dlp", "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                 "--merge-output-format", "mp4",
                 "-o", out_tmpl, job.source_url],
                check=True, capture_output=True,
            )
            # Find downloaded file
            for f in os.listdir(dl_dir):
                if f.startswith(jid):
                    return f"{dl_dir}/{f}"
            raise FileNotFoundError("Download gagal: file tidak ditemukan")

        if job.source_type in ("ai_generate", "text_to_shorts"):
            from backend.modules.text_to_shorts.generator import TextToShortsGenerator
            gen = TextToShortsGenerator()
            path = gen.generate(job)
            return path

        raise ValueError(f"source_type tidak dikenal: {job.source_type}")

    def _probe(self, path: str) -> dict:
        r = subprocess.run(
            [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_format", path],
            capture_output=True, text=True,
        )
        import json
        data = json.loads(r.stdout or "{}")
        return data.get("format", {})

    def _generate_script(self, job: VideoJob, duration: float):
        try:
            from backend.modules.script_generator.generator import ScriptGenerator
            gen = ScriptGenerator()
            result = gen.generate(
                tenant_id=job.tenant_id,
                niche=job.niche or "lainnya",
                topic=job.hook_text or "Konten menarik",
                duration_seconds=int(min(duration, 60)),
            )
            job.script = result.get("full_script", "")
            if not job.title:
                job.title = result.get("title", "")
            if not job.description:
                job.description = result.get("description", "")
            if not job.tags or job.tags == []:
                job.tags = result.get("tags", [])
            self.db.commit()
        except Exception:
            pass  # Script generation optional

    def _crop(self, src: str, out: str):
        _run([
            FFMPEG, "-y", "-i", src,
            "-vf", "crop=ih*9/16:ih,scale=1080:1920",
            "-c:a", "copy",
            "-movflags", "+faststart",
            out,
        ])

    def _add_hook(self, src: str, out: str, hook_text: str):
        safe_text = hook_text.replace("'", "\\'").replace(":", "\\:")
        _run([
            FFMPEG, "-y", "-i", src,
            "-vf",
            f"drawtext=text='{safe_text}':fontsize=64:fontcolor=white"
            f":x=(w-text_w)/2:y=h*0.15:enable='between(t,0,3)'"
            f":borderw=4:bordercolor=black:font=sans",
            "-c:a", "copy",
            out,
        ])

    def _write_srt(self, job: VideoJob, temp_dir: str, duration: float) -> str:
        """Generate simple SRT from script text."""
        srt_path = f"{temp_dir}/{job.id}.srt"
        lines = [l.strip() for l in (job.script or "").split("\n") if l.strip()]
        if not lines:
            lines = [""]

        chunk_dur = min(duration / max(len(lines), 1), 5.0)

        def fmt(t: float) -> str:
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            s = int(t % 60)
            ms = int((t - int(t)) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        with open(srt_path, "w", encoding="utf-8") as f:
            for i, line in enumerate(lines):
                start = i * chunk_dur
                end = start + chunk_dur
                f.write(f"{i+1}\n{fmt(start)} --> {fmt(end)}\n{line}\n\n")

        return srt_path

    def _burn_subtitles(self, src: str, out: str, srt_path: str):
        # Use absolute path for subtitles filter
        abs_srt = os.path.abspath(srt_path).replace("\\", "/").replace(":", "\\:")
        _run([
            FFMPEG, "-y", "-i", src,
            "-vf",
            f"subtitles='{abs_srt}':force_style='FontSize=24,Bold=1,Alignment=2,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,Outline=2'",
            "-c:a", "copy",
            out,
        ])

    def _pick_music(self) -> Optional[str]:
        music_dir = "storage/shared/music"
        if not os.path.isdir(music_dir):
            return None
        files = [f for f in os.listdir(music_dir) if f.endswith(".mp3")]
        return f"{music_dir}/{files[0]}" if files else None

    def _mix_music(self, src: str, music: str, out: str):
        _run([
            FFMPEG, "-y", "-i", src, "-i", music,
            "-filter_complex",
            "[1:a]volume=0.12[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=2",
            "-c:v", "copy",
            out,
        ])

    def _extract_thumbnail(self, video: str, out: str):
        _run([
            FFMPEG, "-y", "-i", video,
            "-ss", "00:00:02",
            "-vframes", "1",
            "-q:v", "2",
            out,
        ])
