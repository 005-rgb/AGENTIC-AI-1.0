# YouTube Shorts Factory SaaS

Platform otomasi produksi dan distribusi YouTube Shorts berbasis AI — multi-tenant SaaS.

## Stack
- **Backend**: Python 3.12, FastAPI, Uvicorn
- **Database**: SQLite (dev) / MySQL (cPanel prod) via SQLAlchemy
- **AI**: Google Gemini API (gemini-2.0-flash)
- **Video**: FFmpeg, MoviePy, yt-dlp
- **Frontend**: Vanilla SPA (HTML/CSS/JS)
- **Scheduler**: APScheduler BackgroundScheduler (5 jobs)
- **Enkripsi**: Fernet symmetric encryption untuk credentials

## Cara Menjalankan di Replit

Workflow **Start application** sudah dikonfigurasi. Cukup klik tombol Run.

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 5000 --reload
```

Akses: port 5000 (mapped ke port 80 via Replit proxy)

### Setup awal di Replit
1. `SESSION_SECRET` sudah tersedia sebagai Replit Secret — tidak perlu `.env`
2. Dependencies diinstal otomatis via `pip install -r requirements.txt`
3. Database SQLite (`shortsdb.sqlite`) dibuat + dimigrate otomatis saat startup
4. Untuk fitur AI: tambahkan Gemini API key via UI → Settings → Gemini Keys
5. Untuk upload YouTube: set `YOUTUBE_CLIENT_ID` dan `YOUTUBE_CLIENT_SECRET` sebagai Replit Secrets
6. Untuk enkripsi credentials: set `FERNET_KEY` sebagai Replit Secret (generate dengan `from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())`)
7. Untuk TikTok upload: set `TIKTOK_CLIENT_KEY` dan `TIKTOK_CLIENT_SECRET`
8. Untuk Instagram/Facebook: set `META_APP_ID` dan `META_APP_SECRET`

## Cara Menjalankan di Laragon (Windows)

```bash
cd C:\laragon\www\shorts-factory
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # edit sesuai kebutuhan
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

## Cara Deploy di cPanel

1. Upload file ke `/home/user/shorts-factory/`
2. Di cPanel → Python App Manager → buat app baru
3. Via SSH: `pip install -r requirements.txt && cp .env.example .env`
4. Restart app dari cPanel

## Struktur Utama

```
backend/
  main.py               — FastAPI app + routing + rate limit + migration
  core/
    config.py           — settings (env vars)
    database.py         — SQLAlchemy engine + session
    deps.py             — FastAPI dependency: get_current_tenant
    encryption.py       — Fernet encrypt/decrypt untuk credentials
    plan_limits.py      — Plan limits: free/pro/enterprise
    security.py         — JWT + bcrypt
    gemini_pool.py      — Gemini API key rotation
  api/                  — REST endpoints (auth, keys, channels, jobs, dll)
  models/models.py      — SQLAlchemy ORM models
  modules/
    video_processor/    — crop 9:16, subtitle, hook, musik
    script_generator/   — AI script generation per niche
    text_to_shorts/     — Pillow + gTTS slide-based video
    trend_scout/        — trend research via Gemini
    hook_library/       — hook templates + seed
    youtube_uploader/   — OAuth2 + resumable upload + A/B variant B
    multi_platform/     — FFmpeg re-encode + TikTok/Meta upload
    tiktok/             — TikTok Content Posting API v2
    meta/               — Meta Graph API (Instagram Reels + Facebook Reels)
    scheduler/          — 5 APScheduler jobs
    competitor_spy/     — yt-dlp + Gemini competitor analysis
    bot/                — Telegram FSM + WhatsApp Twilio
    reseller/           — multi-tenant reseller management
frontend/
  index.html            — SPA dashboard
  css/app.css
  js/app.js
```

## Scheduler Jobs (5)

| Job | Interval | Fungsi |
|-----|----------|--------|
| check_pending_jobs | 30s | Proses video pending |
| check_scheduled_uploads | 60s | Upload terjadwal ke semua platform |
| check_ab_test_results | 30m | Evaluasi A/B test setelah 48h |
| analyze_best_hours | 6h | Update jam terbaik upload per channel |
| cleanup_old_files | daily 03:00 | Hapus temp/platform exports lama |

## Plan Limits

| Feature | Free | Pro | Enterprise |
|---------|------|-----|------------|
| Channels | 3 | 15 | unlimited |
| Gemini keys | 5 | 30 | 50 |
| Jobs/hari | 10 | 100 | unlimited |
| A/B Test | ❌ | ✅ | ✅ |
| Multi-platform | ❌ | ✅ | ✅ |
| Competitor Spy | ❌ | ✅ | ✅ |
| Rate limit/menit | 20 | 60 | 300 |

## API Endpoints Utama

- `POST /api/auth/register` — daftar tenant
- `POST /api/auth/login` — login, dapat JWT
- `GET/POST /api/keys` — Gemini key management
- `GET/POST /api/channels` — channel management
- `GET/{id}/oauth-url` — YouTube OAuth
- `GET/{id}/tiktok-oauth-url` — TikTok OAuth
- `GET/{id}/meta-oauth-url` — Meta OAuth (Instagram/Facebook)
- `POST /api/jobs` — buat job (multipart)
- `POST /api/jobs/json` — buat job (JSON)
- `POST /api/jobs/{id}/upload-now` — upload manual
- `POST /api/jobs/{id}/ab-test/start` — mulai A/B test
- `GET /api/jobs/{id}/ab-test/result` — hasil A/B test
- `GET /api/health` — health check
- `GET /api/plans` — info plan limits

## Environment Variables

Lihat `.env.example` untuk daftar lengkap. Minimal:
- `SESSION_SECRET` — JWT signing key (sudah ada sebagai Replit Secret)

Optional untuk fitur penuh:
- `FERNET_KEY` — enkripsi credentials (generate dengan Fernet.generate_key())
- `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` — YouTube OAuth
- `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` — TikTok upload
- `META_APP_ID`, `META_APP_SECRET` — Instagram/Facebook upload
- `TELEGRAM_BOT_TOKEN` — Telegram bot
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` — WhatsApp bot

## Build Status

| Phase | Status |
|-------|--------|
| Phase 1: Foundation | ✅ Selesai |
| Phase 2: AI Features | ✅ Selesai |
| Phase 3: Multi-Platform & A/B | ✅ Selesai |
| Phase 4: Bot & Competitor Spy | ✅ Selesai |
| Phase 5: Reseller + Hardening | ✅ Selesai |
| Phase 6: Production Hardening | ✅ Selesai |

## User Preferences

- Bahasa komunikasi: Bahasa Indonesia
- Target deployment: cPanel dan Laragon (bukan Docker/cloud)
- Database: SQLite untuk dev, MySQL untuk prod
- No billing di fase awal
