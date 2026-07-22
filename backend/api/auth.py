from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from backend.core.database import get_db
from backend.core.security import hash_password, verify_password, create_access_token
from backend.core.deps import get_current_tenant
from backend.models.models import Tenant

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str


class TenantOut(BaseModel):
    id: str
    email: str
    name: str
    plan: str

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    tenant: TenantOut


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if len(body.password) < 8:
        raise HTTPException(status_code=422, detail="Password minimal 8 karakter")
    existing = db.query(Tenant).filter(Tenant.email == body.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email sudah terdaftar")
    tenant = Tenant(
        email=body.email,
        hashed_password=hash_password(body.password),
        name=body.name,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    token = create_access_token({"sub": tenant.id})
    return {"access_token": token, "token_type": "bearer", "tenant": tenant}


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    tenant = db.query(Tenant).filter(Tenant.email == form_data.username).first()
    if not tenant or not verify_password(form_data.password, tenant.hashed_password):
        raise HTTPException(status_code=401, detail="Email atau password salah")
    if not tenant.is_active:
        raise HTTPException(status_code=401, detail="Akun tidak aktif")
    token = create_access_token({"sub": tenant.id})
    return {"access_token": token, "token_type": "bearer", "tenant": tenant}


@router.get("/me", response_model=TenantOut)
def me(current: Tenant = Depends(get_current_tenant)):
    return current
