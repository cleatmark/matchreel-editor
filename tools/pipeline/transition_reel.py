#!/usr/bin/env python3
"""Assemble clips into a reel with a random xfade transition at each junction.

xfade OVERLAPS the two clips by `duration`, so the transition eats into the
tail of one clip and the head of the next. Clips cut with --edge 0.5 have
padding for exactly this; older clips do not, so keep the duration short.
"""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils\ on PATH
import argparse, os, random, subprocess, sys, tempfile

# curated: readable at a glance, no gimmicks that look broken on wide sports footage
STYLES = ["slideleft","slideright","slideup","slidedown",
          "wipeleft","wiperight","wipeup","wipedown",
          "smoothleft","smoothright","smoothup","smoothdown",
          "circlecrop","rectcrop","circleopen","circleclose",
          "dissolve","pixelize","radial","fadeblack","diagtl","diagbr"]

def dur(f):
    r=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                      "-of","csv=p=0",f],capture_output=True,text=True)
    return float(r.stdout.strip())

FPS=30

def reel_starts(ds, T):
    """Where each clip begins on the reel timeline, given xfade overlaps."""
    st=[0.0]
    for d in ds[:-1]: st.append(st[-1]+d-T)
    return st

def build(clips, out, T=0.4, seed=None, styles=None,
          music=None, music_vol=0.18, cheers=None, cheer_at=None, cheer_vol=0.9,
          preset="veryfast", crf="20"):
    rnd=random.Random(seed)
    pool=styles or STYLES
    ds=[dur(c) for c in clips]
    n=len(clips)
    if n<2:
        subprocess.run(["ffmpeg","-v","error","-i",clips[0],"-c","copy","-y",out]); return []
    ins=[]
    for c in clips: ins += ["-i",c]
    # xfade refuses mismatched timebases/frame rates, and clips cut at different
    # times can differ - normalise every input first.
    vf=[]; af=[]; picked=[]
    for i in range(n):
        vf.append(f"[{i}:v]fps={FPS},settb=AVTB,format=yuv420p,setsar=1[nv{i}]")
        af.append(f"[{i}:a]aresample=48000,asettb=AVTB[na{i}]")
    off=ds[0]-T
    vprev,aprev="nv0","na0"
    for i in range(1,n):
        st=rnd.choice(pool); picked.append(st)
        vout=f"v{i}"; aout=f"a{i}"
        vf.append(f"[{vprev}][nv{i}]xfade=transition={st}:duration={T}:offset={off:.3f}[{vout}]")
        af.append(f"[{aprev}][na{i}]acrossfade=d={T}:c1=tri:c2=tri[{aout}]")
        vprev,aprev=vout,aout
        if i<n-1: off += ds[i]-T
    # --- music bed + cheer stings -------------------------------------------
    total=sum(ds)-T*(n-1)
    extra=[]; mixes=[f"[{aprev}]"]
    nin=n                       # inputs so far; -stream_loop adds tokens, not inputs
    if music:
        mi=nin; nin+=1; ins += ["-stream_loop","-1","-i",music]
        extra.append(f"[{mi}:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
                     f"afade=t=in:d=1,afade=t=out:st={max(0,total-2):.3f}:d=2,"
                     f"volume={music_vol},aresample=48000,asettb=AVTB[bed]")
        mixes.append("[bed]")
    for k,(cf,at) in enumerate(zip(cheers or [], cheer_at or [])):
        ci=nin; nin+=1; ins += ["-i",cf]
        extra.append(f"[{ci}:a]volume={cheer_vol},aresample=48000,asettb=AVTB,"
                     f"adelay={int(max(0,at)*1000)}|{int(max(0,at)*1000)}[ch{k}]")
        mixes.append(f"[ch{k}]")
    if len(mixes)>1:
        extra.append("".join(mixes)+f"amix=inputs={len(mixes)}:duration=first:"
                     f"normalize=0[amixed]")
        amap="amixed"
    else:
        amap=aprev
    fc=";".join(vf+af+extra)
    cmd=["ffmpeg","-v","error",*ins,"-filter_complex",fc,
         "-map",f"[{vprev}]","-map",f"[{amap}]",
         "-c:v","libx264","-preset",preset,"-crf",crf,"-pix_fmt","yuv420p",
         "-c:a","aac","-b:a","128k","-movflags","+faststart","-y",out]
    r=subprocess.run(cmd,capture_output=True,text=True)
    if r.returncode!=0 or r.stderr.strip():
        print("ffmpeg rc=%s" % r.returncode,file=sys.stderr)
        print((r.stderr or "")[-1500:],file=sys.stderr)
    return picked

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--clips",required=True,help="directory of clips, or a comma-separated list")
    ap.add_argument("--out",required=True)
    ap.add_argument("--duration",type=float,default=0.4)
    ap.add_argument("--seed",type=int,default=None)
    ap.add_argument("--only-goals",action="store_true")
    ap.add_argument("--music-dir",default=os.path.expanduser("~/mnt/XbotGo/music"))
    ap.add_argument("--no-music",action="store_true")
    ap.add_argument("--music-volume",type=float,default=0.18)
    ap.add_argument("--no-cheer",action="store_true")
    ap.add_argument("--preset",default="veryfast")
    ap.add_argument("--crf",default="20")
    a=ap.parse_args()
    if os.path.isdir(a.clips):
        cl=sorted(os.path.join(a.clips,f) for f in os.listdir(a.clips) if f.endswith(".mp4"))
        if a.only_goals: cl=[c for c in cl if "_goal_" in os.path.basename(c)]
    else:
        cl=a.clips.split(",")
    rnd=random.Random(a.seed)
    # a random music bed - "whatever track was picked" - excluding the stings
    music=None
    if not a.no_music and os.path.isdir(a.music_dir):
        pool=[os.path.join(a.music_dir,f) for f in sorted(os.listdir(a.music_dir))
              if f.lower().endswith(".mp3") and not f.lower().startswith("cheer ")]
        if pool: music=rnd.choice(pool)
    # a random cheer sting on every goal, placed on the event itself
    stings=[os.path.join(a.music_dir,f) for f in sorted(os.listdir(a.music_dir))
            if f.lower().startswith("cheer ") and os.path.getsize(
                os.path.join(a.music_dir,f))<500_000] if os.path.isdir(a.music_dir) else []
    cheers=[]; cheer_at=[]
    if stings and not a.no_cheer:
        ds=[dur(c) for c in cl]; starts=reel_starts(ds,a.duration)
        import json as _j
        plan={}
        pf=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(cl[0]))),"cut_plan.json")
        if os.path.exists(pf):
            plan={j["clip"]:j for j in _j.load(open(pf, encoding="utf-8"))}
        for c,st in zip(cl,starts):
            b=os.path.basename(c)
            if "_goal_" not in b: continue
            j=plan.get(b)
            ev=(j["lead"]+j["pad"]) if j else 1.0          # event offset inside the clip
            cheers.append(rnd.choice(stings))
            cheer_at.append(st+ev-0.6)                     # peak lands on the goal
    tmp=a.out+".tmp.mp4"
    picked=build(cl,tmp,a.duration,a.seed,music=music,music_vol=a.music_volume,
                 cheers=cheers,cheer_at=cheer_at,preset=a.preset,crf=a.crf)
    # a killed ffmpeg leaves a sizeable but headerless file - verify before replacing
    good=False
    if os.path.exists(tmp) and os.path.getsize(tmp)>0:
        pr=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                           "-of","csv=p=0",tmp],capture_output=True,text=True)
        good=bool(pr.stdout.strip())
    if good:
        os.replace(tmp,a.out)
        print(f"{len(cl)} clips -> {a.out}  ({dur(a.out):.1f}s)")
        print("  transitions:", ", ".join(picked))
        if music: print("  music bed  :", os.path.basename(music))
        for cf,at in zip(cheers,cheer_at):
            print(f"  cheer      : {os.path.basename(cf)} at {at:.1f}s")
    else:
        if os.path.exists(tmp): os.remove(tmp)
        print("FAILED (incomplete output discarded)"); sys.exit(1)
