"""
Telegram bot handler — FSM-based command processing.
Integrates with tenant account via chat_id matching.
Mengirim balasan nyata via Telegram Bot API.
"""
import logging
import httpx
from sqlalchemy.orm import Session
from backend.models.models import Tenant, BotSession, VideoJob
from backend.core.encryption import decrypt_credentials
import uuid

logger = logging.getLogger(__name__)

BOT_COMMANDS = """
/start    — selamat datang & panduan
/status   — ringkasan akun
/jobs     — 5 job terakhir
/stats    — statistik hari ini
/trends [niche] — topik trending
/help     — bantuan
"""


def _find_tenant_by_chat_id(chat_id: str, db: Session):
    return db.query(Tenant).filter(Tenant.telegram_chat_id == chat_id).first()


def _get_bot_token(tenant: Tenant) -> str | None:
    if not tenant.telegram_bot_credentials:
        return None
    creds = decrypt_credentials(tenant.telegram_bot_credentials)
    return creds.get("bot_token")


def _get_or_create_session(tenant_id: str, chat_id: str, db: Session) -> BotSession:
    session = db.query(BotSession).filter(
        BotSession.tenant_id == tenant_id,
        BotSession.platform == "telegram",
        BotSession.chat_id == chat_id,
    ).first()
    if not session:
        session = BotSession(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            platform="telegram",
            chat_id=chat_id,
            state="idle",
            context={},
        )
        db.add(session)
        db.commit()
        db.refresh(session)
    return session


def _send_telegram_message(bot_token: str, chat_id: str, text: str) -> bool:
    """Kirim pesan ke Telegram via Bot API. Return True jika berhasil."""
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        data = resp.json()
        if not data.get("ok"):
            logger.warning(f"Telegram sendMessage gagal: {data.get('description')}")
            return False
        return True
    except Exception as e:
        logger.error(f"Telegram sendMessage error: {e}")
        return False


def _format_status(tenant: Tenant, db: Session) -> str:
    total_jobs = db.query(VideoJob).filter(VideoJob.tenant_id == tenant.id).count()
    done_jobs = db.query(VideoJob).filter(
        VideoJob.tenant_id == tenant.id, VideoJob.status == "done"
    ).count()
    from backend.models.models import GeminiKey, Channel
    total_keys = db.query(GeminiKey).filter(
        GeminiKey.tenant_id == tenant.id, GeminiKey.is_active == True
    ).count()
    total_channels = db.query(Channel).filter(
        Channel.tenant_id == tenant.id, Channel.is_active == True
    ).count()

    return (
        f"📊 *Status Akun: {tenant.name}*\n\n"
        f"📹 Total Job: {total_jobs}\n"
        f"✅ Job Selesai: {done_jobs}\n"
        f"🔑 AI Key Aktif: {total_keys}\n"
        f"📺 Channel Terhubung: {total_channels}\n"
        f"💎 Plan: {tenant.plan or 'free'}"
    )


def _format_recent_jobs(tenant_id: str, db: Session) -> str:
    jobs = db.query(VideoJob).filter(
        VideoJob.tenant_id == tenant_id
    ).order_by(VideoJob.created_at.desc()).limit(5).all()

    if not jobs:
        return "📭 Belum ada job. Buat job baru di dashboard!"

    lines = ["📋 *5 Job Terakhir:*\n"]
    status_emoji = {
        "pending": "⏳", "processing": "🔄", "done": "✅",
        "failed": "❌", "scheduled": "📅", "uploaded": "🚀"
    }
    for j in jobs:
        emoji = status_emoji.get(j.status, "❓")
        title = (j.title or "Untitled")[:30]
        lines.append(f"{emoji} {title} — `{j.status}`")

    return "\n".join(lines)


def handle_telegram_update(payload: dict, db: Session):
    """Process incoming Telegram update dan kirim balasan via API."""
    try:
        message = payload.get("message") or payload.get("edited_message")
        if not message:
            return

        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "").strip()

        if not chat_id or not text:
            return

        tenant = _find_tenant_by_chat_id(chat_id, db)
        if not tenant:
            logger.info(f"Unknown chat_id: {chat_id}")
            return

        bot_token = _get_bot_token(tenant)
        if not bot_token:
            logger.warning(f"Bot token tidak tersimpan untuk tenant {tenant.id}")
            return

        _get_or_create_session(tenant.id, chat_id, db)

        # Handle commands
        if text.startswith("/start") or text.startswith("/help"):
            reply = (
                f"👋 Halo *{tenant.name}*! Selamat datang di Shorts Factory Bot.\n\n"
                f"Perintah yang tersedia:\n{BOT_COMMANDS}"
            )
        elif text.startswith("/status") or text.startswith("/stats"):
            reply = _format_status(tenant, db)
        elif text.startswith("/jobs"):
            reply = _format_recent_jobs(tenant.id, db)
        elif text.startswith("/trends"):
            parts = text.split(" ", 1)
            niche = parts[1] if len(parts) > 1 else "motivasi"
            reply = f"🔍 Riset tren untuk niche *{niche}*...\n\nGunakan dashboard untuk analisis lengkap dengan AI."
        else:
            reply = "❓ Perintah tidak dikenal. Ketik /help untuk bantuan."

        sent = _send_telegram_message(bot_token, chat_id, reply)
        logger.info(f"Telegram reply sent={sent} for chat_id={chat_id}: {reply[:60]}...")

    except Exception as e:
        logger.error(f"Telegram handler error: {e}")


def send_notification(tenant: Tenant, message: str) -> bool:
    """Kirim notifikasi proaktif ke tenant via Telegram. Return True jika berhasil."""
    if not tenant.telegram_chat_id or not tenant.bot_active:
        return False
    bot_token = _get_bot_token(tenant)
    if not bot_token:
        return False
    return _send_telegram_message(bot_token, tenant.telegram_chat_id, message)
