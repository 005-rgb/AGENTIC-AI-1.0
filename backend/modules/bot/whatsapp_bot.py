"""
WhatsApp bot handler via Twilio webhooks.
"""
import logging
from sqlalchemy.orm import Session
from backend.models.models import Tenant, VideoJob
import uuid

logger = logging.getLogger(__name__)


def _find_tenant_by_whatsapp(number: str, db: Session):
    # Strip whatsapp: prefix if present
    clean = number.replace("whatsapp:", "").strip()
    return db.query(Tenant).filter(
        Tenant.whatsapp_number == clean
    ).first()


def handle_whatsapp_message(payload: dict, db: Session):
    """Process incoming WhatsApp message from Twilio."""
    try:
        from_number = payload.get("From", "")
        body = payload.get("Body", "").strip()

        if not from_number or not body:
            return

        tenant = _find_tenant_by_whatsapp(from_number, db)
        if not tenant:
            logger.info(f"Unknown WhatsApp number: {from_number}")
            return

        text = body.lower()

        if "status" in text:
            total_jobs = db.query(VideoJob).filter(VideoJob.tenant_id == tenant.id).count()
            done_jobs = db.query(VideoJob).filter(
                VideoJob.tenant_id == tenant.id,
                VideoJob.status == "done"
            ).count()
            reply = (
                f"📊 Status Akun: {tenant.name}\n"
                f"Total Job: {total_jobs}\n"
                f"Selesai: {done_jobs}\n"
                f"Plan: {tenant.plan or 'free'}"
            )
        elif "job" in text:
            jobs = db.query(VideoJob).filter(
                VideoJob.tenant_id == tenant.id
            ).order_by(VideoJob.created_at.desc()).limit(5).all()
            if not jobs:
                reply = "Belum ada job. Gunakan dashboard untuk membuat job baru."
            else:
                lines = ["5 Job Terakhir:"]
                for j in jobs:
                    title = (j.title or "Untitled")[:25]
                    lines.append(f"- {title}: {j.status}")
                reply = "\n".join(lines)
        elif "help" in text or "bantuan" in text:
            reply = (
                "Perintah WhatsApp Bot:\n"
                "- 'status' → ringkasan akun\n"
                "- 'jobs' → 5 job terakhir\n"
                "- 'help' → bantuan ini\n\n"
                "Untuk fitur lengkap, gunakan dashboard web."
            )
        else:
            reply = "Ketik 'help' untuk melihat perintah yang tersedia."

        logger.info(f"WhatsApp reply for {from_number}: {reply[:50]}...")

    except Exception as e:
        logger.error(f"WhatsApp handler error: {e}")
