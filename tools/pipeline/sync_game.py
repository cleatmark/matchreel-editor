#!/usr/bin/env python3
"""Bring a game's reviewed CSV, clips, zoom replays and preview reel in line with the sheet.

  python3 tools/pipeline/sync_game.py --out out/2026-03-14-g1 --json values.json     # sheet values (list of rows, header first)
  python3 tools/pipeline/sync_game.py --out out/2026-03-14-g1 --csv  tab_export.csv   # or File > Download > CSV of the tab
  options: --no-cut (don't run cut_reviewed)  --no-reel (don't rebuild the preview reel)  --dry-run
"""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils\ on PATH
import argparse
import os
import subprocess
import sys

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from xbotgo_core.xbl import sh, PY

# Whole-game cut limit. None = no limit (a first cut of ~25 clips takes 5-10 min on the PC; the old fixed 170 s
# came from the 3-minute device-shell cap and made every first Re-cut fail). Set XBOTGO_CUT_TIMEOUT_S to cap it.
CUT_TIMEOUT_S = float(os.environ.get("XBOTGO_CUT_TIMEOUT_S", "0")) or None
import preview_reel
from xbotgo_core.sync_service import sync_game_state, read_incoming, two_phase_rename


from xbotgo_core.procs import run_streaming  # noqa: F401  (kept importable from here)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--json")
    ap.add_argument("--csv")
    ap.add_argument("--no-cut", action="store_true")
    ap.add_argument("--no-reel", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--local", action="store_true", help="use local reviewed CSV as-is without pulling or overwriting it")
    a = ap.parse_args()

    if not (a.json or a.csv or a.local):
        sys.exit("give --json, --csv or --local")

    if a.local:
        # Check CSV existence before running
        from xbotgo_core.xbl import Game
        g_check = Game(a.out)
        if not os.path.exists(g_check.csv):
            sys.exit(f"local mode: reviewed CSV not found: {g_check.csv}")

    res = sync_game_state(
        out_dir=a.out,
        json_path=a.json,
        csv_path=a.csv,
        is_local=a.local,
        dry_run=a.dry_run
    )

    g = res["game"]
    if a.local:
        print(f"local mode: using existing reviewed CSV {g.csv} ({res['sheet_row_count']} rows)")
    elif a.dry_run:
        print("dry run: would write", g.csv, f"({res['sheet_row_count']} rows)")

    print(f"{res['job_count']} clips, {res['skipped_count']} skipped, {res['zoom_count']} zoom rows")
    print("\n".join(res["changes"]) or "no clip changes")
    print("\n".join(res["todo"]))

    # ---- Cut + Reel ---------------------------------------------------------
    recut_failed = False
    failure_reasons = []

    if not a.dry_run and not a.no_cut:
        cmd = [
            PY, os.path.join("tools", "pipeline", "cut_reviewed.py"), "--csv", g.csv, "--out", g.out, "--roster", g.roster_path,
            "--bounds", "startend", "--height", "720", "--preset", "ultrafast", "--crf", "26",
            "--clipdir", "preview720", "--no-reels"
        ]
        try:
            r = run_streaming(cmd, timeout=CUT_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            sys.exit(f"ERROR: cut_reviewed exceeded {CUT_TIMEOUT_S}s (XBOTGO_CUT_TIMEOUT_S); run Re-cut again, finished clips are kept")
        tail = [l for l in r.stdout.splitlines() if "ok" in l or "redo" in l or "FAIL" in l or "clips" in l]
        print("cut_reviewed:", " | ".join(tail[-6:]) or r.stdout[-200:])

        fails = [l.strip() for l in (r.stdout + "\n" + r.stderr).splitlines() if "FAIL " in l or "FAIL\t" in l]
        if r.returncode != 0:
            recut_failed = True
            failure_reasons.append(f"cut_reviewed process exited with error code {r.returncode}")
        if fails:
            recut_failed = True
            clip_names = [f.split()[-1] for f in fails]
            failure_reasons.append(f"{len(fails)} clip(s) failed to cut: {', '.join(clip_names)}")

    if not a.dry_run and not a.no_reel:
        dst, total, got = preview_reel.build(g, with_replays=False, quiet=True)
        if total > 0 and (got is None or abs(got - total) >= preview_reel.LENGTH_TOLERANCE_S):
            recut_failed = True
            failure_reasons.append(f"preview reel check failed (expected {total:.1f}s, got {got})")

    if not a.dry_run:
        print(f"clip numbers saved for the sheet (column P, {res['sheet_row_count']} rows): {res['clip_column_path']}")

    if recut_failed:
        err_msg = "Re-cut finished with errors:\n  - " + "\n  - ".join(failure_reasons)
        print(f"\nERROR: {err_msg}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
