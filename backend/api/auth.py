from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, field_validator
import uuid

from backend.core.database import get_db
from backend.core.security import hash_password, verify_password, create_access_token
from backend.core.deps import get_current_tenant
from backend.models.models import Tenant

router = APIRouter()


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        import re
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("Format email tidak valid")
        return v.lower().strip()


class TenantOut(BaseModel):
    id: str
    email: str
    name: str
    plan: str
    is_reseller: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant: TenantOut


def _tenant_out(t) -> TenantOut:
    return TenantOut(
        id=t.id,
        email=t.email,
        name=t.name,
        plan=t.plan or "free",
        is_reseller=getattr(t, "is_reseller", False) or False,
        created_at=t.created_at,
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    if len(data.password) < 8:
        raise HTTPException(422, "Password minimal 8 karakter")
    existing = db.query(Tenant).filter(Tenant.email == data.email).first()
    if existing:
        raise HTTPException(409, "Email sudah terdaftar")
    tenant = Tenant(
        id=str(uuid.uuid4()),
        email=data.email,
        hashed_password=hash_password(data.password),
        name=data.name,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    token = create_access_token({"sub": tenant.id})
    return TokenResponse(access_token=token, tenant=_tenant_out(tenant))


@router.post("/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.email == form.username).first()
    if not tenant or not verify_password(form.password, tenant.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email atau password salah")
    if not tenant.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Akun tidak aktif")
    token = create_access_token({"sub": tenant.id})
    return TokenResponse(access_token=token, tenant=_tenant_out(tenant))


@router.get("/me", response_model=TenantOut)
def me(tenant: Tenant = Depends(get_current_tenant)):
    return _tenant_out(tenant)
