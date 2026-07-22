# PRD — YouTube Shorts Factory SaaS
**Version:** 1.0.0  
**Date:** 2026-07-22  
**Status:** Active  
**Audience:** Engineering, Product, QA

---

## 1. Overview

YouTube Shorts Factory adalah platform SaaS **multi-tenant** yang mengotomasi seluruh pipeline produksi dan distribusi konten YouTube Shorts — mulai dari riset tren, penulisan skrip AI, pemrosesan video, hingga upload terjadwal ke YouTube. Platform ini memanfaatkan rotasi **50 Gemini API key** per-tenant untuk bypass rate limit dan parallelism tinggi.

---

## 2. Goals & Non-Goals

### Goals
| # | Goal |
|---|------|
| G1 | Tenant dapat mendaftar, login, dan mengelola akun secara mandiri |
| G2 | Tenant dapat mendaftarkan hingga 50 Gemini API key yang berputar otomatis |
| G3 | Tenant dapat memproses video (crop 9:16, subtitle, hook text, musik) |
| G4 | Tenant dapat membuat skrip Shorts berbasis niche dengan AI |
| G5 | Tenant dapat menghubungkan channel YouTube via OAuth dan upload otomatis |
| G6 | Tenant dapat menjadwalkan upload di jam prime time |
| G7 | Tenant dapat memantau performa video (views, CTR, likes) di dashboard |
| G8 | Isolasi data antar tenant penuh (tidak ada kebocoran lintas tenant) |
| G9 | Background worker memproses antrian job secara async |

### Non-Goals (v1.0)
- Billing / payment gateway
- Mobile app (iOS/Android)
- Video generation dari teks murni (tanpa footage)
- Multi-bahasa UI (hanya Bahasa Indonesia & English)

---

## 3. User Personas

### 3.1 Content Creator Solo
- Punya 1–3 channel YouTube Shorts
- Ingin hemat waktu editing dan riset
- Tidak paham coding, butuh UI yang simpel

### 3.2 Agensi Konten
- Kelola 10–50 channel untuk klien berbeda
- Butuh multi-channel management dalam 1 akun
- Prioritas: bulk processing, scheduling, analytics

### 3.3 Developer / Power User
- Akses via API langsung
- Butuh dokumentasi endpoint yang jelas
- Mau integrasi dengan tools eksternal (n8n, Zapier)

---

## 4. Tech Stack

| Layer | Teknologi |
|-------|-----------|
| **Backend** | Python 3.13, FastAPI, Uvicorn |
| **Database** | SQLite (dev) / PostgreSQL (prod) via SQLAlchemy |
| **Auth** | JWT (python-jose), bcrypt |
| **AI** | Google Gemini API (`gemini-2.0-flash`, `gemini-1.5-flash`) |
| **Video** | FFmpeg (system), MoviePy |
| **Download** | yt-dlp |
| **Scheduler** | APScheduler (BackgroundScheduler) |
| **Frontend** | Vanilla HTML/CSS/JS SPA (served dari FastAPI) |
| **Storage** | Filesystem lokal `storage/{tenant_id}/` |
| **Queue** | In-memory job queue + DB status tracking |

---

## 5. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND (SPA)                        │
│   Dashboard · Jobs · Channels · Keys · Settings         │
└───────────────────────┬─────────────────────────────────┘
                        │ REST API (JSON)
┌───────────────────────▼─────────────────────────────────┐
│                  FastAPI Backend                         │
│                                                          │
│  /api/auth/*      Auth (register, login, me)            │
│  /api/keys/*      Gemini key CRUD                       │
│  /api/channels/*  YouTube channel management            │
│  /api/jobs/*      Video job CRUD + trigger              │
│  /api/trends/*    Trend scouting                        │
│  /api/analytics/* YouTube analytics                     │
│  /api/admin/*     Admin (super user only)               │
└──┬──────────────┬──────────────┬──────────────┬─────────┘
   │              │              │              │
   ▼              ▼              ▼              ▼
GeminiPool   VideoProcessor  YouTubeUploader  Scheduler
(per-tenant  (FFmpeg/MoviePy) (OAuth v3)    (APScheduler)
 key rotation)
   │
   ▼
TenantKeyPool[tenant_id] → round-robin rotation
```

---

## 6. Data Models

### 6.1 Tenant
```
tenants
├── id              UUID PK
├── email           String UNIQUE NOT NULL
├── hashed_password String NOT NULL
├── name            String NOT NULL
├── plan            Enum(free|pro|enterprise) DEFAULT free
├── is_active       Boolean DEFAULT true
└── created_at      DateTime
```

### 6.2 GeminiKey
```
gemini_keys
├── id           UUID PK
├── tenant_id    FK → tenants.id
├── api_key      String NOT NULL
├── label        String (deskripsi opsional)
├── is_active    Boolean DEFAULT true
├── usage_count  Integer DEFAULT 0
├── last_used_at DateTime nullable
└── created_at   DateTime
```

### 6.3 Channel
```
channels
├── id                   UUID PK
├── tenant_id            FK → tenants.id
├── channel_name         String NOT NULL
├── niche                String NOT NULL  [motivasi|edukasi|humor|fakta|tutorial|lifestyle|finance|kesehatan|teknologi|lainnya]
├── youtube_credentials  JSON nullable    {access_token, refresh_token, expiry}
├── is_active            Boolean DEFAULT true
└── created_at           DateTime
```

### 6.4 VideoJob
```
video_jobs
├── id                UUID PK
├── tenant_id         FK → tenants.id
├── channel_id        FK → channels.id nullable
├── source_type       Enum(upload|url|ai_generate)
├── source_url        String nullable
├── source_filename   String nullable
├── niche             String nullable
├── title             String nullable
├── description       Text nullable
├── tags              JSON  []
├── add_subtitles     Boolean DEFAULT true
├── add_music         Boolean DEFAULT false
├── hook_text         String nullable
├── output_filename   String nullable
├── script            Text nullable
├── thumbnail_filename String nullable
├── status            Enum(pending|processing|done|failed|scheduled|uploaded)
├── error_message     Text nullable
├── progress          Float 0.0–100.0
├── scheduled_at      DateTime nullable
├── uploaded_at       DateTime nullable
├── youtube_video_id  String nullable
├── created_at        DateTime
└── updated_at        DateTime
```

---

## 7. API Specification

### 7.1 Auth

#### POST /api/auth/register
**Body:**
```json
{
  "email": "user@example.com",
  "password": "min8chars",
  "name": "Creator Name"
}
```
**Response 201:**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "tenant": { "id": "...", "email": "...", "name": "...", "plan": "free" }
}
```
**Errors:** 409 email sudah terdaftar, 422 validasi

---

#### POST /api/auth/login
**Body (form-data):** `username`, `password`  
**Response 200:** sama dengan register  
**Errors:** 401 credentials salah

---

#### GET /api/auth/me
**Header:** `Authorization: Bearer <token>`  
**Response 200:**
```json
{
  "id": "...", "email": "...", "name": "...", "plan": "free", "created_at": "..."
}
```

---

### 7.2 Gemini Keys

#### GET /api/keys
**Response 200:**
```json
{
  "keys": [
    { "id": "...", "label": "Key utama", "api_key": "AIza***masked***", "is_active": true, "usage_count": 42, "last_used_at": "..." }
  ],
  "total": 1,
  "pool_size": 1
}
```
> api_key selalu di-mask: tampilkan 8 karakter pertama + `***masked***`

---

#### POST /api/keys
**Body:**
```json
{ "api_key": "AIzaSy...", "label": "Key produksi" }
```
**Response 201:** `{ "id": "...", "label": "...", "api_key": "AIzaSy***masked***", "is_active": true }`  
**Errors:** 400 jika key duplikat, 422 validasi

---

#### DELETE /api/keys/{key_id}
**Response 204:** No Content  
**Errors:** 404 key tidak ditemukan

---

#### POST /api/keys/{key_id}/toggle
**Response 200:** `{ "id": "...", "is_active": false }`

---

#### POST /api/keys/test
**Body:** `{ "api_key": "AIzaSy..." }`  
**Response 200:** `{ "valid": true, "model": "gemini-2.0-flash" }`  
**Response 200:** `{ "valid": false, "error": "API key tidak valid" }`

---

### 7.3 Channels

#### GET /api/channels
**Response 200:**
```json
{
  "channels": [
    { "id": "...", "channel_name": "Motivasi Harian", "niche": "motivasi", "is_active": true, "has_youtube_auth": false }
  ]
}
```

---

#### POST /api/channels
**Body:**
```json
{ "channel_name": "Motivasi Harian", "niche": "motivasi" }
```
**Response 201:** `{ "id": "...", "channel_name": "...", "niche": "...", "is_active": true }`

---

#### DELETE /api/channels/{channel_id}
**Response 204**

---

#### GET /api/channels/{channel_id}/oauth-url
**Response 200:** `{ "auth_url": "https://accounts.google.com/o/oauth2/..." }`  
> Membuat URL Google OAuth untuk consent screen YouTube

---

#### POST /api/channels/{channel_id}/oauth-callback
**Body:** `{ "code": "4/0A..." }`  
**Response 200:** `{ "success": true, "channel_name": "My YT Channel" }`

---

### 7.4 Video Jobs

#### GET /api/jobs
**Query params:** `status`, `channel_id`, `page` (default 1), `limit` (default 20)  
**Response 200:**
```json
{
  "jobs": [...],
  "total": 100,
  "page": 1,
  "limit": 20
}
```

---

#### POST /api/jobs
**Content-Type:** `multipart/form-data` ATAU `application/json`

**Skenario 1 — Upload file:**
```
source_type=upload
file=<binary>
niche=motivasi
add_subtitles=true
hook_text=Fakta mengejutkan!
channel_id=<uuid>
scheduled_at=2026-07-23T08:00:00Z   (opsional)
```

**Skenario 2 — URL (YouTube/TikTok/dll):**
```json
{
  "source_type": "url",
  "source_url": "https://youtube.com/watch?v=xxx",
  "niche": "edukasi",
  "add_subtitles": true,
  "channel_id": "..."
}
```

**Skenario 3 — AI Generate (tanpa footage):**
```json
{
  "source_type": "ai_generate",
  "niche": "fakta",
  "hook_text": "5 Fakta Mengejutkan Tentang Otak",
  "add_subtitles": true
}
```

**Response 201:**
```json
{ "job_id": "...", "status": "pending", "message": "Job diterima, sedang diproses" }
```

---

#### GET /api/jobs/{job_id}
**Response 200:**
```json
{
  "id": "...",
  "status": "processing",
  "progress": 45.0,
  "title": "...",
  "script": "...",
  "output_filename": "...",
  "youtube_video_id": null,
  "error_message": null,
  "created_at": "..."
}
```

---

#### DELETE /api/jobs/{job_id}
**Response 204**

---

#### POST /api/jobs/{job_id}/upload-now
> Upload segera ke YouTube (tanpa menunggu jadwal)  
**Response 200:** `{ "success": true, "youtube_video_id": "abc123" }`

---

#### GET /api/jobs/{job_id}/download
> Download file output video  
**Response:** `StreamingResponse` dengan header `Content-Disposition: attachment`

---

### 7.5 Trends

#### GET /api/trends
**Query params:** `niche` (required), `limit` (default 10)  
**Response 200:**
```json
{
  "niche": "motivasi",
  "trends": [
    { "topic": "Kebiasaan Pagi Orang Sukses", "score": 95, "suggested_hook": "Jam 5 pagi orang sukses sudah..." }
  ]
}
```

---

#### POST /api/trends/generate-script
**Body:**
```json
{ "topic": "Kebiasaan Pagi Orang Sukses", "niche": "motivasi", "duration_seconds": 45 }
```
**Response 200:**
```json
{
  "script": "Hook: Jam 5 pagi orang sukses sudah...\n\nIsi: ...\n\nCTA: Follow untuk tips sukses lainnya!",
  "title": "5 Kebiasaan Pagi yang Mengubah Hidupku",
  "description": "...",
  "tags": ["motivasi", "sukses", "kebiasaan"]
}
```

---

### 7.6 Analytics

#### GET /api/analytics/{channel_id}
**Query params:** `days` (default 30)  
**Response 200:**
```json
{
  "channel_id": "...",
  "period_days": 30,
  "summary": { "total_views": 150000, "total_videos": 45, "avg_ctr": 8.2 },
  "videos": [
    { "youtube_video_id": "...", "title": "...", "views": 25000, "likes": 1200, "ctr": 9.5 }
  ]
}
```

---

## 8. Module Specifications

### 8.1 GeminiPool (backend/core/gemini_pool.py)

**Prinsip:**
- Setiap tenant memiliki `TenantKeyPool` yang **terisolasi**
- Rotasi round-robin thread-safe menggunakan `threading.Lock`
- `pool_manager` adalah singleton global
- Saat key DB berubah (add/remove/toggle), pool di-resync via `load_tenant_keys_from_db()`

**TenantKeyPool methods:**
- `next_key()` → str | None (thread-safe)
- `add_key(key)` 
- `remove_key(key)`
- `count` property

**PoolManager methods:**
- `get_pool(tenant_id)` → TenantKeyPool | None
- `set_pool(tenant_id, keys)` → TenantKeyPool
- `add_key(tenant_id, key)`
- `remove_key(tenant_id, key)`
- `next_key(tenant_id)` → str | None
- `delete_tenant_pool(tenant_id)`

**Helper:**
- `get_genai_client(tenant_id)` → configured `google.generativeai` module
- `load_tenant_keys_from_db(db, tenant_id)` → syncs DB keys into pool

---

### 8.2 VideoProcessor (backend/modules/video_processor/)

**File:** `processor.py`

**Pipeline per job:**
1. **Download/copy** — jika `source_url`, pakai `yt-dlp`; jika `upload`, file sudah ada di `storage/{tid}/uploads/`
2. **Probe** — baca metadata (durasi, resolusi, fps) via `ffprobe`
3. **Crop 9:16** — FFmpeg filter: `crop=ih*9/16:ih` + scale ke `1080x1920`
4. **Subtitles** — kirim frame ke Gemini Vision → transkripsi → burn SRT via FFmpeg `subtitles=` filter (teks besar, bold, tengah layar)
5. **Hook Overlay** — jika `hook_text`, tambah teks animated di 0–3 detik (FFmpeg `drawtext`)
6. **Background Music** — jika `add_music`, mix audio dari `storage/shared/music/` (royalty-free)
7. **Output** — simpan ke `storage/{tid}/output/{job_id}.mp4`
8. **Thumbnail** — ekstrak frame terbaik, kirim ke Gemini untuk pilih + caption

**Progress callback:**
- Update `job.progress` di DB setiap langkah (0→20→40→60→80→100)

**FFmpeg command patterns:**
```bash
# Step 3 — Crop & scale
ffmpeg -i input.mp4 -vf "crop=ih*9/16:ih,scale=1080:1920" -c:a copy output_cropped.mp4

# Step 5 — Hook text overlay
ffmpeg -i cropped.mp4 -vf "drawtext=text='HOOK TEXT':fontsize=72:fontcolor=white:x=(w-text_w)/2:y=h*0.15:enable='between(t,0,3)':borderw=3:bordercolor=black" output_hook.mp4

# Step 4 — Burn subtitles
ffmpeg -i hook.mp4 -vf "subtitles=subs.srt:force_style='FontSize=28,Bold=1,Alignment=2'" output_final.mp4

# Step 6 — Mix music (volume ducking)
ffmpeg -i video.mp4 -i music.mp3 -filter_complex "[1:a]volume=0.15[music];[0:a][music]amix=inputs=2:duration=first" final.mp4
```

---

### 8.3 ScriptGenerator (backend/modules/script_generator/)

**File:** `generator.py`

**Prompt template per niche:**
```
Kamu adalah scriptwriter ahli YouTube Shorts niche {niche}.
Buat skrip video berdurasi {duration} detik dengan struktur:
1. HOOK (0-3 detik): kalimat pembuka yang memancing rasa ingin tahu
2. ISI (4-{mid} detik): {point_count} poin utama, singkat dan padat
3. CTA (akhir): ajak subscribe/like/follow

Topik: {topic}
Gaya bahasa: santai, energik, mudah dipahami
Output JSON: {"hook": "...", "body": ["poin1", "poin2"], "cta": "...", "full_script": "...", "title": "...", "description": "...", "tags": [...]}
```

**Niche-specific behavior:**
| Niche | Model | Tone | Duration |
|-------|-------|------|----------|
| motivasi | gemini-2.0-flash | inspiratif | 45–60s |
| edukasi | gemini-2.0-flash | informatif | 50–60s |
| humor | gemini-1.5-flash | santai, lucu | 30–45s |
| fakta | gemini-2.0-flash | mengejutkan | 40–55s |
| tutorial | gemini-2.0-flash | step-by-step | 55–60s |
| lifestyle | gemini-1.5-flash | casual | 35–50s |
| finance | gemini-2.0-flash | serius tapi simpel | 50–60s |
| kesehatan | gemini-2.0-flash | informatif | 45–55s |
| teknologi | gemini-2.0-flash | exciting | 40–55s |

---

### 8.4 TrendScout (backend/modules/trend_scout/)

**File:** `scout.py`

**Method:** `get_trends(tenant_id, niche, limit) → list[TrendItem]`

**Implementation:**
1. Minta Gemini untuk generate daftar topik trending berdasarkan niche (dengan konteks waktu saat ini)
2. Beri skor relevansi 0–100
3. Generate suggested hook untuk tiap topik

**Prompt:**
```
Hari ini {date}. Buat daftar {limit} topik trending untuk YouTube Shorts niche "{niche}" yang berpotensi viral di Indonesia.
Untuk setiap topik berikan:
- topic: judul topik
- score: skor viralitas 0-100
- suggested_hook: kalimat pembuka yang menarik (max 15 kata)
Output JSON array.
```

---

### 8.5 YouTubeUploader (backend/modules/youtube_uploader/)

**File:** `uploader.py`

**OAuth Flow:**
1. `get_oauth_url(channel_id)` → redirect URL ke Google consent screen
   - Scope: `youtube.upload`, `youtube.readonly`, `youtube`, `youtube.force-ssl`
2. `handle_callback(channel_id, code, db)` → tukar code dengan token, simpan ke `channel.youtube_credentials`
3. `refresh_token_if_needed(channel)` → cek expiry, auto-refresh jika perlu

**Upload:**
```python
def upload_video(job, channel, db) -> str:
    # Returns youtube_video_id
    # Uses googleapiclient.discovery + httplib2
    # Resumable upload untuk file besar
    # Set title, description, tags, categoryId=22 (People & Blogs), privacyStatus=public
```

**Metadata mapping:**
```
title       = job.title (max 100 chars)
description = job.description + "\n\n#Shorts"
tags        = job.tags + ["shorts", "ytshorts"]
category    = 22 (People & Blogs) untuk semua niche
privacyStatus = "public"
madeForKids = false
```

---

### 8.6 Scheduler (backend/modules/scheduler/)

**File:** `scheduler.py`

**Uses:** `APScheduler.BackgroundScheduler`

**Jobs terdaftar:**
1. `check_pending_jobs` — setiap 30 detik: ambil job `status=pending`, trigger processing
2. `check_scheduled_uploads` — setiap 1 menit: cek job `status=scheduled` dan `scheduled_at <= now()`, trigger upload
3. `cleanup_old_files` — setiap hari jam 03:00: hapus file temp lebih dari 7 hari

**Prime time slots (WIB, UTC+7):**
```
07:00, 12:00, 16:00, 19:00, 21:00
```
> Jika tenant tidak set `scheduled_at`, sistem auto-assign ke slot prime time berikutnya

---

## 9. Frontend Dashboard

### 9.1 Pages / Views

```
/                   → redirect ke /dashboard jika login, /login jika tidak
/login              → form login
/register           → form register
/dashboard          → overview stats + recent jobs
/jobs               → daftar semua job + filter
/jobs/new           → buat job baru (wizard 3 langkah)
/channels           → daftar channel + connect YouTube
/keys               → kelola Gemini API key
/trends             → scouting tren + generate script
/settings           → profil akun
```

### 9.2 Dashboard Overview (/)
- Cards: Total Jobs, Jobs Done, Sedang Proses, Terjadwal
- Chart: Views 30 hari terakhir (per channel)
- Tabel recent jobs (10 terakhir) dengan status badge

### 9.3 Job Wizard (/jobs/new)
**Step 1 — Sumber konten:**
- Tab: Upload File | URL | AI Generate
- Upload: drag-and-drop, max 500MB, accept .mp4 .mov .avi
- URL: input field, preview thumbnail
- AI: pilih niche, input topik atau pakai saran trend

**Step 2 — Pengaturan:**
- Toggle: Tambah Subtitle otomatis
- Toggle: Tambah Musik Latar
- Input: Hook Text (opsional)
- Pilih Channel (dropdown)
- Jadwal: Segera / Prime time otomatis / Tanggal & jam custom

**Step 3 — Review & Submit:**
- Preview setting
- Tombol "Mulai Proses"

### 9.4 Job Detail
- Status badge dengan animasi (processing = spinner)
- Progress bar real-time (polling /api/jobs/{id} setiap 3 detik)
- Preview script (expandable)
- Tombol: Download Video | Upload ke YouTube | Hapus Job

### 9.5 Gemini Key Manager (/keys)
- Tabel key dengan kolom: Label, API Key (masked), Status, Penggunaan, Terakhir Dipakai
- Tombol: Tambah Key | Test Key | Toggle Aktif | Hapus
- Badge: "Pool Aktif: X dari Y key"
- Alert jika pool kosong

### 9.6 Design System
```
Warna Utama:  #FF0000 (YouTube Red)
Warna Aksen:  #282828 (YouTube Dark)
Background:   #F9F9F9
Card:         #FFFFFF, shadow-sm
Font:         Inter (Google Fonts)
Radius:       8px
```

---

## 10. Security Requirements

| Req | Detail |
|-----|--------|
| S1 | Semua password di-hash bcrypt (cost factor 12) |
| S2 | JWT RS256 dengan expiry 24 jam |
| S3 | Semua endpoint /api/* (kecuali /auth/*) wajib Bearer token |
| S4 | Tenant hanya bisa akses data dengan `tenant_id` miliknya sendiri — validasi di setiap query |
| S5 | API key Gemini selalu di-mask di response (8 char + `***masked***`) |
| S6 | YouTube credentials disimpan terenkripsi di JSON field (Fernet enkripsi — fase 2) |
| S7 | File upload dibatasi tipe (whitelist: mp4, mov, avi) dan ukuran (max 500MB) |
| S8 | Rate limiting: max 100 req/menit per tenant (fase 2) |
| S9 | CORS hanya izinkan origin yang terdaftar di prod |

---

## 11. Storage Layout

```
storage/
├── shared/
│   └── music/           # Royalty-free BGM tracks
│       ├── upbeat_01.mp3
│       └── calm_01.mp3
└── {tenant_id}/
    ├── uploads/         # File yang di-upload tenant
    │   └── {job_id}.mp4
    ├── downloads/       # File yang di-download dari URL
    │   └── {job_id}.mp4
    ├── output/          # Hasil final yang sudah diproses
    │   └── {job_id}.mp4
    ├── thumbnails/      # Thumbnail frame
    │   └── {job_id}.jpg
    └── temp/            # File intermediate (dihapus setelah done)
        └── {job_id}_cropped.mp4
```

---

## 12. Background Job Flow

```
POST /api/jobs
     │
     ▼
DB: status=pending
     │
     ▼ (APScheduler check_pending_jobs, setiap 30s)
     │
     ├─ source_type=url? → yt-dlp download → storage/{tid}/downloads/
     ├─ source_type=upload? → sudah ada di storage/{tid}/uploads/
     └─ source_type=ai_generate? → generate script → generate video (fase 2)
     │
     ▼
DB: status=processing, progress=0
     │
     ▼
VideoProcessor.run(job)
  ├── probe            progress=10
  ├── crop 9:16        progress=30
  ├── script gen       progress=50
  ├── subtitles        progress=70
  ├── hook overlay     progress=80
  ├── music mix        progress=90
  └── thumbnail        progress=95
     │
     ▼
DB: status=done, progress=100, output_filename=...
     │
     ├── scheduled_at set? → DB: status=scheduled
     └── upload_now? → YouTubeUploader.upload(job) → DB: status=uploaded
```

---

## 13. Error Handling

| Error Code | Situasi | Response |
|------------|---------|----------|
| 400 | Input tidak valid | `{ "error": "pesan spesifik" }` |
| 401 | Token tidak ada/expired | `{ "error": "Unauthorized" }` |
| 403 | Akses data tenant lain | `{ "error": "Forbidden" }` |
| 404 | Resource tidak ditemukan | `{ "error": "Not found" }` |
| 409 | Duplikasi (email, key) | `{ "error": "Sudah terdaftar" }` |
| 422 | Validasi Pydantic gagal | Pydantic default response |
| 429 | Rate limit (fase 2) | `{ "error": "Too many requests" }` |
| 500 | Error internal | `{ "error": "Internal server error", "job_id": "..." }` |

Semua error dari job processing disimpan ke `job.error_message` dan job berstatus `failed`.

---

## 14. Limits per Plan

| Feature | Free | Pro | Enterprise |
|---------|------|-----|------------|
| Gemini Keys | 3 | 20 | 50 |
| Channels | 1 | 5 | Unlimited |
| Jobs/bulan | 10 | 200 | Unlimited |
| File upload max | 100MB | 500MB | 2GB |
| Concurrent jobs | 1 | 5 | 20 |

> v1.0: semua tenant = free plan, limit enforcement di fase 2

---

## 15. Testing Checklist

### API (Smoke Tests)
- [ ] POST /api/auth/register → 201
- [ ] POST /api/auth/login → 200 dengan token
- [ ] GET /api/auth/me → 200 dengan data tenant
- [ ] POST /api/keys → 201, api_key di-mask
- [ ] POST /api/keys/test (key valid) → `{ valid: true }`
- [ ] POST /api/jobs (sumber: url) → 201
- [ ] GET /api/jobs/{id} → 200 dengan progress
- [ ] GET /api/trends?niche=motivasi → 200 dengan list topik
- [ ] GET /api/jobs/{id}/download (setelah done) → file stream
- [ ] Akses data tenant lain → 403

### Video Processing
- [ ] Crop video 16:9 → output 9:16 (1080x1920)
- [ ] Subtitle ter-burn di video output
- [ ] Hook text muncul di 0–3 detik
- [ ] Musik ter-mix di volume rendah (tidak mendominasi)

### Scheduler
- [ ] Job pending diambil dalam 30 detik
- [ ] Job scheduled di-upload tepat waktu

---

## 16. Environment Variables

| Variable | Required | Default | Keterangan |
|----------|----------|---------|------------|
| `SESSION_SECRET` | ✅ | — | JWT signing key |
| `DATABASE_URL` | ✗ | `sqlite:///./shortsdb.sqlite` | PostgreSQL di prod |
| `YOUTUBE_CLIENT_ID` | ✅ (untuk upload) | — | Google OAuth client |
| `YOUTUBE_CLIENT_SECRET` | ✅ (untuk upload) | — | Google OAuth secret |
| `YOUTUBE_REDIRECT_URI` | ✅ (untuk upload) | — | Callback URL OAuth |

---

## 17. File Structure Target

```
/
├── PRD.md
├── README.md
├── replit.md
├── requirements.txt
├── backend/
│   ├── __init__.py
│   ├── main.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── security.py
│   │   ├── gemini_pool.py
│   │   └── deps.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── models.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── keys.py
│   │   ├── channels.py
│   │   ├── jobs.py
│   │   ├── trends.py
│   │   └── analytics.py
│   └── modules/
│       ├── __init__.py
│       ├── video_processor/
│       │   ├── __init__.py
│       │   └── processor.py
│       ├── script_generator/
│       │   ├── __init__.py
│       │   └── generator.py
│       ├── youtube_uploader/
│       │   ├── __init__.py
│       │   └── uploader.py
│       ├── trend_scout/
│       │   ├── __init__.py
│       │   └── scout.py
│       └── scheduler/
│           ├── __init__.py
│           └── scheduler.py
├── frontend/
│   └── index.html          # SPA entry point
└── storage/
    └── shared/
        └── music/
```

---

## 18. Implementation Priority (Sprint Order)

### Sprint 1 — Foundation ✅ (sedang berjalan)
- [x] Project structure
- [x] Database models
- [x] Auth (register/login/me)
- [x] Gemini key pool (per-tenant isolation)
- [ ] FastAPI main + routing
- [ ] SPA frontend dasar

### Sprint 2 — Core Pipeline
- [ ] Video processor (crop, subtitle, hook)
- [ ] Script generator (semua niche)
- [ ] Trend scout
- [ ] Job API + background worker
- [ ] File upload/download

### Sprint 3 — YouTube Integration
- [ ] OAuth flow
- [ ] Video upload
- [ ] Analytics fetch

### Sprint 4 — Scheduler & Polish
- [ ] APScheduler integration
- [ ] Prime time auto-scheduling
- [ ] Dashboard UI lengkap
- [ ] Error handling & logging

### Sprint 5 — SaaS Hardening
- [ ] Plan limits enforcement
- [ ] Rate limiting
- [ ] YouTube credential encryption
- [ ] Multi-channel support penuh

---

*PRD ini adalah dokumen living — update setiap ada keputusan arsitektur baru.*
