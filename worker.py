"""
Standalone worker script — untuk cPanel Cron Jobs atau Laragon.
Jalankan setiap menit via cron:
  * * * * * /path/to/venv/bin/python /path/to/worker.py

Atau jalankan terus di background:
  nohup python worker.py &
"""
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/worker.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


def run():
    from backend.core.database import Base, engine, SessionLocal
    from backend.modules.scheduler.scheduler import check_pending_jobs, check_scheduled_uploads, cleanup_old_files

    # Init DB
    Base.metadata.create_all(bind=engine)
    log.info("Worker started")

    import os
    os.makedirs("logs", exist_ok=True)

    cycle = 0
    while True:
        try:
            check_pending_jobs()
            check_scheduled_uploads()
            if cycle % 86400 == 0:   # once per day
                cleanup_old_files()
            cycle += 60
        except Exception as e:
            log.error(f"Worker error: {e}")
        time.sleep(30)


if __name__ == "__main__":
    run()
