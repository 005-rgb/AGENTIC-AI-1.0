"""
Fernet symmetric encryption untuk menyimpan credentials sensitif.
Aktif jika FERNET_KEY di-set sebagai env var/secret.
Jika tidak di-set, fall back ke plain JSON (backward compatible).
"""
import json
import logging
import os
from typing import Any, Optional

log = logging.getLogger(__name__)

_fernet = None
_fernet_disabled = False


def _get_fernet():
    global _fernet, _fernet_disabled
    if _fernet_disabled:
        return None
    if _fernet is not None:
        return _fernet
    key = os.getenv("FERNET_KEY", "").strip()
    if not key:
        log.warning(
            "FERNET_KEY tidak di-set — credentials disimpan tanpa enkripsi. "
            "Set FERNET_KEY sebagai Replit Secret untuk enkripsi penuh."
        )
        _fernet_disabled = True
        return None
    try:
        from cryptography.fernet import Fernet
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
        log.info("Fernet encryption aktif untuk credentials storage")
        return _fernet
    except Exception as e:
        log.error(f"Fernet init gagal: {e} — fall back ke plain JSON")
        _fernet_disabled = True
        return None


def encrypt_credentials(data: dict) -> str:
    """Encrypt dict ke string (Fernet atau plain JSON fallback)."""
    f = _get_fernet()
    raw = json.dumps(data)
    if f is None:
        return raw
    return f.encrypt(raw.encode()).decode()


def decrypt_credentials(stored: Any) -> dict:
    """Decrypt stored string kembali ke dict."""
    if stored is None:
        return {}
    # Jika sudah dict (lama, pre-encryption), return as-is
    if isinstance(stored, dict):
        return stored
    if not isinstance(stored, str):
        return {}
    f = _get_fernet()
    if f is None:
        # Mungkin plain JSON
        try:
            return json.loads(stored)
        except Exception:
            return {}
    try:
        return json.loads(f.decrypt(stored.encode()).decode())
    except Exception:
        # Mungkin plain JSON lama
        try:
            return json.loads(stored)
        except Exception:
            log.error("Gagal decrypt credentials — data mungkin korup")
            return {}
