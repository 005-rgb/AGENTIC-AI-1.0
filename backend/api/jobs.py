import os
import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.core.database import get_db
from backend.core.deps import get_current_tenant
from backend.core.plan_limits import (
    check_daily_job_limit, require_ab_test, require_multi_platform
)
from backend.models.models import VideoJob, Channel, Tenant, AbTestResult

log = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB


class JobJsonCreate(BaseModel):
    source_type: str           # url | ai_generate | text_to_shorts
    source_url: Optional[str] = None
    niche: Optional[str] = None
    channel_id: Optional[str] = None
    topic: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    hook_text: Optional[str] = None
    add_subtitles: bool = True
    add_music: bool = False
    scheduled_at: Optional[datetime] = None
    platforms: List[str] = ["youtube"]


class AbTestStart(BaseModel):
    title_variant_b: str


def _job_out(j: VideoJob) -> dict:
    return {
        "id": j.id,
        "source_type": j.source_type,
        "source_url": j.source_url,
        "niche": j.niche,
        "title": j.title,
        "title_variant_b": j.title_variant_b,
        "status": j.status,
        "progress": j.progress,
        "script": j.script,
        "hook_text": j.hook_text,
        "output_filename": j.output_filename,
        "thumbnail_filename": j.thumbnail_filename,
        "youtube_video_id": j.youtube_video_id,
        "youtube_video_id_b": j.youtube_video_id_b,
        "tiktok_video_id": j.tiktok_video_id,
        "instagram_media_id": j.instagram_media_id,
        "facebook_video_id": j.facebook_video_id,
        "platforms": j.platforms or ["youtube"],
        "ab_test_active": j.ab_test_active,
        "ab_winner": j.ab_winner,
        "error_message": j.error_message,
        "scheduled_at": j.scheduled_at,
        "uploaded_at": j.uploaded_at,
        "created_at": j.created_at,
        "updated_at": j.updated_at,
    }


# ─── List / Get ──────────────────────────────────────────────────────────

@router.get("")
def list_jobs(
    status: Optional[str] = None,
    channel_id: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    q = db.query(VideoJob).filter(VideoJob.tenant_id == tenant.id)
    if status:
        q = q.filter(VideoJob.status == status)
    if channel_id:
        q = q.filter(VideoJob.channel_id == channel_id)
    total = q.count()
    jobs = q.order_by(VideoJob.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    return {"jobs": [_job_out(j) for j in jobs], "total": total, "page": page, "limit": limit}


@router.get("/{job_id}")
def get_job(
    job_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    job = db.query(VideoJob).filter(VideoJob.id == job_id, VideoJob.tenant_id == tenant.id).first()
    if not job:
        raise HTTPException(404, "Job tidak ditemukan")
    return _job_out(job)


# ─── Create (multipart upload) ───────────────────────────────────────────

@router.post("", status_code=201)
async def create_job_upload(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    source_type: str = Form("upload"),
    source_url: Optional[str] = Form(None),
    niche: Optional[str] = Form(None),
    channel_id: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    hook_text: Optional[str] = Form(None),
    add_subtitles: bool = Form(True),
    add_music: bool = Form(False),
    scheduled_at: Optional[str] = Form(None),
    platforms: str = Form('["youtube"]'),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    check_daily_job_limit(tenant, db)

    job_id = str(uuid.uuid4())
    source_filename = None

    if source_type == "upload":
        if not file:
            raise HTTPException(400, "File diperlukan untuk source_type=upload")
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"Format tidak didukung: {', '.join(ALLOWED_EXTENSIONS)}")
        upload_dir = f"storage/{tenant.id}/uploads"
        os.makedirs(upload_dir, exist_ok=True)
        dest = f"{upload_dir}/{job_id}{ext}"
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(400, "File terlalu besar (maks 500MB)")
        with open(dest, "wb") as f_out:
            f_out.write(content)
        source_filename = f"{job_id}{ext}"

    elif source_type in ("url", "ai_generate", "text_to_shorts"):
        if source_type == "url" and not source_url:
            raise HTTPException(400, "source_url diperlukan untuk source_type=url")
    else:
        raise HTTPException(400, "source_type tidak valid")

    if channel_id:
        ch = db.query(Channel).filter(Channel.id == channel_id, Channel.tenant_id == tenant.id).first()
        if not ch:
            raise HTTPException(404, "Channel tidak ditemukan")

    sched = None
    if scheduled_at:
        try:
            sched = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(400, "Format scheduled_at tidak valid (ISO 8601)")

    try:
        platforms_list = json.loads(platforms)
        if not isinstance(platforms_list, list):
            platforms_list = ["youtube"]
    except Exception:
        platforms_list = ["youtube"]

    # Cek plan untuk multi-platform
    if len([p for p in platforms_list if p != "youtube"]) > 0:
        from backend.core.plan_limits import get_limits
        limits = get_limits(tenant)
        if not limits.can_use_multi_platform:
            raise HTTPException(403, "Multi-platform upload hanya tersedia di plan Pro dan Enterprise.")

    job = VideoJob(
        id=job_id,
        tenant_id=tenant.id,
        channel_id=channel_id,
        source_type=source_type,
        source_url=source_url,
        source_filename=source_filename,
        niche=niche,
        title=title,
        description=description,
        hook_text=hook_text,
        add_subtitles=add_subtitles,
        add_music=add_music,
        scheduled_at=sched,
        platforms=platforms_list,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(_process_job_background, job_id)
    return {"job_id": job.id, "status": job.status, "message": "Job diterima, sedang diproses"}


# ─── Create (JSON) ───────────────────────────────────────────────────────

@router.post("/json", status_code=201)
async def create_job_json(
    data: JobJsonCreate,
    background_tasks: BackgroundTasks,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    check_daily_job_limit(tenant, db)

    if data.source_type == "url" and not data.source_url:
        raise HTTPException(400, "source_url diperlukan")
    if data.channel_id:
        ch = db.query(Channel).filter(Channel.id == data.channel_id, Channel.tenant_id == tenant.id).first()
        if not ch:
            raise HTTPException(404, "Channel tidak ditemukan")

    # Cek plan untuk multi-platform
    if len([p for p in data.platforms if p != "youtube"]) > 0:
        from backend.core.plan_limits import get_limits
        limits = get_limits(tenant)
        if not limits.can_use_multi_platform:
            raise HTTPException(403, "Multi-platform upload hanya tersedia di plan Pro dan Enterprise.")

    job_id = str(uuid.uuid4())
    job = VideoJob(
        id=job_id,
        tenant_id=tenant.id,
        channel_id=data.channel_id,
        source_type=data.source_type,
        source_url=data.source_url,
        niche=data.niche,
        hook_text=data.hook_text,
        title=data.title,
        description=data.description,
        add_subtitles=data.add_subtitles,
        add_music=data.add_music,
        scheduled_at=data.scheduled_at,
        platforms=data.platforms,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(_process_job_background, job_id)
    return {"job_id": job.id, "status": job.status, "message": "Job diterima, sedang diproses"}


# ─── Delete ──────────────────────────────────────────────────────────────

@router.delete("/{job_id}", status_code=204)
def delete_job(
    job_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    job = db.query(VideoJob).filter(VideoJob.id == job_id, VideoJob.tenant_id == tenant.id).first()
    if not job:
        raise HTTPException(404, "Job tidak ditemukan")
    db.delete(job)
    db.commit()


# ─── Upload Now ──────────────────────────────────────────────────────────

@router.post("/{job_id}/upload-now")
def upload_now(
    job_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    job = db.query(VideoJob).filter(VideoJob.id == job_id, VideoJob.tenant_id == tenant.id).first()
    if not job:
        raise HTTPException(404, "Job tidak ditemukan")
    if job.status != "done":
        raise HTTPException(400, f"Job belum selesai. Status: {job.status}")
    if not job.channel_id:
        raise HTTPException(400, "Job tidak punya channel")

    channel = db.query(Channel).filter(Channel.id == job.channel_id).first()
    if not channel:
        raise HTTPException(404, "Channel tidak ditemukan")

    result = {}
    platforms = job.platforms or ["youtube"]

    # YouTube
    if "youtube" in platforms:
        if not channel.youtube_credentials:
            raise HTTPException(400, "Channel belum terhubung ke YouTube")
        try:
            from backend.modules.youtube_uploader.uploader import upload_video
            video_id = upload_video(job, channel, db)
            result["youtube_video_id"] = video_id
        except Exception as e:
            raise HTTPException(500, f"Upload YouTube gagal: {str(e)}")

    # Multi-platform
    from backend.core.plan_limits import get_limits
    limits = get_limits(tenant)
    if limits.can_use_multi_platform:
        from backend.modules.scheduler.scheduler import _upload_job_all_platforms
        try:
            _upload_job_all_platforms(job, channel, db)
            db.refresh(job)
            result.update({
                "tiktok_video_id": job.tiktok_video_id,
                "instagram_media_id": job.instagram_media_id,
                "facebook_video_id": job.facebook_video_id,
            })
        except Exception as e:
            log.error(f"Multi-platform upload error: {e}")

    return {"success": True, **result}


# ─── Download ────────────────────────────────────────────────────────────

@router.get("/{job_id}/download")
def download_job(
    job_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    job = db.query(VideoJob).filter(VideoJob.id == job_id, VideoJob.tenant_id == tenant.id).first()
    if not job:
        raise HTTPException(404, "Job tidak ditemukan")
    if job.status not in ("done", "uploaded") or not job.output_filename:
        raise HTTPException(400, "Video belum siap didownload")

    file_path = f"storage/{tenant.id}/output/{job.output_filename}"
    if not os.path.exists(file_path):
        raise HTTPException(404, "File output tidak ditemukan")

    def iter_file():
        with open(file_path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                yield chunk

    return StreamingResponse(
        iter_file(),
        media_type="video/mp4",
        headers={"Content-Disposition": f"attachment; filename={job.output_filename}"},
    )


# ─── A/B Test ────────────────────────────────────────────────────────────

@router.post("/{job_id}/ab-test/start")
def start_ab_test(
    job_id: str,
    data: AbTestStart,
    tenant: Tenant = Depends(require_ab_test),
    db: Session = Depends(get_db),
):
    """
    Aktifkan A/B test: upload variant B dengan judul berbeda ke YouTube.
    Job harus sudah di-upload (status=uploaded) dan punya youtube_video_id.
    """
    job = db.query(VideoJob).filter(VideoJob.id == job_id, VideoJob.tenant_id == tenant.id).first()
    if not job:
        raise HTTPException(404, "Job tidak ditemukan")
    if job.status != "uploaded" or not job.youtube_video_id:
        raise HTTPException(400, "Job harus sudah ter-upload ke YouTube terlebih dahulu")
    if job.ab_test_active:
        raise HTTPException(400, "A/B test sudah aktif untuk job ini")
    if not job.channel_id:
        raise HTTPException(400, "Job tidak punya channel")

    channel = db.query(Channel).filter(Channel.id == job.channel_id).first()
    if not channel or not channel.youtube_credentials:
        raise HTTPException(400, "Channel belum terhubung ke YouTube")

    if not data.title_variant_b or not data.title_variant_b.strip():
        raise HTTPException(400, "title_variant_b tidak boleh kosong")

    job.title_variant_b = data.title_variant_b.strip()

    try:
        from backend.modules.youtube_uploader.uploader import upload_video_variant_b
        video_id_b = upload_video_variant_b(job, channel, db)
        job.ab_test_active = True
        job.ab_winner = None
        db.commit()
        return {
            "success": True,
            "youtube_video_id_a": job.youtube_video_id,
            "youtube_video_id_b": video_id_b,
            "message": "A/B test dimulai. Hasil akan dievaluasi setelah 48 jam.",
        }
    except Exception as e:
        raise HTTPException(500, f"Gagal upload variant B: {str(e)}")


@router.get("/{job_id}/ab-test/result")
def get_ab_test_result(
    job_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    job = db.query(VideoJob).filter(VideoJob.id == job_id, VideoJob.tenant_id == tenant.id).first()
    if not job:
        raise HTTPException(404, "Job tidak ditemukan")
    if not job.ab_test_active:
        raise HTTPException(400, "A/B test tidak aktif untuk job ini")

    results = (
        db.query(AbTestResult)
        .filter(AbTestResult.job_id == job_id)
        .all()
    )
    variants = {r.variant: {
        "youtube_video_id": r.youtube_video_id,
        "views_48h": r.views_48h,
        "ctr_48h": r.ctr_48h,
        "checked_at": r.checked_at,
    } for r in results}

    return {
        "job_id": job_id,
        "title_a": job.title,
        "title_b": job.title_variant_b,
        "ab_winner": job.ab_winner,
        "status": "completed" if job.ab_winner else "pending",
        "results": variants,
    }


@router.post("/{job_id}/ab-test/winner")
def set_ab_winner(
    job_id: str,
    body: dict,
    tenant: Tenant = Depends(require_ab_test),
    db: Session = Depends(get_db),
):
    """Deklarasikan winner A/B test secara manual."""
    job = db.query(VideoJob).filter(VideoJob.id == job_id, VideoJob.tenant_id == tenant.id).first()
    if not job:
        raise HTTPException(404, "Job tidak ditemukan")
    if not job.ab_test_active:
        raise HTTPException(400, "A/B test tidak aktif")

    winner = body.get("winner")
    if winner not in ("a", "b"):
        raise HTTPException(400, "winner harus 'a' atau 'b'")

    job.ab_winner = winner
    db.commit()
    return {"success": True, "winner": winner}


# ─── Background processor ────────────────────────────────────────────────

def _process_job_background(job_id: str):
    """Trigger processor — dipanggil via BackgroundTasks."""
    from backend.core.database import SessionLocal
    from backend.modules.video_processor.processor import VideoProcessor
    db = SessionLocal()
    try:
        job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
        if job:
            processor = VideoProcessor(db)
            processor.run(job)
    except Exception as e:
        log.error(f"Background job {job_id} error: {e}")
        db2 = SessionLocal()
        try:
            j = db2.query(VideoJob).filter(VideoJob.id == job_id).first()
            if j:
                j.status = "failed"
                j.error_message = str(e)
                db2.commit()
        finally:
            db2.close()
    finally:
        db.close()
