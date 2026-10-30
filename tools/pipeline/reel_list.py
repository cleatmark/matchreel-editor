#!/usr/bin/env python3
"""Print the reel_build.py inputs for a game from the reviewed sheet export.

  python3 tools/pipeline/reel_list.py --csv out/reviewed/<date>_reviewed.csv --out out/<date> \
      [--clipdir reviewed4k] [--no-halftime]

Prints three lines:
  CLIPS=<cards/000_intro.mp4,clip...,cards/500_halftime.mp4,clip...,cards/999_outro.mp4>
  CHEERS=<our goal clip basenames>
  HALFTIME_SCORE=<home-away at the half-time whistle>
"""
import argparse
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from xbotgo_core.reel_service import calculate_reel_manifest, row_skip, has_value as has


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--clipdir", default="reviewed4k")
    ap.add_argument("--no-halftime", action="store_true")
    a = ap.parse_args()

    res = calculate_reel_manifest(
        csv_path=a.csv,
        out_dir=a.out,
        clipdir=a.clipdir,
        no_halftime=a.no_halftime
    )

    print("CLIPS=" + ",".join(res["clips"]))
    print("CHEERS=" + ",".join(res["cheers"]))
    print("HALFTIME_SCORE=" + res["halftime_score"])


if __name__ == "__main__":
    main()
