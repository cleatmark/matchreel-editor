"""XbotGo Review Editor Backend Server.

Local Flask server providing:
- Reviewed CSV loading, editing, and atomic saving.
- Range-served video playback for smooth seeking in browsers.
- Google Sheet synchronization (whole-table push to matched/created tab).
- Background task execution with streaming logs for Re-cut and CSV generation.
- Calendar date checking, dump folder discovery, and auto-generation.
"""
import csv
import datetime
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

# Ensure tools and utils are available via xb_env
TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS_DIR)
PIPELINE_DIR = os.path.join(TOOLS_DIR, "pipeline")
sys.path.insert(0, PIPELINE_DIR)
from xbotgo_core import xb_env  # puts ffmpeg, tesseract on PATH
from xbotgo_core.atomic_io import write_json_atomic
from xbotgo_core.diag import swallowed as _swallowed
from xbotgo_core.xbl import Game, is_zoom, default_window, PY, probe_dur
from xbotgo_core import jobs_by_clip, names, sig

from flask import Flask, jsonify, request, send_from_directory, abort, Response

import xbotgo_core
from xbotgo_core import (
    csv_io,
    time_utils,
    game_state,
    zoom_state,
    clip_bookkeeping,
    reel_selection,
    resolve_game_out,
    find_timeline_for_game,
    resolve_video_info,
    find_game_dump_folder,
    find_game_info_path,
    load_game_info,
    load_game_defaults,
    get_available_logos,
    check_csv_validity,
    load_roster,
    fetch_remote_roster,
    write_roster_local,
    push_roster_remote,
    normalize_roster,
    resolve_token,
    get_zoom_replays_data,
    get_zoom_replay_details_data,
    auto_frame_zoom_replays_data,
    get_zoom_homographies_data,
    remove_zoom_replay_data,
    restore_zoom_replay_data,
    check_4k_outputs_staleness,
    calculate_production_preflight,
    DEFAULTS_FILE,
)
import dumplayout
from xbotgo_core import sheet_sync_service

ROOT = os.environ.get("XBOTGO_ROOT") or os.path.dirname(TOOLS_DIR)
OUT_REVIEWED = os.path.join(ROOT, "out", "reviewed")

app = Flask(__name__, static_folder="static", static_url_path="")

# Track server process start time for stale-server detection
SERVER_START_TIME = time.time()

# In-memory background task registry for streaming logs
TASKS: Dict[str, Dict[str, Any]] = {}

TASK_LOGS_DIR = os.path.join(ROOT, "tmp", "task_logs")
os.makedirs(TASK_LOGS_DIR, exist_ok=True)
LAST_TASKS_FILE = os.path.join(TASK_LOGS_DIR, "last_tasks.json")


def get_last_tasks_map() -> Dict[str, str]:
    if os.path.exists(LAST_TASKS_FILE):
        try:
            with open(LAST_TASKS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            _swallowed()
    return {}


def record_last_task(key: str, task_id: str):
    m = get_last_tasks_map()
    m[key] = task_id
    for k in [k for k in m if k.startswith("test_game_")]:   # keys left behind by the unit tests
        del m[k]
    try:
        write_json_atomic(LAST_TASKS_FILE, m, indent=None)
    except Exception:
        _swallowed()


def run_cli(cmd, timeout):
    """subprocess.run for the short helper scripts (apply spec, make_run_all, organize): never hangs the request.
    On timeout returns a CompletedProcess-like result with returncode 124 and a clear stderr line."""
    try:
        return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", f"ERROR: timed out after {timeout}s: {os.path.basename(str(cmd[1]))}")


def start_background_task(cmd: List[str], cwd: str, task_name: str, on_complete=None, game_id: Optional[str] = None, task_type: str = "general") -> str:
    """Run a subprocess in a background thread and record output lines for streaming & disk persistence."""
    task_id = str(uuid.uuid4())[:8]
    log_path = os.path.join(TASK_LOGS_DIR, f"{task_id}.log")
    TASKS[task_id] = {
        "id": task_id,
        "name": task_name,
        "lines": [],
        "done": False,
        "exit_code": None,
        "error": None,
        "created_at": time.time(),
        "log_path": log_path,
        "game_id": game_id,
        "task_type": task_type,
    }

    if game_id:
        record_last_task(f"{game_id}_{task_type}", task_id)
        record_last_task(f"{game_id}_all", task_id)

    def run_proc():
        task = TASKS[task_id]
        cmd_str = " ".join(f'"{c}"' if " " in c else c for c in cmd)
        first_line = f"[{task_name}] Starting: {cmd_str}"
        task["lines"].append(first_line)
        try:
            with open(log_path, "w", encoding="utf-8") as lf:
                lf.write(first_line + "\n")
        except Exception:
            _swallowed()

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=dict(os.environ, PYTHONUNBUFFERED="1"),  # live progress lines in the modal
                text=True,
                bufsize=1,
                universal_newlines=True,
            )
            for line in proc.stdout:
                clean_line = line.rstrip()
                task["lines"].append(clean_line)
                try:
                    with open(log_path, "a", encoding="utf-8") as lf:
                        lf.write(clean_line + "\n")
                except Exception:
                    _swallowed()
            proc.wait()
            has_fatal_error = any("ERROR: Re-cut finished with errors" in l or l.startswith("ERROR:") for l in task["lines"])
            proc_code = 1 if (proc.returncode == 0 and has_fatal_error) else proc.returncode
            task["exit_code"] = proc_code
            task["done"] = True

            fin_msg = f"[{task_name}] Process finished successfully." if proc_code == 0 else f"[{task_name}] Process exited with error code {proc_code}."
            task["lines"].append(fin_msg)
            try:
                with open(log_path, "a", encoding="utf-8") as lf:
                    lf.write(fin_msg + "\n")
            except Exception:
                _swallowed()

            if proc_code == 0 and on_complete:
                try:
                    on_complete()
                except Exception as ex:
                    task["lines"].append(f"[{task_name}] Post-processing error: {ex}")
                    task["error"] = str(ex)
        except Exception as e:
            task["done"] = True
            task["exit_code"] = -1
            task["error"] = str(e)
            err_msg = f"[{task_name}] Execution failed: {e}"
            task["lines"].append(err_msg)
            try:
                with open(log_path, "a", encoding="utf-8") as lf:
                    lf.write(err_msg + "\n")
            except Exception:
                _swallowed()

    t = threading.Thread(target=run_proc, daemon=True)
    t.start()
    return task_id


def start_background_pipeline(commands: List[List[str]], cwd: str, task_name: str, game_id: Optional[str] = None, task_type: str = "zoom") -> str:
    """Run a pipeline of subprocess commands in sequence, streaming logs until complete or failed."""
    task_id = str(uuid.uuid4())[:8]
    log_path = os.path.join(TASK_LOGS_DIR, f"{task_id}.log")
    TASKS[task_id] = {
        "id": task_id,
        "name": task_name,
        "lines": [],
        "done": False,
        "exit_code": None,
        "error": None,
        "created_at": time.time(),
        "log_path": log_path,
        "game_id": game_id,
        "task_type": task_type,
    }

    if game_id:
        record_last_task(f"{game_id}_{task_type}", task_id)
        record_last_task(f"{game_id}_all", task_id)

    def run_pipeline():
        task = TASKS[task_id]
        overall_exit = 0
        has_critical_failure = False

        for i, cmd in enumerate(commands, 1):
            run_cmd = list(cmd)
            if run_cmd and ("python" in os.path.basename(run_cmd[0]).lower()) and "-u" not in run_cmd:
                run_cmd.insert(1, "-u")
            cmd_str = " ".join(f'"{c}"' if " " in c else str(c) for c in run_cmd)
            step_header = f"[{task_name}] Step {i}/{len(commands)}: {cmd_str}"
            task["lines"].append(step_header)
            try:
                with open(log_path, "a", encoding="utf-8") as lf:
                    lf.write(step_header + "\n")
            except Exception:
                _swallowed()

            try:
                proc = subprocess.Popen(
                    run_cmd,
                    cwd=cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=dict(os.environ, PYTHONUNBUFFERED="1"),
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                )
                for line in proc.stdout:
                    clean_line = line.rstrip()
                    task["lines"].append(clean_line)
                    is_missing = "MISSING" in clean_line
                    is_budget = "budget reached" in clean_line
                    is_flagged = bool(re.search(r'\b[1-9]\d*\s*flagged\b', clean_line, re.IGNORECASE) or clean_line.startswith("FLAGGED:"))
                    if (is_missing or is_budget or is_flagged) and not ("0 flagged" in clean_line):
                        has_critical_failure = True
                    try:
                        with open(log_path, "a", encoding="utf-8") as lf:
                            lf.write(clean_line + "\n")
                    except Exception:
                        _swallowed()
                proc.wait()
                if proc.returncode != 0:
                    err_step = f"[{task_name}] Step {i} exited with error code {proc.returncode}"
                    task["lines"].append(err_step)
                    overall_exit = proc.returncode
                    break
            except Exception as e:
                err_fail = f"[{task_name}] Step {i} failed: {e}"
                task["lines"].append(err_fail)
                overall_exit = -1
                task["error"] = str(e)
                break

        if overall_exit == 0 and has_critical_failure:
            overall_exit = 1
            task["error"] = "Verification reported missing or unrendered clips"

        task["exit_code"] = overall_exit
        task["done"] = True

        if overall_exit == 0:
            fin_text = f"[{task_name}] All steps completed successfully."
        else:
            fin_text = f"[{task_name}] Pipeline stopped with error code {overall_exit} (verify or render issues detected)."
        task["lines"].append(fin_text)
        try:
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(fin_text + "\n")
        except Exception:
            _swallowed()

    t = threading.Thread(target=run_pipeline, daemon=True)
    t.start()
    return task_id


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/games", methods=["GET"])
def list_games():
    """List all games that have a reviewed CSV."""
    pattern = os.path.join(OUT_REVIEWED, "*_reviewed.csv")
    csv_paths = sorted(glob.glob(pattern), reverse=True)
    games = []

    for path in csv_paths:
        fname = os.path.basename(path)
        game_id = fname.replace("_reviewed.csv", "")
        display_name = game_id
        if game_id.startswith("2026-"):
            parts = game_id.split("-")
            if len(parts) >= 3:
                display_name = f"{parts[1]}-{parts[2]}"

        timeline = find_timeline_for_game(game_id)
        if timeline and "teams" in timeline:
            teams = " v ".join(timeline["teams"][:2])
            display_name = f"{display_name} ({teams})"

        games.append({
            "id": game_id,
            "name": display_name,
            "filename": fname,
            "has_timeline": timeline is not None,
        })

    return jsonify({"games": games})


@app.route("/api/build-info", methods=["GET"])
def get_build_info():
    """Return server startup time and newest file mtime to detect stale server processes."""
    tracked_files = [
        os.path.abspath(__file__),
        os.path.join(ROOT, "tools", "editor", "csv_io.py"),
        os.path.join(ROOT, "tools", "editor", "sheet_sync_service.py"),
        os.path.join(ROOT, "tools", "editor", "static", "app.js"),
        os.path.join(ROOT, "tools", "editor", "static", "app.css"),
        os.path.join(ROOT, "tools", "editor", "static", "index.html"),
        os.path.join(ROOT, "tools", "editor", "static", "zoom.html"),
        os.path.join(ROOT, "tools", "editor", "static", "zoom.js"),
        os.path.join(ROOT, "tools", "editor", "static", "zoom.css"),
    ]
    mtimes = []
    for f in tracked_files:
        if os.path.exists(f):
            mtimes.append(os.path.getmtime(f))
    latest_mtime = max(mtimes) if mtimes else SERVER_START_TIME
    is_stale = (latest_mtime > SERVER_START_TIME + 2.0)
    return jsonify({
        "server_start": SERVER_START_TIME,
        "server_start_str": datetime.datetime.fromtimestamp(SERVER_START_TIME).strftime("%H:%M:%S"),
        "server_start_datetime": datetime.datetime.fromtimestamp(SERVER_START_TIME).strftime("%Y-%m-%d %H:%M:%S"),
        "latest_mtime": latest_mtime,
        "is_stale": is_stale,
        "build_time_str": datetime.datetime.fromtimestamp(latest_mtime).strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.route("/api/calendar/available-dates", methods=["GET"])
def get_available_dates():
    """Return dates with reviewed CSVs, out directories, or source dumps for the calendar,

    including format validation status and hover hints for legacy data.
    """
    all_dates = set()

    # 1. Dates in out/reviewed
    for p in glob.glob(os.path.join(OUT_REVIEWED, "*_reviewed.csv")):
        fn = os.path.basename(p)
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", fn)
        if m:
            all_dates.add(m.group(1))

    # 2. Dates in raw dump folders in repo root
    dump_folder_dates = set()
    for entry in os.listdir(ROOT):
        p = os.path.join(ROOT, entry)
        if os.path.isdir(p) and not entry.startswith((".", "_", "tools", "utils", "shared", "tmp", "xbotgo_app", "out")):
            try:
                vdir = dumplayout.find_video_dir(p)
                if vdir:
                    for f in os.listdir(vdir):
                        m = re.match(r"^(\d{4}-\d{2}-\d{2})", f)
                        if m:
                            dump_folder_dates.add(m.group(1))
                            all_dates.add(m.group(1))
            except Exception:
                _swallowed()

    # 3. Dates in out/ directory
    out_dir = os.path.join(ROOT, "out")
    if os.path.isdir(out_dir):
        for entry in os.listdir(out_dir):
            m = re.match(r"^(\d{4}-\d{2}-\d{2})", entry)
            if m:
                all_dates.add(m.group(1))

    date_entries = []
    reviewed_dates = []
    dump_dates = []
    out_dates = []

    for d in sorted(list(all_dates), reverse=True):
        rev_path = os.path.join(OUT_REVIEWED, f"{d}_reviewed.csv")
        has_rev = os.path.exists(rev_path)

        matching_out = []
        if os.path.isdir(out_dir):
            matching_out = [e for e in os.listdir(out_dir) if e.startswith(d)]

        is_multi_game = len(matching_out) > 1

        # Check candidate review.csv in out/
        has_valid_out_csv = False
        invalid_cols_count = None
        for mo in matching_out:
            for sub in ["review.csv", os.path.join("work", "review.csv")]:
                cp = os.path.join(out_dir, mo, sub)
                if os.path.exists(cp):
                    is_valid, n_cols = check_csv_validity(cp)
                    if is_valid:
                        has_valid_out_csv = True
                    else:
                        invalid_cols_count = n_cols

        has_dump = d in dump_folder_dates

        if has_rev:
            is_valid_rev, rev_cols = check_csv_validity(rev_path)
            if is_valid_rev:
                reviewed_dates.append(d)
                date_entries.append({
                    "date": d,
                    "status": "reviewed",
                    "enabled": True,
                    "hint": "Reviewed CSV available (ready to open)",
                })
            else:
                date_entries.append({
                    "date": d,
                    "status": "unsupported",
                    "enabled": False,
                    "hint": f"Legacy {rev_cols}-column format in reviewed table; not supported in Review Editor.",
                })
        elif is_multi_game:
            sub_str = ", ".join(matching_out)
            date_entries.append({
                "date": d,
                "status": "unsupported",
                "enabled": False,
                "hint": f"Multi-game day ({sub_str}); multi-game days are not yet supported.",
            })
        elif has_dump:
            dump_dates.append(d)
            date_entries.append({
                "date": d,
                "status": "dump",
                "enabled": True,
                "hint": "Video dump detected (ready to auto-generate review table)",
            })
        elif has_valid_out_csv:
            out_dates.append(d)
            date_entries.append({
                "date": d,
                "status": "importable",
                "enabled": True,
                "hint": "Current 16-column review table found (ready to import)",
            })
        elif invalid_cols_count is not None:
            date_entries.append({
                "date": d,
                "status": "unsupported",
                "enabled": False,
                "hint": f"Legacy {invalid_cols_count}-column format; not supported in Review Editor.",
            })
        else:
            date_entries.append({
                "date": d,
                "status": "unsupported",
                "enabled": False,
                "hint": "Legacy game data (lacks 16-column review table); not supported.",
            })

    return jsonify({
        "reviewed_dates": reviewed_dates,
        "dump_dates": dump_dates,
        "out_dates": out_dates,
        "dates": date_entries,
    })


@app.route("/api/game/find-or-generate", methods=["POST"])
def find_or_generate_game():
    """Check if reviewed CSV exists for date; if not, find dump and run review_from_log.py."""
    data = request.get_json(silent=True) or {}
    date_iso = (data.get("date") or "").strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_iso):
        abort(400, description="Valid date (YYYY-MM-DD) required")

    csv_path = os.path.join(OUT_REVIEWED, f"{date_iso}_reviewed.csv")
    if os.path.exists(csv_path):
        is_val, n_cols = check_csv_validity(csv_path)
        if not is_val:
            return jsonify({
                "status": "unsupported",
                "message": f"Cannot open {date_iso}: existing reviewed table has legacy format ({n_cols} columns). Only current 16-column tables are supported.",
            })
        return jsonify({
            "status": "exists",
            "game_id": date_iso,
            "message": f"Reviewed CSV already exists for {date_iso}.",
        })

    # Check for multi-game day
    out_dir = os.path.join(ROOT, "out")
    if os.path.isdir(out_dir):
        matching_out = [e for e in os.listdir(out_dir) if e.startswith(date_iso)]
        if len(matching_out) > 1:
            return jsonify({
                "status": "unsupported",
                "message": f"Multi-game day detected ({', '.join(matching_out)}); multi-game days are not yet supported.",
            })

    # Look for existing review.csv in out/<date_iso>/
    candidate_out_review = os.path.join(ROOT, "out", date_iso, "review.csv")
    candidate_work_review = os.path.join(ROOT, "out", date_iso, "work", "review.csv")
    source_review_csv = None
    if os.path.exists(candidate_out_review):
        source_review_csv = candidate_out_review
    elif os.path.exists(candidate_work_review):
        source_review_csv = candidate_work_review

    if source_review_csv:
        is_val, n_cols = check_csv_validity(source_review_csv)
        if not is_val:
            return jsonify({
                "status": "unsupported",
                "message": f"Cannot import {date_iso}: legacy format detected ({n_cols} columns). Only current 16-column tables are supported.",
            })
        headers, rows = csv_io.read_reviewed_csv(source_review_csv)
        csv_io.write_reviewed_csv(csv_path, headers, rows, create_backup=False)
        return jsonify({
            "status": "imported",
            "game_id": date_iso,
            "message": f"Imported existing review.csv for {date_iso}.",
        })

    # Find dump folder
    dump_folder = find_game_dump_folder(date_iso)
    if not dump_folder:
        return jsonify({
            "status": "not_found",
            "message": f"No video dump or supported 16-column review table found for {date_iso}.",
        })

    # Generate via review_from_log.py
    out_dir_match = os.path.join(ROOT, "out", date_iso)
    os.makedirs(out_dir_match, exist_ok=True)
    out_csv = os.path.join(out_dir_match, "review.csv")

    cmd = [
        sys.executable,
        os.path.join(PIPELINE_DIR, "review_from_log.py"),
        "--day", os.path.basename(dump_folder),
        "--out", out_csv,
    ]

    def on_generator_complete():
        if os.path.exists(out_csv):
            headers, rows = csv_io.read_reviewed_csv(out_csv)
            csv_io.write_reviewed_csv(csv_path, headers, rows, create_backup=False)

    task_id = start_background_task(
        cmd=cmd,
        cwd=ROOT,
        task_name=f"Generate CSV ({date_iso})",
        on_complete=on_generator_complete,
    )

    return jsonify({
        "status": "started",
        "task_id": task_id,
        "game_id": date_iso,
        "dump_folder": os.path.basename(dump_folder),
    })


@app.route("/shared/<path:filename>", methods=["GET"])
def serve_shared(filename: str):
    """Serve static files from shared/ directory (team logos, etc.)."""
    shared_dir = os.path.join(ROOT, "shared")
    return send_from_directory(shared_dir, filename)


@app.route("/api/logos", methods=["GET"])
def get_logos_endpoint():
    """Return list of available team logos in shared/team_logos/."""
    return jsonify({"logos": get_available_logos()})


@app.route("/api/game/<game_id>/info", methods=["GET"])
def get_game_info_endpoint(game_id: str):
    """Get current game_info.json plus list of all available team logos for setup wizard."""
    return jsonify({
        "game_id": game_id,
        "game_info": load_game_info(game_id),
        "logos": get_available_logos()
    })


@app.route("/api/game/<game_id>/last-task", methods=["GET"])
def get_game_last_task(game_id: str):
    """Retrieve last task ID, metadata, and logs for a game (survives tab close and server restart)."""
    task_type = request.args.get("type", "all")
    m = get_last_tasks_map()
    task_id = m.get(f"{game_id}_{task_type}") or m.get(f"{game_id}_all")
    if not task_id:
        return jsonify({"has_task": False})

    task = TASKS.get(task_id)
    lines = []
    if task:
        lines = task["lines"]
        name = task["name"]
        done = task["done"]
        exit_code = task["exit_code"]
    else:
        log_path = os.path.join(TASK_LOGS_DIR, f"{task_id}.log")
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = [ln.rstrip() for ln in f]
            except Exception:
                _swallowed()
        name = "Previous Task"
        done = True
        exit_code = 0

    return jsonify({
        "has_task": True,
        "task_id": task_id,
        "task_name": name,
        "done": done,
        "exit_code": exit_code,
        "lines": lines
    })


@app.route("/api/upload-logo", methods=["POST"])
def upload_logo():
    """Upload a new team or league logo into shared/team_logos/."""
    if "file" not in request.files:
        return jsonify({"error": "no_file", "message": "No file uploaded"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "empty_filename", "message": "Filename is empty"}), 400

    # Sanitize filename
    clean_name = os.path.basename(file.filename)
    clean_name = re.sub(r"[^\w\s\-\.\(\)]", "", clean_name).strip()
    if not clean_name:
        return jsonify({"error": "invalid_filename", "message": "Invalid filename"}), 400

    ext = os.path.splitext(clean_name)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg"):
        return jsonify({"error": "invalid_extension", "message": "Only PNG, JPG, and JPEG images are supported"}), 400

    target_dir = os.path.join(ROOT, "shared", "team_logos")
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, clean_name)
    rel_path = f"shared/team_logos/{clean_name}"

    overwrite = request.form.get("overwrite") == "true"
    if os.path.exists(target_path) and not overwrite:
        return jsonify({
            "exists": True,
            "filename": clean_name,
            "path": rel_path,
            "message": f"A logo named '{clean_name}' already exists. Overwrite?"
        })

    file.save(target_path)
    return jsonify({
        "success": True,
        "filename": clean_name,
        "path": rel_path
    })


@app.route("/api/game/<game_id>/info", methods=["POST"])
def save_game_info_endpoint(game_id: str):
    """Save updated game_info.json for a game, validate fields, propagate match name to CSV."""
    data = request.get_json(force=True)
    if not data or not isinstance(data, dict):
        abort(400, description="Invalid game_info payload")

    home = (data.get("home") or "").strip()
    opponent = (data.get("opponent") or "").strip()
    if not home:
        abort(400, description="Home team name cannot be empty")
    if not opponent:
        abort(400, description="Opponent/Away team name cannot be empty")

    score = (data.get("score") or "").strip()
    halftime_score = (data.get("halftime_score") or "").strip()
    if score and not re.match(r"^\d+\s*-\s*\d+$", score):
        abort(400, description="Invalid score format (expected 'H - A', e.g. '3 - 1')")
    if halftime_score and not re.match(r"^\d+\s*-\s*\d+$", halftime_score):
        abort(400, description="Invalid halftime score format (expected 'H - A', e.g. '1 - 0')")

    _defs = load_game_defaults()
    home_logo = (data.get("home_logo") or _defs.get("team_logo") or "").strip()
    away_logo = (data.get("away_logo") or "").strip() or None
    league = (data.get("league") or _defs["league"]).strip()
    league_logo = (data.get("league_logo") or _defs.get("league_logo") or "").strip()

    # Validate logos exist on disk if specified
    if home_logo and not os.path.exists(os.path.join(ROOT, home_logo)):
        abort(400, description=f"Home logo file not found: {home_logo}")
    if away_logo and not os.path.exists(os.path.join(ROOT, away_logo)):
        abort(400, description=f"Away logo file not found: {away_logo}")
    if league_logo and not os.path.exists(os.path.join(ROOT, league_logo)):
        abort(400, description=f"League logo file not found: {league_logo}")

    target_path = find_game_info_path(game_id, create_dir_if_missing=True)
    if not target_path:
        abort(404, description=f"Could not resolve out directory for game {game_id}")

    prev_gi = load_game_info(game_id) or {}

    # Match name for game column (e.g. "2026-03-29 Home FC v Guest FC")
    match_name = (data.get("match_name") or "").strip()
    if not match_name:
        match_name = f"{game_id} {home} v {opponent}"

    # Build clean game_info
    gi = {
        "league": league,
        "league_logo": league_logo,
        "home": home,
        "home_logo": home_logo,
        "date": data.get("date") or "",
        "opponent": opponent,
        "away_logo": away_logo,
        "score": score,
        "halftime_score": halftime_score,
        "match_name": match_name
    }

    # Detect if changes make existing title cards or reels stale
    diff_keys = [k for k in ("home", "opponent", "score", "halftime_score", "home_logo", "away_logo", "league", "league_logo") if prev_gi.get(k) != gi.get(k)]
    gdir = resolve_game_out(game_id)
    cards_exist = bool(gdir and os.path.exists(os.path.join(gdir, "clips", "cards", "000_intro.mp4")))
    cards_stale = bool(diff_keys and cards_exist)

    # Save to primary location
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    write_json_atomic(target_path, gi, indent=1)

    # If a work directory exists, also keep work/game_info.json in sync
    if gdir:
        work_gi = os.path.join(gdir, "work", "game_info.json")
        if os.path.exists(os.path.dirname(work_gi)) and os.path.abspath(work_gi) != os.path.abspath(target_path):
            try:
                write_json_atomic(work_gi, gi, indent=1)
            except Exception:
                _swallowed()


    # Propagate match_name to CSV "game" column
    csv_path = Game(gdir).csv if gdir else os.path.join(OUT_REVIEWED, f"{game_id}_reviewed.csv")
    if os.path.exists(csv_path):
        try:
            headers, rows = csv_io.read_reviewed_csv(csv_path)
            if "game" in headers:
                changed = False
                for r in rows:
                    if r.get("game") != match_name:
                        r["game"] = match_name
                        changed = True
                if changed:
                    csv_io.write_reviewed_csv(csv_path, headers, rows, create_backup=True)
        except Exception as e:
            print(f"Error updating CSV game column: {e}")

    return jsonify({
        "status": "saved",
        "game_id": game_id,
        "game_info": gi,
        "cards_stale": cards_stale,
        "match_name": match_name,
        "revision": csv_revision(csv_path) if os.path.exists(csv_path) else "",
    })


def _default_player() -> str:
    return load_game_defaults()["featured_players"][0]


@app.route("/api/defaults", methods=["GET"])
def get_defaults_endpoint():
    """Get current global game and workflow defaults."""
    return jsonify(load_game_defaults())


@app.route("/api/defaults", methods=["POST"])
def save_defaults_endpoint():
    """Save global game and workflow defaults to config/game_defaults.json."""
    data = request.get_json(force=True)
    if not data or not isinstance(data, dict):
        abort(400, description="Invalid payload for defaults")

    cur = load_game_defaults()
    if "team_name" in data:
        cur["team_name"] = str(data["team_name"]).strip()
    if "is_home" in data:
        cur["is_home"] = bool(data["is_home"])
    if "team_logo" in data:
        t_logo = str(data["team_logo"]).strip()
        if t_logo and not os.path.exists(os.path.join(ROOT, t_logo)):
            abort(400, description=f"Team logo file not found: {t_logo}")
        cur["team_logo"] = t_logo
    if "league" in data:
        cur["league"] = str(data["league"]).strip()
    if "league_logo" in data:
        l_logo = str(data["league_logo"]).strip()
        if l_logo and not os.path.exists(os.path.join(ROOT, l_logo)):
            abort(400, description=f"League logo file not found: {l_logo}")
        cur["league_logo"] = l_logo
    if "leagues" in data:
        from xbotgo_core import app_config as _ac
        lg = _ac._clean_leagues(data["leagues"])
        for e in lg:
            if e["logo"] and not os.path.exists(os.path.join(ROOT, e["logo"])):
                abort(400, description=f"League logo file not found: {e['logo']}")
        if lg:
            cur["leagues"] = lg
    if "guest_name" in data:
        cur["guest_name"] = str(data["guest_name"]).strip() or cur.get("guest_name", "Guest FC")
    if "featured_players" in data:
        fps = data["featured_players"]
        if isinstance(fps, str):
            fps = [p.strip() for p in fps.split(",") if p.strip()]
        elif isinstance(fps, list):
            fps = [str(p).strip() for p in fps if str(p).strip()]
        cur["featured_players"] = fps or load_game_defaults()["featured_players"]
    if "sheet_id" in data:
        cur["sheet_id"] = str(data["sheet_id"]).strip()

    os.makedirs(os.path.dirname(DEFAULTS_FILE), exist_ok=True)
    write_json_atomic(DEFAULTS_FILE, cur, indent=2)

    return jsonify({"status": "saved", "defaults": cur})


def csv_revision(path: str) -> str:
    """Cheap change marker of the reviewed CSV (mtime + size). Used to refuse a save that would overwrite
    edits made after this page loaded the file (second browser tab, zoom editor 'Remove zoom', manual edit)."""
    try:
        st = os.stat(path)
        return f"{st.st_mtime_ns}-{st.st_size}"
    except OSError:
        return ""


@app.route("/api/game/<game_id>", methods=["GET"])
def get_game(game_id: str):
    """Load reviewed CSV and segment videos for a game."""
    out_dir = resolve_game_out(game_id)
    csv_path = Game(out_dir).csv if (out_dir and os.path.exists(Game(out_dir).csv)) else os.path.join(OUT_REVIEWED, f"{game_id}_reviewed.csv")
    if not os.path.exists(csv_path):
        abort(404, description=f"Game reviewed CSV not found: {game_id}")

    headers, rows = csv_io.read_reviewed_csv(csv_path)
    timeline = find_timeline_for_game(game_id)
    clips = csv_io.compute_clip_numbers(rows)

    video_files = set()
    enriched_rows = []
    for i, r in enumerate(rows):
        f = (r.get("file") or "").strip()
        if f:
            video_files.add(f)

        valid_order, warn_msg = time_utils.validate_timing_order(
            r.get("action_start"), r.get("event"), r.get("action_end")
        )

        row_copy = dict(r)
        row_copy["clip"] = clips[i]
        row_copy["_row_index"] = i
        row_copy["_order_valid"] = valid_order
        row_copy["_order_warning"] = warn_msg
        row_copy["_is_skipped"] = csv_io.is_row_skipped(r.get("instructions"), r.get("skip"))
        enriched_rows.append(row_copy)

    videos_map = {}
    for vf in video_files:
        videos_map[vf] = resolve_video_info(vf, timeline)

    return jsonify({
        "game_id": game_id,
        "headers": headers,
        "rows": enriched_rows,
        "videos": videos_map,
        "game_info": load_game_info(game_id),
        "csv_path": os.path.relpath(csv_path, ROOT).replace("\\", "/"),
        "revision": csv_revision(csv_path),
    })


@app.route("/api/game/<game_id>", methods=["PUT"])
def save_game(game_id: str):
    """Save updated CSV rows atomically with backup and optional auto-push to Google Sheet."""
    out_dir = resolve_game_out(game_id)
    csv_path = Game(out_dir).csv if (out_dir and os.path.exists(Game(out_dir).csv)) else os.path.join(OUT_REVIEWED, f"{game_id}_reviewed.csv")
    if not os.path.exists(csv_path):
        abort(404, description=f"Game CSV not found: {game_id}")

    data = request.get_json(force=True)
    if not data or "rows" not in data or "headers" not in data:
        abort(400, description="Invalid payload: headers and rows required")

    headers = data["headers"]
    rows = data["rows"]

    base_rev = data.get("base_revision")
    if base_rev and not data.get("force") and base_rev != csv_revision(csv_path):
        return jsonify({
            "status": "conflict", "success": False, "error": "stale_save",
            "message": "The reviewed CSV changed on disk after this page loaded it (another tab, the zoom editor or a manual edit).",
        }), 409

    clean_rows = []
    for r in rows:
        c = {}
        for h in headers:
            c[h] = r.get(h, "")
        clean_rows.append(c)

    try:
        csv_io.write_reviewed_csv(csv_path, headers, clean_rows, create_backup=True)
    except Exception as e:
        abort(500, description=f"Failed to save CSV: {str(e)}")

    new_clips = csv_io.compute_clip_numbers(clean_rows)

    sheet_result = None
    has_invalid_timings = False
    for r in clean_rows:
        if not csv_io.is_row_skipped(r.get("instructions"), r.get("skip")):
            is_valid, _ = time_utils.validate_timing_order(r.get("action_start"), r.get("event"), r.get("action_end"))
            if not is_valid:
                has_invalid_timings = True
                break

    should_push = bool(data.get("sync_sheet") or data.get("auto_push") or data.get("should_push_sheet"))
    if should_push and not has_invalid_timings:
        try:
            for i, r in enumerate(clean_rows):
                r["clip"] = new_clips[i]
            sheet_result = sheet_sync_service.push_to_google_sheet(game_id, headers, clean_rows)
        except Exception as e:
            sheet_result = {"success": False, "error": str(e), "message": str(e)}
    elif should_push and has_invalid_timings:
        sheet_result = {
            "success": False,
            "error": "invalid_timings_exist",
            "message": "Skipped sheet push: blocked because table contains invalid timing rows (e.g. End before Event). Fix times before pushing."
        }

    return jsonify({
        "status": "saved",
        "success": True,
        "revision": csv_revision(csv_path),
        "rows_count": len(clean_rows),
        "clips": new_clips,
        "sheet": sheet_result,
        "sheet_result": sheet_result,
    })


@app.route("/api/sheet/push/<game_id>", methods=["POST"])
def push_sheet(game_id: str):
    """Explicitly push the ENTIRE reviewed table to Google Sheet."""
    csv_path = os.path.join(OUT_REVIEWED, f"{game_id}_reviewed.csv")
    if not os.path.exists(csv_path):
        abort(404, description=f"Game CSV not found: {game_id}")

    data = request.get_json(silent=True) or {}
    headers = data.get("headers")
    rows = data.get("rows")

    if not headers or not rows:
        headers, rows = csv_io.read_reviewed_csv(csv_path)

    clips = csv_io.compute_clip_numbers(rows)
    for i, r in enumerate(rows):
        r["clip"] = clips[i]

    try:
        res = sheet_sync_service.push_to_google_sheet(game_id, headers, rows)
        return jsonify(res)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def is_pid_running(pid: int) -> bool:
    """Check if process with given PID is still active on Windows."""
    if not pid or pid <= 0:
        return False
    if os.name != "nt":
        # POSIX: signal 0 probes existence; reap zombies of our own children first.
        try:
            os.waitpid(pid, os.WNOHANG)
        except Exception:
            _swallowed()
        try:
            os.kill(pid, 0)
            return True
        except PermissionError:
            return True
        except Exception:
            return False
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return exit_code.value == STILL_ACTIVE
    except Exception:
        try:
            out = subprocess.check_output(f'tasklist /FI "PID eq {pid}" /NH', shell=True, text=True)
            return str(pid) in out
        except Exception:
            return False


def get_production_pid_and_status(game_id: str):
    """Retrieve PID, status, and recent log lines for 4K final production."""
    out_dir = resolve_game_out(game_id)
    if not out_dir:
        return None, "idle", [], None
    base_name = os.path.basename(out_dir)
    day = base_name[:10] if len(base_name) >= 10 and base_name[4] == "-" and base_name[7] == "-" else base_name
    pid_file = os.path.join(out_dir, f"run_everything_{day}.pid")
    log_file = os.path.join(out_dir, f"run_everything_{day}.log")

    pid = None
    if os.path.exists(pid_file):
        try:
            with open(pid_file, "r", encoding="utf-8") as f:
                c = f.read().strip()
                if c.isdigit():
                    pid = int(c)
        except Exception:
            _swallowed()

    log_lines = []
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                log_lines = [line.rstrip() for line in f.readlines()[-100:]]
        except Exception:
            _swallowed()

    is_running = is_pid_running(pid) if pid else False
    if is_running and log_lines:
        # The run is over when the final check has printed its last line ("ALL OK" or "N file(s) to look at") into THIS run's log
        # (log newer than the pid file); the console window then waits ~20 s (timeout in the .bat), which must not keep the status "running".
        try:
            fresh = os.path.getmtime(log_file) >= os.path.getmtime(pid_file)
        except OSError:
            fresh = False
        if fresh and any(l.strip() == "ALL OK" or "file(s) to look at" in l for l in log_lines):
            is_running = False
    if is_running:
        status = "running"
    elif any("[CANCELLED BY USER]" in l for l in log_lines):
        status = "cancelled"
    elif any("ALL DONE" in l for l in log_lines):
        status = "completed"
    elif any("errorlevel 1" in l for l in log_lines):
        status = "failed"
    elif pid is not None:
        status = "finished"
    else:
        status = "idle"

    return pid, status, log_lines, log_file


def is_production_running(game_id: str) -> bool:
    """Return True if 4K production is actively running for this game."""
    _, status, _, _ = get_production_pid_and_status(game_id)
    return status == "running"


@app.route("/api/recut/<game_id>", methods=["POST"])
def trigger_recut(game_id: str):
    """Run tools/pipeline/sync_game.py in --local mode without pulling or overwriting sheet."""
    if is_production_running(game_id):
        return jsonify({
            "error": "production_running",
            "message": "Final 4K Production is currently running in background. Re-cutting is locked until production finishes."
        }), 409

    out_dir = resolve_game_out(game_id)
    if not out_dir:
        abort(404, description=f"Match directory for {game_id} not found")

    cmd = [
        sys.executable,
        os.path.join(PIPELINE_DIR, "sync_game.py"),
        "--out", out_dir,
        "--local",
    ]

    task_id = start_background_task(
        cmd=cmd,
        cwd=ROOT,
        task_name=f"Re-cut ({game_id})",
    )

    return jsonify({
        "status": "started",
        "task_id": task_id,
        "out_dir": out_dir,
    })


@app.route("/api/roster", methods=["GET"])
def get_roster_endpoint():
    """Return team roster with cache metadata and optional Google Sheet sync verification."""
    check_remote = request.args.get("check_remote", "0") in ("1", "true", "yes")
    local_roster = load_roster()
    roster_path = os.path.join(ROOT, "out", "reviewed", "roster.csv")
    cached_at = None
    if os.path.exists(roster_path):
        mtime = os.path.getmtime(roster_path)
        cached_at = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

    is_in_sync = None
    remote_available = False
    remote_count = None
    if check_remote:
        remote = fetch_remote_roster()
        if remote is not None:
            remote_available = True
            remote_count = len(remote)
            if not local_roster:
                write_roster_local(remote)
                local_roster = remote
                is_in_sync = True
            else:
                is_in_sync = (normalize_roster(local_roster) == remote)

    return jsonify({
        "roster": local_roster,
        "is_in_sync": is_in_sync,
        "remote_available": remote_available,
        "cached_at": cached_at,
        "local_count": len(local_roster),
        "remote_count": remote_count
    })


@app.route("/api/roster/pull", methods=["POST"])
def pull_roster_endpoint():
    """Explicitly pull roster from Google Sheet and update local cache in exact sheet order."""
    remote = fetch_remote_roster()
    if remote is None:
        abort(502, description="Failed to connect to Google Sheet to pull roster.")

    try:
        write_roster_local(remote)
    except Exception as e:
        abort(500, description=f"Failed to update local roster cache: {e}")

    return jsonify({
        "success": True,
        "roster": remote,
        "count": len(remote),
        "message": f"Successfully pulled {len(remote)} players from Google Sheet and updated local cache."
    })


@app.route("/api/roster", methods=["POST", "PUT"])
def save_roster_endpoint():
    """Save updated roster locally to CSV and push to Google Sheet 'Roster' tab in exact order."""
    data = request.get_json(force=True)
    if not data or "roster" not in data or not isinstance(data["roster"], list):
        abort(400, description="Invalid roster payload: 'roster' array required")

    raw_roster = data["roster"]
    clean_roster = normalize_roster(raw_roster)

    # 1. Save locally with backup
    try:
        write_roster_local(clean_roster)
    except Exception as e:
        abort(500, description=f"Failed to write local roster.csv: {e}")

    # 2. Push to Google Sheet in exact order
    sheet_synced = False
    sheet_error = None
    try:
        push_roster_remote(clean_roster)
        sheet_synced = True
    except Exception as e:
        sheet_error = str(e)
        print(f"Error syncing roster to Google Sheet: {e}")

    return jsonify({
        "success": True,
        "sheet_synced": sheet_synced,
        "error": sheet_error,
        "roster": clean_roster,
        "message": f"Roster updated ({len(clean_roster)} players saved to disk and Google Sheet)." if sheet_synced else f"Roster saved locally ({len(clean_roster)} players), but Google Sheet sync failed: {sheet_error}"
    })


@app.route("/api/game/<game_id>/reels", methods=["POST"])
def trigger_generate_reels(game_id: str):
    """Run tools/pipeline/make_reels.py --out <game_dir> --stage <stage> --player <player> in background."""
    if is_production_running(game_id):
        return jsonify({
            "error": "production_running",
            "message": "Final 4K Production is currently running in background. Generating reels is locked until production finishes."
        }), 409

    out_dir = resolve_game_out(game_id)
    if not out_dir:
        abort(404, description=f"Match directory for {game_id} not found")

    data = request.get_json(silent=True) or {}
    player = str(data.get("player") or _default_player()).strip()
    stage = str(data.get("stage") or "all").strip()
    if stage not in ("all", "reels", "cards", "clips", "replays"):
        stage = "all"

    cmd = [
        sys.executable,
        os.path.join(PIPELINE_DIR, "make_reels.py"),
        "--out", out_dir,
        "--stage", stage,
        "--player", player,
    ]

    task_id = start_background_task(
        cmd=cmd,
        cwd=ROOT,
        task_name=f"Generate Reels ({game_id} #{player})",
    )

    return jsonify({
        "status": "started",
        "task_id": task_id,
        "out_dir": out_dir,
        "player": player,
        "stage": stage,
    })


@app.route("/api/game/<game_id>/cards", methods=["POST"])
def trigger_generate_cards(game_id: str):
    """Run tools/pipeline/make_reels.py --out <game_dir> --stage cards in background."""
    if is_production_running(game_id):
        return jsonify({
            "error": "production_running",
            "message": "Final 4K Production is currently running in background. Generating cards is locked until production finishes."
        }), 409

    out_dir = resolve_game_out(game_id)
    if not out_dir:
        abort(404, description=f"Match directory for {game_id} not found")

    cmd = [
        sys.executable,
        os.path.join(PIPELINE_DIR, "make_reels.py"),
        "--out", out_dir,
        "--stage", "cards",
    ]

    task_id = start_background_task(
        cmd=cmd,
        cwd=ROOT,
        task_name=f"Generate Cards ({game_id})",
    )

    return jsonify({
        "status": "started",
        "task_id": task_id,
        "out_dir": out_dir,
    })


@app.route("/api/tasks/<task_id>/stream", methods=["GET"])
def stream_task_events(task_id: str):
    """Server-Sent Events (SSE) stream for real-time process logs."""
    task = TASKS.get(task_id)
    if not task:
        abort(404, description="Task not found")

    def event_stream():
        last_idx = 0
        while True:
            lines = task["lines"]
            while last_idx < len(lines):
                line = lines[last_idx]
                last_idx += 1
                yield f"data: {json.dumps({'line': line, 'done': False})}\n\n"

            if task["done"]:
                yield f"data: {json.dumps({'done': True, 'exit_code': task['exit_code'], 'error': task['error']})}\n\n"
                break
            time.sleep(0.12)

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.route("/api/tasks/<task_id>/status", methods=["GET"])
def get_task_status(task_id: str):
    """Polling fallback for task logs."""
    task = TASKS.get(task_id)
    if not task:
        abort(404, description="Task not found")

    offset = int(request.args.get("offset", 0))
    lines = task["lines"][offset:]
    return jsonify({
        "id": task_id,
        "name": task["name"],
        "done": task["done"],
        "exit_code": task["exit_code"],
        "error": task["error"],
        "lines": lines,
        "next_offset": len(task["lines"]),
    })


@app.route("/api/video", methods=["GET"])
def stream_video():
    """Stream video with HTTP 206 Partial Content support."""
    rel_path = request.args.get("path")
    if not rel_path:
        abort(400, description="Missing path parameter")

    norm_path = os.path.normpath(rel_path)
    if norm_path.startswith("..") or os.path.isabs(norm_path):
        abort(403, description="Path traversal forbidden")

    abs_path = os.path.abspath(os.path.join(ROOT, norm_path))
    if not abs_path.startswith(os.path.abspath(ROOT)):
        abort(403, description="Access outside project directory forbidden")

    if not os.path.exists(abs_path):
        abort(404, description=f"Video file not found: {rel_path}")

    directory = os.path.dirname(abs_path)
    filename = os.path.basename(abs_path)

    return send_from_directory(directory, filename, conditional=True)


# ==============================================================================
# Zoom Editor Endpoints (ZOOM_EDITOR_SPEC.md Phase 1)
# ==============================================================================

@app.route("/zoom/<game_id>/<token_or_clip>", methods=["GET"])
def zoom_page(game_id: str, token_or_clip: str):
    """Serve the Zoom Replay Editor single-page application."""
    return app.send_static_file("zoom.html")


@app.route("/api/zoom/<game_id>", methods=["GET"])
def list_zoom_replays(game_id: str):
    """List all zoom replay candidates for a game with status."""
    out_dir = resolve_game_out(game_id)
    if not out_dir:
        abort(404, description=f"Game directory not found for {game_id}")
    return jsonify(get_zoom_replays_data(out_dir, game_id))


@app.route("/api/zoom/<game_id>/<token_or_clip>", methods=["GET"])
def get_zoom_replay_details(game_id: str, token_or_clip: str):
    """Get complete replay specification and source video info."""
    out_dir = resolve_game_out(game_id)
    if not out_dir:
        abort(404, description=f"Game directory not found for {game_id}")
    data = get_zoom_replay_details_data(out_dir, game_id, token_or_clip)
    if not data:
        abort(404, description=f"Replay not found for '{token_or_clip}' in game {game_id}")
    return jsonify(data)


@app.route("/api/zoom/<game_id>/auto-frame", methods=["POST"])
def auto_frame_zoom_replays(game_id: str):
    """Auto-frame replay(s) using standard soccer framing [1152, 450] at 2.5x (1536x864)."""
    out_dir = resolve_game_out(game_id)
    if not out_dir:
        abort(404, description=f"Game directory not found for {game_id}")
    data = request.get_json(silent=True) or {}
    token = data.get("token")
    all_unplaced = data.get("all_unplaced", False)
    res = auto_frame_zoom_replays_data(out_dir, token=token, all_unplaced=all_unplaced)
    return jsonify(res)



@app.route("/api/zoom/<game_id>/<token_or_clip>/prepare", methods=["POST"])
def prepare_zoom_homographies(game_id: str, token_or_clip: str):
    """Run zoom_clip.py --step h to compute homographies in background."""
    out_dir = resolve_game_out(game_id)
    if not out_dir:
        abort(404, description=f"Game directory not found for {game_id}")

    g = Game(out_dir)
    st = g.state()
    js_n, js_t = jobs_by_clip(g)

    tok = resolve_token(g, token_or_clip)
    if not tok:
        abort(404, description="Replay not found")

    r = st.get("replays", {}).get(tok)
    j = js_t.get(tok)
    if not r and not j:
        abort(404, description="Job not found")

    event = r["event"] if r else j["event"]
    src_path = r["path"] if r else j["path"]
    start = r["start"] if r and r.get("start") is not None else default_window(event, g.action_end(j))[0]
    dur = r["dur"] if r and r.get("dur") is not None else default_window(event, g.action_end(j))[1]
    crop = r["crop"] if r and r.get("crop") is not None else [1152, 648]
    crop_w = r.get("crop_w", 1280 if (r and r.get("crop") is not None) else 1536) if r else 1536

    r_eff = {
        "path": src_path,
        "event": event,
        "start": start,
        "dur": dur,
        "crop": crop,
        "crop_w": crop_w if crop_w != 1280 else None,
        "pan": r.get("pan") if r else None,
        "zoom_to": r.get("zoom_to") if r else None
    }
    key = sig(r_eff, 720)
    work = os.path.join(xb_env.tmp_for(g.out), "zw", f"{tok}_{hashlib.md5(key.encode()).hexdigest()[:8]}")
    os.makedirs(work, exist_ok=True)

    h_path = os.path.join(work, "H.json")
    if os.path.exists(h_path):
        return jsonify({"status": "ready", "work_dir": work})

    cmd = [
        PY, os.path.join(PIPELINE_DIR, "zoom_clip.py"),
        "--src", src_path,
        "--start", str(start),
        "--dur", str(dur),
        "--ref", str(event),
        "--crop", f"{crop[0]},{crop[1]},{crop_w}",
        "--ease", "0.6",
        "--height", "720",
        "--work", os.path.abspath(work),
        "--step", "h",
    ]
    task_id = start_background_task(cmd, ROOT, f"Prepare H.json {tok}")
    return jsonify({"status": "running", "task_id": task_id, "work_dir": work})


@app.route("/api/zoom/<game_id>/<token_or_clip>/homographies", methods=["GET"])
def get_zoom_homographies(game_id: str, token_or_clip: str):
    """Retrieve per-frame homography matrices for live canvas transform."""
    out_dir = resolve_game_out(game_id)
    if not out_dir:
        abort(404, description=f"Game directory not found for {game_id}")
    status_code, res = get_zoom_homographies_data(out_dir, token_or_clip)
    return jsonify(res), status_code


@app.route("/api/zoom/<game_id>/<token_or_clip>", methods=["PUT"])
def save_zoom_spec(game_id: str, token_or_clip: str):
    """Save replay spec atomically via zoom_edit.py apply."""
    out_dir = resolve_game_out(game_id)
    if not out_dir:
        abort(404, description=f"Game directory not found for {game_id}")
    spec = request.get_json(silent=True) or {}

    g = Game(out_dir)
    tok = resolve_token(g, token_or_clip)
    if not tok:
        abort(404, description="Replay not found")

    spec["token"] = tok
    tmp_dir = os.path.join(ROOT, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    spec_path = os.path.join(tmp_dir, f"spec_{tok}_{int(time.time()*1000)}.json")
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)

    cmd = [
        PY, os.path.join(PIPELINE_DIR, "zoom_edit.py"),
        "apply", tok,
        "--out", out_dir,
        "--spec", spec_path
    ]
    try:
        res = run_cli(cmd, 120)
    finally:
        if os.path.exists(spec_path):
            try:
                os.remove(spec_path)
            except OSError:
                pass
    if res.returncode != 0:
        return jsonify({"error": "Failed to apply spec", "output": res.stdout + res.stderr}), 500

    st = g.state()
    return jsonify({
        "status": "saved",
        "replay": st.get("replays", {}).get(tok),
        "output": res.stdout.strip(),
    })


@app.route("/api/zoom/<game_id>/<token_or_clip>/render", methods=["POST"])
def render_zoom(game_id: str, token_or_clip: str):
    """Execute background 720p render followed by verify_zoom.py edge/length check.
    
    Blocks rendering of unreviewed or unplaced clips. Never injects silent defaults.
    """
    if is_production_running(game_id):
        return jsonify({
            "error": "production_running",
            "message": "Final 4K Production is currently running in background. Zoom rendering is locked until production finishes."
        }), 409

    out_dir = resolve_game_out(game_id)
    if not out_dir:
        abort(404, description=f"Game directory not found for {game_id}")

    data = request.get_json(silent=True) or {}
    scope = data.get("scope", "current")
    spec = data.get("spec")
    reviewed_only = bool(data.get("reviewed_only", False))

    g = Game(out_dir)
    st = g.state()
    js_n, js_t = jobs_by_clip(g)
    tok = resolve_token(g, token_or_clip)

    pipeline = []
    tmp_dir = os.path.join(ROOT, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    if scope == "all":
        reps = st.get("replays", {})
        reviewed_clips = []
        unreviewed_clips = []

        for tok_c, j_c in sorted(js_t.items(), key=lambda kv: kv[1]["n"]):
            if is_zoom(j_c["row"]):
                r_c = reps.get(tok_c)
                is_rev = bool(r_c and r_c.get("reviewed") is True and r_c.get("crop") is not None)
                if is_rev:
                    reviewed_clips.append(j_c["n"])
                else:
                    unreviewed_clips.append({
                        "n": j_c["n"],
                        "token": tok_c,
                        "reason": "unreviewed" if (r_c and r_c.get("crop")) else "unplaced"
                    })

        # If there are unreviewed clips and reviewed_only wasn't explicitly chosen, block render
        if unreviewed_clips and not reviewed_only:
            return jsonify({
                "error": "unreviewed_clips_exist",
                "message": f"{len(unreviewed_clips)} of {len(reviewed_clips) + len(unreviewed_clips)} zoom clips are unreviewed or unplaced. Please review them or choose to render reviewed clips only.",
                "unreviewed_clips": unreviewed_clips,
                "reviewed_count": len(reviewed_clips),
                "total_count": len(reviewed_clips) + len(unreviewed_clips)
            }), 400

        if reviewed_only and not reviewed_clips:
            return jsonify({
                "error": "no_reviewed_clips",
                "message": "No reviewed zoom clips found to render."
            }), 400

        render_cmd = [
            PY, os.path.join(PIPELINE_DIR, "zoom_edit.py"), "render",
            "--out", out_dir, "--height", "720", "--budget", "100000"
        ]
        verify_cmd = [
            PY, os.path.join(PIPELINE_DIR, "verify_zoom.py"),
            "--out", out_dir, "--height", "720"
        ]

        if reviewed_only and reviewed_clips:
            clips_str = ",".join(str(n) for n in reviewed_clips)
            render_cmd.extend(["--only", clips_str])
            verify_cmd.extend(["--only", clips_str])
            task_name = f"Render {len(reviewed_clips)} reviewed zoom replays ({game_id})"
        else:
            task_name = f"Render all zoom replays ({game_id})"

        pipeline.append(render_cmd)
        pipeline.append(verify_cmd)
    else:
        if not tok:
            abort(404, description="Replay not found")
        clip_num = js_t[tok]["n"] if tok in js_t else st.get("replays", {}).get(tok, {}).get("n", 0)
        r = st.get("replays", {}).get(tok)

        # Block rendering single unreviewed clip unless spec is being provided in this request
        if not spec and (not r or not r.get("reviewed") or r.get("crop") is None):
            return jsonify({
                "error": "unreviewed_clip",
                "message": f"Clip {clip_num} ({tok}) has not been reviewed yet. Adjust the crop box and save the plan before rendering."
            }), 400

        if spec:
            spec["token"] = tok
            spec["reviewed"] = True
            spec_path = os.path.join(tmp_dir, f"spec_render_{tok}.json")
            with open(spec_path, "w", encoding="utf-8") as f:
                json.dump(spec, f, indent=2)
            pipeline.append([
                PY, os.path.join(PIPELINE_DIR, "zoom_edit.py"), "apply", tok,
                "--out", out_dir, "--spec", spec_path, "--render", "--height", "720"
            ])
        else:
            pipeline.append([
                PY, os.path.join(PIPELINE_DIR, "zoom_edit.py"), "apply", tok,
                "--out", out_dir, "--render", "--height", "720"
            ])
        pipeline.append([
            PY, os.path.join(PIPELINE_DIR, "verify_zoom.py"),
            "--out", out_dir, "--only", str(clip_num), "--height", "720"
        ])
        task_name = f"Render clip {clip_num} ({tok})"

    task_id = start_background_pipeline(pipeline, ROOT, task_name, game_id=game_id, task_type="zoom")
    return jsonify({"task_id": task_id, "scope": scope, "token": tok})


@app.route("/api/zoom/<game_id>/<token_or_clip>/remove", methods=["POST"])
def remove_zoom_from_clip(game_id: str, token_or_clip: str):
    """Remove 'zoom' instruction from this row in the review CSV (atomic with zoom_state.json)."""
    out_dir = resolve_game_out(game_id)
    if not out_dir:
        abort(404, description=f"Game directory not found for {game_id}")
    status_code, res = remove_zoom_replay_data(out_dir, token_or_clip)
    if status_code != 200:
        abort(status_code, description=res.get("error", "remove failed"))
    return jsonify(res)


@app.route("/api/zoom/<game_id>/<token_or_clip>/restore", methods=["POST"])
def restore_zoom_to_clip(game_id: str, token_or_clip: str):
    """Restore a previously removed zoom replay: adds 'zoom' back to CSV and moves replay from removed back to replays."""
    out_dir = resolve_game_out(game_id)
    if not out_dir:
        abort(404, description=f"Game directory not found for {game_id}")
    status_code, res = restore_zoom_replay_data(out_dir, token_or_clip)
    if status_code != 200:
        abort(status_code, description=res.get("error", "restore failed"))
    return jsonify(res)


@app.route("/api/game/<game_id>/production/preflight", methods=["GET"])
def production_preflight(game_id: str):
    """Run pre-flight validation checks before generating or starting 4K final production."""
    out_dir = resolve_game_out(game_id)
    if not out_dir:
        abort(404, description=f"Game directory not found for {game_id}")
    res = calculate_production_preflight(game_id, out_dir)
    from xbotgo_core.organize_service import is_tidied_dir
    # A tidied game (timeline in work/, finished videos in final/) is an archive: Start only re-checks it.
    res["tidied"] = bool(is_tidied_dir(out_dir) and glob.glob(os.path.join(out_dir, "final", "*_full_game*.mp4")))
    return jsonify(res)


@app.route("/api/game/<game_id>/production/rebuild-stale", methods=["POST"])
def production_rebuild_stale(game_id: str):
    """Rebuild only changed 4K replays and highlight reels in background."""
    out_dir = resolve_game_out(game_id)
    if not out_dir:
        abort(404, description=f"Game directory not found for {game_id}")

    if is_production_running(game_id):
        return jsonify({
            "error": "production_running",
            "message": "Final 4K production is actively running. Rebuild is locked until completion."
        }), 409

    data = request.get_json(silent=True) or {}
    player = str(data.get("player") or _default_player()).strip()

    cmd = [PY, os.path.join(PIPELINE_DIR, "make_reels.py"), "--out", out_dir, "--stage", "all", "--player", player]
    task_id = start_background_pipeline(
        commands=[cmd],
        cwd=ROOT,
        task_name=f"Rebuild Changed 4K Replays & Reels ({game_id})",
        game_id=game_id,
        task_type="production",
    )
    return jsonify({
        "status": "started",
        "task_id": task_id,
        "command": " ".join(cmd),
        "player": player,
    })


@app.route("/api/game/<game_id>/production/generate-bat", methods=["POST"])
def production_generate_bat(game_id: str):
    """Generate run_everything_<day>.bat for the game."""
    out_dir = resolve_game_out(game_id)
    if not out_dir:
        abort(404, description=f"Game directory not found for {game_id}")

    data = request.get_json(silent=True) or {}
    player = (data.get("player") or _default_player()).strip()
    base_name = os.path.basename(out_dir)
    day = base_name[:10] if len(base_name) >= 10 and base_name[4] == "-" and base_name[7] == "-" else base_name

    cmd = [PY, os.path.join(PIPELINE_DIR, "make_run_all.py"), "--out", out_dir, "--player", player]
    res = run_cli(cmd, 120)
    if res.returncode != 0:
        return jsonify({
            "error": "generate_bat_failed",
            "message": res.stderr or res.stdout or "Failed to generate batch file."
        }), 500

    bat_file = os.path.join(out_dir, f"run_everything_{day}.bat")
    if not os.path.exists(bat_file):
        return jsonify({
            "error": "bat_not_found",
            "message": f"Expected batch file {bat_file} was not created."
        }), 500

    command_to_run = f'cmd.exe /c "{bat_file}"' if os.name == "nt" else f'{PY} tools/pipeline/run_everything.py --day {day} --player {player}'
    return jsonify({
        "success": True,
        "bat_path": bat_file,
        "bat_rel": os.path.relpath(bat_file, ROOT),
        "command": command_to_run,
        "day": day,
        "player": player
    })


@app.route("/api/game/<game_id>/production/dry-run", methods=["POST"])
def production_dry_run(game_id: str):
    """Generate and return planned batch execution without modifying or running files."""
    out_dir = resolve_game_out(game_id)
    if not out_dir:
        abort(404, description=f"Game directory not found for {game_id}")

    data = request.get_json(silent=True) or {}
    player = (data.get("player") or _default_player()).strip()
    base_name = os.path.basename(out_dir)
    day = base_name[:10] if len(base_name) >= 10 and base_name[4] == "-" and base_name[7] == "-" else base_name

    cmd = [PY, os.path.join(PIPELINE_DIR, "make_run_all.py"), "--out", out_dir, "--player", player, "--dry-run"]
    res = run_cli(cmd, 120)
    return jsonify({
        "success": True,
        "dry_run": True,
        "day": day,
        "player": player,
        "output": res.stdout or res.stderr
    })


@app.route("/api/game/<game_id>/production/start", methods=["POST"])
def production_start(game_id: str):
    """Launch run_everything_<day>.bat detached in a visible new console window."""
    out_dir = resolve_game_out(game_id)
    if not out_dir:
        abort(404, description=f"Game directory not found for {game_id}")

    if is_production_running(game_id):
        return jsonify({
            "error": "already_running",
            "message": "Final 4K Production is already running."
        }), 400

    base_name = os.path.basename(out_dir)
    day = base_name[:10] if len(base_name) >= 10 and base_name[4] == "-" and base_name[7] == "-" else base_name
    bat_file = os.path.join(out_dir, f"run_everything_{day}.bat")
    if not os.path.exists(bat_file):
        return jsonify({
            "error": "bat_not_found",
            "message": f"Batch file {bat_file} not found. Generate it first."
        }), 400

    pid_file = os.path.join(out_dir, f"run_everything_{day}.pid")

    if os.name == "nt":
        # Launch detached in a new console window (visible to user, independent of editor)
        cmd = ["cmd.exe", "/c", bat_file]
        proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
    else:
        # Not Windows: the .bat is only a thin wrapper, start the same Python runner in its own session
        # (its own process group, so Cancel can kill the whole tree) with output to a console log.
        args_file = os.path.join(out_dir, f"run_everything_{day}.args.json")
        try:
            with open(args_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            meta = {}
        cmd = [PY, os.path.join(PIPELINE_DIR, "run_everything.py"), "--day", day, "--player", str(meta.get("player") or _default_player())]
        if int(meta.get("games") or 1) == 1:
            cmd += ["--out", out_dir]
        console_log = open(os.path.join(out_dir, f"run_everything_{day}.console.txt"), "ab")
        proc = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=console_log, stderr=subprocess.STDOUT,
                                start_new_session=True)

    with open(pid_file, "w", encoding="utf-8") as f:
        f.write(str(proc.pid))

    return jsonify({
        "success": True,
        "pid": proc.pid,
        "bat_path": bat_file,
        "day": day
    })


@app.route("/api/game/<game_id>/production/cancel", methods=["POST"])
def production_cancel(game_id: str):
    """Terminate the running 4K production batch and its child processes."""
    out_dir = resolve_game_out(game_id)
    if not out_dir:
        abort(404, description=f"Game directory not found for {game_id}")

    base_name = os.path.basename(out_dir)
    day = base_name[:10] if len(base_name) >= 10 and base_name[4] == "-" and base_name[7] == "-" else base_name
    pid_file = os.path.join(out_dir, f"run_everything_{day}.pid")
    log_file = os.path.join(out_dir, f"run_everything_{day}.log")

    if not os.path.exists(pid_file):
        return jsonify({"error": "not_running", "message": "No active production PID found."}), 400

    pid = None
    try:
        with open(pid_file, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
    except Exception:
        _swallowed()

    if pid and is_pid_running(pid):
        # Kill process tree with taskkill /F /T
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
        else:
            try:
                import signal
                # Only kill the whole group if the process leads its own group;
                # never signal a group we ourselves belong to.
                if os.getpgid(pid) == pid and pid != os.getpgrp():
                    os.killpg(pid, signal.SIGKILL)
                else:
                    os.kill(pid, signal.SIGKILL)
            except Exception:
                _swallowed()

    # Append cancellation marker to log
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write("\r\n[CANCELLED BY USER]\r\n")
    except Exception:
        _swallowed()

    # Remove PID file
    try:
        os.remove(pid_file)
    except Exception:
        _swallowed()

    return jsonify({
        "success": True,
        "status": "cancelled",
        "message": f"Production process (PID {pid}) cancelled."
    })


@app.route("/api/game/<game_id>/production/status", methods=["GET"])
def production_status(game_id: str):
    """Check log, PID and execution status of 4K production run."""
    out_dir = resolve_game_out(game_id)
    if not out_dir:
        abort(404, description=f"Game directory not found for {game_id}")

    pid, status, log_lines, log_file = get_production_pid_and_status(game_id)

    # When the run started (pid file) and when the log was last written, as epoch seconds, so the dialog can say
    # "Status from the last run on <date>" instead of looking like a live status.
    def _mtime(path):
        try:
            return os.path.getmtime(path) if path and os.path.exists(path) else None
        except OSError:
            return None
    pid_file = os.path.join(out_dir, os.path.basename(log_file)[:-4] + ".pid") if log_file else None

    return jsonify({
        "status": status,
        "pid": pid,
        "log_path": log_file if log_file and os.path.exists(log_file) else None,
        "lines": log_lines,
        "started_ts": _mtime(pid_file),
        "log_ts": _mtime(log_file)
    })


@app.route("/api/game/<game_id>/organize", methods=["POST"])
def organize_game_output(game_id: str):
    """Run tools/pipeline/organize_out.py to tidy match directory into final/, work/, and _to_delete/.
    
    Request body:
        apply (bool, optional): If True, applies moves. If False or omitted, runs dry-run preview.
        action (str, optional): "tidy" (default) or "untidy" (move work/ and final/ of THIS game folder back so it can be re-rendered).
    Returns:
        200 OK: { success: bool, applied: bool, output: str, day: str }
        409 Conflict: If production is running.
    """
    if is_production_running(game_id):
        return jsonify({
            "error": "production_running",
            "message": "Folder organization is locked while 4K production is actively running."
        }), 409

    out_dir = resolve_game_out(game_id)
    if not out_dir:
        abort(404, description=f"Game directory not found for {game_id}")

    base_name = os.path.basename(out_dir)
    day = base_name[:10] if len(base_name) >= 10 and base_name[4] == "-" and base_name[7] == "-" else base_name

    data = request.get_json(silent=True) or {}
    apply_moves = bool(data.get("apply", False))

    untidy = str(data.get("action", "tidy")).lower() == "untidy"
    cmd = [PY, os.path.join(PIPELINE_DIR, "organize_out.py"), "--only", base_name if untidy else day]
    if untidy:
        cmd.append("--untidy")
    if apply_moves:
        cmd.append("--apply")

    res = run_cli(cmd, 900)

    return jsonify({
        "success": res.returncode == 0,
        "applied": apply_moves,
        "action": "untidy" if untidy else "tidy",
        "output": res.stdout or res.stderr or "No output from organize_out.py",
        "day": day
    })


@app.route("/api/docs", methods=["GET"])
def api_documentation():
    """Self-describing REST API documentation and route registry."""
    docs = {
        "title": "XbotGo Review & Zoom Editor API",
        "version": "2.14.0",
        "description": "Self-describing REST API for video match reviewing, homography zoom replays, and master 4K production.",
        "endpoints": [
            {
                "path": "/api/docs",
                "method": "GET",
                "summary": "Self-describing API documentation and schema registry."
            },
            {
                "path": "/api/build-info",
                "method": "GET",
                "summary": "Check server startup time, code modification timestamps, and staleness status."
            },
            {
                "path": "/api/games",
                "method": "GET",
                "summary": "List all games having a reviewed CSV."
            },
            {
                "path": "/api/calendar/available-dates",
                "method": "GET",
                "summary": "Scan dump folders and reviewed CSVs for the date picker."
            },
            {
                "path": "/api/game/find-or-generate",
                "method": "POST",
                "summary": "Find or generate reviewed CSV for a selected calendar date."
            },
            {
                "path": "/api/game/<game_id>",
                "method": "GET",
                "summary": "Load reviewed CSV rows, video mapping, and game info."
            },
            {
                "path": "/api/game/<game_id>",
                "method": "PUT",
                "summary": "Save edited review rows atomically with automatic backup."
            },
            {
                "path": "/api/game/<game_id>/info",
                "method": "GET",
                "summary": "Get game setup metadata (teams, logos, league, scores) and available logos."
            },
            {
                "path": "/api/game/<game_id>/info",
                "method": "POST",
                "summary": "Save game setup metadata, validate names/scores/logos, and rename Google Sheet tab in place."
            },
            {
                "path": "/api/upload-logo",
                "method": "POST",
                "summary": "Upload high-res team crest to shared/team_logos/."
            },
            {
                "path": "/api/roster",
                "method": "GET",
                "summary": "Load team player roster with cache metadata and Google Sheet sync verification."
            },
            {
                "path": "/api/roster",
                "method": "POST",
                "summary": "Save updated player roster locally to CSV and sync to Google Sheet 'Roster' tab."
            },
            {
                "path": "/api/roster/pull",
                "method": "POST",
                "summary": "Pull latest roster from Google Sheet 'Roster' tab and update local cache."
            },
            {
                "path": "/api/sheet/push/<game_id>",
                "method": "POST",
                "summary": "Push full table to Google Sheets tab."
            },
            {
                "path": "/api/recut/<game_id>",
                "method": "POST",
                "summary": "Trigger local 720p re-cut and preview reel build (locked during production)."
            },
            {
                "path": "/api/game/<game_id>/cards",
                "method": "POST",
                "summary": "Generate Intro, Halftime, and Outro title cards."
            },
            {
                "path": "/api/game/<game_id>/reels",
                "method": "POST",
                "summary": "Generate highlight and spotlight reels for selected player(s)."
            },
            {
                "path": "/api/game/<game_id>/organize",
                "method": "POST",
                "summary": "Tidy match folder into canonical final/, work/, and _to_delete/ subdirectories (locked during production)."
            },
            {
                "path": "/api/game/<game_id>/production/preflight",
                "method": "GET",
                "summary": "Run 6 automated pre-flight checks and estimate duration."
            },
            {
                "path": "/api/game/<game_id>/production/generate-bat",
                "method": "POST",
                "summary": "Generate master run_everything_<day>.bat script in strict stage dependency order."
            },
            {
                "path": "/api/game/<game_id>/production/dry-run",
                "method": "POST",
                "summary": "Dry-run master batch generation and output planned command execution."
            },
            {
                "path": "/api/game/<game_id>/production/start",
                "method": "POST",
                "summary": "Launch master production batch in detached visible console window with PID tracking."
            },
            {
                "path": "/api/game/<game_id>/production/status",
                "method": "GET",
                "summary": "Poll PID liveness and tail production log."
            },
            {
                "path": "/api/game/<game_id>/production/cancel",
                "method": "POST",
                "summary": "Cancel running production process tree via taskkill /F /T."
            },
            {
                "path": "/api/game/<game_id>/production/rebuild-stale",
                "method": "POST",
                "summary": "Rebuild only changed 4K replays and highlight reels in background (locked during production)."
            },
            {
                "path": "/api/zoom/<game_id>",
                "method": "GET",
                "summary": "List all zoom clips with reviewed, auto-placed, and unplaced statuses."
            },
            {
                "path": "/api/zoom/<game_id>/<token_or_clip>",
                "method": "GET",
                "summary": "Get full zoom replay specification, crop bounds, and pans."
            },
            {
                "path": "/api/zoom/<game_id>/<token_or_clip>",
                "method": "PUT",
                "summary": "Save updated replay specification atomically."
            },
            {
                "path": "/api/zoom/<game_id>/auto-frame",
                "method": "POST",
                "summary": "Auto-frame single or all unplaced replays to upper-midfield [1152, 450] (2.5x)."
            },
            {
                "path": "/api/zoom/<game_id>/<token_or_clip>/render",
                "method": "POST",
                "summary": "Execute background 720p render with verify_zoom validation (blocks unreviewed clips)."
            },
            {
                "path": "/api/zoom/<game_id>/<token_or_clip>/remove",
                "method": "POST",
                "summary": "Atomic Remove-Zoom: clears zoom instruction in CSV and archives replay."
            },
            {
                "path": "/api/zoom/<game_id>/<token_or_clip>/restore",
                "method": "POST",
                "summary": "Undo Remove-Zoom: restores zoom instruction and replay spec."
            },
            {
                "path": "/api/video",
                "method": "GET",
                "summary": "HTTP 206 Partial Content video streaming for smooth frame scrubbing."
            }
        ]
    }
    return jsonify(docs)



def check_port_in_use(port: int = 5000) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def get_existing_server_start_time(port: int = 5000) -> Optional[str]:
    import urllib.request
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/build-info", headers={"User-Agent": "port-check"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "server_start_str" in data:
                return data["server_start_str"]
            if "server_start" in data:
                return datetime.datetime.fromtimestamp(data["server_start"]).strftime("%H:%M:%S")
    except Exception:
        _swallowed()
    return None


# ---- restart by flag file (test workflow): create tmp/restart_editor.flag and the editor restarts itself --------------------
RESTART_EXIT_CODE = 75                      # review_editor.bat / .sh start python again when the server exits with this code
RESTART_FLAG = os.path.join(ROOT, "tmp", "restart_editor.flag")


def restart_flag_state(flag: str = None) -> str:
    """'none' (no flag), 'waiting' (flag present but a background job is still running; put the word force in the flag to override)
    or 'restart' (flag present and REMOVED now, so a restart can never loop). Called once a second by the watcher thread."""
    flag = flag or RESTART_FLAG
    if not os.path.exists(flag):
        return "none"
    try:
        with open(flag, "r", encoding="utf-8", errors="replace") as f:
            force = "force" in f.read().lower()
    except OSError:
        force = False
    if not force and any(not t.get("done") for t in TASKS.values()):
        return "waiting"
    try:
        os.remove(flag)
    except OSError:
        return "waiting"
    return "restart"


def _restart_watcher():
    warned = False
    while True:
        time.sleep(1.0)
        try:
            st = restart_flag_state()
        except Exception:
            continue
        if st == "waiting" and not warned:
            print("Restart requested, waiting for background jobs to finish (put 'force' in tmp/restart_editor.flag to restart now).", flush=True)
            warned = True
        elif st == "restart":
            if os.environ.get("XBOTGO_RESTART_LOOP") == "1":
                print("Restart flag found and removed: restarting the editor...", flush=True)
                os._exit(RESTART_EXIT_CODE)
            print("Restart flag found and removed, but this editor was not started by review_editor.bat/.sh (no restart loop): close it and start it again.", flush=True)
            warned = False


if __name__ == "__main__":
    port = int(os.environ.get("XBOTGO_PORT", "5000"))  # a second copy for testing: set XBOTGO_PORT=5001
    if check_port_in_use(port):
        st_str = get_existing_server_start_time(port) or "unknown time"
        print(f"Editor is already running on port {port} (started {st_str}). Close that window first.")
        sys.exit(1)
    print(f"XbotGo Review Editor starting at http://127.0.0.1:{port}")
    os.makedirs(os.path.dirname(RESTART_FLAG), exist_ok=True)
    try:  # render specs (tmp/spec_*.json) are only needed while a render runs: drop old ones left by killed runs
        for _f in glob.glob(os.path.join(ROOT, "tmp", "spec_*.json")):
            if time.time() - os.path.getmtime(_f) > 86400:
                os.remove(_f)
    except OSError:
        pass
    threading.Thread(target=_restart_watcher, daemon=True).start()
    app.run(host=os.environ.get("XBOTGO_HOST", "127.0.0.1"), port=port, debug=False)  # XBOTGO_HOST=0.0.0.0 inside Docker
