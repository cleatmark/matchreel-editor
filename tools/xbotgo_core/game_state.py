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
import json
import os
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(TOOLS_DIR)
OUT_REVIEWED = os.path.join(ROOT, "out", "reviewed")
DEFAULTS_FILE = os.path.join(ROOT, "config", "game_defaults.json")

from . import csv_io
import dumplayout


def resolve_game_out(game_id: str) -> Optional[str]:
    """Resolve out directory path for a game_id, auto-repairing any legacy '../' video paths."""
    res = None
    if os.path.isabs(game_id) and os.path.isdir(game_id):
        res = game_id
    else:
        candidates = [
            os.path.join(ROOT, "out", game_id),
            os.path.join(ROOT, "out", game_id + "-g1"),
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
    """Look for timeline.json in standard out locations."""
    candidates = [
        os.path.join(ROOT, "out", game_id, "work", "timeline.json"),
        os.path.join(ROOT, "out", game_id, "timeline.json"),
        os.path.join(ROOT, "out", game_id + "-g1", "work", "timeline.json"),
        os.path.join(ROOT, "out", game_id + "-g1", "timeline.json"),
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
                    elif os.path.exists(os.path.join(ROOT, candidate_rel)):
                        rel_path = candidate_rel
                        duration = v.get("duration")
                        break

    # If not found via timeline, search standard dump folders
    if not rel_path:
        for entry in os.listdir(ROOT):
            day_dir = os.path.join(ROOT, entry)
            if os.path.isdir(day_dir):
                candidate = os.path.join(day_dir, "Videos", filename)
                if os.path.exists(candidate):
                    rel_path = os.path.relpath(candidate, ROOT)
                    break
                candidate_dcim = os.path.join(day_dir, "DCIM", "XbotGo", filename)
                if os.path.exists(candidate_dcim):
                    rel_path = os.path.relpath(candidate_dcim, ROOT)
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
    for c in cands:
        p = os.path.join(ROOT, c)
        if os.path.isdir(p):
            try:
                vdir = dumplayout.find_video_dir(p)
                if vdir:
                    return p
            except Exception:
                _swallowed()

    # Broader search in root
    for entry in os.listdir(ROOT):
        p = os.path.join(ROOT, entry)
        if os.path.isdir(p) and not entry.startswith((".", "_", "tools", "utils", "shared", "tmp", "xbotgo_app", "out")):
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
            gdir = os.path.join(ROOT, "out", game_id)
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
    logos_dir = os.path.join(ROOT, "shared", "team_logos")
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
                "rel_path": f"shared/team_logos/{f}",
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
    """Write normalized roster to out/reviewed/roster.csv with .bak backup in existing order."""
    roster_path = os.path.join(ROOT, "out", "reviewed", "roster.csv")
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
    """Load roster from out/reviewed/roster.csv (auto-hydrating from Google Sheet Roster tab if missing or incomplete)."""
    roster_path = os.path.join(ROOT, "out", "reviewed", "roster.csv")
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
                    if p and (p.startswith("../") or p.startswith("..\\")):
                        clean = re.sub(r"^\.\.[\\/]", "", p)
                        if os.path.exists(os.path.join(ROOT, clean)):
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
                        if p and (p.startswith("../") or p.startswith("..\\")):
                            clean = re.sub(r"^\.\.[\\/]", "", p)
                            if os.path.exists(os.path.join(ROOT, clean)):
                                r["path"] = clean.replace("\\", "/")
                                st_modified = True
                if st_modified:
                    from .atomic_io import write_json_atomic
                    write_json_atomic(cand, st, indent=2)
                    repaired_any = True
            except Exception:
                _swallowed()

    return repaired_any
