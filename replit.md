# YouTube Shorts Factory SaaS

Platform otomasi produksi dan distribusi YouTube Shorts berbasis AI — multi-tenant SaaS.

## Stack
- **Backend**: Python 3.13, FastAPI, Uvicorn
- **Database**: SQLite (dev) / MySQL (cPanel prod) via SQLAlchemy
- **AI**: Google Gemini API (gemini-2.0-flash)
- **Video**: FFmpeg, MoviePy, yt-dlp
- **Frontend**: Vanilla SPA (HTML/CSS/JS)
- **Scheduler**: APScheduler BackgroundScheduler

## Cara Menjalankan (Replit / Lokal)

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 5000 --reload
```

Akses: http://localhost:5000

## Cara Menjalankan di Laragon (Windows)

```bash
cd C:\laragon\www\shorts-factory
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # edit sesuai kebutuhan
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Akses: http://localhost:8000

## Cara Deploy di cPanel

1. Upload file ke `/home/user/shorts-factory/`
2. Di cPanel → Python App Manager → buat app baru:
   - Application root: `shorts-factory`
   - Startup file: `passenger_wsgi.py`
   - Python: 3.11+
3. Via SSH:
   ```bash
   source virtualenv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env   # isi DATABASE_URL MySQL
   ```
4. Restart app dari cPanel
5. (Opsional) Tambah cron job: `* * * * * python worker.py`

## Struktur Utama

```
backend/
  main.py          — FastAPI app + routing
  core/            — config, db, security, gemini pool
  api/             — REST endpoints
  models/          — SQLAlchemy models
  modules/         — video processor, script gen, scheduler, dll
frontend/
  index.html       — SPA dashboard
  css/app.css
  js/app.js
storage/           — file uploads, output, temp (auto-created)
passenger_wsgi.py  — cPanel entry point
worker.py          — standalone background worker
PRD.md             — Product Requirements Document lengkap
```

## Environment Variables

Lihat `.env.example` untuk daftar lengkap. Minimal:
- `SESSION_SECRET` — JWT signing key

## Build Phases

Lihat `PRD.md` section 17 untuk roadmap lengkap 6 phase.

## User Preferences

- Bahasa komunikasi: Bahasa Indonesia
- Target deployment: cPanel dan Laragon (bukan Docker/cloud)
- Database: SQLite untuk dev, MySQL untuk prod
- No billing di fase awal
