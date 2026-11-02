#!/usr/bin/env python3
"""Build the review table for one game straight from the MP4 uuid box (ScoreLog / ManualMark, true
video seconds) + the app log pauses. No OCR. Writes, next to --out:
  review.csv (sheet format), timeline.json, clockmap.json, game_info.json (partial; fill logos by hand if missing).

Layouts supported: <day>/Videos + <day>/com.blink.blinkfocos/files, or the older DCIM/Android one (dumplayout.py).

  review_from_log.py --day 03-21-26 --out out/2026-03-21/review.csv
  review_from_log.py --day 03-14-26 --files a.mp4,b.mp4 --out out/2026-03-14-g1/review.csv      # two games in one dump
"""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils\ on PATH
import argparse
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from xbotgo_core.log_importer import (
    extract_match_info as box,
    probe_duration as dur,
    format_mmss as mmss,
    format_gclk as gclk,
    build_review_from_log
)

ap = argparse.ArgumentParser()
ap.add_argument('--day', required=True)
ap.add_argument('--files', default='')
ap.add_argument('--pauses', default=None)
ap.add_argument('--out', default=None, help='review.csv path; default out/<date of first video>/review.csv under the XbotGo folder')
ap.add_argument('--home', default=None, help='home team name (default: team_name from config/game_defaults.json)')
ap.add_argument('--tz', default='America/New_York')
ap.add_argument('--lead', type=float, default=12)
ap.add_argument('--post', type=float, default=4)
ap.add_argument('--merge-window', type=float, default=60)
ap.add_argument('--min-half-pause', type=float, default=120)
a = ap.parse_args()


def main():
    res = build_review_from_log(
        day=a.day,
        out_csv=a.out,
        files=a.files,
        pauses_override=a.pauses,
        home=a.home,
        tz_str=a.tz,
        lead=a.lead,
        post=a.post,
        merge_window=a.merge_window,
        min_half_pause=a.min_half_pause
    )
    half = res["half"]
    ht = res["ht_score"]
    final = res["final_score"]

    print('pauses (file idx: [(pos s, dur s)]):', {i: p for i, p in res["pauses"].items()})
    print(
        'half time:',
        half and f'file {half[0]} pos {half[1]:.1f}s ({mmss(half[1])}) dur {half[2]:.0f}s',
        '| half-time score', f'{ht[0]}-{ht[1]}',
        '| final', f'{final[0]}-{final[1]}'
    )
    for s in res["goal_summary"]:
        print(s)
    print('rows', len(res["rows"]), '->', res["csv_path"])


if __name__ == "__main__":
    main()
