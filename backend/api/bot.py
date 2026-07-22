from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.core.database import get_db
from backend.core.deps import get_current_tenant
from backend.models.models import Tenant

router = APIRouter()


class TelegramConnectRequest(BaseModel):
    bot_token: str
    chat_id: str


class WhatsAppConnectRequest(BaseModel):
    account_sid: str
    auth_token: str
    from_number: str
    whatsapp_number: str


class BotStatusOut(BaseModel):
    telegram_connected: bool
    whatsapp_connected: bool
    telegram_chat_id: Optional[str] = None
    whatsapp_number: Optional[str] = None
    bot_active: bool


@router.get("/status")
def bot_status(
    current_tenant: Tenant = Depends(get_current_tenant),
):
    return BotStatusOut(
        telegram_connected=bool(current_tenant.telegram_chat_id),
        whatsapp_connected=bool(current_tenant.whatsapp_number),
        telegram_chat_id=current_tenant.telegram_chat_id,
        whatsapp_number=current_tenant.whatsapp_number,
        bot_active=current_tenant.bot_active or False,
    )


@router.post("/connect/telegram")
def connect_telegram(
    data: TelegramConnectRequest,
    db: Session = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    """Connect Telegram bot to tenant account."""
    tenant = db.query(Tenant).filter(Tenant.id == current_tenant.id).first()
    tenant.telegram_chat_id = data.chat_id
    tenant.bot_active = True
    db.commit()
    return {"success": True, "chat_id": data.chat_id}


@router.post("/connect/whatsapp")
def connect_whatsapp(
    data: WhatsAppConnectRequest,
    db: Session = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    """Connect WhatsApp bot to tenant account."""
    tenant = db.query(Tenant).filter(Tenant.id == current_tenant.id).first()
    tenant.whatsapp_number = data.whatsapp_number
    tenant.bot_active = True
    db.commit()
    return {"success": True, "whatsapp_number": data.whatsapp_number}


@router.delete("/disconnect/{platform}", status_code=204)
def disconnect_bot(
    platform: str,
    db: Session = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    if platform not in ("telegram", "whatsapp"):
        raise HTTPException(400, "Platform harus 'telegram' atau 'whatsapp'")
    tenant = db.query(Tenant).filter(Tenant.id == current_tenant.id).first()
    if platform == "telegram":
        tenant.telegram_chat_id = None
    else:
        tenant.whatsapp_number = None
    if not tenant.telegram_chat_id and not tenant.whatsapp_number:
        tenant.bot_active = False
    db.commit()


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Handle incoming Telegram updates."""
    try:
        from backend.modules.bot.telegram_bot import handle_telegram_update
        payload = await request.json()
        background_tasks.add_task(handle_telegram_update, payload, db)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Handle incoming WhatsApp (Twilio) messages."""
    try:
        from backend.modules.bot.whatsapp_bot import handle_whatsapp_message
        form = await request.form()
        payload = dict(form)
        background_tasks.add_task(handle_whatsapp_message, payload, db)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
