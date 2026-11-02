#!/usr/bin/env python3
"""Intro / outro title cards for highlight reels.

Intro : league logo at the top, team logos + names in the middle
        ("Home FC  vs  Guest FC").
Outro : same layout with the final score on a line below the names.
Half  : (--halftime-score) league logo, a big gold HALFTIME banner, then the
        same tiles/names with the score at the half-time whistle. Reel version
        500_halftime.mp4 is 1.3 s = 0.5 s fully on screen + a 0.4 s xfade each
        side; insert it between the last 1st-half clip and the first 2nd-half
        clip.
--fullgame also writes source-matched 000_intro_fullgame.mp4 and
        500_halftime_fullgame.mp4 (H.264 High@5.1, 44.1 kHz) for the
        stream-copied full-game join (tools/pipeline/fullgame_bat.py).

Cards are rendered at the reel's native size (default 3840x2160, 30 fps) with a
silent stereo AAC track so reel_build.py can xfade them like any other clip.
Put them in out/<date>/clips/cards/ - same depth as the clip folder, so
reel_build still finds cut_plan.json from the first clip's path.

  python3 tools/pipeline/title_cards.py --out out/2026-03-07/clips/cards \
      --league "shared/team_logos/league_a.png" \
      --home "Home FC" --home-logo shared/team_logos/home_fc.png \
      --away "Guest FC" --away-logo "shared/team_logos/guest_fc.png" \
      --score 5-1 --halftime-score 3-1 --date "March 7, 2026" --fullgame
"""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils\ on PATH
import argparse, os, subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter

_BOLD = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", r"C:\\Windows\\Fonts\\segoeuib.ttf",
         r"C:\\Windows\\Fonts\\arialbd.ttf", "DejaVuSans-Bold.ttf", "arialbd.ttf"]
_REG = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", r"C:\\Windows\\Fonts\\segoeui.ttf",
        r"C:\\Windows\\Fonts\\arial.ttf", "DejaVuSans.ttf", "arial.ttf"]
BOLD, REG = "bold", "reg"      # symbolic names; font() resolves them per machine (Linux VM or Windows PC)

def font(p, s):
    """TrueType only. The old fallback (ImageFont.load_default) drew tiny bitmap text on the PC - never fall back to it."""
    for cand in (_BOLD if p == BOLD else _REG if p == REG else [p]):
        try: return ImageFont.truetype(cand, s)
        except OSError: pass
    raise SystemExit("no TrueType font found for title cards (tried: %s)" % ", ".join(_BOLD if p == BOLD else _REG))

def background(W, H):
    # deep navy vertical gradient with a soft centre glow
    top, bot = (10, 22, 48), (3, 8, 20)
    bg = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(bg)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse([W*0.15, H*0.25, W*0.85, H*1.05], fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(W // 12))
    bg.paste(Image.new("RGB", (W, H), (40, 80, 150)), (0, 0), glow)
    return bg

def fit_up(im, w, h):
    """Scale to fit w x h, upscaling small logos too (thumbnail() never enlarges)."""
    k = min(w / im.width, h / im.height)
    return im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)


def tile(path, size, radius):
    """Logo on a rounded tile. Transparent logos get a white plate (dark-blue
    crests vanish on navy); opaque logos keep their own background."""
    im = Image.open(path).convert("RGBA")
    opaque = im.getchannel("A").getextrema()[0] == 255
    t = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius, fill=255)
    if opaque:
        fit = fit_up(im, size, size)
        plate = Image.new("RGBA", (size, size), fit.getpixel((2, 2)))
        plate.paste(fit, ((size - fit.width) // 2, (size - fit.height) // 2), fit)
    else:
        plate = Image.new("RGBA", (size, size), (255, 255, 255, 255))
        pad = int(size * 0.08)
        fit = fit_up(im, size - 2 * pad, size - 2 * pad)
        plate.paste(fit, ((size - fit.width) // 2, (size - fit.height) // 2), fit)
    t.paste(plate, (0, 0), mask)
    return t

def shadow(canvas, box, radius, blur):
    sh = Image.new("L", canvas.size, 0)
    x0, y0, x1, y1 = box
    ImageDraw.Draw(sh).rounded_rectangle([x0 + blur // 3, y0 + blur // 2, x1 + blur // 3, y1 + blur // 2], radius, fill=160)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    canvas.paste(Image.new("RGB", canvas.size, (0, 0, 0)), (0, 0), sh)

def ctext(d, cx, y, s, f, fill):
    w = d.textlength(s, font=f)
    d.text((cx - w / 2, y), s, font=f, fill=fill)

def render(a, score, W, H, halftime=False, player_line=""):
    """score=None -> intro; score + halftime=False -> final; halftime=True ->
    half-time card (big HALFTIME banner, current score)."""
    k = W / 3840
    img = background(W, H)
    d = ImageDraw.Draw(img)
    if halftime:
        lh, ts, ty = int(300 * k), int(500 * k), int(720 * k)
    else:
        lh = int((520 if not score else 440) * k)
        ts = int((680 if not score else 600) * k)
        ty = int((780 if not score else 660) * k)
    # league logo, top centre
    lg = Image.open(a.league).convert("RGBA")
    lg.thumbnail((int(lh * 1.4), lh), Image.LANCZOS)
    img.paste(lg, ((W - lg.width) // 2, int((70 if halftime else 90) * k)), lg)
    if halftime:
        hf = font(BOLD, int(250 * k)); gold = (236, 196, 92)
        ctext(d, W // 2, int(395 * k), "HALFTIME", hf, gold)
    r = int(60 * k)
    cxL, cxR = int(W * 0.29), int(W * 0.71)
    for cx, p in ((cxL, a.home_logo), (cxR, a.away_logo)):
        box = (cx - ts // 2, ty, cx + ts // 2, ty + ts)
        shadow(img, box, r, int(40 * k))
        t = tile(p, ts, r)
        img.paste(t, box[:2], t)
    d = ImageDraw.Draw(img)
    ctext(d, W // 2, ty + ts // 2 - int(110 * k), "vs", font(BOLD, int(200 * k)), (230, 236, 245))
    fn = font(BOLD, int((120 if halftime else 130) * k))
    ny = ty + ts + int(50 * k)
    for cx, n in ((cxL, a.home), (cxR, a.away)):
        f = fn
        while d.textlength(n, font=f) > W * 0.40: f = font(BOLD, int(f.size * 0.92))
        ctext(d, cx, ny, n, f, (255, 255, 255))
    if score:
        hs, as_ = score.split("-")
        fs = font(BOLD, int((300 if halftime else 330) * k)); sy = ny + int((160 if halftime else 190) * k)
        col = (255, 255, 255) if halftime else (236, 196, 92)
        ctext(d, cxL, sy, hs.strip(), fs, col)
        ctext(d, cxR, sy, as_.strip(), fs, col)
        if not halftime:
            ctext(d, W // 2, sy + int(40 * k), "FINAL", font(BOLD, int(110 * k)), (200, 210, 225))
    if player_line and not score and not halftime:
        # player reel intro: "Full Name - 7" in gold under the team names
        pf = font(BOLD, int(170 * k))
        while d.textlength(player_line, font=pf) > W * 0.80: pf = font(BOLD, int(pf.size * 0.92))
        ctext(d, W // 2, ny + int(230 * k), player_line, pf, (236, 196, 92))
    if a.date:
        ctext(d, W // 2, H - int(150 * k), a.date, font(REG, int(70 * k)), (170, 182, 200))
    return img

def to_video(png, dst, secs, W, H, fps, ar=48000, fullgame=False):
    """fullgame=True: match the phone recording (H.264 High@5.1, 44.1 kHz AAC)
    so the card can be stream-copy joined with the source files."""
    prof = ["-profile:v", "high", "-level", "5.1"] if fullgame else []
    subprocess.run(["ffmpeg", "-v", "error", "-loop", "1", "-framerate", str(fps), "-i", png,
                    "-f", "lavfi", "-i", f"anullsrc=r={ar}:cl=stereo",
                    "-t", f"{secs}", "-vf", f"scale={W}:{H},format=yuv420p,setsar=1",
                    "-c:v", "libx264", *prof, "-preset", "veryfast", "-crf", "18", "-tune", "stillimage",
                    "-r", str(fps), "-c:a", "aac", "-b:a", "128k", "-ar", str(ar),
                    "-shortest", "-movflags", "+faststart", "-y", dst], check=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--league", required=True)
    ap.add_argument("--home", required=True); ap.add_argument("--home-logo", required=True)
    ap.add_argument("--away", required=True); ap.add_argument("--away-logo", required=True)
    ap.add_argument("--score", required=True, help="final score, home-away, e.g. 5-1")
    ap.add_argument("--halftime-score", default=None,
                    help="score at the half-time whistle, home-away; renders 500_halftime.mp4")
    ap.add_argument("--date", default="", help="optional footer line")
    ap.add_argument("--secs", type=float, default=4.0, help="intro/outro length")
    ap.add_argument("--halftime-secs", type=float, default=1.3,
                    help="reel half-time card length: 0.5 s fully visible + 2 x 0.4 s xfade")
    ap.add_argument("--fullgame", action="store_true",
                    help="also render source-matched 000_intro_fullgame.mp4 (+ 500_halftime_fullgame.mp4)")
    ap.add_argument("--fullgame-halftime-secs", type=float, default=4.0)
    ap.add_argument("--player-line", default="", help='extra player-reel intro 000_intro_player.mp4 with this line, e.g. "Full Name - 7"')
    ap.add_argument("--player-tag", default="player", help="file tag: 000_intro_<tag>.mp4 (e.g. p11)")
    ap.add_argument("--only-player-intro", action="store_true", help="render only 000_intro_player.mp4")
    ap.add_argument("--size", default="3840x2160"); ap.add_argument("--fps", type=int, default=30)
    a = ap.parse_args()
    W, H = map(int, a.size.split("x"))
    os.makedirs(a.out, exist_ok=True)
    jobs = [("000_intro", None, False, a.secs), ("999_outro", a.score, False, a.secs)]
    if a.halftime_score:
        jobs.append(("500_halftime", a.halftime_score, True, a.halftime_secs))
    if a.player_line:
        jobs.append(("000_intro_" + a.player_tag, None, False, a.secs))
    if a.only_player_intro:
        jobs = [j for j in jobs if j[0] == "000_intro_" + a.player_tag]
    for name, sc, ht, secs in jobs:
        png = os.path.join(a.out, name + ".png")
        render(a, sc, W, H, halftime=ht, player_line=a.player_line if name == "000_intro_" + a.player_tag else "").save(png)
        to_video(png, os.path.join(a.out, name + ".mp4"), secs, W, H, a.fps)
        print("  ", os.path.join(a.out, name + ".mp4"))
    if a.fullgame and not a.only_player_intro:
        fg = [("000_intro", a.secs)]
        if a.halftime_score: fg.append(("500_halftime", a.fullgame_halftime_secs))
        for name, secs in fg:
            dst = os.path.join(a.out, name + "_fullgame.mp4")
            to_video(os.path.join(a.out, name + ".png"), dst, secs, W, H, a.fps,
                     ar=44100, fullgame=True)
            print("  ", dst)

if __name__ == "__main__": main()
