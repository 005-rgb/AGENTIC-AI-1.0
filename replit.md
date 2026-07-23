# YouTube Shorts Factory — AGENTIC-AI-1.0

AI Agent otomatis untuk manajemen channel YouTube Shorts. Multi-tenant, multi-platform (YouTube, TikTok, Instagram/Meta).

## Stack

- **Backend**: FastAPI + SQLAlchemy + SQLite (`shortsdb.sqlite`)
- **Frontend**: Vanilla HTML/CSS/JS (static files served oleh FastAPI)
- **AI**: Google Gemini (`gemini-2.0-flash`) via rotasi key pool dengan retry 429 otomatis
- **TTS**: edge-tts (Microsoft, suara natural) → fallback gTTS → silent
- **Video**: moviepy + FFmpeg + yt-dlp
- **Scheduler**: APScheduler (5 background jobs)

## Cara Menjalankan

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 5000 --reload
```

Workflow sudah dikonfigurasi: **Start application**

## Fitur Utama

- Script generator berbasis niche (motivasi, edukasi, humor, fakta, dll.)
- Text-to-Shorts: generate video slide otomatis dari teks (Gemini + Pillow + edge-tts)
- Video processor: crop 9:16, hook overlay, subtitle, background music
- Trend scout & competitor spy (analisis via Gemini + yt-dlp)
- Multi-platform upload: YouTube, TikTok, Meta (Instagram/Facebook)
- Telegram & WhatsApp bot notifications
- Reseller / multi-tenant support
- A/B test judul video
- Gemini key pool: round-robin + retry otomatis saat 429

## Environment Secrets

| Secret | Keterangan |
|--------|-----------|
| `SESSION_SECRET` | ✅ Sudah di-set |
| `FERNET_KEY` | Enkripsi credentials (opsional, auto-plain jika kosong) |
| `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` | YouTube OAuth |
| `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET` | TikTok OAuth |
| `META_APP_ID` / `META_APP_SECRET` | Instagram/Facebook OAuth |
| `TELEGRAM_BOT_TOKEN` | Notifikasi Telegram |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | WhatsApp via Twilio |

## Database

SQLite lokal (`shortsdb.sqlite`). Migration otomatis via `_migrate_db()` di startup.
Tidak butuh PostgreSQL.

## Catatan Penting

- Semua Gemini key dari **project Google Cloud yang sama** berbagi quota. Buat key dari project berbeda agar rotasi benar-benar efektif.
- Pool retry otomatis: jika satu key 429, langsung coba key berikutnya.
- edge-tts butuh koneksi internet (Microsoft Azure TTS gratis).

## User Preferences

- Bahasa komunikasi: Indonesia
