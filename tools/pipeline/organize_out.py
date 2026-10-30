#!/usr/bin/env python3
"""Tidy out\\<game> folders: final reels -> final\\, inputs needed to regenerate -> work\\, intermediates -> _to_delete\\.
Nothing is deleted. Every move is recorded in out\\_organize_manifest.json and can be undone with --restore.

  python tools\\pipeline\\organize_out.py            # dry run: prints the plan with sizes
  python tools\\pipeline\\organize_out.py --apply    # does the moves
  python tools\\pipeline\\organize_out.py --restore  # puts everything back (all games, uses the manifest)
  python tools\\pipeline\\organize_out.py --untidy --only 2026-04-01 [--apply]   # one game: work\\ and final\\ back to the game folder (to re-render)
"""
import argparse
import os
import sys

# Ensure tools is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xbotgo_core.organize_service import (
    file_or_dir_size as size,
    plan_game,
    plan_all,
    execute_organize_plan,
    restore_organize_manifest,
    plan_untidy,
    execute_untidy,
    is_tidied_dir,
    match_patterns as m,
    FINAL_FILES,
    WORK_FILES,
    DEL_FILES,
    DEL_DIRS
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "out"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--untidy", action="store_true", help="undo Tidy for the games in --only (work/ and final/ back to the game root); with --apply to do it")
    a = ap.parse_args()

    man_p = os.path.join(ROOT, "_organize_manifest.json")
    if a.restore:
        cnt = restore_organize_manifest(man_p)
        print(f"restored {cnt} moves (empty final/work/_to_delete folders can be removed)")
        return

    only_games = a.only.split(",") if a.only else None
    if a.untidy:
        if not only_games:
            sys.exit("--untidy needs --only <game folder name(s)>")
        man_u = os.path.join(ROOT, "_organize_manifest.json")
        for gname in only_games:
            g = os.path.join(ROOT, gname)
            ops = plan_untidy(g)
            print(f"== {gname}: {'tidied' if is_tidied_dir(g) else 'not tidied'}; {len(ops)} item(s) would move back to the game folder")
            for src, dst in ops:
                print(f"   {os.path.relpath(src, g)} -> {os.path.relpath(dst, g)}  ({size(src)/2**20:.0f} MB)")
            if a.apply:
                moved, skipped = execute_untidy(ops, man_u, gname)
                for sk in skipped:
                    print("  exists, skipped:", sk)
                print("moved back", moved, "items")
        if not a.apply:
            print("\n(dry run - nothing moved; add --apply)")
        return
    plan_res = plan_all(ROOT, only_games=only_games)

    for d, gdata in plan_res["games"].items():
        g = gdata["path"]
        ops = gdata["ops"]
        unk = gdata["unknown"]
        s = gdata["sizes"]
        print(f"\n== {d}: final {s['final']/2**30:.1f} GB | work {s['work']/2**30:.1f} GB | to_delete {s['delete']/2**30:.1f} GB")
        for src, dst, b in ops:
            sz = size(src)
            if b == "final" or sz > 300e6 or (b == "work" and not a.apply and sz > 100e6):
                print(f"   {b:6} {sz/2**20:8.0f} MB  {os.path.relpath(src, g)} -> {dst}")
        for u in unk:
            print(f"   ?????? {size(u)/2**20:8.0f} MB  {os.path.relpath(u, g)}  (left in place)")

    if not only_games:
        print("\n== out\\ top level:")
        for src, dst, b in plan_res["shared"]:
            print(f"   {b:6} {size(src)/2**20:8.1f} MB  {os.path.basename(src)}")

    tot = plan_res["totals"]
    print(f"\nTOTAL final {tot['final']/2**30:.1f} GB | work {tot['work']/2**30:.1f} GB | to_delete {tot['delete']/2**30:.1f} GB")

    if a.apply:
        moved, skipped = execute_organize_plan(plan_res["all_moves"], man_p)
        for sk in skipped:
            print("  exists, skipped:", sk)
        print("moved", moved, "items; manifest", man_p)
    else:
        print("\n(dry run - nothing moved; add --apply)")


if __name__ == "__main__":
    main()
