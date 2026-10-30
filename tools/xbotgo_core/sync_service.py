"""State reconciliation and sync service for game clips, replays, and review sheet.
Brings a game's reviewed CSV, clips, zoom replays and preview reel in line with the sheet or local CSV.
Nothing is ever deleted: old files are moved to clips/dropped or clips/stale.
"""
from .diag import swallowed as _swallowed
import csv
import json
import os
import re
import sys
import time
from typing import Dict, Any, List, Optional, Tuple

# Import xbl helpers from tools/
TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from .xbl import Game, is_zoom, move_aside, token_of, row_skip


def read_incoming(json_path: Optional[str] = None, csv_path: Optional[str] = None) -> List[List[str]]:
    """Read incoming rows from JSON or CSV file."""
    if json_path:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    if csv_path:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            return list(csv.reader(f))
    raise ValueError("Neither json_path nor csv_path provided")


def two_phase_rename(folder: str, ops: List[Tuple[str, str]]) -> None:
    """Rename ops [(old, new)] in two phases without filename collisions."""
    ops = [(o, n) for o, n in ops if o != n]
    for o, n in ops:
        os.replace(os.path.join(folder, o), os.path.join(folder, "~tmp~" + o))
    for o, n in ops:
        os.replace(os.path.join(folder, "~tmp~" + o), os.path.join(folder, n))


def sync_game_state(
    out_dir: str,
    json_path: Optional[str] = None,
    csv_path: Optional[str] = None,
    is_local: bool = False,
    dry_run: bool = False
) -> Dict[str, Any]:
    """Reconcile reviewed CSV, clips, zoom state, and generate clip_column.json.
    
    Returns a dict with:
        changes: list of human-readable clip/replay change descriptions
        todo: list of pending zoom actions needed
        job_count: int
        skipped_count: int
        zoom_count: int
        sheet_row_count: int
        clip_column_path: str
        csv_path: str
        game: Game instance
    """
    g = Game(out_dir)

    # ---- Old state (before touching the CSV) -------------------------------
    old_plan = {}
    pp = os.path.join(g.out, "cut_plan.json")
    if not os.path.exists(pp) and os.path.exists(os.path.join(g.out, "work", "cut_plan.json")):
        pp = os.path.join(g.out, "work", "cut_plan.json")
    if os.path.exists(pp):
        try:
            with open(pp, "r", encoding="utf-8") as f:
                for p in json.load(f):
                    tok = token_of(p["clip"])
                    old_plan[tok] = p
        except Exception:
            _swallowed()

    st = g.state()

    # ---- 1. Write the reviewed CSV -----------------------------------------
    sheet_rows = []
    if is_local:
        if not os.path.exists(g.csv):
            raise FileNotFoundError(f"local mode: reviewed CSV not found: {g.csv}")
        with open(g.csv, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        header = [h.strip() for h in rows[0]]
        for r in rows[1:]:
            r = list(r) + [""] * (len(header) - len(r))
            d = {header[i]: r[i] for i in range(len(header))}
            sheet_rows.append(d)
    else:
        inc = read_incoming(json_path=json_path, csv_path=csv_path)
        header = [h.strip() for h in inc[0]]
        keep = [i for i, h in enumerate(header) if h != "clip"]
        hdr = [header[i] for i in keep]
        body = []
        for r in inc[1:]:
            r = list(r) + [""] * (len(header) - len(r))
            d = {header[i]: r[i] for i in range(len(header))}
            sheet_rows.append(d)
            if (d.get("file") or "").strip():
                body.append([r[i] for i in keep])

        if not dry_run:
            if os.path.exists(g.csv):
                os.replace(g.csv, g.csv + ".bak-" + time.strftime("%m%d-%H%M%S"))
            os.makedirs(os.path.dirname(os.path.abspath(g.csv)), exist_ok=True)
            with open(g.csv, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, lineterminator="\r\n")
                w.writerow(hdr)
                w.writerows(body)

    jobs = Game(out_dir).jobs() if not dry_run else g.jobs()
    new = {g.token(j): j for j in jobs}
    skipped = sum(1 for r in g.rows() if row_skip(r))
    zoom_rows_count = sum(1 for j in jobs if is_zoom(j["row"]))

    # ---- 2-4. Clips ----------------------------------------------------------
    changes = []
    drop_dir = os.path.join(g.out, "clips", "dropped")
    stale_dir = os.path.join(g.out, "clips", "stale")

    if os.path.isdir(g.clipdir):
        ops = []
        for f in sorted(os.listdir(g.clipdir)):
            tok = token_of(f)
            if not f.endswith(".mp4") or tok is None:
                continue
            p = os.path.join(g.clipdir, f)
            if tok not in new:
                changes.append(f"drop   {f}")
                if not dry_run:
                    move_aside(p, drop_dir)
                continue
            j = new[tok]
            o = old_plan.get(tok)
            if o and (abs(o["cin"] - j["cin"]) > 0.05 or abs(o["cout"] - j["cout"]) > 0.05):
                changes.append(
                    f"stale  {f} (bounds changed {o['cin']:.1f}-{o['cout']:.1f} -> {j['cin']:.1f}-{j['cout']:.1f}) - will re-cut"
                )
                if not dry_run:
                    move_aside(p, stale_dir)
                continue
            if f != j["clip"]:
                changes.append(f"rename {f} -> {j['clip']}")
                ops.append((f, j["clip"]))
        if ops and not dry_run:
            two_phase_rename(g.clipdir, ops)

    for tok, j in new.items():
        if tok not in old_plan:
            changes.append(f"new    {j['clip']}")

    # ---- 2,3,5,6. Replays ----------------------------------------------------
    reps = st["replays"]
    zoom_tokens = {t for t, j in new.items() if is_zoom(j["row"])}
    for sub in (g.extra, os.path.join(g.extra, "master")):
        if not os.path.isdir(sub):
            continue
        ops = []
        for f in sorted(os.listdir(sub)):
            m = re.match(r"^(\d+)b_((?:goal|mark|[a-z]+)_\d{6})_zoom3x_(\w+)\.mp4$", f)
            if not m:
                continue
            tok = m.group(2)
            p = os.path.join(sub, f)
            if tok not in zoom_tokens:
                changes.append(f"drop   replay {f} ({'row skipped/removed' if tok not in new else 'zoom removed'})")
                if not dry_run:
                    move_aside(p, drop_dir)
                continue
            r = reps.get(tok)
            if r and abs(r["event"] - new[tok]["event"]) > 0.5:
                changes.append(f"stale  replay {f} (event moved {r['event']} -> {new[tok]['event']}) - re-render")
                if not dry_run:
                    move_aside(p, stale_dir)
                continue
            nn = f"{new[tok]['n']:03d}b_{tok}_zoom3x_{m.group(3)}.mp4"
            if nn != f:
                changes.append(f"rename replay {f} -> {nn}")
                ops.append((f, nn))
        if ops and not dry_run:
            two_phase_rename(sub, ops)

    todo = []
    for tok in sorted(zoom_tokens, key=lambda t: new[t]["n"]):
        j = new[tok]
        r = reps.get(tok)
        if r is None:
            reps[tok] = {
                "n": j["n"], "event": j["event"], "file": j["file"], "path": j["path"], "crop": None,
                "start": None, "dur": None, "cut_start": 0.0, "cut_end": 0.0, "master_key": None,
                "final_key": None, "history": []
            }
            todo.append(f"clip {j['n']} {tok}: new zoom row - needs a crop")
        else:
            r["n"] = j["n"]
            if abs(r["event"] - j["event"]) > 0.5:
                r.update(
                    event=j["event"], start=None, dur=None, cut_start=0.0, cut_end=0.0,
                    master_key=None, final_key=None
                )
                todo.append(f"clip {j['n']} {tok}: event changed - re-render (crop kept)")

    for tok in list(reps):
        if tok not in zoom_tokens:
            st["removed"][tok] = reps.pop(tok)

    clip_col_path = os.path.join(g.out, "clip_column.json")
    if not dry_run:
        g.save_state(st)
        # ---- 8. Clip column ---------------------------------------------------
        col = [["clip"]]
        rows_by_key = {}
        for j in jobs:
            rows_by_key[(j["row"].get("file"), j["row"].get("video_sec"), j["row"].get("type"), j["row"].get("video_time"))] = j["n"]
        for d in sheet_rows:
            n = rows_by_key.get((d.get("file"), d.get("video_sec"), d.get("type"), d.get("video_time")))
            col.append([n if n is not None else ""])
        with open(clip_col_path, "w", encoding="utf-8") as f:
            json.dump(col, f)

    return {
        "changes": changes,
        "todo": todo,
        "job_count": len(jobs),
        "skipped_count": skipped,
        "zoom_count": zoom_rows_count,
        "sheet_row_count": len(sheet_rows),
        "clip_column_path": clip_col_path,
        "csv_path": g.csv,
        "game": g
    }
