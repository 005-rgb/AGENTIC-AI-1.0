---
name: Multi-Provider AI Pool
description: Arsitektur pool AI multi-provider (Gemini + Groq) dengan fallback otomatis dan bulk import key.
---

# Multi-Provider AI Pool

## Arsitektur
- `backend/core/ai_pool.py` — pool utama, singleton `ai_manager` (MultiProviderManager)
- `backend/core/gemini_pool.py` — wrapper backward-compat; `generate_with_retry()` → delegates ke `ai_pool.generate()`
- `backend/api/keys.py` — CRUD + `/bulk` endpoint; model `GeminiKey` tabel masih `gemini_keys` tapi sudah ada kolom `provider`

## Provider order
`PROVIDER_ORDER = ["gemini", "groq"]` — Gemini dicoba dulu, Groq fallback saat semua Gemini key 429.

## Model mapping
- gemini → `gemini-2.0-flash`
- groq   → `llama-3.3-70b-versatile`

## DB
- Tabel `gemini_keys`, kolom `provider VARCHAR DEFAULT 'gemini'`
- Kolom ditambah via `_migrate_db()` di `backend/main.py`

## Caller interface
Semua generator (script, text_to_shorts, trend_scout, competitor_spy) pakai `generate_with_retry(tenant_id, model, prompt)` — tidak perlu ubah signature.

**Why:** Satu interface untuk semua provider; failover transparan tanpa ubah business logic.

**How to apply:** Kalau tambah provider baru (OpenRouter, DeepSeek, dll): tambah entry di `PROVIDER_ORDER`, `PROVIDER_MODELS`, `PROVIDER_CALLERS` di ai_pool.py, dan opsi di select HTML frontend.
