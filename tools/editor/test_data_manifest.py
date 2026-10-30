"""Project files the unit tests (test_roundtrip.py) read. They come from the synthetic project in tools/editor/fixtures/project/ (no real data). Single source of truth for:
  - setUpModule in test_roundtrip.py (skips with a clear message if something is missing),
  - make_test_root.py (builds a ready-to-test project from the synthetic fixtures),
  - app_design/TEST_FIXTURES.md (the same list, explained).
Paths are relative to the project root, with forward slashes. Measured by logging every file the tests open."""

# (path, why the tests need it)
REQUIRED_FILES = [
    ("config/game_defaults.json", "defaults endpoints (/api/defaults) read a copy of it; the tests never write the real file (since 1BA)"),
    ("app_design/USER_GUIDE.html", "guide mirror test: must be byte-identical to tools/editor/static/guide.html (generated from it by make_test_root.py)"),
    ("out/2026-03-29/work/timeline.json", "the reference game for zoom, clip and Game() tests (also copied into temp games)"),
    ("out/2026-03-29/work/zoom_state.json", "zoom replays of the reference game; its hash is checked so tests cannot mutate it"),
    ("out/2026-03-29/work/review.csv", "reference game review table"),
    ("out/2026-03-29/work/game_info.json", "reference game setup (teams, logos, league)"),
    ("out/reviewed/2026-03-29_reviewed.csv", "reference reviewed CSV: round-trip, validity, sync and hash-guard tests"),
    ("out/reviewed/2026-03-21_reviewed.csv", "calendar classification (reviewed status)"),
    ("out/reviewed/2026-03-22_reviewed.csv", "calendar classification (reviewed status)"),
    ("out/reviewed/roster.csv", "roster endpoints and exact-order tests (needs at least one player row; columns name,no,short_name,contact)"),
    ("out/2026-03-07/work/review.csv", "legacy 10-column review.csv: calendar must show it disabled"),
    ("out/2026-03-08/work/review.csv", "calendar classification (unreviewed day)"),
    ("out/2026-03-14-g1/work/game_info.json", "multi-game day: calendar must show it disabled"),
    ("out/2026-03-14-g1/work/review.csv", "multi-game day, game 1"),
    ("out/2026-03-14-g2/work/review.csv", "multi-game day, game 2"),
    ("out/2026-03-21/game_info.json", "calendar classification"),
    ("out/2026-03-21/review.csv", "calendar classification"),
    ("out/2026-03-22/review.csv", "calendar classification"),
    ("shared/team_logos/metadata.json", "logo list endpoint"),
    ("shared/team_logos/league_a.png", "static logo streaming test; league logo validation"),
    ("shared/team_logos/home_fc.png", "game setup / defaults validation: logo files must exist"),
    ("shared/team_logos/guest_fc.png", "game setup validation: logo files must exist"),
]

# NOT needed by the tests: videos (*.mp4), out/<game>/clips, final, reels, _to_delete, utils/, a Google key, music.


# A game folder can be tidied (files in work/) or untidied (files at the game root) at any time, so for these
# entries EITHER location satisfies the test data requirement (added with Untidy, 1BA). The kit copies whichever exists
# to the first (primary) path.
ALTERNATIVES = {
}


def resolve(root, rel):
    """Absolute path of the first existing file among rel and its alternatives, or None."""
    import os
    for r in [rel] + ALTERNATIVES.get(rel, []):
        p = os.path.join(root, *r.split("/"))
        if os.path.isfile(p):
            return p
    return None
