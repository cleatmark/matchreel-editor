#!/usr/bin/env python3
"""Join the 720p preview clips of one game into a no-music review reel (MPEG-TS join, never the concat demuxer).

  python3 tools/pipeline/preview_reel.py --out out/2026-03-14-g1 [--with-replays]

--with-replays puts each approved 720p zoom replay right after its clip (as the final reel will).
Prints every piece, the expected length (sum of the pieces) and the probed length.
"""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils\ on PATH
import argparse, os, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xbotgo_core.xbl import Game, sh, probe_dur, is_zoom


# A concat of many re-encoded pieces drifts by a few frames; both build() and Re-cut use the same tolerance.
LENGTH_TOLERANCE_S = 1.5


def build(g, with_replays=False, quiet=False):
    jobs = g.jobs()
    pieces = []
    for j in jobs:
        c = os.path.join(g.clipdir, j["clip"])
        if os.path.exists(c):
            pieces.append((f"{j['n']:03d}", c))
        else:
            print(f"  MISSING clip {j['clip']}")
        if with_replays and is_zoom(j["row"]):
            r = os.path.join(g.extra, g.replay_name(j))
            if os.path.exists(r):
                pieces.append((f"{j['n']:03d}b", r))
    tmp = os.path.join(tempfile.gettempdir(), "xb_" + g.base + ("_r" if with_replays else ""))
    os.makedirs(tmp, exist_ok=True)
    try:
        ts, total = [], 0.0
        for lab, p in pieces:
            d = probe_dur(p)
            if d is None:
                print("  UNREADABLE", p); continue
            total += d
            t = os.path.join(tmp, lab + ".ts")
            sh(["ffmpeg", "-v", "error", "-y", "-i", p, "-c", "copy", "-bsf:v", "h264_mp4toannexb", "-f", "mpegts", t])
            ts.append(t)
            if not quiet:
                print(f"  {lab:>5} {d:6.2f}s  {os.path.basename(p)}")
        os.makedirs(os.path.join(g.out, "reels"), exist_ok=True)
        dst = os.path.join(g.out, "reels", f"{g.prefix}_preview720_nomusic{'_with_replays' if with_replays else ''}.mp4")
        sh(["ffmpeg", "-v", "error", "-y", "-i", "concat:" + "|".join(ts), "-c", "copy",
            "-bsf:a", "aac_adtstoasc", "-movflags", "+faststart", dst])
        got = probe_dur(dst)
        ok = got is not None and abs(got - total) < LENGTH_TOLERANCE_S
        print(f"{'OK ' if ok else 'BAD'} {os.path.basename(dst)}: {len(ts)} pieces, expected {total:.1f}s, probed {got and round(got, 1)}s")
        return dst, total, got
    finally:
        shutil.rmtree(tmp, ignore_errors=True)  # the .ts pieces are scratch (rebuilt on every run); never leave ~0.5 GB per game behind


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--with-replays", action="store_true")
    a = ap.parse_args()
    build(Game(a.out), a.with_replays)
