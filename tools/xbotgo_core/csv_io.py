"""CSV Input/Output handler for XbotGo Review Editor.

Preserves exact formatting, line endings (CRLF), unknown columns, and row order.
Opening and saving with no edits leaves the file byte-identical.
Atomic writes with automatic backups in C:\\temp\\XbotGo\\tmp\\review_editor\\backups\\.
"""
import csv
import datetime
import os
import re
import tempfile
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP_BACKUPS = os.path.join(ROOT, "tmp", "review_editor", "backups")

# Column synonyms mapping older names to standard short names
HEADER_SYNONYMS = {
    "action_start_video": "action_start",
    "event_video": "event",
    "action_end_video": "action_end",
}

STANDARD_COLUMNS = [
    "game", "half", "type", "label", "file",
    "video_time", "video_sec", "clock_time", "game_clock",
    "notes", "action_start", "event", "action_end",
    "player", "instructions"
]


def is_row_skipped(instructions: Optional[str], skip_val: Optional[str] = None) -> bool:
    """Check if a row is skipped via 'skip' in instructions or a legacy skip column."""
    if skip_val and str(skip_val).strip().lower() in ("true", "1", "skip", "yes", "x"):
        return True
    if instructions and re.search(r"\bskip\b", str(instructions), re.IGNORECASE):
        return True
    return False


def read_reviewed_csv(csv_path: str) -> Tuple[List[str], List[Dict[str, str]]]:
    """Read a reviewed CSV file.
    Returns (headers, list of row dicts).
    Preserves all columns and short rows are padded.
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    if not reader:
        return [], []

    raw_headers = [h.strip() for h in reader[0]]
    # Normalize headers mapping synonyms
    headers = [HEADER_SYNONYMS.get(h, h) for h in raw_headers]

    rows: List[Dict[str, str]] = []
    for r in reader[1:]:
        # Pad short rows
        padded = list(r) + [""] * (len(headers) - len(r))
        row_dict: Dict[str, str] = {}
        for i, h in enumerate(headers):
            row_dict[h] = padded[i]
        rows.append(row_dict)

    return headers, rows


def compute_clip_numbers(rows: List[Dict[str, str]]) -> List[str]:
    """Calculate 1-indexed clip numbers for non-skipped rows in order."""
    clip_num = 1
    clips: List[str] = []
    for r in rows:
        if is_row_skipped(r.get("instructions"), r.get("skip")):
            clips.append("")
        else:
            clips.append(str(clip_num))
            clip_num += 1
    return clips


def write_reviewed_csv(
    csv_path: str,
    headers: List[str],
    rows: List[Dict[str, Any]],
    create_backup: bool = True
) -> None:
    """Write rows back to CSV atomically with CRLF line endings.
    If 'clip' column exists in headers, recomputes clip numbering.
    """
    has_clip_col = "clip" in headers
    if has_clip_col:
        clips = compute_clip_numbers(rows)
        for i, r in enumerate(rows):
            r["clip"] = clips[i]

    # Backup existing file if requested
    if create_backup and os.path.exists(csv_path):
        os.makedirs(TMP_BACKUPS, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        base_name = os.path.basename(csv_path)
        backup_path = os.path.join(TMP_BACKUPS, f"{base_name}.{ts}.bak")
        try:
            with open(csv_path, "rb") as src, open(backup_path, "wb") as dst:
                dst.write(src.read())
        except Exception as e:
            print(f"Warning: backup failed: {e}")

        # Sibling backup in same directory matching existing convention: .bak-MMDD-HHMMSS
        sibling_ts = datetime.datetime.now().strftime("%m%d-%H%M%S")
        sibling_bak = f"{csv_path}.bak-{sibling_ts}"
        try:
            with open(csv_path, "rb") as src, open(sibling_bak, "wb") as dst:
                dst.write(src.read())
        except Exception as e:
            print(f"Warning: sibling backup failed: {e}")

    # Write atomically via temp file
    dir_name = os.path.dirname(os.path.abspath(csv_path))
    os.makedirs(dir_name, exist_ok=True)

    with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, newline="", encoding="utf-8") as tf:
        tmp_name = tf.name
        writer = csv.writer(tf, lineterminator="\r\n")
        writer.writerow(headers)

        for r in rows:
            row_vals = []
            for h in headers:
                val = r.get(h, "")
                if val is None:
                    val = ""
                # Keep string format, never coerce player or text
                row_vals.append(str(val))
            writer.writerow(row_vals)

    # Atomic replace
    os.replace(tmp_name, csv_path)
