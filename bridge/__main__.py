"""
AudioSocket Bridge Server — entry point.

Run with:
    python -m bridge

Environment variables (required):
    DEEPGRAM_API_KEY

Optional:
    BRIDGE_HOST        (default 0.0.0.0)
    BRIDGE_PORT        (default 9093)
    BRAIN_URL          (default http://localhost:8000)
    TTS_DEEPGRAM_VOICE (default aura-asteria-en)
    LOG_LEVEL          (default INFO)
"""
import asyncio
import os
import signal
import sys

from bridge.log import configure as configure_logging, get_logger, BoundLogger
from bridge.session import CallSession

_HOST = os.environ.get("BRIDGE_HOST", "0.0.0.0")
_PORT = int(os.environ.get("BRIDGE_PORT", "9093"))

configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
log = BoundLogger(get_logger("bridge.server"))


async def handle_connection(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    peer = writer.get_extra_info("peername", ("?", 0))
    bound = BoundLogger(get_logger("bridge.session"), peer=f"{peer[0]}:{peer[1]}")
    session = CallSession(reader, writer, bound)
    await session.run()


async def main() -> None:
    # Validate required env vars before binding
    missing = [k for k in ("DEEPGRAM_API_KEY",) if not os.environ.get(k)]
    if missing:
        log.error("missing_env_vars", vars=", ".join(missing))
        sys.exit(1)

    server = await asyncio.start_server(handle_connection, _HOST, _PORT)
    addrs = [str(s.getsockname()) for s in server.sockets]
    log.info("bridge_listening", host=_HOST, port=_PORT, addrs=addrs)

    loop = asyncio.get_running_loop()
    stop = loop.create_future()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set_result, sig)

    async with server:
        log.info("bridge_ready")
        await stop  # blocks until SIGINT/SIGTERM

    log.info("bridge_shutdown")


asyncio.run(main())
