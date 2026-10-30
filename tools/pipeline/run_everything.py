#!/usr/bin/env python3
"""Run everything for a game day, serially, no prompts, on any OS (Windows .bat files are thin wrappers around this).

  python tools/pipeline/run_everything.py --out out/2026-04-01 --day 2026-04-01 --player 11 [--dry-run]

Stages (same order and log format as the old run_everything_<day>.bat):
  1. title cards, 2. full game video (skip-if-valid, .partial + rename), 3. 4K clips + replays + reels, 4. check_outputs
Every stage is resumable (finished pieces are skipped), a failing stage is logged ("errorlevel N") and the run goes on,
the check at the end flags anything missing. Log: <out>/run_everything_<day>.log (the editor reads it; ends with ALL OK).
"""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils/ on PATH
import argparse, datetime, glob, os, subprocess, sys

ROOT = xb_env.ROOT
PY = sys.executable


def day_of(out_dir):
    b = os.path.basename(os.path.abspath(out_dir))
    return b[:10] if len(b) >= 10 and b[4] == "-" and b[7] == "-" else b


def find_outs(root, day=None, out=None):
    """One game folder (--out) or every out/<day>* folder that has a game_info.json."""
    if out:
        return [os.path.abspath(out)]
    found = sorted(d for d in glob.glob(os.path.join(root, "out", day + "*")) if os.path.isdir(d) and (
        os.path.exists(os.path.join(d, "game_info.json")) or os.path.exists(os.path.join(d, "work", "game_info.json"))))
    return found


def is_tidied(d):
    """True for a game folder after Tidy: timeline.json lives in work/ and the finished videos are in final/.
    Such a game is archived: re-running stages 2 and 3 would fail (timeline.json is not in the old place) or, worse,
    re-cut hours of 4K, so the runner skips them and only checks final/."""
    return (not os.path.exists(os.path.join(d, "timeline.json"))
            and os.path.exists(os.path.join(d, "work", "timeline.json"))
            and bool(glob.glob(os.path.join(d, "final", "*_full_game*.mp4"))))


def build_plan(root, outs, day, player, skip_tidied=False):
    """[(heading, argv, log_tag)] with argv relative to root (run with cwd=root).
    skip_tidied=True leaves out stages 2 and 3 for tidied games (see is_tidied)."""
    rel = lambda d: os.path.relpath(d, root)
    T = lambda s: os.path.join("tools", "pipeline", s)
    plan = []
    for d in outs:
        plan.append((f"1. Title cards: {rel(d)}", [PY, T("make_reels.py"), "--out", rel(d), "--stage", "cards"], f"{rel(d)} cards"))
    for d in outs:
        if skip_tidied and is_tidied(d):
            continue
        plan.append((f"2. Full game video: {os.path.basename(d)}", [PY, T("fullgame_bat.py"), "--out", rel(d), "--run"],
                     f"{os.path.basename(d)} full game"))
    for d in outs:
        if skip_tidied and is_tidied(d):
            continue
        plan.append((f"3. 4K clips, replays, reels: {rel(d)}",
                     [PY, T("make_reels.py"), "--out", rel(d), "--stage", "all", "--player", str(player)], f"{rel(d)} reels"))
    return plan


def check_cmd(root, outs, day):
    return [PY, os.path.join("tools", "pipeline", "check_outputs.py"), "--out", os.path.relpath(outs[0], root), "--day", day]


def stamp():
    return datetime.datetime.now().strftime("%a %m/%d/%Y %H:%M:%S.%f")[:-4]


def run(root, outs, day, player):
    log_path = os.path.join(outs[0], f"run_everything_{day}.log")
    env = dict(os.environ, PYTHONUNBUFFERED="1")

    def log(line):
        with open(log_path, "a", encoding="utf-8", newline="") as f:
            f.write(line + "\r\n")

    with open(log_path, "w", encoding="utf-8", newline="") as f:
        f.write(f"{stamp()} start \r\n")
    for d in outs:
        if is_tidied(d):
            print(f"===== {os.path.basename(d)} is tidied (finished videos are in final/): stages 2 and 3 skipped =====", flush=True)
            log(f"{stamp()} {os.path.basename(d)} full game errorlevel 0 (skipped: tidied game, see final)")
            log(f"{stamp()} {os.path.relpath(d, root)} reels errorlevel 0 (skipped: tidied game, see final)")
    for heading, argv, tag in build_plan(root, outs, day, player, skip_tidied=True):
        print(f"===== {heading} =====", flush=True)
        rc = subprocess.run(argv, cwd=root, env=env, stdin=subprocess.DEVNULL).returncode
        log(f"{stamp()} {tag} errorlevel {rc} ")
    print("===== 4. Checking lengths and outputs =====", flush=True)
    res = subprocess.run(check_cmd(root, outs, day), cwd=root, env=env, capture_output=True, text=True, errors="replace")
    for line in (res.stdout or "").splitlines():
        log(line)
    if res.stderr:
        for line in res.stderr.splitlines():
            log(line)
    try:
        print(open(log_path, encoding="utf-8", errors="replace").read(), flush=True)
    except OSError:
        pass
    print(f"ALL DONE - see {os.path.relpath(log_path, root)}", flush=True)
    return res.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day")
    ap.add_argument("--out")
    ap.add_argument("--root", default=None)
    ap.add_argument("--player", default=None, help="featured player number(s) for spotlights (default: featured_players from config)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.player:
        from xbotgo_core import app_config
        a.player = app_config.default_featured_player(a.root)
    root = os.path.abspath(a.root or ROOT)
    day = a.day or (day_of(a.out) if a.out else None)
    if not day:
        sys.exit("need --day or --out")
    outs = find_outs(root, day, a.out)
    if not outs:
        sys.exit(f"no out/{day}* folder with game_info.json - write game_info.json first (see make_reels.py)")
    if a.dry_run:
        for d in outs:
            if is_tidied(d):
                print(f"===== {os.path.basename(d)} is tidied: stages 2 and 3 will be skipped =====")
        for heading, argv, _ in build_plan(root, outs, day, a.player, skip_tidied=True):
            print(f"===== {heading} =====\n  {' '.join(argv[1:])}")
        print("===== 4. Checking lengths and outputs =====\n  " + " ".join(check_cmd(root, outs, day)[1:]))
        return 0
    return run(root, outs, day, a.player)


if __name__ == "__main__":
    raise SystemExit(main())
