# XbotGo Review & Zoom Editor — API Reference

**Document Version:** 2.29.0 (adds revision/base_revision/force/409 stale_save, match_name; see ARCHITECTURE section 12) - previous 2.28.3 (adds /api/defaults, /api/logos, zoom prepare/homographies, production status finish marker, tidied-game runs; earlier: 2.17.0 Staleness Filter & UI Ergonomics)  
**Base URL:** `http://127.0.0.1:5000`  
**Protocol:** HTTP/1.1 (JSON, Server-Sent Events, HTTP 206 Video Streaming)  
**Self-Describing Endpoint:** `GET /api/docs`

---

## 1. Architecture & Protocol Conventions

### 1.1 Content Types & Headers
- **JSON Requests/Responses:** `Content-Type: application/json; charset=utf-8`
- **Streaming Execution Logs:** `Content-Type: text/event-stream; charset=utf-8` with SSE payload format:
  ```text
  data: {"line": "Rendering clip 5...", "done": false}
  data: {"done": true, "exit_code": 0, "error": null}
  ```
- **Video Scrubbing & Streaming:** `Accept-Ranges: bytes` supporting `HTTP 206 Partial Content` with `Content-Range: bytes <start>-<end>/<total>` and `Content-Type: video/mp4`.

### 1.2 Production Lock & Conflict Handling (`409 Conflict`)
When master 4K production is actively running (`is_production_running() == True`), all state-altering endpoints return HTTP `409 Conflict` to prevent file corruption and race conditions:
```json
{
  "error": "production_running",
  "message": "Action is locked while 4K production is actively running."
}
```
Locked endpoints include:
- `POST /api/recut/<game_id>`
- `POST /api/game/<game_id>/cards`
- `POST /api/game/<game_id>/reels`
- `POST /api/game/<game_id>/organize`
- `POST /api/zoom/<game_id>/<token_or_clip>/render`

### 1.3 Quality Framing Guarantee (`400 Bad Request`)
To eliminate unwatchable replays and blind renders:
- Any zoom clip with `crop: null` or `reviewed: false` is strictly blocked from rendering unless an explicit crop specification is passed with the request.
- Batch render (`scope: "all"`) returns HTTP `400 Bad Request` with `error: "unreviewed_clips_exist"` listing all unreviewed clip indices and tokens unless `reviewed_only: true` is explicitly requested.

---

## 2. System & Diagnostics

### `GET /api/docs`
Returns this self-describing REST API registry.
- **Response `200 OK`:**
  ```json
  {
    "title": "XbotGo Review & Zoom Editor API",
    "version": "2.14.0",
    "endpoints": [ ... ]
  }
  ```

### `GET /api/build-info`
Checks server process liveness, startup timestamp, and file modification staleness.
- **Response `200 OK`:**
  ```json
  {
    "server_start": 1775109341.88,
    "server_start_datetime": "2026-04-02 08:08:41",
    "server_start_str": "08:08:41",
    "build_time_str": "2026-04-02 08:13:40",
    "latest_mtime": 1775109640.12,
    "is_stale": false
  }
  ```

---

## 3. Calendar & Match Discovery

### `GET /api/games`
Scans `out\reviewed\` for all available games having a reviewed CSV.
- **Response `200 OK`:**
  ```json
  {
    "games": [
      {
        "game_id": "2026-03-29",
        "csv_path": "out/reviewed/2026-03-29_reviewed.csv",
        "mtime": 1775040091.0,
        "size": 18240
      }
    ]
  }
  ```

### `GET /api/calendar/available-dates`
Scans known dump folders (`YY-MM-DD\`), `out\<date>\`, and `out\reviewed\<date>_reviewed.csv` to populate the calendar picker with recording dates.
- **Response `200 OK`:**
  ```json
  {
    "reviewed_dates": ["2026-03-29", "2026-04-01"],
    "available_dates": [
      {
        "date": "2026-04-01",
        "status": "reviewed",
        "has_dump": true,
        "has_out": true,
        "has_reviewed": true,
        "hint": "Reviewed CSV available (ready to open)"
      }
    ]
  }
  ```

### `POST /api/game/find-or-generate`
Finds an existing reviewed CSV or generates a new one from camera dump logs (`review_from_log.py`).
- **Request Body:**
  ```json
  { "date": "2026-04-01" }
  ```
- **Response `200 OK`:**
  ```json
  {
    "status": "exists" | "generated" | "imported",
    "game_id": "2026-04-01",
    "message": "Reviewed CSV already exists for 2026-04-01."
  }
  ```

---

## 4. Match Timings & Video Streaming

### `GET /api/game/<game_id>`
Loads reviewed CSV, enriched with clip numbering, timing order validity flags, skipped status, and video file resolution.
- **Response `200 OK`:**
  ```json
  {
    "game_id": "2026-04-01",
    "headers": ["game", "half", "type", "file", "event", "action_start", "action_end", ...],
    "rows": [
      {
        "game": "2026-04-01 Home FC v Guest FC",
        "half": "1",
        "type": "goal",
        "file": "2026-04-01-10-41-31_1775040091448.mp4",
        "event": "05:27",
        "action_start": "05:24",
        "action_end": "05:29",
        "instructions": "zoom",
        "notes": "",
        "clip": "3",
        "_row_index": 2,
        "_order_valid": true,
        "_is_skipped": false
      }
    ],
    "videos": {
      "2026-04-01-10-41-31_1775040091448.mp4": {
        "exists": true,
        "path": "04-01-26/Videos/2026-04-01-10-41-31_1775040091448.mp4",
        "url": "/api/video?path=04-01-26%2FVideos%2F2026-04-01-10-41-31_1775040091448.mp4"
      }
    },
    "game_info": { ... }
  }
  ```

### `PUT /api/game/<game_id>`
Saves modified review table rows. Creates timestamped sibling backup `out/reviewed/<date>_reviewed.csv.bak-<timestamp>`, recalculates sequential clip numbers, and writes atomically with CRLF line endings.
- **Request Body:**
  ```json
  {
    "rows": [ ... ],
    "auto_push": false,
    "base_revision": "<revision returned by GET or the previous PUT>",
    "force": false
  }
  ```
  `base_revision` is the stale-save guard (2026-04-03): if the CSV changed on disk after the page loaded it (second tab, zoom editor, manual edit) the server answers `409 {"status":"conflict","error":"stale_save"}` and writes nothing; the editor then asks "File Changed Elsewhere - Overwrite?" and retries with `"force": true`. Omit `base_revision` to skip the check. `POST /api/game/<id>/info` also returns the new `revision` and `match_name` because it rewrites the CSV `game` column.
- **Response `200 OK`:**
  ```json
  {
    "status": "saved",
    "revision": "<new revision>",
    "clips": ["", "", "1", "2", "3", ...],
    "backup": "out/reviewed/2026-04-01_reviewed.csv.bak-20261029_080000"
  }
  ```

### `GET /api/video?path=<relative_or_absolute_path>`
Streaming video delivery engine supporting HTTP 206 Partial Content range requests.
- **Headers:** `Range: bytes=0-1048575`
- **Response `206 Partial Content`:**
  - `Content-Range: bytes 0-1048575/153629482`
  - `Content-Length: 1048576`
  - `Content-Type: video/mp4`

---

## 5. Game Setup & Team Crests

### `GET /api/game/<game_id>/info`
Returns game setup metadata (`game_info.json`) and lists available crests in `shared/team_logos/`.
- **Response `200 OK`:**
  ```json
  {
    "game_id": "2026-04-01",
    "game_info": {
      "home": "Home FC",
      "opponent": "Guest FC",
      "date": "2026-04-01",
      "league": "League A",
      "score": "6-0",
      "halftime": "3-0",
      "home_logo": "shared/team_logos/home_fc.png",
      "away_logo": "shared/team_logos/guest_fc.png"
    },
    "match_name": "2026-04-01 Home FC v Guest FC",
    "logos": [
      {
        "filename": "guest_fc.png",
        "team": "Guest FC",
        "rel_path": "shared/team_logos/guest_fc.png",
        "url": "/api/team-logo/shared/team_logos/guest_fc.png"
      }
    ]
  }
  ```

### `POST /api/game/<game_id>/info`
Saves game setup. Validates non-empty team names, score format (`^\d+\s*-\s*\d+$`), crest file existence, propagates match name to the review CSV `game` column, and executes in-place Google Sheet tab renaming via `gspread.Worksheet.update_title()`.
- **Request Body:**
  ```json
  {
    "home": "Home FC",
    "opponent": "Guest FC",
    "match_name": "2026-04-01 Home FC v Guest FC",
    "date": "2026-04-01",
    "league": "League A",
    "score": "6-0",
    "halftime": "3-0",
    "home_logo": "shared/team_logos/home_fc.png",
    "away_logo": "shared/team_logos/guest_fc.png"
  }
  ```
- **Response `200 OK`:**
  ```json
  {
    "status": "saved",
    "game_info": { ... },
    "match_name": "2026-04-01 Home FC v Guest FC",
    "csv_updated": true,
    "sheet_tab_renamed": true
  }
  ```

### `POST /api/upload-logo`
Uploads a new team crest to `shared/team_logos/` with path sanitization and directory containment checks.
- **Request:** `multipart/form-data` with `logo` file and optional `overwrite: "true"`.
- **Response `200 OK`:**
  ```json
  {
    "success": true,
    "filename": "crest.png",
    "rel_path": "shared/team_logos/crest.png",
    "team": "Crest",
    "url": "/api/team-logo/shared/team_logos/crest.png"
  }
  ```

### `GET /api/roster`
Returns the team player roster loaded from local cache `out/reviewed/roster.csv` with optional Google Sheet sync verification.
- **Query Parameters:**
  - `check_remote` (optional, bool `1` or `0`): When `1`, connects to Google Sheets `Roster` tab and compares local vs remote data to determine `is_in_sync`.
- **Response `200 OK`:**
  ```json
  {
    "roster": [
      { "no": "1", "name": "Player 1", "short_name": "P1", "contact": "parent1@example.com" },
      { "no": "11", "name": "Player 11", "short_name": "P11", "contact": "parent11@example.com" }
    ],
    "is_in_sync": true,
    "remote_available": true,
    "cached_at": "2026-04-02 11:34:00",
    "local_count": 11,
    "remote_count": 11
  }
  ```

### `POST /api/roster`
Saves updated player roster locally to `out/reviewed/roster.csv` (with `.bak` backup) and syncs to Google Sheet `Roster` tab in exact row order.
- **Request Body:**
  ```json
  {
    "roster": [
      { "no": "1", "name": "Player 1", "short_name": "P1", "contact": "parent1@example.com" },
      { "no": "11", "name": "Player 11", "short_name": "P11", "contact": "parent11@example.com" }
    ]
  }
  ```
- **Response `200 OK`:**
  ```json
  {
    "success": true,
    "sheet_synced": true,
    "error": null,
    "roster": [...],
    "message": "Roster updated (11 players saved to disk and Google Sheet)."
  }
  ```

### `POST /api/roster/pull`
Explicitly pulls the latest roster from Google Sheet `Roster` tab and updates the local cache (`out/reviewed/roster.csv`) in exact sheet order.
- **Response `200 OK`:**
  ```json
  {
    "success": true,
    "count": 11,
    "roster": [...],
    "message": "Successfully pulled 11 players from Google Sheet and updated local cache."
  }
  ```

---

## 6. Asynchronous Tasks & Streaming Logs

### `GET /api/tasks/<task_id>/stream`
Server-Sent Events (SSE) streaming process stdout/stderr line by line.
- **Response `200 OK` (`text/event-stream`):**
  ```text
  data: {"line": "ffmpeg -i ...", "done": false}
  data: {"line": "PASS: 16 checked, 0 flagged (verify_zoom)", "done": false}
  data: {"done": true, "exit_code": 0, "error": null}
  ```

### `GET /api/tasks/<task_id>/status`
Polling fallback for task progress.
- **Response `200 OK`:**
  ```json
  {
    "done": true,
    "exit_code": 0,
    "lines": [ ... ],
    "error": null
  }
  ```

### `GET /api/game/<game_id>/last-task?type=zoom|general|production`
Retrieves disk-persisted execution logs from `tmp/task_logs/{task_id}.log`.
- **Response `200 OK`:**
  ```json
  {
    "task_id": "zoom_20261029_080000",
    "type": "zoom",
    "status": "completed",
    "exit_code": 0,
    "lines": [ ... ]
  }
  ```

---

## 7. Downstream Match Operations

### `POST /api/sheet/push/<game_id>`
Pushes whole reviewed table (A..P) to Google Sheet with raw numbers and auto-fitted layout.
- **Response `200 OK`:**
  ```json
  {
    "status": "pushed",
    "tab_name": "04/01/26 League A",
    "rows_written": 25
  }
  ```

### `POST /api/recut/<game_id>`
*(Production locked)* Spawns `sync_game.py --local` to re-cut modified clips and update preview reel.
- **Response `200 OK`:**
  ```json
  {
    "status": "started",
    "task_id": "recut_20261029_080000"
  }
  ```

### `POST /api/game/<game_id>/cards`
*(Production locked)* Spawns `make_reels.py --stage cards` generating intro, halftime, and outro cards.
- **Response `200 OK`:**
  ```json
  {
    "status": "started",
    "task_id": "cards_20261029_080000"
  }
  ```

### `POST /api/game/<game_id>/reels`
*(Production locked)* Spawns `make_reels.py` building team highlight reel and player spotlight reels.
- **Request Body:**
  ```json
  {
    "player": "11,7",
    "stage": "all" | "reels"
  }
  ```
- **Response `200 OK`:**
  ```json
  {
    "status": "started",
    "task_id": "reels_20261029_080000"
  }
  ```

### `POST /api/game/<game_id>/organize`
*(Production locked)* Runs `tools/pipeline/organize_out.py` to tidy match outputs into `final/`, `work/`, and `_to_delete/`.
- **Request Body:**
  ```json
  { "apply": false, "action": "tidy" }  // apply: true performs the moves, false = dry-run preview. action: "tidy" (default) or "untidy" (undo Tidy for this game folder so it can be re-rendered)
  ```
- **Response `200 OK`:**
  ```json
  {
    "success": true,
    "applied": false,
    "action": "tidy",
    "output": "== 2026-04-01: final 15.6 GB | work 1.8 GB | to_delete 1.0 GB\n...",
    "day": "2026-04-01"
  }
  ```

---

## 8. Zoom Replay Subsystem

### `GET /api/zoom/<game_id>`
Lists all replays with current review, auto-placement, and render status.
- **Response `200 OK`:**
  ```json
  {
    "game_id": "2026-04-01",
    "replays": [
      {
        "clip": 3,
        "token": "mark_000527",
        "crop": [1203, 446],
        "crop_w": 1280,
        "reviewed": true,
        "is_auto_placed": false,
        "status": "rendered"
      }
    ]
  }
  ```

### `GET /api/zoom/<game_id>/<token_or_clip>`
Fetches detailed replay spec, frame boundaries, and homography state.
- **Response `200 OK`:**
  ```json
  {
    "clip": 3,
    "token": "mark_000527",
    "replay": {
      "crop": [1203, 446],
      "crop_w": 1280,
      "start": 324.5,
      "dur": 4.5,
      "pans": [],
      "reviewed": true,
      "is_auto_placed": false
    },
    "has_homographies": true,
    "video": {
      "url": "/api/video?path=..."
    }
  }
  ```

### `POST /api/zoom/<game_id>/auto-frame`
Applies upper-midfield framing `[1280, 360]` at 3.0x zoom (1280x720 in 4K), setting `is_auto_placed: true` and `reviewed: false`.
- **Request Body:**
  ```json
  { "all_unplaced": true }  // Or { "token": "mark_000527" }
  ```
- **Response `200 OK`:**
  ```json
  {
    "success": true,
    "updated_tokens": ["mark_000527", "mark_000622", ...]
  }
  ```

### `PUT /api/zoom/<game_id>/<token_or_clip>`
Saves replay framing atomically via `tools/pipeline/zoom_edit.py apply`. Manual dragging/resizing automatically clears `is_auto_placed` to `false`.
- **Request Body:**
  ```json
  {
    "token": "mark_000527",
    "clip": 3,
    "crop": [1200, 400],
    "crop_w": 1280,
    "is_auto_placed": false,
    "reviewed": true,
    "start": 324.5,
    "dur": 4.5,
    "cut_start": 0.0,
    "cut_end": 0.0,
    "pans": [[1200, 400, 4.0, 1.2]]
  }
  ```
- **Response `200 OK`:**
  ```json
  {
    "status": "saved",
    "replay": { ... }
  }
  ```

### `POST /api/zoom/<game_id>/<token_or_clip>/render`
*(Production locked)* Executes 720p render followed by `verify_zoom.py` validation. Blocks unreviewed clips.
- **Request Body (Single):**
  ```json
  { "scope": "current" }
  ```
- **Request Body (Batch):**
  ```json
  {
    "scope": "all",
    "reviewed_only": false
  }
  ```
- **Response `200 OK`:**
  ```json
  {
    "status": "started",
    "task_id": "zoom_render_20261029_080000"
  }
  ```
- **Response `400 Bad Request` (Unreviewed Block):**
  ```json
  {
    "error": "unreviewed_clips_exist",
    "message": "11 of 16 zoom clips are unreviewed or unplaced.",
    "unreviewed_clips": [{ "n": 4, "token": "mark_000622", "reason": "unreviewed" }],
    "reviewed_count": 5,
    "total_count": 16
  }
  ```

### `POST /api/zoom/<game_id>/<token_or_clip>/remove`
Atomic Remove-Zoom: Backs up CSV, clears `zoom` flag in CSV, moves replay to `removed` dictionary in `zoom_state.json`.
- **Response `200 OK`:**
  ```json
  {
    "status": "removed",
    "token": "mark_000527"
  }
  ```

### `POST /api/zoom/<game_id>/<token_or_clip>/restore`
Undo Remove-Zoom: Re-adds `zoom` flag to CSV and restores replay from `removed` to `replays`.
- **Response `200 OK`:**
  ```json
  {
    "status": "restored",
    "token": "mark_000527"
  }
  ```

---

## 9. Master 4K Production Pipeline

### `GET /api/game/<game_id>/production/preflight`
Runs 6 automated system validation checks and calculates duration estimates.
- **Response `200 OK`:**
  ```json
  {
    "all_passed": true,
    "checks": {
      "game_info": { "ok": true, "label": "Game Setup Complete", "details": "Home FC vs Guest FC, score 6-0" },
      "roster": { "ok": true, "label": "Roster Available", "details": "18 players loaded" },
      "cards": { "ok": true, "label": "Title Cards", "details": "Intro and cards ready on disk" },
      "zoom": { "ok": true, "label": "Zoom Replays Reviewed", "details": "16 clips ready" },
      "timings": { "ok": true, "label": "Clip Timings Valid", "details": "All row timestamps valid" },
      "disk_space": { "ok": true, "label": "Free Disk Space", "details": "48.2 GB free" }
    },
    "staleness": {
      "is_stale": true,
      "stale_count": 5,
      "stale_replays": [
        { "n": 4, "token": "mark_000622", "expected_dur": 11.0, "file_dur": 9.0, "reason": "Duration mismatch (9.0s vs expected 11.0s)" }
      ],
      "reels_stale": true,
      "est_rebuild_minutes": 8
    },
    "estimates": {
      "clip_count": 25,
      "zoom_count": 16,
      "est_minutes": 58,
      "est_hours": 1.0,
      "est_label": "~1.0 hours (58 min)"
    }
  }
  ```

### `POST /api/game/<game_id>/production/generate-bat`
Generates the thin run file `out/<game>/run_everything_<date>.bat` (plus `run_everything_<date>.args.json`). The .bat only calls `python tools\pipeline\run_everything.py ...`, which runs in strict dependency sequence:
1. Title cards (`make_reels.py --stage cards`)
2. Full-game assembly (`fullgame_bat.py --out <rel> --run`, skip-if-valid, partial + rename)
3. 4K clips, replays & reels (`make_reels.py --stage all --player <P>`)
4. Output verification (`check_outputs.py`)
- **Request Body:**
  ```json
  { "player": "11" }
  ```
- **Response `200 OK`:**
  ```json
  {
    "success": true,
    "bat_path": "C:\\temp\\XbotGo\\out\\2026-04-01\\run_everything_2026-04-01.bat",
    "bat_rel": "out\\2026-04-01\\run_everything_2026-04-01.bat",
    "command": "cmd.exe /c \"...\""
  }
  ```

### `POST /api/game/<game_id>/production/dry-run`
Simulates batch generation and prints the complete planned execution script without running ffmpeg.
- **Request Body:**
  ```json
  { "player": "11" }
  ```
- **Response `200 OK`:**
  ```json
  {
    "dry_run": true,
    "output": "[DRY-RUN] Would write out\\2026-04-01\\run_everything_2026-04-01.bat ...",
    "day": "2026-04-01"
  }
  ```

### `POST /api/game/<game_id>/production/start`
Windows: launches the run file in an independent console window (`subprocess.CREATE_NEW_CONSOLE`). Other systems: starts `tools/pipeline/run_everything.py` directly in its own session (`start_new_session=True`, console output in `run_everything_<date>.console.txt`). Both write the PID to `run_everything_<date>.pid`; progress goes to `run_everything_<date>.log`.
- **Request Body:**
  ```json
  { "player": "11" }
  ```
- **Response `200 OK`:**
  ```json
  {
    "started": true,
    "pid": 14820,
    "log_file": "C:\\temp\\XbotGo\\out\\2026-04-01\\run_everything_2026-04-01.log",
    "status": "running"
  }
  ```

### `GET /api/game/<game_id>/production/status`
Polls PID liveness (`GetExitCodeProcess` on Windows, `waitpid`/`kill 0` on POSIX) and tails the production log.
- **Response `200 OK`:**
  ```json
  {
    "status": "idle" | "running" | "finished" | "cancelled",
    "pid": 14820,
    "log_path": "out/2026-04-01/run_everything_2026-04-01.log",
    "lines": [
      "===== 1. Title cards =====",
      "===== 2. Full game video =====",
      "ALL OK"
    ]
  }
  ```

### `POST /api/game/<game_id>/production/cancel`
Terminates the running batch process tree cleanly via `taskkill /F /T /PID <pid>`, writes `[CANCELLED BY USER]` to the log, and unlocks modifying actions.
- **Response `200 OK`:**
  ```json
  {
    "status": "cancelled",
    "pid": 14820,
    "message": "Production process 14820 cancelled."
  }
  ```

### `POST /api/game/<game_id>/production/rebuild-stale`
*(Production locked)* Rebuilds only changed 4K replays and updates highlight reels without re-encoding full game video.
Runs `python tools/pipeline/make_reels.py --out out/<game> --stage all [--player <P>]`. Skips existing clips and unchanged replays based on signature match, finishing in ~2 minutes.
- **Request Body:**
  ```json
  { "player": "11" }
  ```
- **Response `200 OK`:**
  ```json
  {
    "status": "started",
    "task_id": "a1b2c3d4",
    "command": "python tools/pipeline/make_reels.py --out out/2026-04-01 --stage all --player 11",
    "player": "11"
  }
  ```
- **Response `409 Conflict`:**
  ```json
  {
    "error": "production_running",
    "message": "Final 4K production is actively running. Rebuild is locked until completion."
  }
  ```

### Endpoints missing from earlier sections (added 2026-04-03)

#### `GET /api/defaults` / `POST /api/defaults`
Global game defaults stored in `config/game_defaults.json` (`team_name`, `is_home`, `team_logo`, `league`, `league_logo`). GET returns the object. POST accepts any subset of those keys, merges it into the current values and returns the saved object; `400` if a logo path does not exist under the project root or the payload is not an object.

#### `GET /api/logos`
`{"logos": [...]}`: the logo files available in `shared/team_logos/` (same list the setup wizard shows).

#### `PUT /api/roster`
Same payload as `POST /api/roster` (the route accepts both methods).

#### `POST /api/zoom/<game_id>/<token_or_clip>/prepare`
Computes the homographies (`zoom_clip.py --step h`) for one replay in the background. Response: `{"status":"ready","work_dir":...}` if `H.json` already exists, otherwise `{"status":"running","task_id":...,"work_dir":...}` (follow it with the task stream/status endpoints). `404` for an unknown game or replay.

#### `GET /api/zoom/<game_id>/<token_or_clip>/homographies`
Per-frame homography matrices used by the zoom editor canvas (from the prepared `H.json`).

#### `GET /shared/<path>` and `GET /zoom/<game_id>/<token_or_clip>`
Static files from `shared/` (logos) and the Zoom Replay Editor page.

## Addendum 2026-04-03
- `GET /api/game/<id>/production/status`: a run whose pid is alive but whose log is newer than the pid file and contains `ALL OK` or `file(s) to look at` is reported as finished (not RUNNING).
- Production runs on a tidied game skip stages 2 and 3 (log `errorlevel 0 (skipped: tidied game, see final)`).
- Restart: no API; create `tmp\restart_editor.flag` (see ARCHITECTURE section 11).
- `GET /api/game/<id>/production/preflight` also returns `"tidied": true|false` (true = timeline in `work/` and a `final/*_full_game*.mp4`); the UI then explains that Start only re-checks the archive.
- `GET /api/game/<id>/production/status` also returns `started_ts` and `log_ts` (epoch seconds of the pid file and the log, or null); the dialog uses them for "Status from last run on <date>".

## Defaults schema (2026-04-03)
`GET /api/defaults` returns the merged config: `{team_name, is_home, team_logo, leagues:[{name, logo, label?}], league, league_logo, featured_players:[...], sheet_id, guest_name}`.
`POST /api/defaults` accepts any subset of these keys (`leagues` and `guest_name` included); logo paths must exist; unspecified keys keep their value.
