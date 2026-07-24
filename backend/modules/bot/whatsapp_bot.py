"""
WhatsApp bot handler via Twilio webhooks.
Mengirim balasan nyata via Twilio REST API.
"""
import logging
import httpx
from sqlalchemy.orm import Session
from backend.models.models import Tenant, VideoJob
from backend.core.encryption import decrypt_credentials

logger = logging.getLogger(__name__)

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"


def _find_tenant_by_whatsapp(number: str, db: Session):
    clean = number.replace("whatsapp:", "").strip()
    return db.query(Tenant).filter(Tenant.whatsapp_number == clean).first()


def _get_twilio_creds(tenant: Tenant) -> dict:
    """Kembalikan {account_sid, auth_token, from_number} atau {} jika tidak ada."""
    if not tenant.whatsapp_credentials:
        return {}
    return decrypt_credentials(tenant.whatsapp_credentials)


def _send_whatsapp_message(account_sid: str, auth_token: str, from_number: str, to_number: str, body: str) -> bool:
    """Kirim pesan WhatsApp via Twilio Messages API. Return True jika berhasil."""
    to_wa = f"whatsapp:{to_number}" if not to_number.startswith("whatsapp:") else to_number
    from_wa = f"whatsapp:{from_number}" if not from_number.startswith("whatsapp:") else from_number
    try:
        resp = httpx.post(
            f"{TWILIO_API_BASE}/Accounts/{account_sid}/Messages.json",
            auth=(account_sid, auth_token),
            data={"From": from_wa, "To": to_wa, "Body": body},
            timeout=15,
        )
        if resp.status_code not in (200, 201):
            logger.warning(f"Twilio send gagal {resp.status_code}: {resp.text[:200]}")
            return False
        return True
    except Exception as e:
        logger.error(f"Twilio sendMessage error: {e}")
        return False


def handle_whatsapp_message(payload: dict, db: Session):
    """Process incoming WhatsApp message dari Twilio dan kirim balasan."""
    try:
        from_number = payload.get("From", "")
        body = payload.get("Body", "").strip()

        if not from_number or not body:
            return

        tenant = _find_tenant_by_whatsapp(from_number, db)
        if not tenant:
            logger.info(f"Unknown WhatsApp number: {from_number}")
            return

        creds = _get_twilio_creds(tenant)
        account_sid = creds.get("account_sid", "")
        auth_token = creds.get("auth_token", "")
        from_wa = creds.get("from_number", "")

        if not account_sid or not auth_token or not from_wa:
            logger.warning(f"Twilio credentials tidak lengkap untuk tenant {tenant.id}")
            return

        text = body.lower()

        if "status" in text:
            total_jobs = db.query(VideoJob).filter(VideoJob.tenant_id == tenant.id).count()
            done_jobs = db.query(VideoJob).filter(
                VideoJob.tenant_id == tenant.id, VideoJob.status == "done"
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

        # Kirim balasan via Twilio
        to_number = from_number.replace("whatsapp:", "").strip()
        sent = _send_whatsapp_message(account_sid, auth_token, from_wa, to_number, reply)
        logger.info(f"WhatsApp reply sent={sent} for {from_number}: {reply[:60]}...")

    except Exception as e:
        logger.error(f"WhatsApp handler error: {e}")


def send_notification(tenant: Tenant, message: str) -> bool:
    """Kirim notifikasi proaktif ke tenant via WhatsApp. Return True jika berhasil."""
    if not tenant.whatsapp_number or not tenant.bot_active:
        return False
    creds = _get_twilio_creds(tenant)
    account_sid = creds.get("account_sid", "")
    auth_token = creds.get("auth_token", "")
    from_wa = creds.get("from_number", "")
    if not account_sid or not auth_token or not from_wa:
        return False
    return _send_whatsapp_message(account_sid, auth_token, from_wa, tenant.whatsapp_number, message)
