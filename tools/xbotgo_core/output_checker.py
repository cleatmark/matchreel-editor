"""Finished match output verification service.
Checks video and audio length consistency across highlight reels and full-game matches.
"""
import glob
import os
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple


def probe_stream_duration(ffprobe_path: str, filepath: str, stream: str) -> Optional[float]:
    """Probe duration of video or audio stream via ffprobe."""
    r = subprocess.run(
        [ffprobe_path, "-v", "error", "-select_streams", stream, "-show_entries", "stream=duration", "-of", "csv=p=0", filepath],
        capture_output=True,
        text=True
    )
    try:
        return float(r.stdout.split()[0])
    except Exception:
        return None


def check_game_outputs(
    out_dir: str,
    day: str,
    root: str = "."
) -> Dict[str, Any]:
    """Verify video/audio agreement for reels and full game file.
    
    Returns:
        dict with:
            results: List[dict] for each file checked (path, status, video_dur, audio_dur, expected_dur, messages)
            bad_count: int
            all_ok: bool
    """
    root_abs = os.path.abspath(root)
    ff = os.path.join(root_abs, "utils", "ffmpeg", "bin", "ffprobe.exe")
    ffprobe_cmd = ff if (os.name == "nt" and os.path.exists(ff)) else "ffprobe"

    results = []
    bad = 0

    def verify_file(f: str, expect: Optional[float] = None):
        nonlocal bad
        v = probe_stream_duration(ffprobe_cmd, f, "v:0")
        au = probe_stream_duration(ffprobe_cmd, f, "a:0")
        msg = []
        if v is None or au is None:
            msg.append("cannot read video/audio length")
        elif abs(v - au) > 0.3:
            msg.append(f"audio {au:.1f}s differs from video {v:.1f}s")
        if expect and v is not None and abs(v - expect) > 3:
            msg.append(f"expected about {expect:.0f}s")

        is_bad = bool(msg)
        if is_bad:
            bad += 1

        results.append({
            "file": f,
            "relpath": os.path.relpath(f, root_abs),
            "status": "CHECK" if is_bad else "OK",
            "video_dur": v,
            "audio_dur": au,
            "expected_dur": expect,
            "messages": msg
        })

    # 1. Reels
    # (after Tidy the finished reels live in <out>/final/; the full game is handled below)
    for f in sorted(glob.glob(os.path.join(out_dir, "reels", "*.mp4")) + glob.glob(os.path.join(out_dir, "final", "*.mp4"))):
        if "_full_game" in os.path.basename(f):
            continue
        verify_file(f)

    # 2. Full Game
    y, m, d = day.split("-")[:3]
    exp = None
    bat = os.path.join(root_abs, "out", "bat", f"run_full_game_{day}.bat")
    if os.path.exists(bat):
        with open(bat, "r", errors="ignore", encoding="utf-8") as f:
            content = f.read()
        mm = re.search(r"expect about ([\d.]+) s", content)
        if mm:
            exp = float(mm.group(1))

    fg = (glob.glob(os.path.join(out_dir, f"{y}_{m}_{d}_full_game*.mp4"))
          or glob.glob(os.path.join(out_dir, "final", f"{y}_{m}_{d}_full_game*.mp4"))
          or glob.glob(os.path.join(root_abs, f"{y}_{m}_{d}_full_game*.mp4")))
    for f in fg:
        verify_file(f, exp)

    if not fg:
        bad += 1
        results.append({
            "file": None,
            "relpath": f"{y}_{m}_{d}_full_game.mp4",
            "status": "CHECK",
            "video_dur": None,
            "audio_dur": None,
            "expected_dur": exp,
            "messages": ["no full game file yet"]
        })

    return {
        "results": results,
        "bad_count": bad,
        "all_ok": bad == 0
    }
