from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from backend.core.database import get_db
from backend.core.deps import get_current_tenant
from backend.models.models import Tenant

router = APIRouter()


class ScriptRequest(BaseModel):
    topic: str
    niche: str
    duration_seconds: int = 45


@router.get("")
def get_trends(
    niche: str = Query(..., description="Niche konten"),
    limit: int = Query(10, ge=1, le=30),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    try:
        from backend.modules.trend_scout.scout import TrendScout
        scout = TrendScout()
        trends = scout.get_trends(tenant.id, niche, limit)
        return {"niche": niche, "trends": trends}
    except Exception as e:
        raise HTTPException(500, f"Gagal ambil tren: {str(e)}")


@router.post("/generate-script")
def generate_script(
    data: ScriptRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    try:
        from backend.modules.script_generator.generator import ScriptGenerator
        gen = ScriptGenerator()
        result = gen.generate(
            tenant_id=tenant.id,
            niche=data.niche,
            topic=data.topic,
            duration_seconds=data.duration_seconds,
        )
        return result
    except Exception as e:
        raise HTTPException(500, f"Gagal generate script: {str(e)}")
