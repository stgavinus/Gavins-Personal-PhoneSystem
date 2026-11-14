"""
POST /trigger/call — place an outbound call to an extension and connect it
to the AudioSocket bridge (extension 200 in the from-internal dialplan).
"""
import socket
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from config import settings

router = APIRouter()


def _require_api_key(x_api_key: str | None):
    if x_api_key != settings.ai_server_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


class CallRequest(BaseModel):
    extension: str = "101"


@router.post("/call")
def trigger_call(
    req: CallRequest = CallRequest(),
    x_api_key: str | None = Header(default=None),
):
    """Call an extension and connect it to the AI voice bridge."""
    _require_api_key(x_api_key)
    _ami_originate(req.extension)
    return {"status": "started", "extension": req.extension}


def _ami_originate(extension: str):
    """Dial extension via AMI; on answer, route to from-internal/200 (AudioSocket bridge)."""
    try:
        with socket.create_connection((settings.ami_host, settings.ami_port), timeout=10) as sock:
            buf = b""
            while b"\n" not in buf:
                buf += sock.recv(256)

            sock.sendall((
                f"Action: Login\r\n"
                f"Username: {settings.ami_user}\r\n"
                f"Secret: {settings.ami_secret}\r\n"
                f"Events: off\r\n\r\n"
            ).encode())
            _read_message(sock)

            sock.sendall((
                f"Action: Originate\r\n"
                f"Channel: PJSIP/{extension}\r\n"
                f"Application: AudioSocket\r\n"
                f"Data: 40325ec2-5b17-4d7c-8df2-36b4c9d4e7a1,localhost:9093\r\n"
                f"Timeout: 30000\r\n"
                f"Async: true\r\n\r\n"
            ).encode())
            _read_message(sock)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AMI error: {e}")


def _read_message(sock: socket.socket) -> str:
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    return buf.decode(errors="replace")
