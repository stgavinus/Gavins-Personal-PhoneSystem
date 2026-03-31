#!/usr/bin/env python3
"""
Asterisk AGI script — inbound AI conversation.
User dials extension 200, AI picks up and has a free-form conversation.
"""
import sys
import os
import tempfile
import subprocess
import requests

AI_SERVER = "http://ai-server:8000"


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
    slin_path = wav_path + ".sln"
    subprocess.run(
        ["ffmpeg", "-y", "-i", wav_path,
         "-ar", "8000", "-ac", "1", "-f", "s16le", slin_path],
        check=True, capture_output=True
    )
    base = slin_path[:-4]
    agi_send(f"STREAM FILE {base} \"\"")
    os.unlink(slin_path)


def record_speech(max_silence: int = 2, timeout: int = 30) -> str | None:
    with tempfile.NamedTemporaryFile(suffix="", delete=False,
                                     dir="/tmp", prefix="conv_rec_") as f:
        base = f.name
    res = agi_send(
        f"RECORD FILE {base} wav \"#\" {timeout * 1000} s={max_silence}"
    )
    wav = base + ".wav"
    exists = os.path.exists(wav)
    size = os.path.getsize(wav) if exists else -1
    if exists and size > 44:
        return wav
    return None


def main():
    _env = agi_read_vars()
    call_id = sys.argv[1] if len(sys.argv) > 1 else "unknown"

    agi_send("ANSWER")

    # Opening greeting
    try:
        r = requests.post(
            f"{AI_SERVER}/api/converse/greet",
            data={"call_id": call_id},
            timeout=30,
        )
        r.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(r.content)
            greeting_wav = f.name
        play_wav(greeting_wav)
        os.unlink(greeting_wav)
    except Exception as e:
        agi_send(f"VERBOSE \"Greet error: {e}\" 1")
        agi_send("HANGUP")
        return

    # Conversation loop
    while True:
        wav_path = record_speech(max_silence=2, timeout=30)

        if not wav_path:
            continue

        try:
            with open(wav_path, "rb") as af:
                r = requests.post(
                    f"{AI_SERVER}/api/converse/process",
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

        if action == "end_call":
            break

    agi_send("HANGUP")


if __name__ == "__main__":
    main()
