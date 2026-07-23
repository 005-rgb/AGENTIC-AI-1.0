"""
APScheduler — background job scheduler.
Jobs:
  - check_pending_jobs     : 30s — proses video yang menunggu
  - check_scheduled_uploads: 60s — upload job terjadwal
  - check_ab_test_results  : 30m — evaluasi A/B test setelah 48h
  - analyze_best_hours     : 6h  — update best upload hours dari YouTube Analytics
  - cleanup_old_files      : daily 03:00 — hapus temp file lama
"""
import logging
import os
import shutil
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

log = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def start_scheduler():
    global _scheduler
    _scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
    _scheduler.add_job(check_pending_jobs,      "interval", seconds=30,  id="pending_jobs")
    _scheduler.add_job(check_scheduled_uploads, "interval", seconds=60,  id="scheduled_uploads")
    _scheduler.add_job(check_ab_test_results,   "interval", minutes=30,  id="ab_test_check")
    _scheduler.add_job(analyze_best_hours,      "interval", hours=6,     id="best_hours")
    _scheduler.add_job(cleanup_old_files,       "cron",     hour=3,      id="cleanup")
    _scheduler.start()
    log.info("Scheduler started (5 jobs registered)")


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Scheduler stopped")


# ─────────────────────────────────────────────────────────────────────────
# Job: check_pending_jobs
# ─────────────────────────────────────────────────────────────────────────

def check_pending_jobs():
    """Pick pending jobs dan trigger processing."""
    from backend.core.database import SessionLocal
    from backend.models.models import VideoJob
    from backend.modules.video_processor.processor import VideoProcessor

    db = SessionLocal()
    try:
        jobs = (
            db.query(VideoJob)
            .filter(VideoJob.status == "pending")
            .order_by(VideoJob.created_at)
            .limit(5)
            .all()
        )
        for job in jobs:
            try:
                processor = VideoProcessor(db)
                processor.run(job)
            except Exception as e:
                log.error(f"Job {job.id} failed: {e}")
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────
# Job: check_scheduled_uploads
# ─────────────────────────────────────────────────────────────────────────

def check_scheduled_uploads():
    """Upload jobs yang sudah melewati waktu jadwal ke semua platform."""
    from backend.core.database import SessionLocal
    from backend.models.models import VideoJob, Channel
    from backend.core.encryption import decrypt_credentials

    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        jobs = (
            db.query(VideoJob)
            .filter(
                VideoJob.status == "scheduled",
                VideoJob.scheduled_at <= now,
                VideoJob.channel_id.isnot(None),
            )
            .all()
        )
        for job in jobs:
            channel = db.query(Channel).filter(Channel.id == job.channel_id).first()
            if not channel:
                continue
            try:
                _upload_job_all_platforms(job, channel, db)
                log.info(f"Scheduled upload done: job={job.id}")
            except Exception as e:
                log.error(f"Scheduled upload failed job={job.id}: {e}")
                job.status = "failed"
                job.error_message = str(e)
                db.commit()
    finally:
        db.close()


def _upload_job_all_platforms(job, channel, db):
    """Upload job ke semua platform yang diminta."""
    from backend.modules.youtube_uploader.uploader import upload_video
    from backend.modules.multi_platform.exporter import MultiPlatformExporter
    from backend.core.encryption import decrypt_credentials

    platforms = job.platforms or ["youtube"]
    video_path = f"storage/{job.tenant_id}/output/{job.output_filename}" if job.output_filename else None

    if not video_path or not os.path.exists(video_path):
        raise FileNotFoundError("Output video tidak ditemukan")

    exporter = MultiPlatformExporter(
        tenant_id=job.tenant_id,
        output_base=f"storage/{job.tenant_id}",
    )
    exported = exporter.export_all(video_path, platforms)
    dirty = False

    # YouTube
    if "youtube" in platforms and channel.youtube_credentials:
        try:
            upload_video(job, channel, db)
            dirty = True
        except Exception as e:
            log.error(f"YouTube upload failed: {e}")

    # TikTok
    if "tiktok" in platforms and channel.tiktok_credentials:
        try:
            creds = decrypt_credentials(channel.tiktok_credentials)
            tiktok_path = exported.get("tiktok") or video_path
            video_id = exporter.upload_tiktok(
                tiktok_path, job.title or "", job.description or "",
                access_token=creds.get("access_token", ""),
            )
            if video_id:
                job.tiktok_video_id = video_id
                dirty = True
        except Exception as e:
            log.error(f"TikTok upload failed: {e}")

    # Instagram
    if "instagram" in platforms and channel.meta_ig_user_id and channel.meta_credentials:
        try:
            creds = decrypt_credentials(channel.meta_credentials)
            ig_path = exported.get("instagram") or video_path
            media_id = exporter.upload_instagram_reels(
                ig_path,
                caption=job.description or job.title or "",
                access_token=creds.get("access_token", ""),
                ig_user_id=channel.meta_ig_user_id,
            )
            if media_id:
                job.instagram_media_id = media_id
                dirty = True
        except Exception as e:
            log.error(f"Instagram upload failed: {e}")

    # Facebook
    if "facebook" in platforms and channel.meta_page_id and channel.meta_credentials:
        try:
            creds = decrypt_credentials(channel.meta_credentials)
            fb_path = exported.get("facebook") or video_path
            video_id = exporter.upload_facebook_reels(
                fb_path,
                description=job.description or "",
                title=job.title or "",
                access_token=creds.get("access_token", ""),
                page_id=channel.meta_page_id,
            )
            if video_id:
                job.facebook_video_id = video_id
                dirty = True
        except Exception as e:
            log.error(f"Facebook upload failed: {e}")

    if dirty:
        if job.status != "uploaded":
            job.status = "uploaded"
            job.uploaded_at = datetime.now(timezone.utc)
        db.commit()


# ─────────────────────────────────────────────────────────────────────────
# Job: check_ab_test_results  (Phase 3)
# ─────────────────────────────────────────────────────────────────────────

def check_ab_test_results():
    """
    Evaluasi A/B test setelah 48 jam.
    Bandingkan views variant A vs B, set ab_winner otomatis.
    """
    from backend.core.database import SessionLocal
    from backend.models.models import VideoJob, AbTestResult, Channel
    from backend.modules.youtube_uploader.uploader import fetch_video_analytics

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=48)

    db = SessionLocal()
    try:
        # Jobs dengan A/B aktif yang sudah 48h+
        jobs = (
            db.query(VideoJob)
            .filter(
                VideoJob.ab_test_active == True,
                VideoJob.ab_winner.is_(None),
                VideoJob.youtube_video_id.isnot(None),
                VideoJob.youtube_video_id_b.isnot(None),
                VideoJob.uploaded_at <= cutoff,
            )
            .all()
        )

        for job in jobs:
            try:
                channel = db.query(Channel).filter(Channel.id == job.channel_id).first()
                if not channel or not channel.youtube_credentials:
                    continue

                stats_a = fetch_video_analytics(channel, job.youtube_video_id)
                stats_b = fetch_video_analytics(channel, job.youtube_video_id_b)

                views_a = stats_a.get("views", 0)
                views_b = stats_b.get("views", 0)
                ctr_a   = stats_a.get("ctr", 0.0)
                ctr_b   = stats_b.get("ctr", 0.0)

                # Update atau buat AbTestResult
                _upsert_ab_result(db, job.id, "a", job.youtube_video_id, views_a, ctr_a)
                _upsert_ab_result(db, job.id, "b", job.youtube_video_id_b, views_b, ctr_b)

                # Tentukan winner (prioritas CTR, fallback ke views)
                if ctr_a > 0 or ctr_b > 0:
                    winner = "a" if ctr_a >= ctr_b else "b"
                else:
                    winner = "a" if views_a >= views_b else "b"

                job.ab_winner = winner
                db.commit()
                log.info(
                    f"A/B result job={job.id}: A={views_a}views/{ctr_a:.2%}ctr "
                    f"B={views_b}views/{ctr_b:.2%}ctr → winner={winner}"
                )
            except Exception as e:
                log.error(f"A/B check error job={job.id}: {e}")
    finally:
        db.close()


def _upsert_ab_result(db, job_id: str, variant: str, yt_video_id: str, views: int, ctr: float):
    from backend.models.models import AbTestResult
    import uuid
    result = (
        db.query(AbTestResult)
        .filter(AbTestResult.job_id == job_id, AbTestResult.variant == variant)
        .first()
    )
    now = datetime.now(timezone.utc)
    if result:
        result.views_48h = views
        result.ctr_48h = ctr
        result.checked_at = now
    else:
        result = AbTestResult(
            id=str(uuid.uuid4()),
            job_id=job_id,
            variant=variant,
            youtube_video_id=yt_video_id,
            views_48h=views,
            ctr_48h=ctr,
            checked_at=now,
        )
        db.add(result)
    db.commit()


# ─────────────────────────────────────────────────────────────────────────
# Job: analyze_best_hours  (Phase 3 / Smart Scheduler)
# ─────────────────────────────────────────────────────────────────────────

def analyze_best_hours():
    """
    Analisis jam terbaik upload per channel dari YouTube Analytics API.
    Update channel.best_upload_hours.
    """
    from backend.core.database import SessionLocal
    from backend.models.models import Channel, VideoJob
    from backend.core.encryption import decrypt_credentials

    db = SessionLocal()
    try:
        channels = (
            db.query(Channel)
            .filter(Channel.youtube_credentials.isnot(None), Channel.is_active == True)
            .all()
        )
        for channel in channels:
            try:
                hours = _compute_best_hours_from_jobs(db, channel)
                if hours:
                    channel.best_upload_hours = hours
                    db.commit()
                    log.info(f"Updated best hours channel={channel.id}: {hours}")
            except Exception as e:
                log.error(f"analyze_best_hours error channel={channel.id}: {e}")
    finally:
        db.close()


def _compute_best_hours_from_jobs(db, channel) -> list:
    """
    Hitung jam upload terbaik dari riwayat job yang berhasil.
    Gunakan YouTube Analytics API jika tersedia, fallback ke pola upload historis.
    """
    from backend.models.models import VideoJob
    import requests
    from backend.core.encryption import decrypt_credentials
    from collections import defaultdict

    # Coba YouTube Analytics API dulu
    try:
        creds = decrypt_credentials(channel.youtube_credentials)
        access_token = creds.get("access_token", "")
        if access_token:
            # YouTube Analytics API: dapatkan performance per jam
            from datetime import date
            end_date = date.today().isoformat()
            start_date = (date.today() - timedelta(days=90)).isoformat()

            resp = requests.get(
                "https://youtubeanalytics.googleapis.com/v2/reports",
                params={
                    "ids": f"channel=={channel.youtube_channel_id or 'mine'}",
                    "startDate": start_date,
                    "endDate": end_date,
                    "metrics": "views,estimatedMinutesWatched",
                    "dimensions": "hour",
                    "sort": "-views",
                },
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            if resp.status_code == 200:
                rows = resp.json().get("rows", [])
                if rows:
                    # Ambil 4 jam teratas
                    top_hours = sorted(
                        [int(row[0]) for row in rows[:4]]
                    )
                    return top_hours
    except Exception as e:
        log.debug(f"YouTube Analytics API unavailable: {e}")

    # Fallback: analisis dari riwayat upload internal
    jobs = (
        db.query(VideoJob)
        .filter(
            VideoJob.channel_id == channel.id,
            VideoJob.status == "uploaded",
            VideoJob.uploaded_at.isnot(None),
        )
        .order_by(VideoJob.uploaded_at.desc())
        .limit(100)
        .all()
    )

    if len(jobs) < 5:
        return []  # Tidak cukup data

    hour_views: dict = defaultdict(list)
    for job in jobs:
        if job.uploaded_at:
            hour = job.uploaded_at.hour
            hour_views[hour].append(1)  # Proxy: tiap upload = 1 event

    if not hour_views:
        return []

    # Pilih 4 jam dengan frekuensi tertinggi
    sorted_hours = sorted(hour_views, key=lambda h: len(hour_views[h]), reverse=True)
    top = sorted(sorted_hours[:4])
    return top


# ─────────────────────────────────────────────────────────────────────────
# Job: cleanup_old_files
# ─────────────────────────────────────────────────────────────────────────

def cleanup_old_files():
    """Hapus temp files dan platform exports lebih dari 7 hari."""
    from backend.core.database import SessionLocal
    from backend.models.models import Tenant

    db = SessionLocal()
    try:
        tenants = db.query(Tenant).all()
        cutoff = datetime.now() - timedelta(days=7)
        for tenant in tenants:
            for subdir in ("temp", os.path.join("platforms")):
                target = f"storage/{tenant.id}/{subdir}"
                if not os.path.isdir(target):
                    continue
                for fname in os.listdir(target):
                    fpath = os.path.join(target, fname)
                    try:
                        mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
                        if mtime < cutoff:
                            if os.path.isdir(fpath):
                                shutil.rmtree(fpath)
                            else:
                                os.remove(fpath)
                    except Exception:
                        pass
    finally:
        db.close()
