#!/usr/bin/env python3
"""Final (4K) production for one game, resumable stage by stage. Run on the PC (no 3-minute cap) or loop on the device.

  python tools\\pipeline\\make_reels.py --out out\\2026-03-14-g1 --stage all
  stages: cards | clips | replays | reels | all      (all = cards, clips, replays, reels, #11 reel)
  --player 11    player number for the per-player reel (default 11; skipped with a message when no rows)
  --seed N       music seed (default 7; the bed is a RANDOM track, looped as needed)

Needs out\\<game>\\game_info.json:
  {"opponent":"Guest FC","away_logo":"shared/team_logos/guest_fc.png","league":"League A","league_logo":"shared/team_logos/league_a.png",
   "home":"Home FC","home_logo":"shared/team_logos/home_fc.png","score":"6-0","halftime_score":"3-0","date":"March 14, 2026"}
Rules baked in: clips cut at original sound 0.4, startend bounds +0.5 s; replay right after its clip; half-time card between halves;
cheers only on home-team goals (normal clip); the featured-player reel has no half-time card; outputs probed against the sum of the pieces.
"""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils\ on PATH
import argparse, csv, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xbotgo_core.xbl import Game, sh, probe_dur, is_zoom, PY
from xbotgo_core.procs import run_streaming

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VOL = "0.4"


def run(cmd, **kw):
    """Run a helper program and echo its output live (so the cmd window shows what is happening); exit on failure."""
    r = run_streaming(cmd)
    if r.returncode:
        sys.exit(f"FAILED: {' '.join(map(str, cmd))[:200]}")
    return r


def info(g):
    p = os.path.join(g.out, "game_info.json")
    if not os.path.exists(p) and os.path.exists(os.path.join(g.out, "work", "game_info.json")):
        p = os.path.join(g.out, "work", "game_info.json")
    return json.load(open(p, encoding="utf-8"))


def player_line(g, no=None):
    """'<Full Name> - <number>' from the roster (full name, number)."""
    no = no or get_default_featured_player()
    for r in csv.DictReader(open(g.roster_path, newline="", encoding="utf-8-sig")):
        r_no = str(r.get("no") or r.get("No") or "").strip()
        if r_no == str(no):
            name = (r.get('name') or r.get('Player') or r.get('short_name') or r.get('Short_Name') or '').strip()
            return f"{name} - {no}"
    return ""


def stage_player_intro(g, no=None, only=True):
    """player-reel intro card (000_intro_p<no>.mp4: normal intro + 'Name - number'); made on demand."""
    i = info(g); pl = player_line(g, no)
    if not pl: return
    run([PY, "tools/pipeline/title_cards.py", "--out", os.path.join(g.out, "clips", "cards"), "--league", i["league_logo"],
         "--home", i["home"], "--home-logo", i["home_logo"], "--away", i["opponent"], "--away-logo", i["away_logo"],
         "--score", i["score"], "--date", i["date"], "--player-line", pl, "--player-tag", f"p{no}"] + (["--only-player-intro"] if only else []))


def stage_cards(g):
    i = info(g)
    run([PY, "tools/pipeline/title_cards.py", "--out", os.path.join(g.out, "clips", "cards"), "--league", i["league_logo"],
         "--home", i["home"], "--home-logo", i["home_logo"], "--away", i["opponent"], "--away-logo", i["away_logo"],
         "--score", i["score"], "--halftime-score", i["halftime_score"], "--date", i["date"], "--fullgame",
         "--player-line", player_line(g), "--player-tag", "p11"])


def stage_clips(g):
    cmd = [PY, "tools/pipeline/cut_reviewed.py", "--csv", g.csv, "--out", g.out, "--roster", g.roster_path, "--bounds", "startend",
           "--height", "0", "--volume", VOL, "--preset", "veryfast", "--crf", "23", "--clipdir", "reviewed4k", "--no-reels", "--no-players"]
    run(cmd)


def stage_replays(g):
    run([PY, "tools/pipeline/zoom_edit.py", "render", "--out", g.out, "--height", "2160", "--budget", "100000"])


def ours_goals(g):
    """clip basenames of home-team goals (home score went up; unlabeled goal rows count unless player starts with oppo)."""
    home = 0; out = set(); jobs = {id(j["row"]): j for j in g.jobs()}
    for r in csv.DictReader(open(g.csv, newline="", encoding="utf-8-sig")):
        m = re.search(r"(\d+)\s*-\s*(\d+)", r.get("label", "") or "")
        if r.get("type") == "goal" and m:
            h = int(m.group(1)); ours = h > home; home = h
        else:
            ours = r.get("type") == "goal" and not (r.get("player") or "").strip().lower().startswith("oppo")
        if ours:
            for j in jobs.values():
                if j["row"].get("video_sec") == r.get("video_sec") and j["row"].get("type") == r.get("type") and j["row"].get("file") == r.get("file"):
                    out.add(j["clip"])
    return out


def load_extras(g):
    """out/<game>/extras.json (optional, main highlights reel only): announcer segments, goal sound overlays, music pauses."""
    p = os.path.join(g.out, "extras.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def build_list(g, player=None, halftime=True, extras=None):
    cards = os.path.join(g.out, "clips", "cards"); cdir = os.path.join(g.out, "clips", "reviewed4k")
    intro = os.path.join(cards, "000_intro.mp4")
    if player:
        ip = os.path.join(cards, f"000_intro_p{player}.mp4")
        if not os.path.exists(ip): stage_player_intro(g, player)
        if os.path.exists(ip): intro = ip
    seq = [intro]; cheers = []; ht_done = not halftime; pieces = 0
    ours = ours_goals(g)
    for j in g.jobs():
        if player and str(player) not in j.get("players", [j.get("player", "")]):
            continue          # "11,1": every listed number gets the clip in their reel
        if not ht_done and (j["row"].get("half") or "").strip() == "2":
            seq.append(os.path.join(cards, "500_halftime.mp4")); ht_done = True
        c = os.path.join(cdir, j["clip"])
        if not os.path.exists(c):
            sys.exit(f"missing 4K clip {c} - run --stage clips")
        for an in (extras or {}).get("announcers", []):
            if an["before_clip"] in j["clip"]:
                af = os.path.join(g.out, an["file"])
                if not os.path.exists(af):
                    sys.exit(f"missing announcer segment {af}")
                seq.append(af)
        seq.append(c); pieces += 1
        p_list = [p.strip() for p in (j.get("player") or "").split(",") if p.strip()]
        player_matches = (not player) or (str(player) in p_list) or (j.get("player") == str(player))
        if j["clip"] in ours and player_matches and not any(o["clip"] in j["clip"] for o in (extras or {}).get("sfx", {}).get("overlays", []) if not o.get("replay")):
            cheers.append(j["clip"])
        if is_zoom(j["row"]):
            rp = os.path.join(g.extra, g.replay_name(j, height=2160))
            if not os.path.exists(rp):
                sys.exit(f"missing 4K replay {rp} - run --stage replays")
            seq.append(rp)
            # second (manual) replay of the same clip, e.g. 10-17 clip 18: state entries with the same clip number but another token
            import zoom_edit
            st = g.state()["replays"]
            for tok2, r2 in sorted(st.items(), key=lambda kv: kv[1]["event"]):
                if r2["n"] == j["n"] and tok2 != g.token(j):
                    rp2 = zoom_edit.names(g, r2, tok2, 2160)[1]
                    if not os.path.exists(rp2):
                        sys.exit(f"missing 4K second replay {rp2} - run --stage replays")
                    seq.append(rp2)
    seq.append(os.path.join(cards, "999_outro.mp4"))
    return seq, cheers, pieces


def probe_total(seq):
    return sum(probe_dur(p) or 0 for p in seq) - 0.4 * (len(seq) - 1)


def pick_tracks(g, n=2):
    """Random music beds for this game's reels: different tracks per reel, and not the ones the previous game used (out\\_music_history.json)."""
    import json, random
    EXC = ["remember_the_name"]
    pool = [f for f in sorted(os.listdir("shared/Music")) if f.lower().endswith(".mp3") and not f.lower().startswith("cheer ") and not any(x in f.lower() for x in EXC)]
    hp = os.path.join("out", "_music_history.json")
    try: hist = json.load(open(hp, encoding="utf-8"))
    except Exception: hist = {}
    last = [t for k, v in hist.items() if k != os.path.basename(g.out) for t in v][-n:]
    cand = [t for t in pool if t not in last]
    if len(cand) < n: cand = pool
    mine = hist.get(os.path.basename(g.out))
    if mine and all(t in pool for t in mine) and len(mine) >= n: return mine           # resume: keep this game's tracks
    pick = random.sample(cand, min(n, len(cand)))
    while len(pick) < n: pick.append(random.choice(pool))
    hist[os.path.basename(g.out)] = pick; json.dump(hist, open(hp, "w", encoding="utf-8"), indent=1)
    return pick


def stage_reel(g, name, player=None, seed=7, track=None):
    extras = load_extras(g) if player is None else None
    seq, cheers, n = build_list(g, player, halftime=player is None, extras=extras)
    if player and n == 0:
        print(f"no rows for player {player} - no reel"); return
    dst = os.path.join(g.out, "reels", f"{g.prefix}_{name}.mp4"); os.makedirs(os.path.dirname(dst), exist_ok=True)
    print(f"[reels] Building {os.path.basename(dst)} from {len(seq)} pieces ({n} clips{', player #' + str(player) if player else ', team highlights'})...", flush=True)
    run([PY, "tools/pipeline/reel_build.py", "--clips", ",".join(seq), "--out", dst, "--music-dir", "shared/Music", "--seed", str(seed)] + (["--track", track] if track else []) + [
         "--preset", "veryfast", "--crf", "23", "--cheer-clips", ",".join(cheers)]
        + (["--extras", os.path.join(g.out, "extras.json"), "--extras-root", g.out] if extras else []))
    exp = probe_total(seq); got = probe_dur(dst)
    print(f"{'OK ' if got and abs(got - exp) < 1.0 else 'BAD'} {os.path.basename(dst)}: {n} clips, expected {exp:.1f}s probed {got and round(got, 1)}s, cheers {len(cheers)}")


def short_name(g, no):
    for r in csv.DictReader(open(g.roster_path, newline="", encoding="utf-8-sig")):
        r_no = str(r.get("no") or r.get("No") or "").strip()
        if r_no == str(no):
            val = (r.get("short_name") or r.get("Short_Name") or r.get("name") or r.get("Player") or "").strip()
            return val.split()[0] if val else "Player"
    return "Player"


def get_default_featured_player():
    from xbotgo_core import app_config
    return app_config.default_featured_player(ROOT)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--stage", default="all", choices=["cards", "clips", "replays", "reels", "all"])
    ap.add_argument("--player", default=get_default_featured_player()); ap.add_argument("--seed", type=int, default=None, help="fixed music seed; default: random tracks")
    a = ap.parse_args(); g = Game(a.out)
    st = a.stage
    cards_ok = os.path.exists(os.path.join(g.out, "clips", "cards", "999_outro.mp4"))
    if st == "cards" or (st == "all" and not cards_ok):
        print(f"[cards] Generating title cards (intro, halftime, outro) for {g.base}...")
        stage_cards(g)
        print(f"[cards] Cards generated successfully in {os.path.join(g.out, 'clips', 'cards')}")
    if st in ("clips", "all"): print("[clips] Cutting 4K clips...", flush=True); stage_clips(g); print("[clips] done", flush=True)
    if st in ("replays", "all"): print("[replays] Rendering 4K zoom replays (finished ones are skipped)...", flush=True); stage_replays(g); print("[replays] done", flush=True)
    if st in ("reels", "all"):
        print("[reels] Assembling highlight reels...", flush=True)
        t1, t2 = (None, None) if a.seed is not None else pick_tracks(g)
        if t1: print("music tracks:", t1, "|", t2)
        stage_reel(g, "highlights_transitions", None, a.seed or 7, t1)
        print("[reels] team highlights done", flush=True)
        players = [p.strip() for p in str(a.player).split(",") if p.strip()]
        for p_no in players:
            _, t_p = (None, None) if a.seed is not None else pick_tracks(g)
            stage_reel(g, f"{short_name(g, p_no)}_{p_no}_highlights", p_no, a.seed or 7, t_p or t2)

        # Output clear completion summary
        reels_built = []
        hl_dst = os.path.join(g.out, "reels", f"{g.prefix}_highlights_transitions.mp4")
        if os.path.exists(hl_dst):
            d = probe_dur(hl_dst)
            reels_built.append(f"{os.path.basename(hl_dst)} ({d:.1f}s)")
        for p_no in players:
            p_dst = os.path.join(g.out, "reels", f"{g.prefix}_{short_name(g, p_no)}_{p_no}_highlights.mp4")
            if os.path.exists(p_dst):
                d = probe_dur(p_dst)
                reels_built.append(f"{os.path.basename(p_dst)} ({d:.1f}s)")

        print("\n=======================================================")
        print(f"[rebuild] Rebuild complete: highlight reels updated:")
        for rb in reels_built:
            print(f"  • {rb}")
        print("=======================================================\n")
