#!/usr/bin/env python3
"""Write the Windows batch file that merges a full game for YouTube.

  intro card -> 1st half -> HALFTIME card -> 2nd half      (no outro)

Video is stream-copied (native 4K, never re-encoded); the joined audio is
re-encoded once at volume 0.4. Pieces are joined as MPEG-TS (never the concat
demuxer).

The half-time card goes at the half-time PAUSE (longest clock-map jump
>= 120 s), not at a file boundary. The file holding the pause is split with
stream copy at the first video keyframe at/after the pause position (the
phone usually writes a fresh keyframe on resume; otherwise GOPs are ~2 s, so
at most ~2 s of 2nd-half footage lands before the card).

  python3 tools/pipeline/fullgame_bat.py --out out/2026-03-07 \
      [--cards out/2026-03-07/clips/cards] [--bat out/bat/run_full_game_2026-03-07.bat] \
      [--no-halftime] [--winroot <project folder>]

Cards must already exist: title_cards.py ... --halftime-score H-A --fullgame
(000_intro_fullgame.mp4, 500_halftime_fullgame.mp4). Prints the expected
length and the YouTube offsets (2nd-half chapter, per-segment shift).
"""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils\ on PATH
import argparse, json, math, os, re, subprocess

BS = chr(92)

def sh(c): return subprocess.run(c, capture_output=True, text=True)
def dur(f):
    try: return float(sh(["ffprobe","-v","error","-show_entries","format=duration",
                          "-of","csv=p=0",f]).stdout.strip())
    except ValueError: return -1.0

def winpath(p, winroot):
    ap = os.path.abspath(p)
    if re.match(r"^[A-Za-z]:[\\/]", ap): return ap.replace("/", BS)        # already a Windows path (script run on the PC)
    m = re.search(r"/mnt/[^/]+/?(.*)$", ap)
    rel = m.group(1) if m else os.path.basename(ap)
    return winroot.rstrip(BS) + BS + rel.replace("/", BS)

def keyframe_at_or_after(f, pos, span=6.0):
    r = sh(["ffprobe","-v","error","-read_intervals",f"{max(0,pos-1):.3f}%+{span}",
            "-select_streams","v","-show_entries","packet=pts_time,flags","-of","csv=p=0",f])
    ks = [float(l.split(",")[0]) for l in r.stdout.split() if ",K" in l]
    after = [k for k in ks if k >= pos - 0.05]
    if not after: raise SystemExit(f"no keyframe found after {pos:.2f}s in {f}")
    return after[0]

def hhmmss(s):
    s = int(round(s)); return f"{s//3600}:{s%3600//60:02d}:{s%60:02d}"

def probe_ok(path, expected, tol=3.0):
    return os.path.exists(path) and abs(dur(path) - expected) <= tol

def run_plan(steps, tmp, dst, part, total, date):
    """Execute the full-game build natively. Skips when a valid full game exists; the final file is only
    ever created by renaming a verified .partial.mp4, so a cancel can never leave a broken final video."""
    print(f"=== {date} - full game ===")
    if probe_ok(dst, total):
        print(f"Full game already finished - skipping ({dst})"); return 0
    if os.path.exists(part): os.remove(part)
    os.makedirs(tmp, exist_ok=True)
    N = len(steps) + 1
    for i, (label, cmd, _) in enumerate(steps, 1):
        print(f"[{i}/{N}] {label}", flush=True)
        if subprocess.run(cmd).returncode != 0: raise SystemExit(f"FAILED at step {i}: {label} (temp files in {tmp})")
    print(f"[{N}/{N}] joining + audio at 0.4", flush=True)
    cat = "|".join(os.path.join(tmp, t) for _, _, t in steps)
    r = subprocess.run(["ffmpeg", "-v", "error", "-stats", "-i", "concat:" + cat, "-map", "0:v", "-map", "0:a",
                        "-c:v", "copy", "-af", "volume=0.4", "-c:a", "aac", "-b:a", "192k",
                        "-movflags", "+faststart", "-f", "mp4", "-y", part])
    if r.returncode != 0: raise SystemExit("FAILED joining full game")
    if not probe_ok(part, total):
        raise SystemExit(f"FAILED: joined file length {dur(part):.1f}s, expected about {total:.1f}s")
    os.replace(part, dst)
    for t in os.listdir(tmp):
        if t.endswith(".ts"): os.remove(os.path.join(tmp, t))
    try: os.rmdir(tmp)
    except OSError: pass
    print(f"Done: {dst}  ({dur(dst):.1f} s, expected about {total:.1f} s)")
    return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="out/<YYYY-MM-DD>")
    ap.add_argument("--cards", default=None)
    ap.add_argument("--bat", default=None)
    ap.add_argument("--winroot", default=os.environ.get("XBOTGO_WINROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), help="project folder as the Windows machine sees it (default: this tree)")
    ap.add_argument("--no-halftime", action="store_true")
    ap.add_argument("--min-pause", type=float, default=120.0)
    ap.add_argument("--run", action="store_true", help="build the full game now (any OS) instead of only writing the .bat")
    ap.add_argument("--title", default="", help="header line, e.g. 'Home FC v Guest FC (League A)'")
    a = ap.parse_args()

    tl = json.load(open(os.path.join(a.out, "timeline.json"), encoding="utf-8"))
    cm = json.load(open(os.path.join(a.out, "clockmap.json"), encoding="utf-8"))
    date = tl["date"]; pfx = date.replace("-", "_")
    cards = a.cards or os.path.join(a.out, "clips", "cards")
    bat = a.bat or os.path.join(os.path.dirname(os.path.abspath(a.out)), "bat",
                                f"run_full_game_{date}.bat")
    W = lambda p: winpath(p, a.winroot)
    ff = a.winroot.rstrip(BS) + BS + "utils" + BS + "ffmpeg" + BS + "bin" + BS + "ffmpeg.exe"
    fp = a.winroot.rstrip(BS) + BS + "utils" + BS + "ffmpeg" + BS + "bin" + BS + "ffprobe.exe"
    tmp = os.path.join(xb_env.tmp_for(a.out), "fullgame_tmp")
    dst = os.path.join(a.out, f"{pfx}_full_game.mp4")
    part = dst[:-4] + ".partial.mp4"

    intro = os.path.join(cards, "000_intro_fullgame.mp4")
    half = os.path.join(cards, "500_halftime_fullgame.mp4")
    if not os.path.exists(intro): raise SystemExit("missing " + intro)
    use_ht = not a.no_halftime
    if use_ht and not os.path.exists(half): raise SystemExit("missing " + half)

    # half-time pause = largest offset jump
    ht = None
    for vi, v in enumerate(tl["videos"]):
        segs = cm.get(v["file"], [])
        for i in range(len(segs) - 1):
            gap = segs[i+1]["offset"] - segs[i]["offset"]
            if gap >= a.min_pause and (ht is None or gap > ht[2]):
                ht = (vi, segs[i]["pos_end"], gap)
    if use_ht and ht is None:
        raise SystemExit("no half-time pause >= %.0fs in clockmap.json - use --no-halftime" % a.min_pause)

    def ts_cmd(src, out_ts, pre=()):
        return ["ffmpeg", "-v", "error", "-stats", *pre, "-i", src, "-c", "copy",
                "-bsf:v", "h264_mp4toannexb", "-f", "mpegts", "-y", os.path.join(tmp, out_ts)]

    steps = [("intro card", ts_cmd(intro, "00_intro.ts"), "00_intro.ts")]
    t_intro = dur(intro); t_half = dur(half) if use_ht else 0.0
    total = t_intro; n = 0; split_k = None
    for vi, v in enumerate(tl["videos"]):
        src = os.path.abspath(v["path"]); d = v["duration"]; total += d
        if use_ht and vi == ht[0]:
            k = keyframe_at_or_after(v["path"], ht[1]); split_k = k
            # -t must stop just BEFORE the keyframe, -ss must land ON it: an
            # input seek with -c copy snaps to the keyframe at or before the
            # time, so a value rounded down (1788.129 < 1788.1294) would pull
            # in the previous GOP (~2 s of duplicated 1st-half footage).
            k_end = math.floor(k * 1000) / 1000; k_seek = math.ceil(k * 1000) / 1000 + 0.001
            n += 1; ta = f"{n:02d}.ts"
            c = ts_cmd(src, ta); c[c.index("-c"):c.index("-c")] = ["-t", f"{k_end:.3f}"]
            steps.append((f"file {vi+1} up to half time ({hhmmss(k)})", c, ta))
            steps.append(("half-time card", ts_cmd(half, f"{n:02d}h.ts"), f"{n:02d}h.ts"))
            n += 1; tb = f"{n:02d}.ts"
            steps.append((f"file {vi+1} from half time", ts_cmd(src, tb, pre=["-ss", f"{k_seek:.3f}"]), tb))
        else:
            n += 1; t = f"{n:02d}.ts"
            steps.append((f"file {vi+1} of {len(tl['videos'])}", ts_cmd(src, t), t))
    total += t_half

    if a.run:
        return run_plan(steps, tmp, dst, part, total, date)

    # The .bat is a thin wrapper: all logic (skip-if-finished, .partial + rename) lives in Python, so it is
    # identical and testable on every OS.
    me = a.winroot.rstrip(BS) + BS + "tools" + BS + "pipeline" + BS + "fullgame_bat.py"
    extra = " --no-halftime" if a.no_halftime else ""
    cards_arg = f' --cards "{W(cards)}"' if a.cards else ""
    L = ["@echo off", "setlocal", f'cd /d "{a.winroot}"',
         f'python "{me}" --out "{W(a.out)}"{cards_arg}{extra} --winroot "{a.winroot}" --run || goto :fail',
         "pause", "exit /b 0", ":fail", "echo.",
         "echo FAILED - see the error above. Partial files are never used as the final video.", "pause", "exit /b 1"]
    os.makedirs(os.path.dirname(bat), exist_ok=True)
    open(bat, "w", newline="\r\n").write("\n".join(L) + "\n")

    print("bat      :", bat)
    print(f"expected : {total:.1f} s  (intro {t_intro:.1f}" + (f" + halftime {t_half:.1f}" if use_ht else "") + ")")
    if use_ht:
        before = sum(v["duration"] for v in tl["videos"][:ht[0]])
        chap = t_intro + before + split_k
        print(f"half time: file {ht[0]+1} pause at {ht[1]:.2f}s ({ht[2]:.0f}s), split at keyframe {split_k:.3f}s")
        print(f"YouTube  : '2nd Half Kickoff' chapter at {hhmmss(chap)} (start of the halftime card);")
        print(f"           events before the split: +{t_intro:.0f}s; after it: +{t_intro+t_half:.0f}s")
    else:
        print(f"YouTube  : every event +{t_intro:.0f}s")

if __name__ == "__main__": raise SystemExit(main() or 0)
