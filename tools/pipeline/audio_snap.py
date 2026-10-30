#!/usr/bin/env python3
"""Locate the crowd-reaction peak near a mark, from the recording's audio."""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils\ on PATH
import subprocess, re, statistics, sys

def energy(video, start, dur, step=0.5):
    """[(video_position, RMS_dB)] over a window."""
    n = int(8000 * step)
    p = subprocess.run(
        ["ffmpeg","-v","error","-ss",f"{start:.2f}","-t",f"{dur:.2f}","-i",video,"-vn",
         "-af",f"aresample=8000,asetnsamples={n},astats=metadata=1:reset=1,"
               "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
         "-f","null","-"], capture_output=True, text=True)
    out, cur = [], 0.0
    for line in p.stdout.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m: cur = float(m.group(1)); continue
        m = re.search(r"RMS_level=(-?[\d.]+)", line)
        if m:
            try: out.append((start + cur, float(m.group(1))))
            except ValueError: pass
    return out

def snap(video, pos, back=25.0, fwd=15.0, context=60.0, smooth=3):
    """Return (best_position, lift_dB, baseline_dB) for the loudest sustained
    moment near `pos`. Baseline is the median over a wider context window."""
    lo = max(0.0, pos - context)
    ctx = energy(video, lo, context + fwd + 10)
    if len(ctx) < 20: return None
    base = statistics.median(v for _, v in ctx)
    win = [(t, v) for t, v in ctx if pos - back <= t <= pos + fwd]
    if not win: return None
    # smooth over `smooth` samples so a single click doesn't win
    best, bestv = None, None
    for i in range(len(win) - smooth + 1):
        seg = win[i:i+smooth]
        avg = sum(v for _, v in seg) / smooth
        if bestv is None or avg > bestv:
            bestv, best = avg, seg[smooth//2][0]
    return best, bestv - base, base

if __name__ == "__main__":
    import csv, json, os
    outdir = sys.argv[1]
    tl = json.load(open(os.path.join(outdir, "timeline.json"), encoding="utf-8"))
    paths = {v["file"]: v["path"] for v in tl["videos"]}
    only_goals = "--goals" in sys.argv
    print(f"{'type':>5}{'label':>14}{'mark':>9}{'audio pk':>10}{'shift':>8}{'lift dB':>9}")
    for r in csv.DictReader(open(os.path.join(outdir, "marks.csv"), encoding="utf-8-sig")):
        if only_goals and not r["kind"].startswith("goal"): continue
        pos = float(r["video_pos_s"])
        res = snap(paths[r["source"]], pos)
        if not res:
            print(f"{r['kind'][:5]:>5}{r['label'][:14]:>14}{pos:>9.0f}{'--':>10}"); continue
        b, lift, base = res
        print(f"{('goal' if r['kind'].startswith('goal') else 'mark'):>5}"
              f"{r['label'][:14]:>14}{pos:>9.0f}{b:>10.1f}{b-pos:>+8.1f}{lift:>9.1f}")
