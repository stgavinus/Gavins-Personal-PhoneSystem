#!/usr/bin/env python3
"""
Asterisk AGI script — runs inside the asterisk container during a live call.

Called via Asterisk call file:
  Application=AGI
  Data=wakeup.py,<call_id>,<confirmed_flag_path>

The ai-server is reachable at http://ai-server:8000 via Docker network.
"""
import sys
import os
import tempfile
import subprocess
import requests

AI_SERVER = "http://ai-server:8000"

# ── AGI protocol helpers ──────────────────────────────────────────────────────

def agi_send(cmd: str) -> str:
    sys.stdout.write(cmd + "\n")
    sys.stdout.flush()
    return sys.stdin.readline().strip()


def agi_read_vars() -> dict:
    env = {}
    while True:
        line = sys.stdin.readline().strip()
        if not line:
            break
        if ":" in line:
            k, v = line.split(":", 1)
            env[k.strip()] = v.strip()
    return env


def play_wav(wav_path: str):
    """Convert AI server WAV response to 8kHz slin and play it."""
    slin_path = wav_path + ".sln"
    subprocess.run(
        ["ffmpeg", "-y", "-i", wav_path,
         "-ar", "8000", "-ac", "1", "-f", "s16le", slin_path],
        check=True, capture_output=True
    )
    base = slin_path[:-4]  # strip .sln — Asterisk adds it
    agi_send(f"STREAM FILE {base} \"\"")
    os.unlink(slin_path)


def record_speech(max_silence: int = 3, timeout: int = 10) -> str | None:
    """
    Record caller speech. Returns path to .wav file or None if nothing recorded.
    Asterisk appends .wav automatically.
    """
    with tempfile.NamedTemporaryFile(suffix="", delete=False,
                                     dir="/tmp", prefix="wakeup_rec_") as f:
        base = f.name

    res = agi_send(
        f"RECORD FILE {base} wav \"#\" {timeout * 1000} s={max_silence}"
    )
    wav = base + ".wav"
    exists = os.path.exists(wav)
    size = os.path.getsize(wav) if exists else -1
    agi_send(f"VERBOSE \"record_speech: res={res!r} exists={exists} size={size}\" 1")
    if exists and size > 44:
        return wav
    return None


def hangup():
    agi_send("HANGUP")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    _env = agi_read_vars()

    args = sys.argv[1:]
    if len(args) < 2:
        hangup()
        return

    call_id = args[0]
    confirmed_flag = args[1]

    agi_send("ANSWER")

    # ── Opening greeting ──────────────────────────────────────────
    try:
        r = requests.post(
            f"{AI_SERVER}/api/greet",
            data={"call_id": call_id},
            timeout=30,
        )
        r.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(r.content)
            greeting_wav = f.name

        play_wav(greeting_wav)
        os.unlink(greeting_wav)

        if r.headers.get("X-Action") == "confirm_awake":
            open(confirmed_flag, "w").close()
            hangup()
            return

    except Exception as e:
        agi_send(f"VERBOSE \"Greet error: {e}\" 1")
        hangup()
        return

    # ── Conversation loop ─────────────────────────────────────────
    while True:
        wav_path = record_speech(max_silence=1, timeout=10)

        if not wav_path:
            # Silence or timeout — prompt again
            continue

        try:
            with open(wav_path, "rb") as af:
                r = requests.post(
                    f"{AI_SERVER}/api/process",
                    data={"call_id": call_id},
                    files={"audio": ("audio.wav", af, "audio/wav")},
                    timeout=60,
                )
            r.raise_for_status()
            action = r.headers.get("X-Action", "continue")

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(r.content)
                resp_wav = f.name

            play_wav(resp_wav)
            os.unlink(resp_wav)

        except Exception as e:
            agi_send(f"VERBOSE \"Process error: {e}\" 1")
            break
        finally:
            try:
                os.unlink(wav_path)
            except Exception:
                pass

        if action in ("confirm_awake", "end_call"):
            if action == "confirm_awake":
                open(confirmed_flag, "w").close()
            break

    hangup()


if __name__ == "__main__":
    main()
