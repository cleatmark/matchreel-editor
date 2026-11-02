#!/usr/bin/env python3
"""Build the fully synthetic test project the unit tests and the guide screenshots run on.

Nothing here is read from disk: the "games" are small event sequences below, and every CSV / JSON / crest file is generated into
the destination folder at test time (python tools/editor/make_test_root.py). No game data is stored in the repository.

  Teams "Home FC" / "Guest FC", players "Player N", leagues "League A" / "League B", generated placeholder crests.

Layout written to <dst> (the same layout a real project has):
  config/game_defaults.json, shared/team_logos/*, out/reviewed/roster.csv, out/reviewed/<game>_reviewed.csv,
  out/<game>/[work/]review.csv, game_info.json, and for the reference game timeline.json, clockmap.json, zoom_state.json.
"""
import argparse
import csv
import datetime
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.join(os.path.dirname(HERE), "pipeline")

HOME, GUEST = "Home FC", "Guest FC"
JERSEYS = [1, 3, 4, 7, 8, 9, 10, 11, 13, 15, 33]
FEATURED = ["7"]
PLAYER_CYCLE = ["9", "op", "", "3", "7", "", "13", "op"]
INSTR_CYCLE = ["", "zoom", "", "skip", "zoom"]

# --- the reference game: full review + reviewed + zoom replays ------------------------------------------------------------
REF_ID = "2026-03-29"
REF_FILE = "2026-03-29-10-41-31_1774780891448.mp4"
REF_LEAGUE = "League A"
REF_DURATION, REF_SPLIT, REF_GAP = 3047.4001, 1531.644, 286   # video length, half-2 position in the file, seconds of pause
# (half, type, video_sec, reviewed start, reviewed event, reviewed end, player, instructions)
REF_ROWS = [
    ("1", "mark", 163, "02:37", "02:42", "02:44", "", ""),
    ("1", "mark", 186, "02:54", "03:06", "03:10", "", "skip"),
    ("1", "mark", 279, "04:27", "04:36", "04:38", "8", ""),
    ("1", "mark", 331, "05:21", "05:27", "05:29", "7", "zoom"),
    ("1", "mark", 386, "06:19", "06:22", "06:25", "11", "zoom"),
    ("1", "goal", 528, "08:34", "08:45", "08:48", "7,10", "zoom"),
    ("1", "mark", 586, "09:33", "09:43", "09:45", "13", "zoom"),
    ("1", "goal", 1090, "17:58", "18:07", "18:11", "10", "zoom"),
    ("1", "mark", 1237, "20:21", "20:25", "20:28", "1", "zoom"),
    ("1", "goal", 1269, "21:04", "21:07", "21:10", "", "zoom"),
    ("1", "mark", 1385, "22:53", "23:03", "23:05", "15", "zoom"),
    ("1", "mark", 1427, "23:37", "23:45", "23:48", "7", "zoom"),
    ("2", "mark", 1838, "30:25", "30:30", "30:35", "11", "zoom"),
    ("2", "goal", 1960, "32:25", "32:36", "32:40", "10", "zoom"),
    ("2", "goal", 2115, "35:02", "35:09", "35:13", "", "zoom"),
    ("2", "mark", 2165, "35:49", "35:59", "36:01", "10", "zoom"),
    ("2", "mark", 2238, "37:06", "37:10", "37:13", "11", ""),
    ("2", "goal", 2251, "37:22", "37:27", "37:31", "88", "zoom"),
    ("2", "mark", 2367, "39:19", "39:22", "39:25", "10", ""),
    ("2", "mark", 2394, "39:45", "39:49", "39:50", "11", ""),
    ("2", "mark", 2461, "40:52", "40:54", "40:59", "1", ""),
    ("2", "mark", 2549, "42:17", "42:25", "42:27", "13", ""),
    ("2", "mark", 2622, "43:29", "43:37", "43:39", "7", "zoom"),
    ("2", "mark", 2811, "46:37", "46:48", "46:55", "13", ""),
    ("2", "mark", 2967, "49:14", "49:22", "49:27", "7", "zoom"),
]
AWAY_GOALS = {2, 4}          # goals (0-based among the goal rows) scored by the guest team
# zoom replays: (token, row n, event, start, dur, crop, crop_w, pan [x, y, t, dur] or None, history entries)
REF_REPLAYS = [
    ("mark_000527", 3, 327, 324.5, 4.5, [2180, 300], None, [2500.0, 300.0, 8.5, 1.0], 4),
    ("mark_000622", 4, 382, 379.5, 5.5, [1670, 660], None, [2150.0, 180.0, 3.5, 1.5], 5),
    ("mark_000943", 6, 583, 580.5, 4.5, [432, 408], 1536, None, 5),
    ("goal_001807", 7, 1087, 1084.5, 4.5, [1940, 300], None, [3800.0, 300.0, 5.5, 3.0], 12),
    ("mark_002025", 8, 1225, 1222.5, 4.5, [2480, 450], None, None, 3),
    ("goal_002107", 9, 1267, 1264.5, 4.5, [2560, 330], None, [2080.0, 330.0, 4.5, 9.0], 6),
    ("mark_002303", 10, 1383, 1380.5, 4.5, [2000, 330], None, None, 3),
    ("mark_002345", 11, 1425, 1422.5, 4.5, [1700, 270], None, [1540.0, 270.0, 4.5, 9.0], 4),
    ("mark_003030", 12, 1830, 1827.5, 5.5, [140, 480], None, [0.0, 480.0, 9.0, 4.0], 4),
    ("goal_003236", 13, 1956, 1953.5, 5.0, [650, 390], None, [810.0, 390.0, 5.0, 10.0], 4),
    ("goal_003509", 14, 2109, 2106.5, 4.5, [660, 390], None, [-1260.0, 390.0, 5.0, 4.0], 6),
    ("mark_003559", 15, 2159, 2156.5, 4.5, [1370, 360], None, None, 3),
    ("goal_003727", 17, 2247, 2244.5, 4.5, [200, 450], None, [680.0, 450.0, 4.5, 9.0], 6),
    ("mark_004337", 22, 2617, 2611.5, 8.0, [1340, 390], None, None, 5),
    ("mark_004922", 24, 2962, 2957.0, 7.0, [1280, 300], None, [1760.0, 300.0, 7.0, 14.0], 5),
    ("goal_000845", 5, 525, 522.5, 4.5, [1220, 240], None, None, 3),
]

# --- the small games: only the event sequence is stored (<half><m|g><video second>) -------------------------------------
# fmt: legacy = 10 columns (old format) | video = *_video columns | new = current review format (+ reviewed copy when reviewed=True)
SMALL = {
    "2026-03-07": dict(file="2026-03-07-11-02-20_1772881340099.mp4", fmt="legacy", where="work", info=False, league="League B",
                       seq="1m258 1g320 1m838 1m905 1g1137 1m1263 1m1289 1g1324 1m1403 1m1603 1g1643 1m1709 1m1782 2m134 2g357 2m544 2m731 2m815 2g1101"),
    "2026-03-08": dict(file="2026-03-08-16-33-10_1772987590115.mp4", fmt="legacy", where="work", info=False, league="League B",
                       seq="1m55 1m161 1g201 1m237 1m683 1g827 1m975 1g1359 2g160 2m383 2m439 2m520 2m721 2m752 2m1320 2m1367 2m1402 2m1539"),
    "2026-03-14-g1": dict(file="2026-03-14-11-47-10_1773488830032.mp4", fmt="video", where="work", info=True, league="League B",
                          seq="1m58 1g241 1m310 1m436 1m602 1m643 1g759 1m812 1g870 1m997 1m1243 2m1744 2g16 2m71 2g183 2m376 2m409 2g483 2m700"),
    "2026-03-14-g2": dict(file="2026-03-14-13-53-01_1773496381650.mp4", fmt="video", where="work", info=False, league="League B",
                          seq="1m102 1g301 1g688 1g855 1m919 1g957 1m1055 1m1239 2m1560 2g144 2g229 2g352 2g545 2g760 2m992 2m1100 2m1119 2g1218 2m1270 2m1378 2m1468"),
    "2026-03-21": dict(file="2026-03-21-11-04-59_1774091099013.mp4", fmt="new", where="", info=True, league="League B", reviewed=True,
                       seq="1m271 1m324 1m569 1m937 1g1101 1m1164 1g1189 1m1217 1m1282 1m1508 1m1645 1g1745 1g1789 2m1995 2g2257 2m2517 2g2629 2g2821 2m2968"),
    "2026-03-22": dict(file="2026-03-22-07-14-31_1774163671969.mp4", fmt="new", where="", info=False, league="League A", reviewed=True,
                       seq="1m373 1m419 1m659 1g839 1m1515 1m1703 2m1898 2m2172 2m2260 2g2389 2g2459 2m2527 2m2717 2m2814 2m2933 2m3046 2g3427 2m3468 2g3560 2g3683 2m3719"),
}

CRLF = "\r\n"
H_REVIEW = "game,half,type,label,file,video_time,video_sec,clock_time,game_clock,notes,action_start,event,action_end,player,instructions,clip"
H_REVIEWED = "game,half,type,label,file,video_time,video_sec,clock_time,game_clock,notes,action_start,event,action_end,player,instructions"
H_LEGACY = "game,half,type,label,file,video_time,video_sec,clock_time,game_clock,notes"
H_VIDEO = "game,half,type,label,file,video_time,video_sec,clock_time,game_clock,notes,action_start_video,event_video,action_end_video,player,skip"


# --- small helpers --------------------------------------------------------------------------------------------------------
def start_sec(file_name):
    """Seconds since local midnight of the recording start, read from the file name (YYYY-MM-DD-HH-MM-SS_<epoch ms>.mp4)."""
    p = file_name.split("_")[0].split("-")
    return int(p[3]) * 3600 + int(p[4]) * 60 + int(p[5])


def epoch_of(file_name):
    return int(file_name.split("_")[1].split(".")[0]) / 1000.0


def mmss(s, pad=True):
    s = int(s)
    return f"{s // 60:02d}:{s % 60:02d}" if pad else f"{s // 60}:{s % 60:02d}"


def hmmss(s):
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def hhmmss(s):
    s = int(s)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def parse_mmss(t):
    m, s = t.split(":")
    return int(m) * 60 + int(s)


def long_date(game_id):
    d = datetime.datetime.strptime(game_id[:10], "%Y-%m-%d")
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def mdy(game_id):
    d = datetime.datetime.strptime(game_id[:10], "%Y-%m-%d")
    return d.strftime("%m-%d-%y")


def parse_seq(seq):
    out = []
    for tok in seq.split():
        out.append((tok[0], "goal" if tok[1] == "g" else "mark", int(tok[2:])))
    return out


def csv_text(header, rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator=CRLF)
    w.writerow(header.split(","))
    w.writerows(rows)
    return buf.getvalue()


def sides(n_goals, idx):
    """Deterministic home/away pattern for the goals of one game (True = guest scored)."""
    return [(k * 5 + idx) % 3 == 1 for k in range(n_goals)]


def running_labels(rows, away):
    """Per goal row: 'Home FC a-b Guest FC'. Returns (labels per row index, final (h, a), halftime (h, a))."""
    h = a = k = 0
    ht = (0, 0)
    labels = {}
    for i, r in enumerate(rows):
        if r[1] != "goal":
            continue
        if away[k]:
            a += 1
        else:
            h += 1
        k += 1
        labels[i] = f"{HOME} {h}-{a} {GUEST}"
        if r[0] == "1":
            ht = (h, a)
    return labels, (h, a), ht


def write(dst, rel, text, bom=False):
    p = os.path.join(dst, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
        f.write(text)


def write_json(dst, rel, obj, indent=None):
    txt = json.dumps(obj, indent=indent, ensure_ascii=False)
    write(dst, rel, txt + ("\n" if indent else ""))


def game_info(game_id, league, score, ht):
    return {
        "league_logo": f"shared/team_logos/{'league_a' if league == 'League A' else 'league_b'}.png",
        "home": HOME, "home_logo": "shared/team_logos/home_fc.png",
        "date": long_date(game_id), "opponent": GUEST, "away_logo": "shared/team_logos/guest_fc.png",
        "score": f"{score[0]}-{score[1]}", "halftime_score": f"{ht[0]}-{ht[1]}", "league": league,
    }


# --- the reference game ---------------------------------------------------------------------------------------------------
def build_reference(dst):
    gid, f = REF_ID, REF_FILE
    s0 = start_sec(f)
    name = f"{gid} {HOME} v {GUEST}"
    goal_idx = [i for i, r in enumerate(REF_ROWS) if r[1] == "goal"]
    away = [k in AWAY_GOALS for k in range(len(goal_idx))]
    labels, final, ht = running_labels(REF_ROWS, away)

    def clock(r):
        return s0 + r[2] + (REF_GAP if r[0] == "2" else 0)

    review, reviewed = [], []
    for i, r in enumerate(REF_ROWS):
        ev = r[2]
        base = [name, r[0], r[1]]
        mid = [f, mmss(ev), ev, hhmmss(clock(r)), mmss(ev, pad=False)]
        note = "mark+goal" if r[1] == "goal" else ""
        review.append(base + [""] + mid + [note, mmss(ev - 12), mmss(ev), mmss(ev + 4), "", "", ""])
        is_away = r[1] == "goal" and away[goal_idx.index(i)]
        player = "" if is_away else r[6]
        reviewed.append(base + [labels.get(i, "")] + mid + [note, r[3], r[4], r[5], player, r[7]])
    write(dst, f"out/{gid}/work/review.csv", csv_text(H_REVIEW, review))
    write(dst, f"out/reviewed/{gid}_reviewed.csv", csv_text(H_REVIEWED, reviewed))
    write_json(dst, f"out/{gid}/work/game_info.json", game_info(gid, REF_LEAGUE, final, ht), indent=1)
    path = f"{mdy(gid)}/Videos/{f}"
    segs = [{"offset": s0, "pos_start": 0.0, "pos_end": REF_SPLIT}, {"offset": s0 + REF_GAP, "pos_start": REF_SPLIT, "pos_end": REF_DURATION}]
    write_json(dst, f"out/{gid}/work/clockmap.json", {f: segs})
    write_json(dst, f"out/{gid}/work/timeline.json", {
        "date": gid, "tz_offset": 0, "teams": [HOME, GUEST, "League B"],
        "videos": [{"file": f, "path": path, "duration": REF_DURATION, "start_epoch": epoch_of(f), "segments": segs}],
        "app_payload": None, "lead": 12, "goal_lead": 20.0, "post": 4}, indent=1)
    replays = {}
    for tok, n, ev, st, dur, crop, cw, pan, nh in REF_REPLAYS:
        key = f"{path}|{ev}|{st}|{dur}|{crop}|2160|stab5" + (f"|cw{cw}" if cw else "") + (f"|pan{pan}" if pan else "")
        rp = {"n": n, "event": ev, "file": f, "path": path, "crop": crop}
        if cw:
            rp["crop_w"] = cw
        rp.update({"start": st, "dur": dur, "cut_start": 0.0, "cut_end": 0.0, "master_key": key, "final_key": key + "|0.0|0.0",
                   "history": [{"t": f"{gid} {10 + k // 60:02d}:{k % 60:02d}:00", "window": [st, dur], "crop": crop, "cut": [0.0, 0.0], "len": 9.0}
                               for k in range(nh)]})
        if pan:
            rp["pan"] = pan
        replays[tok] = rp
    write_json(dst, f"out/{gid}/work/zoom_state.json", {"version": 1, "replays": replays, "removed": {}}, indent=1)


# --- the small games ------------------------------------------------------------------------------------------------------
def build_small(dst, idx, gid, spec):
    f = spec["file"]
    s0 = start_sec(f)
    name = f"{gid[:10]} {HOME} v {GUEST}"
    ev = parse_seq(spec["seq"])
    goals = [i for i, e in enumerate(ev) if e[1] == "goal"]
    away = sides(len(goals), idx)
    labels, final, ht = running_labels([(e[0], e[1]) for e in ev], away)
    rows = []
    for i, (half, typ, sec) in enumerate(ev):
        clock = hhmmss(s0 + sec)
        label = labels.get(i, "")
        if spec["fmt"] == "legacy":
            note = "mark+goal (3s apart)" if typ == "goal" else ""
            rows.append([name, half, typ, label, f, hhmmss(sec), f"{sec}.0", clock, mmss(sec), note])
        elif spec["fmt"] == "video":
            note = "mark+goal (3s apart)" if typ == "goal" else ""
            rows.append([name, half, typ, label, f, hmmss(sec), sec, clock, "'" + mmss(sec, pad=False), note,
                         hmmss(sec - 12), hmmss(sec), hmmss(sec + 4), "", ""])
        else:
            note = "mark+goal" if typ == "goal" else ""
            rows.append([name, half, typ, "", f, mmss(sec), sec, clock, mmss(sec, pad=False), note, mmss(sec - 12), mmss(sec), mmss(sec + 4), "", "", ""])
    header = {"legacy": H_LEGACY, "video": H_VIDEO, "new": H_REVIEW}[spec["fmt"]]
    base = f"out/{gid}/work" if spec["where"] == "work" else f"out/{gid}"
    write(dst, f"{base}/review.csv", csv_text(header, rows))
    if spec.get("reviewed"):
        out = []
        for i, (half, typ, sec) in enumerate(ev):
            mid = [f, mmss(sec), sec, hhmmss(s0 + sec), mmss(sec, pad=False)]
            note = "mark+goal" if typ == "goal" else ""
            player = PLAYER_CYCLE[i % len(PLAYER_CYCLE)]
            if typ == "goal" and away[goals.index(i)]:
                player = ""
            out.append([name, half, typ, labels.get(i, "")] + mid + [note, mmss(sec - 6), mmss(sec - 3), mmss(sec - 1), player, INSTR_CYCLE[i % len(INSTR_CYCLE)]])
        write(dst, f"out/reviewed/{gid}_reviewed.csv", csv_text(H_REVIEWED, out))
    if spec["info"]:
        write_json(dst, f"{base}/game_info.json", game_info(gid, spec["league"], final, ht), indent=1)
    return final


def build(dst):
    """Write the whole synthetic project into dst (created if needed; existing files are overwritten)."""
    os.makedirs(dst, exist_ok=True)
    write_json(dst, "config/game_defaults.json", {
        "team_name": HOME, "is_home": True, "team_logo": "shared/team_logos/home_fc.png",
        "leagues": [{"name": "League A", "logo": "shared/team_logos/league_a.png"}, {"name": "League B", "logo": "shared/team_logos/league_b.png"}],
        "league": "League A", "league_logo": "shared/team_logos/league_a.png", "featured_players": FEATURED, "sheet_id": "", "guest_name": GUEST}, indent=2)
    roster = [[f"Player {n}", n, f"P{n}", f"parent{n}@example.com"] for n in JERSEYS]
    write(dst, "out/reviewed/roster.csv", csv_text("name,no,short_name,contact", roster), bom=True)
    subprocess.check_call([sys.executable, os.path.join(PIPELINE, "make_placeholder_logos.py"), "--out", os.path.join(dst, "shared", "team_logos")],
                          stdout=subprocess.DEVNULL)
    build_reference(dst)
    for i, (gid, spec) in enumerate(SMALL.items()):
        build_small(dst, i, gid, spec)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dst", required=True)
    a = ap.parse_args()
    build(os.path.abspath(a.dst))
    print("synthetic project written to", os.path.abspath(a.dst))


if __name__ == "__main__":
    main()
