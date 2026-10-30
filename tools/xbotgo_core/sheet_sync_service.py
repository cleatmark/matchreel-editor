"""Google Sheet synchronization service for XbotGo.
Manages worksheet tabs, text formatting, full table pushes (A..P), pulls, and column P (clip numbers).
"""
from .diag import swallowed as _swallowed
import csv
import glob
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_SHEET_ID = ""  # no built-in sheet: set sheet_id in config/game_defaults.json or XBOTGO_SHEET_ID
SHEET_ID = DEFAULT_SHEET_ID
TEXT_RANGES = ["F", "H:I", "K:M"]  # video_time; clock_time, game_clock; action_start, event, action_end
INT_COLS = {"half", "video_sec", "clip"}


def get_configured_sheet_id(root_dir: Optional[str] = None) -> str:
    """Google Sheet ID from config/game_defaults.json (or XBOTGO_SHEET_ID); empty string if not configured."""
    from . import app_config
    return (app_config.load(root_dir or ROOT).get("sheet_id") or "").strip()


def get_service_account_client(key_path: Optional[str] = None, sheet_id: Optional[str] = None, root_dir: Optional[str] = None):
    """Connect to Google Sheets via service account key in shared/secrets/."""
    try:
        import gspread
    except ImportError:
        raise RuntimeError("gspread is not installed. Run: pip install gspread")

    base = root_dir or ROOT
    key = key_path or (sorted(glob.glob(os.path.join(base, "shared", "secrets", "*.json")) or [None])[0])
    if not key or not os.path.exists(key):
        raise FileNotFoundError(f"No Google service account key found in {os.path.join(base, 'shared', 'secrets')}")

    target_sheet = sheet_id or get_configured_sheet_id(base)
    if not target_sheet:
        raise RuntimeError("No Google Sheet configured: set sheet_id in config/game_defaults.json (or XBOTGO_SHEET_ID)")
    return gspread.service_account(filename=key), target_sheet


def determine_desired_tab_name(game_id: str, root_dir: Optional[str] = None) -> str:
    """Construct canonical tab name from date and current game_info (e.g. '03/29/26 League A')."""
    base = root_dir or ROOT
    m = re.match(r"^20(\d{2})-(\d{2})-(\d{2})(?:-g(\d))?", game_id)
    if not m:
        return game_id
    yy, mm, dd, g = m.groups()
    prefix = f"{mm}/{dd}/{yy}"

    from . import app_config
    cfg = app_config.load(base)
    league = cfg["league"]
    out_dir = os.path.join(base, "out", game_id)
    candidates = [
        os.path.join(out_dir, "game_info.json"),
        os.path.join(out_dir, "work", "game_info.json"),
    ]
    for cp in candidates:
        if os.path.exists(cp):
            try:
                with open(cp, "r", encoding="utf-8") as f:
                    gi = json.load(f)
                l_raw = (gi.get("league") or "").strip()
                if l_raw:
                    league = l_raw
                break
            except Exception:
                _swallowed()

    suffix = f" G{g}" if g else ""
    return f"{prefix} {league}{suffix}"


def determine_tab_name(game_id: str, existing_tab_titles: Optional[List[str]] = None, root_dir: Optional[str] = None) -> str:
    """Determine the Google Sheet tab title for a game ID."""
    return determine_desired_tab_name(game_id, root_dir=root_dir)


def list_tabs(client=None, sheet_key: Optional[str] = None) -> List[Tuple[int, str]]:
    """Return list of (tab_id, tab_title) for all worksheets in the sheet."""
    if client is None:
        client, key = get_service_account_client(sheet_id=sheet_key)
        sheet_key = key
    sh = client.open_by_key(sheet_key)
    return [(w.id, w.title) for w in sh.worksheets()]


def rename_google_sheet_tab(old_title: str, new_title: str, client=None, sheet_key: Optional[str] = None) -> bool:
    """Rename a worksheet tab in place on the season Google Sheet."""
    try:
        if client is None:
            client, key = get_service_account_client(sheet_id=sheet_key)
            sheet_key = key
        sh = client.open_by_key(sheet_key)
        existing = {w.title: w for w in sh.worksheets()}
        if old_title in existing and (new_title == old_title or new_title not in existing):
            if new_title != old_title:
                existing[old_title].update_title(new_title)
            return True
    except Exception:
        _swallowed()
    return False


def build_sheet_push_payload(
    headers: List[str],
    rows: List[Dict[str, Any]]
) -> List[List[Any]]:
    """Build the complete 2D matrix for Google Sheets: header row plus all data rows.
    
    Enforces integer coercion for INT_COLS (half, video_sec, clip) when non-empty,
    leaving times and strings intact for RAW entry.
    """
    out: List[List[Any]] = [headers]
    for r in rows:
        row_vals: List[Any] = []
        for h in headers:
            v = r.get(h, "")
            if h in INT_COLS and v not in ("", None):
                try:
                    v = int(float(v))
                except (ValueError, TypeError):
                    pass
            elif v is None:
                v = ""
            else:
                v = str(v)
            row_vals.append(v)
        out.append(row_vals)
    return out


def fit_columns(sh, ws_id: int, ncols: int = 16):
    """Auto-fit column widths across the worksheet."""
    try:
        sh.batch_update({
            "requests": [{
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": ws_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": ncols
                    }
                }
            }]
        })
    except Exception:
        _swallowed()


def push_to_google_sheet(
    game_id: str,
    headers: List[str],
    rows: List[Dict[str, Any]],
    client=None,
    sheet_key: Optional[str] = None,
    root_dir: Optional[str] = None
) -> Dict[str, Any]:
    """Write the ENTIRE reviewed table (A..P) into the matching Google Sheet tab.
    
    Creates the tab if it does not exist; overwrites it if it already exists.
    Applies plain text format to columns F, H:I, K:M before and after writing in RAW mode.
    """
    if client is None:
        client, key = get_service_account_client(sheet_id=sheet_key, root_dir=root_dir)
        sheet_key = key
    sh = client.open_by_key(sheet_key)

    existing_tabs = {w.title: w for w in sh.worksheets()}
    desired_tab = determine_desired_tab_name(game_id, root_dir=root_dir)
    tab_name = desired_tab

    # If old matching tab exists with different league name, rename in place
    m = re.match(r"^20(\d{2})-(\d{2})-(\d{2})(?:-g(\d))?", game_id)
    if m:
        yy, mm, dd, g = m.groups()
        prefix = f"{mm}/{dd}/{yy}"
        for t, old_ws in list(existing_tabs.items()):
            matches_pfx = (g and prefix in t and f"G{g}" in t.upper()) or (not g and prefix in t)
            if matches_pfx and t != desired_tab:
                if desired_tab not in existing_tabs:
                    old_ws.update_title(desired_tab)
                    existing_tabs[desired_tab] = old_ws
                    existing_tabs.pop(t, None)
                    break

    if tab_name in existing_tabs:
        ws = existing_tabs[tab_name]
        needed_rows = max(1000, len(rows) + 50)
        needed_cols = max(16, len(headers))
        if ws.row_count < needed_rows:
            ws.add_rows(needed_rows - ws.row_count)
        if ws.col_count < needed_cols:
            ws.add_cols(needed_cols - ws.col_count)
    else:
        ws = sh.add_worksheet(
            title=tab_name,
            rows=max(1000, len(rows) + 50),
            cols=max(16, len(headers))
        )

    def apply_text_format():
        reqs = []
        for r_spec in TEXT_RANGES:
            parts = r_spec.split(":")
            start_col = ord(parts[0].strip().upper()) - 65
            end_col = (ord(parts[-1].strip().upper()) - 64) if len(parts) > 1 else (start_col + 1)
            reqs.append({
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 1,
                        "endRowIndex": max(1000, len(rows) + 50),
                        "startColumnIndex": start_col,
                        "endColumnIndex": end_col
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "TEXT"}
                        }
                    },
                    "fields": "userEnteredFormat.numberFormat"
                }
            })
        try:
            sh.batch_update({"requests": reqs})
        except Exception:
            _swallowed()

    # 1. Apply plain-text format FIRST
    apply_text_format()

    # 2. Build full table payload (A..P)
    matrix = build_sheet_push_payload(headers, rows)

    # 3. Update values in RAW mode (so "04:01" stays text, no apostrophe or formula coercions)
    ws.update(values=matrix, range_name="A1", value_input_option="RAW")

    # 4. Re-apply plain-text format AGAIN
    apply_text_format()

    # 5. Freeze header row
    try:
        ws.freeze(rows=1)
    except Exception:
        _swallowed()

    # 6. Auto-fit columns
    fit_columns(sh, ws.id, len(headers))

    # 7. Clear trailing rows
    try:
        prev_row_count = ws.row_count
        if prev_row_count > len(matrix):
            clear_start = len(matrix) + 1
            if clear_start <= prev_row_count:
                ws.batch_clear([f"A{clear_start}:P{prev_row_count}"])
    except Exception:
        _swallowed()

    return {
        "status": "ok",
        "tab_name": tab_name,
        "rows_count": len(rows),
        "url": f"https://docs.google.com/spreadsheets/d/{sheet_key}/edit#gid={ws.id}"
    }


def pull_from_google_sheet(
    tab_name: str,
    dst_csv_path: str,
    client=None,
    sheet_key: Optional[str] = None
) -> int:
    """Pull rows from a Google Sheet tab into a local CSV file.
    
    Returns the number of rows pulled.
    """
    if client is None:
        client, key = get_service_account_client(sheet_id=sheet_key)
        sheet_key = key
    sh = client.open_by_key(sheet_key)
    ws = sh.worksheet(tab_name)
    vals = ws.get_all_values()
    if not vals:
        return 0

    ncols = max(len(r) for r in vals)
    os.makedirs(os.path.dirname(os.path.abspath(dst_csv_path)), exist_ok=True)
    with open(dst_csv_path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([r + [""] * (ncols - len(r)) for r in vals])
    return len(vals)


def push_clip_column(
    tab_name: str,
    clip_column_json_path: str,
    client=None,
    sheet_key: Optional[str] = None
) -> int:
    """Push clip column numbers from clip_column.json into column P of the worksheet tab.
    
    Returns the number of clip values updated.
    """
    if client is None:
        client, key = get_service_account_client(sheet_id=sheet_key)
        sheet_key = key
    sh = client.open_by_key(sheet_key)
    ws = sh.worksheet(tab_name)

    if not os.path.exists(clip_column_json_path):
        raise FileNotFoundError(f"Clip column JSON not found: {clip_column_json_path}")

    with open(clip_column_json_path, "r", encoding="utf-8") as f:
        col = json.load(f)

    if not col or col[0] != ["clip"]:
        raise ValueError("Invalid clip_column.json format: expected [['clip'], ...]")

    hdr = ws.row_values(1)
    if len(hdr) < 16 or hdr[15] != "clip":
        raise ValueError(f"Column P of tab '{tab_name}' is not 'clip' (found {hdr[15:16]})")

    ws.update(values=col, range_name=f"P1:P{len(col)}", value_input_option="RAW")
    return len(col) - 1
