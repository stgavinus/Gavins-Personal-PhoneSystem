"""
Web management UI.
Serves a browser interface at / for managing schedule, settings, and prompts.
Protected by HTTP Basic Auth (WEB_USERNAME / WEB_PASSWORD in .env).
"""
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

import data_store
import scheduler as sched
from agents.conversation_agent import SYSTEM_PROMPT as CONV_DEFAULT
from agents.wakeup_agent import SYSTEM_PROMPT as WAKEUP_DEFAULT
from config import settings

router = APIRouter()
templates = Jinja2Templates(directory="templates")
_security = HTTPBasic()

TIMEZONES = [
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Phoenix",
    "America/Anchorage",
    "Pacific/Honolulu",
    "UTC",
]


def _auth(credentials: HTTPBasicCredentials = Depends(_security)):
    ok = secrets.compare_digest(
        credentials.username.encode(), settings.web_username.encode()
    ) and secrets.compare_digest(
        credentials.password.encode(), settings.web_password.encode()
    )
    if not ok:
        raise HTTPException(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Phone System"'},
        )
    return credentials.username


# ── Pages ──────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def index(request: Request, _=Depends(_auth)):
    cfg = data_store.load()
    schedule = cfg["schedule"]
    prompts = cfg["prompts"]
    call_log = list(reversed(cfg.get("call_log", [])))[:20]

    # Next run time
    next_run = None
    job = sched.get_scheduler().get_job("wakeup")
    if job and job.next_run_time:
        next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M %Z")

    return templates.TemplateResponse("index.html", {
        "request": request,
        "schedule": schedule,
        "prompts": prompts,
        "settings": settings,
        "call_log": call_log,
        "next_run": next_run,
        "timezones": TIMEZONES,
        "conv_default": CONV_DEFAULT,
        "wakeup_default": WAKEUP_DEFAULT,
    })


# ── API endpoints (return HTML fragments for HTMX) ─────────────────────────

@router.post("/web/schedule", response_class=HTMLResponse)
async def save_schedule(
    _=Depends(_auth),
    enabled: bool = Form(False),
    hour: int = Form(8),
    minute: int = Form(0),
    timezone: str = Form("America/New_York"),
):
    data_store.patch("schedule", {
        "enabled": enabled,
        "hour": max(0, min(23, hour)),
        "minute": max(0, min(59, minute)),
        "timezone": timezone,
    })
    sched.sync_job()

    job = sched.get_scheduler().get_job("wakeup")
    next_run = None
    if job and job.next_run_time:
        next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M %Z")

    status = f"Next run: {next_run}" if next_run else "Schedule disabled."
    return _toast("Schedule saved. " + status, "success")


@router.post("/web/prompts", response_class=HTMLResponse)
async def save_prompts(
    _=Depends(_auth),
    conversation: str = Form(""),
    wakeup: str = Form(""),
):
    data_store.patch("prompts", {
        "conversation": conversation.strip(),
        "wakeup": wakeup.strip(),
    })
    return _toast("Prompts saved. Active on next call.", "success")


@router.post("/web/prompts/reset", response_class=HTMLResponse)
async def reset_prompts(
    _=Depends(_auth),
    which: str = Form(...),
):
    cfg = data_store.load()
    if which == "conversation":
        cfg["prompts"]["conversation"] = ""
    elif which == "wakeup":
        cfg["prompts"]["wakeup"] = ""
    data_store.save(cfg)
    return _toast(f"{which.title()} prompt reset to default.", "success")


@router.post("/web/trigger", response_class=HTMLResponse)
async def manual_trigger(_=Depends(_auth)):
    import httpx
    data_store.log_call("manual_trigger", "Triggered from web UI")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"http://localhost:{settings.ai_server_port}/trigger/wakeup",
                headers={"X-API-Key": settings.ai_server_api_key},
                timeout=10,
            )
        if r.status_code == 200:
            return _toast("Wake-up call started.", "success")
        return _toast(f"Trigger failed: HTTP {r.status_code}", "error")
    except Exception as e:
        return _toast(f"Trigger failed: {e}", "error")


def _toast(message: str, kind: str = "success") -> HTMLResponse:
    color = "#2ecc71" if kind == "success" else "#e74c3c"
    html = f'<div class="toast" style="background:{color}">{message}</div>'
    return HTMLResponse(html)
