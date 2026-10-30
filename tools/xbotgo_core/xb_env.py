"""Put the helper programs in C:\\temp\\XbotGo\\utils on PATH for this process (import it first in every tool script).

utils\\ffmpeg\\bin (ffmpeg, ffprobe), utils\\tesseract (tesseract, with tessdata), utils\\yt-dlp, utils\\scrcpy, utils\\untrunc_x64.
Only folders that exist are added, so it is harmless on the cloud VM. Nothing outside the XbotGo folder is touched."""
import os

ROOT = os.environ.get("XBOTGO_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # XBOTGO_ROOT lets a copy/container point at the data folder
UTILS = os.path.join(ROOT, "utils")
DIRS = [os.path.join(UTILS, "ffmpeg", "bin"), os.path.join(UTILS, "tesseract"), os.path.join(UTILS, "yt-dlp"), os.path.join(UTILS, "scrcpy"), os.path.join(UTILS, "untrunc_x64")]

def _add():
    cur = os.environ.get("PATH", "").split(os.pathsep)
    new = [d for d in DIRS if os.path.isdir(d) and d not in cur]
    if new: os.environ["PATH"] = os.pathsep.join(new + cur)
    td = os.path.join(UTILS, "tesseract", "tessdata")
    if os.path.isdir(td): os.environ.setdefault("TESSDATA_PREFIX", td)

def which(name):
    """Full path of a helper program: utils/ first (already on PATH after _add), then the system PATH; None if missing."""
    import shutil
    return shutil.which(name)

def tmp_for(p):
    """Scratch location for anything under out\\<game>\\...: C:\\temp\\XbotGo\\tmp\\<game>\\... (mirrors the out tree). All temp files and folders go under tmp\\."""
    ap = os.path.abspath(p); od = os.path.join(ROOT, "out")
    try: rel = os.path.relpath(ap, od)
    except ValueError: rel = ".."
    if rel.startswith(".."): rel = os.path.basename(ap)
    return os.path.join(ROOT, "tmp", rel)

def _tmp():
    d = os.path.join(ROOT, "tmp", "_sys")
    try: os.makedirs(d, exist_ok=True)
    except OSError: return
    if os.name == "nt":
        for k in ("TMP", "TEMP"): os.environ[k] = d
        import tempfile; tempfile.tempdir = d

_add()
_tmp()
