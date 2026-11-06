#!/usr/bin/env python3
"""Build the VAR offside-review insert for one match (1-1, free kick at 13:40.7).

Uses the 4K source frames 819.0-821.2 s (fr/001..066.jpg, ~30 fps) and the
per-frame homographies to the kick frame (H.json, frame index 50 = file 051.jpg),
so lines drawn in kick-frame coordinates stay fixed on the grass while the
camera pans.

Offside geometry (measured in the kick frame, 4K px):
  vanishing point of goal-line-parallel lines  VP = (3029.2, 422.2)
    (penalty-box front line and a blue field line agree to 2 px)
  2nd-last defender's foot                       D6 = (172, 1077)
  receiver (HOME #10) lead foot                   RC = (1468, 778)
"""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils\ on PATH
import argparse, json, os, subprocess
import cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont

VP = np.array([3029.2, 422.2]); D6 = np.array([172., 1077.]); RC = np.array([1468., 778.])
KICK = 50                                   # index into sorted frames
MAIN = (0, 340, 2000, 1125)                 # x0, y0, w, h in kick-frame coords (16:9)
ZOOM = (1100, 462, 1200, 675)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FPS = 30

def sh(c):
    r = subprocess.run(c, capture_output=True, text=True)
    if r.returncode: raise SystemExit(" ".join(c[:6]) + "\n" + r.stderr[-1500:])

def line_y(p, x):  # offside line through p, toward VP
    return p[1] + (x - p[0]) * (VP[1] - p[1]) / (VP[0] - p[0])

class View:
    def __init__(s, crop, W, Hh):
        s.x0, s.y0, s.cw, s.ch = crop; s.W, s.H = W, Hh; s.k = W / s.cw
    def M(s, H):
        T = np.array([[1, 0, -s.x0], [0, 1, -s.y0], [0, 0, 1.]])
        return np.diag([s.k, s.k, 1]) @ T @ H
    def P(s, x, y): return (int(round((x - s.x0) * s.k)), int(round((y - s.y0) * s.k)))
    def render(s, img, H):
        return cv2.warpPerspective(img, s.M(H), (s.W, s.H), flags=cv2.INTER_LANCZOS4,
                                   borderMode=cv2.BORDER_REPLICATE)

def offside_line(img, v, p, col, th, dashed=False):
    xa, xb = v.x0 - 50, v.x0 + v.cw + 50
    if not dashed:
        cv2.line(img, v.P(xa, line_y(p, xa)), v.P(xb, line_y(p, xb)), col, th, cv2.LINE_AA); return
    step = v.cw / 50
    for a in np.arange(xa, xb, step):
        b = a + step * 0.6
        cv2.line(img, v.P(a, line_y(p, a)), v.P(b, line_y(p, b)), col, th, cv2.LINE_AA)

def ring(img, v, p, col, th):
    cv2.ellipse(img, v.P(*p), (int(26 * v.k), int(11 * v.k)), 0, 0, 360, col, th, cv2.LINE_AA)

def text_boxes(img, items):
    """items: (text, (x,y) top-left, size_px, fg rgb, bg rgba)"""
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).convert("RGBA")
    ov = Image.new("RGBA", pil.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    for t, (x, y), sz, fg, bg in items:
        f = ImageFont.truetype(FONT, sz); l, tp, r, b = d.textbbox((x, y), t, font=f)
        pad = int(sz * 0.35)
        if bg: d.rounded_rectangle((l - pad, tp - pad, r + pad, b + pad), int(sz * 0.25), fill=bg)
        d.text((x, y), t, font=f, fill=fg)
    pil.alpha_composite(ov)
    return cv2.cvtColor(np.array(pil.convert("RGB")), cv2.COLOR_RGB2BGR)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", default=os.path.expanduser("~/w/fr"))
    ap.add_argument("--hjson", default=os.path.expanduser("~/w/H.json"))
    ap.add_argument("--assets", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--height", type=int, default=2160)
    ap.add_argument("--preset", default="medium"); ap.add_argument("--crf", default="20")
    ap.add_argument("--first", type=int, default=25, help="first slow-motion frame index")
    a = ap.parse_args()
    Hh = a.height; W = Hh * 16 // 9
    os.makedirs(a.work, exist_ok=True)
    fr = sorted(os.path.join(a.frames, f) for f in os.listdir(a.frames) if f.endswith(".jpg"))
    Hs = {int(k): np.array(v) for k, v in json.load(open(a.hjson, encoding="utf-8")).items()}
    Hs[KICK] = np.eye(3)
    vm, vz = View(MAIN, W, Hh), View(ZOOM, W, Hh)
    th = max(2, round(W / 640)); fs = lambda r: max(12, int(Hh * r))
    YEL, RED, CYN = (0, 215, 255), (40, 40, 255), (255, 230, 0)
    BOX = (0, 0, 0, 170)
    seq = []                                 # (jpg, seconds)
    def put(img, name, secs):
        p = os.path.join(a.work, name)
        if not os.path.exists(p): cv2.imwrite(p, img, [cv2.IMWRITE_JPEG_QUALITY, 94])
        seq.append((p, secs))

    # S1 - VAR CHECK title over the first slow-mo frame (1.2 s)
    im = vm.render(cv2.imread(fr[a.first]), Hs[a.first])
    im = text_boxes(im, [("VAR CHECK", (int(W*.04), int(Hh*.05)), fs(.075), (255, 255, 255), (20, 60, 160, 230)),
                         ("Possible offside  -  HOME 1-1, free kick 13:40", (int(W*.04), int(Hh*.17)), fs(.035), (255, 255, 255), BOX)])
    put(im, "s1.jpg", 1.2)
    # S2 - quarter-speed run-up to the kick, defender line dashed
    for i in range(a.first, KICK):
        im = vm.render(cv2.imread(fr[i]), Hs[i])
        offside_line(im, vm, D6, YEL, th, dashed=True)
        im = text_boxes(im, [("VAR", (int(W*.03), int(Hh*.04)), fs(.04), (255, 255, 255), (20, 60, 160, 230)),
                             ("1/4 speed", (int(W*.86), int(Hh*.92)), fs(.028), (255, 255, 255), BOX)])
        put(im, f"s2_{i:03d}.jpg", 4 / FPS)
    # S3 - freeze at the moment the ball is played
    base = vm.render(cv2.imread(fr[KICK]), Hs[KICK]); kick_clean = base.copy()
    im = base.copy()
    offside_line(im, vm, D6, RED, th + 1)
    offside_line(im, vm, RC, CYN, th, dashed=True)
    ring(im, vm, D6, RED, th); ring(im, vm, RC, CYN, th)
    lines_only = im.copy()
    dx, dy = vm.P(*D6); rx, ry = vm.P(*RC)
    im = text_boxes(im, [
        ("BALL PLAYED  13:40.7", (int(W*.03), int(Hh*.04)), fs(.05), (255, 255, 255), (20, 60, 160, 230)),
        ("red = offside line (2nd-last defender)", (int(W*.03), int(Hh*.14)), fs(.03), (255, 120, 120), BOX),
        ("cyan = HOME #10, lead foot", (int(W*.03), int(Hh*.20)), fs(.03), (0, 230, 255), BOX),
        ("2nd-last defender", (dx - int(W*.02), dy + int(Hh*.04)), fs(.028), (255, 120, 120), BOX),
        ("#10", (rx - int(W*.015), ry - int(Hh*.22)), fs(.04), (0, 230, 255), BOX)])
    put(im, "s3.jpg", 3.5); kick_lines = im
    # S4 - zoom on the receiver at the same instant
    im = vz.render(cv2.imread(fr[KICK]), Hs[KICK])
    offside_line(im, vz, D6, RED, th + 2)
    offside_line(im, vz, RC, CYN, th, dashed=True)
    ring(im, vz, RC, CYN, th + 1)
    im = text_boxes(im, [("ZOOM  -  ball played", (int(W*.03), int(Hh*.04)), fs(.045), (255, 255, 255), (20, 60, 160, 230)),
                         ("#10 level with the line  =  ONSIDE", (int(W*.03), int(Hh*.86)), fs(.045), (255, 255, 255), (0, 120, 40, 220))])
    put(im, "s4.jpg", 3.0)
    # S5 - cartoon referee announces the decision, mouth synced to the voice
    m = json.load(open(os.path.join(a.assets, "mouth.json"), encoding="utf-8"))
    lead, tailpad = 0.3, 0.9
    bg = (lines_only * 0.45).astype(np.uint8)
    bg = text_boxes(bg, [("VAR DECISION", (int(W*.04), int(Hh*.05)), fs(.06), (255, 255, 255), (20, 60, 160, 230)),
                         ("NOT OFFSIDE", (int(W*.06), int(Hh*.40)), fs(.11), (255, 255, 255), (0, 130, 45, 235)),
                         ("GOAL STANDS!", (int(W*.06), int(Hh*.60)), fs(.09), (255, 230, 60), (0, 0, 0, 200))])
    pil_bg = Image.fromarray(cv2.cvtColor(bg, cv2.COLOR_BGR2RGB)).convert("RGBA")
    rh = int(Hh * .9)
    states = []
    for s in (0, 1):
        r = Image.open(os.path.join(a.assets, f"ref_{s}.png")).convert("RGBA")
        r = r.resize((int(r.width * rh / r.height), rh), Image.LANCZOS)
        c = pil_bg.copy(); c.alpha_composite(r, (W - r.width - int(W * .03), Hh - rh))
        states.append(cv2.cvtColor(np.array(c.convert("RGB")), cv2.COLOR_RGB2BGR))
    cv2.imwrite(os.path.join(a.work, "s5_1.jpg"), states[1], [cv2.IMWRITE_JPEG_QUALITY, 94])
    s5_start = sum(d for _, d in seq)
    cv2.imwrite(os.path.join(a.work, "s5_0.jpg"), states[0], [cv2.IMWRITE_JPEG_QUALITY, 94]); seq.append((os.path.join(a.work, "s5_0.jpg"), lead))
    runs = []
    for v in m["mouth"]:
        if runs and runs[-1][0] == v: runs[-1][1] += 1
        else: runs.append([v, 1])
    for k, (v, n) in enumerate(runs):
        p = os.path.join(a.work, f"s5_{v}.jpg"); seq.append((p, n / m["fps"]))
    seq.append((os.path.join(a.work, "s5_0.jpg"), tailpad))
    total = sum(d for _, d in seq)
    voice_at = s5_start
    # ---- encode ----
    lst = os.path.join(a.work, "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p, d in seq: f.write(f"file '{p}'\nduration {d:.4f}\n")
        f.write(f"file '{seq[-1][0]}'\n")
    vid = os.path.join(a.work, "video.mp4")
    sh(["ffmpeg", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
        "-vf", f"fps={FPS},format=yuv420p,setsar=1", "-c:v", "libx264", "-preset", a.preset,
        "-crf", a.crf, "-t", f"{total:.3f}", "-y", vid])
    voice = os.path.join(a.assets, "ref_voice.wav")
    beeps = ("sine=f=1320:d=0.12,volume=0.25,apad=pad_dur=0.10[b1];"
             "sine=f=1760:d=0.18,volume=0.25[b2];[b1][b2]concat=n=2:v=0:a=1[bp]")
    fc = (f"anullsrc=r=48000:cl=stereo,atrim=0:{total:.3f}[sil];{beeps};"
          f"[bp]aresample=48000,pan=stereo|c0=c0|c1=c0,adelay=150|150[beep];"
          f"[1:a]aresample=48000,pan=stereo|c0=c0|c1=c0,adelay={int((voice_at+lead)*1000)}|{int((voice_at+lead)*1000)}[vo];"
          f"[sil][beep][vo]amix=inputs=3:duration=first:normalize=0[a]")
    sh(["ffmpeg", "-v", "error", "-i", vid, "-i", voice, "-filter_complex", fc,
        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
        "-movflags", "+faststart", "-t", f"{total:.3f}", "-y", a.out])
    print(f"VAR insert -> {a.out}  {total:.2f}s  ({W}x{Hh})")

if __name__ == "__main__":
    main()
