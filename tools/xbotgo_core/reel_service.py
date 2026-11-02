"""Highlight reel generation and clip sequence calculation service.
Determines clip ordering, intro/halftime/outro card placement, cheer clips, and halftime score.
"""
import csv
import os
import re
from typing import Any, Dict, List, Optional


def row_skip(r: Dict[str, Any]) -> bool:
    """Return True if legacy skip column is non-empty, or the word 'skip' is in instructions."""
    return bool((r.get("skip") or "").strip()) or bool(re.search(r"\bskip\b", r.get("instructions") or "", re.IGNORECASE))


def has_value(v: Any) -> bool:
    """Return True if string value is non-empty."""
    return bool((v or "").strip())


def calculate_reel_manifest(
    csv_path: str,
    out_dir: str,
    clipdir: str = "reviewed4k",
    no_halftime: bool = False
) -> Dict[str, Any]:
    """Calculate the clip list, cheers list, and halftime score for reel assembly.
    
    Returns:
        dict with:
            clips: List[str] of file paths including intro, halftime card, clips, outro
            cheers: List[str] of goal clip filenames for cheering audio/effects
            halftime_score: str (e.g. '2-1')
    """
    cdir = os.path.join(out_dir, "clips", clipdir)
    cards = os.path.join(out_dir, "clips", "cards")

    if not os.path.isdir(cdir):
        raise FileNotFoundError(f"Clip directory not found: {cdir}")

    files = sorted(f for f in os.listdir(cdir) if f.endswith(".mp4"))
    byn = {int(f[:3]): f for f in files if f[:3].isdigit()}

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    n = 0
    seq = []
    cheers = []
    home = away = 0
    ht = None

    for r in rows:
        m = re.search(r"(\d+)\s*-\s*(\d+)", r.get("label", "") or "")
        if r.get("type") == "goal" and m:
            h, w = int(m.group(1)), int(m.group(2))
            ours = h > home
            home, away = h, w
        else:
            ours = r.get("type") == "goal" and not (r.get("player", "") or "").strip().lower().startswith("oppo")
        if (r.get("half") or "").strip() == "1":
            ht = f"{home}-{away}"
        if row_skip(r) or not (
            has_value(r.get("event") or r.get("event_video")) and has_value(r.get("action_end") or r.get("action_end_video"))
        ):
            continue
        n += 1
        f_clip = byn.get(n)
        if not f_clip:
            raise FileNotFoundError(f"clip {n:03d} missing in {cdir}")
        seq.append(((r.get("half") or "").strip(), os.path.join(cdir, f_clip)))
        if r.get("type") == "goal" and ours:
            cheers.append(f_clip)

    out = [os.path.join(cards, "000_intro.mp4")]
    hcard = os.path.join(cards, "500_halftime.mp4")
    put = no_halftime or not os.path.exists(hcard)

    for half, p in seq:
        if not put and half == "2":
            out.append(hcard)
            put = True
        out.append(p)
    out.append(os.path.join(cards, "999_outro.mp4"))

    return {
        "clips": out,
        "cheers": cheers,
        "halftime_score": ht or "0-0"
    }
