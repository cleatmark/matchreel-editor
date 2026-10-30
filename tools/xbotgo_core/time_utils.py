"""Time parsing, formatting, and validation utilities for XbotGo Review Editor.

Exact formatting rules:
- Times are zero-padded 'mm:ss' text, e.g. '04:01'; never '0:mm:ss' or a duration.
- 2-part time 'm:ss' or 'mm:ss' -> total seconds.
- 3-part time:
  - If first part == 0 (e.g. '0:04:01' or '00:04:01') -> 0 hours, 4 mins, 1 sec -> 241 s.
  - If first part != 0 (e.g. '04:01:00') -> Sheets-mangled mm:ss where mm is part[0] and ss is part[1] -> 241 s.
- Video duration for youth soccer rarely exceeds 50 minutes.
"""
from typing import Optional, Tuple


def secs(v: Optional[str]) -> Optional[int]:
    """Parse time string into whole seconds. Returns None if blank or invalid."""
    if v is None:
        return None
    s = str(v).strip()
    if not s or s == "-":
        return None
    parts = s.split(":")
    try:
        parts_int = [int(p) for p in parts]
    except ValueError:
        return None

    if len(parts_int) == 1:
        return None
    if len(parts_int) == 2:
        return parts_int[0] * 60 + parts_int[1]
    if len(parts_int) == 3:
        # If first part is 0, e.g. 0:04:01 -> 0h 4m 1s -> 241s
        if parts_int[0] == 0:
            return parts_int[1] * 60 + parts_int[2]
        # Sheets-mangled '04:01:00' -> 4m 1s -> 241s
        return parts_int[0] * 60 + parts_int[1]
    return None


def format_time(total_seconds: Optional[int]) -> str:
    """Format total seconds into zero-padded 'mm:ss' string.
    If None or negative, returns empty string.
    """
    if total_seconds is None or total_seconds < 0:
        return ""
    total = int(round(total_seconds))
    m = total // 60
    s = total % 60
    return f"{m:02d}:{s:02d}"


def is_valid_time_str(v: Optional[str]) -> bool:
    """Check if input string can be parsed into valid time seconds."""
    return secs(v) is not None


def validate_timing_order(action_start: Optional[str], event: Optional[str], action_end: Optional[str]) -> Tuple[bool, str]:
    """Validate that action_start <= event <= action_end.
    Returns (is_valid, warning_message).
    """
    s = secs(action_start)
    e = secs(event)
    end = secs(action_end)

    if s is None or e is None or end is None:
        return True, ""  # partial/blank row is allowed

    if s > e:
        return False, f"Start ({action_start}) is after Event ({event})"
    if e > end:
        return False, f"Event ({event}) is after End ({action_end})"
    if s > end:
        return False, f"Start ({action_start}) is after End ({action_end})"
    return True, ""
