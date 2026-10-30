# XbotGo Review Editor

A local web app and command-line toolkit that turns a recording dump from an XbotGo auto-tracking camera into reviewed clips, zoom replays,
highlight and player reels, and a full-game video. You review the detected moments in the browser editor (times table on the left, video on the
right, click any time to seek), then render.

> Unofficial community project. It is not affiliated with or endorsed by XbotGo. It works on the files the XbotGo phone app writes; it contains
> no XbotGo firmware or app code.

## Quick start
1. Python 3.10+ and `pip install -r requirements.txt`.
2. Put `ffmpeg` and `ffprobe` on your PATH (or into `utils/ffmpeg/bin/`).
3. Optional: `python tools/pipeline/make_placeholder_logos.py` creates generic crests in `shared/team_logos/`.
4. Copy `config/game_defaults.example.json` to `config/game_defaults.json` and fill in your team, leagues and featured player number(s).
   Nothing about your team is hard-coded: with no config the app shows generic placeholders (Home FC / Guest FC / League A).
5. Start the editor: `review_editor.bat` (Windows) or `./review_editor.sh`, then open the Guide from the app (the first-time setup is described there).

## User guide

- Read it on GitHub: [docs/USER_GUIDE.md](docs/USER_GUIDE.md)
- Styled web version (GitHub Pages, once enabled for the repo): https://cleatmark.github.io/matchreel-editor/
- Inside the app: **Guide** button (same content).

## Per game
Copy the phone dump into `MM-DD-YY/` (`Videos/` and `com.blink.blinkfocos/`), open the editor, pick the date in the calendar, review the times,
Re-cut, adjust zoom replays, then Menu > Final 4K Production.

## Configuration (`config/game_defaults.json`, git-ignored)
| key | meaning |
|---|---|
| `team_name`, `team_logo`, `is_home` | your team, crest (path under the project) and default role |
| `leagues` | list of `{name, logo, label?}`; becomes the league choice in Game Setup and the tab-name suffix |
| `league` | name of the default league |
| `featured_players` | player number(s) preselected for individual player reels |
| `sheet_id` | optional Google Sheet ID for pushing review tabs (needs a service-account key in `shared/secrets/*.json`); empty = off. Env override: `XBOTGO_SHEET_ID` |

## Layout
`tools/editor/` web app, `tools/pipeline/` command-line scripts, `tools/xbotgo_core/` shared logic, `docs/` architecture and API reference,
`config/` your settings, `shared/` crests, music and keys, `out/` results, `tmp/` scratch.

## Tests
`run_tests.bat` / `./run_tests.sh` build a fully synthetic project (fake teams, players, generated crests; no video, no network) and run the suite.
A guard test fails if identifying values (names, e-mail addresses, IDs, personal paths) appear in the code.

## License
MIT, see `LICENSE`.
