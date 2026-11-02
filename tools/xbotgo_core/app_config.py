"""Single source of truth for per-user defaults (team, leagues, featured players, Google Sheet).

Nothing identifying lives in code. The only built-in values are the generic placeholders in FALLBACK
(Home FC, Guest FC, ...). A user's real values live in config/game_defaults.json, which is git-ignored;
config/game_defaults.example.json documents the format.

Layers (later wins): FALLBACK -> config/game_defaults.json -> env XBOTGO_SHEET_ID.
"""
import copy
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULTS_FILE = os.path.join(ROOT, "config", "game_defaults.json")

FALLBACK = {
    "team_name": "Home FC",
    "is_home": True,
    "team_logo": "",
    # leagues: [{"name": tab/label text, "logo": "shared/team_logos/..." (optional), "label": optional UI text}]
    "leagues": [
        {"name": "League A", "logo": ""},
        {"name": "League B", "logo": ""},
    ],
    "league": "League A",       # name of the default league (one of `leagues`, or free text)
    "league_logo": "",
    "featured_players": ["7"],
    "sheet_id": "",             # Google Sheet ID of the season workbook; empty = Google Sheet sync disabled
    "guest_name": "Guest FC",   # placeholder opponent name used when none is known
}


def _clean_leagues(raw):
    out = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                out.append({"name": item.strip(), "logo": ""})
            elif isinstance(item, dict) and str(item.get("name") or "").strip():
                e = {"name": str(item["name"]).strip(), "logo": str(item.get("logo") or "").strip()}
                if str(item.get("label") or "").strip():
                    e["label"] = str(item["label"]).strip()
                out.append(e)
    return out


def load_from_file(path=None):
    """Merged config dict. `path` is the game_defaults.json to read (default: this tree's config)."""
    cfg = copy.deepcopy(FALLBACK)
    p = path or DEFAULTS_FILE
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                cfg.update({k: v for k, v in d.items() if k != "leagues"})
                leagues = _clean_leagues(d.get("leagues"))
                if leagues:
                    cfg["leagues"] = leagues
        except Exception:
            pass
    env_sheet = os.environ.get("XBOTGO_SHEET_ID", "").strip()
    if env_sheet:
        cfg["sheet_id"] = env_sheet
    fps = cfg.get("featured_players")
    if isinstance(fps, str):
        fps = [s.strip() for s in fps.split(",") if s.strip()]
    cfg["featured_players"] = [str(s) for s in (fps or []) if str(s).strip()] or list(FALLBACK["featured_players"])
    if not str(cfg.get("league") or "").strip():
        cfg["league"] = cfg["leagues"][0]["name"]
    if not cfg.get("league_logo"):
        cfg["league_logo"] = logo_for_league(cfg["league"], cfg)
    return cfg


def load(root=None):
    return load_from_file(os.path.join(root, "config", "game_defaults.json") if root else None)


def logo_for_league(name, cfg):
    for lg in cfg.get("leagues", []):
        if lg["name"].lower() == str(name or "").strip().lower():
            return lg.get("logo", "")
    return ""


def default_featured_player(root=None):
    return load(root)["featured_players"][0]
