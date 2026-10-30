import re,sys,json,csv
TS=re.compile(r'^\d{4}-\d\d-\d\d (\d\d):(\d\d):(\d\d\.\d+)$')
def records(path):
    lines=open(path,errors='replace', encoding="utf-8").read().split('\n')
    # rejoin lines split by an injected timestamp (timestamp not preceded by blank line)
    out=[];cur_t=None;i=0;buf=[]
    blocks=[]  # (t, text)
    prev_blank=True
    for ln in lines:
        m=TS.match(ln)
        if m:
            t=int(m.group(1))*3600+int(m.group(2))*60+float(m.group(3))
            if prev_blank or not buf:
                if buf: blocks.append((cur_t,'\n'.join(buf)))
                buf=[];cur_t=t
                prev_blank=False
                continue
            else:
                # split: mark join
                buf.append('\x00'); prev_blank=False; continue
        if ln=='' : prev_blank=True
        else: prev_blank=False
        buf.append(ln)
    if buf: blocks.append((cur_t,'\n'.join(buf)))
    res=[]
    for t,txt in blocks:
        txt=txt.replace('\n\x00\n','')
        res.append((t,txt))
    return res
rx=dict(
 frame=re.compile(r'Frame(\d+) fps(\d+) SZ(\d+) Yaw(-?[\d.]+) Pit(-?[\d.]+)'),
 ff=re.compile(r'FFilterP(\d+) mot(\d+) Deque(\d+)'),
 fast=re.compile(r'Fast(\d+) Crowdx(-?\d+)'),
 ball=re.compile(r'BallSz(\d+)(?: TSz(\d+))?\s*(BallFail)?'),
 bt=re.compile(r'BT(\d+)(maySta)?(RB|PB)\((-?\d+),(-?\d+),(\d+),(\d+)\)V(-?\d+)(F)?to([LR]) Ballx(-?\d+) OutX(-?\d+)'),
 auto=re.compile(r'autoCenterX(-?\d+)'),
 back=re.compile(r'backCenterX(-?\d+)'),
 bnd=re.compile(r'boundary(-?\d+) ([LR])X(-?\d+)'),
 fin=re.compile(r'Frame(\d+) FIN:x(-?\d+) y(-?\d+) V(-?\d+) YawErr(-?\d+) out(-?\d+) Ctrl:X(-?\d+) Y(-?\d+) (?:\+Zoom:([\d.]+) )?zoomSz(-?\d+) In:(-?\d+) Lock:(\d+)/(\d+)'),
)
def parse(path):
    frames={}; sess=0
    for t,txt in records(path):
        if 'SDKStart' in txt: sess+=1
        m=rx['frame'].search(txt)
        if m:
            d=frames.setdefault(f'{sess}:{int(m.group(1)):06d}',{})
            d.update(t=t,fps=int(m.group(2)),sz=int(m.group(3)),yaw=float(m.group(4)),pit=float(m.group(5)))
            if (x:=rx['ff'].search(txt)): d.update(ffp=int(x.group(1)),mot=int(x.group(2)),deq=int(x.group(3)))
            if (x:=rx['fast'].search(txt)): d.update(fast=int(x.group(1)),crowdx=int(x.group(2)))
            if (x:=rx['ball'].search(txt)): d.update(ballsz=int(x.group(1)),tsz=int(x.group(2) or 0),ballfail=bool(x.group(3)))
            d['ntracks']=len(re.findall(r'^T\d+ RB',txt,re.M))
            if (x:=rx['bt'].search(txt)):
                d.update(bpos=[int(x.group(i)) for i in (4,5,6,7)],mode=('sta' if x.group(2) else '')+x.group(3),bv=int(x.group(8)),bfast=bool(x.group(9)),bdir=x.group(10),ballx=int(x.group(11)),outx=int(x.group(12)))
            elif (x:=rx['bnd'].search(txt)): d.update(mode='boundary')
            elif (x:=rx['back'].search(txt)): d.update(mode='backCenter',outx=int(x.group(1)))
            elif (x:=rx['auto'].search(txt)): d.update(mode='autoCenter',outx=int(x.group(1)))
            else: d.setdefault('mode','other'); d.setdefault('raw',txt[:300])
            if (x:=rx['auto'].search(txt)): d['autox']=int(x.group(1))
        m=rx['fin'].search(txt)
        if m:
            d=frames.setdefault(f'{sess}:{int(m.group(1)):06d}',{})
            g=list(m.groups()); zc=g.pop(8); g=[int(v) for v in g]
            d.update(finx=g[1],finV=g[3],yawerr=g[4],out=g[5],ctrlx=g[6],zoom=g[8],inn=g[9],lk1=g[10],lk2=g[11],tfin=t,zcmd=float(zc) if zc else None)
    return frames
if __name__=='__main__':
    fr=parse(sys.argv[1]); json.dump(fr,open(sys.argv[2],'w', encoding="utf-8"))
    print(len(fr))
