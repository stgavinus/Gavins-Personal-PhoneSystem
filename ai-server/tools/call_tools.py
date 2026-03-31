"""
Call control tools. These return a signal string that the AGI script
interprets to control the call.
"""


def confirm_awake() -> dict:
    """User has confirmed they're awake. Stop retrying."""
    return {"action": "confirm_awake"}


def end_call() -> dict:
    """Hang up the call."""
    return {"action": "end_call"}
