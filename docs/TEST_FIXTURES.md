# Test fixtures

The unit tests run on a fully synthetic project (fake teams `Home FC` / `Guest FC`, players `Player N`, generated crests, no video).
`python editor/tools/editor/make_test_root.py` copies `editor/tools/` into a fresh folder and generates the synthetic project there with `editor/tools/editor/fixture_builder.py` (no test data is stored in the repository); `run_tests.bat` / `run_tests.sh` do that and run the suite.

| file (relative to the test project) | why the tests need it |
|---|---|
| `editor/config/game_defaults.json` | defaults endpoints (/api/defaults) read a copy of it; the tests never write the real file (since 1BA) |
| `editor/shared/documents/app_design/USER_GUIDE.html` | guide mirror test: must be byte-identical to tools/editor/static/guide.html (generated from it by make_test_root.py) |
| `output/2026-03-29/work/timeline.json` | the reference game for zoom, clip and Game() tests (also copied into temp games) |
| `output/2026-03-29/work/clockmap.json` | the reference game clockmap (halftime pause detection and fullgame_bat runner tests) |
| `output/2026-03-29/work/zoom_state.json` | zoom replays of the reference game; its hash is checked so tests cannot mutate it |
| `output/2026-03-29/work/review.csv` | reference game review table |
| `output/2026-03-29/work/game_info.json` | reference game setup (teams, logos, league) |
| `output/reviewed/2026-03-29_reviewed.csv` | reference reviewed CSV: round-trip, validity, sync and hash-guard tests |
| `output/reviewed/2026-03-21_reviewed.csv` | calendar classification (reviewed status) |
| `output/reviewed/2026-03-22_reviewed.csv` | calendar classification (reviewed status) |
| `output/reviewed/roster.csv` | roster endpoints and exact-order tests (needs at least one player row; columns name,no,short_name,contact) |
| `output/2026-03-07/work/review.csv` | legacy 10-column review.csv: calendar must show it disabled |
| `output/2026-03-08/work/review.csv` | calendar classification (unreviewed day) |
| `output/2026-03-14-g1/work/game_info.json` | multi-game day: calendar must show it disabled |
| `output/2026-03-14-g1/work/review.csv` | multi-game day, game 1 |
| `output/2026-03-14-g2/work/review.csv` | multi-game day, game 2 |
| `output/2026-03-21/game_info.json` | calendar classification |
| `output/2026-03-21/review.csv` | calendar classification |
| `output/2026-03-22/review.csv` | calendar classification |
| `editor/shared/team_logos/metadata.json` | logo list endpoint |
| `editor/shared/team_logos/league_a.png` | static logo streaming test; league logo validation |
| `editor/shared/team_logos/home_fc.png` | game setup / defaults validation: logo files must exist |
| `editor/shared/team_logos/guest_fc.png` | game setup validation: logo files must exist |
