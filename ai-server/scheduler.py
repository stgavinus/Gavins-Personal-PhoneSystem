"""
Internal wake-up scheduler.
Uses APScheduler to fire the wake-up trigger at the configured time.
Replaces the Mac cron job — the schedule is managed via the web UI.
"""
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import data_store
from config import settings

_scheduler = AsyncIOScheduler()


def get_scheduler() -> AsyncIOScheduler:
    return _scheduler


def start():
    _scheduler.start()
    sync_job()


def stop():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)


def sync_job():
    """Re-read config and update the scheduled wake-up job."""
    cfg = data_store.load()
    schedule = cfg.get("schedule", {})
    _scheduler.remove_all_jobs()

    if schedule.get("enabled"):
        hour = schedule.get("hour", 8)
        minute = schedule.get("minute", 0)
        tz = schedule.get("timezone", "America/New_York")
        _scheduler.add_job(
            _fire_wakeup,
            CronTrigger(hour=hour, minute=minute, timezone=tz),
            id="wakeup",
            replace_existing=True,
        )
        print(f"[scheduler] wake-up job set for {hour:02d}:{minute:02d} {tz}")
    else:
        print("[scheduler] wake-up job disabled")


async def _fire_wakeup():
    print("[scheduler] firing scheduled wake-up")
    data_store.log_call("scheduled_trigger", "Scheduler fired wake-up")
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                f"http://localhost:{settings.ai_server_port}/trigger/wakeup",
                headers={"X-API-Key": settings.ai_server_api_key},
                timeout=10,
            )
            print(f"[scheduler] trigger response: {r.status_code}")
        except Exception as e:
            print(f"[scheduler] trigger failed: {e}")
