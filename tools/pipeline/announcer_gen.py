#!/usr/bin/env python3
"""Cartoon announcer segment (original character, drawn with PIL; mouth follows the audio) for highlight reels.

  python tools\\pipeline\\announcer_gen.py --line "Three minutes left in the game, and S P F trails three to one! Can they pull off a comeback?" ^
      --clock "3:13 LEFT" --score "Home FC  1 - 3  Guest FC" --out out\\2026-03-22\\announcer\\announcer1_4k.mp4 [--banner "COMEBACK ALERT!"] [--height 2160|720]
  --audio some.wav   use ready-made audio instead of text-to-speech (e.g. a sound effect)
  --goal             excited version: arms up, confetti, GOOOAL! text (use with --audio)

Text-to-speech: kokoro-onnx (pip install kokoro-onnx soundfile pillow numpy), voice am_michael, then pitched up 8% with a stadium echo.
Model files (download once, put them in tools\\kokoro\\): 
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx   (kokoro.onnx)
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin    (voices.bin)
Output: 30 fps h264 + aac 48k, same size as the clips. Used by out\\<game>\\extras.json -> make_reels.py (see the project doc
xbotgo-zoom-pan-and-reel-extras.md). First built for an earlier game; now generic.
"""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils\ on PATH
import argparse, os, subprocess, sys, tempfile
ap = argparse.ArgumentParser()
ap.add_argument("--line"); ap.add_argument("--audio"); ap.add_argument("--clock", default="")
ap.add_argument("--score", default=""); ap.add_argument("--banner", default=""); ap.add_argument("--goal", action="store_true")
ap.add_argument("--out", required=True); ap.add_argument("--height", type=int, default=2160)
ap.add_argument("--model-dir", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kokoro"))
A = ap.parse_args()
tmp = tempfile.mkdtemp()
if not A.audio:
    if not A.line: sys.exit("give --line or --audio")
    from kokoro_onnx import Kokoro
    import soundfile as sf
    k = Kokoro(os.path.join(A.model_dir, "kokoro.onnx"), os.path.join(A.model_dir, "voices.bin"))
    smp, sr0 = k.create(A.line, voice="am_michael", speed=1.0, lang="en-us")
    raw = os.path.join(tmp, "raw.wav"); sf.write(raw, smp, sr0)
    A.audio = os.path.join(tmp, "voice.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-af",
                    "atempo=0.95,asetrate=24000*1.08,aresample=24000,highpass=f=120,acompressor=threshold=-20dB:ratio=4,aecho=0.8:0.5:60:0.25,volume=1.6",
                    A.audio], check=True)
AUD, OUT = A.audio, A.out
OHH = A.height; OWW = OHH * 16 // 9
os.environ["SS"] = "4"; os.environ["OW"] = str(OWW); os.environ["OH"] = str(OHH)
CLOCK, SCORE, BANNER, GOAL = A.clock, A.score, A.banner, A.goal
import numpy as np, soundfile as sf, math, random
from PIL import Image, ImageDraw, ImageFont
import os
W,H,S=1280,720,int(os.environ['SS'])
OW,OH=int(os.environ['OW']),int(os.environ['OH'])
FPS=30; LEAD=0.45; TAIL=0.5
a,sr=sf.read(AUD); 
if a.ndim>1: a=a.mean(1)
dur=LEAD+len(a)/sr+TAIL; N=int(dur*FPS)
env=np.zeros(N)
for i in range(N):
    t=i/FPS-LEAD; j0=int(t*sr); j1=j0+int(sr/FPS)
    if 0<=j0<len(a): env[i]=np.sqrt(np.mean(a[j0:j1]**2)) if j1>j0 else 0
env=env/(env.max()+1e-9); env=np.convolve(env,[.3,.4,.3],'same')
F=lambda s,b=True: ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if b else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',int(s*S))
def bg(d):
    # studio: dark blue gradient + spotlights + city skyline silhouette
    for y in range(H*S):
        c=int(20+40*y/(H*S)); d.line([(0,y),(W*S,y)],fill=(c//2,c//2+6,c+40))
    random.seed(3)
    x=0
    while x<W*S:
        w=random.randint(60,140)*S//1; h=random.randint(120,300)*S//1
        d.rectangle([x,(430*S)-h,x+w,430*S],fill=(18,22,48)); 
        for wy in range(int(430*S-h)+10*S,430*S-10*S,28*S):
            for wx in range(x+10*S,x+w-12*S,24*S):
                if random.random()<.35: d.rectangle([wx,wy,wx+8*S,wy+12*S],fill=(255,214,102))
        x+=w+6*S
    d.rectangle([0,430*S,W*S,H*S],fill=(30,34,70))
def tri(d,pts,fill): d.polygon(pts,fill=fill)
def frame(i):
    t=i/FPS; k=env[i]
    im=Image.new('RGB',(W*S,H*S)); d=ImageDraw.Draw(im,'RGBA'); bg(d)
    # spotlight cones
    sw=math.sin(t*1.6)*40*S
    tri(d,[(260*S,0),(60*S+sw,H*S),(520*S+sw,H*S)],(255,255,255,26)); tri(d,[(1020*S,0),(760*S-sw,H*S),(1220*S-sw,H*S)],(255,255,255,26))
    # scale-in bounce for the whole character
    bob=math.sin(t*9)*4*S*(0.3+k)
    cx,cy=640*S,330*S+bob
    # body (blazer + shirt + tie)
    d.rounded_rectangle([cx-190*S,cy+120*S,cx+190*S,cy+330*S],radius=70*S,fill=(40,70,170))
    tri(d,[(cx-60*S,cy+120*S),(cx+60*S,cy+120*S),(cx,cy+260*S)],(245,245,245))
    tri(d,[(cx-14*S,cy+150*S),(cx+14*S,cy+150*S),(cx+22*S,cy+250*S),(cx,cy+275*S),(cx-22*S,cy+250*S)],(210,40,50))
    if GOAL:
        up=0.5+0.5*math.sin(t*7)
        for sx in (-1,1):
            d.line([cx+sx*170*S,cy+170*S,cx+sx*(230+20*up)*S,cy-60*S-40*S*up],fill=(40,70,170),width=44*S)
            d.ellipse([cx+sx*(230+20*up)*S-30*S,cy-100*S-40*S*up,cx+sx*(230+20*up)*S+30*S,cy-40*S-40*S*up],fill=(246,190,140),outline=(120,70,40),width=4*S)
    # neck + head
    d.rectangle([cx-40*S,cy+85*S,cx+40*S,cy+135*S],fill=(238,178,128))
    d.ellipse([cx-140*S,cy-160*S,cx+140*S,cy+110*S],fill=(246,190,140),outline=(120,70,40),width=5*S)
    # ears
    for sx in (-1,1): d.ellipse([cx+sx*140*S-26*S,cy-30*S,cx+sx*140*S+26*S,cy+40*S],fill=(238,176,126),outline=(120,70,40),width=4*S)
    # hair
    d.pieslice([cx-150*S,cy-190*S,cx+150*S,cy+20*S],180,360,fill=(60,38,24))
    tri(d,[(cx-150*S,cy-70*S),(cx-120*S,cy-120*S),(cx-100*S,cy-60*S)],(60,38,24)); tri(d,[(cx+150*S,cy-70*S),(cx+120*S,cy-120*S),(cx+100*S,cy-60*S)],(60,38,24))
    # eyes (blink + excited look), big brows
    blink=1 if (int(t*1000)%2300)<110 else 0
    exc=0.5+0.5*math.sin(t*5)
    for sx in (-1,1):
        ex,ey=cx+sx*58*S,cy-40*S
        d.ellipse([ex-34*S,ey-38*S,ex+34*S,ey+38*S],fill='white',outline=(60,40,30),width=4*S)
        if blink: d.line([ex-30*S,ey,ex+30*S,ey],fill=(60,40,30),width=6*S)
        else: d.ellipse([ex-14*S+sx*-4*S,ey-14*S+(exc-.5)*8*S,ex+14*S+sx*-4*S,ey+14*S+(exc-.5)*8*S],fill=(30,20,20))
        lift=(10+18*k)*S
        d.line([ex-34*S,ey-46*S-lift*(0.5 if sx<0 else 1),ex+34*S,ey-52*S-lift*(1 if sx<0 else .5)],fill=(60,38,24),width=12*S)
    # nose
    d.ellipse([cx-16*S,cy-4*S,cx+16*S,cy+30*S],fill=(236,160,112))
    # mouth driven by audio
    mo=max(0.08,min(1,k*1.4))
    mw=70*S; mh=(10+62*mo)*S
    d.ellipse([cx-mw,cy+48*S,cx+mw,cy+48*S+mh],fill=(110,20,35),outline=(70,10,20),width=4*S)
    if mo>0.25: d.ellipse([cx-mw*.55,cy+48*S+mh*.55,cx+mw*.55,cy+48*S+mh*.95],fill=(230,90,110))
    d.rectangle([cx-mw*.8,cy+52*S,cx+mw*.8,cy+52*S+min(mh*.3,16*S)],fill='white')
    # headset + microphone
    d.arc([cx-160*S,cy-185*S,cx+160*S,cy+60*S],200,340,fill=(30,30,30),width=12*S)
    d.ellipse([cx-172*S,cy-40*S,cx-118*S,cy+30*S],fill=(30,30,30)); d.ellipse([cx+118*S,cy-40*S,cx+172*S,cy+30*S],fill=(30,30,30))
    d.line([cx-150*S,cy+10*S,cx-90*S,cy+85*S,cx-30*S,cy+100*S],fill=(30,30,30),width=8*S)
    d.ellipse([cx-52*S,cy+88*S,cx-6*S,cy+122*S],fill=(80,80,80),outline=(20,20,20),width=3*S)
    # hand-held fist-pump arm when loud
    # desk
    d.rounded_rectangle([140*S,520*S,1140*S,720*S],radius=30*S,fill=(122,64,34)); d.rectangle([140*S,520*S,1140*S,545*S],fill=(150,84,46))
    d.text((640*S,690*S),"S P F   S P O R T S   N E T W O R K",font=F(26),fill=(255,214,102),anchor='mm')
    # speech burst lines
    for n in range(6):
        ang=-60+n*24; r1=185*S; r2=(205+60*k)*S
        if k>0.35:
            x1=cx+r1*math.cos(math.radians(ang-90)); y1=cy-20*S+r1*math.sin(math.radians(ang-90))
            x2=cx+r2*math.cos(math.radians(ang-90)); y2=cy-20*S+r2*math.sin(math.radians(ang-90))
            d.line([x1,y1,x2,y2],fill=(255,214,102),width=7*S)
    # scoreboard + banner
    slide=min(1,t/0.35); bx=int((-460+460*slide)*S)
    d.rounded_rectangle([bx+30*S,30*S,bx+430*S,150*S],radius=18*S,fill=(10,20,60),outline=(255,214,102),width=5*S)
    d.text((bx+230*S,62*S),CLOCK,font=F(44),fill=(255,214,102),anchor='mm')
    d.text((bx+230*S,115*S),SCORE,font=F(34),fill='white',anchor='mm')
    if BANNER:
        pulse=1+0.04*math.sin(t*8)
        bw=int(560*pulse)*S
        d.rounded_rectangle([W*S//2-bw//2,565*S,W*S//2+bw//2,645*S],radius=14*S,fill=(210,40,50),outline='white',width=4*S)
        d.text((W*S//2,605*S),BANNER,font=F(40),fill='white',anchor='mm')
        if GOAL:
            rnd=random.Random(7)
            for n in range(90):
                x0=rnd.random()*W; sp=120+rnd.random()*260; ph=rnd.random()*6
                yy=((t*sp+rnd.random()*H)%(H+40))-20; xx=x0+math.sin(t*3+ph)*20
                col=rnd.choice([(255,214,102),(210,40,50),(80,200,255),(255,255,255),(120,255,140)])
                d.rectangle([xx*S,yy*S,xx*S+9*S,yy*S+14*S],fill=col)
            if True:
                sc=1+0.08*math.sin(t*10)
                d.text((720*S,95*S),"GOOOAL!",font=F(int(70*sc)),fill=(255,214,102),anchor='mm',stroke_width=6*S,stroke_fill=(120,30,20))
            else:
                d.text((720*S,95*S),"UNBELIEVABLE FINISH!",font=F(40),fill='white',anchor='mm',stroke_width=5*S,stroke_fill=(20,30,100))
    return im.resize((OW,OH),Image.LANCZOS)
enc=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{OW}x{OH}','-r',str(FPS),'-i','-',
  '-f','lavfi','-t',f'{dur:.3f}','-i','anullsrc=r=48000:cl=stereo','-i',AUD,
  '-filter_complex',f'[2:a]aresample=48000,adelay={int(LEAD*1000)}|{int(LEAD*1000)},apad,atrim=0:{dur:.3f}[a]',
  '-map','0:v','-map','[a]','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000','-t',f'{dur:.3f}',OUT],stdin=subprocess.PIPE)
for i in range(N):
    enc.stdin.write(frame(i).tobytes())
enc.stdin.close(); enc.wait(); print('done',dur,N)
