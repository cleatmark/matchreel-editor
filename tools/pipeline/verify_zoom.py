#!/usr/bin/env python3
"""Automatic checks on the 720p zoom replays: length vs expected, streaky / smeared / black edges.

  python3 tools/pipeline/verify_zoom.py --out out/2026-03-14-g1 [--only 3,5] [--files a.mp4 b.mp4] [--sheet]
Edge test: on sampled frames (4 per second) the outer 28 px of each side is compared with the interior.
BORDER_REPLICATE smear = almost no variation across the strip -> flagged.  Black strip = flagged.
--sheet writes out/<game>/zoom_verify/flagged.png (first flagged frame of each bad replay, offending edge marked).
Exit status 1 when anything is flagged.
"""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils\ on PATH
import argparse, os, sys
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xbotgo_core.xbl import Game, probe_dur

STRIP = 28


def edge_scores(gray):
    """Per side: (across, along) mean abs gradient inside the outer strip. Replicate smear = content varies ALONG the
    border but (almost) not ACROSS it. Flat sky/grass has both low and is not flagged."""
    g = gray.astype(np.float32)
    S = STRIP
    strips = {"left": g[:, :S], "right": g[:, -S:], "top": g[:S, :].T, "bottom": g[-S:, :].T}   # across = axis 1 for all
    sc = {}
    for k, m in strips.items():
        across = np.abs(np.diff(m, axis=1)).mean()
        along = np.abs(np.diff(m, axis=0)).mean()
        sc[k] = (across, along)
    black = {"left": g[:, :6].mean(), "right": g[:, -6:].mean(), "top": g[:6, :].mean(), "bottom": g[-6:, :].mean()}
    return sc, black


def is_bad(sc, bl, k):
    across, along = sc[k]
    return (along > 3.0 and across < 0.12 * along) or bl[k] < 6


def check_file(path, fps_sample=4):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30; n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, int(round(fps / fps_sample)))
    bad = {}; first = None; idx = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if idx % step == 0:
            ok, fr = cap.retrieve()
            if ok:
                sc, bl = edge_scores(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY))
                for k in sc:
                    if is_bad(sc, bl, k):
                        bad.setdefault(k, []).append(round(idx / fps, 2))
                        if first is None:
                            first = (idx / fps, k, fr.copy())
        idx += 1
    cap.release()
    return bad, first, n / fps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out"); ap.add_argument("--only"); ap.add_argument("--files", nargs="*")
    ap.add_argument("--sheet", action="store_true"); ap.add_argument("--height", type=int, default=720)
    a = ap.parse_args()
    items = []     # (label, path, expected_len or None)
    if a.files:
        items = [(os.path.basename(f), f, None) for f in a.files]
        g = Game(a.out) if a.out else None
    else:
        if not a.out:
            sys.exit("need --out or --files")
        g = Game(a.out); st = g.state()
        only = {int(x) for x in a.only.split(",")} if a.only else None
        missing = []
        for tok, r in sorted(st["replays"].items(), key=lambda kv: kv[1]["n"]):
            if only and r["n"] not in only:
                continue
            nm = f"{r['n']:03d}b_{tok}_zoom3x_{'720' if a.height == 720 else a.height}.mp4"
            p = os.path.join(g.extra, nm)
            if not os.path.exists(p):
                print(f"clip {r['n']:>2} {tok}: MISSING {nm}")
                missing.append(f"clip {r['n']} {tok}")
                continue
            exp = None if r.get("start") is None else 2 * r["dur"] - r["cut_start"] - r["cut_end"]
            items.append((f"clip {r['n']} {tok}", p, exp))
    flagged = []; shots = []
    for lab, p, exp in items:
        bad, first, L = check_file(p)
        msgs = []
        if exp is not None and abs(L - exp) > 0.35:
            msgs.append(f"length {L:.2f}s, expected {exp:.2f}s")
        if bad:
            msgs.append("edges: " + ", ".join(f"{k} @ {v[0]}s-{v[-1]}s ({len(v)} samples)" for k, v in bad.items()))
        print(f"{'FLAG' if msgs else 'ok  '} {lab:<26} {L:6.2f}s  " + "; ".join(msgs))
        if msgs:
            flagged.append(lab)
            if first:
                t, k, fr = first
                h, w = fr.shape[:2]
                cv2.rectangle(fr, (0, 0), (w - 1, h - 1), (0, 0, 255), 3)
                cv2.putText(fr, f"{lab} {k} @{t:.1f}s", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                shots.append(cv2.resize(fr, (640, 360)))
    if missing:
        print(f"{len(missing)} clip(s) MISSING")
        flagged.extend(missing)
    print(f"{len(items)} checked, {len(flagged)} flagged")
    if a.sheet and shots and g:
        d = os.path.join(xb_env.tmp_for(g.out), "zoom_verify"); os.makedirs(d, exist_ok=True)
        while len(shots) % 3:
            shots.append(np.zeros((360, 640, 3), np.uint8))
        im = cv2.vconcat([cv2.hconcat(shots[i:i + 3]) for i in range(0, len(shots), 3)])
        cv2.imwrite(os.path.join(d, "flagged.png"), im); print("wrote", os.path.join(d, "flagged.png"))
    sys.exit(1 if flagged else 0)


if __name__ == "__main__":
    main()
