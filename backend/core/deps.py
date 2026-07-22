"""FastAPI dependency helpers."""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.security import decode_token
from backend.models.models import Tenant

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_tenant(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Tenant:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_token(token)
    if payload is None:
        raise credentials_exception
    tenant_id: str = payload.get("sub")
    if not tenant_id:
        raise credentials_exception
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None or not tenant.is_active:
        raise credentials_exception
    return tenant
