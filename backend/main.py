import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.core.config import settings
from backend.core.database import Base, engine
from backend.modules.scheduler.scheduler import start_scheduler, stop_scheduler
from backend.api import auth, keys, channels, jobs, trends, analytics, hooks, spy, bot, reseller


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Base.metadata.create_all(bind=engine)
    start_scheduler()
    # Ensure storage dirs exist
    os.makedirs("storage/shared/music", exist_ok=True)
    # Seed global hook library
    try:
        from backend.core.database import SessionLocal
        from backend.modules.hook_library.library import seed_global_hooks
        db = SessionLocal()
        added = seed_global_hooks(db)
        db.close()
        if added:
            import logging
            logging.getLogger(__name__).info(f"Seeded {added} global hooks")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Hook seed skipped: {e}")
    yield
    # Shutdown
    stop_scheduler()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
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

# Serve frontend static files
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/api/health")
def health():
    return {"status": "ok", "version": settings.APP_VERSION}


# SPA fallback — serve index.html for all non-API routes
@app.get("/{full_path:path}")
async def spa_fallback(request: Request, full_path: str):
    if full_path.startswith("api/"):
        return JSONResponse({"error": "Not found"}, status_code=404)
    index = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return JSONResponse({"message": f"{settings.APP_NAME} API running. Frontend not built yet."})
