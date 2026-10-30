#!/usr/bin/env python3
"""Cut clips from the user's reviewed spreadsheet export.

Bounds rules (the user's, measured visually):
  lead  = event - action_start          verbatim, never altered
  tail  = max(action_end - event, 4)    at least 4 s after the event
  if the original window (action_end - action_start) < 5 s:
        widen 2 s on each side for breathing room
Rows flagged `skip` (legacy column) or with `skip` in `instructions` are not cut and appear in no reel.
"""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils\ on PATH
import argparse, csv, json, os, re, subprocess, sys, tempfile

def sh(c): return subprocess.run(c, capture_output=True, text=True)
def hhmmss(s):
    s=int(round(s)); return f"{s//3600:02d}:{s%3600//60:02d}:{s%60:02d}"
def row_skip(r):
    """skip = legacy `skip` column non-empty, or the word 'skip' in `instructions` (from 2026-03-14)."""
    return bool((r.get("skip") or "").strip()) or bool(re.search(r"\bskip\b", r.get("instructions") or "", re.I))
def secs(v):
    v=(v or "").strip()
    if not v: return None
    p=[int(x) for x in v.split(":")]
    if len(p)==1: return None
    if len(p)==2: return p[0]*60+p[1]
    return p[0]*3600+p[1]*60+p[2] if p[0]==0 else p[0]*60+p[1]
def slug(s):
    return re.sub(r"[^A-Za-z0-9]+","-",(s or "").strip()).strip("-")

def plan(rows, tl, roster, edge=0.5, bounds='rules'):
    files=[v["file"] for v in tl["videos"]]
    dur={v["file"]:v["duration"] for v in tl["videos"]}
    path={v["file"]:v["path"] for v in tl["videos"]}
    out=[]; n=0
    for r in rows:
        if row_skip(r): continue
        f = (r.get("file") or "").strip()
        if not f or f not in path: continue
        s,e,d = map(secs,(r.get("action_start") or r.get("action_start_video"),r.get("event") or r.get("event_video"),r.get("action_end") or r.get("action_end_video")))
        if None in (e,d): continue
        n+=1
        cross = "prior file" in r["notes"] and s is not None
        prev = files[files.index(r["file"])-1] if cross else None
        # lead measured across the file boundary when the action starts in the prior file
        lead = (dur[prev]-s)+e if cross else e-s
        win  = (dur[prev]-s)+d if cross else d-s
        tail = max(d-e, 4.0)
        pad  = 2.0 if win < 5 else 0.0
        # extra headroom at both ends so a transition can overlap padding
        # rather than eating into the measured action
        cin, cout = e-lead-pad-edge, e+tail+pad+edge
        if bounds=="startend" and not cross:
            # the user's action_start/action_end are authoritative, verbatim
            # (plus --edge headroom); event only places the cheer sting
            lead, pad, tail = e-s, 0.0, d-e
            cin, cout = s-edge, d+edge
        # player cell: "1" or "11,1" (assist, scorer). op = opposition, ? = unsure are ignored (user, 2026-03-23).
        # Every number listed belongs to that clip (per-player reels); the LAST one is the primary (2026-03-30: "11,1" = 1 scored, 11 assisted)
        import re as _re
        players = [t for t in [x.strip() for x in _re.split(r"[,;/&+]", r["player"])] if t and t.lower() not in ("op", "?")]
        player = players[-1] if players else ""
        name = roster.get(player, "")
        plabel = (name.strip().replace(" ","_")+"_"+player) if name else slug(player).replace("-","_")
        parts=[f"{n:03d}", r["type"], hhmmss(e).replace(":","")]
        if plabel: parts.append(plabel)
        out.append(dict(n=n, row=r, file=r["file"], path=path[r["file"]],
                        prev=prev, prev_path=path[prev] if prev else None,
                        prev_dur=dur[prev] if prev else None,
                        event=e, cin=max(0.0,cin), cout=min(dur[r["file"]],cout), ev_off=e-max(0.0,cin),
                        lead=lead, tail=tail, pad=pad, win=win,
                        player=player, players=players, name=name, plabel=plabel,
                        clip="_".join(parts)+".mp4"))
    return out

def vf_args(height):
    """height 0 = keep the recording's native resolution (no scaling)."""
    return ["-vf",f"scale=-2:{height}"] if height else []

def cut(job, dst, height, volume=0.5, ducks=(), preset='veryfast', crf='20'):
    if job["prev"]:   # action starts in the previous file - join tail + head
        with tempfile.TemporaryDirectory() as td:
            a=os.path.join(td,"a.mp4"); b=os.path.join(td,"b.mp4"); lst=os.path.join(td,"l.txt")
            astart = job["prev_dur"] - (job["lead"] + job["pad"] - job["event"])
            enc=[*vf_args(height),"-c:v","libx264","-preset","veryfast","-crf","20",
                 "-pix_fmt","yuv420p","-af",f"volume={volume}",
                 "-c:a","aac","-b:a","128k","-ar","48000"]
            sh(["ffmpeg","-v","error","-ss",f"{max(0,astart-5):.3f}","-i",job["prev_path"],
                "-ss",f"{min(5,astart):.3f}","-t",f"{job['prev_dur']-astart:.3f}",*enc,"-y",a])
            sh(["ffmpeg","-v","error","-i",job["path"],"-t",f"{job['cout']:.3f}",*enc,"-y",b])
            # The concat DEMUXER mis-times this join (a seeked part carries AAC
            # priming / edit-list offsets, and the second part lands late - a
            # 10.1 s clip came out 13.5 s). MPEG-TS intermediates re-time cleanly.
            ats=os.path.join(td,"a.ts"); bts=os.path.join(td,"b.ts")
            for src,tsf in ((a,ats),(b,bts)):
                sh(["ffmpeg","-v","error","-i",src,"-c","copy",
                    "-bsf:v","h264_mp4toannexb","-f","mpegts","-y",tsf])
            sh(["ffmpeg","-v","error","-i",f"concat:{ats}|{bts}","-c","copy",
                "-movflags","+faststart","-y",dst])
    else:
        dura=job["cout"]-job["cin"]
        af=f"volume={volume}"
        stem=os.path.splitext(job["file"])[0]
        for (f,a0,a1,g) in ducks:
            if f in stem and a1>job["cin"] and a0<job["cout"]:
                t0,t1=a0-job["cin"],a1-job["cin"]
                af+=f",volume='if(between(t,{t0:.3f},{t1:.3f}),{g/volume:.4f},1)':eval=frame"
        # single accurate input seek, so filter time t starts at 0 = clip start
        sh(["ffmpeg","-v","error","-ss",f"{job['cin']:.3f}","-i",job["path"],
            "-t",f"{dura:.3f}",
            *vf_args(height),"-c:v","libx264","-preset",preset,"-crf",crf,
            "-pix_fmt","yuv420p","-af",af,
            "-c:a","aac","-b:a","128k","-ar","48000",
            "-movflags","+faststart","-y",dst])
    return os.path.exists(dst) and os.path.getsize(dst)>0

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--csv",required=True); ap.add_argument("--out",required=True)
    ap.add_argument("--roster",default=None)
    ap.add_argument("--height",type=int,default=0,
                    help="0 (default) = native recording resolution; else scale to this height")
    ap.add_argument("--edge",type=float,default=0.5,
                    help="extra seconds at each end, room for transitions (default 0.5)")
    ap.add_argument("--volume",type=float,default=0.5,
                    help="audio gain on every clip (default 0.5 = -6 dB)")
    ap.add_argument("--bounds",choices=["rules","startend"],default="rules",
                    help="startend = cut action_start..action_end verbatim (+edge)")
    ap.add_argument("--duck",action="append",default=[],
                    help="FILEPART@H:MM:SS-H:MM:SS=GAIN  lower clip audio to GAIN in that source-time window")
    ap.add_argument("--clipdir",default="reviewed",help="clips/<clipdir>")
    ap.add_argument("--preset",default="veryfast"); ap.add_argument("--crf",default="20")
    ap.add_argument("--no-reels",action="store_true",help="cut clips only")
    ap.add_argument("--no-players",action="store_true",help="skip per-player reels")
    ap.add_argument("--dry-run",action="store_true"); ap.add_argument("--force",action="store_true")
    a=ap.parse_args()
    tl=json.load(open(os.path.join(a.out,"timeline.json"), encoding="utf-8"))
    roster={}
    if a.roster and os.path.exists(a.roster):
        with open(a.roster, encoding="utf-8-sig") as f:
            roster = {
                str(r.get("no") or r.get("No") or "").strip(): str(r.get("name") or r.get("Player") or "").strip()
                for r in csv.DictReader(f)
                if (r.get("no") or r.get("No"))
            }
    rows=list(csv.DictReader(open(a.csv, encoding="utf-8-sig")))
    def tsec(x):
        p=[float(v) for v in x.split(":")]; return p[0]*3600+p[1]*60+p[2] if len(p)==3 else p[0]*60+p[1]
    ducks=[]
    for dk in a.duck:
        f,rest=dk.split("@"); win,g=rest.split("="); w0,w1=win.split("-")
        ducks.append((f,tsec(w0),tsec(w1),float(g)))
    jobs=plan(rows,tl,roster,a.edge,a.bounds)
    skipped=[r for r in rows if row_skip(r)]
    print(f"{len(jobs)} clips, {len(skipped)} skipped")
    print(f"{'#':>3} {'in':>9}{'out':>9}{'len':>5}{'lead':>6}{'tail':>6}{'pad':>5}  clip")
    for j in jobs:
        print(f"{j['n']:>3} {hhmmss(j['cin']):>9}{hhmmss(j['cout']):>9}"
              f"{j['cout']-j['cin']:>5.0f}{j['lead']:>6.0f}{j['tail']:>6.0f}{j['pad']:>5.0f}  {j['clip']}")
    if a.dry_run: return
    cdir=os.path.join(a.out,"clips",a.clipdir); os.makedirs(cdir,exist_ok=True)
    made=[]
    for jn,j in enumerate(jobs,1):
        dst=os.path.join(cdir,j["clip"])
        want=j["cout"]-j["cin"] if not j["prev"] else j["lead"]+j["pad"]+j["tail"]
        if not a.force and os.path.exists(dst) and os.path.getsize(dst)>0:
            r=sh(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",dst])
            try: have=float(r.stdout.strip())
            except ValueError: have=-1          # unreadable/truncated -> re-cut
            if abs(have-want)<1.5:
                print("  skip",j["clip"]); made.append((j,dst)); continue
            print(f"  redo {j['clip']} (was {have:.1f}s, want {want:.1f}s)")
        ok=cut(j,dst,a.height,a.volume,ducks,a.preset,a.crf); print(f"  [{jn}/{len(jobs)}] "+("ok   " if ok else "FAIL ")+j["clip"])
        if ok: made.append((j,dst))
    json.dump([{k:v for k,v in j.items() if k!="row"} for j,_ in made],
              open(os.path.join(a.out,"cut_plan.json"),"w", encoding="utf-8"),indent=1,default=str)

    if a.no_reels:
        print(f"\nclips: {cdir}"); return
    rdir=os.path.join(a.out,"reels"); os.makedirs(rdir,exist_ok=True)
    PFX=tl["date"].replace("-","_")+"_"          # same prefix as the full game
    pdir=os.path.join(rdir,"players"); os.makedirs(pdir,exist_ok=True)
    def reel(sel,dst):
        parts=[d for j,d in made if sel(j)]
        if not parts: return
        if (not a.force and os.path.exists(dst) and os.path.getsize(dst)>0
                and os.path.getmtime(dst)>=max(os.path.getmtime(q) for q in parts)):
            probe=sh(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",dst])
            if probe.stdout.strip():
                print(f"  reel ok  {os.path.basename(dst)} ({len(parts)} clips, unchanged)"); return
            print(f"  reel rebuild {os.path.basename(dst)} (unreadable)")
        # The concat demuxer mis-times these joins (clips carry AAC priming and
        # edit-list offsets, so parts land late and the reel runs long - a 134 s
        # reel came out 786 s). MPEG-TS intermediates re-time exactly.
        with tempfile.TemporaryDirectory() as td:
            tss=[]
            for i,q in enumerate(parts):
                t=os.path.join(td,f"{i:04d}.ts")
                sh(["ffmpeg","-v","error","-i",q,"-c","copy",
                    "-bsf:v","h264_mp4toannexb","-f","mpegts","-y",t])
                if os.path.exists(t) and os.path.getsize(t)>0: tss.append(t)
            r=sh(["ffmpeg","-v","error","-i","concat:"+"|".join(tss),"-c","copy",
                  "-movflags","+faststart","-y",dst])
        ok=os.path.exists(dst) and os.path.getsize(dst)>0
        print(f"  reel {'->' if ok else 'FAILED'} {os.path.basename(dst)} ({len(parts)} clips)"
              + ("" if ok else "  "+(r.stderr or "")[:200]))
    reel(lambda j: True, os.path.join(rdir,PFX+"highlights_reviewed.mp4"))
    reel(lambda j: j["row"]["type"]=="goal", os.path.join(rdir,PFX+"goals_reviewed.mp4"))
    labels=[] if a.no_players else sorted({j["plabel"] for j,_ in made if j["name"]})
    for nm in labels:
        reel(lambda j,nm=nm: j["plabel"]==nm, os.path.join(pdir,PFX+nm+".mp4"))
    print(f"\nclips: {cdir}\nreels: {rdir}")

if __name__=="__main__": main()
