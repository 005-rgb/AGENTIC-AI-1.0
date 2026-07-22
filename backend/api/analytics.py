from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.deps import get_current_tenant
from backend.models.models import Channel, VideoJob, Tenant

router = APIRouter()


@router.get("/{channel_id}")
def get_analytics(
    channel_id: str,
    days: int = Query(30, ge=1, le=365),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    ch = db.query(Channel).filter(Channel.id == channel_id, Channel.tenant_id == tenant.id).first()
    if not ch:
        raise HTTPException(404, "Channel tidak ditemukan")

    jobs = (
        db.query(VideoJob)
        .filter(
            VideoJob.channel_id == channel_id,
            VideoJob.tenant_id == tenant.id,
            VideoJob.status == "uploaded",
        )
        .all()
    )

    # If YouTube credentials available, try to fetch real analytics
    videos = []
    if ch.youtube_credentials and jobs:
        try:
            from backend.modules.youtube_uploader.uploader import fetch_video_analytics
            for j in jobs:
                if j.youtube_video_id:
                    stats = fetch_video_analytics(ch, j.youtube_video_id)
                    videos.append({
                        "youtube_video_id": j.youtube_video_id,
                        "title": j.title or "",
                        "views": stats.get("views", 0),
                        "likes": stats.get("likes", 0),
                        "ctr": stats.get("ctr", 0.0),
                        "uploaded_at": j.uploaded_at,
                    })
        except Exception:
            pass

    total_views = sum(v.get("views", 0) for v in videos)
    avg_ctr = (sum(v.get("ctr", 0) for v in videos) / len(videos)) if videos else 0.0

    return {
        "channel_id": channel_id,
        "channel_name": ch.channel_name,
        "period_days": days,
        "summary": {
            "total_views": total_views,
            "total_videos": len(jobs),
            "avg_ctr": round(avg_ctr, 2),
            "best_upload_hours": ch.best_upload_hours or [7, 12, 19],
        },
        "videos": videos,
    }
