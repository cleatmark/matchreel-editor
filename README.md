# XbotGo Review Editor

A local web app and command-line toolkit that turns a recording dump from an XbotGo auto-tracking camera into reviewed clips, zoom replays,
highlight and player reels, and a full-game video. You review the detected moments in the browser editor (times table on the left, video on the
right, click any time to seek), then render.

> Unofficial community project. It is not affiliated with or endorsed by XbotGo. It works on the files the XbotGo phone app writes; it contains
> no XbotGo firmware or app code.

## Quick start
1. Python 3.10+ and `pip install -r requirements.txt`.
2. Put `ffmpeg` and `ffprobe` on your PATH (or into `editor/utils/`).
3. Optional: `python editor/tools/pipeline/make_placeholder_logos.py` creates generic crests in `editor/shared/team_logos/`.
4. Copy `editor/config/game_defaults.example.json` to `editor/config/game_defaults.json` and fill in your team, leagues and featured player number(s).
   Nothing about your team is hard-coded: with no config the app shows generic placeholders (Home FC / Guest FC / League A).
5. Start the editor: `review_editor.bat` (Windows) or `./review_editor.sh`, then open the Guide from the app (the first-time setup is described there).

## Upgrading from Previous Versions

> **Important:** There is no in-place automatic migration from the pre-refactor directory layout (`tools/`, `out/`, `shared/`).  
> **We advise saving your existing installation aside and starting from a fresh checkout:**
>
> 1. **Move your current install aside:** Rename your existing project folder (e.g. rename `XbotGo` to `XbotGo_backup`).
> 2. **Check out from scratch:** Clone or download a clean checkout of this repository into your desired working folder.
> 3. **Copy your configuration and assets:**
>    - Settings: `config/game_defaults.json` -> `editor/config/game_defaults.json`
>    - Custom crests & logos: `shared/team_logos/` -> `editor/shared/team_logos/`
>    - Music beds & cheer sounds: `Music/` or `shared/Music/` -> `editor/shared/Music/`
>    - Google Sheets credentials: `shared/secrets/*.json` -> `editor/shared/secrets/`
> 4. **Move your game data:**
>    - Raw phone dumps: Move your match dumps (e.g. `03-29-26/`) into `input/` (`input/03-29-26/`).
>    - Processed output & reels: Move previous processed games from `out/` into `output/` (`output/2026-03-29/`).
>    - Master CSVs: Move `out/reviewed/*.csv` into `output/reviewed/`.

## User guide

- Read it on GitHub: [docs/USER_GUIDE.md](docs/USER_GUIDE.md)
- Styled web version (GitHub Pages): https://cleatmark.github.io/matchreel-editor/
- Inside the app: **Guide** button (same content).

## Per game
Copy the phone dump into `input/MM-DD-YY/` (`Videos/` and `com.blink.blinkfocos/`), open the editor, pick the date in the calendar, review the times,
Re-cut, adjust zoom replays, then select `✂️ Re-cut & Review ▾` > Final 4K Production. Processed game folders, clips, and reels are generated under `output/`.

## Configuration (`editor/config/game_defaults.json`, git-ignored)
| key | meaning |
|---|---|
| `team_name`, `team_logo`, `is_home` | your team, crest (path under the project) and default role |
| `leagues` | list of `{name, logo, label?}`; becomes the league choice in Game Setup and the tab-name suffix |
| `league` | name of the default league |
| `featured_players` | player number(s) preselected for individual player reels |
| `sheet_id` | optional Google Sheet ID for pushing review tabs (needs a service-account key in `editor/shared/secrets/*.json`); empty = off. Env override: `XBOTGO_SHEET_ID` |

## Project Architecture & Refactoring

The repository has been restructured into clean, separated tiers designed for zero-install execution and full USB drive portability:

```text
├── editor/                  # Complete self-contained application suite
│   ├── config/              # User settings (game_defaults.json)
│   ├── shared/              # Team crests, documentation, and assets
│   ├── tools/
│   │   ├── editor/          # Flask web app backend, static frontend UI, and unit tests
│   │   ├── pipeline/        # CLI scripts (sync_game.py, make_reels.py, zoom_edit.py, run_everything.py)
│   │   └── xbotgo_core/     # Standalone business logic library (game_state, zoom_state, csv_io, time_utils)
│   └── utils/               # Bundled helper binaries (ffmpeg, tesseract) auto-added to PATH
├── docs/                    # Architecture specification, API reference, and user guide
├── input/                   # Raw camera and mobile device dumps (MM-DD-YY)
├── output/                  # Generated match folders, 720p/4K reels, and reviewed master CSVs
└── tmp/                     # Disposable scratch data and test trees
```

### Complete USB Portability
- **Zero hardcoded paths or drive letters:** All batch files (`%~dp0`), shell scripts, and core environment logic (`xb_env.py`) dynamically resolve root directories relative to the script location.
- **Plug-and-play across drives:** The entire workspace can reside on and execute directly from external hard drives or USB sticks across varying Windows drive letters or POSIX mount points.
- **Path compatibility layer:** Automatically discovers and bridges legacy directory layouts (`tools/`, `out/`, `shared/`) and phone dump variations.

## Key Changes & Enhancements

- **Modular Core Package**: Extracted pure business logic from `server.py` into a standalone `editor/tools/xbotgo_core/` library (`game_state.py`, `zoom_state.py`, `csv_io.py`, `time_utils.py`, `organize_service.py`) with zero Flask dependencies.
- **Interactive Viewport Zoom & Pan**: Hardware-accelerated focal zoom (1.0× to 6.0× via `Ctrl + Wheel` / `Shift + Wheel`) centered on the mouse pointer with smooth drag-panning directly on the review video player and a quick-reset pill.
- **2-Pane Media Review Player**: Dedicated review modal with categorized tabs (Reels, Replays, Clips) and keyboard navigation for rapid quality inspection of rendered assets.
- **Revamped Zoom Replay Editor**: Manual glide keyframing (<kbd>K</kbd>), window boundary placement buttons (`Set [`, `Set ]`), 15-frame ORB homography temporal smoothing to eliminate panning jitter, and an in-app HTML5 loop preview modal.
- **Consolidated Action Workflow**: Unified top action menu (`✂️ Re-cut & Review ▾`) linking Fast 720p Re-cut, Featured Player Reels, and Final 4K Production with active job locking, process log inspection, and tidy output binding.
- **Playhead Tracking & Visual Feedback**: Smooth 60fps playhead tracking, persistent adjustment badges (`†`) indicating modified clips across reloads, click-to-loop playback, and an interactive player multi-select modal.
- **Safety & Input Guards**: Strict modifier state checks (`isStrictAltModifier`) preventing Windows Alt-Tab latching bugs from triggering hotkeys during plain typing; safe bare-URL launch without auto-selecting games; persistent Auto-push toggle.
- **Expanded Test Suite**: 179 automated unit tests verifying end-to-end roundtrip behavior, API contracts, frontend JavaScript syntax parsing, path portability, and data leak prevention gates.

## Tests
`run_tests.bat` (Windows) or `./run_tests.sh` (Linux/macOS) builds a fully synthetic project (fake teams, players, generated crests; no video, no network) and runs the entire 179-test suite.
A guard test fails if identifying values (names, e-mail addresses, IDs, personal paths) appear in the code.

## License
MIT, see `LICENSE`.
