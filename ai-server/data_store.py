"""
Persistent JSON config overlay.
Stores schedule, prompt overrides, and settings that the web UI can change.
Lives in /app/data/config.json (mounted volume — survives container rebuilds).
"""
import json
from pathlib import Path
from typing import Any

DATA_FILE = Path("/app/data/config.json")

DEFAULTS: dict[str, Any] = {
    "schedule": {
        "enabled": False,
        "hour": 8,
        "minute": 0,
        "timezone": "America/New_York",
    },
    "prompts": {
        "conversation": "",   # empty = use agent's built-in default
        "wakeup": "",
    },
    "call_log": [],           # last N call events
}


def load() -> dict:
    if DATA_FILE.exists():
        with open(DATA_FILE) as f:
            stored = json.load(f)
        return _deep_merge(_copy_defaults(), stored)
    return _copy_defaults()


def save(data: dict):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def patch(section: str, values: dict):
    """Update one section and save. Returns full config."""
    cfg = load()
    cfg.setdefault(section, {}).update(values)
    save(cfg)
    return cfg


def log_call(event: str, detail: str = ""):
    """Append a call event to the log (keep last 50)."""
    from datetime import datetime
    cfg = load()
    entry = {"time": datetime.utcnow().isoformat(), "event": event, "detail": detail}
    log = cfg.setdefault("call_log", [])
    log.append(entry)
    cfg["call_log"] = log[-50:]
    save(cfg)


def _copy_defaults() -> dict:
    import copy
    return copy.deepcopy(DEFAULTS)


def _deep_merge(base: dict, override: dict) -> dict:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base
