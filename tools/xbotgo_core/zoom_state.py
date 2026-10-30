"""Zoom replay state and data transformation services for XbotGo.

Pure Python module with zero web framework dependencies.
Provides:
- Token and clip resolution.
- Zoom candidate listing with status classification (unplaced, unreviewed, reviewed, rendered, rendered (stale)).
- Zoom replay detail resolution and 4K bounding box clamping.
- Auto-frame calculation to standard soccer framing [1152, 450] (2.5x).
- Homography matrix discovery.
- Atomic Remove-Zoom and Restore-Zoom synchronization between CSV and zoom_state.json.
"""
from .diag import swallowed as _swallowed
import glob
import hashlib
import json
import os
import re
import shutil
import time
from typing import Any, Dict, List, Optional, Tuple

from . import xb_env
from .xbl import Game, is_zoom, default_window, probe_dur

CROP_W = 1280


def lab(height: int) -> str:
    """Return '720' or stringified height."""
    return "720" if height == 720 else str(height)


def jobs_by_clip(g: Game) -> Tuple[Dict[int, Any], Dict[str, Any]]:
    """Return dicts of jobs by clip number (n) and by token."""
    js = g.jobs()
    return {j["n"]: j for j in js}, {g.token(j): j for j in js}


def names(g: Game, r: Dict[str, Any], tok: str, height: int) -> Tuple[str, str]:
    """Return (master_path, final_path) for a replay."""
    nm = f"{r['n']:03d}b_{tok}_zoom3x_{lab(height)}.mp4"
    return os.path.join(g.extra, "master", nm), os.path.join(g.extra, nm)


def sig(r: Dict[str, Any], height: int) -> str:
    """Return signature hash key for replay render staleness detection."""
    k = f"{r['path']}|{r['event']}|{r['start']}|{r['dur']}|{r['crop']}|{height}"
    return (
        k
        + "|stab5"
        + (f"|pan{r['pan']}" if r.get("pan") else "")
        + (f"|zoomto{r['zoom_to']}" if r.get("zoom_to") else "")
        + (f"|cw{r['crop_w']}" if r.get("crop_w") else "")
    )


def parse_crop(crop_str: Optional[str] = None, tile_str: Optional[str] = None) -> List[int]:
    """Parse crop coordinates [x, y] clamped to 4K bounds."""
    if tile_str:
        tx, ty = map(float, tile_str.split(","))
        x, y = tx * 6 - 640, ty * 6 - 360
    elif crop_str:
        x, y = map(float, crop_str.split(",")[:2])
    else:
        return [0, 0]
    return [int(max(0, min(3840 - CROP_W, round(x)))), int(max(0, min(2160 - 720, round(y))))]


from . import csv_io
from . import time_utils
from .game_state import ROOT, resolve_game_out, find_timeline_for_game, resolve_video_info


def resolve_token(g: Game, token_or_clip: str) -> Optional[str]:
    """Resolve token_or_clip to canonical token string."""
    st = g.state()
    js_n, js_t = jobs_by_clip(g)

    # 1. Direct match in jobs, replays, or removed
    if token_or_clip in js_t or token_or_clip in st.get("replays", {}) or token_or_clip in st.get("removed", {}):
        return token_or_clip

    # 2. Extract token if full filename/label given (e.g. 007b_goal_001807...)
    extracted = re.search(r"((?:goal|mark|[a-z]+)_\d{6})", token_or_clip)
    if extracted and (extracted.group(1) in js_t or extracted.group(1) in st.get("removed", {})):
        return extracted.group(1)

    # 3. Numeric clip number
    try:
        c_num = int(token_or_clip)
        if c_num in js_n:
            return g.token(js_n[c_num])
        for tok, r_cand in st.get("replays", {}).items():
            if r_cand.get("n") == c_num:
                return tok
        for tok, r_cand in st.get("removed", {}).items():
            if r_cand.get("n") == c_num:
                return tok
    except (ValueError, TypeError):
        pass

    return None


def get_zoom_replays_data(out_dir: str, game_id: str) -> Dict[str, Any]:
    """List all zoom replay candidates for a game with status."""
    g = Game(out_dir)
    st = g.state()
    js_n, js_t = jobs_by_clip(g)
    zoom_list = []

    for tok, j in sorted(js_t.items(), key=lambda kv: kv[1]["n"]):
        if not is_zoom(j["row"]):
            continue
        r = st.get("replays", {}).get(tok)
        master_path, final_path = names(g, r if r else {"n": j["n"]}, tok, 720)

        # Check existing final video at 720p or 2160p (master / extra / work folders)
        final_cands = [
            final_path,
            os.path.join(g.extra, f"{j['n']:03d}b_{tok}_zoom3x_2160.mp4"),
            os.path.join(g.out, "work", "clips", "extra", f"{j['n']:03d}b_{tok}_zoom3x_720.mp4"),
            os.path.join(g.out, "work", "clips", "extra", f"{j['n']:03d}b_{tok}_zoom3x_2160.mp4"),
        ]
        final_found = next((p for p in final_cands if os.path.exists(p)), None)
        final_exists = (final_found is not None)

        # Status determination
        is_stale = False
        if final_exists and r and r.get("history") and len(r["history"]) > 0:
            last_h = r["history"][-1]
            if last_h.get("window"):
                if abs((r.get("start") or 0) - last_h["window"][0]) > 0.05 or abs((r.get("dur") or 0) - last_h["window"][1]) > 0.05:
                    is_stale = True
            if last_h.get("cut"):
                if abs((r.get("cut_start") or 0) - last_h["cut"][0]) > 0.05 or abs((r.get("cut_end") or 0) - last_h["cut"][1]) > 0.05:
                    is_stale = True
            if last_h.get("crop") and r.get("crop"):
                if list(r.get("crop")) != list(last_h["crop"]):
                    is_stale = True

        is_reviewed = bool(r.get("reviewed")) if r else False
        if final_exists and r and r.get("crop") is not None and not is_reviewed:
            is_reviewed = True

        if r is None or r.get("crop") is None:
            status = "unplaced"
        elif not is_reviewed:
            status = "unreviewed"
        elif is_stale:
            status = "rendered (stale)"
        elif not final_exists:
            status = "reviewed"
        else:
            status = "rendered" if (r.get("final_key") or is_reviewed) else "needs render"

        # Check homographies presence
        has_h = False
        zw_dir = os.path.join(xb_env.tmp_for(g.out), "zw")
        if os.path.exists(zw_dir):
            if glob.glob(os.path.join(zw_dir, f"{tok}_*", "H.json")):
                has_h = True

        crop = r.get("crop") if r else None
        if r and r.get("crop") is not None:
            crop_w = r.get("crop_w") or 1280
        else:
            crop_w = 1536
        zoom_ratio = round(3840.0 / crop_w, 2) if crop_w else 3.0
        s = r.get("start") if r else None
        d = r.get("dur") if r else None
        if s is None:
            s, d = default_window(j["event"], g.action_end(j))

        zoom_list.append({
            "clip": j["n"],
            "token": tok,
            "event": j["event"],
            "file": j["file"],
            "status": status,
            "crop": crop,
            "crop_w": crop_w,
            "zoom": zoom_ratio,
            "window": {"start": s, "dur": d},
            "has_homographies": has_h,
            "reviewed": is_reviewed,
            "is_auto_placed": bool(r and r.get("is_auto_placed") and not is_reviewed),
            "final_exists": final_exists,
            "is_stale": is_stale,
            "final_url": f"/api/video?path={os.path.relpath(final_found, ROOT).replace(chr(92), '/')}" if final_found else None,
        })

    return {"game_id": game_id, "replays": zoom_list}


def get_zoom_replay_details_data(out_dir: str, game_id: str, token_or_clip: str) -> Optional[Dict[str, Any]]:
    """Get complete replay specification and source video info."""
    g = Game(out_dir)
    st = g.state()
    js_n, js_t = jobs_by_clip(g)

    tok = resolve_token(g, token_or_clip)
    if not tok:
        return None

    job = js_t.get(tok)
    r = st.get("replays", {}).get(tok)
    is_removed = False
    if r is None and tok in st.get("removed", {}):
        r = st.get("removed", {}).get(tok)
        is_removed = True

    clip_num = job["n"] if job else (r.get("n", 0) if r else 0)
    event_sec = job["event"] if job else (r.get("event", 0.0) if r else 0.0)
    action_end_sec = g.action_end(job) if job else None
    s_def, d_def = default_window(event_sec, action_end_sec)

    if r is None:
        def_crop_w = 1280
        r = {
            "n": clip_num,
            "event": event_sec,
            "file": job["file"] if job else "",
            "path": job["path"] if job else "",
            "crop": None,
            "crop_w": def_crop_w,
            "start": s_def,
            "dur": d_def,
            "cut_start": 0.0,
            "cut_end": 0.0,
            "master_key": None,
            "final_key": None,
            "history": [],
            "pan": None,
            "zoom_to": None,
            "hold_end": None,
            "is_auto_placed": False,
            "reviewed": False,
        }
    else:
        crop_w = r.get("crop_w") or 1280
        r["crop_w"] = crop_w
        r["reviewed"] = bool(r.get("reviewed") is True)
        if r.get("crop") is None:
            r["crop"] = None
            r["is_auto_placed"] = bool(r.get("is_auto_placed", False))
        else:
            max_x = max(0, 3840 - crop_w)
            max_y = max(0, 2160 - int(round(crop_w * 9 / 16)))
            r["crop"] = [
                max(0, min(max_x, int(round(r["crop"][0])))),
                max(0, min(max_y, int(round(r["crop"][1]))))
            ]
        if r.get("start") is None:
            r["start"] = s_def
            r["dur"] = d_def

    timeline = find_timeline_for_game(game_id)
    vinfo = resolve_video_info(r.get("file", ""), timeline)

    has_h = False
    exact_h = False
    zw_dir = os.path.join(xb_env.tmp_for(g.out), "zw")
    if os.path.exists(zw_dir):
        key = sig(r, 720)
        target_work = os.path.join(zw_dir, f"{tok}_{hashlib.md5(key.encode()).hexdigest()[:8]}")
        if os.path.exists(os.path.join(target_work, "H.json")):
            has_h = True
            exact_h = True
        elif glob.glob(os.path.join(zw_dir, f"{tok}_*", "H.json")):
            has_h = True
            exact_h = False

    master_path, final_path = names(g, r, tok, 720)
    final_cands = [
        final_path,
        os.path.join(g.extra, f"{clip_num:03d}b_{tok}_zoom3x_2160.mp4"),
        os.path.join(g.out, "work", "clips", "extra", f"{clip_num:03d}b_{tok}_zoom3x_720.mp4"),
        os.path.join(g.out, "work", "clips", "extra", f"{clip_num:03d}b_{tok}_zoom3x_2160.mp4"),
    ]
    final_found = next((p for p in final_cands if os.path.exists(p)), None)
    final_exists = (final_found is not None)

    is_stale = False
    if final_exists and r and r.get("history") and len(r["history"]) > 0:
        last_h = r["history"][-1]
        if last_h.get("window"):
            if abs((r.get("start") or 0) - last_h["window"][0]) > 0.05 or abs((r.get("dur") or 0) - last_h["window"][1]) > 0.05:
                is_stale = True
        if last_h.get("cut"):
            if abs((r.get("cut_start") or 0) - last_h["cut"][0]) > 0.05 or abs((r.get("cut_end") or 0) - last_h["cut"][1]) > 0.05:
                is_stale = True
        if last_h.get("crop") and r.get("crop"):
            if list(r.get("crop")) != list(last_h["crop"]):
                is_stale = True

    all_zoom = []
    reps_map = st.get("replays", {})
    for t_k, j_k in sorted(js_t.items(), key=lambda kv: kv[1]["n"]):
        if is_zoom(j_k["row"]):
            r_k = reps_map.get(t_k)
            is_rev = bool(r_k and r_k.get("reviewed") is True and r_k.get("crop") is not None)
            all_zoom.append({
                "clip": j_k["n"],
                "token": t_k,
                "label": f"Clip {j_k['n']} ({t_k})",
                "is_current": t_k == tok,
                "reviewed": is_rev,
                "status": "reviewed" if is_rev else ("unreviewed" if r_k and r_k.get("crop") else "unplaced")
            })

    return {
        "game_id": game_id,
        "clip": clip_num,
        "token": tok,
        "file": r.get("file"),
        "video": vinfo,
        "event": event_sec,
        "action_end": action_end_sec,
        "default_window": {"start": s_def, "dur": d_def},
        "replay": r,
        "has_homographies": has_h,
        "exact_homographies": exact_h,
        "final_exists": final_exists,
        "is_stale": is_stale,
        "is_removed": is_removed,
        "final_url": f"/api/video?path={os.path.relpath(final_found, ROOT).replace(chr(92), '/')}" if final_found else None,
        "all_zoom_clips": all_zoom,
    }


def auto_frame_zoom_replays_data(out_dir: str, token: Optional[str] = None, all_unplaced: bool = False) -> Dict[str, Any]:
    """Auto-frame replay(s) using standard soccer framing [1152, 450] at 2.5x (1536x864).
    
    Sets is_auto_placed: True, but keeps reviewed: False so render is blocked until user review.
    """
    g = Game(out_dir)
    st = g.state()
    js_n, js_t = jobs_by_clip(g)

    std_crop = [1152, 450]
    std_crop_w = 1536

    updated_tokens = []
    for tok, j in sorted(js_t.items(), key=lambda kv: kv[1]["n"]):
        if not is_zoom(j["row"]):
            continue
        if token and tok != token:
            continue
        r = st.get("replays", {}).setdefault(tok, {
            "n": j["n"], "event": j["event"], "file": j["file"], "path": j["path"],
            "crop": None, "start": None, "dur": None, "cut_start": 0.0, "cut_end": 0.0,
            "master_key": None, "final_key": None, "history": []
        })
        if all_unplaced and r.get("crop") is not None:
            continue

        s, d = default_window(j["event"], g.action_end(j))
        if r.get("start") is None:
            r["start"] = s
            r["dur"] = d
        r["crop"] = std_crop
        r["crop_w"] = std_crop_w
        r["is_auto_placed"] = True
        r["reviewed"] = False
        updated_tokens.append(tok)

    g.save_state(st)
    return {
        "success": True,
        "updated_tokens": updated_tokens,
        "count": len(updated_tokens)
    }


def get_zoom_homographies_data(out_dir: str, token_or_clip: str) -> Tuple[int, Dict[str, Any]]:
    """Retrieve per-frame homography matrices for live canvas transform."""
    g = Game(out_dir)
    st = g.state()
    js_n, js_t = jobs_by_clip(g)
    tok = resolve_token(g, token_or_clip)
    if not tok:
        return 404, {"error": "Replay not found", "available": False}

    r = st.get("replays", {}).get(tok)
    j = js_t.get(tok)

    # 1. First look for H.json matching current replay signature exactly
    if r or j:
        event = r["event"] if r else j["event"]
        src_path = r["path"] if r else j["path"]
        start = r["start"] if r and r.get("start") is not None else default_window(event, g.action_end(j))[0]
        dur = r["dur"] if r and r.get("dur") is not None else default_window(event, g.action_end(j))[1]
        crop = r["crop"] if r and r.get("crop") is not None else [1152, 648]
        crop_w = r.get("crop_w", 1280 if (r and r.get("crop") is not None) else 1536) if r else 1536
        r_eff = {
            "path": src_path, "event": event, "start": start, "dur": dur, "crop": crop,
            "crop_w": crop_w if crop_w != 1280 else None,
            "pan": r.get("pan") if r else None, "zoom_to": r.get("zoom_to") if r else None
        }
        key = sig(r_eff, 720)
        target_work = os.path.join(xb_env.tmp_for(g.out), "zw", f"{tok}_{hashlib.md5(key.encode()).hexdigest()[:8]}")
        h_exact = os.path.join(target_work, "H.json")
        if os.path.exists(h_exact):
            with open(h_exact, "r", encoding="utf-8") as f:
                data = json.load(f)
            return 200, {"token": tok, "available": True, "count": len(data), "homographies": data, "exact": True}

    # 2. Fallback to newest H.json for this token if any
    zw_dir = os.path.join(xb_env.tmp_for(g.out), "zw")
    if os.path.exists(zw_dir):
        matches = glob.glob(os.path.join(zw_dir, f"{tok}_*", "H.json"))
        if matches:
            newest = max(matches, key=os.path.getmtime)
            with open(newest, "r", encoding="utf-8") as f:
                data = json.load(f)
            return 200, {"token": tok, "available": True, "count": len(data), "homographies": data, "exact": False}

    return 404, {"error": "Homographies not computed yet. Click Prepare.", "available": False}


def remove_zoom_replay_data(out_dir: str, token_or_clip: str) -> Tuple[int, Dict[str, Any]]:
    """Remove 'zoom' instruction from this row in the review CSV (atomic with zoom_state.json)."""
    g = Game(out_dir)
    js_n, js_t = jobs_by_clip(g)
    st = g.state()

    tok = resolve_token(g, token_or_clip)
    if not tok:
        return 404, {"error": "Replay not found"}

    j = js_t.get(tok)
    target_clip = j["n"] if j else (st.get("replays", {}).get(tok, {}).get("n"))

    headers, rows = csv_io.read_reviewed_csv(g.csv)
    target_row = None

    if target_clip is not None:
        computed_clips = csv_io.compute_clip_numbers(rows)
        target_clip_str = str(target_clip)
        for i, c in enumerate(computed_clips):
            if c == target_clip_str:
                target_row = rows[i]
                break

    if not target_row and j:
        f_name = j.get("file")
        ev = j.get("event")
        for r in rows:
            if r.get("file") == f_name:
                try:
                    r_ev = time_utils.secs(r.get("event") or "")
                    if r_ev is not None and abs(r_ev - ev) < 1.0:
                        target_row = r
                        break
                except Exception:
                    _swallowed()

    if not target_row:
        return 404, {"error": f"Row for clip {token_or_clip} not found in review CSV"}

    inst = target_row.get("instructions", "")
    new_inst = re.sub(r"\bzoom\b", "", inst, flags=re.IGNORECASE).strip()
    new_inst = re.sub(r"\s*,\s*,+", ", ", new_inst)
    new_inst = re.sub(r"^\s*,\s*|\s*,\s*$", "", new_inst).strip()
    target_row["instructions"] = new_inst

    csv_bak = g.csv + f".remove_zoom.{int(time.time()*1000)}.bak"
    shutil.copy2(g.csv, csv_bak)

    try:
        csv_io.write_reviewed_csv(g.csv, headers, rows, create_backup=True)

        if tok in st.get("replays", {}):
            st.setdefault("removed", {})[tok] = st["replays"].pop(tok)
            g.save_state(st)

        if os.path.exists(csv_bak):
            try:
                os.remove(csv_bak)
            except OSError:
                pass
    except Exception as e:
        if os.path.exists(csv_bak):
            shutil.copy2(csv_bak, g.csv)
            try:
                os.remove(csv_bak)
            except OSError:
                pass
        return 500, {"error": f"Atomic remove-zoom failed: {e}"}

    return 200, {"status": "removed", "token": tok, "clip": target_clip}


def restore_zoom_replay_data(out_dir: str, token_or_clip: str) -> Tuple[int, Dict[str, Any]]:
    """Restore a previously removed zoom replay: adds 'zoom' back to CSV and moves replay from removed back to replays."""
    g = Game(out_dir)
    st = g.state()
    js_n, js_t = jobs_by_clip(g)

    tok = resolve_token(g, token_or_clip)
    if not tok:
        return 404, {"error": f"Replay '{token_or_clip}' not found"}

    j = js_t.get(tok)
    target_clip = j["n"] if j else (
        st.get("removed", {}).get(tok, {}).get("n") or st.get("replays", {}).get(tok, {}).get("n")
    )

    headers, rows = csv_io.read_reviewed_csv(g.csv)
    target_row = None

    if target_clip is not None:
        computed_clips = csv_io.compute_clip_numbers(rows)
        target_clip_str = str(target_clip)
        for i, c in enumerate(computed_clips):
            if c == target_clip_str:
                target_row = rows[i]
                break

    if not target_row:
        rem_rep = st.get("removed", {}).get(tok) or st.get("replays", {}).get(tok)
        f_name = j.get("file") if j else (rem_rep.get("file") if rem_rep else None)
        ev = j.get("event") if j else (rem_rep.get("event") if rem_rep else None)
        if f_name and ev is not None:
            for r in rows:
                if r.get("file") == f_name:
                    try:
                        r_ev = time_utils.secs(r.get("event") or "")
                        if r_ev is not None and abs(r_ev - ev) < 1.0:
                            target_row = r
                            break
                    except Exception:
                        _swallowed()

    if not target_row:
        return 404, {"error": f"Row for clip {token_or_clip} not found in review CSV"}

    inst = target_row.get("instructions", "").strip()
    if not re.search(r"\bzoom\b", inst, flags=re.IGNORECASE):
        target_row["instructions"] = f"{inst} zoom".strip() if inst else "zoom"

    csv_bak = g.csv + f".restore_zoom.{int(time.time()*1000)}.bak"
    shutil.copy2(g.csv, csv_bak)

    try:
        csv_io.write_reviewed_csv(g.csv, headers, rows, create_backup=True)

        if tok in st.get("removed", {}):
            st.setdefault("replays", {})[tok] = st["removed"].pop(tok)
            g.save_state(st)

        if os.path.exists(csv_bak):
            try:
                os.remove(csv_bak)
            except OSError:
                pass
    except Exception as e:
        if os.path.exists(csv_bak):
            shutil.copy2(csv_bak, g.csv)
            try:
                os.remove(csv_bak)
            except OSError:
                pass
        return 500, {"error": f"Atomic restore-zoom failed: {e}"}

    return 200, {"status": "restored", "token": tok, "clip": target_clip}


def apply_zoom_spec_to_state(
    g: Game,
    spec: Dict[str, Any],
    token_or_target: Optional[str] = None
) -> Tuple[str, Dict[str, Any], bool]:
    """Single-pass atomic apply of a replay specification dictionary to zoom_state.json.
    
    Returns:
        (tok, replay_dict, is_changed)
    """
    st = g.state()
    js_n, js_t = jobs_by_clip(g)

    tok = spec.get("token")
    if not tok:
        target = token_or_target or spec.get("clip")
        if target is not None:
            if isinstance(target, str) and target in st["replays"]:
                tok = target
            elif isinstance(target, str) and target in js_t:
                tok = target
            else:
                try:
                    c_num = int(target)
                    if c_num in js_n:
                        tok = g.token(js_n[c_num])
                    else:
                        for k, r_cand in st["replays"].items():
                            if r_cand.get("n") == c_num:
                                tok = k
                                break
                except (ValueError, TypeError):
                    pass

    if not tok:
        raise ValueError(f"Cannot resolve replay token from spec or target {token_or_target}")

    r = st["replays"].get(tok)
    if r is None:
        if tok in js_t:
            j = js_t[tok]
            s, d = default_window(j["event"], g.action_end(j))
            r = st["replays"].setdefault(tok, {
                "n": j["n"], "event": j["event"], "file": j["file"], "path": j["path"],
                "crop": None, "start": s, "dur": d, "cut_start": 0.0, "cut_end": 0.0,
                "master_key": None, "final_key": None, "history": []
            })
        else:
            raise KeyError(f"Token {tok} not found in replays or game jobs")

    if tok in js_t:
        r["n"] = js_t[tok]["n"]

    orig_crop_w = r.get("crop_w", CROP_W)
    crop_w = int(round(spec.get("crop_w") or orig_crop_w))
    crop_h = int(round(crop_w * 9 / 16))
    max_x = max(0, 3840 - crop_w)
    max_y = max(0, 2160 - crop_h)

    raw_crop = spec.get("crop") if "crop" in spec and spec["crop"] is not None else (r.get("crop") or [0, 0])
    cx = max(0, min(max_x, int(round(raw_crop[0]))))
    cy = max(0, min(max_y, int(round(raw_crop[1]))))

    new_pan = None
    if "pans" in spec or "pan" in spec:
        pans = spec.get("pans", spec.get("pan"))
        if pans:
            parsed_pans = []
            if isinstance(pans, (list, tuple)) and pans and isinstance(pans[0], (int, float)):
                parsed_pans.append([float(v) for v in pans])
            else:
                for p in pans:
                    if isinstance(p, dict):
                        x = float(p.get("x", 0))
                        y = float(p.get("y", 0))
                        at = float(p.get("at", 0))
                        mode = p.get("mode", "snap")
                        if mode == "glide" and "len" in p:
                            parsed_pans.append([x, y, at, float(p["len"])])
                        elif "len" in p and float(p["len"]) > 0:
                            parsed_pans.append([x, y, at, float(p["len"])])
                        else:
                            parsed_pans.append([x, y, at])
                    elif isinstance(p, (list, tuple)):
                        parsed_pans.append([float(v) for v in p])
            if parsed_pans:
                new_pan = parsed_pans[0] if len(parsed_pans) == 1 else parsed_pans
    else:
        new_pan = r.get("pan")

    new_zoom_to = None
    if "zoom_to" in spec:
        zt = spec.get("zoom_to")
        if zt and zt != "off":
            if isinstance(zt, str):
                new_zoom_to = [float(v) for v in zt.split(",")]
            elif isinstance(zt, (list, tuple)):
                new_zoom_to = [float(v) for v in zt]
    else:
        new_zoom_to = r.get("zoom_to")

    orig_he = r.get("hold_end")
    if "hold_end" in spec:
        he = spec.get("hold_end")
        new_he = round(float(he), 3) if (he is not None and float(he) > 0) else None
    else:
        new_he = orig_he

    crop_w_changed = (crop_w != orig_crop_w)
    crop_changed = (r.get("crop") != [cx, cy])
    start_changed = ("start" in spec and spec["start"] is not None and round(float(spec["start"]), 3) != r.get("start"))
    dur_changed = ("dur" in spec and spec["dur"] is not None and round(float(spec["dur"]), 3) != r.get("dur"))
    cut_start_changed = ("cut_start" in spec and spec["cut_start"] is not None and round(float(spec["cut_start"]), 3) != r.get("cut_start", 0.0))
    cut_end_changed = ("cut_end" in spec and spec["cut_end"] is not None and round(float(spec["cut_end"]), 3) != r.get("cut_end", 0.0))
    pan_changed = (new_pan != r.get("pan"))
    zoom_to_changed = (new_zoom_to != r.get("zoom_to"))
    hold_changed = (new_he != orig_he)

    is_changed = (
        crop_w_changed or crop_changed or start_changed or dur_changed or
        cut_start_changed or cut_end_changed or pan_changed or zoom_to_changed or hold_changed
    )

    if is_changed:
        r["crop"] = [cx, cy]
        r["reviewed"] = True
        if "is_auto_placed" in spec:
            r["is_auto_placed"] = bool(spec["is_auto_placed"])
        else:
            r["is_auto_placed"] = False
        if abs(crop_w - CROP_W) == 0:
            r.pop("crop_w", None)
        else:
            r["crop_w"] = crop_w

        if "start" in spec and spec["start"] is not None:
            r["start"] = round(float(spec["start"]), 3)
        if "dur" in spec and spec["dur"] is not None:
            r["dur"] = round(float(spec["dur"]), 3)

        if "cut_start" in spec and spec["cut_start"] is not None:
            r["cut_start"] = round(float(spec["cut_start"]), 3)
        if "cut_end" in spec and spec["cut_end"] is not None:
            r["cut_end"] = round(float(spec["cut_end"]), 3)

        if new_pan is not None:
            r["pan"] = new_pan
        else:
            r.pop("pan", None)

        if new_zoom_to is not None:
            r["zoom_to"] = new_zoom_to
        else:
            r.pop("zoom_to", None)

        if new_he is not None:
            r["hold_end"] = new_he
        else:
            r.pop("hold_end", None)

        if "history" not in r or not isinstance(r["history"], list):
            r["history"] = []
        r["history"].append({
            "t": time.strftime("%F %T"),
            "window": [r["start"], r["dur"]],
            "crop": r["crop"],
            "cut": [r.get("cut_start", 0.0), r.get("cut_end", 0.0)]
        })
        g.save_state(st)
    else:
        if "reviewed" in spec:
            r["reviewed"] = bool(spec["reviewed"])
        else:
            r["reviewed"] = True
        if "is_auto_placed" in spec:
            r["is_auto_placed"] = bool(spec["is_auto_placed"])
        g.save_state(st)

    return tok, r, is_changed

