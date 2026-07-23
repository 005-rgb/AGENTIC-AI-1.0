"""
Per-tenant Gemini API key pool with round-robin rotation and 429-retry.
Each tenant has an isolated pool derived from their stored GeminiKey records.
"""
import logging
import threading
import time
from datetime import datetime
from typing import Optional

try:
    import google.generativeai as genai   # legacy SDK still works
except ImportError:
    genai = None  # type: ignore

log = logging.getLogger(__name__)


class TenantKeyPool:
    """Round-robin key rotator for a single tenant."""

    def __init__(self, keys: list[str]):
        self._keys = list(keys)
        self._index = 0
        self._lock = threading.Lock()

    def next_key(self) -> Optional[str]:
        if not self._keys:
            return None
        with self._lock:
            key = self._keys[self._index % len(self._keys)]
            self._index += 1
        return key

    def all_keys(self) -> list[str]:
        with self._lock:
            return list(self._keys)

    def add_key(self, key: str):
        with self._lock:
            if key not in self._keys:
                self._keys.append(key)

    def remove_key(self, key: str):
        with self._lock:
            self._keys = [k for k in self._keys if k != key]

    @property
    def count(self) -> int:
        return len(self._keys)


class PoolManager:
    """Global registry of per-tenant key pools."""

    def __init__(self):
        self._pools: dict[str, TenantKeyPool] = {}
        self._lock = threading.Lock()

    def get_pool(self, tenant_id: str) -> Optional[TenantKeyPool]:
        with self._lock:
            return self._pools.get(tenant_id)

    def set_pool(self, tenant_id: str, keys: list[str]) -> TenantKeyPool:
        pool = TenantKeyPool(keys)
        with self._lock:
            self._pools[tenant_id] = pool
        return pool

    def add_key(self, tenant_id: str, key: str):
        with self._lock:
            if tenant_id not in self._pools:
                self._pools[tenant_id] = TenantKeyPool([])
            self._pools[tenant_id].add_key(key)

    def remove_key(self, tenant_id: str, key: str):
        with self._lock:
            if tenant_id in self._pools:
                self._pools[tenant_id].remove_key(key)

    def delete_tenant_pool(self, tenant_id: str):
        with self._lock:
            self._pools.pop(tenant_id, None)

    def next_key(self, tenant_id: str) -> Optional[str]:
        pool = self.get_pool(tenant_id)
        return pool.next_key() if pool else None


# Singleton
pool_manager = PoolManager()


def generate_with_retry(tenant_id: str, model_name: str, prompt: str, max_retries: int = None):  # noqa: ARG001
    """
    Delegates to multi-provider ai_pool.generate() which handles
    Gemini → Groq fallback automatically.
    Kept for backward compatibility with existing callers.
    """
    from backend.core.ai_pool import generate as _ai_generate
    return _ai_generate(tenant_id, prompt)


def get_genai_client(tenant_id: str):
    """Return a configured genai module using the next key for this tenant.
    Kept for backward compatibility — prefer generate_with_retry for new code."""
    key = pool_manager.next_key(tenant_id)
    if not key:
        raise RuntimeError(f"No Gemini API keys configured for tenant {tenant_id}")
    genai.configure(api_key=key)
    return genai


def load_tenant_keys_from_db(db, tenant_id: str):
    """Sync active AI keys from DB into all provider pools.
    Delegates to ai_pool.load_from_db and also keeps legacy gemini-only pool in sync."""
    from backend.core.ai_pool import load_from_db as _ai_load
    summary = _ai_load(db, tenant_id)
    # Also keep legacy pool_manager in sync (for any code that still calls next_key)
    from backend.models.models import GeminiKey
    keys = (
        db.query(GeminiKey)
        .filter(GeminiKey.tenant_id == tenant_id, GeminiKey.is_active == True)
        .all()
    )
    gemini_keys = [k.api_key for k in keys if (getattr(k, "provider", "gemini") or "gemini") == "gemini"]
    pool_manager.set_pool(tenant_id, gemini_keys)
    return gemini_keys
