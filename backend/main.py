import logging
import os
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.core.config import settings
from backend.core.database import Base, engine
from backend.modules.scheduler.scheduler import start_scheduler, stop_scheduler
from backend.api import auth, keys, channels, jobs, trends, analytics, hooks, spy, bot, reseller

# ─── Logging setup ───────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s [%(request_id)s] %(message)s"
    if False  # Custom filter below handles this
    else "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger(__name__)


# ─── DB Migration helper ─────────────────────────────────────────────────

def _migrate_db():
    """
    Tambahkan kolom baru ke tabel yang sudah ada.
    SQLite tidak support ALTER TABLE ... ADD COLUMN IF NOT EXISTS,
    jadi kita pakai PRAGMA table_info untuk cek dulu.
    """
    from sqlalchemy import text, inspect

    NEW_COLUMNS = {
        "tenants": [
            ("is_reseller",              "BOOLEAN DEFAULT 0"),
            ("parent_tenant_id",         "VARCHAR"),
            ("brand_name",               "VARCHAR"),
            ("brand_logo_url",           "VARCHAR"),
            ("brand_color",              "VARCHAR"),
            ("telegram_chat_id",         "VARCHAR"),
            ("whatsapp_number",          "VARCHAR"),
            ("bot_active",               "BOOLEAN DEFAULT 0"),
            ("telegram_bot_credentials", "TEXT"),
            ("whatsapp_credentials",     "TEXT"),
        ],
        "gemini_keys": [
            ("label",              "VARCHAR DEFAULT ''"),
            ("usage_count",        "INTEGER DEFAULT 0"),
            ("last_used_at",       "DATETIME"),
            ("provider",           "VARCHAR DEFAULT 'gemini'"),
        ],
        "channels": [
            ("youtube_channel_id", "VARCHAR"),
            ("subscriber_count",   "INTEGER DEFAULT 0"),
            ("best_upload_hours",  "JSON"),
            ("tiktok_credentials", "TEXT"),
            ("tiktok_open_id",     "VARCHAR"),
            ("meta_credentials",   "TEXT"),
            ("meta_page_id",       "VARCHAR"),
            ("meta_ig_user_id",    "VARCHAR"),
        ],
        "video_jobs": [
            ("hook_library_id",    "VARCHAR"),
            ("title_variant_b",    "VARCHAR"),
            ("platforms",          "JSON"),
            ("ab_test_active",     "BOOLEAN DEFAULT 0"),
            ("ab_winner",          "VARCHAR"),
            ("tiktok_video_id",    "VARCHAR"),
            ("instagram_media_id", "VARCHAR"),
            ("youtube_video_id_b", "VARCHAR"),
            ("facebook_video_id",  "VARCHAR"),
            ("description",        "TEXT"),
            ("updated_at",         "DATETIME"),
        ],
    }

    with engine.connect() as conn:
        for table, cols in NEW_COLUMNS.items():
            # Ambil kolom yang sudah ada
            try:
                result = conn.execute(text(f"PRAGMA table_info({table})"))
                existing = {row[1] for row in result}
            except Exception:
                existing = set()

            for col_name, col_type in cols:
                if col_name not in existing:
                    try:
                        conn.execute(text(
                            f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"
                        ))
                        conn.commit()
                        log.info(f"Migration: added {table}.{col_name}")
                    except Exception as e:
                        log.warning(f"Migration skip {table}.{col_name}: {e}")


# ─── Simple in-memory rate limiter ───────────────────────────────────────

_rate_counters: dict = defaultdict(list)

def _is_rate_limited(key: str, limit: int, window: int = 60) -> bool:
    """Sliding window rate limiter. Returns True jika melebihi limit."""
    now = time.time()
    calls = _rate_counters[key]
    # Hapus entri di luar window
    _rate_counters[key] = [t for t in calls if now - t < window]
    if len(_rate_counters[key]) >= limit:
        return True
    _rate_counters[key].append(now)
    return False


# ─── Lifespan ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Base.metadata.create_all(bind=engine)
    _migrate_db()
    start_scheduler()
    os.makedirs("storage/shared/music", exist_ok=True)

    # Seed global hook library
    try:
        from backend.core.database import SessionLocal
        from backend.modules.hook_library.library import seed_global_hooks
        db = SessionLocal()
        added = seed_global_hooks(db)
        db.close()
        if added:
            log.info(f"Seeded {added} global hooks")
    except Exception as e:
        log.warning(f"Hook seed skipped: {e}")

    log.info(f"{settings.APP_NAME} v{settings.APP_VERSION} started")
    yield

    # Shutdown
    stop_scheduler()
    log.info(f"{settings.APP_NAME} stopped")


# ─── App ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


# ─── Middleware: CORS ─────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Middleware: Request ID + logging ────────────────────────────────────

@app.middleware("http")
async def request_id_middleware(request: Request, call_next: Callable):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    start = time.time()
    response: Response = await call_next(request)
    duration_ms = int((time.time() - start) * 1000)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{duration_ms}ms"
    log.info(
        f"{request.method} {request.url.path} → {response.status_code} "
        f"({duration_ms}ms) [req:{request_id}]"
    )
    return response


# ─── Middleware: Rate limiting ────────────────────────────────────────────

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next: Callable):
    # Hanya limit API endpoints, bukan static files
    if not request.url.path.startswith("/api/"):
        return await call_next(request)

    # Identifikasi berdasarkan IP (anonymous) atau token sub (authenticated)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        # Attempt to extract tenant_id untuk rate key yang lebih granular
        try:
            from backend.core.security import decode_token
            payload = decode_token(auth_header[7:])
            tenant_id = payload.get("sub", "") if payload else ""
            rate_key = f"tenant:{tenant_id}"
            # Plan-based limit — cek dari DB
            from backend.core.database import SessionLocal
            from backend.models.models import Tenant as TenantModel
            from backend.core.plan_limits import get_limits
            db = SessionLocal()
            try:
                tenant = db.query(TenantModel).filter(TenantModel.id == tenant_id).first()
                limit = get_limits(tenant).rate_limit_per_minute if tenant else 20
            finally:
                db.close()
        except Exception:
            rate_key = f"ip:{request.client.host}"
            limit = 20
    else:
        rate_key = f"ip:{request.client.host}"
        limit = 30  # anonymous: lebih longgar untuk auth endpoints

    if _is_rate_limited(rate_key, limit):
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "message": f"Terlalu banyak request. Coba lagi dalam 1 menit.",
                "retry_after": 60,
            },
            headers={"Retry-After": "60"},
        )
    return await call_next(request)


# ─── Global exception handler ─────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    log.error(f"Unhandled error [{request_id}] {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "request_id": request_id,
        },
    )


# ─── API routes ───────────────────────────────────────────────────────────

app.include_router(auth.router,      prefix="/api/auth",      tags=["Auth"])
app.include_router(keys.router,      prefix="/api/keys",      tags=["Gemini Keys"])
app.include_router(channels.router,  prefix="/api/channels",  tags=["Channels"])
app.include_router(jobs.router,      prefix="/api/jobs",      tags=["Jobs"])
app.include_router(trends.router,    prefix="/api/trends",    tags=["Trends"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(hooks.router,     prefix="/api/hooks",     tags=["Hook Library"])
app.include_router(spy.router,       prefix="/api/spy",       tags=["Competitor Spy"])
app.include_router(bot.router,       prefix="/api/bot",       tags=["Bot"])
app.include_router(reseller.router,  prefix="/api/reseller",  tags=["Reseller"])


# ─── Static files + SPA ──────────────────────────────────────────────────

frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/api/health")
def health():
    from backend.core.database import SessionLocal
    db_ok = True
    try:
        db = SessionLocal()
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db.close()
    except Exception:
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "version": settings.APP_VERSION,
        "database": "ok" if db_ok else "error",
        "scheduler": "running",
    }


@app.get("/api/plans")
def get_plans():
    """Info plan limits — publik."""
    from backend.core.plan_limits import PLAN_LIMITS
    return {
        plan: {
            "max_channels": limits.max_channels,
            "max_gemini_keys": limits.max_gemini_keys,
            "max_jobs_per_day": limits.max_jobs_per_day,
            "can_use_ab_test": limits.can_use_ab_test,
            "can_use_multi_platform": limits.can_use_multi_platform,
            "can_use_competitor_spy": limits.can_use_competitor_spy,
            "rate_limit_per_minute": limits.rate_limit_per_minute,
        }
        for plan, limits in PLAN_LIMITS.items()
    }


@app.get("/{full_path:path}")
async def spa_fallback(request: Request, full_path: str):
    if full_path.startswith("api/"):
        return JSONResponse({"error": "Not found"}, status_code=404)
    index = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return JSONResponse({"message": f"{settings.APP_NAME} API running."})
