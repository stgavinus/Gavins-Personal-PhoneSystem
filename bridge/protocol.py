"""
AudioSocket frame codec.

Wire format (Asterisk app_audiosocket):
    [type: 1 byte][length: 2 bytes big-endian][payload: <length> bytes]

Audio format: slin16 — signed 16-bit little-endian PCM, 8 kHz mono.
Each frame from Asterisk is 320 bytes = 160 samples = 20 ms.
"""
import asyncio
import struct

# ── Frame type constants ───────────────────────────────────────────────────────
HANGUP = 0x00  # no payload — call ended
UUID   = 0x01  # 16-byte string — call identifier sent first
AUDIO  = 0x10  # slin16 payload
ERROR  = 0xFF  # error string payload

# Audio geometry
SAMPLE_RATE   = 8_000   # Hz
SAMPLE_WIDTH  = 2       # bytes (int16)
FRAME_MS      = 20      # milliseconds per frame
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000   # 160
FRAME_BYTES   = FRAME_SAMPLES * SAMPLE_WIDTH      # 320


async def read_frame(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    """
    Read exactly one AudioSocket frame from *reader*.

    Raises asyncio.IncompleteReadError on EOF.
    """
    header = await reader.readexactly(3)
    ftype  = header[0]
    flen   = struct.unpack(">H", header[1:3])[0]
    payload = await reader.readexactly(flen) if flen else b""
    return ftype, payload


def build_frame(ftype: int, payload: bytes = b"") -> bytes:
    """Serialize one AudioSocket frame."""
    return bytes([ftype]) + struct.pack(">H", len(payload)) + payload


def iter_pcm_frames(raw_pcm: bytes) -> list[bytes]:
    """
    Split a raw PCM buffer into FRAME_BYTES-sized chunks suitable for sending
    back to Asterisk one audio frame at a time.  The last chunk is zero-padded
    if it is shorter than FRAME_BYTES.
    """
    frames = []
    for i in range(0, len(raw_pcm), FRAME_BYTES):
        chunk = raw_pcm[i : i + FRAME_BYTES]
        if len(chunk) < FRAME_BYTES:
            chunk = chunk + b"\x00" * (FRAME_BYTES - len(chunk))
        frames.append(chunk)
    return frames
