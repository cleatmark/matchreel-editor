"""Emit Windows .bat + playlist so the heavy ffmpeg jobs run natively on the PC
(reading/writing 15 GB through the Claude folder bridge is far too slow)."""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils\ on PATH
import json, os, re

BS = chr(92)          # backslash, kept out of literals to avoid escaping traps

def winpath(linux_path, winroot):
    """/..../mnt/<folder>/sub/x  ->  <winroot>\\sub\\x"""
    ap = os.path.abspath(linux_path)
    m = re.search(r"/mnt/[^/]+/?(.*)$", ap)
    rel = m.group(1) if m else os.path.basename(ap)
    root = winroot.rstrip(BS)
    return (root + BS + rel.replace("/", BS)) if rel else root

def crlf(path):
    return open(path, "w", newline="\r\n")

def emit(outdir, timeline, rows, src_path, winroot, height):
    W  = lambda q: winpath(q, winroot)
    ff = winroot.rstrip(BS) + BS + "utils" + BS + "ffmpeg" + BS + "bin" + BS + "ffmpeg.exe"
    sdir = os.path.join(outdir, "scripts"); os.makedirs(sdir, exist_ok=True)
    reels = os.path.join(outdir, "reels");  os.makedirs(reels, exist_ok=True)
    made = []

    # 1 - playlist: plays all segments back to back, produces no file at all
    m3u = os.path.join(outdir, "full_game.m3u")
    with crlf(m3u) as fh:
        fh.write("#EXTM3U\n")
        for v in timeline["videos"]:
            fh.write(W(v["path"]) + "\n")
    made.append((m3u, "open in VLC / mpv - plays the whole game, instant, no re-encode"))

    # 2 - full-game concat
    lst = os.path.join(sdir, "full_concat.txt")
    with crlf(lst) as fh:
        for v in timeline["videos"]:
            fh.write("file '" + W(v["path"]).replace(BS, "/") + "'\n")
    bat1 = os.path.join(sdir, "run_full_concat.bat")
    with crlf(bat1) as fh:
        fh.write("@echo off\n")
        # video stream-copied (native res, lossless); audio at half volume to
        # keep sideline chatter down
        fh.write('"%s" -f concat -safe 0 -i "%s" -c:v copy -af volume=0.5 '
                 '-c:a aac -b:a 128k -movflags +faststart -y "%s"\n'
                 % (ff, W(lst), W(os.path.join(reels, "full_game.mp4"))))
        fh.write("echo done & pause\n")
    made.append((bat1, "double-click -> reels" + BS + "full_game.mp4 (lossless, ~15 GB)"))

    # 3 - final clips + reels at <height>p
    cdir = os.path.join(outdir, "clips", "final"); os.makedirs(cdir, exist_ok=True)
    hl, gl = [], []
    bat2 = os.path.join(sdir, "run_final_render.bat")
    with crlf(bat2) as fh:
        fh.write("@echo off\n")
        for r in rows:
            name = "%03d_%s_%s.mp4" % (int(r["id"]), r["kind"], r["video_pos"].replace(":", ""))
            dst  = os.path.join(cdir, name)
            tin  = r["clip_in_s"]; dur = r["clip_out_s"] - tin
            fh.write("echo   " + name + "\n")
            fh.write('"%s" -v error -ss %.3f -i "%s" -ss %.3f -t %.3f -vf scale=-2:%d '
                     '-c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p '
                     '-c:a aac -b:a 128k -movflags +faststart -y "%s"\n'
                     % (ff, max(0.0, tin - 5), W(src_path(timeline, r["source"])),
                        min(5.0, tin), dur, height, W(dst)))
            hl.append(W(dst))
            if r["kind"].startswith("goal"):
                gl.append(W(dst))
        for parts, fname, lname in ((hl, "highlights_final.mp4", "hl_list.txt"),
                                    (gl, "goals_final.mp4", "goal_list.txt")):
            if not parts:
                continue
            lp = os.path.join(sdir, lname)
            with crlf(lp) as lf:
                for q in parts:
                    lf.write("file '" + q.replace(BS, "/") + "'\n")
            fh.write('"%s" -v error -f concat -safe 0 -i "%s" -c copy -movflags +faststart -y "%s"\n'
                     % (ff, W(lp), W(os.path.join(reels, fname))))
        fh.write("echo ALL DONE & pause\n")
    made.append((bat2, "double-click -> %dp clips + highlights_final.mp4 + goals_final.mp4" % height))

    return [(W(q), why) for q, why in made]
