"""
/trigger — scheduler-agnostic endpoints.
Anything (cron, n8n, Python script, curl) can POST here to start a call.
"""
import asyncio
import os
import socket
import uuid
from datetime import datetime
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from config import settings

router = APIRouter()

FLAG_DIR = "/tmp/wakeup"


def _require_api_key(x_api_key: str | None):
    if x_api_key != settings.ai_server_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


class WakeupRequest(BaseModel):
    extension: str | None = None
    retry_interval: int | None = None
    max_retries: int | None = None


@router.post("/wakeup")
async def trigger_wakeup(
    req: WakeupRequest = WakeupRequest(),
    x_api_key: str | None = Header(default=None),
):
    """Trigger the wake-up call sequence. Returns immediately, runs in background."""
    _require_api_key(x_api_key)

    extension = req.extension or settings.wakeup_extension
    retry_interval = req.retry_interval or settings.wakeup_retry_interval
    max_retries = req.max_retries or settings.wakeup_max_retries

    asyncio.create_task(_run_wakeup_sequence(extension, retry_interval, max_retries))
    return {
        "status": "started",
        "extension": extension,
        "at": datetime.utcnow().isoformat(),
    }


async def _run_wakeup_sequence(extension: str, retry_interval: int, max_retries: int):
    session_id = str(uuid.uuid4())[:8]
    confirmed_flag = os.path.join(FLAG_DIR, f"confirmed_{session_id}")

    os.makedirs(FLAG_DIR, exist_ok=True)
    if os.path.exists(confirmed_flag):
        os.unlink(confirmed_flag)

    for attempt in range(1, max_retries + 1):
        print(f"[wakeup] attempt {attempt}/{max_retries} → ext {extension}")
        call_id = str(uuid.uuid4())
        _ami_originate(extension, call_id, confirmed_flag)

        await asyncio.sleep(retry_interval)

        if os.path.exists(confirmed_flag):
            print(f"[wakeup] confirmed awake after {attempt} attempt(s)")
            os.unlink(confirmed_flag)
            return

    print(f"[wakeup] max retries reached for ext {extension}")


def _ami_read_message(sock: socket.socket) -> str:
    """Read one complete AMI message (ends with blank line)."""
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    return buf.decode(errors="replace")


def _ami_originate(extension: str, call_id: str, confirmed_flag: str):
    """Place a call via Asterisk Manager Interface."""
    try:
        with socket.create_connection((settings.ami_host, settings.ami_port), timeout=10) as sock:
            # Banner is a single line, not a blank-line-terminated message
            buf = b""
            while b"\n" not in buf:
                buf += sock.recv(256)

            login = (
                f"Action: Login\r\n"
                f"Username: {settings.ami_user}\r\n"
                f"Secret: {settings.ami_secret}\r\n"
                f"Events: off\r\n"
                f"\r\n"
            )
            sock.sendall(login.encode())
            login_resp = _ami_read_message(sock)
            if "Success" not in login_resp:
                print(f"[wakeup] AMI login failed: {login_resp!r}")
                return

            action = (
                f"Action: Originate\r\n"
                f"Channel: PJSIP/{extension}\r\n"
                f"Application: AGI\r\n"
                f"Data: wakeup.py,{call_id},{confirmed_flag}\r\n"
                f"Timeout: 30000\r\n"
                f"Async: true\r\n"
                f"\r\n"
            )
            sock.sendall(action.encode())
            orig_resp = _ami_read_message(sock)
            print(f"[wakeup] AMI originate response: {orig_resp!r}")
        print(f"[wakeup] AMI originate sent for {extension}, call_id={call_id}")
    except Exception as e:
        print(f"[wakeup] AMI originate failed: {e}")
