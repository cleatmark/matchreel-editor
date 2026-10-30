#!/usr/bin/env python3
"""Write ONE thin run file for a game day; the work is done by tools/pipeline/run_everything.py (any OS).

  python tools/pipeline/make_run_all.py --day 2026-03-14      # -> out/2026-03-14/run_everything_2026-03-14.bat (game folder; with several games the first one)
  python tools/pipeline/make_run_all.py --out out/2026-03-14 [--player 11] [--dry-run]
The .bat only changes to the project folder and calls `python tools\\pipeline\\run_everything.py`; a small run_everything_<day>.args.json
next to it lets the editor start the same run on non-Windows systems. Handles one game (out/<day>) or several (out/<day>-g1, -g2 ...).
Stages: title cards -> full game (skip-if-valid) -> 4K clips/replays/reels -> check_outputs. Safe to stop and re-run (resumable).
"""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils/ on PATH
import argparse, json, os, re, subprocess, sys
import run_everything as RE

ap = argparse.ArgumentParser()
ap.add_argument("--day")
ap.add_argument("--out")
ap.add_argument("--root", default=None)
ap.add_argument("--player", default=None, help="comma-separated featured player numbers for spotlights (default: featured_players from config)")
ap.add_argument("--dry-run", action="store_true", help="print the planned steps without writing or running anything")
a = ap.parse_args(); root = os.path.abspath(a.root or xb_env.ROOT)
if not a.player:
    from xbotgo_core import app_config
    a.player = app_config.default_featured_player(root)

day = a.day or (RE.day_of(a.out) if a.out else None)
if not day:
    sys.exit("need --day or --out")
outs = RE.find_outs(root, day, a.out)
if not outs:
    sys.exit(f"no out/{day}* folder with game_info.json - write game_info.json first (see make_reels.py)")

# Title cards must exist before the full game can be assembled
if not a.dry_run:
    for d in outs:
        rel = os.path.relpath(d, root)
        if not (os.path.exists(os.path.join(d, "clips", "cards", "000_intro_fullgame.mp4")) or
                os.path.exists(os.path.join(d, "work", "clips", "cards", "000_intro_fullgame.mp4"))):
            print(f"[make_run_all] Generating title cards for {rel}...")
            subprocess.run([sys.executable, os.path.join(root, "tools", "pipeline", "make_reels.py"), "--out", rel, "--stage", "cards"], cwd=root)

name = f"run_everything_{day}.bat"
gf = os.path.relpath(outs[0], root)
winroot = root if re.match(r"^[A-Za-z]:[\\/]", root) else (os.environ.get("XBOTGO_WINROOT") or root)
out_args = f'--out "{os.path.relpath(outs[0], root)}" ' if len(outs) == 1 else ""
L = ["@echo off",
     f"rem Runs everything for {day} serially, no prompts. Safe to stop and run again (finished pieces are skipped).",
     f"rem Log: {gf}\\run_everything_{day}.log",
     f'cd /d "{winroot}"',
     f"python tools\\pipeline\\run_everything.py {out_args}--day {day} --player {a.player}",
     "timeout /t 20 >nul", ""]
bat_content = "\r\n".join(L)

if a.dry_run:
    print(f"[DRY-RUN] Would write {os.path.join(gf, name)} ({len(outs)} game(s)); the run_everything.py steps are:")
    print("----------------------------------------------------------------------")
    for heading, argv, _ in RE.build_plan(root, outs, day, a.player):
        print(f"===== {heading} =====\n  {' '.join(argv[1:])}")
    print("===== 4. Checking lengths and outputs =====\n  " + " ".join(RE.check_cmd(root, outs, day)[1:]))
    print("----------------------------------------------------------------------")
    print(bat_content)
    print("----------------------------------------------------------------------")
else:
    open(os.path.join(outs[0], name), "w", newline="").write(bat_content)
    # macOS/Linux twin: same thin wrapper around the platform-independent run_everything.py
    sh_content = ("#!/bin/sh\n# Runs everything for %s serially, no prompts. Safe to stop and run again.\n"
                  'cd "$(dirname "$0")/%s" || exit 1\n'
                  "python3 tools/pipeline/run_everything.py %s--day %s --player %s\n"
                  % (day, "/".join([".."] * len(os.path.relpath(outs[0], root).replace("\\", "/").split("/"))), out_args.replace('"', "'"), day, a.player))
    shp = os.path.join(outs[0], f"run_everything_{day}.sh")
    open(shp, "w", newline="\n").write(sh_content)
    try: os.chmod(shp, 0o755)
    except OSError: pass
    json.dump({"out": os.path.relpath(outs[0], root), "day": day, "player": str(a.player), "games": len(outs)},
              open(os.path.join(outs[0], f"run_everything_{day}.args.json"), "w"))
    print("wrote", os.path.join(gf, name), f"({len(outs)} game(s))")
