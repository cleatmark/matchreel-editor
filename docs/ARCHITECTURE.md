# Architecture & Implementation Reference: XbotGo Review Editor

**Document Version:** 2.29.0 (adds section 12: atomic writes, stale-save guard, diag, procs streaming, log auto-close, START lock, .sh twin; previous 2.28.3 (adds section 11 operations: tidied games, restart flag, test kit, leak fixes; previous 2.4.0: Section 1T Calendar & Wizard Separation, High-Contrast Calendar Modal, Reload Warning & In-Page Confirm, Escape Dismissal Stack, Row Selection Seek to Start, Non-Sliding Mark Read-Only Rule; 67 Unit Tests Passing)  
**Date:** April 3, 2026  
**Companion Documents:** [Handoff](HANDOFF_review_editor.md) | [Plan](PLAN_review_editor.md) | [Zoom Editor Spec](ZOOM_EDITOR_SPEC.md)  
**Codebase Root:** `<project>\tools\editor\`

---

## 1. System Overview & Design Principles

The **XbotGo Review Editor** is a lightweight, zero-build desktop web application designed to eliminate manual guesswork when reviewing and timing youth soccer match highlights. It pairs a match's reviewed CSV table directly with its high-resolution video footage in a responsive, resizable two-pane browser interface, enabling instant click-to-seek, in-place timestamp editing, visual timeline handle dragging, background video re-cutting, and synchronized cloud export.

```
+-----------------------------------------------------------------------------------------------+
|                                         USER BROWSER                                          |
|                                    (http://127.0.0.1:5000)                                    |
|                                                                                               |
|  +---------------------------+  +----+  +--------------------------------------------------+  |
|  |     LEFT: TIMES PANEL     |  | R  |  |               RIGHT: VIDEO & TIMELINE            |  |
|  | - Filter Half/Type/Skip   |  | E  |  | - HTML5 Video Player (Maximized Canvas)          |  |
|  | - Table Grid (Dirty '*')  |  | S  |  | - Dual-Mode Timeline (30s Zoom / 5m Full)        |  |
|  | - Inline Text Editors     |  | I  |  | - Draggable Lines (Start, Event, End, Mark, Play)|  |
|  | - Duration & Badges       |  | Z  |  | - Compact Transport & Speed Controls             |  |
|  | - Save, Re-cut, Push Sheet|  | E  |  | - Compact Timing & Meta Strip (~70px height)     |  |
|  | - Calendar Date Picker    |  | R  |  | - Live Task Terminal Modal (SSE logs)            |  |
|  +---------------------------+  +----+  +--------------------------------------------------+  |
+-------------------------------------------|---------------------------------------------------+
                                            | REST API / SSE Streams / HTTP 206 Streaming
                                            v
+-----------------------------------------------------------------------------------------------+
|                                    PYTHON / FLASK BACKEND                                     |
|                                (tools\editor\server.py)                                |
|                                                                                               |
|  +----------------------+  +---------------------+  +---------------------+  +-------------+  |
|  |     csv_io.py        |  |    time_utils.py    |  |sheet_sync_service.py|  |sync_game.py |  |
|  | - Atomic CSV Write   |  | - Defensive Parser  |  | - Whole Table A..P  |  | (--local)   |  |
|  | - Backup Generator   |  | - Formatters        |  | - Tab Create/Overw. |  | - Re-cuts   |  |
|  | - Clip Renumbering   |  | - Timing Validation |  | - RAW / Plain Text  |  | - Previews  |  |
|  +----------------------+  +---------------------+  +---------------------+  +-------------+  |
+-------------------------------------------|---------------------------------------------------+
                                            | Local FS & Cloud APIs
                     +----------------------+----------------------+
                     |                                             |
                     v                                             v
+-------------------------------------------+ +-------------------------------------------------+
|              LOCAL FILE SYSTEM            | |               GOOGLE SHEETS CLOUD               |
| - CSV: out\reviewed\<date>_reviewed.csv   | | Workbook: 1alsCivTNRrijhiQ_...                  |
| - Backups: tmp\review_editor\backups\     | | Tab: e.g. '03/29/26 League A' (A..P whole table)    |
| - Videos: 03-29-26\Videos\*.mp4           | | Editor is sole source of truth; sheet is viewer |
| - Review gen: tools\pipeline\review_from_log.py    | |                                                 |
+-------------------------------------------+ +-------------------------------------------------+
```

### Core Design Principles
1. **The Reviewed CSV is the Sole Source of Truth:** The editor is the only place match times are edited. Nobody edits the Google Sheet by hand. The Google Sheet is a one-way mirror for match viewing. Saving with zero edits is guaranteed byte-identical (verified by unit test `test_roundtrip.py`). CRLF line endings, exact 15-column schema, and zero-padded `mm:ss` text formats are rigorously maintained.
2. **Whole-Table Cloud Export (A..P):** Google Sheets push writes the entire table (header row plus every row, all columns A through P) into a correctly named tab (e.g. `03/29/26 League A`), creating the tab if missing or overwriting it if existing. Time columns F, H:I, and K:M are formatted as `TEXT` before and after writing in `RAW` mode.
3. **Local Re-cut Integration:** A dedicated **Re-cut** button runs `tools\pipeline\sync_game.py` in `--local` mode. It uses the local reviewed CSV directly without pulling from Google Sheets and without overwriting the editor's CSV. Output is streamed live via Server-Sent Events (SSE) into a browser terminal modal.
4. **Calendar Date Picker & Initial Table Generator:** Users can open matches from a calendar date picker. If `out\reviewed\<date>_reviewed.csv` exists, it opens directly; if not, the app discovers that day's video dump, executes `tools\pipeline\review_from_log.py`, streams the generator output, fills sequential clip numbers, and loads the game.
5. **Draggable Splitter & Maximized Video Canvas:** A draggable vertical splitter (`#paneResizer`) allows users to narrow the times table (default 340px) and expand the 16:9 video player, with position saved in `localStorage`. The compact bottom controls (~70px height) maximize video stage height and player width on desktop monitors.

---

## 2. Directory & Component Structure

```text
<project>\
├── review_editor.bat                     # Windows 1-click launcher (starts server & opens browser)
├── review_editor.sh                      # Linux/macOS/Docker launcher (same server, XBOTGO_ROOT / XBOTGO_HOST aware)
├── requirements.txt                      # Python packages (flask, gspread, numpy, opencv-python, Pillow; optional extras commented)
├── config\game_defaults.json             # Team name, logos, league, featured players, Google sheet_id
├── tools\
│   ├── xbotgo_core\                      # SHARED logic used by both editor and pipeline (csv_io, game_state, zoom_state, sheet_sync_service, log_importer, sync_service, reel_service, organize_service, output_checker ...)
│   │   ├── xb_env.py                     # ROOT (XBOTGO_ROOT override), utils\ on PATH, which(), tmp_for()   (moved here 2026-04-03)
│   │   └── xbl.py                        # Game class and shared helpers for the per-game scripts           (moved here 2026-04-03)
│   ├── pipeline\                         # command-line scripts, run by hand (runbook) or called by the editor as subprocesses
│   │   ├── run_everything.py             # Serial production runner (cards -> full game -> 4K clips/replays/reels -> check_outputs), any OS
│   │   ├── make_run_all.py               # Writes the thin run_everything_<day>.bat (+ .args.json) that calls run_everything.py
│   │   ├── sync_game.py                  # Re-cut engine (supports --local mode)
│   │   ├── review_from_log.py            # Initial review table generator from MP4 uuid box
│   │   ├── dumplayout.py                 # Dump folder and video discovery engine
│   │   └── make_reels.py, zoom_edit.py, zoom_clip.py, verify_zoom.py, cut_reviewed.py, reel_build.py, organize_out.py, xbotgo.py ... (all other scripts)
│   └── editor\                           # the Review Editor web app (was tools\review_editor\ until 2026-04-03)
│       ├── server.py                     # Flask application, SSE log stream, range video server
│       ├── csv_io.py                     # shim -> xbotgo_core.csv_io
│       ├── time_utils.py                 # shim -> xbotgo_core.time_utils
│       ├── sheet_sync_service.py         # shim -> xbotgo_core.sheet_sync_service
│       ├── test_roundtrip.py             # automated unit tests (byte-identity, CLI, payloads)
│       ├── make_test_root.py, test_data_manifest.py, fixtures\   # test-kit builder and the list of real files the tests need
│       └── static\
│           ├── index.html                # 2-pane HTML layout, resizer, calendar & terminal modals
│           ├── app.css                   # Theme, responsive layout, resizer, terminal, modals
│           └── app.js                    # Reactive UI state, dragging engine, SSE log consumer
├── out\
│   └── reviewed\                         # Authoritative reviewed match CSVs (<date>_reviewed.csv)
├── tmp\
│   └── review_editor\
│       └── backups\                      # Timestamped automated CSV backups before every save
└── shared\
    └── secrets\                          # Google Cloud service account JSON credentials
```

---

## 3. Backend & Middleware Architecture

### 3.1 Flask Web Server (`server.py`)
Provides the REST API on `http://127.0.0.1:5000`, Server-Sent Events (SSE) streaming for background processes, and static file hosting.

> [!NOTE]
> Complete, self-describing REST API documentation covering all endpoints, parameters, JSON payload schemas, HTTP status codes, error models, and production lock rules is maintained in **[`app_design/API_REFERENCE.md`](API_REFERENCE.md)** and dynamically exposed at runtime via `GET /api/docs`.

#### Endpoints
- `GET /` — Serves `static/index.html`.
- `GET /api/games` — Scans `out\reviewed\` for all `*_reviewed.csv` files and returns a list of available games with match metadata and file paths.
- `GET /api/calendar/available-dates` — Scans `out\reviewed\`, `out\`, and root dump folders, returning dates with existing reviewed CSVs, out directories, or raw video dumps for the calendar picker.
- `POST /api/game/find-or-generate` — Accepts `{"date": "YYYY-MM-DD"}`. If `out\reviewed\<date>_reviewed.csv` exists, returns `{ "status": "exists", "game_id": date }`. If an existing `out/<date>/review.csv` exists, imports it. If not found, discovers the day's dump folder (e.g. `03-29-26\`), runs `tools\pipeline\review_from_log.py`, streams logs, and generates the reviewed CSV.
- `GET /api/game/<game_id>` — Loads and parses the specified game's reviewed CSV, checks for corresponding video files across known video directories, and returns:
  ```json
  {
    "game_id": "2026-03-29",
    "csv_path": "out/reviewed/2026-03-29_reviewed.csv",
    "headers": ["game", "half", "type", ...],
    "rows": [...],
    "videos": {
      "2026-03-29-10-41-31_1774780891448.mp4": {
        "exists": true,
        "path": "03-29-26/Videos/2026-03-29-10-41-31_1774780891448.mp4",
        "url": "/api/video?path=..."
      }
    }
  }
  ```
- `PUT /api/game/<game_id>` — Validates incoming row payload, ensures timing formats are compliant `mm:ss`, creates a timestamped backup in `tmp\review_editor\backups\`, recalculates sequential clip numbers (1..N) for non-skipped rows, and writes the CSV atomically. If `auto_push` is enabled, pushes the whole table to Google Sheets. Returns `{ "status": "saved", "clips": [...], "sheet": {...} }`.
- `POST /api/sheet/push/<game_id>` — Triggers the Google Sheet update service, writing the entire table (A..P) to the matching or newly created tab.
- `POST /api/recut/<game_id>` — Spawns `python tools\pipeline\sync_game.py --out out/<game_id> --local` in a background thread and returns `{ "status": "started", "task_id": "..." }`.
- `GET /api/tasks/<task_id>/stream` — Server-Sent Events (SSE) streaming output lines (`data: {"line": "...", "done": false}`) in real-time until process exit.
- `GET /api/tasks/<task_id>/status` — Polling fallback returning `{ "done": bool, "exit_code": int, "lines": [...] }`.
- `GET /api/game/<game_id>/last-task?type=zoom|general|production` — Retrieves persisted task execution logs from disk (`tmp/task_logs/{task_id}.log`). Enables log restoration even if tabs close or the editor restarts.
- `GET /api/game/<game_id>/info` — Loads game setup metadata (`game_info.json`) and scans available team crests in `shared/team_logos/`.
- `POST /api/game/<game_id>/info` — Validates and saves updated game setup metadata, checks home/away logo existence on disk, detects if changes make existing title cards stale, and propagates `match_name` to the review CSV `game` column across all active rows.
- `GET /api/roster` — Loads team roster (`roster.csv` or Google Sheets `Roster` tab), returning player names, numbers, and short names.
- `POST /api/game/<game_id>/cards` — Spawns `make_reels.py --stage cards` in the background to generate Intro, Halftime, and Outro title cards.
- `POST /api/game/<game_id>/reels` — Spawns `make_reels.py` in the background with multi-player selection support (`--player p1,p2`) and stage choices (`all` vs `reels`).
- `GET /api/game/<game_id>/production/preflight` — Executes 6 automated validation checks: Game Setup completeness, Roster availability, Title cards existence, Zoom replays review completeness (0 unreviewed), Clip timings validity, and Free disk space (20+ GB).
- `POST /api/game/<game_id>/production/generate-bat` — Executes `make_run_all.py --out <out_dir>` to generate the master serial batch script `out\<game>\run_everything_<date>.bat`.
- `POST /api/game/<game_id>/production/start` — Launches `run_everything_<date>.bat` via background task runner with streamed and disk-persisted logging.
- `GET /api/game/<game_id>/production/status` — Checks live status and tails execution logs from `run_everything_<date>.log`.
- `GET /api/video?path=<path>` — **HTTP 206 Partial Content (Range Requests) streaming engine**. Reads video chunks (`Range: bytes=start-end`), enabling instantaneous seeking and frame scrubbing.
- `GET /zoom/<game_id>/<token_or_clip>` — Serves the dedicated Visual Zoom Replay Editor single-page application.
- `GET /api/zoom/<game_id>` — Returns a list of all zoom clips for the game with current edit and render statuses.
- `GET /api/zoom/<game_id>/<token_or_clip>` — Resolves canonical token and returns full replay spec, window boundaries, and homography status.
- `POST /api/zoom/<game_id>/<token_or_clip>/prepare` — Starts background worker generating `H.json` matrices.
- `GET /api/zoom/<game_id>/<token_or_clip>/homographies` — Serves parsed homography matrices.
- `PUT /api/zoom/<game_id>/<token_or_clip>` — Saves updated replay specification via atomic `zoom_edit.py apply`. Automatically deletes temporary spec file on completion.
- `POST /api/zoom/<game_id>/<token_or_clip>/render` — **Quality Framing Render Pipeline:** Strictly blocks rendering of unreviewed or unplaced zoom clips. For `scope: "all"`, returns HTTP 400 listing all blocked clips unless `reviewed_only: true` is passed. Executes `zoom_edit.py render --height 720` followed by automated verification via `verify_zoom.py`. Fails pipeline (exit 1) and turns drawer red if any clips are `MISSING` or `FLAGGED`.
- `POST /api/zoom/<game_id>/<token_or_clip>/remove` — **Atomic Remove-Zoom Contract:** Matches row via `csv_io.compute_clip_numbers(rows)` (or file + event fallback). Clears `zoom` instruction and writes CSV with automatic backup; only on CSV success archives replay from `st["replays"]` to `st["removed"]`. If row is not found, returns 404 and leaves both CSV and state unchanged; if state write fails, restores CSV backup.
- `POST /api/zoom/<game_id>/<token_or_clip>/restore` — Moves replay from `st["removed"]` back to `st["replays"]` and restores `zoom` instruction in the reviewed CSV atomically.

### 3.2 CSV I/O Engine (`csv_io.py`)
Responsible for preserving data integrity during read, backup, and write cycles.
- **Reading (`read_reviewed_csv`)**: Reads with `csv.reader`, preserves exact column header casing, detects BOMs, and safely parses ragged rows by padding with blank strings.
- **Backups (`backup_reviewed_csv`)**: Before writing changes, copies the target file to `tmp\review_editor\backups\<game_id>_<YYYYMMDD_HHMMSS>.csv`.
- **Clip Renumbering (`renumber_clips`)**: Iterates through rows in physical sheet order; if `instructions` contains `"skip"`, `clip` is set to blank `""`; otherwise assigns sequential integer `1`, `2`, `3`, etc.
- **Atomic Writing (`write_reviewed_csv`)**: Writes to a temporary sibling file (`<file>.tmp`), flushes buffers to disk, and performs an atomic replace (`os.replace`). Enforces standard CRLF (`\r\n`) line terminators.

### 3.3 Time Utilities (`time_utils.py`)
Handles parsing, formatting, and validation of soccer video timestamps.
- **`parse_time(val) -> Optional[int]`**:
  - Handles `m:ss` and `mm:ss` (e.g. `"14:02"` -> 842s).
  - Handles `h:mm:ss` where hours is 0 (e.g. `"0:14:02"` -> 842s).
  - Handles Google Sheets auto-formatting mangled times (e.g. `"14:02:00"` -> 842s, recognizing match video is < 40 mins).
  - Returns `None` for blanks, hyphens, or malformed strings.
- **`format_time(sec) -> str`**: Returns zero-padded `mm:ss` text (e.g. `842` -> `"14:02"`). Never outputs decimals or single-digit minutes.
- **`validate_timing_order(start, event, end) -> (bool, str)`**: Validates logical clip ordering: `start <= event <= end`. Returns descriptive warning messages if violated.

### 3.4 Google Sheet Synchronization Service (`sheet_sync_service.py`)
Integrates with Google Sheets API v4 using `gspread` and service account keys in `shared\secrets\*.json`.
- **Whole-Table Export (A..P)**: Writes the header row plus every row, all columns A through P, directly from the reviewed CSV.
- **Tab Name Resolution / Creation (`determine_tab_name`)**: Maps game ID to workbook tab using standard naming (e.g. `03/29/26 League A` or `03/21/26 League B`). Overwrites contents if the tab exists; creates the tab if it does not exist.
- **`TEXT` Formatting & `RAW` Input**: Sets plain-text number format (`TEXT`) to columns F, H:I, and K:M for rows 2-999 before and after writing in `RAW` mode so Sheets never turns `mm:ss` into durations.
- **Freeze & Auto-Fit**: Freezes header row 1 and auto-resizes column dimensions to fit content cleanly.

### 3.5 Re-cut Local Execution (`tools\pipeline\sync_game.py --local`)
- When invoked with `--local`, `sync_game.py` reads `out\reviewed\<game>_reviewed.csv` directly without pulling from Google Sheets and without overwriting the editor's CSV.
- Renumbers clips by token, moves dropped/stale clips aside, updates `zoom_state.json`, writes `clip_column.json`, cuts 720p clips via `cut_reviewed.py`, and rebuilds the preview reel via `preview_reel.py`.

---

## 4. Frontend Architecture

The frontend is a single-page application built directly in HTML5 (`static/index.html`), CSS3 (`static/app.css`), and JavaScript ES6+ (`static/app.js`).

### 4.1 Reactive State Store (`state`)
```javascript
const state = {
  games: [],
  selectedGameId: null,
  csvHeaders: [],
  rows: [],                 // Full array of row objects
  selectedRowIndex: 0,      // Currently active/inspected row index
  activeTimeField: null,    // 'video_time' | 'action_start' | 'event' | 'action_end'
  filterHalf: 'all',        // 'all' | '1' | '2'
  filterType: 'all',        // 'all' | 'goal' | 'mark'
  showSkipped: true,
  undoStack: [],            // Global undo stack
  clipUndoHistory: {},      // Per-row snapshot stack for clip-level undo
  isDirty: false,           // Has unsaved edits
  loopingAction: false,     // Is action loop playback active
  loopTimer: null,          // Loop interval ticker
  timelineZoom: {
    isZoomed: true,         // true: 30s zoom; false: full match view
    startSec: 0,
    endSec: 30,
  },
  activeTimelineLine: null, // Which line is currently selected/dragged
};
```

### 4.2 Two-Pane Interface Layout with Resizer Splitter
1. **Top Control Bar**:
   - Match dropdown with `📅 Pick game...` entry and calendar button.
   - Half filters (`All`, `1st half`, `2nd half`).
   - Type filter (`All`, `Goal`, `Mark`) and `Show skipped` toggle.
   - Save status badge (`Saved` / `Unsaved changes`).
   - Push status pill (e.g. `Pushed to 03/29/26 League A at 14:32:10`).
   - Undo button (`Undo (Ctrl+Z)`).
   - **`💾 Save`** button (`Ctrl+S`).
   - **`✂️ Re-cut`** button (immediately right of Save).
   - **`☁️ Push to Sheet`** button.
   - Checkbox **`Auto-push on save`**.
2. **Left Pane: Times Panel (`#timesPanel`, default 340px width)**:
   - Sticky table header.
   - Clip column with dirty indicator: Displays `1*` if the row has uncommitted edits.
   - Type badge: Color-coded green for `goal`, neutral dark for `mark`.
   - Four clickable time cells (`Mark`, `Start`, `Event`, `End`) in a compact grid.
   - Player field.
   - Instructions and Notes fields (scrollable horizontally without taking away video width).
3. **Draggable Pane Splitter (`#paneResizer`)**:
   - 8px wide divider between left and right panes.
   - Drag left/right to resize; automatically saves width to `localStorage` (`review_editor_table_width`).
4. **Right Pane: Maximized Video Player & Timeline (`#videoPanel`)**:
   - **Video Meta Bar**: Filename display, scale mode toggle pill (`Zoom: 14:15 – 14:45`), and high-precision current playback time (`00:00.0`).
   - **Video Player Canvas**: 16:9 canvas with `object-fit: contain`, fills all vertical space down to the compact controls.
   - **Timeline Strip**:
     - Dual-scale ruler: 30s Zoom mode (5s major / 1s minor ticks) vs Full Match mode (clean 5-minute ticks).
     - Shaded green/red action window showing `[action_start .. action_end]` bounds.
     - Draggable lines: **Start** (green), **Event** (amber), **End** (red), **Mark** (gray), and **Playhead** (red needle).
   - **Compact Bottom Controls (~70px height)**:
     - Row 1: Transport, scale mode switch `[ 🔍 30s | 🌐 Full (5m) ]`, playback speed pills `0.25x`, `0.5x`, `1x`, `2x`.
     - Row 2: Streamlined Horizontal Timing bar (`Mark`, `Start (1)`, `Event (2)`, and `End (3)` with live values and `-1s / Set / +1s` nudge buttons).
     - Row 3: Clip metadata, player tag `P:`, notes input `Notes:`, `Zoom (Z)` toggle, `Skip (X)` toggle, `▶ Loop Action` / `⏹ Stop Loop` button, `⟲ Undo Clip` button, and order validation warning badge.

---

## 5. Detailed Action & Interaction Reference

### 5.1 Game Selection & Calendar Date Picker
- **Dropdown**: Select any existing match from the dropdown list.
- **Calendar Date Picker**: Click `📅 Pick game...` or the calendar icon.
  - Displays detected dates on disk with green pills (reviewed CSVs) and amber pills (video dumps).
  - Select or type a date (`YYYY-MM-DD`).
  - Clicking **Open / Generate**:
    - If reviewed CSV exists, opens immediately.
    - If video dump exists, opens the terminal modal, runs `review_from_log.py`, streams progress live, saves `out\reviewed\<date>_reviewed.csv`, and opens the game.
    - If no recording found, shows clear error in modal.

### 5.2 Re-cut Process Execution (`✂️ Re-cut`)
- **Trigger**: Click `✂️ Re-cut` button in top bar (immediately right of Save).
- **Behavior**:
  - If there are unsaved edits, saves the CSV first with an automated backup.
  - Disables the button with text `✂️ Re-cutting...`.
  - Opens `#logModal` with title `✂️ Re-cut: <game_id>`.
  - Dispatches `POST /api/recut/<game_id>`.
  - Subscribes to `/api/tasks/<task_id>/stream` via Server-Sent Events (SSE) and displays live terminal logs.
  - On completion: restores button, displays `Re-cut complete (<timestamp>)` or error details.

### 5.3 Google Sheet Whole-Table Push (`☁️ Push to Sheet`)
- **Trigger**: Click `☁️ Push to Sheet` button or auto-push on save.
- **Behavior**:
  - Dispatches `POST /api/sheet/push/<game_id>`.
  - Writes the entire table (A..P) into the matching Google Sheet tab.
  - Updates `#sheetSyncStatus` with `Pushed to <tab_name> at HH:MM:SS`.

### 5.4 Timeline Scale Mode Switching (`[ 🔍 30s | 🌐 Full (5m) ]` / Hotkey `F`)
- **Zoom Mode (30s)**: Clamps timeline window to `[mark - 15s, mark + 15s]`. Ruler renders major tick labels every 5 seconds (`12:00`, `12:05`, `12:10`, ...) and minor ticks every 1 second.
- **Full Match Mode**: Expands timeline window to `[0, duration]`. Ruler renders major tick labels strictly at **5-minute intervals** (`00:00`, `05:00`, `10:00`, `15:00`, `20:00`, `25:00`, etc.) with minor ticks every 1 minute.
- **Auto-Zoom**: Selecting any row in the times table automatically switches the timeline slider into 30s Zoom mode around that mark.

### 5.5 Action Loop Playback (`▶ Loop Action` / `⏹ Stop Loop` / Hotkey `Ctrl+Enter`)
- Validates that `action_start` and `action_end` exist and `end > start`.
- Starts video playback from `action_start` and transforms button to red `⏹ Stop Loop`.
- Automatically loops seamlessly from `action_end` back to `action_start`. Pressing `Space` or clicking button stops playback.

---

## 6. Comprehensive Keyboard Shortcuts Reference

| Shortcut | Scope | Action |
| :--- | :--- | :--- |
| `Space` | Global | Play / Pause video playback |
| `1` | Global | Set `action_start` of selected clip to current playhead |
| `2` | Global | Set `event` timestamp of selected clip to current playhead |
| `3` | Global | Set `action_end` of selected clip to current playhead |
| `F` | Global | Toggle timeline scale between **30s Zoom** and **5m Full Match** |
| `Ctrl + Enter`| Global | Toggle **Action Window Loop** (Play <-> Stop) |
| `Z` | Global | Toggle `zoom` flag in instructions |
| `X` | Global | Toggle `skip` flag in instructions |
| `Left Arrow` | Global | Step video backward 1 second (`Shift + Left` for 5 seconds) |
| `Right Arrow`| Global | Step video forward 1 second (`Shift + Right` for 5 seconds) |
| `,` (Comma) | Global | Step video backward exactly 1 frame |
| `.` (Period) | Global | Step video forward exactly 1 frame |
| `Up Arrow` | Global | Select previous clip row in times table |
| `Down Arrow` | Global | Select next clip row in times table |
| `Ctrl + S` | Global | Save CSV changes atomically (and auto-push to Google Sheet) |
| `Ctrl + Z` | Global | Global undo last edit action |
| `Escape` | Modal/Input | Cancel active text input or close modal |
| `Enter` | Input | Commit inline time or text edit |

---

## 7. Verification & Testing

### 7.1 Automated Unit Testing (`test_roundtrip.py`)
Run all tests from the project root:
```powershell
python <project>\tools\editor\test_roundtrip.py
```
- **Byte-Identical Round-Trip Test**: Loads all existing `*_reviewed.csv` files, writes without edits, and validates byte-for-byte identity.
- **Time Parsing & Mangling Tests**: Validates standard `m:ss`, zero-padded `mm:ss`, leading-zero hour `0:mm:ss`, and Google Sheets mangled `mm:ss:00`.
- **Clip Renumbering Tests**: Tests that skipped clips are assigned `""` while active clips renumber strictly sequentially `1..N`.
- **Whole-Table Push Payload Builder Tests**: Verifies header row, columns A..P, and integer coercion on `INT_COLS`.
- **Tab Name Resolution Tests**: Verifies existing tab matching (e.g. `03/29/26 League A`) and new tab generation from `game_info.json`.
- **Re-cut CLI Test**: Verifies `tools\pipeline\sync_game.py --out out/2026-03-29 --local --dry-run` executes without pulling from Google Sheets.
- **Row Insertion & Blank File Row Tests**: Verifies chronological placement, clip renumbering, 24h clock calculation, and blank file safety in `cut_reviewed.py`.
- **Real Data Hash Guard Test**: Computes baseline MD5 hashes at suite start and asserts that `out/2026-03-29/work/zoom_state.json` and `out/reviewed/2026-03-29_reviewed.csv` remain strictly unmutated after test runs.
- **Isolated Write Test Fixtures (`make_temp_game_fixture`)**: All tests that modify state, CSVs, or replays execute exclusively against temporary copies in `tmp/`, never writing to live games.
- **Zoom Editor Phase 1 Tests**:
  - `zoom.html` delivery and route resolution.
  - `/api/zoom/<game>` replay discovery and details loading.
  - Spec clamping on 4K boundaries (`max_x = 3840 - crop_w`, `max_y = 2160 - crop_h`).
  - No-op save test: loads all replays from game 10-25 and saves them unchanged, verifying zero drift in keys, history, or values.
  - Preview base crop isolation: verifies that client-side pan preview animations do not pollute `state.baseCrop`.
  - Glide arrival math: tests forward conversion ($t \to at = \max(len/2, t - len/2)$, arrival $t_{arr} = at + len/2 = t$) and reverse conversion.
  - Remove zoom endpoint: tests `POST /remove`, verifying removal from CSV instructions and archival into `st["removed"]`.
  - Render pipeline command line assertion.
(As of 2026-04-03 the suite has 139 tests: `python -m unittest tools.editor.test_roundtrip` from the project root. It must pass on Windows; on a Linux scratch copy it needs ffmpeg for the media tests. Do NOT run it against a read-only/no-delete mount: several tests create and delete temp files in the live tree. New classes: `TestPortableRunEverything` (runner plan, thin .bat, stage logging, env overrides) and `TestEditorUiFixes` (Tab handling, chip nowrap, preflight no-blank, quiet ffmpeg frames).)

### 7.2 Manual Smoke Test Checklist
1. Launch app with `review_editor.bat`. Verify browser opens at `http://127.0.0.1:5000`.
2. Select `📅 Pick game...` from dropdown: verify calendar modal opens showing detected dates.
3. Open date `2026-03-29`: loads game directly.
4. Drag vertical splitter divider `#paneResizer`: verify times table narrows and video canvas expands. Refresh page: verify width persists.
5. Drag green `Start` handle: verify dirty asterisk `*` appears on clip number (e.g. `1*`).
6. Click `💾 Save`: verify asterisk clears, backup is created, and "Saved" status updates.
7. Click `✂️ Re-cut`: verify log terminal modal opens, streams `sync_game.py --local` logs in real time, and finishes with success.
8. Click `☁️ Push to Sheet`: verify whole table pushes to matching tab and status pill shows `Pushed to <tab> at <time>`.
9. Click `ZOOM 🔍` link on clip 7: verify visual Zoom Editor opens at `/zoom/2026-03-29/7`.
10. Drag zoom box and slider (2.5x): verify coordinates and crop width update live; click `💾 Save Plan (Ctrl+S)`.

---

## 8. Visual Zoom Replay Editor Subsystem (Phase 1)

The **Zoom Replay Editor** is a dedicated single-page visual workspace inside the Review Editor server, fulfilling [`ZOOM_EDITOR_SPEC.md`](ZOOM_EDITOR_SPEC.md). It replaces manual tile picking and trial-and-error CLI scripts with an interactive video canvas, draggable 16:9 crop framing, keyframe pan transitions, and background 720p rendering with automated streak/edge verification.

```
+-------------------------------------------------------------------------------------------------+
|                                    ZOOM REPLAY EDITOR PAGE                                      |
|                               (http://127.0.0.1:5000/zoom/<game>/<clip>)                         |
|                                                                                                 |
|  TOP BAR:  [← Review Editor]   Clip 7 (goal_001807)   [◀ Prev] 7/16 [Next ▶]   status: edited     |
|                                                                                                 |
|  +--------------------------------------------------+  +-------------------------------------+  |
|  |             LEFT: VIDEO VIEWPORT & STEPPING      |  |           RIGHT: SIDEBAR            |  |
|  |                                                  |  |                                     |  |
|  |  +--------------------------------------------+  |  |  ZOOM RATIO:                        |  |
|  |  |  HTML5 Video Player (720p stream)          |  |  |  [====O========] 2.50x (1536px)     |  |
|  |  |                                            |  |  |  [2.0x] [2.5x] [3.0x] [4.0x] [5.0x] |  |
|  |  |       +-------------------+                |  |  |                                     |  |
|  |  |       | 16:9 Crop Box     |                |  |  |  REPLAY WINDOW:                      |  |
|  |  |       | (x: 1940, y: 300) |                |  |  |  Start: event - 2.5s (1084.5s)       |  |
|  |  |       +-------------------+                |  |  |  End:   event + 2.0s (1089.0s)       |  |
|  |  |                                            |  |  |  Trims: cut_start 0.0s, cut_end 0.0s |  |
|  |  +--------------------------------------------+  |  |                                     |  |
|  |                                                  |  |  SPEED & HOLD:                      |  |
|  |  TRANSPORT & TIMELINE:                           |  |  Speed: 0.25x [0.5x] 1.0x           |  |
|  |  [|<] [-1s] [-0.5s] [◀frame] [PLAY 0.5x] ... [>|]|  |  Hold last frame: 0.0s              |  |
|  |  Source: 18:07.0 (event 18:07.0)                 |  |                                     |  |
|  |  Replay: 04.5s / 09.0s (speed 0.5x)              |  |  PANS & KEYFRAMES:                  |  |
|  |  [=========|---|===========O==============]      |  |  #1 0.0s (Anchor) (1940, 300)      |  |
|  |                                                  |  |  #2 5.5s (Glide)  (3800, 300) [✕]   |  |
|  |  [x] Loop window   [ ] 6x6 Grid   [ ] Snap tiles |  |  [➕ Keyframe at Playhead (K)]      |  |
|  +--------------------------------------------------+  +-------------------------------------+  |
|                                                                                                 |
|  BOTTOM:  [Auto start]  [💾 Save Plan (Ctrl+S)]  [▶ Preview (R)]  |  Scope: [Current]  [⚡ Render] |
+-------------------------------------------------------------------------------------------------+
```

### 8.1 Data Contracts, Defaults & Storage
Replays are saved in `out/<game>/zoom_state.json` (or `work/zoom_state.json`) keyed by their stable `type_HHMMSS` token (e.g. `goal_001807`). The Review CSV is never touched by the Zoom Editor, except the explicit "Remove zoom" action which strips the word `zoom` from that row's `instructions` and archives the replay under `st["removed"]`.

#### Default `crop_w` Rule:
- **Existing Replays with a Stored Crop:** `crop_w` defaults to `1280` (3.0x zoom, matching `CROP_W = 1280`). If `crop_w == 1280`, it is omitted from the saved JSON spec and state to prevent payload bloat.
- **Brand-New Unconfigured Replays:** Replays with no prior crop default to `crop_w = 1536` (2.5x zoom, centered).

#### Base Crop vs. Display Box:
- In `zoom.js`, `state.baseCrop` stores the keyframe-0 anchor coordinates `[baseX, baseY]`.
- The Preview Replay feature (`R` shortcut or button) animates an on-screen display box using smoothstep interpolation without mutating `state.baseCrop`.
- When preview stops or the playhead seeks, the display box renders at the interpolated time coordinate, and saving always submits `state.baseCrop`.

#### Keyframe Arrival Timing Math:
- In `zoom_clip.py`, glides run over $[at - len/2, at + len/2]$, completing at $t_{\text{arrival}} = at + len/2$.
- When dropping a glide keyframe at paused replay playhead time $t$, `zoom.js` calculates and stores $at = \max(len/2, t - len/2)$, ensuring the camera completes arrival at $(x, y)$ exactly at $t$.
- Scrubber markers and keyframe rows display $t_{\text{arrival}}$. Snap keyframes keep $at = t$.

```json
{
  "token": "goal_001807",
  "clip": 7,
  "crop": [1940, 300],
  "start": 1084.5,
  "dur": 4.5,
  "cut_start": 0.0,
  "cut_end": 0.0,
  "pans": [
    {"mode": "glide", "at": 4.0, "len": 3.0, "x": 3800.0, "y": 300.0}
  ],
  "zoom_to": null,
  "hold_end": 0.0
}
```

### 8.2 Single-Pass Atomic Apply (`tools\pipeline\zoom_edit.py apply`)
To eliminate multiple disjoint rendering passes, `zoom_edit.py` provides an atomic `apply` command:
```powershell
python tools\pipeline\zoom_edit.py apply <token_or_clip> --out out\<game> --spec <path_to_spec.json> [--render] [--height 720]
```
- **Token-First Resolution:** Looks up the target by stable token or numeric clip number in `jobs_by_clip(g)` and `st["replays"]`.
- **Reference Frame Clamping:** Reference resolution is strictly 4K (3840×2160). Coordinates are clamped so the box never exceeds visible bounds:
  $$\text{max\_x} = \max(0, 3840 - \text{crop\_w})$$
  $$\text{max\_y} = \max(0, 2160 - \text{round}(\text{crop\_w} \times 9 / 16))$$
- **Pan Translation:**
  - `snap`: written as `[x, y, at]` (quick ease ramp).
  - `glide`: written as `[x, y, at, len]` where `len` is replay duration of the glide.
  - Supports both 1D keyframe lists `[x, y, at, len]` and 2D keyframe arrays `[[x, y, at, len], ...]`.
- **No-Op Change Detection:** If the incoming specification matches stored replay parameters, `cmd_apply` preserves keys, history, and timestamps with zero modifications.
- **Trims Preservation:** When `cut_start`, `cut_end`, or `hold_end` are omitted from the incoming spec, existing replay trims are strictly preserved.
- **Rendering & Verification Pipeline:** When `--render` is passed, `zoom_edit.py apply` checks signature `sig(r, height)` and produces the master and cut replays in `clips/extra/`, followed immediately by `tools\pipeline\verify_zoom.py` checking edge smear and length.

### 8.2.1 Stabilized Canvas & Render Architecture
- **Client-Side Pan Preview:** In the browser, pressing <kbd>R</kbd> executes smoothstep pan preview across the HTML5 video player, providing real-time trajectory visualization.
- **Server-Side Exact Render:** Complete homography-stabilized rendering uses OpenCV perspective warping in `zoom_clip.py render`, streaming step-by-step progress via Server-Sent Events (SSE) into the log drawer modal.

### 8.3 Coordinate Systems & Client Mapping
1. **4K Reference Frame:** 3840×2160 sensor-space reference frame taken at `event` time. All persisted coordinates (`crop`, `crop_w`, pans) are in this space.
2. **Display Scale Factor:** In the browser, the video element size varies based on display resolution. The scale factor is dynamically derived:
   $$\text{scale} = \frac{\text{videoStage.clientWidth}}{3840}$$
3. **Screen Box Geometry:**
   $$\text{screenLeft} = \text{cropX} \times \text{scale}$$
   $$\text{screenTop} = \text{cropY} \times \text{scale}$$
   $$\text{screenWidth} = \text{cropW} \times \text{scale}$$
   $$\text{screenHeight} = \text{cropH} \times \text{scale}$$
   $$\text{zoomRatio} = \frac{3840}{\text{cropW}}$$

### 8.4 Keyboard Ergonomics for One-Hand Editing
| Key | Action |
| :--- | :--- |
| `A` / `D` | Step 1 frame backward / forward (1/15s) |
| `S` / `W` | Step 0.5s backward / forward |
| `Space` | Play / Pause playback at current speed (default 0.5x) |
| `K` | Drop or update keyframe at playhead |
| `R` | Play animated replay preview with smoothstep pan interpolation |
| `Ctrl + S` | Save plan atomically to `zoom_state.json` |
| `Escape` | Close modals if open; otherwise close zoom window and return to review editor |

### 8.5 Window Lifecycle & Tab Management
- **Dedicated Named Window Target:** Clicking `ZOOM 🔍` in the review table executes `onZoomChipClick(e, url)` invoking `window.open(url, 'xbotgo_zoom')`. This targets a single dedicated browser tab; selecting another zoom clip reuses and focuses the existing tab instead of accumulating multiple orphan tabs.
- **Opener Reference & Clean Close:** Opening via script establishes `window.opener`, which grants the child tab permission to invoke `window.close()` without browser restrictions.
- **Graceful Return (`closeOrReturnToReview`):** Triggered by clicking `← Review Editor`, pressing <kbd>Escape</kbd>, or upon removing a zoom instruction. Focuses `window.opener` and closes the zoom window cleanly. If opened directly without an opener (e.g. pasted URL), safely falls back to `history.back()` or navigation to `/`.

---

## 9. Final 4K Production & Downstream Pipeline Integration

### 9.1 Multi-Stage Downstream Architecture
Full-game rendering, 4K clip extraction, and reel compilation are intentionally separated from the review editor UI to ensure maximum performance and crash resilience. The editor generates a master serial execution batch script:
```
[Pre-Flight Checks] ➔ [Generate .bat] ➔ [Title Cards] ➔ [4K Master Clips] ➔ [4K Zoom Replays] ➔ [Full Game Assembly] ➔ [Reels] ➔ [Output Verification]
```

### 9.2 Pre-Flight Validation Engine (`/api/game/<game_id>/production/preflight`)
Before generation or execution, 6 system checks are validated:
1. **Game Setup (`game_info.json`):** Verifies non-empty Home and Opponent team names, valid final and halftime scores, and on-disk existence of both club crests.
2. **Roster (`roster.csv`):** Ensures player list is loaded with at least 1 player.
3. **Title Cards:** Checks for existence of intro cards (`000_intro_fullgame.mp4`). If missing, prompts card generation first.
4. **Zoom Replay Completeness:** Verifies that 100% of zoom replays have `reviewed: true` and a valid crop box. Any unreviewed or unplaced zoom replays fail pre-flight and block batch execution.
5. **Timestamp Sequence:** Validates all row timestamps via `time_utils.validate_timing_order` (`start <= event <= end`).
6. **Disk Space:** Calculates free disk space via `shutil.disk_usage(out_dir)`, recommending at least 20 GB free space for intermediate 4K files.

### 9.3 Run File Generation and the Python Runner (`make_run_all.py` + `run_everything.py`, v2.28)
Invoked via `POST /api/game/<game_id>/production/generate-bat`:
- `make_run_all.py --out <out_dir> --player <numbers>` writes `out\<game>\run_everything_<date>.bat` plus `run_everything_<date>.args.json` ({out, day, player, games}). It first generates missing title cards (`make_reels.py --stage cards`).
- **The .bat is a thin wrapper**: `cd /d <project root>` then `python tools\pipeline\run_everything.py --out <rel> --day <date> --player <P>` then a 20 s timeout. No logic lives in the .bat any more (the old version had the stage list, `%errorlevel%` logging and a per-game full-game .bat). The project root in the .bat is the real root when generated on the PC, else `XBOTGO_WINROOT` (default `<project>\`).
- **`run_everything.py`** (any OS) runs the stages serially with `build_plan()`: 1. title cards (`make_reels.py --stage cards`), 2. full game (`fullgame_bat.py --out <rel> --run`, skip-if-valid + `.partial.mp4` + rename), 3. 4K clips, replays and reels (`make_reels.py --stage all --player P`), 4. `check_outputs.py`. A failing stage is logged as `<tag> errorlevel N` and the run continues; the check at the end flags missing outputs. Log lines are written to `run_everything_<date>.log` in the same format as before (first line `<ts> start`, then `... cards errorlevel 0`, `... full game errorlevel 0`, `... reels errorlevel 0`, check_outputs lines, ending `ALL OK`). `--dry-run` prints the plan only (headings "1. Title cards", "2. Full game video", "3. 4K clips, replays, reels", "4. Checking lengths and outputs" are relied on by tests and the Dry Run modal).
- **Resume Safety:** every stage skips finished pieces (finished 4K clips, replays and reels, and a finished full game via `probe_ok`). Cancel Run, then Start again, resumes; title cards (~15 s) are rebuilt; a full game cancelled mid-way restarts from its beginning (partial file is never used).
- Children run with `PYTHONUNBUFFERED=1` when started from the editor so task modals show live lines.

### 9.4 Multi-Player Featured Spotlight Reels (`make_reels.py`)
- Supports multi-player arguments e.g. `--player 11,7`.
- Generates team highlights (`_highlights_transitions.mp4`) followed by individual spotlight reels (`<prefix>_<short_name>_<no>_highlights.mp4`) for each requested player in a single unified run.
- Zero-clip players are automatically skipped to avoid generating empty video files.

### 9.5 Detached Independent Process Runner & Lifecycle Management
- **Detached Execution:** `POST /api/game/<game_id>/production/start`. On Windows the .bat is started with `cmd.exe /c` and `subprocess.CREATE_NEW_CONSOLE` (visible console, decoupled from Flask, survives editor restarts and tab closures). On other systems (`os.name != "nt"`) the same Python runner is started directly (`run_everything.py --day D --player P [--out ...]`, values read from `run_everything_<date>.args.json`) with `start_new_session=True` (its own process group) and output to `run_everything_<date>.console.txt`.
- **PID Persistence & Liveness:** the PID is written to `out/<game>/run_everything_<date>.pid`. `is_pid_running` uses `ctypes.windll.kernel32.GetExitCodeProcess` on Windows and `waitpid(WNOHANG)` + `os.kill(pid, 0)` on POSIX.
- **Cancellation:** `POST .../production/cancel`: Windows `taskkill /F /T /PID`; POSIX `os.killpg` only when the process leads its own group and it is not the editor's group, else `SIGKILL` on the pid. Writes `[CANCELLED BY USER]` to the log and removes the PID file. The UI clears the typed START after cancel and after launch (`resetProductionConfirm`).
- **Status:** from PID liveness plus the log: running / cancelled / completed (`ALL DONE`) / failed (`errorlevel 1`) / finished.

### 9.6 Modifying Action Locks (409 Conflict)
- To prevent file corruption and race conditions while 4K production is actively running, all state-modifying endpoints strictly enforce a lock:
  - `/api/recut/<game_id>`
  - `/api/zoom/<game_id>/<token>/render`
  - `/api/game/<game_id>/cards`
  - `/api/game/<game_id>/reels`
- When called during an active run, these endpoints return `409 Conflict` with `{"error": "production_running"}`.
- Both the Review Editor and Zoom Editor display a prominent amber top banner: *"Production is currently running. Editing actions are locked."*

### 9.7 Dry-Run Simulation Mode (`--dry-run`)
- `tools/pipeline/make_run_all.py` supports a `--dry-run` flag.
- Invoked via `POST /api/game/<game_id>/production/dry-run`, it generates and displays the entire plan, verifies batch files, and echoes every command string without invoking ffmpeg or modifying outputs.

### 9.8 In-Place Google Sheet Tab Rename
- Implemented in `tools/pipeline/sheet_sync.py` and `tools/editor/sheet_sync_service.py`.
- Evaluates the canonical tab name (e.g. `10/25 Home FC v Guest FC`). If a tab matching the date or generic name exists with an old title, it executes an in-place rename via `gspread.Worksheet.update_title()`, preserving cell histories, permissions, and links without duplicating tabs.

### 9.9 Secure Logo Upload Pipeline
- `POST /api/upload-logo` allows uploading transparent PNG/JPG crests directly to `shared/team_logos/`.
- Uses `werkzeug.utils.secure_filename` and strict directory confinement checks (`os.path.commonpath`) to prevent path traversal attacks.
- Supports overwrite verification and automatically selects the newly uploaded crest in the Game Setup Wizard.

### 9.10 Standalone Match Folder Organization (`tools/pipeline/organize_out.py`)
- Independent from the serial batch script, folder organization is available as a dedicated menu tool under `☰ Menu ▾ → 🧹 Tidy Output Folder...`.
- Invoked via `POST /api/game/<game_id>/organize` with `{"apply": bool}`.
- Reorganizes the match directory into canonical subfolders:
  - Final full game and highlight reels are moved into `final/`.
  - Regenerable input files (`timeline.json`, `game_info.json`, etc.) are moved into `work/`.
  - Intermediate clips and render artifacts are moved into `_to_delete/`.
- Nothing is permanently deleted; every move is logged in `out\_organize_manifest.json` and can be restored.
- Enforces the production lock (returns `409 Conflict`) if master 4K production is actively running.

### 9.11 4K Outputs Staleness Detection & Fast Rebuild Pipeline
- **Staleness Mechanics (`check_4k_outputs_staleness`):**
  - Cross-references expected replay duration `(dur - cut_start - cut_end) / speed + hold` against existing 4K master files (`out/<game>/clips/extra/*_2160.mp4`).
  - Detects if replay plan modifications or history timestamps postdate existing 4K files or highlight reels.
  - Returned in `GET /api/game/<game_id>/production/preflight` under `staleness`.
- **Fast Rebuild Pipeline (`POST /api/game/<game_id>/production/rebuild-stale`):**
  - Spawns `python tools/pipeline/make_reels.py --out out/<game> --stage all [--player <P>]`.
  - Automatically skips existing 4K clips (`stage_clips`) and unchanged replays (`stage_replays`), only re-encoding modified 4K replays and updating highlight reels in ~2 minutes.
  - Locked during active production runs with `409 Conflict`.
- **Stale Replay State Tracking (`RENDERED (stale)`):**
  - If a replay has an existing rendered review file on disk, but its window offsets, trims, or crop box have been edited, its badge updates to `RENDERED (stale)` in amber (`#F59E0B`).
  - Marked with `is_stale: true` in the API and badged `STALE` in the review table.
- **Window Start Shift Guard & Auto-Seek:**
  - Adjusting `Window Start Offset` shifts the START anchor moment. The editor warns the user to verify framing at the new start moment and automatically seeks the video playhead to the new start time.

### 9.12 UI Layout, Timing Strip Color Hierarchy & Compact Times Grid
- **Top Bar Reorganization:**
  - Brand title removed; `[☰ Menu ▾] [Game Select] [📅] [⚙️]` are grouped cleanly on the top left, with the Menu button positioned first on the far left.
  - "Pick Match from Calendar" is integrated into the Game Setup Wizard (`#gameInfoModal`) while retaining the quick `📅` calendar icon on the top bar.
- **Timing Controls Strip Color Hierarchy:**
  - Control labels strictly match slider handle colors:
    - `Mark`: Green (`#16A34A` / `.lbl-mark`)
    - `Start (1)`: Blue (`#2563EB` / `.lbl-start`)
    - `Event (2)`: Amber (`#D97706` / `.lbl-event`)
    - `End (3)`: Red (`#DC2626` / `.lbl-end`)
- **Immutable Mark Reference:**
  - Mark represents ground-truth match events. Dragging and sliding on the timeline Mark line are completely disabled; clicking seeks playhead to the mark.
  - Inline editing and pencil icons for Mark are removed; double-clicking Mark cells in the table is guarded against edits.
  - Timeline handle tag is spelled out as `MARK` in green (`#16A34A`).
- **Compact Times Grid & Combined Type-Mark Cell:**
  - Merged `Type` and `Mark` time into `col-type` pill: `M (2:43)`, `G (8:48)`, `A (12:15)`.
  - `col-times` reduced from 4 to 3 columns (`Start`, `Event`, `End`), saving 44px of horizontal space.
- **4K Staleness Exclusion & Progress Summary:**
  - `check_4k_outputs_staleness` strictly excludes `*preview*` files, comparing only production highlight and spotlight reels against 4K masters.
  - `make_reels.py` outputs a structured completion banner logging exact reel names and probed durations.

### 9.13 Calendar & Wizard Separation, In-Page Confirmation, Escape Stack & Row Seek Target (v2.4.0)
- **Wizard & Calendar Architectural Separation:**
  - Removed calendar date controls and styles entirely from the Game Setup Wizard (`#gameInfoModal`). The wizard is reserved strictly for match metadata (teams, logos, league, scores, cards).
  - Removed "Pick Match from Calendar" from the application menu dropdown.
  - The standalone `📅` calendar icon on the top bar serves as the sole entry point to date discovery and game loading.
- **Escape Key Dismissal Stack (`dismissTopmostLayer`):**
  - To eliminate unexpected layer closure when closing nested dialogs, <kbd>Escape</kbd> evaluates active layers in strict topmost-first order:
    1. **In-page confirmation dialogs:** `#calendarConfirmBox` (closes without dismissing the underlying calendar modal).
    2. **Open modals:** `#calendarModal`, `#gameInfoModal`, `#finalProductionModal`, `#featuredPlayerModal`, `#organizeModal`, `#logModal`.
    3. **Application menu dropdown:** `#appMenuDropdown`.
  - The keydown listener intercepts <kbd>Escape</kbd> **before** checking if an `<input>`, `<select>`, or `<textarea>` has focus, ensuring modals can always be dismissed with <kbd>Escape</kbd> even while typing.
  - Same hierarchical dismissal model applied in Zoom Replay Editor (`zoom.js`).
- **Calendar Modal Reload Warning & In-Page Confirmation:**
  - An informational notice is persistently visible at the bottom of `#calendarModal`: *"Opening a date reloads all data for that game."*
  - When clicking any date pill, `updateCalendarReloadNote(dateVal)` dynamically displays the exact action:
    - Reviewed match: *"Reviewed table for <date> will be loaded from disk."*
    - Recording dump: *"A new review table will be generated from the dump for <date>."*
    - Current open game: *"Current game <date> will be reloaded; unsaved changes will be lost."* (only displayed when dirty changes exist).
  - Clicking **Open / Generate** displays an in-page confirmation dialog (`#calendarConfirmBox`) with styled **Continue** and **Cancel** buttons (zero native `confirm()` dialogs). Cancel returns directly to the calendar.
- **Row Selection Target (`action_start`):**
  - Selecting any row in the times table (via mouse click or <kbd>ArrowUp</kbd> / <kbd>ArrowDown</kbd>) automatically seeks the video playhead to that row's `action_start` timestamp (falling back to `video_time` only if start is unconfigured). This ensures review and tuning playback begins immediately before the action develops.
  - Clicking the `Type (Mark)` pill explicitly seeks the video playhead to the ground-truth `video_time`.
- **Mark Ground Truth Immutability:**
  - Match marks (`video_time`) represent physical button presses during recording and are strictly immutable reference points.
  - Mark handles on the timeline ruler cannot be dragged; double-clicking Mark cells in the table is guarded against edits; inspector pencil edits are removed. Erroneous marks are flagged with skip (`X`); new moments are created via <kbd>Insert</kbd>.



## 10. Portability and Environment Independence (v2.28, 2026-04-03)
Goal: remove ties to Windows without changing Windows behaviour. Everything below is additive and defaults to the old behaviour.
- **Root:** `XBOTGO_ROOT` environment variable overrides the auto-detected project root (`xb_env.ROOT`, `server.ROOT`). `XBOTGO_WINROOT` is the Windows path written into generated .bat files and `fullgame_bat.py --winroot` (default `<project>\`). `XBOTGO_HOST` (default 127.0.0.1) lets the server bind 0.0.0.0 inside Docker.
- **Helper programs:** `utils\` (ffmpeg, ffprobe, tesseract, yt-dlp, scrcpy, untrunc) is put on PATH by `xb_env`; if a program is not there the system PATH is used (`xb_env.which`). Scripts call programs by bare name (`ffmpeg`), never `ffmpeg.exe`.
- **Python packages:** `requirements.txt`. Required: flask, gspread, numpy, opencv-python, Pillow. Optional: kokoro-onnx, soundfile, websockets (announcer voice). Dev: pyflakes.
- **Credentials:** the first `shared/secrets/*.json` Google service-account key, loaded with `gspread.service_account(filename=...)`; sheet id from `config/game_defaults.json`. No environment-variable option yet; in a container mount the key read-only; never include it in a distributable zip.
- **Production launch:** see 9.3 / 9.5 - the only Windows-specific piece left is the visible console window; the run itself is Python.
- **Still Windows-specific / open:** `review_editor.bat` (use `review_editor.sh` elsewhere); `xb_env._tmp` redirects TMP only on Windows; Docker image and portable zip packaging not built (plan in handoff 1AX); Google key still file-based.
- **Quiet ffmpeg:** `zoom_clip.frames()` no longer lets a broken-pipe from an early-stopped read print ffmpeg muxer errors; stderr is shown only when no frame could be read.
- **Live progress:** background task children run unbuffered; `make_reels.py --stage all` prints `[clips]`, `[replays]`, `[reels]`, `team highlights done` lines.

## 11. Operations added 2026-04-03 (handoff 1AY/1AZ)
- **Tidied games:** `run_everything.is_tidied(dir)` = no `timeline.json` at the game root, one in `work\`, and a `final\*_full_game*.mp4`. Stages 2 and 3 are then logged `errorlevel 0 (skipped: tidied game, see final)`; `output_checker` looks in `final\` too.
- **Production status:** a running pid whose log is newer than the pid file and contains `ALL OK` or `file(s) to look at` counts as finished (console `timeout` lag).
- **Restart by flag:** `tmp\restart_editor.flag` -> server removes it, exits with code 75 (`RESTART_EXIT_CODE`), launchers (`review_editor.bat`, `review_editor_5001.bat`, `tools\editor\review_editor.bat`, `review_editor.sh`) loop on 75 (`XBOTGO_RESTART_LOOP=1`). Waits while a background job runs; `force` in the flag overrides. An editor not started by a launcher is not restarted.
- **Test kit:** `tools/editor/make_test_root.py` builds `tmp\test_root` from `test_data_manifest.py` (24 files, no videos/key, contacts scrubbed). See `TEST_FIXTURES.md`.
- **Leak fixes:** `preview_reel.build()` removes its scratch in `finally`; tests clean `out\test_game_*`, backups and `spec_*.json`; server sweeps old `spec_*.json`.
- **Untidy (2.28.3):** `organize_service.plan_untidy/execute_untidy` reverse Tidy for one game by rules (work -> root, `final/*_full_game.mp4` -> root, other final reels -> `reels/`, `final/players` -> `reels/players`; `_to_delete` untouched, never overwrites, manifest entries of the game dropped). CLI `organize_out.py --untidy --only <game> [--apply]`, API `POST /organize {"action":"untidy"}`, UI toggle in the Tidy dialog.
- **Encoding rule (2.28.3):** every text `open()` in tools/ passes `encoding=` (utf-8, utf-8-sig for review CSV reads); .bat writers stay on the default encoding on purpose.
- **Tidied note (2.28.3):** the preflight response carries `tidied`; the Final 4K dialog shows only an archive panel with an Untidy button for such games (everything else hidden).

## 12. Changes of 2026-04-03 (handoff 1BB and its addenda; version 2.29.0)
Layout is `tools\editor\` (Flask server + static UI), `tools\pipeline\` (CLI scripts), `tools\xbotgo_core\` (shared logic, no Flask). `tools\editor\csv_io.py`, `time_utils.py`, `sheet_sync_service.py` are thin re-export shims of the core modules.
New core modules:
- `xbotgo_core/atomic_io.py`: `write_json_atomic` / atomic text+bytes writes (temp file in the same folder, then `os.replace`). Used for game_info.json, game_defaults.json, roster.csv, zoom_state, organize manifest, last_tasks. A crash can no longer leave a half-written state file.
- `xbotgo_core/diag.py`: `swallowed(where, exc)` replaces every silent `except Exception: pass`; prints `[note] ignored <Error> (in <fn>, <file>:<line>)` in the editor window.
- `xbotgo_core/procs.py`: `run_streaming(cmd, timeout=None)` runs a child (python gets `-u`), echoes each line live with a two-space prefix, optional kill-timeout (raises `TimeoutExpired`). Used by `sync_game.py` (Re-cut; no timeout by default, `XBOTGO_CUT_TIMEOUT_S` to cap) and `make_reels.py run()` (clips, zoom replays, reels now visible in the cmd window). `sync_game.run_streaming` is re-exported.
Server (`tools\editor\server.py`):
- Stale-save guard: `csv_revision()` = `mtime_ns-size` of the review CSV; GET returns `revision`; PUT sends `base_revision`; mismatch gives 409 `stale_save` unless `force`. PUT and POST game-info return the new `revision` (Game Setup rewrites the CSV game column) and `match_name`. UI: "File Changed Elsewhere" dialog.
- `run_cli(cmd, timeout)` wraps the short CLI calls (120 s x3, 900 s for long) so a hung child cannot hang the server.
Final production: `make_run_all.py` writes a thin `run_everything_<day>.bat` AND `run_everything_<day>.sh` plus `.args.json`; all real work is the platform-independent `run_everything.py` (cards, full game, reels, check_outputs; log ends `ALL OK`). Tidy treats `.bat`, `.sh`, `.args.json` as work files.
UI (`static/app.js`, `index.html`, `zoom.js`): beforeunload guard (editor and zoom page); calendar overwrite warnings only when something can really be overwritten; opponent logo pre-selected from the opponent name; zoom badge says REVIEWED vs EDITED; Re-cut shows `[i/N]`; Generate-review and Re-cut log windows auto-close on success (checkbox `logAutoClose`, default on, remembered in localStorage) with a 📋 Log button (`viewLastLog`); the START confirmation is locked read-only while a run is going (`syncProductionConfirmLock`) and cleared on completed/failed/cancelled; Player field wider, aria-labels, fonts >= 11 px.
Root files: `README.md` (setup + first run), `run_tests.bat` (Windows suite), `restart_editor.bat`, `review_editor.bat`, `review_editor_5001.bat`.


## 13. Configuration and private data (2026-04-03)

No team, league, player, sheet or path value is hard-coded. `tools/xbotgo_core/app_config.py` is the single loader:
built-in generic fallback (`Home FC`, `Guest FC`, `League A`/`League B`, featured player `7`, empty `sheet_id`) <- `config/game_defaults.json`
(git-ignored, the user's real values) <- env `XBOTGO_SHEET_ID`. `game_state.load_game_defaults()`, the sheet-sync service (tab name =
`MM/DD/YY <league>[ Gn]`, league from `game_info.json`, else the default league), `log_importer` (new `game_info.json` carries `league`), the CLI
defaults (`--home`, `--player`) and the whole frontend (league pills, fallbacks) read it; the browser gets it from `GET /api/defaults`.
`leagues` is a list of `{name, logo, label?}`; any other league name in a game is treated as a custom league ("Other"). There is no
backward-compatibility layer for the old two-league (League A/League B) logic.
`tools/xbotgo_core/identifier_scan.py` + `tools/pipeline/export_public.py` keep private values out of the public repository (see the publish plan);
`TestNoIdentifiersInCode` fails the suite if a deny-list term or a generic leak (email, long ID, personal path) appears under `tools/`.
Tests run on a synthetic project (`tools/editor/fixtures/project/`, built by `make_test_root.py`), never on real game data.
