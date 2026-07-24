import hashlib
import hmac
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.core.database import get_db
from backend.core.deps import get_current_tenant
from backend.core.encryption import encrypt_credentials, decrypt_credentials
from backend.models.models import Tenant

log = logging.getLogger(__name__)
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
def bot_status(current_tenant: Tenant = Depends(get_current_tenant)):
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
    """Connect Telegram bot — simpan token terenkripsi dan verifikasi bot_token dulu."""
    # Validasi token via Telegram getMe
    import httpx
    try:
        r = httpx.get(
            f"https://api.telegram.org/bot{data.bot_token}/getMe",
            timeout=10,
        )
        result = r.json()
        if not result.get("ok"):
            raise HTTPException(400, f"Bot token tidak valid: {result.get('description', 'unknown')}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Gagal verifikasi Telegram token: {e}")

    # Derive webhook_secret deterministik dari bot_token + app secret
    # (dipakai sebagai `secret_token` saat memanggil setWebhook)
    from backend.core.config import settings as app_settings
    import hashlib as _hl
    webhook_secret = hmac.new(
        app_settings.SECRET_KEY.encode(),
        data.bot_token.encode(),
        _hl.sha256,
    ).hexdigest()[:64]

    tenant = db.query(Tenant).filter(Tenant.id == current_tenant.id).first()
    tenant.telegram_chat_id = data.chat_id
    tenant.telegram_bot_credentials = encrypt_credentials({
        "bot_token": data.bot_token,
        "webhook_secret": webhook_secret,
    })
    tenant.bot_active = True
    db.commit()
    return {
        "success": True,
        "chat_id": data.chat_id,
        "webhook_secret": webhook_secret,   # Pakai ini sebagai secret_token di setWebhook
    }


@router.post("/connect/whatsapp")
def connect_whatsapp(
    data: WhatsAppConnectRequest,
    db: Session = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    """Connect WhatsApp bot — simpan Twilio credentials terenkripsi."""
    tenant = db.query(Tenant).filter(Tenant.id == current_tenant.id).first()
    tenant.whatsapp_number = data.whatsapp_number
    tenant.whatsapp_credentials = encrypt_credentials({
        "account_sid": data.account_sid,
        "auth_token": data.auth_token,
        "from_number": data.from_number,
    })
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
        tenant.telegram_bot_credentials = None
    else:
        tenant.whatsapp_number = None
        tenant.whatsapp_credentials = None
    if not tenant.telegram_chat_id and not tenant.whatsapp_number:
        tenant.bot_active = False
    db.commit()


# ─── Webhook: Telegram ───────────────────────────────────────────────────────

@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Handle incoming Telegram updates.

    Fail-closed per tenant:
    - Jika tenant punya webhook_secret tersimpan → header WAJIB ada dan cocok (constant-time).
    - Jika tidak cocok atau header hilang padahal secret tersimpan → 403.
    - Tenant tanpa webhook_secret → diterima (webhook lama, sebelum fitur ini).
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    chat_id = str(
        (payload.get("message") or payload.get("edited_message") or {})
        .get("chat", {})
        .get("id", "")
    )

    if chat_id:
        tenant = db.query(Tenant).filter(Tenant.telegram_chat_id == chat_id).first()
        if tenant and tenant.telegram_bot_credentials:
            creds = decrypt_credentials(tenant.telegram_bot_credentials)
            stored_secret = creds.get("webhook_secret", "")
            if stored_secret:
                # Tenant punya webhook_secret — wajib cocok, fail-closed
                provided_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
                if not provided_secret or not hmac.compare_digest(stored_secret, provided_secret):
                    raise HTTPException(403, "X-Telegram-Bot-Api-Secret-Token tidak valid atau tidak ada")

    try:
        from backend.modules.bot.telegram_bot import handle_telegram_update
        background_tasks.add_task(handle_telegram_update, payload, db)
        return {"ok": True}
    except Exception as e:
        log.error(f"Telegram webhook error: {e}")
        return {"ok": False, "error": str(e)}


# ─── Webhook: WhatsApp (Twilio) ──────────────────────────────────────────────

def _verify_twilio_signature(auth_token: str, url: str, params: dict, provided_sig: str) -> bool:
    """
    Verifikasi X-Twilio-Signature menggunakan HMAC-SHA1.
    https://www.twilio.com/docs/usage/webhooks/webhooks-security
    Fail-closed: signature wajib ada jika auth_token tersedia.
    """
    if not provided_sig:
        return False  # Signature wajib ada — tolak jika tidak ada
    s = url + "".join(f"{k}{v}" for k, v in sorted(params.items()))
    expected = hmac.new(auth_token.encode(), s.encode(), hashlib.sha1).digest()
    import base64
    expected_b64 = base64.b64encode(expected).decode()
    return hmac.compare_digest(expected_b64, provided_sig)


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Handle incoming WhatsApp (Twilio) messages — verifikasi HMAC."""
    form = await request.form()
    payload = dict(form)

    from_number = payload.get("From", "").replace("whatsapp:", "").strip()
    if from_number:
        tenant = db.query(Tenant).filter(Tenant.whatsapp_number == from_number).first()
        if tenant and tenant.whatsapp_credentials:
            creds = decrypt_credentials(tenant.whatsapp_credentials)
            auth_token = creds.get("auth_token", "")
            provided_sig = request.headers.get("X-Twilio-Signature", "")
            url = str(request.url)
            if auth_token and not _verify_twilio_signature(auth_token, url, payload, provided_sig):
                raise HTTPException(403, "Signature Twilio tidak valid — request ditolak")
        elif tenant:
            # Tenant ditemukan tapi belum punya credentials — tidak bisa verifikasi, tolak
            provided_sig = request.headers.get("X-Twilio-Signature", "")
            if not provided_sig:
                raise HTTPException(403, "Signature Twilio wajib ada")

    try:
        from backend.modules.bot.whatsapp_bot import handle_whatsapp_message
        background_tasks.add_task(handle_whatsapp_message, payload, db)
        return {"ok": True}
    except Exception as e:
        log.error(f"WhatsApp webhook error: {e}")
        return {"ok": False, "error": str(e)}
