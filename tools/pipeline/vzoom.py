#!/usr/bin/env python3
"""vzoom.py - post-production virtual zoom for XbotGo 4K footage, driven by the gimbal's own log.

The gimbal's tracking log (<date> <HH-MM-SS>time.txt) records, ~9x per second, the gimbal yaw,
how many tracked players are near the aim point (zoomSz), what it is following (ball / crowd /
nothing) and its in-frame target. With hindsight we can:
  * lead the play: frame where the camera WILL point ~1 s later (the gimbal is always late);
  * zoom when play is bunched (zoomSz high), widen on fast transitions / lost tracking;
  * beyond the pan limit, shift the crop toward the gimbal's in-frame target.
Crop is taken from the 4K source and scaled to 1920x1080, so zoom up to 2.0x never upscales.

  python3 vzoom.py --day 09-20-26 --out out/2026-09-20 --file <segment.mp4> --start S --dur D --name N [--compare]
Needs <out>/timeline.json from `xbotgo.py analyze`.
"""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils\ on PATH
import argparse, glob, json, os, subprocess, sys
from datetime import datetime
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import track_parse

W, H = 3840, 2160
OW, OH, OFPS = 1920, 1080, 30
PX_PER_DEG = 37.0        # measured 09-20: 35-38 px (4K) per degree of yaw, at camera zoom 1.0
LOG_LAG = 0.2            # log timestamps trail the video by ~0.2 s (pan/shift correlation)
LEAD = 1.0               # seconds of look-ahead
ZMIN, ZMAX = 1.0, 2.0
Z_BALL, Z_CROWD, Z_HOLD, Z_BUNCH, Z_FAST = 1.70, 1.50, 1.25, 0.30, 1.15
YAW_LIMIT = 52.0
CY = 0.36               # crop vertical centre (play sits in the upper-middle of the wide shot)
SB = (40, 300, 60, 1090) # burned-in scoreboard y0,y1,x0,x1 in the 4K source

def tod(ts):             # seconds of day
    return ts % 86400 if ts > 86400 else ts

def load_log(appdir, date):
    rows = []
    for f in sorted(glob.glob(os.path.join(appdir, f'{date} *time.txt'))):
        fr = track_parse.parse(f)
        for k in sorted(fr):
            d = fr[k]
            if 't' not in d or 'finx' not in d: continue
            rows.append((d['t'], d['yaw'], d.get('zoom', 0), d.get('mot', d.get('ffp', 0)) or 0,
                         d['finx'], d.get('mode', 'other'), d.get('crowdx', 1280)))
    rows.sort()
    a = np.array([r[:5] for r in rows], float)
    modes = [r[5] for r in rows]; crowd = np.array([r[6] for r in rows], float)
    return a, modes, crowd

def wall_of_pos(video, pos, tz_offset):
    """video position -> local wall seconds-of-day, using the pause-aware segments of timeline.json"""
    start = (video['start_epoch'] + tz_offset) % 86400
    segs = video['segments']; off0 = segs[0]['offset']
    for s in segs:
        if s['pos_start'] <= pos <= s['pos_end'] + 0.5:
            return start + pos + (s['offset'] - off0)
    return start + pos + (segs[-1]['offset'] - off0)

def gsmooth(v, sigma):
    k = np.arange(-int(3*sigma), int(3*sigma)+1); g = np.exp(-0.5*(k/max(sigma, 1e-3))**2); g /= g.sum()
    return np.convolve(np.pad(v, (len(k)//2,), mode='edge'), g, mode='valid')

def plan(log, modes, t_video, walls):
    """returns per-output-frame crop x,y,w,h"""
    t, yaw, zsz, mot, finx = log.T
    fps_an = 10.0
    tw = np.arange(walls[0] - 3, walls[-1] + 3 + LEAD, 1/fps_an)       # uniform analysis grid (wall)
    yaw_g = np.interp(tw, t, yaw)
    zsz_g = np.interp(tw, t, zsz)
    fin_g = np.interp(tw, t, finx)
    ball = np.array([m in ('staRB', 'PB', 'staPB') for m in modes], float)
    ball_g = np.interp(tw, t, ball)
    yaw_s = gsmooth(yaw_g, 0.4*fps_an)
    rate = np.gradient(yaw_s)*fps_an                                   # deg/s
    crowdm = np.array([m == 'other' for m in modes], float)            # crowd-driven frames
    crowd_g = np.interp(tw, t, crowdm) * (np.abs(fin_g - 1280) > 5)
    # 1) look-ahead: where will the camera point LEAD seconds from now
    fut = np.interp(tw + LEAD, tw, yaw_s)
    xoff = (fut - yaw_s)*PX_PER_DEG
    # 2) nudge toward the gimbal's in-frame target while it is locked on the ball; at the pan
    #    limit the gimbal cannot turn further, so the in-frame target is all we have
    bl = gsmooth(ball_g, 0.5*fps_an)
    atlim = (np.abs(yaw_s) >= YAW_LIMIT).astype(float)
    tgt = (fin_g - 1280)*1.5
    xoff = xoff + np.maximum(0.4*bl, 0.7*atlim)*tgt
    xoff = gsmooth(xoff, 0.6*fps_an)
    # 3) zoom by state (Z_BALL / Z_CROWD / Z_HOLD);
    #    +0.35 when play is bunched around the aim point; back off on fast pans
    st_z = Z_HOLD + (Z_BALL-Z_HOLD)*np.clip(bl, 0, 1) + (Z_CROWD-Z_HOLD)*np.clip(gsmooth(crowd_g, 0.5*fps_an), 0, 1)
    zs = gsmooth(zsz_g, 1.5*fps_an)
    st_z = st_z + Z_BUNCH*np.clip((zs - 3)/4, 0, 1)
    fast = np.clip((np.abs(gsmooth(rate, 0.8*fps_an)) - 10)/15, 0, 1)  # 10..25 deg/s
    z = st_z - (st_z - Z_FAST)*fast
    z = gsmooth(np.clip(z, ZMIN, ZMAX), 1.2*fps_an)
    lim = 0.35/fps_an                                                  # zoom rate limit 0.35x / s
    for i in range(1, len(z)): z[i] = np.clip(z[i], z[i-1]-lim, z[i-1]+lim)
    for i in range(len(z)-2, -1, -1): z[i] = np.clip(z[i], z[i+1]-lim, z[i+1]+lim)
    # sample at output frames
    zz = np.interp(walls, tw, z); xo = np.interp(walls, tw, xoff)
    cw = W/zz; ch = cw*9/16
    cx = W/2 + xo; cy = np.full_like(cx, CY*H)
    x0 = np.clip(cx - cw/2, 0, W - cw); y0 = np.clip(cy - ch/2, 0, H - ch)
    return x0, y0, cw, ch, zz

def read_frames(src, ss, dur):
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-ss', f'{ss:.3f}', '-t', f'{dur:.3f}', '-i', src,
                          '-vf', f'fps={OFPS}', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'],
                         stdout=subprocess.PIPE, bufsize=W*H*3*2)
    while True:
        b = p.stdout.read(W*H*3)
        if len(b) < W*H*3: break
        yield np.frombuffer(b, np.uint8).reshape(H, W, 3)
    p.wait()

def render(src, ss, dur, crop, base, compare):
    x0, y0, cw, ch, zz = crop
    enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{OW}x{OH}',
        '-r', str(OFPS), '-i', '-', '-ss', f'{ss:.3f}', '-t', f'{dur:.3f}', '-i', src, '-map', '0:v', '-map', '1:a?',
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k',
        '-shortest', '-movflags', '+faststart', base + '_vzoom.mp4'], stdin=subprocess.PIPE)
    cmp = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', '1920x540',
        '-r', str(OFPS), '-i', '-', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart', base + '_compare.mp4'], stdin=subprocess.PIPE) if compare else None
    n = 0
    for f in read_frames(src, ss, dur):
        i = min(n, len(x0)-1)
        xi, yi, wi, hi = int(x0[i]), int(y0[i]), int(cw[i]), int(ch[i])
        f = f.copy(); a, b, c, d = SB
        board = f[a:b, c:d].copy()
        # hide the board so no clipped fragment shows in the crop: low-res inpaint of the area
        reg = f[a:b+40, max(c-40, 0):d+40]
        sm = cv2.resize(reg, (reg.shape[1]//8, reg.shape[0]//8), interpolation=cv2.INTER_AREA)
        mk = np.zeros(sm.shape[:2], np.uint8); mk[:(b-a)//8+1, (c-max(c-40, 0))//8:(d-max(c-40, 0))//8+1] = 255
        fill = cv2.resize(cv2.inpaint(sm, mk, 5, cv2.INPAINT_TELEA), (reg.shape[1], reg.shape[0]), interpolation=cv2.INTER_CUBIC)
        f[a:b, c:d] = fill[:b-a, c-max(c-40, 0):d-max(c-40, 0)]
        zf = cv2.resize(f[yi:yi+hi, xi:xi+wi], (OW, OH), interpolation=cv2.INTER_AREA)
        bs = cv2.resize(board, ((d-c)//2, (b-a)//2), interpolation=cv2.INTER_AREA)
        zf[20:20+bs.shape[0], 20:20+bs.shape[1]] = bs   # re-apply full scoreboard, native 1080p size
        enc.stdin.write(zf.tobytes())
        if cmp:
            sm = cv2.resize(f, (960, 540), interpolation=cv2.INTER_AREA)
            cv2.rectangle(sm, (xi//4, yi//4), ((xi+wi)//4, (yi+hi)//4), (0, 255, 255), 2)
            cv2.putText(sm, f'x{zz[i]:.2f}', (14, 520), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
            cmp.stdin.write(np.hstack([sm, cv2.resize(zf, (960, 540), interpolation=cv2.INTER_AREA)]).tobytes())
        n += 1
    enc.stdin.close(); enc.wait()
    if cmp: cmp.stdin.close(); cmp.wait()
    return n

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--day', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--file', required=True); ap.add_argument('--start', type=float, required=True)
    ap.add_argument('--dur', type=float, required=True); ap.add_argument('--name', required=True)
    ap.add_argument('--compare', action='store_true'); ap.add_argument('--plan-only', action='store_true')
    a = ap.parse_args()
    tl = json.load(open(os.path.join(a.out, 'timeline.json'), encoding="utf-8"))
    video = next(v for v in tl['videos'] if v['file'] == os.path.basename(a.file))
    appdir = next(glob.iglob(os.path.join(a.day, '**', 'com.blink.blinkfocos', 'files'), recursive=True))
    cache = os.path.join(a.out, 'vzoom', f"tracklog_{tl['date']}.npz")
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    if os.path.exists(cache):
        z = np.load(cache, allow_pickle=True); log, modes = z['log'], list(z['modes'])
    else:
        log, modes, _ = load_log(appdir, tl['date']); np.savez(cache, log=log, modes=np.array(modes))
    tv = a.start + np.arange(int(a.dur*OFPS))/OFPS
    walls = np.array([wall_of_pos(video, p, tl['tz_offset']) for p in tv]) + LOG_LAG
    print(f'log {len(log)} frames {log[0,0]:.0f}-{log[-1,0]:.0f}; clip wall {walls[0]:.1f}-{walls[-1]:.1f}')
    crop = plan(log, modes, tv, walls)
    zz = crop[4]
    print(f'zoom min {zz.min():.2f} median {np.median(zz):.2f} max {zz.max():.2f}; zoomed>1.2 {100*np.mean(zz>1.2):.0f}%')
    base = os.path.join(a.out, 'vzoom', a.name)
    json.dump({'start': a.start, 'fps': OFPS, 'x': crop[0][::3].round(0).tolist(), 'z': zz[::3].round(2).tolist()},
              open(base + '_plan.json', 'w', encoding="utf-8"))
    if not a.plan_only:
        print('frames', render(a.file, a.start, a.dur, crop, base, a.compare))
