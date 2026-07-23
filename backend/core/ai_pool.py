"""
Multi-provider AI pool — Gemini → Groq fallback.
Round-robin within each provider; pada 429/quota exhausted otomatis pindah ke provider berikutnya.

Provider order: gemini → groq
Model mapping:
  gemini  → gemini-2.0-flash
  groq    → llama-3.3-70b-versatile
"""
import logging
import threading
import time
from typing import Optional

log = logging.getLogger(__name__)

PROVIDER_ORDER = ["gemini", "groq"]

PROVIDER_MODELS = {
    "gemini": "gemini-2.0-flash",
    "groq":   "llama-3.3-70b-versatile",
}

# ── Per-provider key pool ─────────────────────────────────────────────────────

class KeyPool:
    def __init__(self, provider: str, keys: list[str]):
        self.provider = provider
        self._keys: list[str] = list(keys)
        self._index = 0
        self._lock = threading.Lock()

    def next_key(self) -> Optional[str]:
        with self._lock:
            if not self._keys:
                return None
            key = self._keys[self._index % len(self._keys)]
            self._index += 1
            return key

    def all_keys(self) -> list[str]:
        with self._lock:
            return list(self._keys)

    def add(self, key: str):
        with self._lock:
            if key not in self._keys:
                self._keys.append(key)

    def remove(self, key: str):
        with self._lock:
            self._keys = [k for k in self._keys if k != key]

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._keys)


# ── Tenant-scoped multi-provider manager ─────────────────────────────────────

class MultiProviderManager:
    def __init__(self):
        # {tenant_id: {provider: KeyPool}}
        self._tenants: dict[str, dict[str, KeyPool]] = {}
        self._lock = threading.Lock()

    def _ensure_tenant(self, tenant_id: str):
        if tenant_id not in self._tenants:
            self._tenants[tenant_id] = {p: KeyPool(p, []) for p in PROVIDER_ORDER}

    def set_keys(self, tenant_id: str, provider: str, keys: list[str]):
        with self._lock:
            self._ensure_tenant(tenant_id)
            self._tenants[tenant_id][provider] = KeyPool(provider, keys)

    def add_key(self, tenant_id: str, provider: str, key: str):
        with self._lock:
            self._ensure_tenant(tenant_id)
            self._tenants[tenant_id][provider].add(key)

    def remove_key(self, tenant_id: str, provider: str, key: str):
        with self._lock:
            if tenant_id in self._tenants:
                self._tenants[tenant_id].get(provider, KeyPool(provider, [])).remove(key)

    def delete_tenant(self, tenant_id: str):
        with self._lock:
            self._tenants.pop(tenant_id, None)

    def pool_for(self, tenant_id: str, provider: str) -> Optional[KeyPool]:
        with self._lock:
            return self._tenants.get(tenant_id, {}).get(provider)

    def summary(self, tenant_id: str) -> dict:
        with self._lock:
            pools = self._tenants.get(tenant_id, {})
            return {p: pools[p].count if p in pools else 0 for p in PROVIDER_ORDER}


# Singleton
ai_manager = MultiProviderManager()


# ── Core generate function ────────────────────────────────────────────────────

def _call_gemini(key: str, model: str, prompt: str):
    import google.generativeai as genai
    genai.configure(api_key=key)
    m = genai.GenerativeModel(model)
    return m.generate_content(prompt)


def _call_groq(key: str, model: str, prompt: str):
    from groq import Groq
    client = Groq(api_key=key)
    chat = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=4096,
    )
    # Wrap to match genai response interface (.text)
    return _GroqResponse(chat.choices[0].message.content)


class _GroqResponse:
    """Thin wrapper so callers can use .text just like Gemini responses."""
    def __init__(self, text: str):
        self.text = text


PROVIDER_CALLERS = {
    "gemini": _call_gemini,
    "groq":   _call_groq,
}


def generate(tenant_id: str, prompt: str, preferred_model: Optional[str] = None) -> "_GroqResponse":
    """
    Generate text using the multi-provider pool.
    Tries PROVIDER_ORDER in sequence; skips a provider if it has no keys.
    Within each provider, tries all keys before moving on.
    Raises RuntimeError only when every provider+key combination is exhausted.
    """
    errors = []

    for provider in PROVIDER_ORDER:
        pool = ai_manager.pool_for(tenant_id, provider)
        if not pool or pool.count == 0:
            continue

        model = PROVIDER_MODELS[provider]
        caller = PROVIDER_CALLERS[provider]
        keys = pool.all_keys()
        tried: set[str] = set()

        for attempt in range(len(keys)):
            key = pool.next_key()
            if not key or key in tried:
                remaining = [k for k in keys if k not in tried]
                if not remaining:
                    break
                key = remaining[0]
            tried.add(key)

            try:
                resp = caller(key, model, prompt)
                log.debug("AI generate OK — provider=%s model=%s key=...%s", provider, model, key[-6:])
                return resp
            except Exception as e:
                err_str = str(e).lower()
                is_quota = any(x in err_str for x in ("429", "quota", "rate_limit", "resource_exhausted", "rate limit"))
                if is_quota:
                    log.warning(
                        "Provider %s key ...%s quota/429 (attempt %d/%d) — rotating",
                        provider, key[-6:], attempt + 1, len(keys),
                    )
                    errors.append(f"{provider}:...{key[-6:]}: 429/quota")
                    if attempt < len(keys) - 1:
                        time.sleep(0.3)
                    continue
                # Non-quota: re-raise immediately (bug, bad key format, etc.)
                raise

        log.warning("Provider %s exhausted all %d key(s), falling back to next provider", provider, len(keys))

    raise RuntimeError(
        f"Semua provider AI habis quota untuk tenant {tenant_id}. "
        f"Detail: {'; '.join(errors) if errors else 'tidak ada key aktif'}. "
        "Tambahkan key baru atau tunggu quota reset."
    )


def load_from_db(db, tenant_id: str):
    """Sync all active AI keys from DB into in-memory pools."""
    from backend.models.models import GeminiKey
    keys = (
        db.query(GeminiKey)
        .filter(GeminiKey.tenant_id == tenant_id, GeminiKey.is_active == True)
        .all()
    )
    # Group by provider
    by_provider: dict[str, list[str]] = {p: [] for p in PROVIDER_ORDER}
    for k in keys:
        p = getattr(k, "provider", "gemini") or "gemini"
        if p in by_provider:
            by_provider[p].append(k.api_key)

    for provider, key_list in by_provider.items():
        ai_manager.set_keys(tenant_id, provider, key_list)

    return {p: len(v) for p, v in by_provider.items()}
