"""
Telegram bot handler — FSM-based command processing.
Integrates with tenant account via chat_id matching.
"""
import logging
from sqlalchemy.orm import Session
from backend.models.models import Tenant, BotSession, VideoJob
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
    return db.query(Tenant).filter(
        Tenant.telegram_chat_id == chat_id
    ).first()


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


def _format_status(tenant: Tenant, db: Session) -> str:
    total_jobs = db.query(VideoJob).filter(VideoJob.tenant_id == tenant.id).count()
    done_jobs = db.query(VideoJob).filter(
        VideoJob.tenant_id == tenant.id,
        VideoJob.status == "done"
    ).count()
    from backend.models.models import GeminiKey, Channel
    total_keys = db.query(GeminiKey).filter(
        GeminiKey.tenant_id == tenant.id,
        GeminiKey.is_active == True
    ).count()
    total_channels = db.query(Channel).filter(
        Channel.tenant_id == tenant.id,
        Channel.is_active == True
    ).count()

    return (
        f"📊 *Status Akun: {tenant.name}*\n\n"
        f"📹 Total Job: {total_jobs}\n"
        f"✅ Job Selesai: {done_jobs}\n"
        f"🔑 Gemini Key Aktif: {total_keys}\n"
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
    """Process incoming Telegram update."""
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

        session = _get_or_create_session(tenant.id, chat_id, db)

        # Handle commands
        if text.startswith("/start") or text.startswith("/help"):
            reply = (
                f"👋 Halo *{tenant.name}*! Selamat datang di Shorts Factory Bot.\n\n"
                f"Perintah yang tersedia:\n{BOT_COMMANDS}"
            )
        elif text.startswith("/status"):
            reply = _format_status(tenant, db)
        elif text.startswith("/jobs"):
            reply = _format_recent_jobs(tenant.id, db)
        elif text.startswith("/stats"):
            reply = _format_status(tenant, db)
        elif text.startswith("/trends"):
            parts = text.split(" ", 1)
            niche = parts[1] if len(parts) > 1 else "motivasi"
            reply = f"🔍 Riset tren untuk niche *{niche}*...\n\nGunakan dashboard untuk analisis lengkap dengan AI."
        else:
            reply = f"❓ Perintah tidak dikenal. Ketik /help untuk bantuan."

        logger.info(f"Telegram reply for {chat_id}: {reply[:50]}...")

    except Exception as e:
        logger.error(f"Telegram handler error: {e}")
