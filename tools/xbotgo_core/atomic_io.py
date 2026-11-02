"""Crash-safe small-file writes: write to a temp file in the same folder, then os.replace.

A plain open(path, "w") truncates the file first, so a crash or power loss mid-write leaves an empty or half
file (zoom_state.json, game_info.json, roster.csv ...). With these helpers the old file stays until the new one is complete.
"""
import json
import os
import tempfile


def _atomic(path, writer, newline=None):
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as f:
            writer(f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def write_json_atomic(path, obj, indent=1):
    _atomic(path, lambda f: json.dump(obj, f, indent=indent))


def write_text_atomic(path, text, newline=None):
    _atomic(path, lambda f: f.write(text), newline=newline)
