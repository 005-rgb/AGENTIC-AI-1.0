"""
APScheduler — background job scheduler.
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
    _scheduler.add_job(check_pending_jobs,      "interval", seconds=30,   id="pending_jobs")
    _scheduler.add_job(check_scheduled_uploads, "interval", seconds=60,   id="scheduled_uploads")
    _scheduler.add_job(cleanup_old_files,       "cron",     hour=3,       id="cleanup")
    _scheduler.start()
    log.info("Scheduler started")


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Scheduler stopped")


def check_pending_jobs():
    """Pick pending jobs and trigger processing."""
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


def check_scheduled_uploads():
    """Upload jobs that have passed their scheduled time."""
    from backend.core.database import SessionLocal
    from backend.models.models import VideoJob, Channel
    from backend.modules.youtube_uploader.uploader import upload_video

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
            if channel and channel.youtube_credentials:
                try:
                    upload_video(job, channel, db)
                    log.info(f"Scheduled upload done: job={job.id}")
                except Exception as e:
                    log.error(f"Scheduled upload failed job={job.id}: {e}")
                    job.status = "failed"
                    job.error_message = str(e)
                    db.commit()
    finally:
        db.close()


def cleanup_old_files():
    """Remove temp files older than 7 days."""
    from backend.core.database import SessionLocal
    from backend.models.models import Tenant

    db = SessionLocal()
    try:
        tenants = db.query(Tenant).all()
        cutoff = datetime.now() - timedelta(days=7)
        for tenant in tenants:
            temp_dir = f"storage/{tenant.id}/temp"
            if not os.path.isdir(temp_dir):
                continue
            for fname in os.listdir(temp_dir):
                fpath = os.path.join(temp_dir, fname)
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
