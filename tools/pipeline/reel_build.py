#!/usr/bin/env python3
"""Assemble clips into a reel with random transitions, a music bed and cheer
stings on goals.

Built in SEGMENTS, not one giant filtergraph: a 13-input xfade chain opens 13
decoders at once and gets OOM-killed. Here every render has at most 2 inputs.

  seg0 = clip0[0 .. d0-T]
  junc_i = xfade(clip_i last T, clip_{i+1} first T)        <- T seconds
  seg_i = clip_i[T .. d_i-T]      (middle clips)
  seg_last = clip_last[T .. d_last]
  reel = seg0 + junc0 + seg1 + junc1 + ... + seg_last

Total length = sum(d) - (n-1)*T, same as a single xfade chain.
Music and cheers are mixed in a final audio-only pass (-c:v copy), which is cheap.
Pieces are cached in <out>.work/ so an interrupted run resumes.
"""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils\ on PATH
import argparse, json, os, random, subprocess, sys

# personal / special-occasion tracks - never picked at random
EXCLUDE = ["remember_the_name"]

STYLES = ["slideleft","slideright","slideup","slidedown",
          "wipeleft","wiperight","wipeup","wipedown",
          "smoothleft","smoothright","smoothup","smoothdown",
          "circlecrop","rectcrop","circleopen","circleclose",
          "dissolve","pixelize","radial","fadeblack","diagtl","diagbr"]
FPS=30
NORM_V=f"fps={FPS},settb=AVTB,format=yuv420p,setsar=1"
NORM_A="aresample=48000,asettb=AVTB"

def sh(c): return subprocess.run(c,capture_output=True,text=True)
def dur(f):
    r=sh(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",f])
    try: return float(r.stdout.strip())
    except ValueError: return -1.0
def ok(f,want=None,tol=0.35):
    if not os.path.exists(f) or os.path.getsize(f)==0: return False
    d=dur(f)
    if d<=0: return False
    return True if want is None else abs(d-want)<tol

def enc(preset,crf):
    return ["-c:v","libx264","-preset",preset,"-crf",crf,"-pix_fmt","yuv420p",
            "-c:a","aac","-b:a","128k","-ar","48000"]

def seg(src,start,length,dst,preset,crf):
    if ok(dst,length): return True
    sh(["ffmpeg","-v","error","-ss",f"{start:.3f}","-i",src,"-t",f"{length:.3f}",
        "-vf",NORM_V,"-af",NORM_A,*enc(preset,crf),"-movflags","+faststart","-y",dst])
    return ok(dst,length)

def junction(a,b,ta,T,style,dst,preset,crf):
    if ok(dst,T): return True
    fc=(f"[0:v]{NORM_V}[v0];[1:v]{NORM_V}[v1];"
        f"[v0][v1]xfade=transition={style}:duration={T}:offset=0[v];"
        f"[0:a]{NORM_A}[a0];[1:a]{NORM_A}[a1];"
        f"[a0][a1]acrossfade=d={T}:c1=tri:c2=tri[a]")
    sh(["ffmpeg","-v","error","-ss",f"{ta:.3f}","-i",a,"-t",f"{T:.3f}",
        "-i",b,"-t",f"{T:.3f}","-filter_complex",fc,"-map","[v]","-map","[a]",
        *enc(preset,crf),"-movflags","+faststart","-y",dst])
    return ok(dst,T)

def ts_concat(parts,dst,work):
    tss=[]
    for i,p in enumerate(parts):
        t=os.path.join(work,f"c{i:04d}.ts")
        # reuse a cached .ts only if it is complete (an interrupted write leaves a short one)
        if not (os.path.exists(t) and os.path.getsize(t)>0 and abs(dur(t)-dur(p))<0.2):
            sh(["ffmpeg","-v","error","-i",p,"-c","copy","-bsf:v","h264_mp4toannexb",
                "-f","mpegts","-y",t])
        tss.append(t)
    sh(["ffmpeg","-v","error","-i","concat:"+"|".join(tss),"-c","copy",
        "-movflags","+faststart","-y",dst])
    return ok(dst)

def sfx_static_db(f):
    """gain in dB that brings the whole file to -14 LUFS (peaks <= -1.5 dBTP): same level loudnorm gave, but no time shift."""
    r=subprocess.run(["ffmpeg","-v","info","-i",f,"-af","loudnorm=I=-14:TP=-1.5:print_format=json","-f","null","-"],
                     capture_output=True,text=True)
    import re
    i=float(re.search(r'"input_i"\s*:\s*"(-?[0-9.]+)"',r.stderr).group(1))
    tp=float(re.search(r'"input_tp"\s*:\s*"(-?[0-9.]+)"',r.stderr).group(1))
    return min(-14.0-i,-1.5-tp)

def make_stem(total,items,work):
    """Mix (file, ffmpeg filter chain, start second) items into one stereo 48 kHz 16-bit wav of exactly `total` seconds."""
    import numpy as np, wave
    SR=48000; buf=np.zeros((int(round(total*SR))+SR,2),dtype=np.float32)
    for f,chain,at in items:
        r=subprocess.run(["ffmpeg","-v","error","-i",f,"-af",chain,"-ac","2","-ar",str(SR),"-f","f32le","-"],capture_output=True)
        pc=np.frombuffer(r.stdout,dtype=np.float32).reshape(-1,2)
        o=int(round(at*SR)); n=min(len(pc),len(buf)-o)
        if n>0: buf[o:o+n]+=pc[:n]
    buf=np.clip(buf[:int(round(total*SR))],-1.0,1.0)
    out=os.path.join(work,"extras_stem.wav")
    w=wave.open(out,"wb"); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((buf*32767).astype("<i2").tobytes()); w.close()
    return out

def make_bed(music,total,vol,pauses,work,f=0.4):
    """Looped music bed for exactly `total` s: fades in/out, volume, and silence (with f-second ramps) inside every pause interval."""
    import numpy as np, wave
    SR=48000
    chain=(f"atrim=0:{total:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=1,afade=t=out:st={max(0,total-2):.3f}:d=2,"
           f"volume={vol},aresample={SR},aformat=channel_layouts=stereo")
    r=subprocess.run(["ffmpeg","-v","error","-stream_loop","-1","-i",music,"-af",chain,"-t",f"{total:.3f}","-ac","2","-ar",str(SR),"-f","f32le","-"],capture_output=True)
    x=np.frombuffer(r.stdout,dtype=np.float32).reshape(-1,2).copy()
    if pauses:
        t=np.arange(len(x))/SR
        d=np.min(np.stack([np.maximum(s-t,t-e) for s,e in pauses]),axis=0)
        x*=np.clip(d/f,0.0,1.0)[:,None].astype(np.float32)
    out=os.path.join(work,"bed_gated.wav")
    w=wave.open(out,"wb"); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(x,-1,1)*32767).astype("<i2").tobytes()); w.close()
    return out

def gate(iv,f=0.4):
    """volume expression that fades the music to 0 inside each (start,end) interval (f s fade on both sides)."""
    if not iv: return ""
    terms=[f"max({s:.3f}-t,t-{e:.3f})" for s,e in iv]
    d=terms[0]
    for t in terms[1:]: d=f"min({d},{t})"
    return f",volume='min(1,max(0,({d})/{f}))':eval=frame"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--clips",required=True)
    ap.add_argument("--out",required=True)
    ap.add_argument("--duration",type=float,default=0.4)
    ap.add_argument("--seed",type=int,default=None)
    ap.add_argument("--only-goals",action="store_true")
    ap.add_argument("--music-dir",default=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),"shared","Music"))
    ap.add_argument("--no-music",action="store_true")
    ap.add_argument("--track",default=None,help="music file name inside --music-dir (overrides the random pick)")
    ap.add_argument("--music-volume",type=float,default=0.18)
    ap.add_argument("--no-tame",action="store_true",
                    help="skip the compressor/limiter on the clip audio (it evens out loud shouting near the camera)")
    ap.add_argument("--game-volume",type=float,default=None,help="level of the recorded game sound (parents, whistles) in the reel; 0 = muted (default, user rule 2026-03-30: parents silenced on reels)")
    ap.add_argument("--no-cheer",action="store_true")
    ap.add_argument("--cheer-volume",type=float,default=0.9)
    ap.add_argument("--cheer-clips",default=None,
                    help="comma list of clip basenames that get a cheer (default: every _goal_ clip)")
    ap.add_argument("--extras",default=None,help="extras.json: goal-sound overlays (sfx) and music pauses around announcer segments / sfx")
    ap.add_argument("--extras-root",default=".")
    ap.add_argument("--preset",default="veryfast"); ap.add_argument("--crf",default="20")
    a=ap.parse_args()

    if os.path.isdir(a.clips):
        cl=sorted(os.path.join(a.clips,f) for f in os.listdir(a.clips) if f.endswith(".mp4"))
        if a.only_goals: cl=[c for c in cl if "_goal_" in os.path.basename(c)]
    else:
        cl=a.clips.split(",")
    n=len(cl); T=a.duration
    if n==0: sys.exit("no clips")
    ds=[dur(c) for c in cl]
    work=xb_env.tmp_for(a.out)+".work"; os.makedirs(work,exist_ok=True)
    rnd=random.Random(a.seed)
    styles=[rnd.choice(STYLES) for _ in range(max(0,n-1))]

    parts=[]; done=0
    for i,c in enumerate(cl):
        start = 0.0 if i==0 else T
        end   = ds[i] if i==n-1 else ds[i]-T
        length= end-start
        p=os.path.join(work,f"seg{i:03d}.mp4")
        if not seg(c,start,length,p,a.preset,a.crf): sys.exit(f"segment {i} failed")
        parts.append(p); done+=1
        if i<n-1:
            j=os.path.join(work,f"junc{i:03d}.mp4")
            if not junction(cl[i],cl[i+1],ds[i]-T,T,styles[i],j,a.preset,a.crf):
                sys.exit(f"junction {i} failed")
            parts.append(j); done+=1
        print(f"  {done}/{2*n-1} pieces", flush=True)

    raw=os.path.join(work,"joined.mp4")
    want=sum(ds)-(n-1)*T
    # resume: keep an existing join that is newer than every piece and the right length
    if os.environ.get('REEL_DEBUG') and ok(raw,want,3.0): print('  debug: reusing joined',dur(raw),'want',want,flush=True)
    elif not (ok(raw,want,0.5) and os.path.getmtime(raw)>=max(os.path.getmtime(p) for p in parts)):
        if not ts_concat(parts,raw,work): sys.exit("concat failed")
        print("  joined", flush=True)

    # ---- music bed + cheer stings, audio only (video stream-copied) ----------
    total=dur(raw)
    music=None; stings=[]
    if os.path.isdir(a.music_dir):
        pool=[os.path.join(a.music_dir,f) for f in sorted(os.listdir(a.music_dir))
              if f.lower().endswith(".mp3") and not f.lower().startswith("cheer ")
              and not any(x in f.lower() for x in EXCLUDE)]
        if pool and not a.no_music:
            # any bed, picked at random (user rule 2026-03-16); -stream_loop below loops it as needed
            music=rnd.choice(pool)
            if a.track:
                hit=[x for x in pool if os.path.basename(x)==a.track]
                if hit: music=hit[0]
        stings=[os.path.join(a.music_dir,f) for f in sorted(os.listdir(a.music_dir))
                if f.lower().startswith("cheer ")
                and os.path.getsize(os.path.join(a.music_dir,f))<500_000]
    # where each clip lands on the reel timeline
    starts=[0.0]
    for d in ds[:-1]: starts.append(starts[-1]+d-T)
    plan={}
    pf=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(cl[0]))),"cut_plan.json")
    if os.path.exists(pf): plan={j["clip"]:j for j in json.load(open(pf, encoding="utf-8"))}
    cheers=[]
    if stings and not a.no_cheer:
        for c,st in zip(cl,starts):
            b=os.path.basename(c)
            if a.cheer_clips is not None:
                if b not in a.cheer_clips.split(","): continue
            elif "_goal_" not in b: continue
            j=plan.get(b)
            ev=(j.get("ev_off", j["lead"]+j["pad"])) if j else 1.0
            cheers.append((rnd.choice(stings), max(0.0, st+ev-0.6)))

    # ---- extras: goal sound overlays + intervals where the music pauses ------------
    sfx=[]; pauses=[]; sfx_file=None
    if a.extras:
        ex=json.load(open(a.extras, encoding="utf-8")); sc=ex.get("sfx") or {}
        sfx_file=os.path.join(a.extras_root,sc["file"]) if sc.get("file") else None
        def find(tok,replay):
            for i,c in enumerate(cl):
                b=os.path.basename(c)
                if tok in b and (("zoom" in b)==bool(replay)): return i
            return None
        for ov in sc.get("overlays",[]):
            if ov.get("silent"): continue   # keeps the "no cheer on this clip" rule but plays no goal sound
            i=find(ov.get("clip") or ov.get("replay"),bool(ov.get("replay")))
            if i is None: print("  sfx: no piece for",ov); continue
            s0,s1=ov["src"]; at=ov["at"]; span=s1-s0
            if ov.get("to_end"): span=min(span,ds[i]-at)
            sfx.append((s0,s0+span,starts[i]+at,ov.get("fade_out",0.05)))
        for k,c in enumerate(cl):
            if os.path.basename(c).startswith("announcer"): pauses.append((starts[k],starts[k]+ds[k]))
        pauses+=[(t,t+(e-s)) for s,e,t,_ in sfx]
        if not ex.get("pause_music",True): pauses=[]
    if a.game_volume is None:
        if any(os.path.basename(c).startswith("announcer") for c in cl):
            a.game_volume=1.0; print("  note: announcer inserts present -> game sound NOT muted (the announcer voice is part of the clip audio); pass --game-volume 0 to mute anyway")
        else: a.game_volume=0.0
    print("  game sound level in reel:",a.game_volume)
    if not music and not cheers and not sfx and a.no_tame and a.game_volume==1:
        os.replace(raw,a.out)
    else:
        ins=["-i",raw]; idx=1
        # even out loud peaks (shouting close to the camera): threshold -30 dB, ratio 4, then a plain peak limiter
        # joined.mp4 audio carries one extra AAC frame per piece boundary (83 duplicate-timestamp packets, ~1.8 s by the end of a reel):
        # decoded sequentially it drifts ~1.3 s away from the picture by minute 3.  async resample trims it back to the video timeline.
        fl=["[0:a]aresample=async=1:min_hard_comp=0.02,"+("anull" if a.no_tame else "acompressor=threshold=0.0316:ratio=4:attack=10:release=250:knee=4,alimiter=limit=0.25:level=0")+f",volume={a.game_volume}[a0]"]
        mixes=["[a0]"]
        if music:
            bed=make_bed(music,total,a.music_volume,pauses,work)   # music with the pauses applied sample-exactly (the ffmpeg volume/eval=frame gate failed inside the full graph)
            ins+=["-i",bed]
            fl.append(f"[{idx}:a]aformat=channel_layouts=stereo,aresample=48000[bed]")
            mixes.append("[bed]"); idx+=1
        # cheers + goal sounds are placed sample-exactly into ONE full-length stem file (numpy), then mixed in as a single input.
        # (long adelay chains inside amix lost/shifted the goal sound with some ffmpeg builds; loudnorm in the chain shifted it ~1.5 s)
        items=[]
        for cf,at in cheers:
            items.append((cf,f"volume={a.cheer_volume},aresample=48000,aformat=channel_layouts=stereo",at))
        if sfx:
            sfx_db=sfx_static_db(sfx_file); g_=sc.get("gain",0.64)
            for k,(s0,s1,at,fo) in enumerate(sfx):
                L=s1-s0
                items.append((sfx_file,f"aresample=48000,aformat=channel_layouts=stereo,volume={sfx_db:.2f}dB,volume={g_},"
                              f"atrim={s0:.3f}:{s1:.3f},asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.05,"
                              f"afade=t=out:st={max(0,L-fo):.3f}:d={fo}",at))
        if items:
            stem=make_stem(total,items,work)
            ins+=["-i",stem]; mixes.append(f"[{idx}:a]aformat=channel_layouts=stereo,aresample=48000"); idx+=1
            mixes[-1]+="[stem]"; fl.append(mixes.pop()); mixes.append("[stem]")
        fl.append("".join(mixes)+f"amix=inputs={len(mixes)}:duration=first:normalize=0:dropout_transition=0[am]")
        if os.environ.get("REEL_DEBUG"):
            print("INS",ins,"\nGRAPH",";\n".join(fl),flush=True)
            if os.environ["REEL_DEBUG"]=="exit": sys.exit(0)
        r=sh(["ffmpeg","-v","error",*ins,"-filter_complex",";".join(fl),
              "-map","0:v","-map","[am]","-c:v","copy","-c:a","aac","-b:a","160k",
              "-movflags","+faststart","-y",a.out])
        if not ok(a.out): sys.exit("audio mix failed:\n"+(r.stderr or "")[-800:])

    print(f"\n{n} clips -> {a.out}  ({dur(a.out):.1f}s)")
    print("  transitions:", ", ".join(styles) if styles else "(none)")
    if music: print("  music bed  :", os.path.basename(music))
    for cf,at in cheers: print(f"  cheer      : {os.path.basename(cf)} at {at:.1f}s")

if __name__=="__main__": main()
