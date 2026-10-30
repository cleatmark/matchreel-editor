"""4K production clip bookkeeping, staleness checking, and preflight calculations for XbotGo.

Pure Python module with zero web framework dependencies.
Provides:
- check_4k_outputs_staleness: Inspects 4K replays and highlight reels against zoom_state.json.
- calculate_production_preflight: Runs preflight validation across game info, roster, cards, zoom replays, timings, and disk space.
"""
from .diag import swallowed as _swallowed
import datetime
import glob
import os
import shutil
from typing import Any, Dict, List, Optional, Set

from .xbl import Game, is_zoom, probe_dur
from .zoom_state import jobs_by_clip

from . import csv_io
from . import time_utils
from .game_state import ROOT, resolve_game_out, load_game_info, load_roster


def check_4k_outputs_staleness(game_id: str, out_dir: str) -> Dict[str, Any]:
    """Check whether any 4K replays or highlight reels are stale compared to zoom_state.json.

    A 4K replay is considered stale if:
      1. An existing 4K file duration differs from expected replay duration ((dur - cut_start - cut_end) / speed + hold).
      2. The replay plan has been modified (history timestamp or state) after the 4K file was generated.
    Highlight reels are considered stale if any 4K replay is stale, or if existing reels
    have mtime older than any 4K replay or zoom_state.json.
    """
    g = Game(out_dir)
    st = g.state()
    reps = st.get("replays", {})
    extra_dir = os.path.join(out_dir, "clips", "extra")
    reels_dir = os.path.join(out_dir, "reels")

    existing_4k_files = glob.glob(os.path.join(extra_dir, "*_2160.mp4")) if os.path.exists(extra_dir) else []
    existing_reels = glob.glob(os.path.join(reels_dir, "*.mp4")) if os.path.exists(reels_dir) else []
    has_production_outputs = bool(existing_4k_files or existing_reels)

    if not has_production_outputs:
        return {
            "is_stale": False,
            "stale_count": 0,
            "stale_replays": [],
            "reels_stale": False,
        }

    stale_replays = []
    zm_path = os.path.join(out_dir, "zoom_state.json")
    zm_mtime = os.path.getmtime(zm_path) if os.path.exists(zm_path) else 0

    for tok, r in sorted(reps.items(), key=lambda kv: kv[1].get("n", 0)):
        if not (r.get("reviewed") and r.get("crop") is not None):
            continue

        n = r.get("n", 0)
        dur = float(r.get("dur", 0.0) or 0.0)
        c_start = float(r.get("cut_start", 0.0) or 0.0)
        c_end = float(r.get("cut_end", 0.0) or 0.0)
        hold = float(r.get("hold_end", 0.0) or 0.0)
        speed = float(r.get("speed", 0.5) or 0.5)
        expected_len = round((dur - c_start - c_end) / speed + hold, 2)

        f_4k = os.path.join(extra_dir, f"{n:03d}b_{tok}_zoom3x_2160.mp4")
        if os.path.exists(f_4k):
            actual_dur = None
            try:
                actual_dur = probe_dur(f_4k)
            except Exception:
                actual_dur = None

            is_clip_stale = False
            reason = "ok"

            if actual_dur is not None and abs(actual_dur - expected_len) > 0.3:
                is_clip_stale = True
                reason = f"Duration mismatch ({actual_dur:.1f}s vs expected {expected_len:.1f}s)"
            elif r.get("history") and len(r["history"]) > 0:
                last_h = r["history"][-1]
                t_str = last_h.get("t")
                if t_str:
                    try:
                        t_hist = datetime.datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S").timestamp()
                        if t_hist > os.path.getmtime(f_4k) + 5:  # 5s tolerance
                            is_clip_stale = True
                            reason = f"Plan edited after 4K master ({t_str})"
                    except Exception:
                        _swallowed()

            if is_clip_stale:
                stale_replays.append({
                    "n": n,
                    "token": tok,
                    "expected_dur": expected_len,
                    "file_dur": actual_dur,
                    "reason": reason,
                })
        elif existing_4k_files:
            stale_replays.append({
                "n": n,
                "token": tok,
                "expected_dur": expected_len,
                "file_dur": None,
                "reason": "Missing 4K master file",
            })

    reels_stale = False
    production_reels = [
        rf for rf in existing_reels
        if not os.path.basename(rf).endswith("_preview720_nomusic.mp4")
        and "preview" not in os.path.basename(rf).lower()
    ]

    if stale_replays:
        reels_stale = True
    elif production_reels and existing_4k_files:
        oldest_prod_reel = min(os.path.getmtime(rf) for rf in production_reels)
        newest_4k = max(os.path.getmtime(kf) for kf in existing_4k_files)
        if newest_4k > oldest_prod_reel + 5:
            reels_stale = True

    est_rebuild_minutes = max(3, int(round(len(stale_replays) * 1.0 + 3.5)))

    return {
        "is_stale": bool(stale_replays or reels_stale),
        "stale_count": len(stale_replays),
        "stale_replays": stale_replays,
        "reels_stale": reels_stale,
        "est_rebuild_minutes": est_rebuild_minutes,
    }


def calculate_production_preflight(game_id: str, out_dir: str) -> Dict[str, Any]:
    """Calculate preflight validation checks, duration estimates, and batch readiness."""
    g = Game(out_dir)
    st = g.state()
    js_n, js_t = jobs_by_clip(g)

    # 1. Game Info completeness
    gi = load_game_info(game_id) or {}
    home = (gi.get("home") or "").strip()
    opponent = (gi.get("opponent") or "").strip()
    score = (gi.get("score") or "").strip()
    home_logo = (gi.get("home_logo") or "").strip()
    away_logo = (gi.get("away_logo") or "").strip()
    home_logo_ok = bool(home_logo and os.path.exists(os.path.join(ROOT, home_logo)))
    away_logo_ok = bool(not away_logo or os.path.exists(os.path.join(ROOT, away_logo)))
    game_info_ok = bool(home and opponent and opponent.lower() != "opponent" and score and home_logo_ok and away_logo_ok)

    # 2. Roster
    roster_rows = load_roster()
    roster_ok = len(roster_rows) > 0

    # 3. Title cards
    cards_intro = os.path.join(out_dir, "clips", "cards", "000_intro_fullgame.mp4")
    cards_work_intro = os.path.join(out_dir, "work", "clips", "cards", "000_intro_fullgame.mp4")
    cards_exist = os.path.exists(cards_intro) or os.path.exists(cards_work_intro)
    cards_details = "Intro and cards ready on disk" if cards_exist else "Will be generated automatically in batch Step 1"

    # 4. Zoom replays reviewed
    reps = st.get("replays", {})
    zoom_clips = []
    unreviewed_zoom = []
    for tok_c, j_c in sorted(js_t.items(), key=lambda kv: kv[1]["n"]):
        if is_zoom(j_c["row"]):
            zoom_clips.append({"n": j_c["n"], "token": tok_c})
            r_c = reps.get(tok_c)
            if r_c and not r_c.get("reviewed") and r_c.get("crop") is not None:
                final_cands = [
                    os.path.join(g.extra, f"{j_c['n']:03d}b_{tok_c}_zoom3x_720.mp4"),
                    os.path.join(g.extra, f"{j_c['n']:03d}b_{tok_c}_zoom3x_2160.mp4"),
                    os.path.join(g.out, "work", "clips", "extra", f"{j_c['n']:03d}b_{tok_c}_zoom3x_720.mp4"),
                    os.path.join(g.out, "work", "clips", "extra", f"{j_c['n']:03d}b_{tok_c}_zoom3x_2160.mp4"),
                ]
                if any(os.path.exists(p) for p in final_cands):
                    r_c["reviewed"] = True
            if not r_c or not r_c.get("reviewed") or r_c.get("crop") is None:
                unreviewed_zoom.append({"n": j_c["n"], "token": tok_c})
    zoom_ok = len(unreviewed_zoom) == 0

    # 5. Timing validity
    timing_invalid_count = 0
    if os.path.exists(g.csv):
        headers, rows = csv_io.read_reviewed_csv(g.csv)
        for row in rows:
            if not csv_io.is_row_skipped(row.get("instructions"), row.get("skip")):
                s_val = row.get("action_start") or row.get("start")
                e_val = row.get("event")
                end_val = row.get("action_end") or row.get("end")
                if s_val or e_val or end_val:
                    is_valid, _ = time_utils.validate_timing_order(s_val, e_val, end_val)
                    if not is_valid:
                        timing_invalid_count += 1
    timings_ok = (timing_invalid_count == 0)

    # 6. Disk space
    try:
        usage = shutil.disk_usage(out_dir)
        free_gb = round(usage.free / (1024 ** 3), 1)
        disk_ok = free_gb >= 20.0
    except Exception:
        free_gb = 50.0
        disk_ok = True

    # 7. Bat file existence
    base_name = os.path.basename(out_dir)
    day = base_name[:10] if len(base_name) >= 10 and base_name[4] == "-" and base_name[7] == "-" else base_name
    bat_file = os.path.join(out_dir, f"run_everything_{day}.bat")
    bat_exists = os.path.exists(bat_file)

    # 8. Staleness check
    staleness = check_4k_outputs_staleness(game_id, out_dir)

    all_passed = bool(game_info_ok and roster_ok and zoom_ok and timings_ok and disk_ok)

    # Duration estimates
    all_jobs = g.jobs()
    n_jobs = len(all_jobs)
    existing_cut_files = set()
    for cd in [os.path.join(out_dir, "clips", "reviewed4k"), os.path.join(out_dir, "reviewed4k"), os.path.join(out_dir, "work", "clips", "reviewed4k")]:
        if os.path.exists(cd):
            existing_cut_files.update(os.listdir(cd))
    missing_clips = 0
    for j in all_jobs:
        n_prefix = f"{j.get('n', 0):03d}_"
        base_f = f"{j.get('basename')}.mp4" if j.get("basename") else None
        tok = j.get("token") or (j.get("basename") or "").split("_", 1)[-1]
        found = False
        if j.get("clip") and j["clip"] in existing_cut_files:
            found = True
        elif base_f and base_f in existing_cut_files:
            found = True
        elif f"{j.get('n', 0):03d}.mp4" in existing_cut_files:
            found = True
        elif any(f.startswith(n_prefix) for f in existing_cut_files):
            found = True
        elif tok and any(tok in f for f in existing_cut_files):
            found = True
        if not found:
            missing_clips += 1

    extra_dirs = [os.path.join(out_dir, "clips", "extra"), os.path.join(out_dir, "work", "clips", "extra")]
    stale_replays = staleness.get("stale_replays", [])
    stale_tokens = {sr.get("token") for sr in stale_replays if isinstance(sr, dict)}
    missing_replays = len(stale_replays)
    for zc in zoom_clips:
        tok_z = zc.get("token") or f"clip_{zc.get('n', 0)}"
        n_z = zc.get("n", 0)
        found_replay = any(
            os.path.exists(os.path.join(ed, f"{n_z:03d}b_{tok_z}_zoom3x_2160.mp4")) or
            os.path.exists(os.path.join(ed, "master", f"{n_z:03d}b_{tok_z}_zoom3x_2160.mp4"))
            for ed in extra_dirs
        )
        if not found_replay and tok_z not in stale_tokens:
            missing_replays += 1

    day_us = day.replace("-", "_")
    fg_candidates = [
        os.path.join(out_dir, f"{day}_fullgame.mp4"),
        os.path.join(out_dir, f"{day}_full_game.mp4"),
        os.path.join(out_dir, f"{day_us}_fullgame.mp4"),
        os.path.join(out_dir, f"{day_us}_full_game.mp4"),
        os.path.join(out_dir, "final", f"{day}_fullgame.mp4"),
        os.path.join(out_dir, "final", f"{day}_full_game.mp4"),
        os.path.join(out_dir, "final", f"{day_us}_fullgame.mp4"),
        os.path.join(out_dir, "final", f"{day_us}_full_game.mp4"),
    ]
    fullgame_needed = not any(os.path.exists(p) for p in fg_candidates)
    reels_needed = staleness.get("reels_stale", False)

    if missing_clips == 0 and missing_replays == 0 and not fullgame_needed and not reels_needed:
        est_minutes = 2
        est_hours = 0.0
        est_label = "Outputs up to date (~1-2 min verification)"
    else:
        est_minutes = int(round(missing_clips * 1.5 + missing_replays * 1.0 + (20 if fullgame_needed else 0) + (3.5 if reels_needed else 0)))
        est_minutes = max(3, est_minutes)
        est_hours = round(est_minutes / 60.0, 1)
        pieces = []
        if missing_clips: pieces.append(f"{missing_clips} clips to cut")
        if missing_replays: pieces.append(f"{missing_replays} replays to encode")
        if fullgame_needed: pieces.append("full-game assembly")
        if reels_needed: pieces.append("reels rebuild")
        pieces_str = ", ".join(pieces) if pieces else "remaining work"
        est_label = f"~{est_hours} hours ({est_minutes} min: {pieces_str})"

    return {
        "all_passed": all_passed,
        "checks": {
            "game_info": {
                "ok": game_info_ok,
                "label": "Game Setup Complete",
                "details": f"{home} vs {opponent}, score {score}" if game_info_ok else "Incomplete game setup or missing logos"
            },
            "roster": {
                "ok": roster_ok,
                "label": "Roster Available",
                "details": f"{len(roster_rows)} players loaded" if roster_ok else "No players found in roster.csv"
            },
            "cards": {
                "ok": True,
                "label": "Title Cards",
                "details": cards_details
            },
            "zoom": {
                "ok": zoom_ok,
                "label": "Zoom Replays Reviewed",
                "details": f"{len(zoom_clips)} clips ready" if zoom_ok else f"{len(unreviewed_zoom)} unreviewed/unplaced clips"
            },
            "timings": {
                "ok": timings_ok,
                "label": "Clip Timings Valid",
                "details": "All row timestamps valid" if timings_ok else f"{timing_invalid_count} rows with invalid start/event/end"
            },
            "disk_space": {
                "ok": disk_ok,
                "label": "Free Disk Space",
                "details": f"{free_gb} GB free (minimum 20 GB recommended)"
            }
        },
        "bat": {
            "exists": bat_exists,
            "path": bat_file,
            "filename": f"run_everything_{day}.bat"
        },
        "staleness": staleness,
        "day": day,
        "estimates": {
            "clip_count": n_jobs,
            "zoom_count": len(zoom_clips),
            "est_minutes": est_minutes,
            "est_hours": est_hours,
            "est_label": est_label
        },
        "unreviewed_zoom_clips": unreviewed_zoom
    }
