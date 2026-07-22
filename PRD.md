# PRD — YouTube Shorts Factory SaaS
**Version:** 2.0.0  
**Date:** 2026-07-22  
**Status:** Active  
**Audience:** Engineering, Product, QA  
**Environment:** cPanel Shared Hosting / Local Server (Laragon)

---

## 1. Overview

YouTube Shorts Factory adalah platform SaaS **multi-tenant** yang mengotomasi seluruh pipeline produksi dan distribusi konten YouTube Shorts — mulai dari riset tren, penulisan skrip AI, pemrosesan video, hingga upload terjadwal ke YouTube dan platform lain. Platform ini memanfaatkan rotasi **Gemini API key per-tenant** (hingga 50 key) untuk bypass rate limit dan parallelism tinggi.

Platform dapat di-deploy di **cPanel shared/VPS hosting** maupun **lokal via Laragon** (Windows). Tidak ada ketergantungan pada Docker atau cloud-native services.

---

## 2. Goals & Non-Goals

### Goals
| # | Goal |
|---|------|
| G1 | Tenant dapat mendaftar, login, dan mengelola akun secara mandiri |
| G2 | Tenant dapat mendaftarkan hingga 50 Gemini API key per akun dengan rotasi otomatis |
| G3 | Tenant dapat memproses video (crop 9:16, subtitle, hook text, musik) |
| G4 | Tenant dapat membuat skrip Shorts berbasis niche dengan AI |
| G5 | Tenant dapat menghubungkan channel YouTube via OAuth dan upload otomatis |
| G6 | Tenant dapat menjadwalkan upload di jam prime time |
| G7 | Tenant dapat memantau performa video di dashboard |
| G8 | Isolasi data antar tenant penuh (tidak ada kebocoran lintas tenant) |
| G9 | Background worker memproses antrian job secara async |
| G10 | Text-to-Shorts: generate video dari teks tanpa footage (slide-based + TTS) |
| G11 | Multi-platform output: 1 video → YouTube Shorts, TikTok, Instagram Reels, Facebook Reels |
| G12 | Viral Hook Library: database hook template terbukti viral per niche |
| G13 | Auto A/B Title Testing: upload 2 varian title, monitor CTR, prune otomatis |
| G14 | Competitor Spy: analisis channel competitor → rekomendasi strategi |
| G15 | WhatsApp / Telegram Bot: kontrol via chat mobile |
| G16 | Reseller / White-label Mode: sub-tenant dengan branding custom |
| G17 | Smart Content Calendar: jadwal berdasarkan pola audience per channel |
| G18 | Dapat berjalan di cPanel dan Laragon tanpa Docker |

### Non-Goals (v1.x)
- Billing / payment gateway (direncanakan fase 5)
- Mobile app native (iOS/Android)
- Streaming live ke YouTube

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

### 3.3 Reseller / White-label Partner
- Beli akses platform, jual ulang ke klien mereka dengan brand sendiri
- Butuh sub-tenant management + custom domain + logo

### 3.4 Developer / Power User
- Akses via API langsung
- Butuh dokumentasi endpoint yang jelas
- Mau integrasi dengan tools eksternal (n8n, Zapier, Make)

---

## 4. Tech Stack

| Layer | Teknologi |
|-------|-----------|
| **Backend** | Python 3.11+, FastAPI, Uvicorn (via Passenger WSGI di cPanel) |
| **Database** | SQLite (dev/Laragon) / MySQL (cPanel prod) via SQLAlchemy |
| **Auth** | JWT (python-jose), bcrypt |
| **AI** | Google Gemini API (`gemini-2.0-flash`, `gemini-1.5-flash`, Gemini TTS) |
| **Video** | FFmpeg (binary), MoviePy |
| **Download** | yt-dlp |
| **Scheduler** | APScheduler (BackgroundScheduler) / cPanel Cron Jobs |
| **Bot** | python-telegram-bot, Twilio WhatsApp API |
| **Frontend** | Vanilla HTML/CSS/JS SPA (served dari FastAPI static) |
| **Storage** | Filesystem lokal `storage/{tenant_id}/` |
| **Deployment** | cPanel Passenger WSGI / Laragon (PHP+Python side-by-side) |

---

## 5. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      FRONTEND (SPA)                              │
│  Dashboard · Jobs · Channels · Keys · Trends · Bot · Reseller   │
└──────────────────────────┬───────────────────────────────────────┘
                           │ REST API (JSON)
┌──────────────────────────▼───────────────────────────────────────┐
│                      FastAPI Backend                             │
│                                                                  │
│  /api/auth/*        Auth (register, login, me)                  │
│  /api/keys/*        Gemini key CRUD                             │
│  /api/channels/*    YouTube channel management                  │
│  /api/jobs/*        Video job CRUD + trigger                    │
│  /api/trends/*      Trend scouting + script gen                 │
│  /api/analytics/*   YouTube analytics                           │
│  /api/hooks/*       Viral hook library                          │
│  /api/bot/*         Telegram/WhatsApp webhook                   │
│  /api/reseller/*    Sub-tenant management                       │
│  /api/admin/*       Super admin                                 │
└──┬──────┬──────┬──────┬──────┬──────┬──────┬────────────────────┘
   │      │      │      │      │      │      │
   ▼      ▼      ▼      ▼      ▼      ▼      ▼
Gemini  Video  Script  YT    Sched  Bot   Reseller
Pool   Proc   Gen    Upload  uler  Notif  Manager
```

---

## 6. Data Models

### 6.1 Tenant
```
tenants
├── id                UUID PK
├── email             String UNIQUE NOT NULL
├── hashed_password   String NOT NULL
├── name              String NOT NULL
├── plan              Enum(free|pro|enterprise) DEFAULT free
├── is_active         Boolean DEFAULT true
├── is_reseller       Boolean DEFAULT false
├── parent_tenant_id  FK → tenants.id nullable  (untuk sub-tenant)
├── brand_name        String nullable            (white-label)
├── brand_logo_url    String nullable
├── brand_color       String nullable            (#hex)
├── telegram_chat_id  String nullable
├── whatsapp_number   String nullable
├── bot_active        Boolean DEFAULT false
└── created_at        DateTime
```

### 6.2 GeminiKey
```
gemini_keys
├── id           UUID PK
├── tenant_id    FK → tenants.id
├── api_key      String NOT NULL
├── label        String
├── is_active    Boolean DEFAULT true
├── usage_count  Integer DEFAULT 0
├── last_used_at DateTime nullable
└── created_at   DateTime
```

### 6.3 Channel
```
channels
├── id                    UUID PK
├── tenant_id             FK → tenants.id
├── channel_name          String NOT NULL
├── niche                 String NOT NULL
├── youtube_credentials   JSON nullable
├── youtube_channel_id    String nullable
├── subscriber_count      Integer DEFAULT 0
├── best_upload_hours     JSON nullable   [7, 12, 19]  ← dari analytics
├── is_active             Boolean DEFAULT true
└── created_at            DateTime
```

### 6.4 VideoJob
```
video_jobs
├── id                  UUID PK
├── tenant_id           FK → tenants.id
├── channel_id          FK → channels.id nullable
├── source_type         Enum(upload|url|ai_generate|text_to_shorts)
├── source_url          String nullable
├── source_filename     String nullable
├── niche               String nullable
├── title               String nullable
├── title_variant_b     String nullable       ← A/B testing
├── description         Text nullable
├── tags                JSON []
├── add_subtitles       Boolean DEFAULT true
├── add_music           Boolean DEFAULT false
├── hook_text           String nullable
├── hook_library_id     FK → hook_library.id nullable
├── output_filename     String nullable
├── script              Text nullable
├── thumbnail_filename  String nullable
├── platforms           JSON ["youtube","tiktok","instagram","facebook"]
├── ab_test_active      Boolean DEFAULT false
├── ab_winner           String nullable       ← "a" | "b" | null
├── status              Enum(pending|processing|done|failed|scheduled|uploaded)
├── error_message       Text nullable
├── progress            Float 0.0–100.0
├── scheduled_at        DateTime nullable
├── uploaded_at         DateTime nullable
├── youtube_video_id    String nullable
├── tiktok_video_id     String nullable
├── instagram_media_id  String nullable
├── created_at          DateTime
└── updated_at          DateTime
```

### 6.5 HookLibrary
```
hook_library
├── id          UUID PK
├── tenant_id   FK → tenants.id nullable  (null = global/shared)
├── niche       String NOT NULL
├── hook_text   Text NOT NULL
├── avg_ctr     Float nullable
├── use_count   Integer DEFAULT 0
├── is_approved Boolean DEFAULT false      (hanya global; tenant punya selalu true)
└── created_at  DateTime
```

### 6.6 AbTestResult
```
ab_test_results
├── id              UUID PK
├── job_id          FK → video_jobs.id
├── variant         Enum(a|b)
├── youtube_video_id String
├── views_48h       Integer DEFAULT 0
├── ctr_48h         Float nullable
├── checked_at      DateTime nullable
└── created_at      DateTime
```

### 6.7 BotSession
```
bot_sessions
├── id          UUID PK
├── tenant_id   FK → tenants.id
├── platform    Enum(telegram|whatsapp)
├── chat_id     String NOT NULL
├── state       String nullable         ← FSM state (awaiting_url, etc.)
├── context     JSON {}                 ← temporary data
└── updated_at  DateTime
```

---

## 7. API Specification

### 7.1 Auth

#### POST /api/auth/register
**Body:**
```json
{ "email": "user@example.com", "password": "min8chars", "name": "Creator Name" }
```
**Response 201:**
```json
{ "access_token": "eyJ...", "token_type": "bearer", "tenant": { "id": "...", "email": "...", "name": "...", "plan": "free" } }
```
**Errors:** 409 email sudah terdaftar, 422 validasi

---

#### POST /api/auth/login
**Body (form-data):** `username`, `password`  
**Response 200:** sama dengan register  
**Errors:** 401 credentials salah

---

#### GET /api/auth/me
**Response 200:** `{ "id", "email", "name", "plan", "is_reseller", "brand_name", "created_at" }`

---

### 7.2 Gemini Keys

#### GET /api/keys
**Response 200:**
```json
{ "keys": [{ "id", "label", "api_key": "AIza***masked***", "is_active", "usage_count", "last_used_at" }], "total": 1, "pool_size": 1 }
```

#### POST /api/keys
**Body:** `{ "api_key": "AIzaSy...", "label": "Key produksi" }`  
**Response 201** | **Errors:** 400 duplikat

#### DELETE /api/keys/{key_id} → 204

#### POST /api/keys/{key_id}/toggle → 200 `{ "is_active": false }`

#### POST /api/keys/test
**Body:** `{ "api_key": "AIzaSy..." }`  
**Response 200:** `{ "valid": true, "model": "gemini-2.0-flash" }`

---

### 7.3 Channels

#### GET /api/channels → list channels tenant
#### POST /api/channels → `{ "channel_name", "niche" }` → 201
#### DELETE /api/channels/{id} → 204
#### GET /api/channels/{id}/oauth-url → `{ "auth_url": "https://accounts.google.com/..." }`
#### POST /api/channels/{id}/oauth-callback → `{ "code": "..." }` → `{ "success": true }`
#### GET /api/channels/{id}/best-hours → `{ "hours": [7, 12, 19], "analyzed_at": "..." }`

---

### 7.4 Video Jobs

#### GET /api/jobs
**Query:** `status`, `channel_id`, `page`, `limit`

#### POST /api/jobs
**Content-Type:** `multipart/form-data` atau `application/json`

**Skenario 1 — Upload:**
```
source_type=upload, file=<binary>, niche, add_subtitles, hook_text, platforms=["youtube","tiktok"]
```

**Skenario 2 — URL:**
```json
{ "source_type": "url", "source_url": "https://youtube.com/...", "niche": "edukasi", "platforms": ["youtube","instagram"] }
```

**Skenario 3 — AI Generate (slide-based):**
```json
{ "source_type": "text_to_shorts", "niche": "fakta", "topic": "5 Fakta Otak Manusia", "duration_seconds": 45, "add_tts": true }
```

**Response 201:** `{ "job_id", "status": "pending" }`

#### GET /api/jobs/{id} → detail + progress
#### DELETE /api/jobs/{id} → 204
#### POST /api/jobs/{id}/upload-now → `{ "success": true, "youtube_video_id": "..." }`
#### GET /api/jobs/{id}/download → StreamingResponse
#### POST /api/jobs/{id}/ab-test → aktifkan A/B testing dengan title_variant_b

---

### 7.5 Trends

#### GET /api/trends?niche=motivasi&limit=10
**Response:**
```json
{ "niche": "motivasi", "trends": [{ "topic": "...", "score": 95, "suggested_hook": "..." }] }
```

#### POST /api/trends/generate-script
**Body:** `{ "topic", "niche", "duration_seconds" }`  
**Response:**
```json
{ "script", "title", "title_variant_b", "description", "tags", "hook_options": ["...", "...", "..."] }
```

---

### 7.6 Hook Library

#### GET /api/hooks?niche=motivasi&limit=20
**Response:** `{ "hooks": [{ "id", "hook_text", "avg_ctr", "use_count" }] }`

#### POST /api/hooks → submit hook custom tenant → `{ "id", "hook_text", "niche" }`
#### DELETE /api/hooks/{id} → 204 (hanya hook milik tenant)
#### GET /api/hooks/best?niche=motivasi → top 5 hook dengan CTR tertinggi

---

### 7.7 Analytics

#### GET /api/analytics/{channel_id}?days=30
```json
{
  "summary": { "total_views", "total_videos", "avg_ctr", "best_upload_hour" },
  "videos": [{ "youtube_video_id", "title", "views", "likes", "ctr", "uploaded_at" }],
  "ab_tests": [{ "job_id", "variant_a_ctr", "variant_b_ctr", "winner" }]
}
```

---

### 7.8 Competitor Spy

#### POST /api/spy/analyze
**Body:** `{ "channel_url": "https://youtube.com/@channel" }`  
**Response:**
```json
{
  "channel_name": "...",
  "avg_views": 50000,
  "posting_frequency": "2x/hari",
  "top_niches": ["motivasi", "fakta"],
  "common_hooks": ["Hook 1", "Hook 2"],
  "best_posting_hours": [7, 19],
  "recommendations": ["Posting 2x sehari di jam 7 dan 19", "Gunakan hook pertanyaan lebih sering"]
}
```

#### GET /api/spy/history → daftar analisis competitor tersimpan

---

### 7.9 Bot (Telegram & WhatsApp)

#### POST /api/bot/telegram/webhook → Telegram webhook handler
#### POST /api/bot/whatsapp/webhook → WhatsApp (Twilio) webhook handler
#### POST /api/bot/connect/telegram → `{ "bot_token": "..." }` → setup webhook
#### POST /api/bot/connect/whatsapp → `{ "account_sid", "auth_token", "from_number" }` → setup
#### DELETE /api/bot/disconnect/{platform} → 204

**Bot Commands:**
```
/start          → welcome + panduan
/status         → ringkasan akun (jobs, keys, channels)
/newjob [url]   → buat job baru dari URL
/jobs           → daftar 5 job terakhir
/stats          → statistik hari ini
/trends [niche] → topik trending
/help           → bantuan
```

---

### 7.10 Reseller / White-label

#### GET /api/reseller/sub-tenants → daftar sub-tenant
#### POST /api/reseller/sub-tenants → buat sub-tenant
```json
{ "email", "password", "name", "plan": "free" }
```
#### DELETE /api/reseller/sub-tenants/{id} → 204
#### PUT /api/reseller/branding → update brand reseller
```json
{ "brand_name": "MyShorts.id", "brand_logo_url": "...", "brand_color": "#FF6B6B" }
```
#### GET /api/reseller/stats → total sub-tenant, total jobs, revenue estimasi

---

## 8. Module Specifications

### 8.1 GeminiPool (backend/core/gemini_pool.py)
- Per-tenant `TenantKeyPool` terisolasi
- Round-robin thread-safe dengan `threading.Lock`
- Singleton `pool_manager` global
- Resync dari DB setiap kali key berubah

---

### 8.2 VideoProcessor (backend/modules/video_processor/processor.py)

**Pipeline:**
1. Download/copy sumber
2. Probe metadata (ffprobe)
3. Crop → 9:16 (1080x1920) via FFmpeg
4. Subtitle via Gemini Vision → burn SRT
5. Hook text overlay (FFmpeg drawtext, 0–3 detik)
6. Background music (volume duck 15%)
7. Export ke format per-platform (rasio, resolusi, durasi max):
   - YouTube Shorts: 1080x1920, max 60s
   - TikTok: 1080x1920, max 60s (metadata berbeda)
   - Instagram Reels: 1080x1920, max 90s
   - Facebook Reels: 1080x1920, max 60s
8. Thumbnail extraction + Gemini caption

**FFmpeg patterns:**
```bash
# Crop & scale 9:16
ffmpeg -i input.mp4 -vf "crop=ih*9/16:ih,scale=1080:1920" -c:a copy cropped.mp4

# Hook text overlay
ffmpeg -i cropped.mp4 -vf "drawtext=text='%{hook}':fontsize=72:fontcolor=white:x=(w-text_w)/2:y=h*0.15:enable='between(t,0,3)':borderw=3:bordercolor=black" hooked.mp4

# Burn subtitles
ffmpeg -i hooked.mp4 -vf "subtitles=subs.srt:force_style='FontSize=28,Bold=1,Alignment=2'" subbed.mp4

# Mix background music
ffmpeg -i subbed.mp4 -i music.mp3 -filter_complex "[1:a]volume=0.15[m];[0:a][m]amix=inputs=2:duration=first" final.mp4
```

---

### 8.3 Text-to-Shorts Generator (backend/modules/text_to_shorts/generator.py)

**Pipeline:**
1. Gemini generate struktur slide (5–8 slide, per slide: heading + body text)
2. Pilih template visual (gradient background per niche, font overlay)
3. Generate gambar per slide via Pillow (atau Gemini Imagen jika tersedia)
4. TTS narasi per slide via Gemini TTS / gTTS fallback
5. Gabung gambar + audio per slide → video clip per slide via MoviePy
6. Concat semua clip → video final
7. Tambah background music (volume 10%)

**Slide structure (Gemini output):**
```json
{
  "slides": [
    { "type": "hook", "heading": "5 Fakta Mengejutkan", "body": "yang jarang diketahui orang" },
    { "type": "fact", "heading": "Fakta #1", "body": "Otak manusia hanya pakai 10% energinya..." },
    ...
    { "type": "cta", "heading": "Follow untuk tips lainnya!", "body": "" }
  ],
  "background_style": "dark_gradient",
  "accent_color": "#FF6B6B"
}
```

---

### 8.4 ScriptGenerator (backend/modules/script_generator/generator.py)

**Output per niche:**
```json
{
  "hook": "...",
  "body": ["poin 1", "poin 2", "poin 3"],
  "cta": "...",
  "full_script": "...",
  "title": "...",
  "title_variant_b": "...",
  "description": "...",
  "tags": ["..."],
  "hook_options": ["hook A", "hook B", "hook C"]
}
```

**Niche config:**
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

### 8.5 TrendScout (backend/modules/trend_scout/scout.py)
- Gemini generate topik trending berdasarkan tanggal + niche
- Skor viralitas 0–100
- Suggested hook per topik
- Simpan cache di DB (TTL 6 jam per niche)

---

### 8.6 CompetitorSpy (backend/modules/competitor_spy/spy.py)
1. `yt-dlp` fetch metadata channel (tanpa download video)
2. Ambil 50 video terakhir: judul, views, upload date, durasi
3. Gemini analisis pola: niche, hook style, jam upload, frekuensi
4. Generate rekomendasi strategi

---

### 8.7 YouTubeUploader (backend/modules/youtube_uploader/uploader.py)
- OAuth2 flow per channel
- Resumable upload (google-api-python-client)
- Auto-refresh token
- A/B test: upload 2 video dengan title berbeda, jadwalkan check CTR 48 jam

---

### 8.8 MultiPlatformExporter (backend/modules/multi_platform/exporter.py)
- Terima output video final + metadata
- Export ke format tiap platform (FFmpeg re-encode jika perlu)
- Upload ke platform masing-masing via API:
  - TikTok: TikTok Upload API (Content Posting API)
  - Instagram Reels: Meta Graph API
  - Facebook Reels: Meta Graph API
- Simpan `{platform}_video_id` ke VideoJob

---

### 8.9 Scheduler (backend/modules/scheduler/scheduler.py)
- `check_pending_jobs` → setiap 30s
- `check_scheduled_uploads` → setiap 1 menit
- `check_ab_tests` → setiap jam: cek job dengan `ab_test_active=true` + `uploaded_at` > 48 jam, fetch CTR via YouTube Analytics API, tentukan winner, private loser
- `analyze_best_hours` → setiap hari jam 02:00: fetch analytics per channel, update `channel.best_upload_hours`
- `cleanup_old_files` → setiap hari jam 03:00

**Prime time slots (WIB):** `07:00, 12:00, 16:00, 19:00, 21:00`  
Jika `channel.best_upload_hours` terisi → pakai itu (lebih personal)

---

### 8.10 BotHandler (backend/modules/bot/)

**Telegram FSM States:**
```
IDLE → awaiting_command
awaiting_url → processing job
awaiting_niche → awaiting_url
```

**WhatsApp:** Same FSM via Twilio webhooks

---

### 8.11 ResellerManager (backend/modules/reseller/manager.py)
- `create_sub_tenant(parent_id, data)` → buat tenant baru dengan `parent_tenant_id` set
- Sub-tenant inherit `brand_name`, `brand_logo_url`, `brand_color` dari parent
- Reseller hanya bisa manage sub-tenant miliknya
- Reseller tidak bisa akses data job sub-tenant (privacy)
- `get_reseller_stats(tenant_id)` → count sub-tenants, total jobs, estimasi value

---

## 9. Frontend Dashboard

### 9.1 Pages / Views
```
/                   → redirect ke /dashboard atau /login
/login              → form login + brand color (white-label aware)
/register           → form register
/dashboard          → overview stats + recent jobs + chart views
/jobs               → daftar job + filter + status badge
/jobs/new           → wizard 3 langkah
/channels           → list channel + connect YouTube
/keys               → kelola Gemini API key
/trends             → scouting + generate script
/hooks              → viral hook library
/spy                → competitor analyzer
/bot                → setup Telegram/WhatsApp bot
/reseller           → (hanya is_reseller=true) sub-tenant management
/settings           → profil + branding
```

### 9.2 Job Wizard — Step 1: Sumber
- **Tab Upload:** drag-and-drop, max 500MB, .mp4/.mov/.avi
- **Tab URL:** input + preview thumbnail yt-dlp
- **Tab AI Generate (slide):** pilih niche + topik/dari trend + toggle TTS
- **Platform checkboxes:** YouTube ✓ | TikTok | Instagram Reels | Facebook Reels

### 9.3 Job Wizard — Step 2: Pengaturan
- Toggle: Subtitle otomatis
- Toggle: Musik Latar
- Hook Text (atau pilih dari library)
- Pilih Channel
- A/B Test title (toggle + input variant B)
- Jadwal: Segera / Prime time otomatis / Smart (dari analytics) / Custom

### 9.4 Job Detail
- Progress bar real-time (polling 3s)
- Preview script, hook yang dipakai
- A/B test status card (jika aktif)
- Multi-platform upload status (badge per platform)
- Tombol: Download | Upload Now | Hapus

### 9.5 Competitor Spy UI
- Input URL channel
- Loading state dengan steps (fetching, analyzing...)
- Report card: Top Niches, Common Hooks, Best Hours, Posting Frequency
- Rekomendasi action items
- Tombol: "Buat Job dari Topik Ini"

### 9.6 Viral Hook Library UI
- Filter per niche
- Sort: CTR tertinggi | Paling sering dipakai | Terbaru
- Tombol "Pakai hook ini" langsung copy ke job form
- Submit hook baru (dari performa real job)

### 9.7 White-label Awareness
- Jika tenant adalah sub-tenant dari reseller → tampilkan `brand_name`, `brand_logo_url`, `brand_color`
- Login page menyesuaikan branding
- URL bisa custom subdomain (konfigurasi via cPanel)

### 9.8 Design System
```
Warna Utama default:  #FF0000 (YouTube Red)
Warna Aksen default:  #282828 (YouTube Dark)
Background:           #F9F9F9
Card:                 #FFFFFF, shadow-sm
Font:                 Inter (Google Fonts)
Radius:               8px
White-label:          override dengan brand_color tenant reseller
```

---

## 10. Security Requirements

| Req | Detail |
|-----|--------|
| S1 | Password di-hash bcrypt (cost 12) |
| S2 | JWT HS256, expiry 24 jam |
| S3 | Semua `/api/*` (kecuali `/auth/*` dan `/bot/*/webhook`) wajib Bearer |
| S4 | Query selalu filter `tenant_id` — tidak ada akses lintas tenant |
| S5 | API key Gemini di-mask di response |
| S6 | YouTube credentials tersimpan terenkripsi (Fernet, fase 3) |
| S7 | File upload: whitelist tipe + max 500MB |
| S8 | Reseller hanya manage sub-tenant dengan `parent_tenant_id = reseller.id` |
| S9 | Bot webhook verify Telegram secret token / Twilio signature |
| S10 | CORS hanya origin terdaftar di prod |

---

## 11. Storage Layout

```
storage/
├── shared/
│   └── music/              # Royalty-free BGM
│       ├── upbeat_01.mp3
│       └── calm_01.mp3
└── {tenant_id}/
    ├── uploads/            # Upload dari user
    ├── downloads/          # Download dari URL
    ├── slides/             # Frame image (text-to-shorts)
    ├── tts/                # Audio TTS per slide
    ├── output/             # Video final
    │   └── platforms/      # Per-platform export
    │       ├── youtube/
    │       ├── tiktok/
    │       ├── instagram/
    │       └── facebook/
    ├── thumbnails/
    └── temp/               # Intermediate, auto-cleaned
```

---

## 12. Deployment Guide

### 12.1 Local — Laragon (Windows)

**Requirements:**
- Laragon Full (Apache + MySQL + PHP 8.x)
- Python 3.11+ terinstall di PATH
- FFmpeg binary di `C:\laragon\bin\ffmpeg\` (add to PATH)

**Setup steps:**
```bash
# 1. Clone repo ke C:\laragon\www\shorts-factory\
# 2. Buat virtual environment
cd C:\laragon\www\shorts-factory
python -m venv venv
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy .env
copy .env.example .env
# Edit .env: DATABASE_URL=sqlite:///./shortsdb.sqlite

# 5. Jalankan
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
# Akses: http://localhost:8000
```

**Laragon Virtual Host (opsional):**
- Di Laragon Menu → Apache → Virtual Hosts → add: `shorts.test → C:\laragon\www\shorts-factory`
- Gunakan reverse proxy Apache → Uvicorn port 8000

---

### 12.2 cPanel Shared/VPS Hosting

**Requirements:**
- cPanel dengan Python App Manager (CloudLinux / LiteSpeed)
- Python 3.11 tersedia di Python App Manager
- MySQL database (via cPanel MySQL Databases)
- SSH access untuk pip install

**Setup steps:**
```bash
# 1. Upload files via File Manager atau Git (cPanel Git Version Control)

# 2. Buat Python App di cPanel:
#    Application root: /home/user/shorts-factory
#    Application URL: /   (atau subdomain)
#    Application startup file: passenger_wsgi.py
#    Python version: 3.11

# 3. SSH: install dependencies
cd ~/shorts-factory
source virtualenv/bin/activate   # path dari cPanel Python App
pip install -r requirements.txt

# 4. Buat .env dengan DATABASE_URL MySQL:
DATABASE_URL=mysql+pymysql://user:pass@localhost/dbname

# 5. cPanel Cron Jobs (pengganti APScheduler jika perlu):
#    * * * * * /home/user/shorts-factory/virtualenv/bin/python /home/user/shorts-factory/worker.py

# 6. Passenger WSGI entry point: passenger_wsgi.py
```

**passenger_wsgi.py:**
```python
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from backend.main import app as application
```

---

## 13. Environment Variables

| Variable | Required | Default | Keterangan |
|----------|----------|---------|------------|
| `SESSION_SECRET` | ✅ | — | JWT signing key |
| `DATABASE_URL` | ✗ | `sqlite:///./shortsdb.sqlite` | MySQL di prod |
| `YOUTUBE_CLIENT_ID` | ✅ upload | — | Google OAuth |
| `YOUTUBE_CLIENT_SECRET` | ✅ upload | — | Google OAuth |
| `YOUTUBE_REDIRECT_URI` | ✅ upload | — | OAuth callback |
| `TELEGRAM_BOT_TOKEN` | ✗ | — | Telegram bot |
| `TWILIO_ACCOUNT_SID` | ✗ | — | WhatsApp via Twilio |
| `TWILIO_AUTH_TOKEN` | ✗ | — | WhatsApp via Twilio |
| `TWILIO_WHATSAPP_FROM` | ✗ | — | `whatsapp:+14155238886` |
| `TIKTOK_CLIENT_KEY` | ✗ | — | TikTok Upload API |
| `TIKTOK_CLIENT_SECRET` | ✗ | — | TikTok Upload API |
| `META_APP_ID` | ✗ | — | Instagram/Facebook API |
| `META_APP_SECRET` | ✗ | — | Instagram/Facebook API |
| `FFMPEG_PATH` | ✗ | `ffmpeg` | Path absolut FFmpeg binary |

---

## 14. Plan Limits

| Feature | Free | Pro | Enterprise |
|---------|------|-----|------------|
| Gemini Keys | 3 | 20 | 50 |
| Channels | 1 | 5 | Unlimited |
| Jobs/bulan | 10 | 200 | Unlimited |
| File upload max | 100MB | 500MB | 2GB |
| Concurrent jobs | 1 | 5 | 20 |
| Platforms | YouTube only | +TikTok | All platforms |
| Bot | ✗ | Telegram | Telegram + WhatsApp |
| Competitor Spy | 3/bulan | 20/bulan | Unlimited |
| Reseller mode | ✗ | ✗ | ✅ |

---

## 15. Testing Checklist

### API Smoke Tests
- [ ] Register, login, /me
- [ ] CRUD Gemini key + test + mask
- [ ] CRUD Channel + OAuth flow
- [ ] Job: upload, url, text_to_shorts
- [ ] Download video output
- [ ] Trends + generate script
- [ ] Hook library CRUD
- [ ] Competitor spy analyze
- [ ] Bot connect + webhook
- [ ] Reseller: buat sub-tenant + branding
- [ ] Cross-tenant access → 403

### Video Processing
- [ ] 16:9 input → 9:16 1080x1920 output
- [ ] Subtitle ter-burn
- [ ] Hook text di 0–3 detik
- [ ] Musik mix volume rendah
- [ ] Text-to-Shorts: slide video dengan TTS
- [ ] Export ke tiap platform format

### Scheduler
- [ ] Pending job diproses dalam 30s
- [ ] Scheduled job di-upload tepat waktu
- [ ] A/B test check di 48 jam
- [ ] Best hours update harian

---

## 16. File Structure Target

```
/
├── PRD.md
├── README.md
├── replit.md
├── requirements.txt
├── .env.example
├── passenger_wsgi.py          ← cPanel entry point
├── worker.py                  ← standalone worker (cPanel cron)
├── backend/
│   ├── __init__.py
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── security.py
│   │   ├── gemini_pool.py
│   │   └── deps.py
│   ├── models/
│   │   └── models.py
│   ├── api/
│   │   ├── auth.py
│   │   ├── keys.py
│   │   ├── channels.py
│   │   ├── jobs.py
│   │   ├── trends.py
│   │   ├── analytics.py
│   │   ├── hooks.py
│   │   ├── spy.py
│   │   ├── bot.py
│   │   └── reseller.py
│   └── modules/
│       ├── video_processor/
│       │   └── processor.py
│       ├── script_generator/
│       │   └── generator.py
│       ├── text_to_shorts/
│       │   └── generator.py
│       ├── youtube_uploader/
│       │   └── uploader.py
│       ├── multi_platform/
│       │   └── exporter.py
│       ├── trend_scout/
│       │   └── scout.py
│       ├── competitor_spy/
│       │   └── spy.py
│       ├── hook_library/
│       │   └── library.py
│       ├── bot/
│       │   ├── telegram_bot.py
│       │   └── whatsapp_bot.py
│       ├── reseller/
│       │   └── manager.py
│       └── scheduler/
│           └── scheduler.py
├── frontend/
│   ├── index.html
│   ├── css/
│   │   └── app.css
│   └── js/
│       ├── app.js
│       ├── auth.js
│       ├── jobs.js
│       ├── channels.js
│       ├── keys.js
│       ├── trends.js
│       ├── hooks.js
│       ├── spy.js
│       ├── bot.js
│       └── reseller.js
└── storage/
    └── shared/
        └── music/
```

---

## 17. Build Phases

---

### 🚀 PHASE 1 — Foundation & Core Pipeline
**Target: Platform bisa dipakai untuk proses dan upload video dasar**  
**Duration: Sprint 1–2**

#### Backend
- [x] Project structure + `__init__.py`
- [x] Database models (Tenant, GeminiKey, Channel, VideoJob)
- [x] Auth: register, login, JWT, `/me`
- [x] Per-tenant Gemini key pool (round-robin, thread-safe)
- [ ] FastAPI `main.py` + routing + CORS + static SPA serve
- [ ] API: `/api/keys` CRUD + test endpoint
- [ ] API: `/api/channels` CRUD
- [ ] API: `/api/jobs` CRUD + file upload
- [ ] VideoProcessor: crop 9:16, hook text, subtitle burn, musik
- [ ] ScriptGenerator: semua 9 niche
- [ ] Background worker (APScheduler): pending jobs
- [ ] File storage layout (`storage/{tid}/...`)

#### Frontend
- [ ] SPA shell (login, register, navbar)
- [ ] Dashboard overview
- [ ] Job list + status badge
- [ ] Job wizard (upload + URL)
- [ ] Gemini key manager
- [ ] Channel manager + OAuth flow

#### Deployment
- [ ] `requirements.txt` final
- [ ] `.env.example`
- [ ] `passenger_wsgi.py` untuk cPanel
- [ ] Panduan setup Laragon (README section)
- [ ] Panduan setup cPanel (README section)

---

### 🔥 PHASE 2 — AI Power Features
**Target: Text-to-Shorts, Trend Scout, Viral Hook Library**  
**Duration: Sprint 3**

#### Backend
- [ ] TrendScout module (Gemini generate + cache 6 jam)
- [ ] API: `/api/trends` + `/api/trends/generate-script` (dengan hook_options + title_variant_b)
- [ ] Text-to-Shorts generator (slide builder + Pillow + gTTS)
- [ ] HookLibrary model + migration
- [ ] API: `/api/hooks` CRUD + best hooks
- [ ] Job wizard: sumber `text_to_shorts`
- [ ] Seeder: 200+ hook pre-built per niche

#### Frontend
- [ ] Trend scouting UI + "buat job dari topik ini"
- [ ] Hook library browser + filter + sort CTR
- [ ] Job wizard tab: AI Generate (slide)
- [ ] Hook picker di job form

---

### ⚡ PHASE 3 — Multi-Platform & A/B Testing
**Target: 1 video → 4 platform, A/B title testing otomatis**  
**Duration: Sprint 4**

#### Backend
- [ ] MultiPlatformExporter: FFmpeg re-encode per platform
- [ ] TikTok Upload API integration
- [ ] Meta Graph API: Instagram Reels + Facebook Reels
- [ ] AbTestResult model + migration
- [ ] API: `/api/jobs/{id}/ab-test`
- [ ] Scheduler: `check_ab_tests` (48 jam CTR fetch + auto-private loser)
- [ ] Smart scheduler: `analyze_best_hours` per channel dari YouTube Analytics
- [ ] Channel model: `best_upload_hours` field

#### Frontend
- [ ] Platform checkboxes di job wizard
- [ ] Per-platform upload status badge
- [ ] A/B test card di job detail
- [ ] Analytics: chart views + A/B results

---

### 🤖 PHASE 4 — Bot & Competitor Spy
**Target: Kontrol via Telegram/WhatsApp, analisis competitor**  
**Duration: Sprint 5**

#### Backend
- [ ] Telegram bot (python-telegram-bot) + FSM
- [ ] WhatsApp bot (Twilio) + FSM
- [ ] BotSession model + migration
- [ ] API: `/api/bot/*` webhook + connect + disconnect
- [ ] CompetitorSpy module (yt-dlp + Gemini analysis)
- [ ] API: `/api/spy/analyze` + history

#### Frontend
- [ ] Bot setup UI (connect Telegram/WhatsApp + QR/link)
- [ ] Competitor spy UI (form URL + report card)
- [ ] Notifikasi toast realtime (job done, upload sukses)

---

### 🏢 PHASE 5 — Reseller / White-label & SaaS Hardening
**Target: Reseller bisa onboard klien dengan brand sendiri**  
**Duration: Sprint 6**

#### Backend
- [ ] Reseller fields di Tenant model + migration
- [ ] ResellerManager module
- [ ] API: `/api/reseller/*`
- [ ] Sub-tenant: inherit branding dari parent
- [ ] Plan limits enforcement (middleware check jobs/bulan, concurrent)
- [ ] Rate limiting (slowapi, 100 req/menit per tenant)
- [ ] YouTube credentials encryption (Fernet)
- [ ] `worker.py` standalone script (untuk cPanel cron tanpa APScheduler)
- [ ] Logging ke file (`logs/app.log`, rotate harian)

#### Frontend
- [ ] Reseller dashboard: sub-tenant list + buat + stats
- [ ] Branding editor (logo, warna, nama)
- [ ] Login page white-label aware (baca branding dari query param `?brand=xxx`)
- [ ] Plan usage indicator di settings

---

### 🔒 PHASE 6 — Production Hardening (Future)
**Duration: Sprint 7+**
- [ ] Billing integration (Midtrans / Stripe)
- [ ] PostgreSQL migration (dari SQLite/MySQL)
- [ ] CDN untuk storage output (Cloudflare R2 / S3)
- [ ] Email notifikasi (job done, upload gagal)
- [ ] API documentation (Swagger UI sudah otomatis via FastAPI)
- [ ] Multi-language UI (EN + ID)
- [ ] Backup otomatis DB harian

---

## 18. Error Handling

| Code | Situasi | Response format |
|------|---------|-----------------|
| 400 | Input tidak valid | `{ "error": "pesan" }` |
| 401 | Token tidak ada/expired | `{ "error": "Unauthorized" }` |
| 403 | Akses data tenant lain | `{ "error": "Forbidden" }` |
| 404 | Resource tidak ditemukan | `{ "error": "Not found" }` |
| 409 | Duplikasi | `{ "error": "Sudah terdaftar" }` |
| 422 | Validasi gagal | Pydantic default |
| 429 | Rate limit | `{ "error": "Too many requests", "retry_after": 60 }` |
| 500 | Error internal | `{ "error": "Internal server error" }` |

Job error: simpan ke `job.error_message`, set `status=failed`.

---

*PRD ini adalah living document. Update setiap ada keputusan arsitektur baru.*  
*Versi sebelumnya: v1.0.0 (2026-07-22) — tanpa multi-platform, bot, spy, reseller*
