from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
import uuid
from datetime import datetime

from backend.core.database import get_db
from backend.core.deps import get_current_tenant
from backend.models.models import CompetitorAnalysis, Tenant

router = APIRouter()


class SpyRequest(BaseModel):
    channel_url: str


def _analysis_out(a) -> dict:
    return {
        "id": a.id,
        "channel_url": a.channel_url,
        "channel_name": a.channel_name,
        "result": a.result,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _run_spy(analysis_id: str, channel_url: str, tenant_id: str, db: Session):
    """Background task to run competitor analysis."""
    from backend.modules.competitor_spy.spy import CompetitorSpy
    from backend.core.gemini_pool import get_genai_client, load_tenant_keys_from_db

    analysis = db.query(CompetitorAnalysis).filter(
        CompetitorAnalysis.id == analysis_id
    ).first()
    if not analysis:
        return

    try:
        # Ensure pool is loaded for this tenant, then get a configured genai module
        load_tenant_keys_from_db(db, tenant_id)
        try:
            genai_client = get_genai_client(tenant_id)
        except RuntimeError:
            genai_client = None  # No keys configured — spy will use basic analysis

        spy = CompetitorSpy(genai_client)
        result = spy.analyze(channel_url)
        analysis.channel_name = result.get("channel_name", "")
        analysis.result = result
        db.commit()
    except Exception as e:
        analysis.result = {"error": str(e), "channel_url": channel_url}
        db.commit()


@router.post("/analyze", status_code=202)
def analyze_competitor(
    data: SpyRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    analysis = CompetitorAnalysis(
        id=str(uuid.uuid4()),
        tenant_id=current_tenant.id,
        channel_url=data.channel_url,
        result={"status": "processing"},
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    background_tasks.add_task(
        _run_spy, analysis.id, data.channel_url, current_tenant.id, db
    )

    return {"id": analysis.id, "status": "processing"}


@router.get("/analyze/{analysis_id}")
def get_analysis(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    analysis = db.query(CompetitorAnalysis).filter(
        CompetitorAnalysis.id == analysis_id,
        CompetitorAnalysis.tenant_id == current_tenant.id,
    ).first()
    if not analysis:
        raise HTTPException(404, "Analisis tidak ditemukan")
    return _analysis_out(analysis)


@router.get("/history")
def spy_history(
    db: Session = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    analyses = db.query(CompetitorAnalysis).filter(
        CompetitorAnalysis.tenant_id == current_tenant.id
    ).order_by(CompetitorAnalysis.created_at.desc()).limit(20).all()
    return {"history": [_analysis_out(a) for a in analyses]}
