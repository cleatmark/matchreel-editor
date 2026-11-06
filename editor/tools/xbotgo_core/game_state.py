"""Game state, metadata, and roster services for XbotGo.

Pure Python module with zero web framework dependencies.
Provides:
- Game output directory resolution (standard out/ and test fixtures).
- Timeline and video file discovery across dump folders.
- Match setup info (game_info.json) and global workflow defaults (config/game_defaults.json).
- Team crest and competition logo scanning.
- Review CSV schema validity checking.
- Team roster loading, normalization, local caching (out/reviewed/roster.csv with .bak),
  and bidirectional Google Sheet synchronization.
"""
from .diag import swallowed as _swallowed
import csv
import datetime
import json
import os
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from . import xb_env
ROOT = xb_env.ROOT
OUT_REVIEWED = os.path.join(xb_env.OUTPUT, "reviewed")
DEFAULTS_FILE = os.path.join(xb_env.CONFIG, "game_defaults.json")

from . import csv_io
import dumplayout


def resolve_game_out(game_id: str) -> Optional[str]:
    """Resolve out directory path for a game_id, auto-repairing any legacy '../' video paths."""
    res = None
    if os.path.isabs(game_id) and os.path.isdir(game_id):
        res = game_id
    else:
        candidates = [
            os.path.join(xb_env.OUTPUT, game_id),
            os.path.join(xb_env.OUTPUT, game_id + "-g1"),
        ]
        for c in candidates:
            if os.path.isdir(c):
                res = c
                break
        if not res and game_id.startswith("test_"):
            tmp_cand = os.path.join(ROOT, "tmp", game_id)
            if os.path.isdir(tmp_cand):
                res = tmp_cand
        if not res and os.path.isdir(game_id):
            res = os.path.abspath(game_id)

    if res and not game_id.startswith("test_"):
        normalize_and_repair_paths(res)
    return res


def find_timeline_for_game(game_id: str) -> Optional[Dict[str, Any]]:
    """Look for timeline.json in standard output locations."""
    candidates = [
        os.path.join(xb_env.OUTPUT, game_id, "work", "timeline.json"),
        os.path.join(xb_env.OUTPUT, game_id, "timeline.json"),
        os.path.join(xb_env.OUTPUT, game_id + "-g1", "work", "timeline.json"),
        os.path.join(xb_env.OUTPUT, game_id + "-g1", "timeline.json"),
    ]
    if os.path.isabs(game_id) and os.path.isdir(game_id):
        candidates.extend([
            os.path.join(game_id, "work", "timeline.json"),
            os.path.join(game_id, "timeline.json"),
        ])
    if game_id.startswith("test_"):
        candidates.extend([
            os.path.join(ROOT, "tmp", game_id, "work", "timeline.json"),
            os.path.join(ROOT, "tmp", game_id, "timeline.json"),
        ])
    for c in candidates:
        if os.path.exists(c):
            try:
                with open(c, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error reading timeline {c}: {e}")
    return None


def resolve_video_info(filename: str, timeline: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Find video path on disk and duration."""
    rel_path = None
    duration = None

    if timeline and "videos" in timeline:
        for v in timeline["videos"]:
            if v.get("file") == filename:
                candidate_rel = v.get("path")
                if candidate_rel:
                    clean_cand = re.sub(r"^\.\.[\\/]", "", candidate_rel)
                    if os.path.exists(os.path.join(ROOT, clean_cand)):
                        rel_path = clean_cand.replace("\\", "/")
                        duration = v.get("duration")
                        break
                    elif os.path.exists(os.path.join(ROOT, "input", clean_cand)):
                        rel_path = f"input/{clean_cand}".replace("\\", "/")
                        duration = v.get("duration")
                        break
                    elif os.path.exists(os.path.join(ROOT, candidate_rel)):
                        rel_path = candidate_rel
                        duration = v.get("duration")
                        break

    # If not found via timeline, search standard dump folders in input/
    if not rel_path:
        search_dirs = [xb_env.INPUT] if os.path.isdir(xb_env.INPUT) else [ROOT]
        for sdir in search_dirs:
            for entry in os.listdir(sdir):
                day_dir = os.path.join(sdir, entry)
                if os.path.isdir(day_dir):
                    candidate = os.path.join(day_dir, "Videos", filename)
                    if os.path.exists(candidate):
                        rel_path = os.path.relpath(candidate, ROOT)
                        break
                    candidate_dcim = os.path.join(day_dir, "DCIM", "XbotGo", filename)
                    if os.path.exists(candidate_dcim):
                        rel_path = os.path.relpath(candidate_dcim, ROOT)
                        break
            if rel_path:
                break

    abs_path = os.path.join(ROOT, rel_path) if rel_path else None
    if abs_path and os.path.exists(abs_path) and duration is None:
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", abs_path],
                capture_output=True, text=True
            )
            duration = float(r.stdout.strip())
        except Exception:
            _swallowed()

    clean_rel = rel_path.replace("\\", "/") if rel_path else None
    return {
        "file": filename,
        "rel_path": clean_rel,
        "exists": abs_path is not None and os.path.exists(abs_path),
        "duration": duration,
        "url": f"/api/video?path={clean_rel}" if clean_rel else None,
    }


def find_game_dump_folder(date_iso: str) -> Optional[str]:
    """Find a dump folder or video directory matching date YYYY-MM-DD."""
    parts = date_iso.split("-")
    if len(parts) != 3:
        return None
    yyyy, mm, dd = parts
    yy = yyyy[2:]

    cands = [
        f"{mm}-{dd}-{yy}",
        f"{yyyy}-{mm}-{dd}",
        f"{mm}-{dd}-{yyyy}",
    ]
    search_dirs = [xb_env.INPUT] if os.path.isdir(xb_env.INPUT) else [ROOT]
    for sdir in search_dirs:
        for c in cands:
            p = os.path.join(sdir, c)
            if os.path.isdir(p):
                try:
                    vdir = dumplayout.find_video_dir(p)
                    if vdir:
                        return p
                except Exception:
                    _swallowed()

        for entry in os.listdir(sdir):
            p = os.path.join(sdir, entry)
            if os.path.isdir(p) and not entry.startswith((".", "_", "editor", "tools", "utils", "shared", "tmp", "reference", "output")):
                try:
                    vdir = dumplayout.find_video_dir(p)
                    if vdir:
                        # Check if videos in vdir match date_iso
                        if any(f.startswith(date_iso) for f in os.listdir(vdir)):
                            return p
                except Exception:
                    _swallowed()
    return None


def find_game_info_path(game_id: str, create_dir_if_missing: bool = False) -> Optional[str]:
    """Find existing game_info.json in game directory or game work/ directory."""
    gdir = resolve_game_out(game_id)
    if not gdir:
        if create_dir_if_missing:
            gdir = os.path.join(xb_env.OUTPUT, game_id)
            os.makedirs(gdir, exist_ok=True)
        else:
            return None

    candidates = [
        os.path.join(gdir, "game_info.json"),
        os.path.join(gdir, "work", "game_info.json"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return os.path.join(gdir, "game_info.json")


def load_game_info(game_id: str) -> Optional[Dict[str, Any]]:
    """Load game_info.json if present."""
    p = find_game_info_path(game_id)
    if p and os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading game_info for {game_id}: {e}")
    return None


def get_available_logos() -> List[Dict[str, str]]:
    """Scan shared/team_logos/ and return list of available logos with team metadata."""
    logos_dir = os.path.join(xb_env.SHARED, "team_logos")
    if not os.path.isdir(logos_dir):
        return []
    meta_path = os.path.join(logos_dir, "metadata.json")
    meta = []
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            _swallowed()
    meta_map = {m["filename"]: m["team"] for m in meta if isinstance(m, dict) and "filename" in m and "team" in m}

    all_logos = []
    for f in sorted(os.listdir(logos_dir)):
        if f.lower().endswith((".png", ".jpg", ".jpeg")) and not f.startswith("."):
            team_name = meta_map.get(f, os.path.splitext(f)[0])
            all_logos.append({
                "filename": f,
                "rel_path": "shared/team_logos/" + f,   # served by /shared/<path>, resolved by _resolve_logo_file and the pipeline (2.62.0 gave "editor/shared/...": 404 previews, blank home logo)
                "team": team_name
            })
    return all_logos


def check_csv_validity(csv_path: str) -> Tuple[bool, int]:
    """Check if a CSV file exists and matches the current review table schema."""
    if not os.path.exists(csv_path):
        return False, 0
    try:
        import csv as _csv
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = _csv.reader(f)
            headers = next(reader, [])
            is_valid = (
                headers == csv_io.STANDARD_COLUMNS
                or headers == csv_io.STANDARD_COLUMNS + ["clip"]
                or all(col in headers for col in csv_io.STANDARD_COLUMNS)
            )
            return is_valid, len(headers)
    except Exception:
        return False, 0


def load_game_defaults() -> dict:
    """Workflow defaults: generic placeholders overlaid with config/game_defaults.json (see app_config)."""
    from . import app_config
    return app_config.load_from_file(DEFAULTS_FILE)


def normalize_roster(roster: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Clean roster rows while preserving exact existing order from Google Sheet / user table."""
    cleaned = []
    for r in roster:
        no_str = str(r.get("no") or r.get("No") or "").strip()
        name_str = str(r.get("name") or r.get("Player") or r.get("player") or "").strip()
        short_str = str(r.get("short_name") or r.get("Short_Name") or r.get("shortname") or "").strip()
        contact_str = str(r.get("contact") or r.get("Contact") or "").strip()
        if no_str or name_str:
            if not short_str and name_str:
                short_str = name_str.split()[0]
            cleaned.append({
                "no": no_str,
                "name": name_str,
                "short_name": short_str,
                "contact": contact_str
            })
    return cleaned


def fetch_remote_roster() -> Optional[List[Dict[str, str]]]:
    """Fetch raw roster directly from Google Sheet 'Roster' tab preserving sheet order."""
    try:
        from sheet_sync_service import get_service_account_client
        gc, sheet_id = get_service_account_client()
        sh = gc.open_by_key(sheet_id)
        ws = sh.worksheet("Roster")
        rows = ws.get_all_values()
        if len(rows) > 1:
            header = [h.strip().lower() for h in rows[0]]
            no_idx = header.index("no") if "no" in header else 1
            name_idx = header.index("player") if "player" in header else 0
            short_idx = header.index("short_name") if "short_name" in header else -1
            contact_idx = header.index("contact") if "contact" in header else -1
            result = []
            for r in rows[1:]:
                if len(r) > max(no_idx, name_idx) and (r[no_idx].strip() or r[name_idx].strip()):
                    result.append({
                        "no": r[no_idx].strip(),
                        "name": r[name_idx].strip(),
                        "short_name": r[short_idx].strip() if short_idx >= 0 and len(r) > short_idx else (r[name_idx].strip().split()[0] if r[name_idx].strip() else ""),
                        "contact": r[contact_idx].strip() if contact_idx >= 0 and len(r) > contact_idx else ""
                    })
            return normalize_roster(result)
    except Exception as e:
        print(f"Error fetching remote roster: {e}")
        return None
    return []


def write_roster_local(roster: List[Dict[str, str]]) -> str:
    """Write normalized roster to output/reviewed/roster.csv with .bak backup in existing order."""
    roster_path = os.path.join(xb_env.OUTPUT, "reviewed", "roster.csv")
    os.makedirs(os.path.dirname(roster_path), exist_ok=True)
    if os.path.exists(roster_path):
        try:
            shutil.copy2(roster_path, roster_path + ".bak")
        except Exception:
            _swallowed()
    clean_roster = normalize_roster(roster)
    fieldnames = ["name", "no", "short_name", "contact"]
    import io
    from .atomic_io import write_text_atomic
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for p in clean_roster:
        writer.writerow({
            "name": p.get("name", ""),
            "no": p.get("no", ""),
            "short_name": p.get("short_name", ""),
            "contact": p.get("contact", "")
        })
    write_text_atomic(roster_path, buf.getvalue(), newline="")
    return roster_path


def push_roster_remote(roster: List[Dict[str, str]]) -> bool:
    """Push normalized roster to Google Sheet 'Roster' tab preserving exact row order."""
    from sheet_sync_service import get_service_account_client
    gc, sheet_id = get_service_account_client()
    sh = gc.open_by_key(sheet_id)
    try:
        ws = sh.worksheet("Roster")
    except Exception:
        ws = sh.add_worksheet(title="Roster", rows=50, cols=10)

    clean_roster = normalize_roster(roster)
    header = ["Player", "No", "Contact", "Short_Name"]
    matrix = [header]
    for p in clean_roster:
        matrix.append([
            p.get("name", ""),
            str(p.get("no", "")),
            p.get("contact", ""),
            p.get("short_name", "")
        ])

    ws.clear()
    ws.update(values=matrix, range_name="A1", value_input_option="RAW")
    try:
        ws.freeze(rows=1)
    except Exception:
        _swallowed()
    return True


def load_roster() -> List[Dict[str, str]]:
    """Load roster from output/reviewed/roster.csv (auto-hydrating from Google Sheet Roster tab if missing or incomplete)."""
    roster_path = os.path.join(xb_env.OUTPUT, "reviewed", "roster.csv")
    cached = []
    if os.path.exists(roster_path):
        try:
            with open(roster_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                cached = [
                    {
                        "no": str(r.get("no", "")).strip(),
                        "name": str(r.get("name") or r.get("Player") or "").strip(),
                        "short_name": str(r.get("short_name") or r.get("Short_Name") or "").strip(),
                        "contact": str(r.get("contact") or r.get("Contact") or "").strip()
                    }
                    for r in reader if (r.get("no") or r.get("name"))
                ]
        except Exception as e:
            print(f"Error reading roster.csv: {e}")

    # If cache is valid and has contact info, return it
    if cached and any(r.get("contact") for r in cached):
        return cached

    # Fallback/Hydration from Google Sheet Roster tab if missing or contacts were blank
    remote = fetch_remote_roster()
    if remote:
        try:
            write_roster_local(remote)
        except Exception:
            _swallowed()
        return remote

    return cached


def normalize_and_repair_paths(out_dir: str) -> bool:
    """Auto-repair any leading '../' video paths in timeline.json and zoom_state.json in place.

    Returns True if any file was repaired.
    """
    repaired_any = False
    # 1. timeline.json
    for cand in [
        os.path.join(out_dir, "timeline.json"),
        os.path.join(out_dir, "work", "timeline.json")
    ]:
        if os.path.exists(cand):
            try:
                with open(cand, "r", encoding="utf-8") as f:
                    tl = json.load(f)
                tl_modified = False
                for v in tl.get("videos", []):
                    p = v.get("path")
                    if p:
                        clean = re.sub(r"^\.\.[\\/]", "", p)
                        if not os.path.exists(os.path.join(ROOT, clean)) and os.path.exists(os.path.join(ROOT, "input", clean)):
                            v["path"] = f"input/{clean}".replace("\\", "/")
                            tl_modified = True
                        elif clean != p and os.path.exists(os.path.join(ROOT, clean)):
                            v["path"] = clean.replace("\\", "/")
                            tl_modified = True
                if tl_modified:
                    from .atomic_io import write_json_atomic
                    write_json_atomic(cand, tl, indent=1)
                    repaired_any = True
            except Exception:
                _swallowed()

    # 2. zoom_state.json
    for cand in [
        os.path.join(out_dir, "zoom_state.json"),
        os.path.join(out_dir, "work", "zoom_state.json")
    ]:
        if os.path.exists(cand):
            try:
                with open(cand, "r", encoding="utf-8") as f:
                    st = json.load(f)
                st_modified = False
                for pool in (st.get("replays", {}), st.get("removed", {})):
                    for r in pool.values():
                        p = r.get("path")
                        if p:
                            clean = re.sub(r"^\.\.[\\/]", "", p)
                            if not os.path.exists(os.path.join(ROOT, clean)) and os.path.exists(os.path.join(ROOT, "input", clean)):
                                r["path"] = f"input/{clean}".replace("\\", "/")
                                st_modified = True
                            elif clean != p and os.path.exists(os.path.join(ROOT, clean)):
                                r["path"] = clean.replace("\\", "/")
                                st_modified = True
                if st_modified:
                    from .atomic_io import write_json_atomic
                    write_json_atomic(cand, st, indent=2)
                    repaired_any = True
            except Exception:
                _swallowed()

    return repaired_any


def format_media_label(filename: str, category: str) -> str:
    """Format clean human-readable label for a media file."""
    base = os.path.splitext(filename)[0]
    # Check clip prefix like 005_goal_000845_...
    m_clip = re.match(r"^(\d{3}[a-z]?)(?:_([a-z]+))?(?:_(\d{6}))?(?:_(.*))?$", base, re.IGNORECASE)
    if m_clip:
        num, kind, t_str, rest = m_clip.groups()
        lbl = f"Clip {num}"
        if kind:
            lbl += f" ({kind.title()})"
        if rest:
            clean_rest = rest.replace("_", " ")
            lbl += f" - {clean_rest}"
        return lbl

    # Check reel patterns
    stem = re.sub(r"^\d{4}[-_]\d{2}[-_]\d{2}(?:-[a-zA-Z0-9]+)?_", "", base)

    if "preview720" in stem or "preview720" in base:
        if "with_replays" in stem or "with_replays" in base:
            return "720p Preview Reel (with Zoom Replays)"
        return "720p Preview Reel (nomusic)"
    if "full_game" in stem:
        return "Full Match (Continuous 4K)"

    # Check player reel patterns BEFORE generic team highlights (e.g. Player_11_highlights, player11_highlights)
    m_player = re.search(r"(?:^|_)([A-Za-z]+)_(\d{1,2})_(?:highlights|reel)(?:$|_)", stem, re.IGNORECASE)
    if m_player:
        p_name, p_num = m_player.groups()
        return f"Player #{p_num} {p_name.title()} Highlights Reel"

    m_pnum = re.search(r"(?:^|_)(?:player|p)?_?(\d{1,2})_(?:highlights|reel)(?:$|_)", stem, re.IGNORECASE)
    if m_pnum:
        p_num = m_pnum.group(1)
        return f"Player #{p_num} Highlights Reel"

    m_pnum2 = re.search(r"(?:^|_)(?:highlights|reel)_(\d{1,2})(?:$|_)", stem, re.IGNORECASE)
    if m_pnum2:
        p_num = m_pnum2.group(1)
        return f"Player #{p_num} Highlights Reel"

    if "highlights" in stem or "highlights" in base:
        if "transitions" in stem or "transitions" in base:
            return "Team Highlights Reel (with transitions)"
        return "Team Highlights Reel"

    clean_base = stem.replace("_", " ").title()
    return clean_base


def list_game_media(out_dir: str, root_dir: Optional[str] = None) -> Dict[str, Any]:
    """Scan and categorize all rendered video outputs for a game directory.
    Categories:
      - clips720: Fast 720p cut action clips (preview720/ and zoom 720p extra replays)
      - clips4k: Full 4K production clips (reviewed4k/, clips/ root, zoom 2160p extra replays)
      - reels720: 720p preview reels
      - reels4k: 4K team highlight reels & full game video
      - player_reels: Individual player spotlight reels
    """
    base_root = root_dir or ROOT
    categories = {
        "clips720": [],
        "clips4k": [],
        "reels720": [],
        "reels4k": [],
        "player_reels": [],
    }

    if not out_dir or not os.path.isdir(out_dir):
        return {"categories": categories, "counts": {k: 0 for k in categories}}

    # Helper to scan a directory for MP4s
    def scan_dir(d):
        if not os.path.isdir(d):
            return []
        try:
            return [os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(".mp4") and os.path.isfile(os.path.join(d, f))]
        except OSError:
            return []

    # 1. 720p Clips
    c720_paths = set()
    for sub in [
        os.path.join(out_dir, "clips", "preview720"),
        os.path.join(out_dir, "work", "clips", "preview720"),
        os.path.join(out_dir, "preview720"),
    ]:
        for p in scan_dir(sub):
            c720_paths.add(p)
    # Extra 720 zoom replays
    for sub in [os.path.join(out_dir, "clips", "extra"), os.path.join(out_dir, "work", "clips", "extra")]:
        for p in scan_dir(sub):
            if p.lower().endswith("_720.mp4"):
                c720_paths.add(p)

    # 2. 4K Clips
    c4k_paths = set()
    for sub in [
        os.path.join(out_dir, "clips", "reviewed4k"),
        os.path.join(out_dir, "work", "clips", "reviewed4k"),
    ]:
        for p in scan_dir(sub):
            c4k_paths.add(p)
    # Root clips/ directory (direct mp4 files only)
    for sub in [os.path.join(out_dir, "clips"), os.path.join(out_dir, "work", "clips")]:
        for p in scan_dir(sub):
            c4k_paths.add(p)
    # Extra 2160 zoom replays
    for sub in [os.path.join(out_dir, "clips", "extra"), os.path.join(out_dir, "work", "clips", "extra")]:
        for p in scan_dir(sub):
            if p.lower().endswith("_2160.mp4"):
                c4k_paths.add(p)

    # 3. Reels & Final Videos
    reel_paths = set()
    for sub in [
        os.path.join(out_dir, "reels"),
        os.path.join(out_dir, "final"),
        os.path.join(out_dir, "work", "reels"),
        out_dir,
    ]:
        for p in scan_dir(sub):
            fn = os.path.basename(p).lower()
            if fn.startswith("000_intro") or fn.startswith("500_halftime") or fn.startswith("999_outro"):
                continue
            reel_paths.add(p)

    # Distribute reels into 720p vs 4K (4K contains full match, team highlights, and player reels)
    r720_paths = set()
    r4k_paths = set()

    for p in reel_paths:
        fn = os.path.basename(p).lower()
        if "preview720" in fn or "_720" in fn:
            r720_paths.add(p)
        else:
            r4k_paths.add(p)

    # Builder helper
    def make_item(p, cat):
        fn = os.path.basename(p)
        try:
            st = os.stat(p)
            sz = round(st.st_size / (1024 * 1024), 1)
            mtime = int(st.st_mtime)
            mtime_str = datetime.datetime.fromtimestamp(mtime).strftime("%b %d, %H:%M")
        except OSError:
            sz = 0.0
            mtime = 0
            mtime_str = ""
        rel = os.path.relpath(p, base_root).replace("\\", "/")
        return {
            "name": fn,
            "path": p,
            "rel_path": rel,
            "url": f"/api/video?path={rel}",
            "size_mb": sz,
            "mtime": mtime,
            "mtime_str": mtime_str,
            "category": cat,
            "label": format_media_label(fn, cat),
        }

    def reel_sort_key(item):
        name = item["name"].lower()
        stem = re.sub(r"^\d{4}[-_]\d{2}[-_]\d{2}(?:-[a-zA-Z0-9]+)?_", "", name)
        # Order: 1. Team highlights, 2. Player reels, 3. Full match, 4. Other
        if "full_game" in stem:
            prio = 3
        elif re.search(r"^[a-z]+_\d{1,2}_", stem) or re.search(r"(?:^|_)player", stem) or re.search(r"(?:^|_)p\d{1,2}", stem) or re.search(r"\d{1,2}_highlights", stem):
            prio = 2
        elif "highlights" in stem:
            prio = 1
        else:
            prio = 4
        return (prio, item["name"])

    categories["clips720"] = sorted([make_item(p, "clips720") for p in c720_paths], key=lambda x: x["name"])
    categories["clips4k"] = sorted([make_item(p, "clips4k") for p in c4k_paths], key=lambda x: x["name"])
    categories["reels720"] = sorted([make_item(p, "reels720") for p in r720_paths], key=lambda x: x["name"])
    categories["reels4k"] = sorted([make_item(p, "reels4k") for p in r4k_paths], key=reel_sort_key)
    categories["player_reels"] = [it for it in categories["reels4k"] if it["label"].startswith("Player #")]

    counts = {k: len(v) for k, v in categories.items()}
    return {"categories": categories, "counts": counts}
