#!/usr/bin/env python3
"""
xbotgo.py - process an XbotGo (app v5.x) match-day dump into reviewable highlights.

Sub-commands
  analyze   parse dump + OCR-align burned-in clock -> timeline.json + marks.csv
  preview   fast stream-copy clips / reels from marks.csv (keyframe-snapped)
  render    frame-accurate re-encode of clips / reels from marks.csv
  full      concat the source segments into one full-game file

See SKILL.md for the workflow.
"""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils\ on PATH
import argparse, csv, json, os, re, subprocess, sys, tempfile, shutil
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------- helpers

def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)

def hhmmss(s):
    s = int(round(s)); sign = "-" if s < 0 else ""; s = abs(s)
    return f"{sign}{s//3600:02d}:{s%3600//60:02d}:{s%60:02d}"

def ffprobe_dur(path):
    r = sh(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",path])
    return float(r.stdout.strip())

def ffprobe_wh(path):
    r = sh(["ffprobe","-v","error","-select_streams","v:0",
            "-show_entries","stream=width,height","-of","csv=p=0:s=x",path])
    w,h = r.stdout.strip().split("x")[:2]
    return int(w), int(h)

# ---------------------------------------------------------------- discovery

VIDEO_RE = re.compile(r'^(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})_(\d{13})\.mp4$', re.I)

def find_root(day_dir):
    """Locate the dump root (the dir holding DCIM/ and Android/) - normally the day folder itself."""
    for dirpath, dirnames, _ in os.walk(day_dir):
        if "DCIM" in dirnames and "Android" in dirnames:
            return dirpath
    # fall back: day_dir itself
    return day_dir

def _find_dir(day_dir, rel):
    """First directory under day_dir whose path ends with rel (a tuple of parts)."""
    for dirpath, dirnames, _ in os.walk(day_dir):
        cand = os.path.join(dirpath, *rel)
        if os.path.isdir(cand):
            return cand
    return None

def discover(day_dir):
    # Layouts: <day>/Videos + <day>/com.blink.blinkfocos/files (from 2026-03-21),
    # <day>/DCIM/XbotGo + <day>/Android/data/... (earlier). See dumplayout.py.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import dumplayout
    root = day_dir
    dcim = dumplayout.find_video_dir(day_dir)
    if dcim is None:
        raise SystemExit(f"no XbotGo videos found under {day_dir}")
    appdir = dumplayout.find_appdir(day_dir)
    if appdir is None:
        raise SystemExit(f"no com.blink.blinkfocos/files under {day_dir}")

    vids = []
    for f in sorted(os.listdir(dcim)):
        m = VIDEO_RE.match(f)
        if not m: continue
        stem, epoch_ms = m.group(1), int(m.group(2))
        local = datetime.strptime(stem, "%Y-%m-%d-%H-%M-%S")
        vids.append(dict(path=os.path.join(dcim,f), file=f, stem=stem,
                         start_epoch=epoch_ms/1000.0, local_naive=local))
    if not vids:
        raise SystemExit("no videos matched the XbotGo naming pattern")

    # timezone offset implied by filename (local wall) vs embedded epoch
    v0 = vids[0]
    tz_off = round((v0["local_naive"].replace(tzinfo=timezone.utc).timestamp()
                    - v0["start_epoch"]) / 60.0) * 60          # seconds, snapped to the minute
    return dict(root=root, dcim=dcim, appdir=appdir, videos=vids, tz_off=tz_off,
                date=vids[0]["stem"][:10])

def local_to_epoch(date_str, clock_str, tz_off):
    dt = datetime.strptime(f"{date_str} {clock_str}", "%Y-%m-%d %H:%M:%S")
    return dt.replace(tzinfo=timezone.utc).timestamp() - tz_off

# ---------------------------------------------------------------- parsers

def parse_dotted(appdir, date_str, stem):
    """files/Dotted/<date>/<stem>.txt -> list of (epoch_seconds, type)."""
    p = os.path.join(appdir, "Dotted", date_str, stem + ".txt")
    if not os.path.exists(p): return []
    try:
        data = json.load(open(p, encoding="utf-8"))
    except Exception:
        return []
    return [(float(e["time"]), e.get("type","click")) for e in data]

SCORE_RE  = re.compile(r"ScoreInfo\(title='(?P<title>[^']*)',\s*section=\d+,\s*"
                       r"homeName='(?P<hn>[^']*)',\s*awayName='(?P<an>[^']*)',\s*"
                       r"homeScore=(?P<hs>\d+),\s*awayScore=(?P<as>\d+)")
TS_RE     = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})\.(\d{3})")

def parse_score_events(appdir, date_str, tz_off):
    """xbot_log MonitorManager/ScoreInfo -> score-change events at wall-clock time."""
    p = os.path.join(appdir, "XbotLog", date_str, f"{date_str}-xbot_log.txt")
    if not os.path.exists(p): return [], None
    events, prev, teams = [], None, None
    with open(p, errors="ignore", encoding="utf-8") as fh:
        for line in fh:
            m = SCORE_RE.search(line)
            if not m: continue
            t = TS_RE.match(line)
            if not t: continue
            hs, as_ = int(m.group("hs")), int(m.group("as"))
            teams = (m.group("hn"), m.group("an"), m.group("title"))
            if prev is None:
                prev = (hs, as_); continue
            if (hs, as_) != prev:
                ep = local_to_epoch(t.group(1), t.group(2), tz_off) + int(t.group(3))/1000.0
                if hs > prev[0]:   kind = "goal_home"
                elif as_ > prev[1]: kind = "goal_away"
                else:              kind = "score_correction"
                events.append(dict(epoch=ep, kind=kind, home=hs, away=as_,
                                   label=f"{m.group('hn')} {hs}-{as_} {m.group('an')}"))
                prev = (hs, as_)
    return events, teams

PAYLOAD_RE = re.compile(r"VideoEditMatchDetailSdkGateway: payload:(MatchAlbumPayload\(.*)")

def parse_app_payload(appdir, date_str):
    """Last MatchAlbumPayload line: the app's own view (ScoreLog = TRUE video positions)."""
    p = os.path.join(appdir, "XbotLog", date_str, f"{date_str}-xbot_log.txt")
    if not os.path.exists(p): return None
    last = None
    with open(p, errors="ignore", encoding="utf-8") as fh:
        for line in fh:
            m = PAYLOAD_RE.search(line)
            if m: last = m.group(1)
    if not last: return None
    out = []
    for chunk in last.split("MatchAlbumMediaAssetPayload(")[1:]:
        dn = re.search(r"displayName='([^']*)'", chunk)
        sl = re.search(r'"ScoreLog":(\[.*?\])\s*,\s*"ManualMark"', chunk, re.S)
        mm = re.search(r'"ManualMark":(\[.*?\])\s*\}', chunk, re.S)
        try:
            out.append(dict(display=dn.group(1) if dn else None,
                            scorelog=json.loads(sl.group(1)) if sl else [],
                            manualmark=json.loads(mm.group(1)) if mm else []))
        except Exception:
            pass
    return out

# ---------------------------------------------------------------- clock OCR

CLOCK_RE = re.compile(r'^(\d{2}):(\d{2}):(\d{2})$')
# burn-in box measured on 3840x2160 output; stored as fractions so it scales
CROP_FRAC = (135/3840.0, 2052/2160.0, 280/3840.0, 80/2160.0)

def read_clock(video, pos, wh):
    from PIL import Image
    w, h = wh
    x, y, cw, ch = (int(CROP_FRAC[0]*w), int(CROP_FRAC[1]*h),
                    int(CROP_FRAC[2]*w), int(CROP_FRAC[3]*h))
    with tempfile.TemporaryDirectory() as td:
        png = os.path.join(td, "f.png")
        sh(["ffmpeg","-v","error","-ss",f"{pos:.3f}","-i",video,"-frames:v","1",
            "-vf",f"crop={cw}:{ch}:{x}:{y}","-y",png])
        if not os.path.exists(png): return None
        im = Image.open(png).convert("L")
        im = im.resize((im.width*5, im.height*5), Image.LANCZOS)
        votes = {}
        for th in (215, 205, 225, 195, 185, 230, 175, 165, 155):
            bw = im.point(lambda p: 0 if p > th else 255)
            bp = os.path.join(td, f"b{th}.png"); bw.save(bp)
            r = sh(["tesseract",bp,"stdout","--psm","7",
                    "-c","tessedit_char_whitelist=0123456789:"])
            m = CLOCK_RE.match(r.stdout.strip().replace(" ",""))
            if m:
                s = int(m.group(1))*3600+int(m.group(2))*60+int(m.group(3))
                votes[s] = votes.get(s,0)+1
                if votes[s] >= 2: return s          # two thresholds agree: done
        if not votes: return None
        return max(votes.items(), key=lambda kv: kv[1])[0]

def sample_offset(video, pos, wh, dur):
    """Verified wall-clock offset at `pos`.

    A single OCR read is not trustworthy (a misread hour silently invents a
    stall).  Read two frames a few seconds apart and require the offsets to
    agree; fall back to a best-of-three.  Returns None if unverifiable.
    """
    def one(t):
        if t >= dur: return None
        s = read_clock(video, t, wh)
        return None if s is None else s - t
    probes = [pos, pos + 3.0, pos + 6.0]
    got = []
    for t in probes:
        o = one(t)
        if o is not None:
            got.append(round(o))
            if len(got) >= 2 and abs(got[-1] - got[-2]) <= 1:
                return got[-1]
    for i in range(len(got)):
        for j in range(i + 1, len(got)):
            if abs(got[i] - got[j]) <= 1:
                return got[j]
    return None

def build_clockmap(video, dur, wh, step=300.0, tol=2, verbose=True):
    """
    Sample the burned-in wall clock and return piecewise segments
    [{pos_start, pos_end, offset}] such that   wall_daysec = pos + offset.
    Detects recording pauses (half time) that make naive
    (press_time - file_start) positions wrong by minutes.

    Offsets can only increase: a pause skips real time, nothing gives it back.
    Any apparent decrease is an OCR error and is discarded.
    """
    samples, pos = [], 0.0
    while pos < dur:
        o = sample_offset(video, pos, wh, dur)
        if o is not None: samples.append((pos, o))
        pos += step
    tail = max(dur - 8.0, 0.0)
    o = sample_offset(video, tail, wh, dur)
    if o is not None: samples.append((tail, o))
    if len(samples) < 2:
        raise SystemExit(f"clock OCR failed on {os.path.basename(video)} "
                         f"(only {len(samples)} verified readings) - "
                         f"is the timestamp overlay enabled?")

    # enforce monotonic non-decreasing offset
    clean, floor = [], None
    for ppos, o in samples:
        if floor is not None and o < floor - tol:
            if verbose: print(f"    discarding impossible reading at {hhmmss(ppos)}")
            continue
        clean.append((ppos, o)); floor = max(floor, o) if floor is not None else o
    samples = clean

    runs, cur = [], [samples[0]]
    for item in samples[1:]:
        if abs(item[1] - cur[-1][1]) <= tol: cur.append(item)
        else: runs.append(cur); cur = [item]
    runs.append(cur)

    segs = []
    for i, run in enumerate(runs):
        o = sorted(x[1] for x in run)[len(run) // 2]
        segs.append(dict(offset=o,
                         pos_start=0.0 if i == 0 else None,
                         pos_end=dur if i == len(runs) - 1 else None))

    for i in range(len(runs) - 1):
        lo, hi = runs[i][-1][0], runs[i + 1][0][0]
        a_off = segs[i]["offset"]
        while hi - lo > 1.0:
            mid = (lo + hi) / 2.0
            o = sample_offset(video, mid, wh, dur)
            if o is None: lo = mid; continue
            if abs(o - a_off) <= tol: lo = mid
            else: hi = mid
        segs[i]["pos_end"] = round(hi, 2)
        segs[i + 1]["pos_start"] = round(hi, 2)
        if verbose:
            print(f"    recording paused at pos {hhmmss(hi)} for "
                  f"{segs[i+1]['offset']-a_off}s (half time)")
    return segs

def wall_to_pos(segs, wall_daysec):
    """Map a wall-clock day-second to a video position; returns (pos, flag)."""
    for s in segs:
        p = wall_daysec - s["offset"]
        if s["pos_start"] - 0.5 <= p <= s["pos_end"] + 0.5:
            return max(0.0, min(p, s["pos_end"])), ""
    # fell inside lost time -> snap to nearest segment edge
    best, flag = None, "DURING_PAUSE"
    for s in segs:
        for edge in (s["pos_start"], s["pos_end"]):
            d = abs((wall_daysec - s["offset"]) - edge)
            if best is None or d < best[0]: best = (d, edge)
    return (best[1] if best else 0.0), flag

# ---------------------------------------------------------------- analyze

def pos_to_wall(segs, pos):
    """Video position -> wall-clock day-second, via the clock map."""
    for sg in segs:
        if sg["pos_start"] - 0.5 <= pos <= sg["pos_end"] + 0.5:
            return pos + sg["offset"]
    return pos + segs[-1]["offset"]

def cmd_analyze(a):
    info = discover(a.day)
    date_str, tz_off = info["date"], info["tz_off"]
    outdir = a.out or os.path.join(a.day, "out")
    os.makedirs(outdir, exist_ok=True)
    day_midnight = local_to_epoch(date_str, "00:00:00", tz_off)

    print(f"day        : {date_str}   (utc offset {tz_off/3600:+.0f}h)")
    print(f"videos     : {len(info['videos'])}")

    score_events, teams = parse_score_events(info["appdir"], date_str, tz_off)
    payload = parse_app_payload(info["appdir"], date_str)
    if teams: print(f"teams      : {teams[0]} vs {teams[1]}  ({teams[2]})")
    print(f"score log  : {len(score_events)} change(s) found in xbot_log")

    cache_path = os.path.join(outdir, "clockmap.json")
    cache = json.load(open(cache_path, encoding="utf-8")) if (os.path.exists(cache_path) and not a.realign) else {}

    rows, timeline = [], []
    rid = 0
    for vi, v in enumerate(info["videos"]):
        dur = ffprobe_dur(v["path"]); wh = ffprobe_wh(v["path"])
        print(f"\n  {v['file']}  {hhmmss(dur)}  {wh[0]}x{wh[1]}")
        if v["file"] in cache:
            segs = cache[v["file"]]; print("    clock map: cached")
        else:
            print("    clock map: OCR scanning burned-in timestamp ...")
            segs = build_clockmap(v["path"], dur, wh, step=a.step)
            cache[v["file"]] = segs
        paused = sum(segs[i+1]["offset"]-segs[i]["offset"] for i in range(len(segs)-1))
        print(f"    segments : {len(segs)}   paused for {paused}s inside this file")

        events = []

        # --- TIME MARKS -------------------------------------------------------
        # Dotted stores a *video-clock* epoch: file_start_epoch + recorded
        # position, i.e. paused time is already excluded.  So the naive
        # subtraction IS the true position in the file.  (Verified 2026-09-13:
        # a mark stored as 13:29:25 sits at 02:22, where the burned-in clock
        # reads 13:35:38 - skewed by exactly the 373 s half-time pause.)
        # Anchor on the Dotted "start" entry, not the filename epoch: the
        # filename carries sub-second precision the marks do not, so
        # subtracting it biases every offset by 0.3-0.9 s.
        dotted = parse_dotted(info["appdir"], date_str, v["stem"])
        anchor = next((ep for ep, typ in dotted if typ == "start"), v["start_epoch"])
        for ep, typ in dotted:
            if typ != "click": continue
            pos = ep - anchor
            events.append(dict(kind="mark", label="time mark",
                               pos=pos, src_daysec=ep - day_midnight))

        # --- GOALS ------------------------------------------------------------
        # MonitorManager logs the scoreboard press at REAL wall-clock time, so
        # these DO need the clock map to become a video position.
        lo, hi = segs[0]["pos_start"], segs[-1]["pos_end"]
        w0, w1 = lo + segs[0]["offset"], hi + segs[-1]["offset"]
        for e in score_events:
            ds = e["epoch"] - day_midnight
            if w0 - 1 <= ds <= w1 + 1:
                pos, _ = wall_to_pos(segs, ds)
                events.append(dict(kind=e["kind"], label=e["label"],
                                   pos=pos, src_daysec=ds))
        # --- MERGE -----------------------------------------------------------
        # The operator marks the goal, then changes the score, so each goal is
        # normally flagged twice. Measured separation over both games: +0 to +3 s,
        # never negative. Fold the pair into one event anchored on the MARK (it
        # is earlier and exact), so nothing appears twice in the reels. A goal
        # with no mark close behind it - e.g. an opponent goal - is left alone.
        if not a.no_merge:
            for g in [e for e in events if e["kind"].startswith("goal")]:
                near = [m for m in events if m["kind"] == "mark"
                        and 0 <= g["pos"] - m["pos"] <= a.merge_window]
                if near:
                    m = max(near, key=lambda x: x["pos"])
                    g["merged_gap"] = round(g["pos"] - m["pos"], 1)
                    g["pos"] = m["pos"]
                    events.remove(m)

        events.sort(key=lambda x: x["pos"])

        for e in events:
            rid += 1
            pos = e["pos"]
            flag = "" if -0.5 <= pos <= dur + 0.5 else "OUTSIDE_FILE"
            pos = max(0.0, min(pos, dur))
            real = pos_to_wall(segs, pos)
            merged = "merged_gap" in e
            # a merged goal is anchored on the mark, so it gets the mark's lead
            lead = a.lead if (merged or not e["kind"].startswith("goal")) else a.goal_lead
            cin, cout = max(0.0, pos - lead), min(dur, pos + a.post)
            rows.append(dict(
                id=rid, include=1, kind=e["kind"], half="", label=e["label"],
                source=v["file"], _vi=vi, _pos=pos,
                video_pos=hhmmss(pos), video_pos_s=round(pos, 2),
                real_time=hhmmss(real), source_time=hhmmss(e["src_daysec"]),
                skew_s=round(real - e["src_daysec"]),
                clip_in=hhmmss(cin),  clip_in_s=round(cin, 2),
                clip_out=hhmmss(cout),clip_out_s=round(cout, 2),
                clip_len_s=round(cout - cin, 2),
                notes=(flag or (f"mark+goal ({e['merged_gap']:g}s apart)" if merged else ""))))

        timeline.append(dict(file=v["file"], path=v["path"], duration=dur,
                             start_epoch=v["start_epoch"], segments=segs))

    # --- half time = the longest pause of the day; the 30-min auto-save is an
    # arbitrary cut and is NOT the half boundary.
    MIN_HT, ht = 120.0, None
    for vi, v in enumerate(info["videos"]):
        segs = cache.get(v["file"]) or []
        for i in range(len(segs) - 1):
            gap = segs[i+1]["offset"] - segs[i]["offset"]
            if gap >= MIN_HT and (ht is None or gap > ht[2]):
                ht = (vi, segs[i]["pos_end"], gap, segs[i]["pos_end"] + segs[i]["offset"])
    for r in rows:
        if ht is None: r["half"] = ""
        elif r["_vi"] < ht[0] or (r["_vi"] == ht[0] and r["_pos"] <= ht[1] + 0.5): r["half"] = "1"
        else: r["half"] = "2"
    if ht:
        print(f"\nhalf time  : whistle at {hhmmss(ht[3])} "
              f"({info['videos'][ht[0]]['file'][:19]} pos {hhmmss(ht[1])}), "
              f"paused {int(ht[2])}s")

    json.dump(cache, open(cache_path, "w", encoding="utf-8"), indent=1)
    json.dump(dict(date=date_str, tz_offset=tz_off, teams=teams, videos=timeline,
                   app_payload=payload, lead=a.lead, goal_lead=a.goal_lead,
                   post=a.post),
              open(os.path.join(outdir, "timeline.json"), "w", encoding="utf-8"), indent=1)

    csv_path = os.path.join(outdir, "marks.csv")
    cols = ["id","include","kind","half","label","source",
            "video_pos","video_pos_s","real_time","source_time","skew_s",
            "clip_in","clip_in_s","clip_out","clip_out_s","clip_len_s","notes"]
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
        for r in rows: w.writerow({k: r[k] for k in cols})

    print(f"\n{len(rows)} events -> {csv_path}")
    worst = max((abs(r["skew_s"]) for r in rows), default=0)
    print(f"largest app-timestamp skew: {worst}s "
          f"(marks only; positions themselves are exact)")
    return 0

def cmd_verify(a):
    """Prove which time base the Dotted marks use, instead of assuming.

    Two possible models for the stored mark timestamp:
      A) VIDEO-CLOCK  - the timestamp pauses with the recording, so
                        pos = epoch - start  is already the true position.
      B) WALL-CLOCK   - the timestamp is real time, so pos must have the
                        accumulated pause subtracted.

    Test: take a mark after a pause, seek to its naive position, OCR the
    burned-in clock.  Under A the clock reads LATER than the stored timestamp
    by exactly the pause; under B it reads the same.
    """
    outdir = a.out or os.path.join(a.day, "out")
    tl = json.load(open(os.path.join(outdir, "timeline.json"), encoding="utf-8"))
    info = discover(a.day)
    day_midnight = local_to_epoch(tl["date"], "00:00:00", tl["tz_offset"])
    for v in info["videos"]:
        segs = next((x["segments"] for x in tl["videos"] if x["file"] == v["file"]), None)
        if not segs or len(segs) < 2: continue
        paused = segs[-1]["offset"] - segs[0]["offset"]
        if paused < 60: continue
        dotted = parse_dotted(info["appdir"], tl["date"], v["stem"])
        anchor = next((ep for ep, t in dotted if t == "start"), v["start_epoch"])
        after = [ep for ep, t in dotted
                 if t == "click" and (ep - anchor) > segs[0]["pos_end"] + 30]
        if not after: continue
        ep = after[len(after)//2]
        pos = ep - anchor
        wh = ffprobe_wh(v["path"])
        print(f"\n{v['file']}   pause {int(paused)}s at pos {hhmmss(segs[0]['pos_end'])}")
        print(f"  mark stored as   {hhmmss(ep - day_midnight)}")
        print(f"  naive position   {hhmmss(pos)}   (epoch - start)")
        obs = sample_offset(v["path"], pos, wh, ffprobe_dur(v["path"]))
        if obs is None:
            print("  burned-in clock unreadable at that position"); continue
        w = obs + pos
        print(f"  clock in frame   {hhmmss(w)}")
        delta = w - (ep - day_midnight)
        print(f"  difference       {int(round(delta)):+d}s  (pause is {int(paused)}s)")
        if abs(delta - paused) <= 5:
            print("  => VIDEO-CLOCK model: marks already exclude paused time.")
            print("     'epoch - start' IS the true video position. No correction.")
        elif abs(delta) <= 5:
            print("  => WALL-CLOCK model: marks are real time.")
            print("     Positions MUST have the accumulated pause subtracted.")
        else:
            print("  => inconclusive - neither model fits; inspect manually.")
        return 0
    print("no pause with a following mark on this day - nothing to test")
    return 0

def cmd_review(a):
    """Flat CSV for eyeballing every event in a spreadsheet."""
    outdir = a.out or os.path.join(a.day, "out")
    tl = json.load(open(os.path.join(outdir, "timeline.json"), encoding="utf-8"))
    rows = list(csv.DictReader(open(a.csv or os.path.join(outdir, "marks.csv"), encoding="utf-8-sig")))
    order = [v["file"] for v in tl["videos"]]
    before = {}
    acc = 0.0
    for v in tl["videos"]:
        before[v["file"]] = acc; acc += v["duration"]
    teams = tl.get("teams") or ("", "", "")
    game = f"{tl['date']} {teams[0]} v {teams[1]}"
    out = os.path.join(outdir, "review.csv")
    cols = ["game","half","type","label","file","video_time","video_sec",
            "clock_time","game_clock","notes"]
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
        for r in sorted(rows, key=lambda x: (order.index(x["source"]),
                                             float(x["video_pos_s"]))):
            gc = before[r["source"]] + float(r["video_pos_s"])
            w.writerow(dict(
                game=game, half=r["half"],
                type="goal" if r["kind"].startswith("goal") else "mark",
                label=r["label"] if r["kind"].startswith("goal") else "",
                file=r["source"],
                video_time=r["video_pos"], video_sec=r["video_pos_s"],
                clock_time=r["real_time"],
                game_clock=f"{int(gc)//60:02d}:{int(gc)%60:02d}",
                notes=r["notes"]))
    print(f"{len(rows)} rows -> {out}")
    return 0

# ---------------------------------------------------------------- rendering

def load_rows(outdir, csv_path=None):
    p = csv_path or os.path.join(outdir,"marks.csv")
    rows = []
    for r in csv.DictReader(open(p, encoding="utf-8-sig")):
        if str(r.get("include","1")).strip() not in ("1","true","yes","y"): continue
        r["clip_in_s"]  = float(r["clip_in_s"])
        r["clip_out_s"] = float(r["clip_out_s"])
        rows.append(r)
    return rows

def src_path(timeline, fname):
    for v in timeline["videos"]:
        if v["file"] == fname: return v["path"]
    raise SystemExit(f"source {fname} not in timeline.json")

def cut(src, tin, tout, dst, mode, height):
    dur = tout - tin
    if mode == "small":
        cmd = ["ffmpeg","-v","error","-ss",f"{max(0,tin-5):.3f}","-i",src,
               "-ss",f"{min(5,tin):.3f}","-t",f"{dur:.3f}",
               "-vf","scale=-2:720","-c:v","libx264","-preset","faster",
               "-crf","26","-pix_fmt","yuv420p","-c:a","aac","-b:a","96k",
               "-movflags","+faststart","-y",dst]
        sh(cmd); return os.path.exists(dst) and os.path.getsize(dst) > 0
    if mode == "copy":
        cmd = ["ffmpeg","-v","error","-ss",f"{tin:.3f}","-i",src,"-t",f"{dur:.3f}",
               "-c","copy","-avoid_negative_ts","make_zero","-y",dst]
    else:
        cmd = ["ffmpeg","-v","error","-ss",f"{max(0,tin-5):.3f}","-i",src,
               "-ss",f"{min(5,tin):.3f}","-t",f"{dur:.3f}",
               "-vf",f"scale=-2:{height}","-c:v","libx264","-preset","veryfast",
               "-crf","20","-pix_fmt","yuv420p","-c:a","aac","-b:a","128k",
               "-movflags","+faststart","-y",dst]
    sh(cmd)
    return os.path.exists(dst) and os.path.getsize(dst) > 0

def concat(parts, dst, reencode, height):
    with tempfile.NamedTemporaryFile("w",suffix=".txt",delete=False) as fh:
        for p in parts:
            ap = os.path.abspath(p)
            fh.write("file '%s'\n" % ap.replace("'", "'\\''"))
        lst = fh.name
    if reencode:
        cmd = ["ffmpeg","-v","error","-f","concat","-safe","0","-i",lst,
               "-vf",f"scale=-2:{height}","-c:v","libx264","-preset","veryfast","-crf","20",
               "-pix_fmt","yuv420p","-c:a","aac","-b:a","128k","-movflags","+faststart","-y",dst]
    else:
        cmd = ["ffmpeg","-v","error","-f","concat","-safe","0","-i",lst,
               "-c","copy","-movflags","+faststart","-y",dst]
    r = sh(cmd); os.unlink(lst)
    if not (os.path.exists(dst) and os.path.getsize(dst) > 0):
        print("    concat FAILED:", (r.stderr or "").strip()[:400])

def build(a, mode):
    outdir = a.out or os.path.join(a.day,"out")
    timeline = json.load(open(os.path.join(outdir,"timeline.json"), encoding="utf-8"))
    rows = load_rows(outdir, a.csv)
    tag = {"copy":"preview","small":"preview720"}.get(mode,"final")
    cdir = os.path.join(outdir,"clips",tag); os.makedirs(cdir, exist_ok=True)
    rdir = os.path.join(outdir,"reels");     os.makedirs(rdir, exist_ok=True)

    # Row ids shift whenever events are added, dropped or merged, which changes
    # every clip filename. Rename a clip whose kind+position still match instead
    # of re-encoding it.
    have = {f for f in os.listdir(cdir) if f.endswith(".mp4")}
    for r in rows:
        want = "%03d_%s_%s.mp4" % (int(r["id"]), r["kind"], r["video_pos"].replace(":", ""))
        if want in have: continue
        suf = "_%s_%s.mp4" % (r["kind"], r["video_pos"].replace(":", ""))
        hit = [f for f in have if f.endswith(suf)]
        if hit:
            os.rename(os.path.join(cdir, hit[0]), os.path.join(cdir, want))
            have.discard(hit[0]); have.add(want)
            print(f"  move {hit[0]} -> {want}")

    made = []
    for r in rows:
        name = f"{int(r['id']):03d}_{r['kind']}_{r['video_pos'].replace(':','')}.mp4"
        dst = os.path.join(cdir,name)
        want = r["clip_out_s"] - r["clip_in_s"]
        if not getattr(a,"force",False) and os.path.exists(dst) and os.path.getsize(dst) > 0:
            try: have = ffprobe_dur(dst)
            except Exception: have = -1
            if abs(have - want) < 1.5:
                print("  skip "+name); made.append((r,dst)); continue
            print("  redo "+name+f" (was {have:.1f}s, want {want:.1f}s)")
        ok = cut(src_path(timeline,r["source"]), r["clip_in_s"], r["clip_out_s"],
                 dst, mode, a.height)
        print(("  ok  " if ok else "  FAIL ")+name)
        if ok: made.append((r,dst))

    def reel(sel, fname):
        parts = [d for r,d in made if sel(r)]
        if not parts: return
        dst = os.path.join(rdir,fname)
        # A reel is a multi-hundred-MB write; skip it when it is already newer
        # than every clip in it, so a resumed run does not redo it each pass.
        if (not getattr(a,"force",False) and os.path.exists(dst)
                and os.path.getsize(dst) > 0
                and os.path.getmtime(dst) >= max(os.path.getmtime(q) for q in parts)):
            print(f"  reel ok  {dst}  ({len(parts)} clips, unchanged)")
            return
        concat(parts, dst, reencode=False, height=a.height)
        print(f"  reel -> {dst}  ({len(parts)} clips)")

    reel(lambda r: True,                          f"highlights_{tag}.mp4")
    reel(lambda r: r["kind"].startswith("goal"),  f"goals_{tag}.mp4")
    print(f"\nclips: {cdir}")

def cmd_preview(a): build(a, "small" if getattr(a,"small",False) else "copy")
def cmd_render(a):  build(a,"encode")

def cmd_full(a):
    """Concatenate the source segments. Video is always stream-copied (native
    resolution, no quality loss); only the audio is touched, and only to pull
    sideline chatter down - default 0.5 (half amplitude, about -6 dB)."""
    outdir = a.out or os.path.join(a.day,"out")
    timeline = json.load(open(os.path.join(outdir,"timeline.json"), encoding="utf-8"))
    os.makedirs(os.path.join(outdir,"reels"), exist_ok=True)
    dst = os.path.join(outdir,"reels",
                       timeline["date"].replace("-","_")+"_full_game.mp4")
    parts = [v["path"] for v in timeline["videos"]]
    with tempfile.TemporaryDirectory() as td:
        tss=[]
        for i,q in enumerate(parts):
            t=os.path.join(td,f"{i:04d}.ts")
            sh(["ffmpeg","-v","error","-i",q,"-c","copy",
                "-bsf:v","h264_mp4toannexb","-f","mpegts","-y",t])
            tss.append(t)
        cmd=["ffmpeg","-v","error","-i","concat:"+"|".join(tss),"-c:v","copy"]
        cmd += (["-c:a","copy"] if a.volume==1.0 else
                ["-af",f"volume={a.volume}","-c:a","aac","-b:a","128k"])
        sh(cmd+["-movflags","+faststart","-y",dst])
    print(f"full game -> {dst}   (audio x{a.volume})")


def cmd_scripts(a):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import winscripts
    outdir = a.out or os.path.join(a.day, "out")
    timeline = json.load(open(os.path.join(outdir, "timeline.json"), encoding="utf-8"))
    rows = load_rows(outdir, a.csv)
    for path, why in winscripts.emit(outdir, timeline, rows, src_path,
                                     a.winroot, a.height):
        print("  " + path)
        print("      " + why)

# ---------------------------------------------------------------- cli

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--day", required=True, help="dated dump folder")
        p.add_argument("--out", help="output folder (default <day>/out)")
        p.add_argument("--height", type=int, default=1080)

    p = sub.add_parser("analyze"); common(p)
    p.add_argument("--lead", type=float, default=12.0, help="seconds before the press")
    p.add_argument("--post", type=float, default=4.0,  help="seconds after the press")
    p.add_argument("--goal-lead", dest="goal_lead", type=float, default=20.0,
                   help="seconds before a scoreboard +1 press (presses lag more than time marks)")
    p.add_argument("--step", type=float, default=300.0, help="clock OCR sampling step")
    p.add_argument("--merge-window", dest="merge_window", type=float, default=60.0,
                   help="fold a goal into the nearest time mark this many seconds before it")
    p.add_argument("--no-merge", dest="no_merge", action="store_true",
                   help="keep marks and goals as separate rows")
    p.add_argument("--realign", action="store_true", help="ignore cached clock map")
    p.set_defaults(fn=cmd_analyze)

    p = sub.add_parser("preview"); common(p); p.add_argument("--csv")
    p.add_argument("--small", action="store_true",
                   help="720p ultrafast preview instead of 4K stream-copy (much smaller files)")
    p.add_argument("--force", action="store_true", help="re-cut clips that already exist")
    p.set_defaults(fn=cmd_preview)
    p = sub.add_parser("render");  common(p); p.add_argument("--csv")
    p.add_argument("--force", action="store_true", help="re-cut clips that already exist")
    p.set_defaults(fn=cmd_render)
    p = sub.add_parser("full");    common(p)
    p.add_argument("--volume", type=float, default=0.5,
                   help="audio gain for the merged game (default 0.5 = -6 dB, to "
                        "keep sideline chatter down); 1.0 leaves audio untouched")
    p.set_defaults(fn=cmd_full)

    p = sub.add_parser("review"); common(p); p.add_argument("--csv")
    p.set_defaults(fn=cmd_review)

    p = sub.add_parser("verify"); common(p)
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("scripts"); common(p); p.add_argument("--csv")
    p.add_argument("--winroot", default=os.environ.get("XBOTGO_WINROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                   help="Windows path that the connected folder maps to")
    p.set_defaults(fn=cmd_scripts)

    p = sub.add_parser("scripts", help="emit Windows .bat + playlist for the heavy jobs")
    common(p); p.add_argument("--csv")
    p.add_argument("--winroot", default=os.environ.get("XBOTGO_WINROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                   help="Windows path the connected folder maps to")
    p.set_defaults(fn=cmd_scripts)

    a = ap.parse_args()
    sys.exit(a.fn(a) or 0)

if __name__ == "__main__":
    main()
