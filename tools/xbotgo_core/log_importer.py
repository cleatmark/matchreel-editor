"""Import review table, timeline, clockmap, and game info from MP4 MatchInfo uuid box and app logs.
No OCR required. Extracts true video seconds, pauses, score events, and manual marks.
"""
from .diag import swallowed as _swallowed
import csv
import datetime
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import dumplayout


def extract_match_info(mp4_path: str) -> Dict[str, Any]:
    """Read the MatchInfo json payload from the uuid box at the end of the MP4 file."""
    with open(mp4_path, "rb") as f:
        f.seek(0, 2)
        n = f.tell()
        f.seek(max(0, n - 60000))
        b = f.read()
    i = b.rfind(b'{"MatchInfo')
    if i < 0:
        raise ValueError(f"No MatchInfo uuid box found at end of {mp4_path}")
    return json.JSONDecoder().raw_decode(b[i:].decode("utf-8", "replace"))[0]


def probe_duration(mp4_path: str) -> float:
    """Return video duration in seconds via ffprobe."""
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp4_path]
    ).decode().strip()
    return float(out)


def format_mmss(s: float) -> str:
    """Format seconds as mm:ss (e.g. 04:01)."""
    return f"{int(round(s)) // 60:02d}:{int(round(s)) % 60:02d}"


def format_gclk(s: float) -> str:
    """Format seconds as game clock m:ss (e.g. 4:01)."""
    return f"{int(round(s)) // 60}:{int(round(s)) % 60:02d}"


def parse_app_pauses(
    video_info: List[Dict[str, Any]],
    pauses_override: Optional[str] = None,
    appdir: Optional[str] = None
) -> Dict[int, List[Tuple[float, float]]]:
    """Parse pause intervals (position_sec, duration_sec) for each video file index."""
    pauses: Dict[int, List[Tuple[float, float]]] = {i: [] for i in range(len(video_info))}
    if pauses_override is not None:
        for p in filter(None, pauses_override.split(",")):
            i, pos, d = p.split(":")
            pauses[int(i)].append((float(pos), float(d)))
    elif appdir and os.path.exists(appdir):
        day_logs = [
            os.path.join(dp, f)
            for dp, _, fs in os.walk(os.path.join(appdir, "XbotLog"))
            for f in fs
            if f.endswith("-xbot_log.txt")
        ]
        for lg in day_logs:
            with open(lg, errors="replace", encoding="utf-8") as f:
                for line in f:
                    m = re.search(r"resumeRecord-currentPauseTime:(\d+),\s*pauseStartTimeMillis(\d+)", line)
                    if not m:
                        continue
                    d, ps = int(m.group(1)) / 1000.0, int(m.group(2)) / 1000.0
                    for i, v in enumerate(video_info):
                        if (
                            v["start"] <= ps <= v["start"] + v["D"] + sum(x[1] for x in pauses[i]) + 5
                            and (i + 1 == len(video_info) or video_info[i + 1]["start"] > ps)
                        ):
                            pauses[i].append((round(ps - v["start"], 3), d))
                            break
    for i in pauses:
        pauses[i].sort()
    return pauses


def build_review_from_log(
    day: str,
    out_csv: Optional[str] = None,
    files: Optional[str] = None,
    pauses_override: Optional[str] = None,
    home: Optional[str] = None,
    tz_str: str = "America/New_York",
    lead: float = 12.0,
    post: float = 4.0,
    merge_window: float = 60.0,
    min_half_pause: float = 120.0,
    root_dir: Optional[str] = None
) -> Dict[str, Any]:
    """Generate review.csv, timeline.json, clockmap.json, and game_info.json from MP4 boxes and logs.
    
    Returns:
        dict containing review rows, output paths, pause info, and score summary.
    """
    base_root = root_dir or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # project root (file lives in tools/xbotgo_core/)
    from . import app_config
    _cfg = app_config.load(base_root)
    home = home or _cfg["team_name"]
    tz = ZoneInfo(tz_str)
    file_list = [f for f in (files or "").split(",") if f]
    vdir, found_files = dumplayout.list_videos(day, file_list)
    appdir = dumplayout.find_appdir(day)

    info = []
    for fn in found_files:
        m = re.match(r"^(\d{4}-\d{2}-\d{2})-(\d{2}-\d{2}-\d{2})_(\d{13})\.mp4$", fn)
        vp = os.path.join(vdir, fn)
        info.append({
            "file": fn,
            "path": vp,
            "date": m.group(1) if m else day,
            "start": (int(m.group(3)) / 1000.0) if m else 0.0,
            "D": probe_duration(vp)
        })

    if not out_csv:
        out_csv = os.path.join(base_root, "out", info[0]["date"], "review.csv")

    outdir = os.path.dirname(os.path.abspath(out_csv))
    os.makedirs(outdir, exist_ok=True)

    pauses = parse_app_pauses(info, pauses_override=pauses_override, appdir=appdir)
    allp = [(i, pos, d) for i, ps in pauses.items() for pos, d in ps]
    half = max(allp, key=lambda x: x[2]) if allp and max(x[2] for x in allp) >= min_half_pause else None

    def wall_off(file_idx: int, pos: float) -> float:
        return sum(d for p, d in pauses[file_idx] if pos >= p)

    rows = []
    carried = (0, 0)
    cum = 0.0
    goal_summary = []
    final = (0, 0)
    ht = (0, 0)
    home_name = home
    opp_name = _cfg["guest_name"]

    for i, v in enumerate(info):
        j = extract_match_info(v["path"])
        sl = j.get("ScoreLog", [])
        if sl:
            home_name = sl[0].get("HomeInfo", {}).get("TeamName") or home
            opp_name = sl[0].get("AwayInfo", {}).get("TeamName") or opp_name
        marks = sorted(m["time"] for m in j.get("ManualMark", []) if m.get("type") != "start" and m.get("time", 0) > 0)
        seq = [
            (e.get("HomeInfo", {}).get("Score", 0), e.get("AwayInfo", {}).get("Score", 0), e.get("Time", 0))
            for e in sl
        ]
        goals = []
        prev = carried
        for k, (h_sc, aw_sc, t) in enumerate(seq):
            if k == 0:
                continue
            nxt = seq[k + 1] if k + 1 < len(seq) else None
            if nxt and nxt[2] - t <= 5 and nxt[0] + nxt[1] < h_sc + aw_sc:
                continue
            if i > 0 and t <= 3 and h_sc <= carried[0] and aw_sc <= carried[1]:
                prev = (h_sc, aw_sc)
                continue
            if h_sc + aw_sc > sum(prev):
                goals.append((h_sc, aw_sc, t))
            prev = (h_sc, aw_sc)
        carried = prev
        final = prev
        used = set()
        grow = {}
        extra = []
        for h_sc, aw_sc, t in goals:
            c = [(abs(t - m), m) for m in marks if m <= t + 5 and t - m <= merge_window and m not in used]
            if c:
                m = min(c)[1]
                used.add(m)
                grow[m] = (h_sc, aw_sc, t)
            else:
                extra.append((t, (h_sc, aw_sc, t)))

        ev = sorted([(m, grow.get(m)) for m in marks] + extra, key=lambda x: x[0])
        for m, g in ev:
            wall = datetime.datetime.fromtimestamp(v["start"] + m + wall_off(i, m), tz)
            after_half = half is not None and (i > half[0] or (i == half[0] and m >= half[1]))
            hf = 2 if after_half else 1
            typ = "goal" if g else "mark"
            label = f"{home_name} {g[0]}-{g[1]} {opp_name}" if g else ""
            note = ("mark+goal" if m in grow else "goal (no mark near it)") if g else ""
            rows.append([
                f"{v['date']} {home_name} v {opp_name}",
                hf,
                typ,
                label,
                v["file"],
                format_mmss(m),
                int(round(m)),
                wall.strftime("%H:%M:%S"),
                format_gclk(cum + m),
                note,
                format_mmss(max(0, m - lead)),
                format_mmss(m),
                format_mmss(min(v["D"], m + post)),
                "", "", ""
            ])
        if half and half[0] == i:
            ht = max([(h_sc, aw_sc) for h_sc, aw_sc, t in seq if t <= half[1]] or [(0, 0)], key=lambda x: x[0] + x[1])
        goal_summary.append((v["file"], round(v["D"], 1), len(marks), [(g[0], g[1], g[2]) for g in goals]))
        cum += v["D"]

    hdr = "game,half,type,label,file,video_time,video_sec,clock_time,game_clock,notes,action_start,event,action_end,player,instructions,clip".split(",")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(hdr)
        w.writerows(rows)

    # ---- timeline.json / clockmap.json / game_info.json
    tzoff = int(datetime.datetime.fromtimestamp(info[0]["start"], tz).utcoffset().total_seconds())
    tl_videos = []
    clock = {}
    for i, v in enumerate(info):
        sod0 = datetime.datetime.fromtimestamp(v["start"], tz)
        sod0 = sod0.hour * 3600 + sod0.minute * 60 + sod0.second
        segs = []
        pos0 = 0.0
        off = sod0
        for pos, d in pauses[i]:
            segs.append({"offset": off, "pos_start": round(pos0, 3), "pos_end": round(pos, 3)})
            off += int(round(d))
            pos0 = pos
        segs.append({"offset": off, "pos_start": round(pos0, 3), "pos_end": round(v["D"], 4)})
        tl_videos.append({
            "file": v["file"],
            "path": os.path.relpath(v["path"], base_root).replace("\\", "/"),
            "duration": round(v["D"], 4),
            "start_epoch": v["start"],
            "segments": segs
        })
        clock[v["file"]] = segs

    tl_path = os.path.join(outdir, "timeline.json")
    with open(tl_path, "w", encoding="utf-8") as f:
        json.dump({
            "date": os.path.basename(outdir),
            "tz_offset": tzoff,
            "teams": [home_name, opp_name, _cfg["league"]],
            "videos": tl_videos,
            "app_payload": None,
            "lead": lead,
            "goal_lead": 20.0,
            "post": post
        }, f, indent=1)

    cm_path = os.path.join(outdir, "clockmap.json")
    with open(cm_path, "w", encoding="utf-8") as f:
        json.dump(clock, f)

    d0 = datetime.date.fromisoformat(info[0]["date"])
    gi_path = os.path.join(outdir, "game_info.json")
    if not os.path.exists(gi_path):
        def_league = _cfg["league"]
        def_league_logo = _cfg["league_logo"]
        def_home_logo = _cfg["team_logo"]
        def_home = _cfg["team_name"] or home_name
        with open(gi_path, "w", encoding="utf-8") as f:
            json.dump({
                "league": def_league,
                "league_logo": def_league_logo,
                "home": def_home,
                "home_logo": def_home_logo,
                "date": f"{d0:%B} {d0.day}, {d0.year}",
                "opponent": opp_name,
                "away_logo": None,
                "score": f"{final[0]}-{final[1]}",
                "halftime_score": f"{ht[0]}-{ht[1]}"
            }, f, indent=1)

    return {
        "csv_path": out_csv,
        "timeline_path": tl_path,
        "clockmap_path": cm_path,
        "game_info_path": gi_path,
        "rows": rows,
        "pauses": pauses,
        "half": half,
        "ht_score": ht,
        "final_score": final,
        "goal_summary": goal_summary
    }
