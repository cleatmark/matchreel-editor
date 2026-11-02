"""Locate videos and the app-data folder in a day dump, whatever the layout.

Layouts seen so far (all supported):
  <day>/Videos/*.mp4                 + <day>/com.blink.blinkfocos/files     (from 2026-03-21; source videos in Videos)
  <day>/DCIM/XbotGo/*.mp4            + <day>/Android/data/com.blink.blinkfocos/files   (2026-03-05 .. 10-12)
  <day>/Internal shared storage/...  (older; found by walking)
"""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils\ on PATH
import os, re

VIDEO_RE = re.compile(r'^(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})_(\d{13})\.mp4$', re.I)


def find_video_dir(day):
    """Directory that holds the <date>-<time>_<epochms>.mp4 sources (the .pending-* stubs never match)."""
    for dirpath, dirnames, files in os.walk(day):
        if any(VIDEO_RE.match(f) for f in files):
            return dirpath
    return None


def find_appdir(day):
    """.../com.blink.blinkfocos/files, directly under the day or under Android/data."""
    for dirpath, dirnames, files in os.walk(day):
        if os.path.basename(dirpath) == "files" and os.path.basename(os.path.dirname(dirpath)) == "com.blink.blinkfocos":
            return dirpath
    return None


def list_videos(day, names=None):
    d = find_video_dir(day)
    if d is None:
        raise SystemExit(f"no XbotGo videos (<date>_<epochms>.mp4) under {day}")
    fs = sorted(f for f in os.listdir(d) if VIDEO_RE.match(f))
    if names:
        fs = [f for f in names if f in fs] if all(n in fs for n in names) else names
    return d, fs
