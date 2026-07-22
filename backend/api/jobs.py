import os
import uuid
import json
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.core.database import get_db
from backend.core.deps import get_current_tenant
from backend.models.models import VideoJob, Channel, Tenant

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
    hook_text: Optional[str] = None
    add_subtitles: bool = True
    add_music: bool = False
    scheduled_at: Optional[datetime] = None
    platforms: List[str] = ["youtube"]


def _job_out(j: VideoJob) -> dict:
    return {
        "id": j.id,
        "source_type": j.source_type,
        "source_url": j.source_url,
        "niche": j.niche,
        "title": j.title,
        "status": j.status,
        "progress": j.progress,
        "script": j.script,
        "hook_text": j.hook_text,
        "output_filename": j.output_filename,
        "thumbnail_filename": j.thumbnail_filename,
        "youtube_video_id": j.youtube_video_id,
        "platforms": j.tags if isinstance(j.tags, list) else [],
        "error_message": j.error_message,
        "scheduled_at": j.scheduled_at,
        "uploaded_at": j.uploaded_at,
        "created_at": j.created_at,
        "updated_at": j.updated_at,
    }


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


@router.post("", status_code=201)
async def create_job_upload(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    source_type: str = Form("upload"),
    source_url: Optional[str] = Form(None),
    niche: Optional[str] = Form(None),
    channel_id: Optional[str] = Form(None),
    hook_text: Optional[str] = Form(None),
    add_subtitles: bool = Form(True),
    add_music: bool = Form(False),
    scheduled_at: Optional[str] = Form(None),
    platforms: str = Form('["youtube"]'),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    job_id = str(uuid.uuid4())
    source_filename = None

    if source_type == "upload":
        if not file:
            raise HTTPException(400, "File diperlukan untuk source_type=upload")
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"Format file tidak didukung. Gunakan: {', '.join(ALLOWED_EXTENSIONS)}")
        upload_dir = f"storage/{tenant.id}/uploads"
        os.makedirs(upload_dir, exist_ok=True)
        dest = f"{upload_dir}/{job_id}{ext}"
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(400, "File terlalu besar. Maksimal 500MB")
        with open(dest, "wb") as f:
            f.write(content)
        source_filename = f"{job_id}{ext}"

    elif source_type in ("url", "ai_generate", "text_to_shorts"):
        if source_type == "url" and not source_url:
            raise HTTPException(400, "source_url diperlukan untuk source_type=url")
    else:
        raise HTTPException(400, "source_type tidak valid")

    # Validate channel ownership
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
    except Exception:
        platforms_list = ["youtube"]

    job = VideoJob(
        id=job_id,
        tenant_id=tenant.id,
        channel_id=channel_id,
        source_type=source_type,
        source_url=source_url,
        source_filename=source_filename,
        niche=niche,
        hook_text=hook_text,
        add_subtitles=add_subtitles,
        add_music=add_music,
        scheduled_at=sched,
        status="pending",
        tags=platforms_list,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Trigger background processing
    background_tasks.add_task(_process_job_background, job_id)

    return {"job_id": job.id, "status": job.status, "message": "Job diterima, sedang diproses"}


@router.post("/json", status_code=201)
async def create_job_json(
    data: JobJsonCreate,
    background_tasks: BackgroundTasks,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    if data.source_type == "url" and not data.source_url:
        raise HTTPException(400, "source_url diperlukan")
    if data.channel_id:
        ch = db.query(Channel).filter(Channel.id == data.channel_id, Channel.tenant_id == tenant.id).first()
        if not ch:
            raise HTTPException(404, "Channel tidak ditemukan")

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
        add_subtitles=data.add_subtitles,
        add_music=data.add_music,
        scheduled_at=data.scheduled_at,
        status="pending",
        tags=data.platforms,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(_process_job_background, job_id)
    return {"job_id": job.id, "status": job.status, "message": "Job diterima, sedang diproses"}


@router.get("/{job_id}")
def get_job(job_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    job = db.query(VideoJob).filter(VideoJob.id == job_id, VideoJob.tenant_id == tenant.id).first()
    if not job:
        raise HTTPException(404, "Job tidak ditemukan")
    return _job_out(job)


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    job = db.query(VideoJob).filter(VideoJob.id == job_id, VideoJob.tenant_id == tenant.id).first()
    if not job:
        raise HTTPException(404, "Job tidak ditemukan")
    db.delete(job)
    db.commit()


@router.post("/{job_id}/upload-now")
def upload_now(job_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    job = db.query(VideoJob).filter(VideoJob.id == job_id, VideoJob.tenant_id == tenant.id).first()
    if not job:
        raise HTTPException(404, "Job tidak ditemukan")
    if job.status != "done":
        raise HTTPException(400, f"Job belum selesai diproses. Status saat ini: {job.status}")
    if not job.channel_id:
        raise HTTPException(400, "Job tidak punya channel. Set channel_id terlebih dahulu")

    channel = db.query(Channel).filter(Channel.id == job.channel_id).first()
    if not channel or not channel.youtube_credentials:
        raise HTTPException(400, "Channel belum terhubung ke YouTube")

    try:
        from backend.modules.youtube_uploader.uploader import upload_video
        video_id = upload_video(job, channel, db)
        return {"success": True, "youtube_video_id": video_id}
    except Exception as e:
        raise HTTPException(500, f"Upload gagal: {str(e)}")


@router.get("/{job_id}/download")
def download_job(job_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    job = db.query(VideoJob).filter(VideoJob.id == job_id, VideoJob.tenant_id == tenant.id).first()
    if not job:
        raise HTTPException(404, "Job tidak ditemukan")
    if job.status != "done" or not job.output_filename:
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


def _process_job_background(job_id: str):
    """Trigger processor — called via BackgroundTasks."""
    from backend.core.database import SessionLocal
    from backend.modules.video_processor.processor import VideoProcessor
    db = SessionLocal()
    try:
        job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
        if job:
            processor = VideoProcessor(db)
            processor.run(job)
    except Exception as e:
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
