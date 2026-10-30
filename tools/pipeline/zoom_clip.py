#!/usr/bin/env python3
"""Slow-motion, stabilised zoom on a fixed area of the pitch (e.g. the goal mouth).

  pass 1  --step h      : homography of every frame to a reference frame (ORB+RANSAC
                          on a 960 px proxy), smoothed over time -> <work>/H.json
  pass 2  --step render --part k/N : render frames of part k (resumable, one part per call)
  pass 3  --step mux    : join parts (MPEG-TS), add half-speed audio -> --out

The crop rectangle is given in reference-frame pixels (4K) so it stays locked on
the grass while the camera pans; the clip eases in from the full frame to the
crop over --ease seconds of source time. --speed 0.5 = half speed.
"""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils\ on PATH
import argparse, json, os, subprocess, sys
import cv2, numpy as np

def sh(c):
    r = subprocess.run(c, capture_output=True, text=True)
    if r.returncode: sys.exit(" ".join(map(str, c[:8])) + "\n" + r.stderr[-1500:])
    return r

def frames(src, t0, dur, w, h):
    """Decoded frames as bgr24 arrays. ffmpeg's stderr is kept quiet when the caller stops reading early (a
    broken pipe then makes ffmpeg print scary 'muxer' errors although nothing is wrong); it is shown only when
    no frame at all could be read (missing input etc.)."""
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-i", src, "-t", f"{dur:.3f}",
                          "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    n = w * h * 3; got = 0
    try:
        while True:
            b = p.stdout.read(n)
            if len(b) < n: break
            got += 1
            yield np.frombuffer(b, np.uint8).reshape(h, w, 3)
    finally:
        try: p.stdout.close()
        except Exception: pass
        if p.poll() is None: p.kill()
        try: err = p.stderr.read()
        except Exception: err = b""
        p.wait()
        if got == 0 and err: sys.stderr.write(err.decode("utf-8", "replace"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True); ap.add_argument("--start", type=float, required=True)
    ap.add_argument("--dur", type=float, required=True)
    ap.add_argument("--ref", type=float, required=True, help="reference time (source s)")
    ap.add_argument("--crop", required=True, help="x,y,w in 4K reference pixels (16:9)")
    ap.add_argument("--ease", type=float, default=1.2)
    ap.add_argument("--start-crop", default="0,0,3840", help="x,y,w the ease begins from (default full frame; use a crop that excludes the burned-in scoreboard)")
    ap.add_argument("--pan", help="x,y,at: glide the crop origin to x,y (4K ref px) around master-replay second `at` (ramp --pan-ramp) and hold")
    ap.add_argument("--zoom-to", help="w,at: from master-replay second `at` to the end, ease the crop width to w (4K ref px; 768 = 5x), centre fixed")
    ap.add_argument("--pan-ramp", type=float, default=0.6, help="source seconds the glide takes")
    ap.add_argument("--speed", type=float, default=0.5)
    ap.add_argument("--volume", type=float, default=0.5)
    ap.add_argument("--work", required=True); ap.add_argument("--out")
    ap.add_argument("--height", type=int, default=2160)
    ap.add_argument("--preset", default="veryfast"); ap.add_argument("--crf", default="20")
    ap.add_argument("--step", choices=["h", "render", "mux"], required=True)
    ap.add_argument("--part", default="1/1")
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    W, H = 3840, 2160; pw, ph = 960, 540; s = W / pw
    hj = os.path.join(a.work, "H.json")

    if a.step == "h":
        orb = cv2.ORB_create(4000); bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        mask = np.zeros((ph, pw), np.uint8); mask[int(ph*.12):int(ph*.93), :] = 255   # no overlays
        ref = next(frames(a.src, a.ref, 0.05, pw, ph)); g0 = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
        k0, d0 = orb.detectAndCompute(g0, mask)
        out = []
        for f in frames(a.src, a.start, a.dur, pw, ph):
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY); k, d = orb.detectAndCompute(g, mask)
            m = sorted(bf.match(d, d0), key=lambda x: x.distance)[:800]
            Hm, _ = cv2.findHomography(np.float32([k[x.queryIdx].pt for x in m]),
                                       np.float32([k0[x.trainIdx].pt for x in m]), cv2.RANSAC, 2.0)
            S = np.diag([s, s, 1.]); out.append((S @ Hm @ np.linalg.inv(S)).tolist())
        A = np.array(out); A = A / A[:, 2:3, 2:3]
        km = 5; pm = np.concatenate([A[:1].repeat(km // 2, 0), A, A[-1:].repeat(km // 2, 0)])   # median kills single bad matches
        A = np.stack([np.median(pm[q:q + km], axis=0) for q in range(len(A))])
        k = int(os.environ.get("XB_HSMOOTH", "1")) | 1; pad = np.concatenate([A[:1].repeat(k//2, 0), A, A[-1:].repeat(k//2, 0)])
        sm = np.stack([pad[i:i+k].mean(0) for i in range(len(A))])          # temporal smoothing
        json.dump(sm.tolist(), open(hj, "w", encoding="utf-8")); print(len(sm), "homographies")
        return

    Hs = np.array(json.load(open(hj, encoding="utf-8"))); n = len(Hs)
    oh = a.height; ow = oh * 16 // 9
    cx, cy, cw = map(float, a.crop.split(",")); ch = cw * 9 / 16
    sx, sy, sw = map(float, a.start_crop.split(","))
    fps_src = n / a.dur
    def view(i):
        t = min(1.0, (i / fps_src) / a.ease) if a.ease > 0 else 1.0
        e = t * t * (3 - 2 * t)                                              # smoothstep
        x = sx + (cx - sx) * e; y = sy + (cy - sy) * e; w = sw + (cw - sw) * e
        if a.pan:
            ox, oy = cx, cy
            for kf in a.pan.split(";"):
                fs = list(map(float, kf.split(","))); px, py, at = fs[:3]
                rd = fs[3] * a.speed if len(fs) > 3 else a.pan_ramp           # optional 4th value: glide length in replay seconds
                T = at * a.speed
                u = min(1.0, max(0.0, ((i / fps_src) - (T - rd / 2)) / rd))
                m = u * u * (3 - 2 * u)
                x += (px - ox) * m; y += (py - oy) * m
                ox, oy = px, py
        if a.zoom_to:
            zw, zat = map(float, a.zoom_to.split(","))
            T = zat * a.speed
            u = min(1.0, max(0.0, ((i / fps_src) - T) / max(0.05, a.dur - T)))
            m = u * u * (3 - 2 * u)
            w2 = w + (zw - w) * m
            x += (w - w2) / 2; y += (w - w2) * 9 / 32; w = w2
        return x, y, w
    if a.step == "render":
        k, N = map(int, a.part.split("/"))
        i0, i1 = (k - 1) * n // N, k * n // N
        dst = os.path.join(a.work, f"part{k:02d}.mp4")
        want = (i1 - i0) / (fps_src * a.speed)
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", dst],
                           capture_output=True, text=True)
        try:
            if abs(float(r.stdout) - want) < 0.2: print("part", k, "ok"); return
        except ValueError: pass
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{ow}x{oh}",
                                "-r", f"{fps_src * a.speed:.4f}", "-i", "-", "-vf", "fps=30,format=yuv420p,setsar=1",
                                "-c:v", "libx264", "-preset", a.preset, "-crf", a.crf, "-y", dst], stdin=subprocess.PIPE)
        t0 = a.start + i0 / fps_src
        def clampv(i, x, y, w):
            q = cv2.perspectiveTransform(np.float32([[[0, 0], [W, 0], [W, H], [0, H]]]), Hs[i])[0]
            lx, rx = max(q[0][0], q[3][0]), min(q[1][0], q[2][0]); ty, by = max(q[0][1], q[1][1]), min(q[2][1], q[3][1])
            wm = min(rx - lx, (by - ty) * 16 / 9)
            if w > wm: x += (w - wm) / 2; y += (w - wm) * 9 / 32; w = wm
            return min(max(x, lx), rx - w), min(max(y, ty), by - w * 9 / 16), w
        D = np.array([view(i) for i in range(n)]); C = np.array([clampv(i, *D[i]) for i in range(n)])
        corr = C - D; kz = 15; pc = np.concatenate([corr[:1].repeat(kz // 2, 0), corr, corr[-1:].repeat(kz // 2, 0)])
        corr = np.stack([pc[j:j + kz].mean(0) for j in range(n)])               # smooth the clamp so it never snaps
        V = np.array([clampv(i, *(D[i] + corr[i])) for i in range(n)])
        json.dump(V.tolist(), open(os.path.join(a.work, "view.json"), "w", encoding="utf-8"))
        for i, f in enumerate(frames(a.src, a.start, i1 / fps_src + 0.05, W, H)):   # always decode from the clip start: exact frame alignment with H.json
            if i < i0: continue
            if i >= i1: break
            x, y, w = V[i]
            kk = ow / w
            M = np.array([[kk, 0, -x * kk], [0, kk, -y * kk], [0, 0, 1.]]) @ Hs[i]
            enc.stdin.write(cv2.warpPerspective(f, M, (ow, oh), flags=cv2.INTER_CUBIC,
                                                borderMode=cv2.BORDER_REPLICATE).tobytes())
        enc.stdin.close(); enc.wait(); print("part", k, "rendered", i1 - i0, "frames")
        return
    # mux
    parts = sorted(p for p in os.listdir(a.work) if p.startswith("part") and p.endswith(".mp4"))
    tss = []
    for p in parts:
        t = os.path.join(a.work, p[:-4] + ".ts")
        sh(["ffmpeg", "-v", "error", "-i", os.path.join(a.work, p), "-c", "copy", "-bsf:v", "h264_mp4toannexb",
            "-f", "mpegts", "-y", t]); tss.append(t)
    vid = os.path.join(a.work, "video.mp4")
    sh(["ffmpeg", "-v", "error", "-i", "concat:" + "|".join(tss), "-c", "copy", "-y", vid])
    vd = float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", vid]).stdout)
    sh(["ffmpeg", "-v", "error", "-i", vid, "-ss", f"{a.start:.3f}", "-t", f"{a.dur:.3f}", "-i", a.src,
        "-map", "0:v", "-map", "1:a", "-c:v", "copy",
        "-af", f"atempo={a.speed},volume={a.volume},aresample=48000", "-c:a", "aac", "-b:a", "128k",
        "-ar", "48000", "-ac", "2", "-t", f"{vd:.3f}", "-movflags", "+faststart", "-y", a.out])
    print("->", a.out, f"{vd:.2f}s")

if __name__ == "__main__":
    main()
