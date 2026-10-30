#!/usr/bin/env python3
"""Check the finished outputs of one game day (run at the end of run_everything_<day>.bat, or by hand).

  python tools\\pipeline\\check_outputs.py --out out\\2026-03-29 --day 2026-03-29

For every reel in <out>\\reels\\*.mp4 and the full game (<root>\\YYYY_MM_DD_full_game.mp4): video and audio length must agree
(within 0.3 s); the full game must also match the length printed by fullgame_bat.py (within 3 s). Prints OK / CHECK per file.
"""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils\ on PATH
import argparse
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from xbotgo_core.output_checker import check_game_outputs

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--day", required=True)
a = ap.parse_args()


def main():
    root = os.path.abspath(".")
    res = check_game_outputs(out_dir=a.out, day=a.day, root=root)

    for item in res["results"]:
        status = item["status"]
        rel = item["relpath"]
        v = item["video_dur"]
        au = item["audio_dur"]
        msgs = item["messages"]

        dur_info = f"  video {v:.1f}s audio {au:.1f}s" if v and au else ""
        msg_info = f"  <- {'; '.join(msgs)}" if msgs else ""
        print(f"{status:6}{rel}{dur_info}{msg_info}")

    if res["all_ok"]:
        print("ALL OK")
    else:
        print(f"{res['bad_count']} file(s) to look at")


if __name__ == "__main__":
    main()
