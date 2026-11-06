"""Highlight reel clip selection, player grouping, and cheer detection rules.

Pure Python module with zero web framework dependencies.
Provides:
- ours_goals: Identifies goal clips scored by our team (score increase or unlabeled non-oppo).
- matches_player: Multi-player check (e.g. "11,4" matches #11 and #4).
- get_player_clip_counts: Computes clip counts for each player jersey on roster.
- get_default_featured_player: Reads default player from config/game_defaults.json.
"""
import csv
import json
import os
import re
from typing import Any, Dict, List, Optional, Set

from .xbl import Game
from .game_state import ROOT, DEFAULTS_FILE, load_game_defaults


def ours_goals(g: Game) -> Set[str]:
    """Clip basenames of our goals (home score went up; unlabeled goal rows count unless player starts with oppo)."""
    home = 0
    out = set()
    jobs = {id(j["row"]): j for j in g.jobs()}
    if not os.path.exists(g.csv):
        return out

    with open(g.csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            m = re.search(r"(\d+)\s*-\s*(\d+)", r.get("label", "") or "")
            if r.get("type") == "goal" and m:
                h = int(m.group(1))
                ours = h > home
                home = h
            else:
                ours = r.get("type") == "goal" and not (r.get("player") or "").strip().lower().startswith("oppo")
            if ours:
                for j in jobs.values():
                    if (
                        j["row"].get("video_sec") == r.get("video_sec")
                        and j["row"].get("type") == r.get("type")
                        and j["row"].get("file") == r.get("file")
                    ):
                        out.add(j["clip"])
    return out


def matches_player(player_val: Any, target_player: str) -> bool:
    """Check if target_player matches a row player field (handles comma-separated multi-player tags e.g. '11,4')."""
    if not target_player or not player_val:
        return False
    target = str(target_player).strip().lower()
    val_str = str(player_val).strip().lower()
    if val_str == target:
        return True
    parts = [p.strip() for p in val_str.split(",") if p.strip()]
    return target in parts


def get_player_clip_counts(g: Game) -> Dict[str, int]:
    """Count non-skipped clips attributed to each player number across all reviewed jobs."""
    counts: Dict[str, int] = {}
    for j in g.jobs():
        p_str = (j.get("player") or j.get("row", {}).get("player") or "").strip()
        if p_str:
            for p in p_str.split(","):
                p_clean = p.strip()
                if p_clean:
                    counts[p_clean] = counts.get(p_clean, 0) + 1
    return counts


def get_default_featured_player() -> str:
    """Return default featured player from workflow defaults."""
    defs = load_game_defaults()
    fps = defs.get("featured_players") or []
    if isinstance(fps, list) and fps:
        return str(fps[0]).strip()
    elif isinstance(fps, str) and fps:
        return fps.split(",")[0].strip()
    from . import app_config
    return app_config.FALLBACK["featured_players"][0]
