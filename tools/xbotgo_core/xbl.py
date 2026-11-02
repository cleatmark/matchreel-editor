"""Shared helpers for the per-game tools: sync_game, zoom_edit, verify_zoom, preview_reel.

All tools run from the XbotGo root (the folder that holds out/, tools/, <MM-DD-YY>/) and take --out out/<day>[-gN].
Works with the long (action_start_video...) and short (action_start...) column names.
"""
from . import xb_env  # helper programs in utils\ on PATH
import csv, hashlib, json, os, re, shutil, subprocess, sys, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
from cut_reviewed import plan, secs, row_skip, hhmmss      # noqa: E402  (the cutting rules live there)

PY = sys.executable


def sh(cmd, **kw):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)


def probe_dur(path):
    r = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def is_zoom(row):
    return bool(re.search(r"\bzoom\b", row.get("instructions") or "", re.I))


def move_aside(path, folder):
    """Never delete: move into <folder> with a free name."""
    os.makedirs(folder, exist_ok=True)
    base = os.path.basename(path); dst = os.path.join(folder, base); k = 1
    while os.path.exists(dst):
        k += 1; dst = os.path.join(folder, f"{k}_{base}")
    shutil.move(path, dst)
    return dst


def token_of(name):
    """'003b_goal_001126_zoom3x_720.mp4' / '003_goal_001126_7.mp4' -> 'goal_001126'."""
    m = re.match(r"^\d+b?_((?:goal|mark|[a-z]+)_\d{6})", name)
    return m.group(1) if m else None


class Game:
    def __init__(self, out):
        self.out = out.rstrip("/\\")
        self.base = os.path.basename(self.out)                       # 2026-03-14-g1
        self.root = os.path.dirname(self.out) or "."                 # out
        self.csv = os.path.join(self.root, "reviewed", self.base + "_reviewed.csv")
        self.roster_path = os.path.join(self.root, "reviewed", "roster.csv")
        tl_path = os.path.join(self.out, "timeline.json")
        if not os.path.exists(tl_path) and os.path.exists(os.path.join(self.out, "work", "timeline.json")):
            tl_path = os.path.join(self.out, "work", "timeline.json")
        with open(tl_path, encoding="utf-8") as _f:
            self.tl = json.load(_f)
        self.prefix = re.sub(r"-g(\d)$", lambda m: "_G" + m.group(1), self.base).replace("-", "_")  # 2026_03_14_G1
        self.clipdir = os.path.join(self.out, "clips", "preview720")
        extra_path = os.path.join(self.out, "clips", "extra")
        if not os.path.exists(extra_path) and os.path.exists(os.path.join(self.out, "work", "clips", "extra")):
            extra_path = os.path.join(self.out, "work", "clips", "extra")
        self.extra = extra_path
        sp = os.path.join(self.out, "zoom_state.json")
        if not os.path.exists(sp) and os.path.exists(os.path.join(self.out, "work", "zoom_state.json")):
            sp = os.path.join(self.out, "work", "zoom_state.json")
        self.state_path = sp

    # ---- sheet rows / clips -------------------------------------------------
    def roster(self):
        """Map of player jersey number to full name (backwards compatible)."""
        if os.path.exists(self.roster_path):
            with open(self.roster_path, encoding="utf-8-sig") as f:
                return {
                    str(r.get("no") or r.get("No") or "").strip(): str(r.get("name") or r.get("Player") or "").strip()
                    for r in csv.DictReader(f)
                    if (r.get("no") or r.get("No"))
                }
        return {}

    def roster_records(self):
        """Map of player jersey number to full record dict {name, no, short_name, contact}."""
        if os.path.exists(self.roster_path):
            with open(self.roster_path, encoding="utf-8-sig") as f:
                records = {}
                for r in csv.DictReader(f):
                    num = str(r.get("no") or r.get("No") or "").strip()
                    if num:
                        name = str(r.get("name") or r.get("Player") or "").strip()
                        records[num] = {
                            "no": num,
                            "name": name,
                            "short_name": str(r.get("short_name") or r.get("Short_Name") or (name.split()[0] if name else "")).strip(),
                            "contact": str(r.get("contact") or r.get("Contact") or "").strip()
                        }
                return records
        return {}

    def rows(self):
        with open(self.csv, newline="", encoding="utf-8-sig") as _f:
            return [r for r in csv.DictReader(_f) if (r.get("file") or "").strip()]

    def jobs(self):
        """Same plan cut_reviewed.py makes (n = clip number among non-skipped rows)."""
        return plan(self.rows(), self.tl, self.roster(), 0.5, "startend")

    def video_path(self, fname):
        return next(v["path"] for v in self.tl["videos"] if v["file"] == fname)

    @staticmethod
    def col(row, name):
        v = row.get(name)
        return v if v not in (None,) else row.get(name + "_video")

    def action_end(self, job):
        return secs(self.col(job["row"], "action_end"))

    def token(self, job):
        return token_of(job["clip"])

    def replay_name(self, job, height=720, master=False):
        lab = "720" if height == 720 else str(height)
        return f"{job['n']:03d}b_{self.token(job)}_zoom3x_{lab}.mp4"

    # ---- zoom state ---------------------------------------------------------
    def state(self):
        if os.path.exists(self.state_path):
            with open(self.state_path, encoding="utf-8") as _f:
                return json.load(_f)
        return {"version": 1, "replays": {}, "removed": {}}

    def save_state(self, st):
        from .atomic_io import write_json_atomic
        write_json_atomic(self.state_path, st, indent=1)


def default_window(event, action_end):
    """event-2.5 .. event+2.0 (4.5 s of source; was +3.5 until 2026-03-16); action_end wins when it comes first."""
    start = max(0.0, event - 2.5)
    end = event + 2.0
    if action_end is not None:
        end = min(end, action_end)
    return round(start, 3), round(max(2.0, min(4.5, end - start)), 3)
