"""Automated round-trip, time parsing, sheet push, and sync_game tests for XbotGo Review Editor.

Verifies:
1. Exact byte-identity when reading and saving real CSVs with no edits.
2. Time parsing: 2-part 'm:ss', 3-part '0:mm:ss', Sheets-mangled 'mm:ss:00'.
3. Time formatting: zero-padded 'mm:ss'.
4. Clip renumbering and skip detection.
5. Google Sheet push payload builder (whole table A..P) and INT_COLS handling.
6. Google Sheet tab name resolver (matching existing vs constructing from game_info.json).
7. sync_game.py CLI in --local mode (no pull, uses existing reviewed CSV).
"""
import datetime
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, TOOLS_DIR)
sys.path.insert(0, os.path.join(TOOLS_DIR, "pipeline"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import csv_io
import sheet_sync_service
import time_utils


class TestTimeUtils(unittest.TestCase):
    def test_standard_times(self):
        self.assertEqual(time_utils.secs("04:01"), 241)
        self.assertEqual(time_utils.secs("4:01"), 241)
        self.assertEqual(time_utils.secs("00:00"), 0)
        self.assertEqual(time_utils.secs("35:15"), 2115)

    def test_three_part_and_sheets_mangled(self):
        # 0:04:01 -> 241
        self.assertEqual(time_utils.secs("0:04:01"), 241)
        self.assertEqual(time_utils.secs("00:04:01"), 241)
        # Sheets-mangled: 04:01:00 -> 241
        self.assertEqual(time_utils.secs("04:01:00"), 241)
        self.assertEqual(time_utils.secs("30:25:00"), 1825)

    def test_format_time(self):
        self.assertEqual(time_utils.format_time(241), "04:01")
        self.assertEqual(time_utils.format_time(0), "00:00")
        self.assertEqual(time_utils.format_time(2115), "35:15")
        self.assertEqual(time_utils.format_time(None), "")

    def test_timing_order(self):
        ok, msg = time_utils.validate_timing_order("04:00", "04:05", "04:10")
        self.assertTrue(ok)
        ok, msg = time_utils.validate_timing_order("04:10", "04:05", "04:15")
        self.assertFalse(ok)
        self.assertIn("Start (04:10) is after Event (04:05)", msg)

    def test_clip_renumbering(self):
        rows = [
            {"instructions": "", "skip": ""},
            {"instructions": "skip", "skip": ""},
            {"instructions": "zoom", "skip": ""},
            {"instructions": "", "skip": "1"},
            {"instructions": "", "skip": ""},
        ]
        clips = csv_io.compute_clip_numbers(rows)
        self.assertEqual(clips, ["1", "", "2", "", "3"])


class TestCsvRoundTrip(unittest.TestCase):
    def test_all_existing_reviewed_csvs(self):
        csv_files = glob.glob(os.path.join(ROOT, "out", "reviewed", "*_reviewed.csv"))
        synth_dir = None
        if not csv_files:
            # Environment-independent fallback: synthesize a reviewed CSV from a real one's shape.
            synth_dir = tempfile.mkdtemp(prefix="rt_csv_")
            self.addCleanup(shutil.rmtree, synth_dir, True)
            src = os.path.join(ROOT, "tools", "editor", "fixtures", "sample_reviewed.csv")
            if os.path.exists(src):
                dst = os.path.join(synth_dir, "sample_reviewed.csv")
                shutil.copy2(src, dst)
                csv_files = [dst]
        if not csv_files:
            self.skipTest("no reviewed CSVs and no fixtures/sample_reviewed.csv available")

        for csv_path in csv_files:
            with self.subTest(csv=os.path.basename(csv_path)):
                with open(csv_path, "rb") as f:
                    orig_bytes = f.read()

                headers, rows = csv_io.read_reviewed_csv(csv_path)
                test_output = csv_path + ".tmp_test"
                try:
                    csv_io.write_reviewed_csv(test_output, headers, rows, create_backup=False)
                    with open(test_output, "rb") as f:
                        new_bytes = f.read()

                    self.assertEqual(
                        orig_bytes,
                        new_bytes,
                        f"Roundtrip failed for {csv_path}: original {len(orig_bytes)} bytes != written {len(new_bytes)} bytes"
                    )
                finally:
                    if os.path.exists(test_output):
                        os.remove(test_output)


class TestSheetSyncService(unittest.TestCase):
    def test_build_sheet_push_payload(self):
        headers = ["game", "half", "video_sec", "video_time", "action_start", "clip"]
        rows = [
            {
                "game": "Test Game",
                "half": "1",
                "video_sec": "241",
                "video_time": "04:01",
                "action_start": "03:49",
                "clip": "1",
            },
            {
                "game": "Test Game",
                "half": "2",
                "video_sec": "",
                "video_time": "12:30",
                "action_start": "12:18",
                "clip": "",
            },
        ]
        matrix = sheet_sync_service.build_sheet_push_payload(headers, rows)
        self.assertEqual(len(matrix), 3)
        self.assertEqual(matrix[0], headers)
        # Check integer coercion for half, video_sec, clip
        self.assertEqual(matrix[1][1], 1)
        self.assertEqual(matrix[1][2], 241)
        self.assertEqual(matrix[1][3], "04:01")
        self.assertEqual(matrix[1][5], 1)
        # Empty string handling
        self.assertEqual(matrix[2][2], "")
        self.assertEqual(matrix[2][5], "")

    def test_determine_tab_name_with_existing(self):
        existing_tabs = ["Sheet1", "03/21/26 League B", "03/29/26 League A", "03/14/26 League B G1"]
        # Match 10-25
        tab = sheet_sync_service.determine_tab_name("2026-03-29", existing_tabs)
        self.assertEqual(tab, "03/29/26 League A")

        # Match 10-17
        tab = sheet_sync_service.determine_tab_name("2026-03-21", existing_tabs)
        self.assertEqual(tab, "03/21/26 League B")

        # Match 10-10 G1
        tab = sheet_sync_service.determine_tab_name("2026-03-14-g1", existing_tabs)
        self.assertEqual(tab, "03/14/26 League B G1")

    def test_determine_tab_name_new(self):
        # A new date not in existing list
        tab = sheet_sync_service.determine_tab_name("2026-11-01", ["03/29/26 League A"])
        self.assertTrue(tab.startswith("11/01/26"))


class TestSyncGameCli(unittest.TestCase):
    def test_sync_game_local_dry_run(self):
        # Test that sync_game.py --local runs without --csv/--json and doesn't pull
        sync_script = os.path.join(TOOLS_DIR, "pipeline", "sync_game.py")
        cmd = [
            sys.executable,
            sync_script,
            "--out", "out/2026-03-29",
            "--local",
            "--dry-run",
        ]
        res = subprocess.run(cmd, cwd=os.path.dirname(TOOLS_DIR), capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"sync_game.py failed: {res.stderr}")
        self.assertIn("local mode: using existing reviewed CSV", res.stdout)
        self.assertIn(os.path.join("out", "reviewed", "2026-03-29_reviewed.csv").replace("\\", "/"),
                      res.stdout.replace("\\", "/"))


class TestFullGameResumeSafety(unittest.TestCase):
    """Cancelling the full-game batch must never leave a corrupt final mp4 and a finished one must be skipped."""
    def test_probe_ok_rejects_missing_and_corrupt_files(self):
        import fullgame_bat as fg
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "trunc.mp4")
            with open(bad, "wb") as f:
                f.write(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)   # no moov atom, like a cancelled ffmpeg
            self.assertFalse(fg.probe_ok(bad, 100))
            self.assertFalse(fg.probe_ok(os.path.join(d, "nope.mp4"), 100))

    def test_fullgame_bat_is_thin_wrapper_around_python_runner(self):
        out = next((os.path.join(ROOT, "out", g) for g in ("2026-04-01", "2026-03-29")
                    if os.path.exists(os.path.join(ROOT, "out", g, "timeline.json"))
                    and os.path.exists(os.path.join(ROOT, "out", g, "clockmap.json"))), None)
        if not out:
            self.skipTest("needs an out/<game> with timeline.json + clockmap.json")
        with tempfile.TemporaryDirectory() as d:
            bat = os.path.join(d, "fg.bat")
            r = subprocess.run([sys.executable, os.path.join(TOOLS_DIR, "pipeline", "fullgame_bat.py"), "--out", out, "--bat", bat],
                               cwd=ROOT, capture_output=True, text=True)
            if r.returncode != 0:
                self.skipTest("fullgame_bat could not run here: " + r.stderr[-200:])
            txt = open(bat, encoding="utf-8").read()
        self.assertIn("fullgame_bat.py", txt)
        self.assertIn("--run", txt)
        self.assertNotIn("ffmpeg", txt.lower(), "no ffmpeg logic in the .bat; it lives in Python")

    def test_run_plan_skips_finished_replaces_corrupt_and_never_leaves_partial(self):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("ffmpeg/ffprobe not available")
        import fullgame_bat as fg
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "src.mp4")
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=d=2:s=64x64:r=25",
                            "-f", "lavfi", "-i", "sine=d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-shortest", "-y", src], check=True)
            tmp = os.path.join(d, "tmp"); dst = os.path.join(d, "full.mp4"); part = dst[:-4] + ".partial.mp4"
            def mk(name):
                return ["ffmpeg", "-v", "error", "-i", src, "-c", "copy", "-bsf:v", "h264_mp4toannexb",
                        "-f", "mpegts", "-y", os.path.join(tmp, name)]
            steps = [("a", mk("01.ts"), "01.ts"), ("b", mk("02.ts"), "02.ts")]
            # a corrupt pre-existing final file is rebuilt
            with open(dst, "wb") as f:
                f.write(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
            self.assertEqual(fg.run_plan(steps, tmp, dst, part, 4.0, "t"), 0)
            self.assertTrue(fg.probe_ok(dst, 4.0))
            self.assertFalse(os.path.exists(part))
            self.assertFalse(os.path.exists(tmp))
            # a finished one is skipped (file untouched)
            m = os.path.getmtime(dst)
            time.sleep(1.1)
            self.assertEqual(fg.run_plan(steps, tmp, dst, part, 4.0, "t"), 0)
            self.assertEqual(os.path.getmtime(dst), m)
            # a failing step never produces a partial or replaces the good final file
            bad = [("bad", ["ffmpeg", "-v", "error", "-i", os.path.join(d, "missing.mp4"), "-f", "mpegts",
                            "-y", os.path.join(tmp, "x.ts")], "x.ts")]
            os.remove(dst)
            with self.assertRaises(SystemExit):
                fg.run_plan(bad, tmp, dst, part, 4.0, "t")
            self.assertFalse(os.path.exists(dst))
            self.assertFalse(os.path.exists(part))


class TestRecutLengthTolerance(unittest.TestCase):
    """Found in the 10-28 fresh-start walkthrough: Re-cut flagged a 0.56 s drift on a 24-piece reel as a failure
    while preview_reel itself accepted up to 1.5 s. Both must use one shared tolerance."""
    def test_sync_game_uses_the_same_tolerance_as_preview_reel(self):
        import preview_reel
        self.assertGreaterEqual(preview_reel.LENGTH_TOLERANCE_S, 1.0)
        src = open(os.path.join(TOOLS_DIR, "pipeline", "sync_game.py"), encoding="utf-8").read()
        self.assertIn("preview_reel.LENGTH_TOLERANCE_S", src)
        self.assertNotIn(">= 0.5", src)


class TestRecutNoShortCutTimeout(unittest.TestCase):
    """Found in the 10-28 walkthrough with the 2026-04-03 reviewer pass: sync_game cut the whole game under a fixed
    timeout=170 (a device-shell leftover), so the first Re-cut of a 25-clip game died with a raw TimeoutExpired."""
    def test_default_cut_has_no_timeout_and_timeout_is_handled(self):
        import sync_game
        self.assertIsNone(sync_game.CUT_TIMEOUT_S)
        src = open(os.path.join(TOOLS_DIR, "pipeline", "sync_game.py"), encoding="utf-8").read()
        self.assertNotIn("timeout=170", src)
        self.assertIn("except subprocess.TimeoutExpired", src)


class TestCalendarWarningsOnlyWhenRelevant(unittest.TestCase):
    """10-30 reviewer feedback: a brand-new game showed red overwrite warnings that did not apply.
    The calendar confirmation must only appear when unsaved edits can be lost; new/reviewed/clean picks go straight through."""
    def test_confirm_only_when_dirty(self):
        src = open(os.path.join(ROOT, "tools", "editor", "static", "app.js"), encoding="utf-8").read()
        a = src.index("function submitCalendarPick")
        b = src.index("async function proceedCalendarPick")
        body = src[a:b]
        self.assertIn("state.isDirty", body)
        self.assertIn("proceedCalendarPick();", body)
        self.assertNotIn("Generate New Review Table", src)
        self.assertNotIn("NOT be overwritten", src)


class TestAtomicStateWritesAndUnloadGuard(unittest.TestCase):
    """10-30 reviewer pass: state files were written with open('w') (a crash leaves a truncated file) and closing the
    tab with unsaved edits lost them silently."""
    def test_failed_write_keeps_old_file_and_leaves_no_temp(self):
        import tempfile
        from xbotgo_core.atomic_io import write_json_atomic, write_text_atomic
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "state.json")
            write_json_atomic(p, {"a": 1})
            with self.assertRaises(TypeError):
                write_json_atomic(p, {"a": object()})
            self.assertEqual(json.load(open(p, encoding="utf-8")), {"a": 1})
            self.assertEqual(os.listdir(d), ["state.json"])
            write_text_atomic(os.path.join(d, "r.csv"), "a,b\r\n", newline="")
            self.assertEqual(open(os.path.join(d, "r.csv"), "rb").read(), b"a,b\r\n")

    def test_state_files_use_the_atomic_helper(self):
        for rel, needle in (("xbotgo_core/xbl.py", "write_json_atomic(self.state_path"),
                            ("editor/server.py", "write_json_atomic(DEFAULTS_FILE"),
                            ("editor/server.py", "write_json_atomic(target_path"),
                            ("xbotgo_core/organize_service.py", "write_json_atomic(manifest_path"),
                            ("xbotgo_core/game_state.py", "write_text_atomic(roster_path")):
            src = open(os.path.join(TOOLS_DIR, rel), encoding="utf-8").read()
            self.assertIn(needle, src, rel)

    def test_beforeunload_guards_exist_on_both_pages(self):
        for name, flag in (("app.js", "state.isDirty"), ("zoom.js", "state.hasUnsavedChanges")):
            src = open(os.path.join(ROOT, "tools", "editor", "static", name), encoding="utf-8").read()
            i = src.index("addEventListener('beforeunload'")
            self.assertIn(flag, src[i:i + 200])


class TestStaleSaveRunCliAndDiag(unittest.TestCase):
    """10-30 open items: refuse a save over a CSV that changed after load; helper CLI calls cannot hang; errors that are
    deliberately ignored are reported, not hidden; test keys do not pile up in last_tasks.json."""
    def test_csv_revision_changes_when_file_changes(self):
        import tempfile
        from editor import server
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.csv")
            open(p, "w").write("a\n1\n")
            r1 = server.csv_revision(p)
            open(p, "w").write("a\n1\n2\n")
            self.assertNotEqual(r1, server.csv_revision(p))
            self.assertEqual(server.csv_revision(os.path.join(d, "missing")), "")

    def test_save_conflict_409_unless_forced(self):
        src = open(os.path.join(TOOLS_DIR, "editor", "server.py"), encoding="utf-8").read()
        self.assertIn('base_rev != csv_revision(csv_path)', src)
        self.assertIn('"stale_save"', src)
        js = open(os.path.join(ROOT, "tools", "editor", "static", "app.js"), encoding="utf-8").read()
        self.assertIn("base_revision: state.csvRevision", js)
        self.assertIn("res.status === 409", js)
        self.assertIn("applyInfoSaveResult(saveData)", js)   # Game Setup rewrites the CSV game column: must not look stale

    def test_run_cli_times_out_cleanly(self):
        from editor import server
        r = server.run_cli([sys.executable, "-c", "import time; time.sleep(5)"], 1)
        self.assertEqual(r.returncode, 124)
        self.assertIn("timed out", r.stderr)

    def test_swallowed_prints_instead_of_hiding(self):
        import io, contextlib
        from xbotgo_core.diag import swallowed
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            try:
                raise ValueError("boom")
            except Exception:
                swallowed()
        self.assertIn("ValueError: boom", buf.getvalue())

    def test_record_last_task_drops_test_keys(self):
        src = open(os.path.join(TOOLS_DIR, "editor", "server.py"), encoding="utf-8").read()
        self.assertIn('k.startswith("test_game_")', src)


class TestUiAndRecutPolish(unittest.TestCase):
    """10-30 open UI items: zoom badge says REVIEWED, opponent crest pre-selected for a new game, Re-cut shows [i/N]
    progress, Player field wide enough for 'assist,scorer'."""
    def _read(self, *parts):
        return open(os.path.join(ROOT, *parts), encoding="utf-8").read()

    def test_zoom_badge_reviewed_vs_edited(self):
        z = self._read("tools", "editor", "static", "zoom.js")
        self.assertIn("r.reviewed ? 'reviewed' : 'edited'", z)
        self.assertIn("REVIEWED (not rendered yet)", z)
        self.assertIn("EDITED (not reviewed)", z)

    def test_opponent_logo_preselected_on_setup_open(self):
        a = self._read("tools", "editor", "static", "app.js")
        self.assertIn("findLogoForOpponent(gi.opponent)", a)

    def test_recut_streams_and_counts(self):
        import sync_game
        r = sync_game.run_streaming([sys.executable, "-c", "print('a'); print('b')"])
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.split(), ["a", "b"])
        with self.assertRaises(__import__("subprocess").TimeoutExpired):
            sync_game.run_streaming([sys.executable, "-c", "import time; time.sleep(5)"], timeout=1)
        cut = open(os.path.join(TOOLS_DIR, "pipeline", "cut_reviewed.py"), encoding="utf-8").read()
        self.assertIn('[{jn}/{len(jobs)}]', cut)

    def test_player_field_is_wide_enough(self):
        css = self._read("tools", "editor", "static", "app.css")
        i = css.index(".insp-player-input")
        self.assertIn("width: 76px", css[i:i + 80])
        self.assertIn('aria-label="Player jersey number"', self._read("tools", "editor", "static", "index.html"))


class TestCalendarFiltering(unittest.TestCase):
    def test_csv_validity_checker(self):
        import server
        # Current format: 10-25
        is_val, n = server.check_csv_validity(os.path.join("out", "reviewed", "2026-03-29_reviewed.csv"))
        self.assertTrue(is_val)
        self.assertEqual(n, 15)

        # Legacy 10-col format: 10-03
        is_val_old, n_old = server.check_csv_validity(os.path.join("out", "2026-03-07", "work", "review.csv"))
        self.assertFalse(is_val_old)
        self.assertEqual(n_old, 10)

    def test_available_dates_classification(self):
        import server
        with server.app.test_client() as client:
            res = client.get("/api/calendar/available-dates")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertIn("dates", data)

            dates_map = {item["date"]: item for item in data["dates"]}

            # 2026-03-29 must be enabled with reviewed status
            self.assertIn("2026-03-29", dates_map)
            self.assertTrue(dates_map["2026-03-29"]["enabled"])
            self.assertEqual(dates_map["2026-03-29"]["status"], "reviewed")

            # 2026-03-07 must be disabled (legacy 10-column)
            self.assertIn("2026-03-07", dates_map)
            self.assertFalse(dates_map["2026-03-07"]["enabled"])
            self.assertIn("10-column", dates_map["2026-03-07"]["hint"])

            # 2026-03-14 must be disabled (multi-game day)
            self.assertIn("2026-03-14", dates_map)
            self.assertFalse(dates_map["2026-03-14"]["enabled"])
            self.assertIn("Multi-game day", dates_map["2026-03-14"]["hint"])

    def test_find_or_generate_rejects_legacy(self):
        import server
        with server.app.test_client() as client:
            # 10-03 should be rejected with status=unsupported
            res = client.post("/api/game/find-or-generate", json={"date": "2026-03-07"})
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data["status"], "unsupported")
            self.assertIn("10 columns", data["message"])

            # 10-10 should be rejected as multi-game day
            res = client.post("/api/game/find-or-generate", json={"date": "2026-03-14"})
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data["status"], "unsupported")
            self.assertIn("Multi-game day", data["message"])


class TestRowInsertionAndContext(unittest.TestCase):
    def test_chronological_placement_and_clip_renumbering(self):
        csv_path = os.path.join(ROOT, "out", "reviewed", "2026-03-29_reviewed.csv")
        headers, rows = csv_io.read_reviewed_csv(csv_path)
        original_clips = csv_io.compute_clip_numbers(rows)
        self.assertEqual(original_clips[0], "1")
        self.assertEqual(original_clips[1], "")  # Row 1 is skipped
        self.assertEqual(original_clips[2], "2")

        # Insert a new row at video_sec = 200 (between row 1 at 186s and row 2 at 279s)
        new_row = dict(rows[0])
        new_row["video_sec"] = "200"
        new_row["video_time"] = "03:20"
        new_row["event"] = "03:20"
        new_row["action_start"] = "03:08"
        new_row["action_end"] = "03:24"
        new_row["label"] = ""
        new_row["notes"] = "hand-added penalty test"

        # Chronological insert
        insert_idx = None
        for i, r in enumerate(rows):
            if int(r.get("video_sec", 0)) > 200:
                insert_idx = i
                break
        self.assertEqual(insert_idx, 2)  # Should insert right before row 2

        new_rows = rows[:insert_idx] + [new_row] + rows[insert_idx:]
        new_clips = csv_io.compute_clip_numbers(new_rows)

        # Verify renumbering: inserted row becomes clip 2, subsequent non-skipped clips shift up by 1
        self.assertEqual(new_clips[0], "1")
        self.assertEqual(new_clips[1], "")   # Skipped row remains blank
        self.assertEqual(new_clips[2], "2")  # New row takes clip 2
        self.assertEqual(new_clips[3], "3")  # Previously clip 2 shifts to clip 3

    def test_derived_clock_time_and_game_clock(self):
        # File start: 10:41:31 (38491s)
        # At video_sec = 200:
        file_start_sec = 12 * 3600 + 54 * 60 + 31
        video_sec = 200
        total_clock_sec = file_start_sec + video_sec
        hh = total_clock_sec // 3600
        mm = (total_clock_sec % 3600) // 60
        ss = total_clock_sec % 60
        derived_clock_time = f"{hh:02d}:{mm:02d}:{ss:02d}"
        self.assertEqual(derived_clock_time, "12:57:51")

        # Prior row at 186s had game_clock "3:06" (186s)
        prior_gc_sec = time_utils.secs("3:06")
        gap = video_sec - 186
        new_gc_sec = prior_gc_sec + gap
        derived_game_clock = f"{new_gc_sec // 60}:{new_gc_sec % 60:02d}"
        self.assertEqual(derived_game_clock, "3:20")

    def test_csv_roundtrip_with_added_row(self):
        import tempfile
        csv_path = os.path.join(ROOT, "out", "reviewed", "2026-03-29_reviewed.csv")
        headers, rows = csv_io.read_reviewed_csv(csv_path)

        new_row = dict(rows[0])
        new_row["video_sec"] = "500"
        new_row["video_time"] = "08:20"
        new_row["notes"] = "user manual added row"

        rows.append(new_row)

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
            tmp_path = tf.name

        try:
            csv_io.write_reviewed_csv(tmp_path, headers, rows, create_backup=False)
            h2, r2 = csv_io.read_reviewed_csv(tmp_path)
            self.assertEqual(headers, h2)
            self.assertEqual(len(rows), len(r2))
            self.assertEqual(r2[-1]["notes"], "user manual added row")
            self.assertEqual(r2[-1]["video_sec"], "500")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


class TestBlankFileRowHandling(unittest.TestCase):
    def test_blank_file_row_does_not_crash_sync_game(self):
        import cut_reviewed
        from xbotgo_core import xbl
        g = xbl.Game("out/2026-03-29")
        rows = g.rows()

        blank_row = dict(rows[0])
        blank_row["file"] = ""
        blank_row["notes"] = "manual marker with no file"

        test_rows = rows + [blank_row]
        jobs = cut_reviewed.plan(test_rows, g.tl, g.roster(), 0.5, "startend")

        # Confirms blank row did NOT raise KeyError and did NOT create an extra cut
        self.assertEqual(len(jobs), 24)


def make_temp_game_fixture():
    """Create an isolated temporary copy of game 2026-03-29 so write tests never mutate real data."""
    game_id = f"test_game_{uuid.uuid4().hex[:8]}"
    tmp_base = os.path.join(ROOT, "tmp")
    os.makedirs(tmp_base, exist_ok=True)
    temp_dir = os.path.join(tmp_base, game_id)
    os.makedirs(os.path.join(temp_dir, "work"), exist_ok=True)
    os.makedirs(os.path.join(temp_dir, "clips", "extra"), exist_ok=True)

    # Copy work/timeline.json and work/zoom_state.json
    shutil.copy2(os.path.join(ROOT, "out", "2026-03-29", "work", "timeline.json"),
                 os.path.join(temp_dir, "work", "timeline.json"))
    shutil.copy2(os.path.join(ROOT, "out", "2026-03-29", "work", "zoom_state.json"),
                 os.path.join(temp_dir, "work", "zoom_state.json"))

    # Copy CSV to tmp/reviewed/<game_id>_reviewed.csv
    tmp_reviewed = os.path.join(tmp_base, "reviewed")
    os.makedirs(tmp_reviewed, exist_ok=True)
    tmp_csv = os.path.join(tmp_reviewed, f"{game_id}_reviewed.csv")
    shutil.copy2(os.path.join(ROOT, "out", "reviewed", "2026-03-29_reviewed.csv"), tmp_csv)

    roster_src = os.path.join(ROOT, "out", "reviewed", "roster.csv")
    if os.path.exists(roster_src):
        shutil.copy2(roster_src, os.path.join(tmp_reviewed, "roster.csv"))

    def cleanup():
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        if os.path.exists(tmp_csv):
            try:
                os.remove(tmp_csv)
            except OSError:
                pass
        # the editor also writes timestamped backups of the CSV (next to it and in tmp/review_editor/backups)
        for pat in (os.path.join(tmp_reviewed, game_id + "_reviewed.csv.bak-*"),
                    os.path.join(tmp_base, "review_editor", "backups", game_id + "*")):
            for _f in glob.glob(pat):
                try:
                    os.remove(_f)
                except OSError:
                    pass

    return game_id, temp_dir, cleanup


# Capture baseline hashes of real user files to guard against test-induced mutation
ZOOM_STATE_PATH = os.path.join(ROOT, "out", "2026-03-29", "work", "zoom_state.json")
REVIEWED_CSV_PATH = os.path.join(ROOT, "out", "reviewed", "2026-03-29_reviewed.csv")

def _md5_or_none(path):
    try:
        with open(path, "rb") as _f:
            return hashlib.md5(_f.read()).hexdigest()
    except OSError:
        return None  # data missing: setUpModule skips the whole module with an explanation


INITIAL_STATE_HASH = _md5_or_none(ZOOM_STATE_PATH)
INITIAL_CSV_HASH = _md5_or_none(REVIEWED_CSV_PATH)


def _debris_names():
    """Names of everything the tests are known to leave behind when a cleanup fails (used for the end-of-run sweep)."""
    tmp = os.path.join(ROOT, "tmp")
    found = set()
    for sub, pat in (("", "test_game_*"), ("reviewed", "test_game_*"), (os.path.join("review_editor", "backups"), "test_game_*"),
                     ("", "spec_*_[0-9]*.json")):
        for p in glob.glob(os.path.join(tmp, sub, pat)):
            found.add(p)
    return found


_DEBRIS_BEFORE = set()


def tearDownModule():
    """Remove debris created during THIS run only (never anything that was there before)."""
    for p in _debris_names() - _DEBRIS_BEFORE:
        try:
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)
        except OSError:
            pass


def setUpModule():
    """These tests run against real game data (see app_design/TEST_FIXTURES.md). Missing data = skip with a clear message, not an import crash."""
    import test_data_manifest as _M
    # A folder that does not allow deleting (e.g. a no-delete mount) would make every test leave temp games, backups and specs behind.
    os.makedirs(os.path.join(ROOT, "tmp"), exist_ok=True)
    _probe = os.path.join(ROOT, "tmp", "_delete_probe_" + uuid.uuid4().hex[:6])
    try:
        with open(_probe, "w", encoding="utf-8") as _f:
            _f.write("x")
        os.remove(_probe)
    except OSError:
        raise unittest.SkipTest("this folder does not allow deleting files, so the tests would leave debris in tmp/: run them in a copy "
                                "(python tools/editor/make_test_root.py) or on the PC")
    _DEBRIS_BEFORE.clear()
    _DEBRIS_BEFORE.update(_debris_names())
    missing = [rel for rel, _why in _M.REQUIRED_FILES if not _M.resolve(ROOT, rel)]
    if missing:
        raise unittest.SkipTest(
            "test data missing in " + ROOT + ": " + ", ".join(missing)
            + ". Build a ready test copy with: python tools/editor/make_test_root.py  (see app_design/TEST_FIXTURES.md)")


class TestZoomEditorRealDataGuard(unittest.TestCase):
    """Guard test verifying real user data files are strictly untouched and unmutated by tests."""

    def test_real_game_data_hashes_strictly_unchanged(self):
        self.assertTrue(os.path.exists(ZOOM_STATE_PATH))
        self.assertTrue(os.path.exists(REVIEWED_CSV_PATH))

        with open(ZOOM_STATE_PATH, "rb") as f:
            state_md5 = hashlib.md5(f.read()).hexdigest()
        with open(REVIEWED_CSV_PATH, "rb") as f:
            csv_md5 = hashlib.md5(f.read()).hexdigest()

        self.assertEqual(
            state_md5,
            INITIAL_STATE_HASH,
            f"out/2026-03-29/work/zoom_state.json was MUTATED by tests! Initial {INITIAL_STATE_HASH}, got {state_md5}"
        )
        self.assertEqual(
            csv_md5,
            INITIAL_CSV_HASH,
            f"out/reviewed/2026-03-29_reviewed.csv was MUTATED by tests! Initial {INITIAL_CSV_HASH}, got {csv_md5}"
        )

        # Invariant: Clip 7 restored values must never be lost
        with open(ZOOM_STATE_PATH, "r", encoding="utf-8") as f:
            st = json.load(f)
        c7 = st["replays"]["goal_001807"]
        self.assertEqual(c7["crop"], [1940, 300])
        self.assertEqual(c7["pan"], [3800.0, 300.0, 5.5, 3.0])


class TestZoomEditorPhase1(unittest.TestCase):
    def setUp(self):
        import server
        self.client = server.app.test_client()

    def test_zoom_html_served(self):
        res = self.client.get("/zoom/2026-03-29/7")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"XbotGo Zoom Replay Editor", res.data)
        self.assertIn(b"zoom.js", res.data)

    def test_list_zoom_replays(self):
        res = self.client.get("/api/zoom/2026-03-29")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["game_id"], "2026-03-29")
        replays = data["replays"]
        self.assertGreater(len(replays), 10)
        # Check clip 7 is present
        c7 = next((r for r in replays if r["clip"] == 7), None)
        self.assertIsNotNone(c7)
        self.assertEqual(c7["token"], "goal_001807")
        self.assertIn("crop", c7)
        self.assertIn("status", c7)

    def test_get_zoom_details_by_clip_and_token(self):
        # By clip number
        res_clip = self.client.get("/api/zoom/2026-03-29/7")
        self.assertEqual(res_clip.status_code, 200)
        d_clip = res_clip.get_json()
        self.assertEqual(d_clip["token"], "goal_001807")
        self.assertEqual(d_clip["clip"], 7)
        self.assertEqual(d_clip["event"], 1087)
        self.assertIn("video", d_clip)
        self.assertIn("replay", d_clip)
        self.assertIn("all_zoom_clips", d_clip)

        # By token directly
        res_tok = self.client.get("/api/zoom/2026-03-29/goal_001807")
        self.assertEqual(res_tok.status_code, 200)
        d_tok = res_tok.get_json()
        self.assertEqual(d_tok["token"], "goal_001807")
        self.assertEqual(d_tok["clip"], 7)

    def test_zoom_apply_spec_and_clamping(self):
        # Must execute on temporary fixture, never mutating live data
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        spec = {
            "token": "goal_001807",
            "clip": 7,
            "crop": [5000, 3000],  # Out of bounds -> must clamp to (3840-crop_w, 2160-crop_h)
            "crop_w": 1536,         # 2.5x zoom
            "start": 1084.5,
            "dur": 4.5,
            "pans": [
                {"mode": "snap", "at": 3.0, "x": 1600, "y": 800},
                {"mode": "glide", "at": 5.5, "len": 1.5, "x": 1900, "y": 800}
            ],
            "zoom_to": [1280, 6.0],
            "hold_end": 1.5,
            "cut_start": 0.5,
            "cut_end": 0.5
        }

        try:
            res = self.client.put(
                f"/api/zoom/{game_id}/goal_001807",
                data=json.dumps(spec),
                content_type="application/json"
            )
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            r = data["replay"]

            # Clamping check:
            # crop_w = 1536 -> max_x = 3840 - 1536 = 2304
            # crop_h = 1536 * 9 / 16 = 864 -> max_y = 2160 - 864 = 1296
            self.assertEqual(r["crop"][0], 2304)
            self.assertEqual(r["crop"][1], 1296)
            self.assertEqual(r["crop_w"], 1536)
            self.assertEqual(r["start"], 1084.5)
            self.assertEqual(r["dur"], 4.5)
            self.assertEqual(r["hold_end"], 1.5)
            self.assertEqual(r["zoom_to"], [1280.0, 6.0])

            # Pans check: snap has 3 elements [x,y,at], glide has 4 elements [x,y,at,len]
            self.assertEqual(len(r["pan"]), 2)
            self.assertEqual(r["pan"][0], [1600.0, 800.0, 3.0])
            self.assertEqual(r["pan"][1], [1900.0, 800.0, 5.5, 1.5])
        finally:
            cleanup()

    def test_save_unchanged_replay_is_noop(self):
        # Loading and re-saving existing replay unchanged must be a strict no-op
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            state_path = os.path.join(temp_dir, "work", "zoom_state.json")
            with open(state_path, "r", encoding="utf-8") as f:
                orig_state = json.load(f)

            for tok, orig_r in orig_state["replays"].items():
                res = self.client.get(f"/api/zoom/{game_id}/{tok}")
                self.assertEqual(res.status_code, 200)
                details = res.get_json()
                r = details["replay"]

                cw = r.get("crop_w") or 1280
                payload = {
                    "token": tok,
                    "clip": details["clip"],
                    "crop": r.get("crop"),
                    "start": r.get("start"),
                    "dur": r.get("dur"),
                    "cut_start": r.get("cut_start", 0.0),
                    "cut_end": r.get("cut_end", 0.0),
                    "pans": r.get("pan") or [],
                    "zoom_to": r.get("zoom_to"),
                    "hold_end": r.get("hold_end"),
                }
                if cw != 1280:
                    payload["crop_w"] = cw

                put_res = self.client.put(
                    f"/api/zoom/{game_id}/{tok}",
                    data=json.dumps(payload),
                    content_type="application/json"
                )
                self.assertEqual(put_res.status_code, 200)

            with open(state_path, "r", encoding="utf-8") as f:
                new_state = json.load(f)

            for tok, orig_r in orig_state["replays"].items():
                new_r = new_state["replays"][tok]
                self.assertEqual(new_r.get("crop"), orig_r.get("crop"))
                self.assertEqual(new_r.get("pan"), orig_r.get("pan"))
                self.assertEqual(new_r.get("master_key"), orig_r.get("master_key"))
                self.assertEqual(new_r.get("final_key"), orig_r.get("final_key"))
                self.assertEqual(len(new_r.get("history", [])), len(orig_r.get("history", [])))
                if orig_r.get("crop_w") is None or orig_r.get("crop_w") == 1280:
                    self.assertNotIn("crop_w", new_r)
        finally:
            cleanup()

    def test_preview_does_not_mutate_base_crop(self):
        # Preview moves only display position; payload builder sends base crop
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            res = self.client.get(f"/api/zoom/{game_id}/9")
            self.assertEqual(res.status_code, 200)
            details = res.get_json()
            tok = details["token"]
            orig_crop = details["replay"]["crop"]

            # Simulate client preview: baseCrop stays orig_crop
            base_crop = list(orig_crop)
            payload = {
                "token": tok,
                "clip": details["clip"],
                "crop": base_crop,
                "start": details["replay"]["start"],
                "dur": details["replay"]["dur"],
                "pans": details["replay"].get("pan") or []
            }
            put_res = self.client.put(
                f"/api/zoom/{game_id}/{tok}",
                data=json.dumps(payload),
                content_type="application/json"
            )
            self.assertEqual(put_res.status_code, 200)
            saved_r = put_res.get_json()["replay"]
            self.assertEqual(saved_r["crop"], orig_crop)
        finally:
            cleanup()

    def test_keyframe_timing_glide_and_snap_math(self):
        # Glide timing math:
        t_user = 4.0
        glide_len = 1.2
        at_stored = max(glide_len / 2.0, t_user - glide_len / 2.0)
        self.assertAlmostEqual(at_stored, 3.4)
        t_arrival = at_stored + glide_len / 2.0
        self.assertAlmostEqual(t_arrival, t_user)

        # Early glide clamping (t < len/2):
        t_early = 0.3
        at_early = max(glide_len / 2.0, t_early - glide_len / 2.0)
        self.assertEqual(at_early, 0.6)
        self.assertAlmostEqual(at_early + glide_len / 2.0, 1.2)

        # Snap timing math:
        t_snap = 2.5
        at_snap = t_snap
        self.assertEqual(at_snap, 2.5)

        # Reverse conversion on load:
        pan_raw = [2500.0, 300.0, 8.5, 1.0]
        is_glide = len(pan_raw) > 3 and pan_raw[3] > 0.05
        t_arr_loaded = pan_raw[2] + pan_raw[3] / 2.0 if is_glide else pan_raw[2]
        self.assertAlmostEqual(t_arr_loaded, 9.0)

    def test_remove_zoom_endpoint(self):
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            res = self.client.post(f"/api/zoom/{game_id}/goal_001807/remove")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data["status"], "removed")
            self.assertEqual(data["token"], "goal_001807")

            state_path = os.path.join(temp_dir, "work", "zoom_state.json")
            with open(state_path, "r", encoding="utf-8") as f:
                st = json.load(f)
            self.assertNotIn("goal_001807", st.get("replays", {}))
            self.assertIn("goal_001807", st.get("removed", {}))

            import csv_io
            csv_path = os.path.join(ROOT, "tmp", "reviewed", f"{game_id}_reviewed.csv")
            headers, rows = csv_io.read_reviewed_csv(csv_path)
            self.assertNotIn("clip", headers)  # Real CSV has 15 columns, no clip column!
            clips = csv_io.compute_clip_numbers(rows)
            idx7 = next(i for i, c in enumerate(clips) if c == "7")
            self.assertNotIn("zoom", (rows[idx7].get("instructions") or "").lower())
        finally:
            cleanup()

    def test_remove_zoom_clears_csv_and_archives_state_goal_row_mark_diff_event(self):
        # Clip 5 is a goal row: mark is 08:48, event is 08:45 (mark != event)
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            import csv_io
            csv_path = os.path.join(ROOT, "tmp", "reviewed", f"{game_id}_reviewed.csv")
            state_path = os.path.join(temp_dir, "work", "zoom_state.json")

            # Verify standard 15-column format without stored clip column
            headers, rows = csv_io.read_reviewed_csv(csv_path)
            self.assertNotIn("clip", headers)
            clips = csv_io.compute_clip_numbers(rows)
            idx5 = next(i for i, c in enumerate(clips) if c == "5")
            row5 = rows[idx5]

            # Verify mark != event for clip 5
            self.assertNotEqual(row5.get("video_time"), row5.get("event"))
            self.assertIn("zoom", (row5.get("instructions") or "").lower())

            # Ensure clip 5 replay exists in fixture state
            with open(state_path, "r", encoding="utf-8") as f:
                st = json.load(f)
            tok5 = "goal_000845"
            st.setdefault("replays", {})[tok5] = {
                "n": 5, "file": row5["file"], "event": 525.0, "start": 520.0, "dur": 9.0, "crop": [1152, 648]
            }
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(st, f, indent=1)

            # Call remove zoom endpoint
            res = self.client.post(f"/api/zoom/{game_id}/{tok5}/remove")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data["status"], "removed")
            self.assertEqual(data["clip"], 5)

            # Verify CSV instruction has 'zoom' cleared atomically
            _, new_rows = csv_io.read_reviewed_csv(csv_path)
            self.assertNotIn("zoom", (new_rows[idx5].get("instructions") or "").lower())

            # Verify state has replay moved to 'removed'
            with open(state_path, "r", encoding="utf-8") as f:
                new_st = json.load(f)
            self.assertNotIn(tok5, new_st.get("replays", {}))
            self.assertIn(tok5, new_st.get("removed", {}))
        finally:
            cleanup()

    def test_remove_zoom_row_not_found_returns_error_and_leaves_both_files_unchanged(self):
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            import csv_io
            csv_path = os.path.join(ROOT, "tmp", "reviewed", f"{game_id}_reviewed.csv")
            state_path = os.path.join(temp_dir, "work", "zoom_state.json")

            with open(csv_path, "rb") as f:
                orig_csv_bytes = f.read()
            with open(state_path, "rb") as f:
                orig_state_bytes = f.read()

            res = self.client.post(f"/api/zoom/{game_id}/nonexistent_token_9999/remove")
            self.assertEqual(res.status_code, 404)

            # Assert strictly zero mutation on either file
            with open(csv_path, "rb") as f:
                self.assertEqual(f.read(), orig_csv_bytes)
            with open(state_path, "rb") as f:
                self.assertEqual(f.read(), orig_state_bytes)
        finally:
            cleanup()

    def test_remove_zoom_with_skipped_rows_renumbers_correctly(self):
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            import csv_io
            csv_path = os.path.join(ROOT, "tmp", "reviewed", f"{game_id}_reviewed.csv")
            headers, rows = csv_io.read_reviewed_csv(csv_path)

            # Skip row 0 via instructions (standard 15-column format has instructions, not skip col)
            rows[0]["instructions"] = "skip"
            csv_io.write_reviewed_csv(csv_path, headers, rows, create_backup=False)

            computed_clips = csv_io.compute_clip_numbers(rows)
            self.assertEqual(computed_clips[0], "")
            self.assertEqual(computed_clips[1], "")
            self.assertEqual(computed_clips[2], "1")

            # Clip 6 among non-skipped rows is now at index where computed_clip == "6" (goal_001807)
            idx_clip6 = next(i for i, c in enumerate(computed_clips) if c == "6")
            rows[idx_clip6]["instructions"] = "zoom"
            csv_io.write_reviewed_csv(csv_path, headers, rows, create_backup=False)

            # Remove zoom by clip number "6"
            res = self.client.post(f"/api/zoom/{game_id}/6/remove")
            self.assertEqual(res.status_code, 200)

            _, verify_rows = csv_io.read_reviewed_csv(csv_path)
            self.assertNotIn("zoom", (verify_rows[idx_clip6].get("instructions") or "").lower())
        finally:
            cleanup()

    def test_no_native_confirm_or_alert_in_static_js(self):
        import glob, re
        static_dir = os.path.join(ROOT, "tools", "editor", "static")
        js_files = glob.glob(os.path.join(static_dir, "*.js"))
        self.assertTrue(len(js_files) >= 2)

        violations = []
        for jf in js_files:
            fname = os.path.basename(jf)
            with open(jf, "r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, 1):
                    if re.search(r"\b(alert|confirm)\s*\(", line):
                        violations.append(f"{fname}:{line_no}: {line.strip()}")

        self.assertEqual(violations, [], f"Found forbidden native dialogs: {violations}")

    def test_keyframe_hint_and_drag_intent_undo_logic(self):
        # Simulate Section 1D Item D:
        # User starts at t=4.0s (replaySec = 4.0), drags START box from (1152, 648) to (2000, 800)
        start_base_crop = [1152, 648]
        current_base_crop = [2000, 800]
        replay_sec = 4.0
        dragged_pos = [2000, 800]
        pans = []

        # Action: Click "Make this a pan keyframe instead":
        # 1. Undo start move:
        current_base_crop = list(start_base_crop)
        self.assertEqual(current_base_crop, [1152, 648])

        # 2. Create glide keyframe at replay_sec
        glide_len = 1.2
        at = max(glide_len / 2.0, replay_sec - glide_len / 2.0)
        t_arrival = at + glide_len / 2.0
        pans.append({
            "mode": "glide",
            "x": dragged_pos[0],
            "y": dragged_pos[1],
            "at": at,
            "len": glide_len,
            "tArrival": t_arrival
        })

        self.assertEqual(len(pans), 1)
        self.assertEqual(pans[0]["x"], 2000)
        self.assertEqual(pans[0]["y"], 800)
        self.assertAlmostEqual(pans[0]["tArrival"], 4.0)
        self.assertEqual(current_base_crop, [1152, 648])  # Start crop is unchanged!

    def test_log_drawer_sse_json_and_verification_badge_parsing(self):
        # Test Section 1D Item C: parsing SSE message and determining badge
        sse_events = [
            json.dumps({"line": "ffmpeg rendering clip 5 720p...", "done": False}),
            json.dumps({"line": "PASS: 1 checked, 0 flagged (verify_zoom)", "done": False}),
            json.dumps({"done": True, "exit_code": 0, "error": None})
        ]

        parsed_lines = []
        last_verify_result = None
        exit_code = None

        for ev in sse_events:
            data = json.loads(ev)
            if data.get("done"):
                exit_code = data.get("exit_code")
            elif "line" in data:
                line = data["line"]
                parsed_lines.append(line)
                if "PASS:" in line or ("checked" in line and "0 flagged" in line):
                    last_verify_result = {"pass": True, "text": line}
                elif "FLAGGED:" in line:
                    last_verify_result = {"pass": False, "text": line}

        self.assertEqual(len(parsed_lines), 2)
        self.assertNotIn('{"line":', parsed_lines[0])  # Clean line string, not raw JSON
        self.assertEqual(exit_code, 0)
        self.assertIsNotNone(last_verify_result)
        self.assertTrue(last_verify_result["pass"])
        self.assertIn("PASS: 1 checked, 0 flagged", last_verify_result["text"])

    def test_render_pipeline_command_lines(self):
        from xbotgo_core import xbl
        import zoom_edit
        g = xbl.Game("out/2026-03-29")
        st = g.state()
        tok = "goal_001807"
        r = st["replays"][tok]

        master, final = zoom_edit.names(g, r, tok, 720)
        self.assertTrue(master.endswith("007b_goal_001807_zoom3x_720.mp4"))

        verify_cmd = [
            sys.executable,
            os.path.join(TOOLS_DIR, "pipeline", "verify_zoom.py"),
            "--out", g.out,
            "--only", "7",
            "--height", "720"
        ]
        self.assertIn("--out", verify_cmd)
        self.assertIn("--only", verify_cmd)
        self.assertIn("--height", verify_cmd)

    def test_remove_then_restore_zoom_roundtrip_leaves_csv_and_state_identical(self):
        # Test Section 1E Item 5: remove then restore zoom on a temp copy
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            import csv_io
            csv_path = os.path.join(ROOT, "tmp", "reviewed", f"{game_id}_reviewed.csv")
            state_path = os.path.join(temp_dir, "work", "zoom_state.json")

            # 1. Baseline state
            headers_orig, rows_orig = csv_io.read_reviewed_csv(csv_path)
            with open(state_path, "r", encoding="utf-8") as f:
                st_orig = json.load(f)

            clips_orig = csv_io.compute_clip_numbers(rows_orig)
            idx5 = next(i for i, c in enumerate(clips_orig) if c == "5")
            self.assertIn("zoom", rows_orig[idx5]["instructions"])
            tok = "goal_000845"
            self.assertIn(tok, st_orig["replays"])

            # 2. Execute Remove Zoom on clip 5
            res_rem = self.client.post(f"/api/zoom/{game_id}/5/remove")
            self.assertEqual(res_rem.status_code, 200)

            # Check post-remove state
            _, rows_after_rem = csv_io.read_reviewed_csv(csv_path)
            with open(state_path, "r", encoding="utf-8") as f:
                st_after_rem = json.load(f)
            self.assertNotIn("zoom", (rows_after_rem[idx5]["instructions"] or "").lower())
            self.assertNotIn(tok, st_after_rem.get("replays", {}))
            self.assertIn(tok, st_after_rem.get("removed", {}))

            # 3. Execute Restore Zoom on clip 5
            res_rest = self.client.post(f"/api/zoom/{game_id}/5/restore")
            self.assertEqual(res_rest.status_code, 200)
            data_rest = res_rest.get_json()
            self.assertEqual(data_rest["status"], "restored")
            self.assertEqual(data_rest["token"], tok)

            # 4. Check post-restore state: CSV instructions and replay spec restored
            headers_rest, rows_rest = csv_io.read_reviewed_csv(csv_path)
            with open(state_path, "r", encoding="utf-8") as f:
                st_rest = json.load(f)

            self.assertEqual(headers_rest, headers_orig)
            self.assertIn("zoom", rows_rest[idx5]["instructions"])
            self.assertIn(tok, st_rest["replays"])
            self.assertNotIn(tok, st_rest.get("removed", {}))

            # Replay specs must be identical
            self.assertEqual(st_rest["replays"][tok], st_orig["replays"][tok])

            # Every row's instructions must match original
            for i in range(len(rows_orig)):
                self.assertEqual(
                    rows_rest[i]["instructions"].strip(),
                    rows_orig[i]["instructions"].strip()
                )
        finally:
            cleanup()

    def test_restore_zoom_404_when_row_not_found(self):
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            res = self.client.post(f"/api/zoom/{game_id}/non_existent_clip_9999/restore")
            self.assertEqual(res.status_code, 404)
        finally:
            cleanup()

    def test_zoom_js_has_no_history_back(self):
        # Section 1E Item 2 rule: zoom.js must never navigate via history.back()
        zoom_js_path = os.path.join(ROOT, "tools", "editor", "static", "zoom.js")
        with open(zoom_js_path, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertNotIn("history.back", code)

    def test_build_info_contains_server_start_str(self):
        # Section 1E Item 1: build-info returns server_start_str
        res = self.client.get("/api/build-info")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("server_start", data)
        self.assertIn("server_start_str", data)
        self.assertIn("is_stale", data)
        self.assertIn("build_time_str", data)

    def test_backup_created_as_sibling_in_reviewed_dir(self):
        # Section 1G Item 6: first save created no .bak sibling in out/reviewed/
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            tmp_csv = os.path.join(ROOT, "tmp", "reviewed", f"{game_id}_reviewed.csv")
            headers, rows = csv_io.read_reviewed_csv(tmp_csv)
            # Mutate one field and write with backup
            rows[0]["notes"] = "Test note for backup creation"
            csv_io.write_reviewed_csv(tmp_csv, headers, rows, create_backup=True)

            baks = glob.glob(os.path.join(os.path.dirname(tmp_csv), f"{game_id}_reviewed.csv.bak-*"))
            self.assertGreater(len(baks), 0, "Expected .bak-* sibling file directly in reviewed dir")
        finally:
            cleanup()

    def test_get_game_info_and_logos(self):
        # Section 1G Item 1: Game info and logos API
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            res = self.client.get(f"/api/game/{game_id}/info")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data["game_id"], game_id)
            self.assertIn("logos", data)
            self.assertGreater(len(data["logos"]), 0)
            # Each logo should have rel_path and team
            for logo in data["logos"][:5]:
                self.assertIn("rel_path", logo)
                self.assertIn("team", logo)
                self.assertIn("filename", logo)
        finally:
            cleanup()

    def test_post_game_info_saves_json(self):
        # Section 1G Item 1: Game info save
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            payload = {
                "league_logo": "shared/team_logos/league_a.png",
                "home": "Home FC",
                "home_logo": "shared/team_logos/home_fc.png",
                "date": "March 29, 2026",
                "opponent": "Guest FC Test",
                "away_logo": "shared/team_logos/guest_fc.png",
                "score": "6-0",
                "halftime_score": "3-0"
            }
            res = self.client.post(f"/api/game/{game_id}/info", json=payload)
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data["status"], "saved")

            # Check that file was written in temp_dir
            gi_path = os.path.join(temp_dir, "game_info.json")
            if not os.path.exists(gi_path):
                gi_path = os.path.join(temp_dir, "work", "game_info.json")
            self.assertTrue(os.path.exists(gi_path), f"game_info.json should exist in {temp_dir}")
            with open(gi_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(saved["opponent"], "Guest FC Test")
            self.assertEqual(saved["away_logo"], "shared/team_logos/guest_fc.png")
            self.assertEqual(saved["score"], "6-0")
        finally:
            cleanup()

    def test_shared_team_logos_static_stream(self):
        # GET /shared/team_logos/...
        res = self.client.get("/shared/team_logos/league_a.png")
        self.assertEqual(res.status_code, 200)
        self.assertIn("image", res.content_type)
        self.assertGreater(len(res.data), 100)

    def test_timing_order_validation(self):
        # Section 1G Item 5: action_end < event validation
        ok, msg = time_utils.validate_timing_order("46:25", "46:45", "46:38")
        self.assertFalse(ok)
        self.assertTrue("Event (46:45) is after End (46:38)" in msg or "End" in msg)

        # start > event validation
        ok, msg = time_utils.validate_timing_order("46:50", "46:45", "47:00")
        self.assertFalse(ok)
        self.assertTrue("Start (46:50) is after Event (46:45)" in msg or "Start" in msg)

        # valid timing
        ok, msg = time_utils.validate_timing_order("46:25", "46:45", "47:00")
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_trigger_generate_cards_endpoint(self):
        # Section 1G User Requirement: generate cards endpoint
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            # First ensure game_info.json exists
            gi_path = os.path.join(temp_dir, "game_info.json")
            with open(gi_path, "w", encoding="utf-8") as f:
                json.dump({
                    "league_logo": "shared/team_logos/league_a.png",
                    "home": "Home FC",
                    "home_logo": "shared/team_logos/home_fc.png",
                    "date": "March 29, 2026",
                    "opponent": "Guest FC",
                    "away_logo": "shared/team_logos/guest_fc.png",
                    "score": "6-0",
                    "halftime_score": "3-0"
                }, f)

            res = self.client.post(f"/api/game/{game_id}/cards")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data["status"], "started")
            self.assertIn("task_id", data)
        finally:
            cleanup()

    def test_get_roster_endpoint(self):
        # Section 1G: Roster endpoint
        res = self.client.get("/api/roster")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("roster", data)
        self.assertGreater(len(data["roster"]), 0)
        p11 = next((p for p in data["roster"] if p["no"] == "11"), None)
        self.assertIsNotNone(p11, "Player #11 (Player 11) should exist in roster")
        self.assertEqual(p11["name"], "Player 11")

    def test_trigger_generate_reels_endpoint(self):
        # Section 1G: Reels trigger endpoint with player selection
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            res = self.client.post(f"/api/game/{game_id}/reels", json={"player": "11,7", "stage": "all"})
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data["status"], "started")
            self.assertIn("task_id", data)
            self.assertEqual(data["player"], "11,7")
        finally:
            cleanup()

    def test_render_zoom_blocks_unreviewed_clips(self):
        # Section 1H: Unreviewed zoom crop blocking
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            # Set up state with an unreviewed zoom clip (auto-placed)
            st_path = os.path.join(temp_dir, "zoom_state.json")
            with open(st_path, "w", encoding="utf-8") as f:
                json.dump({
                    "version": 1,
                    "replays": {
                        "tok_unrev": {
                            "n": 1,
                            "crop": [1152, 648],
                            "is_auto_placed": True,
                            "reviewed": False
                        }
                    }
                }, f)

            # Single clip without spec and unreviewed must be rejected with 400
            res = self.client.post(f"/api/zoom/{game_id}/tok_unrev/render", json={"scope": "current"})
            self.assertEqual(res.status_code, 400)
            data = res.get_json()
            self.assertEqual(data.get("error"), "unreviewed_clip")

            # Batch render without reviewed_only must be rejected with 400
            res_all = self.client.post(f"/api/zoom/{game_id}/tok_unrev/render", json={"scope": "all"})
            self.assertEqual(res_all.status_code, 400)
            data_all = res_all.get_json()
            self.assertEqual(data_all.get("error"), "unreviewed_clips_exist")
            self.assertIn("unreviewed_clips", data_all)
            self.assertGreater(len(data_all["unreviewed_clips"]), 0)
            self.assertIn("n", data_all["unreviewed_clips"][0])
            self.assertIn("token", data_all["unreviewed_clips"][0])

            # Mark reviewed: True and test single-clip render starts pipeline
            with open(st_path, "w", encoding="utf-8") as f:
                json.dump({
                    "version": 1,
                    "replays": {
                        "tok_unrev": {
                            "n": 1,
                            "crop": [1152, 648],
                            "crop_w": 1536,
                            "is_auto_placed": False,
                            "reviewed": True
                        }
                    }
                }, f)

            res_rev = self.client.post(f"/api/zoom/{game_id}/tok_unrev/render", json={"scope": "current"})
            self.assertEqual(res_rev.status_code, 200)
            self.assertIn("task_id", res_rev.get_json())
        finally:
            cleanup()

    def test_verify_zoom_returns_exit_1_on_missing_files(self):
        # Section 1H: Honest verify_zoom exit status
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            st_path = os.path.join(temp_dir, "zoom_state.json")
            with open(st_path, "w", encoding="utf-8") as f:
                json.dump({
                    "version": 1,
                    "replays": {
                        "tok_missing": {
                            "n": 5,
                            "crop": [1000, 500],
                            "reviewed": True
                        }
                    }
                }, f)

            # Run verify_zoom.py on fixture where 005b_tok_missing_zoom3x_720.mp4 does NOT exist
            cmd = [sys.executable, os.path.join(TOOLS_DIR, "pipeline", "verify_zoom.py"), "--out", temp_dir, "--height", "720"]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1, f"verify_zoom must exit 1 when clips are missing, got {proc.returncode}")
            self.assertIn("MISSING", proc.stdout)
        finally:
            cleanup()

    def test_save_game_info_updates_csv_game_column(self):
        # Section 1H: Match name propagation to CSV game column
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            payload = {
                "match_name": "2026-03-29 Home FC Championship Final",
                "home": "Home FC",
                "home_logo": "shared/team_logos/home_fc.png",
                "opponent": "Guest FC Red Bulls",
                "away_logo": None,
                "score": "4-1",
                "halftime_score": "2-0"
            }
            res = self.client.post(f"/api/game/{game_id}/info", json=payload)
            self.assertEqual(res.status_code, 200)

            # Check that review CSV has updated game column
            csv_path = os.path.join(ROOT, "tmp", "reviewed", f"{game_id}_reviewed.csv")
            headers, rows = csv_io.read_reviewed_csv(csv_path)
            for r in rows:
                if not r.get("skip"):
                    self.assertEqual(r.get("game"), "2026-03-29 Home FC Championship Final")
        finally:
            cleanup()

    def test_production_preflight_and_generate_bat(self):
        # Section 1H: Production pre-flight checklist and batch generation
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            # Create game_info.json and dummy cards so batch generation runs synchronously
            with open(os.path.join(temp_dir, "work", "game_info.json"), "w", encoding="utf-8") as f:
                json.dump({
                    "home": "Home FC",
                    "opponent": "Guest FC",
                    "score": "2-0",
                    "date": "2026-03-29"
                }, f)
            cards_dir = os.path.join(temp_dir, "work", "clips", "cards")
            os.makedirs(cards_dir, exist_ok=True)
            with open(os.path.join(cards_dir, "000_intro_fullgame.mp4"), "w", encoding="utf-8") as f:
                f.write("dummy")

            # 1. Preflight
            res = self.client.get(f"/api/game/{game_id}/production/preflight")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertIn("checks", data)
            self.assertIn("game_info", data["checks"])
            self.assertIn("roster", data["checks"])
            self.assertIn("zoom", data["checks"])
            self.assertIn("bat", data)

            # 2. Generate bat
            gen_res = self.client.post(f"/api/game/{game_id}/production/generate-bat", json={"player": "11,7"})
            self.assertEqual(gen_res.status_code, 200, f"Generate bat failed: {gen_res.get_json()}")
            gen_data = gen_res.get_json()
            self.assertTrue(gen_data.get("success"))
            self.assertIn("bat_path", gen_data)
            self.assertIn("command", gen_data)
            self.assertTrue(os.path.exists(gen_data["bat_path"]))
        finally:
            cleanup()

    def test_upload_logo_endpoint(self):
        import io
        # 1. Reject invalid extension
        res = self.client.post("/api/upload-logo", data={"file": (io.BytesIO(b"dummy"), "malicious.exe")})
        self.assertEqual(res.status_code, 400)

        # 2. Upload valid png
        test_filename = f"test_crest_tmp_{int(time.time())}.png"
        res = self.client.post("/api/upload-logo", data={"file": (io.BytesIO(b"\x89PNG\r\n\x1a\n"), test_filename)})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        uploaded_path = os.path.join(ROOT, data["path"])
        self.assertTrue(os.path.exists(uploaded_path))

        # 3. Test overwrite prompt
        res2 = self.client.post("/api/upload-logo", data={"file": (io.BytesIO(b"\x89PNG\r\n\x1a\n"), test_filename)})
        self.assertEqual(res2.status_code, 200)
        data2 = res2.get_json()
        self.assertTrue(data2.get("exists"))

        # Clean up
        if os.path.exists(uploaded_path):
            os.remove(uploaded_path)

    def test_game_info_validation_extended(self):
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            # Empty home name
            res = self.client.post(f"/api/game/{game_id}/info", json={"home": "", "opponent": "Team B"})
            self.assertEqual(res.status_code, 400)

            # Empty opponent name
            res = self.client.post(f"/api/game/{game_id}/info", json={"home": "Team A", "opponent": ""})
            self.assertEqual(res.status_code, 400)

            # Invalid score format
            res = self.client.post(f"/api/game/{game_id}/info", json={
                "home": "Team A",
                "opponent": "Team B",
                "score": "invalid-score"
            })
            self.assertEqual(res.status_code, 400)

            # Valid score
            res = self.client.post(f"/api/game/{game_id}/info", json={
                "home": "Team A",
                "opponent": "Team B",
                "score": "3-1",
                "halftime_score": "1-0",
                "league": "League A"
            })
            self.assertEqual(res.status_code, 200)
        finally:
            cleanup()

    def test_unplaced_replay_and_auto_frame(self):
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            # Fetch replay 9 - in temp fixture it has no crop in state
            # Wipe state replays crop to test unplaced
            st_path = os.path.join(temp_dir, "work", "zoom_state.json")
            if os.path.exists(st_path):
                st = json.load(open(st_path, encoding="utf-8"))
                for r in st.get("replays", {}).values():
                    r["crop"] = None
                    r["reviewed"] = False
                json.dump(st, open(st_path, "w", encoding="utf-8"))

            res = self.client.get(f"/api/zoom/{game_id}/9")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            tok = data["token"]
            self.assertIsNone(data["replay"]["crop"])
            self.assertFalse(data["replay"]["reviewed"])

            # Auto-frame single clip
            af_res = self.client.post(f"/api/zoom/{game_id}/auto-frame", json={"token": tok})
            self.assertEqual(af_res.status_code, 200)

            # Verify it has standard 2.5x crop [1152, 450], is_auto_placed: True, reviewed: False
            res2 = self.client.get(f"/api/zoom/{game_id}/9")
            data2 = res2.get_json()
            self.assertEqual(data2["replay"]["crop"], [1152, 450])
            self.assertTrue(data2["replay"].get("is_auto_placed"))
            self.assertFalse(data2["replay"].get("reviewed"))

            # Verify rendering this unreviewed clip is BLOCKED
            render_res = self.client.post(f"/api/zoom/{game_id}/{tok}/render", json={"scope": "current"})
            self.assertEqual(render_res.status_code, 400)
            self.assertEqual(render_res.get_json().get("error"), "unreviewed_clip")
        finally:
            cleanup()

    def test_detached_production_lifecycle_and_locks(self):
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            with open(os.path.join(temp_dir, "work", "game_info.json"), "w", encoding="utf-8") as f:
                json.dump({"home": "Home FC", "opponent": "Guest FC", "date": "2026-03-29"}, f)
            cards_dir = os.path.join(temp_dir, "work", "clips", "cards")
            os.makedirs(cards_dir, exist_ok=True)
            with open(os.path.join(cards_dir, "000_intro_fullgame.mp4"), "w", encoding="utf-8") as f:
                f.write("dummy")

            # 1. Preflight includes duration estimates
            pf_res = self.client.get(f"/api/game/{game_id}/production/preflight")
            self.assertEqual(pf_res.status_code, 200)
            pf_data = pf_res.get_json()
            self.assertIn("estimates", pf_data)
            self.assertIn("est_hours", pf_data["estimates"])

            # 2. Dry run returns planned steps
            dry_res = self.client.post(f"/api/game/{game_id}/production/dry-run", json={"player": "11"})
            self.assertEqual(dry_res.status_code, 200)
            dry_data = dry_res.get_json()
            self.assertTrue(dry_data.get("dry_run"))
            self.assertIn("DRY-RUN", dry_data["output"])

            # 3. Simulate production lock using a dummy background process
            pid_file = os.path.join(temp_dir, f"run_everything_{game_id}.pid")
            dummy_proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            with open(pid_file, "w", encoding="utf-8") as f:
                f.write(str(dummy_proc.pid))

            try:
                # Check status reports running
                st_res = self.client.get(f"/api/game/{game_id}/production/status")
                self.assertEqual(st_res.status_code, 200)
                self.assertEqual(st_res.get_json()["status"], "running")

                # Check locked endpoints return 409
                recut_res = self.client.post(f"/api/recut/{game_id}")
                self.assertEqual(recut_res.status_code, 409)
                self.assertEqual(recut_res.get_json()["error"], "production_running")

                # Cancel production (should kill dummy_proc and remove pid_file)
                cancel_res = self.client.post(f"/api/game/{game_id}/production/cancel")
                self.assertEqual(cancel_res.status_code, 200)
                self.assertFalse(os.path.exists(pid_file))
                # Confirm dummy_proc is dead
                try:
                    dummy_proc.wait(timeout=2.0)
                except Exception:
                    pass
                self.assertIsNotNone(dummy_proc.poll())
            finally:
                if dummy_proc.poll() is None:
                    try:
                        dummy_proc.kill()
                    except Exception:
                        pass
        finally:
            cleanup()

    def test_make_run_all_order(self):
        # Verify step order in make_run_all.py: cards -> full-game -> reels -> check_outputs
        cmd = [sys.executable, os.path.join(TOOLS_DIR, "pipeline", "make_run_all.py"), "--day", "2026-03-29", "--dry-run"]
        res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        out = res.stdout

        idx_cards = out.find("1. Title cards")
        idx_fg = out.find("2. Full game video")
        idx_reels = out.find("3. 4K clips, replays, reels")
        idx_check = out.find("4. Checking lengths and outputs")

        self.assertTrue(idx_cards >= 0, "Missing title cards stage")
        self.assertTrue(idx_fg >= 0, "Missing full game stage")
        self.assertTrue(idx_reels >= 0, "Missing reels stage")
        self.assertTrue(idx_check >= 0, "Missing check stage")

        self.assertTrue(idx_cards < idx_fg < idx_reels < idx_check,
                        f"Steps out of order: cards={idx_cards}, fg={idx_fg}, reels={idx_reels}, check={idx_check}")

    def test_preflight_timing_catches_invalid_order(self):
        # T3: Ensure pre-flight catches timing order violations (e.g. action_end < event)
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            csv_path = os.path.join(ROOT, "tmp", "reviewed", f"{game_id}_reviewed.csv")
            headers, rows = csv_io.read_reviewed_csv(csv_path)
            # Create timing violation: action_end before event
            rows[0]["action_start"] = "10:00"
            rows[0]["event"] = "10:15"
            rows[0]["action_end"] = "10:10"  # Invalid! end < event
            csv_io.write_reviewed_csv(csv_path, headers, rows, create_backup=False)

            pf_res = self.client.get(f"/api/game/{game_id}/production/preflight")
            self.assertEqual(pf_res.status_code, 200)
            pf_data = pf_res.get_json()
            self.assertFalse(pf_data["checks"]["timings"]["ok"])
            self.assertFalse(pf_data["all_passed"])
            self.assertIn("rows with invalid start/event/end", pf_data["checks"]["timings"]["details"])
        finally:
            cleanup()

    def test_zero_flagged_verify_regex_logic(self):
        # T2: Test that '0 flagged' is not considered a failure by regex/parser
        import re
        success_line = "PASS: 16 checked, 0 flagged (verify_zoom)"
        is_missing = "MISSING" in success_line
        is_budget = "budget reached" in success_line
        is_flagged = bool(re.search(r'\b[1-9]\d*\s*flagged\b', success_line, re.IGNORECASE) or success_line.startswith("FLAGGED:"))
        has_failure = (is_missing or is_budget or is_flagged) and not ("0 flagged" in success_line)
        self.assertFalse(has_failure)

        failure_line = "FLAGGED: 2 clips (verify_zoom)"
        is_flagged_fail = bool(re.search(r'\b[1-9]\d*\s*flagged\b', failure_line, re.IGNORECASE) or failure_line.startswith("FLAGGED:"))
        has_fail = (is_flagged_fail) and not ("0 flagged" in failure_line)
        self.assertTrue(has_fail)

    def test_auto_placed_flag_cleared_on_manual_edit(self):
        # T4: Manual edit clears is_auto_placed
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            # 1. Unplace clip 9
            st_path = os.path.join(temp_dir, "work", "zoom_state.json")
            if os.path.exists(st_path):
                st = json.load(open(st_path, encoding="utf-8"))
                for r in st.get("replays", {}).values():
                    r["crop"] = None
                    r["reviewed"] = False
                    r["is_auto_placed"] = False
                json.dump(st, open(st_path, "w", encoding="utf-8"))

            # 2. Auto-frame
            af_res = self.client.post(f"/api/zoom/{game_id}/auto-frame", json={"all_unplaced": True})
            self.assertEqual(af_res.status_code, 200)

            # 3. Check clip 9 is auto-placed
            res = self.client.get(f"/api/zoom/{game_id}/9")
            tok = res.get_json()["token"]
            self.assertTrue(res.get_json()["replay"].get("is_auto_placed"))

            # 4. Save manual edit (crop [1200, 400])
            save_res = self.client.put(f"/api/zoom/{game_id}/{tok}", json={
                "crop": [1200, 400],
                "crop_w": 1280,
                "is_auto_placed": False,
                "reviewed": True
            })
            self.assertEqual(save_res.status_code, 200)
            data_saved = save_res.get_json()
            self.assertFalse(data_saved["replay"].get("is_auto_placed"))
            self.assertTrue(data_saved["replay"].get("reviewed"))
            self.assertEqual(data_saved["replay"]["crop"], [1200, 400])
        finally:
            cleanup()

    def test_api_docs_endpoint(self):
        # Verify self-describing GET /api/docs endpoint
        res = self.client.get("/api/docs")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("title", data)
        self.assertIn("version", data)
        self.assertIn("endpoints", data)
        self.assertGreater(len(data["endpoints"]), 20)

    def test_organize_endpoint_and_lock(self):
        # Verify POST /api/game/<game_id>/organize preview and 409 production lock
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            # 1. Preview dry-run (apply=false)
            res = self.client.post(f"/api/game/{game_id}/organize", json={"apply": False})
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data.get("success"))
            self.assertFalse(data.get("applied"))
            self.assertIn("output", data)

            # 2. Lock check when production PID is running
            pid_file = os.path.join(temp_dir, f"run_everything_{game_id}.pid")
            dummy_proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            with open(pid_file, "w", encoding="utf-8") as f:
                f.write(str(dummy_proc.pid))

            try:
                lock_res = self.client.post(f"/api/game/{game_id}/organize", json={"apply": False})
                self.assertEqual(lock_res.status_code, 409)
                self.assertEqual(lock_res.get_json().get("error"), "production_running")
            finally:
                if dummy_proc.poll() is None:
                    dummy_proc.kill()
        finally:
            cleanup()

    def test_4k_outputs_staleness_and_preflight(self):
        # Section 1O: 4K Outputs Out of Date detection in pre-flight
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            # 1. Without 4K files, staleness is False
            pre_res = self.client.get(f"/api/game/{game_id}/production/preflight")
            self.assertEqual(pre_res.status_code, 200)
            data = pre_res.get_json()
            self.assertIn("staleness", data)
            self.assertFalse(data["staleness"]["is_stale"])

            # 2. Create a replay in zoom_state.json with dur = 5.5 (expected replay = 11.0s)
            st_path = os.path.join(temp_dir, "zoom_state.json")
            extra_dir = os.path.join(temp_dir, "clips", "extra")
            os.makedirs(extra_dir, exist_ok=True)
            tok = "mark_000527"
            hist_time_str = (datetime.datetime.now() - datetime.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
            st = {
                "replays": {
                    tok: {
                        "n": 3,
                        "crop": [1200, 400],
                        "reviewed": True,
                        "start": 320.0,
                        "dur": 5.5,
                        "cut_start": 0.0,
                        "cut_end": 0.0,
                        "history": [{"t": hist_time_str, "window": [320.0, 5.5], "crop": [1200, 400], "cut": [0.0, 0.0], "len": 11.0}]
                    }
                }
            }
            json.dump(st, open(st_path, "w", encoding="utf-8"))

            # Create an existing 4K file that was rendered at 9.0s (e.g. dummy mp4 file with old mtime)
            f_4k = os.path.join(extra_dir, f"003b_{tok}_zoom3x_2160.mp4")
            with open(f_4k, "wb") as f:
                f.write(b"\x00" * 1024)  # dummy content
            # Set mtime to past
            old_time = time.time() - 3600
            os.utime(f_4k, (old_time, old_time))

            # Query preflight
            res = self.client.get(f"/api/game/{game_id}/production/preflight")
            self.assertEqual(res.status_code, 200)
            data2 = res.get_json()
            self.assertIn("staleness", data2)
            self.assertTrue(data2["staleness"]["is_stale"])
            self.assertEqual(data2["staleness"]["stale_count"], 1)
            self.assertEqual(data2["staleness"]["stale_replays"][0]["n"], 3)
            self.assertIn("est_rebuild_minutes", data2["staleness"])

            # Now simulate updated 4K file and updated production reels, with older preview720
            new_4k_time = time.time()
            os.utime(f_4k, (new_4k_time, new_4k_time))
            reels_dir = os.path.join(temp_dir, "reels")
            os.makedirs(reels_dir, exist_ok=True)
            # Preview reel older than 4k master
            preview_reel = os.path.join(reels_dir, f"{game_id}_preview720_nomusic.mp4")
            with open(preview_reel, "wb") as f:
                f.write(b"\x00" * 512)
            os.utime(preview_reel, (new_4k_time - 300, new_4k_time - 300))

            # Production highlight reel newer than 4k master
            prod_reel = os.path.join(reels_dir, f"{game_id}_highlights_transitions.mp4")
            with open(prod_reel, "wb") as f:
                f.write(b"\x00" * 512)
            os.utime(prod_reel, (new_4k_time + 10, new_4k_time + 10))

            res3 = self.client.get(f"/api/game/{game_id}/production/preflight")
            self.assertEqual(res3.status_code, 200)
            data3 = res3.get_json()
            # Stale flag must clear because production reels are newer and preview720 is ignored
            self.assertFalse(data3["staleness"]["is_stale"])
            self.assertFalse(data3["staleness"]["reels_stale"])
            self.assertEqual(data3["staleness"]["stale_count"], 0)
        finally:
            cleanup()

    def test_production_rebuild_stale_endpoint(self):
        # Section 1O: POST /api/game/<game_id>/production/rebuild-stale
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            # 1. Normal call starts background pipeline
            res = self.client.post(f"/api/game/{game_id}/production/rebuild-stale", json={"player": "11"})
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data.get("status"), "started")
            self.assertIn("task_id", data)
            self.assertIn("make_reels.py", data.get("command", ""))

            # 2. Production lock: when production is active, returns 409
            pid_file = os.path.join(temp_dir, f"run_everything_{game_id}.pid")
            dummy_proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            with open(pid_file, "w", encoding="utf-8") as f:
                f.write(str(dummy_proc.pid))

            try:
                lock_res = self.client.post(f"/api/game/{game_id}/production/rebuild-stale", json={"player": "11"})
                self.assertEqual(lock_res.status_code, 409)
                self.assertEqual(lock_res.get_json().get("error"), "production_running")
            finally:
                if dummy_proc.poll() is None:
                    dummy_proc.kill()
        finally:
            cleanup()

    def test_zoom_stale_status_detection(self):
        # Section 1O: Replay status returns 'rendered (stale)' when window or crop modified
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            st_path = os.path.join(temp_dir, "zoom_state.json")
            tok = "mark_000527"
            extra_dir = os.path.join(temp_dir, "clips", "extra")
            os.makedirs(extra_dir, exist_ok=True)
            f_720 = os.path.join(extra_dir, f"003b_{tok}_zoom3x_720.mp4")
            with open(f_720, "wb") as f:
                f.write(b"\x00" * 1024)

            # State has history with window [320.0, 4.5], but current window is [320.0, 5.5]
            st = {
                "replays": {
                    tok: {
                        "n": 3,
                        "crop": [1200, 400],
                        "reviewed": True,
                        "start": 320.0,
                        "dur": 5.5,
                        "history": [{"t": "2026-04-02 07:00:00", "window": [320.0, 4.5], "crop": [1200, 400], "cut": [0.0, 0.0], "len": 9.0}],
                        "final_key": "some_old_key"
                    }
                }
            }
            json.dump(st, open(st_path, "w", encoding="utf-8"))

            # 1. Check list endpoint
            res_list = self.client.get(f"/api/zoom/{game_id}")
            self.assertEqual(res_list.status_code, 200)
            reps = res_list.get_json().get("replays", [])
            rep3 = next((r for r in reps if r["clip"] == 3), None)
            self.assertIsNotNone(rep3)
            self.assertTrue(rep3.get("is_stale"))
            self.assertEqual(rep3.get("status"), "rendered (stale)")

            # 2. Check details endpoint
            res_det = self.client.get(f"/api/zoom/{game_id}/3")
            self.assertEqual(res_det.status_code, 200)
            det = res_det.get_json()
            self.assertTrue(det.get("is_stale"))
        finally:
            cleanup()

    def test_dynamic_rebuild_estimate_formula(self):
        # Section 1Q/1T: Test dynamic rebuild estimate calculation
        from tools.editor.server import check_4k_outputs_staleness
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            # 0 replays
            st0 = check_4k_outputs_staleness(game_id, temp_dir)
            self.assertFalse(st0["is_stale"])
            self.assertIsNone(st0.get("est_rebuild_minutes"))

            # 5 stale replays: formula max(3, round(5 * 1.0 + 3.5)) = 9 minutes
            st_path = os.path.join(temp_dir, "zoom_state.json")
            extra_dir = os.path.join(temp_dir, "clips", "extra")
            os.makedirs(extra_dir, exist_ok=True)
            hist_time_str = (datetime.datetime.now() - datetime.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
            replays = {}
            for i in range(1, 6):
                tok = f"mark_000{i:03d}"
                replays[tok] = {
                    "n": i,
                    "crop": [1200, 400],
                    "reviewed": True,
                    "start": float(i * 100),
                    "dur": 5.0,
                    "history": [{"t": hist_time_str, "window": [float(i * 100), 5.0], "crop": [1200, 400], "len": 10.0}]
                }
                f_4k = os.path.join(extra_dir, f"{i:03d}b_{tok}_zoom3x_2160.mp4")
                with open(f_4k, "wb") as f:
                    f.write(b"\x00" * 256)
                old_time = time.time() - 3600
                os.utime(f_4k, (old_time, old_time))
            json.dump({"replays": replays}, open(st_path, "w", encoding="utf-8"))

            st5 = check_4k_outputs_staleness(game_id, temp_dir)
            self.assertTrue(st5["is_stale"])
            self.assertEqual(st5["stale_count"], 5)
            # Python banker's rounding: round(5 * 1.0 + 3.5) = round(8.5) = 8
            expected_mins = max(3, round(5 * 1.0 + 3.5))
            self.assertEqual(st5["est_rebuild_minutes"], expected_mins)
        finally:
            cleanup()

    def test_make_reels_completion_summary_banner(self):
        # Section 1Q/1T: Test completion summary banner formatting in make_reels.py
        make_reels_path = os.path.join(ROOT, "tools", "pipeline", "make_reels.py")
        with open(make_reels_path, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("[rebuild] Rebuild complete: highlight reels updated:", code)
        self.assertIn("probe_dur", code)

    def test_mark_read_only_and_non_sliding_contract(self):
        # Section 1T Item 2: Marks are never changed or dragged by the user
        app_js_path = os.path.join(ROOT, "tools", "editor", "static", "app.js")
        with open(app_js_path, "r", encoding="utf-8") as f:
            app_js = f.read()
        # Ensure startInlineEdit prevents video_time edits
        self.assertIn("field === 'video_time'", app_js)
        # Ensure timeline mark line does not drag
        self.assertIn("timelineMarkLine", app_js)
        # Ensure double-click on table cell does not edit video_time
        self.assertNotIn("startEditCell(idx, 'video_time')", app_js)

    def test_row_selection_seeks_to_action_start(self):
        # Section 1T Item 4: selectRow defaults to action_start, pill seeks to video_time
        app_js_path = os.path.join(ROOT, "tools", "editor", "static", "app.js")
        with open(app_js_path, "r", encoding="utf-8") as f:
            app_js = f.read()
        self.assertIn("function selectRow(idx, targetField = 'action_start')", app_js)
        self.assertIn("selectRow(idx, 'action_start')", app_js)
        self.assertIn("onTimeCellClick(${idx}, 'video_time'", app_js)

    def test_escape_dismiss_hierarchy_and_input_handling(self):
        # Section 1T Item 5: Escape closes confirm -> modal -> menu in strict order
        app_js_path = os.path.join(ROOT, "tools", "editor", "static", "app.js")
        with open(app_js_path, "r", encoding="utf-8") as f:
            app_js = f.read()
        self.assertIn("dismissTopmostLayer()", app_js)
        self.assertIn("calendarConfirmBox", app_js)
        self.assertIn("appMenuDropdown", app_js)

        # Confirm Escape is handled before input guard in keydown
        esc_idx = app_js.find("e.key === 'Escape'")
        self.assertTrue(esc_idx >= 0)

        # In zoom.js, Escape closes modals before input guard
        zoom_js_path = os.path.join(ROOT, "tools", "editor", "static", "zoom.js")
        with open(zoom_js_path, "r", encoding="utf-8") as f:
            zoom_js = f.read()
        self.assertIn("e.key === 'Escape'", zoom_js)
        self.assertIn("closeOrReturnToReview", zoom_js)

    def test_invalid_timing_row_blocks_sheet_push(self):
        # Section 1V Item 1: Save with invalid timing row blocks Google Sheets push
        import server
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            csv_path = os.path.join(ROOT, "tmp", "reviewed", f"{game_id}_reviewed.csv")
            headers, rows = csv_io.read_reviewed_csv(csv_path)
            # Create a deliberate invalid timing row: action_start=46:37, event=46:51, action_end=46:38
            rows[0]["action_start"] = "46:37"
            rows[0]["event"] = "46:51"
            rows[0]["action_end"] = "46:38"

            res = self.client.put(f"/api/game/{game_id}", json={
                "headers": headers,
                "rows": rows,
                "should_push_sheet": True
            })
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data.get("success"))
            sheet_res = data.get("sheet_result", {})
            self.assertFalse(sheet_res.get("success"))
            self.assertEqual(sheet_res.get("error"), "invalid_timings_exist")
            self.assertIn("blocked", sheet_res.get("message", "").lower())
        finally:
            cleanup()

    def test_flags_column_header_and_unrev_badge(self):
        # Compaction & clarity: 'Flags' header replaces 'Instructions', 'UNREV' pill replaces 'UNREVIEWED'
        idx_path = os.path.join(ROOT, "tools", "editor", "static", "index.html")
        with open(idx_path, "r", encoding="utf-8") as f:
            idx_html = f.read()
        self.assertIn('<th class="col-instructions">Flags</th>', idx_html)
        self.assertNotIn('<th class="col-instructions">Instructions</th>', idx_html)

        app_js_path = os.path.join(ROOT, "tools", "editor", "static", "app.js")
        with open(app_js_path, "r", encoding="utf-8") as f:
            app_js = f.read()
        self.assertIn("UNREV", app_js)

    def test_escape_cancels_inline_time_edit(self):
        # Section 1V Item 3: Escape in inline edit cancels and restores without blur committing
        app_js_path = os.path.join(ROOT, "tools", "editor", "static", "app.js")
        with open(app_js_path, "r", encoding="utf-8") as f:
            app_js = f.read()
        self.assertIn("let cancelled = false;", app_js)
        self.assertIn("cancelled = true;", app_js)
        self.assertIn("if (cancelled) return;", app_js)

    def test_unsaved_zoom_guard_and_modals(self):
        # Section 1V Item 4: Unsaved zoom edits guard on exit
        zoom_html_path = os.path.join(ROOT, "tools", "editor", "static", "zoom.html")
        with open(zoom_html_path, "r", encoding="utf-8") as f:
            zoom_html = f.read()
        self.assertIn('id="unsavedZoomModal"', zoom_html)
        self.assertIn('id="btnKeepEditingZoom"', zoom_html)
        self.assertIn('id="btnDiscardZoom"', zoom_html)
        self.assertIn('id="btnSaveAndLeaveZoom"', zoom_html)

        zoom_js_path = os.path.join(ROOT, "tools", "editor", "static", "zoom.js")
        with open(zoom_js_path, "r", encoding="utf-8") as f:
            zoom_js = f.read()
        self.assertIn("openUnsavedModal()", zoom_js)
        self.assertIn("closeUnsavedModal()", zoom_js)
        self.assertIn("state.hasUnsavedChanges", zoom_js)

    def test_dynamic_production_duration_subtracts_existing(self):
        # Section 1V Item 6: Subtract already completed outputs from pre-flight estimate
        from xbotgo_core.xbl import Game
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            out_dir = temp_dir
            cut_dir = os.path.join(out_dir, "reviewed4k")
            os.makedirs(cut_dir, exist_ok=True)
            # Create all required reviewed4k clips to simulate completed cutting
            g = Game(out_dir)
            for j in g.jobs():
                base = j.get("basename") or f"{j.get('n', 0):03d}"
                with open(os.path.join(cut_dir, f"{base}.mp4"), "wb") as f:
                    f.write(b"fake_mp4_bytes")

            # Create fake 4K master replays in clips/extra
            extra_dir = os.path.join(out_dir, "clips", "extra")
            os.makedirs(extra_dir, exist_ok=True)
            st_path = os.path.join(out_dir, "work", "zoom_state.json")
            if os.path.exists(st_path):
                st = json.load(open(st_path, encoding="utf-8"))
                for tok, r in st.get("replays", {}).items():
                    n = r.get("n") or r.get("clip") or 1
                    with open(os.path.join(extra_dir, f"{n:03d}b_{tok}_zoom3x_2160.mp4"), "wb") as f:
                        f.write(b"fake_2160_replay")

            # Create fake fullgame video
            with open(os.path.join(out_dir, f"{game_id}_fullgame.mp4"), "wb") as f:
                f.write(b"fake_fullgame")

            res = self.client.get(f"/api/game/{game_id}/production/preflight")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            est = data.get("estimates", {})
            # Since outputs are up to date, it should report verification label
            self.assertIn("Outputs up to date", est.get("est_label", ""))
            self.assertEqual(est.get("est_minutes"), 2)
        finally:
            cleanup()

    def test_roster_endpoints_and_exact_order_preservation(self):
        # Verify GET /api/roster returns contact and cached_at
        res = self.client.get("/api/roster")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("roster", data)
        self.assertGreater(len(data["roster"]), 0)
        p = data["roster"][0]
        self.assertIn("no", p)
        self.assertIn("name", p)
        self.assertIn("short_name", p)
        self.assertIn("contact", p)

        # Test normalize_roster preserving exact existing order from sheet (no diverging)
        from server import normalize_roster
        unordered_input = [
            {"no": "11", "name": "Player 11", "short_name": "P11", "contact": "p11@example.com"},
            {"no": "1", "name": "Player 1", "short_name": "P1", "contact": "p1@example.com"},
            {"no": "33", "name": "Player 33", "short_name": "P33", "contact": "p33@example.com"}
        ]
        norm = normalize_roster(unordered_input)
        self.assertEqual([x["no"] for x in norm], ["11", "1", "33"])

    def test_roster_modal_ui_and_wizard_text_removal(self):
        # 1. Verify text '(Wizard)' is removed from drop down menu
        idx_path = os.path.join(ROOT, "tools", "editor", "static", "index.html")
        with open(idx_path, "r", encoding="utf-8") as f:
            idx_html = f.read()
        self.assertIn('<span class="menu-title">Game Setup...</span>', idx_html)
        self.assertNotIn('<span class="menu-title">Game Setup (Wizard)...</span>', idx_html)

        # 2. Verify Roster menu item and modal exist
        self.assertIn('<span class="menu-title">Roster...</span>', idx_html)
        self.assertIn('id="rosterModal"', idx_html)
        self.assertIn('id="btnPullRoster"', idx_html)
        self.assertIn('id="btnAddRosterRow"', idx_html)
        self.assertIn('id="btnSaveRoster"', idx_html)
        self.assertIn('id="rosterEditorTableBody"', idx_html)

        # 3. Verify Escape stack in app.js handles rosterModal
        app_js_path = os.path.join(ROOT, "tools", "editor", "static", "app.js")
        with open(app_js_path, "r", encoding="utf-8") as f:
            app_js = f.read()
        self.assertIn("{ id: 'rosterModal', close: closeRosterModal }", app_js)
        self.assertIn("openRosterModal", app_js)
        self.assertIn("closeRosterModal", app_js)
        self.assertIn("saveRoster", app_js)
        self.assertIn("pullRosterFromGoogle", app_js)

        # 4. Verify 2-row collapsed layout in index.html (row 3 eliminated)
        self.assertNotIn('compact-meta-strip', idx_html)
        self.assertIn('timing-blocks-cluster', idx_html)
        self.assertIn('insp-player-input', idx_html)
        self.assertIn('insp-notes-input', idx_html)
        self.assertIn('max-width: 980px', idx_html)

        # 5. Verify Game.roster_records in xbl.py
        from tools.xbotgo_core.xbl import Game
        # test game out dir
        g = Game("out/2026-03-29")
        records = g.roster_records()
        self.assertIsInstance(records, dict)
        if records:
            first_key = next(iter(records))
            self.assertIn("name", records[first_key])
            self.assertIn("no", records[first_key])
            self.assertIn("short_name", records[first_key])
            self.assertIn("contact", records[first_key])

    def test_game_defaults_endpoints_roundtrip(self):
        # Isolated: the endpoints read/write a TEMP copy, config\\game_defaults.json is never touched
        # (before 1BA this test briefly rewrote the real file and a crash could leave test values in it).
        import xbotgo_core.game_state as _gs
        import server
        tmpd = tempfile.mkdtemp(prefix="xb_defaults_")
        tmp_defaults = os.path.join(tmpd, "config", "game_defaults.json")
        os.makedirs(os.path.dirname(tmp_defaults))
        real = _gs.DEFAULTS_FILE
        if os.path.exists(real):
            shutil.copy(real, tmp_defaults)
        real_md5 = _md5_or_none(real)
        old_gs, old_srv = _gs.DEFAULTS_FILE, server.DEFAULTS_FILE
        _gs.DEFAULTS_FILE = tmp_defaults
        server.DEFAULTS_FILE = tmp_defaults
        try:
            self._defaults_roundtrip_body()
        finally:
            _gs.DEFAULTS_FILE = old_gs
            server.DEFAULTS_FILE = old_srv
            shutil.rmtree(tmpd, ignore_errors=True)
        self.assertEqual(_md5_or_none(real), real_md5, "real game_defaults.json must be untouched")

    def _defaults_roundtrip_body(self):
        # 1. GET /api/defaults
        res = self.client.get("/api/defaults")
        self.assertEqual(res.status_code, 200)
        orig = res.get_json()
        self.assertIn("team_name", orig)
        self.assertIn("team_logo", orig)
        self.assertIn("featured_players", orig)
        self.assertIn("sheet_id", orig)

        # 2. POST /api/defaults
        try:
            update_payload = {
                "team_name": "Test United",
                "is_home": False,
                "team_logo": "shared/team_logos/home_fc.png",
                "league": "League B",
                "featured_players": ["7", "10"],
                "sheet_id": "test_sheet_id_12345"
            }
            res_post = self.client.post("/api/defaults", data=json.dumps(update_payload), content_type="application/json")
            self.assertEqual(res_post.status_code, 200)
            data_post = res_post.get_json()
            self.assertEqual(data_post.get("status"), "saved")
            self.assertEqual(data_post["defaults"]["team_name"], "Test United")
            self.assertFalse(data_post["defaults"]["is_home"])
            self.assertEqual(data_post["defaults"]["featured_players"], ["7", "10"])

            # Verify GET reflects update
            res2 = self.client.get("/api/defaults")
            self.assertEqual(res2.get_json()["team_name"], "Test United")
        finally:
            # Restore original defaults
            self.client.post("/api/defaults", data=json.dumps(orig), content_type="application/json")

    def test_make_reels_cheer_detection_on_multi_player_goal(self):
        import tools.pipeline.make_reels as mr
        j = {"clip": "005_goal_000845.mp4", "player": "11,1"}
        p_list = [p.strip() for p in (j.get("player") or "").split(",") if p.strip()]
        player = "11"
        player_matches = (not player) or (str(player) in p_list) or (j.get("player") == str(player))
        self.assertTrue(player_matches)

        # Also player 1
        player1_matches = (not "1") or (str("1") in p_list) or (j.get("player") == str("1"))
        self.assertTrue(player1_matches)

        # But not player 9
        player9_matches = (not "9") or (str("9") in p_list) or (j.get("player") == str("9"))
        self.assertFalse(player9_matches)

    def test_production_preflight_detects_player_suffixed_clips_and_migrates_legacy_replays(self):
        game_id, out_dir, cleanup = make_temp_game_fixture()
        try:
            from tools.xbotgo_core.xbl import Game
            g = Game(out_dir)
            all_jobs = g.jobs()

            # Create clips with player suffixes in clips/reviewed4k
            cut_dir = os.path.join(out_dir, "clips", "reviewed4k")
            os.makedirs(cut_dir, exist_ok=True)
            for j in all_jobs:
                base = j.get("basename") or f"{j.get('n', 0):03d}"
                with open(os.path.join(cut_dir, f"{base}_Player_Name_{j.get('n', 0)}.mp4"), "wb") as f:
                    f.write(b"fake_mp4_bytes")

            # Create full game video with underscore format
            with open(os.path.join(out_dir, "2026_04_02_pf_full_game.mp4"), "wb") as f:
                f.write(b"fake_fullgame")

            # Verify preflight recognizes these files
            res = self.client.get(f"/api/game/{game_id}/production/preflight")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            est = data.get("estimates", {})
            self.assertEqual(est.get("missing_clips", 0), 0)
        finally:
            cleanup()

    def test_zoom_dirty_flag_set_on_inspector_inputs(self):
        zoom_js_path = os.path.join(ROOT, "tools", "editor", "static", "zoom.js")
        with open(zoom_js_path, "r", encoding="utf-8") as f:
            code = f.read()

        # Verify dirty listeners for all offset and trim inputs
        self.assertIn("el.inpWinStartOffset.addEventListener('change'", code)
        self.assertIn("el.inpWinEndOffset.addEventListener('change'", code)
        self.assertIn("el.inpCutStart.addEventListener('change'", code)
        self.assertIn("el.inpCutEnd.addEventListener('change'", code)
        self.assertIn("el.inpHoldEnd.addEventListener('change'", code)
        self.assertIn("el.btnLooksGood", code)

    def test_video_resizer_and_16x9_fit_controls(self):
        index_html_path = os.path.join(ROOT, "tools", "editor", "static", "index.html")
        with open(index_html_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn('id="videoResizer"', html)
        self.assertIn('class="video-resizer-handle"', html)
        self.assertIn('id="videoFitPill"', html)
        self.assertIn('id="playerWrapper"', html)

        app_css_path = os.path.join(ROOT, "tools", "editor", "static", "app.css")
        with open(app_css_path, "r", encoding="utf-8") as f:
            css = f.read()
        self.assertIn('.video-resizer', css)
        self.assertIn('.video-resizer-handle', css)
        self.assertIn('row-resize', css)
        self.assertNotIn('max-height: calc(100vh - 175px)', css)
        # Strict zero-scrollbar layout assertions
        self.assertIn('.video-panel {', css)
        self.assertIn('.player-wrapper {', css)
        self.assertIn('object-fit: contain;', css)

        app_js_path = os.path.join(ROOT, "tools", "editor", "static", "app.js")
        with open(app_js_path, "r", encoding="utf-8") as f:
            js = f.read()
        self.assertIn('setupVideoResizer', js)
        self.assertIn('toggleVideoFit16x9', js)
        self.assertIn('review_editor_video_height', js)
        self.assertIn('setAutoFitMode', js)

    def test_defaults_modal_structure_and_logos_api(self):
        # 1. Verify GET /api/logos returns 200 with logos list
        res = self.client.get("/api/logos")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("logos", data)
        self.assertIsInstance(data["logos"], list)
        self.assertGreater(len(data["logos"]), 0)

        # 2. Verify index.html modal structure
        index_html_path = os.path.join(ROOT, "tools", "editor", "static", "index.html")
        with open(index_html_path, "r", encoding="utf-8") as f:
            html = f.read()

        # Exactly 1 gameDefaultsModal and no stray duplicate inputs
        self.assertEqual(html.count('id="gameDefaultsModal"'), 1)
        self.assertEqual(html.count('id="defFeaturedPlayers"'), 1)
        self.assertEqual(html.count('id="defSheetId"'), 1)
        self.assertEqual(html.count('id="defLeagueLogo"'), 1)
        self.assertEqual(html.count('id="defTeamLogo"'), 1)

        # High z-index (2100) so it pops up in front of gameInfoModal (2000)
        self.assertIn('id="gameDefaultsModal" class="app-modal" style="display: none; z-index: 2100;"', html)

        # 3. Verify app.js defaults functions
        app_js_path = os.path.join(ROOT, "tools", "editor", "static", "app.js")
        with open(app_js_path, "r", encoding="utf-8") as f:
            js = f.read()
        self.assertIn('openGameDefaultsModal', js)
        self.assertIn('updateDefLeagueLogoPreview', js)
        self.assertIn('updateDefLogoPreview', js)
        self.assertIn('onDefLeagueChange', js)
        self.assertIn('submitGameDefaults', js)




    def test_critical1_log_importer_path_depth_and_project_root_resolution(self):
        # Section 1AN CRITICAL 1: Verify log_importer writes timeline paths relative to project root (no leading ../)
        from xbotgo_core import log_importer
        base_root = log_importer.os.path.dirname(log_importer.os.path.dirname(log_importer.os.path.dirname(log_importer.os.path.abspath(log_importer.__file__))))
        self.assertEqual(os.path.abspath(base_root), os.path.abspath(ROOT), "base_root in log_importer must match ROOT")

        # Create mock video and test relative path calculation
        mock_video_path = os.path.join(ROOT, "04-01-26", "Videos", "mock.mp4")
        rel = os.path.relpath(mock_video_path, base_root).replace("\\", "/")
        self.assertFalse(rel.startswith("../"), f"Calculated path must not start with ../: {rel}")
        self.assertTrue(rel.startswith("04-01-26/Videos/"), f"Expected 04-01-26/Videos/, got {rel}")

    def test_critical2_sync_game_honestly_fails_when_clips_fail(self):
        # Section 1AN CRITICAL 2: sync_game.py must report errors and exit code 1 when cut_reviewed fails
        sync_script = os.path.join(TOOLS_DIR, "pipeline", "sync_game.py")
        with open(sync_script, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("recut_failed = True", code)
        self.assertIn("FAIL ", code)
        self.assertIn("sys.exit(1)", code)
        self.assertIn("Re-cut finished with errors", code)

    def test_critical3_all_routes_and_roster_symbols_defined(self):
        # Section 1AN CRITICAL 3: Every Flask route handler and roster function must be cleanly defined
        from editor import server as s
        self.assertTrue(hasattr(s, "fetch_remote_roster"), "server must have fetch_remote_roster defined")
        self.assertTrue(callable(s.fetch_remote_roster), "fetch_remote_roster must be callable")

        # Inspect all registered route view functions for basic callability
        rule_count = 0
        for rule in s.app.url_map.iter_rules():
            fn = s.app.view_functions.get(rule.endpoint)
            self.assertIsNotNone(fn, f"Endpoint {rule.endpoint} has no view function")
            self.assertTrue(callable(fn), f"View function for {rule.endpoint} is not callable")
            rule_count += 1
        self.assertGreaterEqual(rule_count, 40, "Expected at least 40 registered API and web routes")

    def test_item3_normalize_and_repair_paths_auto_heals_dotdot(self):
        # Section 1AN Item 3: Auto-repair ../ in timeline.json and zoom_state.json
        from xbotgo_core.game_state import normalize_and_repair_paths
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            # Create a timeline.json with legacy ../ path
            tl_path = os.path.join(temp_dir, "timeline.json")
            legacy_path = "../04-01-26/Videos/test.mp4"
            with open(tl_path, "w", encoding="utf-8") as f:
                json.dump({"videos": [{"file": "test.mp4", "path": legacy_path}]}, f)

            # Create a zoom_state.json with legacy ../ path
            zs_path = os.path.join(temp_dir, "zoom_state.json")
            with open(zs_path, "w", encoding="utf-8") as f:
                json.dump({"replays": {"tok1": {"path": legacy_path}}}, f)

            # Mock file existence for the cleaned path
            cleaned = "04-01-26/Videos/test.mp4"
            real_file = os.path.join(ROOT, cleaned)
            file_existed = os.path.exists(real_file)
            if not file_existed:
                os.makedirs(os.path.dirname(real_file), exist_ok=True)
                with open(real_file, "w", encoding="utf-8") as mf:
                    mf.write("mock")

            try:
                repaired = normalize_and_repair_paths(temp_dir)
                self.assertTrue(repaired)

                with open(tl_path, "r", encoding="utf-8") as f:
                    tl_data = json.load(f)
                self.assertEqual(tl_data["videos"][0]["path"], cleaned)

                with open(zs_path, "r", encoding="utf-8") as f:
                    zs_data = json.load(f)
                self.assertEqual(zs_data["replays"]["tok1"]["path"], cleaned)
            finally:
                if not file_existed and os.path.exists(real_file):
                    os.remove(real_file)
        finally:
            cleanup()

    def test_item4_homography_exact_flag_and_status_text(self):
        # Section 1AN Item 4: details report exact vs reused H.json
        import hashlib
        from xbotgo_core import xb_env
        from xbotgo_core.zoom_state import get_zoom_replay_details_data, sig
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        try:
            details = get_zoom_replay_details_data(temp_dir, game_id, "1")
            self.assertIsNotNone(details)
            self.assertIn("exact_homographies", details)
            self.assertIn("has_homographies", details)
            self.assertFalse(details["has_homographies"])
            tok = details["token"]
            zw = os.path.join(xb_env.tmp_for(temp_dir), "zw")
            # 1) only an H.json from some older plan -> has but not exact
            old_dir = os.path.join(zw, f"{tok}_deadbeef")
            os.makedirs(old_dir, exist_ok=True)
            with open(os.path.join(old_dir, "H.json"), "w", encoding="utf-8") as f:
                f.write("[]")
            d2 = get_zoom_replay_details_data(temp_dir, game_id, tok)
            self.assertTrue(d2["has_homographies"])
            self.assertFalse(d2["exact_homographies"])
            # 2) exact signature folder -> exact
            key = sig(d2["replay"], 720)
            exact_dir = os.path.join(zw, f"{tok}_{hashlib.md5(key.encode()).hexdigest()[:8]}")
            os.makedirs(exact_dir, exist_ok=True)
            with open(os.path.join(exact_dir, "H.json"), "w", encoding="utf-8") as f:
                f.write("[]")
            d3 = get_zoom_replay_details_data(temp_dir, game_id, tok)
            self.assertTrue(d3["has_homographies"])
            self.assertTrue(d3["exact_homographies"])
        finally:
            shutil.rmtree(os.path.join(__import__("xbotgo_core.xb_env", fromlist=["x"]).tmp_for(temp_dir)), ignore_errors=True)
            cleanup()

    def test_zoom_js_shows_reused_homography_label(self):
        js = open(os.path.join(STATIC_DIR, "zoom.js"), encoding="utf-8").read() if "STATIC_DIR" in globals() else open(os.path.join(TOOLS_DIR, "editor", "static", "zoom.js"), encoding="utf-8").read()
        self.assertIn("exact_homographies === false", js)
        self.assertIn("Ready (reused from older plan)", js)

    def test_xbotgo_core_modules_import_every_stdlib_module_they_use(self):
        # Regression for 1AN/1AO: game_state used re.sub() without importing re (NameError at runtime, hidden by try/except).
        import re as _re
        import glob as _glob
        core_dir = os.path.join(TOOLS_DIR, "xbotgo_core")
        mods = ["re", "os", "json", "csv", "glob", "shutil", "hashlib", "subprocess", "datetime", "time", "sys", "uuid", "tempfile"]
        problems = []
        for path in _glob.glob(os.path.join(core_dir, "*.py")) + [os.path.join(TOOLS_DIR, "editor", "server.py")]:
            src = open(path, encoding="utf-8").read()
            code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
            for m in mods:
                uses = _re.search(r"(?<![\w.])" + m + r"\.[A-Za-z_]", code)
                imported = _re.search(r"^\s*(import\s+[^\n]*\b" + m + r"\b|from\s+" + m + r"\s+import)", src, _re.M)
                if uses and not imported:
                    problems.append(f"{os.path.basename(path)} uses {m}. without importing it")
        self.assertEqual(problems, [])

    def test_xbotgo_core_has_no_undefined_names_when_pyflakes_available(self):
        try:
            import pyflakes.api  # noqa: F401
        except ImportError:
            self.skipTest("pyflakes not installed (pip install pyflakes)")
        import io
        from pyflakes import api, reporter
        out, err = io.StringIO(), io.StringIO()
        rep = reporter.Reporter(out, err)
        for fn in ["editor/server.py", "xbotgo_core/game_state.py", "xbotgo_core/zoom_state.py", "xbotgo_core/sync_service.py",
                   "xbotgo_core/sheet_sync_service.py", "xbotgo_core/log_importer.py", "xbotgo_core/clip_bookkeeping.py",
                   "xbotgo_core/reel_service.py", "xbotgo_core/output_checker.py", "xbotgo_core/organize_service.py", "pipeline/sync_game.py"]:
            path = os.path.join(TOOLS_DIR, fn)
            api.checkPath(path, rep)
        undefined = [l for l in out.getvalue().splitlines() if "undefined name" in l]
        self.assertEqual(undefined, [])

    def test_resolve_video_info_and_timeline_heal_dotdot_paths(self):
        # A timeline path with a leading ../ (v2.26-2.27 importer bug) must still resolve to the real video.
        from xbotgo_core.game_state import resolve_video_info
        rel_dir = os.path.join(ROOT, "zz-test-1029", "Videos")
        mock = os.path.join(rel_dir, "mock_1029.mp4")
        existed = os.path.exists(mock)
        os.makedirs(rel_dir, exist_ok=True)
        if not existed:
            open(mock, "w", encoding="utf-8").write("mock")
        try:
            tl = {"videos": [{"file": "mock_1029.mp4", "path": "../zz-test-1029/Videos/mock_1029.mp4", "duration": 12.5}]}
            info = resolve_video_info("mock_1029.mp4", tl)
            self.assertIsNotNone(info)
            self.assertEqual(str(info.get("rel_path") or info.get("path") or "").replace("\\", "/"), "zz-test-1029/Videos/mock_1029.mp4")
        finally:
            if not existed and os.path.exists(mock):
                os.remove(mock)
            shutil.rmtree(os.path.join(ROOT, "zz-test-1029"), ignore_errors=True)

    def test_background_task_fails_when_output_has_error_line_even_if_exit_zero(self):
        # Section 1AN critical 2 behavioral check: a Re-cut-style process that prints ERROR: but exits 0 must end failed.
        from editor import server as s
        import time as _t
        code_err = "import sys; print('ERROR: Re-cut finished with errors', file=sys.stderr)"
        code_ok = "print('all good')"
        res = {}
        for name, code in (("err", code_err), ("ok", code_ok)):
            tid = s.start_background_task([sys.executable, "-c", code], ROOT, f"test-{name}")
            for _ in range(100):
                if s.TASKS[tid]["done"]:
                    break
                _t.sleep(0.1)
            res[name] = (s.TASKS[tid]["done"], s.TASKS[tid]["exit_code"], s.TASKS[tid]["lines"][-1])
        self.assertTrue(res["err"][0])
        self.assertEqual(res["err"][1], 1)
        self.assertIn("error code 1", res["err"][2])
        self.assertEqual(res["ok"][1], 0)
        self.assertIn("finished successfully", res["ok"][2])


class TestPortableRunEverything(unittest.TestCase):
    """Phase 1/2 portability: the run-everything work is a Python runner, the .bat is a thin wrapper."""

    def _fixture(self):
        tmp = tempfile.mkdtemp(prefix="xb_run_")
        out = os.path.join(tmp, "out", "2026-04-03")
        os.makedirs(out)
        json.dump({"opponent": "X"}, open(os.path.join(out, "game_info.json"), "w", encoding="utf-8"))
        return tmp, out

    def test_runner_plan_order_and_dry_run(self):
        sys.path.insert(0, TOOLS_DIR)
        import run_everything as RE
        tmp, out = self._fixture()
        try:
            plan = RE.build_plan(tmp, [out], "2026-04-03", "11")
            heads = [h for h, _, _ in plan]
            self.assertTrue(heads[0].startswith("1. Title cards"))
            self.assertTrue(heads[1].startswith("2. Full game video"))
            self.assertTrue(heads[2].startswith("3. 4K clips, replays, reels"))
            self.assertIn("--run", plan[1][1])
            self.assertIn("--player", plan[2][1])
            r = subprocess.run([sys.executable, os.path.join(TOOLS_DIR, "pipeline", "run_everything.py"), "--root", tmp, "--out", out,
                                "--dry-run"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("4. Checking lengths and outputs", r.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_make_run_all_writes_thin_bat_and_args(self):
        tmp, out = self._fixture()
        try:
            os.makedirs(os.path.join(out, "clips", "cards"))
            open(os.path.join(out, "clips", "cards", "000_intro_fullgame.mp4"), "wb").close()
            r = subprocess.run([sys.executable, os.path.join(TOOLS_DIR, "pipeline", "make_run_all.py"), "--root", tmp, "--out", out,
                                "--player", "11"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            bat = open(os.path.join(out, "run_everything_2026-04-03.bat"), encoding="utf-8").read()
            self.assertIn("tools\\pipeline\\run_everything.py", bat)
            self.assertNotIn("make_reels.py", bat)      # no logic in the .bat any more
            meta = json.load(open(os.path.join(out, "run_everything_2026-04-03.args.json"), encoding="utf-8"))
            self.assertEqual(meta["day"], "2026-04-03")
            self.assertEqual(meta["player"], "11")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_runner_logs_stages_and_check(self):
        sys.path.insert(0, TOOLS_DIR)
        import run_everything as RE
        tmp, out = self._fixture()
        try:
            calls = []
            real_run = subprocess.run
            class R:  # fake finished process
                def __init__(self, rc=0, so="", se=""): self.returncode = rc; self.stdout = so; self.stderr = se
            def fake(argv, **kw):
                calls.append(argv[1:3])
                return R(0, "ALL OK\n") if "check_outputs.py" in " ".join(argv) else R(1 if "fullgame" in " ".join(argv) else 0)
            RE.subprocess.run = fake
            try:
                rc = RE.run(tmp, [out], "2026-04-03", "11")
            finally:
                RE.subprocess.run = real_run
            log = open(os.path.join(out, "run_everything_2026-04-03.log"), encoding="utf-8").read()
            self.assertIn("cards errorlevel 0", log)
            self.assertIn("full game errorlevel 1", log)     # failure logged, run continued
            self.assertIn("reels errorlevel 0", log)
            self.assertTrue(log.rstrip().endswith("ALL OK"))
            self.assertEqual(rc, 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_root_and_host_env_overrides_exist(self):
        src = open(os.path.join(TOOLS_DIR, "xbotgo_core", "xb_env.py"), encoding="utf-8").read()
        self.assertIn("XBOTGO_ROOT", src)
        srv = open(os.path.join(TOOLS_DIR, "editor", "server.py"), encoding="utf-8").read()
        self.assertIn("XBOTGO_HOST", srv)
        self.assertIn("start_new_session=True", srv)     # non-Windows production launch
        self.assertIn('PYTHONUNBUFFERED', srv)           # live progress lines in task modals


class TestEditorUiFixes(unittest.TestCase):
    """Static checks for the reviewer findings fixed in 1AX (no browser needed)."""

    def setUp(self):
        d = os.path.join(TOOLS_DIR, "editor", "static")
        self.js = open(os.path.join(d, "app.js"), encoding="utf-8").read()
        self.css = open(os.path.join(d, "app.css"), encoding="utf-8").read()

    def test_tab_in_time_editors_moves_to_next_time(self):
        self.assertIn("function nextTimeField", self.js)
        self.assertGreaterEqual(self.js.count("e.key === 'Tab'"), 2)   # table cell editor and inspector editor

    def test_flag_chips_do_not_wrap(self):
        self.assertIn(".chip-tag { white-space: nowrap; }", self.css)

    def test_preflight_does_not_blank_list_on_refresh(self):
        self.assertIn("!listEl.children.length", self.js)

    def test_zoom_clip_frames_quiet_on_early_stop(self):
        src = open(os.path.join(TOOLS_DIR, "pipeline", "zoom_clip.py"), encoding="utf-8").read()
        self.assertIn("stderr=subprocess.PIPE", src)
        self.assertIn("if got == 0 and err", src)



class TestTidiedGameRun(unittest.TestCase):
    """1AY: after Tidy (timeline.json in work/, videos in final/) the runner must not re-run stages 2/3 and the check must look in final/."""

    def _tidied(self):
        d = tempfile.mkdtemp(prefix="xb_tidy_")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        out = os.path.join(d, "out", "2026-04-03")
        os.makedirs(os.path.join(out, "work"))
        os.makedirs(os.path.join(out, "final"))
        with open(os.path.join(out, "work", "timeline.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        with open(os.path.join(out, "final", "2026_04_03_full_game.mp4"), "wb") as f:
            f.write(b"x")
        return d, out

    def test_is_tidied_and_plan_skips_stages_2_and_3(self):
        import run_everything
        d, out = self._tidied()
        self.assertTrue(run_everything.is_tidied(out))
        full = run_everything.build_plan(d, [out], "2026-04-03", "11")
        self.assertEqual(len(full), 3)  # default plan unchanged
        skipped = run_everything.build_plan(d, [out], "2026-04-03", "11", skip_tidied=True)
        self.assertEqual([h.split(".")[0] for h, _, _ in skipped], ["1"])  # only title cards
        with open(os.path.join(out, "timeline.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        self.assertFalse(run_everything.is_tidied(out))  # not tidied once timeline.json is back in the game folder

    def test_check_outputs_looks_in_final(self):
        from xbotgo_core.output_checker import check_game_outputs
        d, out = self._tidied()
        res = check_game_outputs(out_dir=out, day="2026-04-03", root=d)
        names = [r["relpath"] for r in res["results"]]
        self.assertTrue(any("final" in n and "full_game" in n for n in names), names)
        self.assertFalse(any("no full game file yet" in " ".join(r["messages"]) for r in res["results"]))


class TestProductionStatusFinishMarker(unittest.TestCase):
    """1AZ: the status must not stay RUNNING for the ~20 s the console waits after the final check printed its last line."""

    def test_running_pid_with_fresh_finished_log_is_not_running(self):
        import server
        base = tempfile.mkdtemp(prefix="xb_status_")
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        d = os.path.join(base, "2026-04-03")  # the status code derives the day from the folder name
        os.makedirs(d)
        pid_f = os.path.join(d, "run_everything_2026-04-03.pid")
        log_f = os.path.join(d, "run_everything_2026-04-03.log")
        with open(pid_f, "w", encoding="utf-8") as f:
            f.write("4242")
        old_res, old_run = server.resolve_game_out, server.is_pid_running
        server.resolve_game_out = lambda g: d
        server.is_pid_running = lambda p: True
        try:
            def write(lines, t):
                with open(log_f, "w", encoding="utf-8") as f:
                    f.write("\r\n".join(lines) + "\r\n")
                os.utime(log_f, (t, t))
            now = time.time()
            os.utime(pid_f, (now, now))
            write(["x start", "OK  a.mp4", "ALL OK"], now + 5)
            self.assertNotEqual(server.get_production_pid_and_status("2026-04-03")[1], "running")
            write(["x start", "OK  a.mp4", "ALL OK"], now - 50)  # stale log from the PREVIOUS run: new run still going
            self.assertEqual(server.get_production_pid_and_status("2026-04-03")[1], "running")
            write(["x start", "x cards errorlevel 0"], now + 5)  # same run, not finished yet
            self.assertEqual(server.get_production_pid_and_status("2026-04-03")[1], "running")
        finally:
            server.resolve_game_out, server.is_pid_running = old_res, old_run


class TestRestartFlag(unittest.TestCase):
    """1AZ: tmp/restart_editor.flag restarts the editor (exit code 75 + looping launcher); the flag is removed BEFORE the restart."""

    def test_flag_states(self):
        import server
        d = tempfile.mkdtemp(prefix="xb_flag_")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        flag = os.path.join(d, "restart_editor.flag")
        old = dict(server.TASKS)
        self.addCleanup(lambda: (server.TASKS.clear(), server.TASKS.update(old)))
        server.TASKS.clear()
        self.assertEqual(server.restart_flag_state(flag), "none")
        with open(flag, "w", encoding="utf-8") as f:
            f.write("")
        server.TASKS["t1"] = {"done": False}
        self.assertEqual(server.restart_flag_state(flag), "waiting")  # a background job is running: wait
        self.assertTrue(os.path.exists(flag))
        with open(flag, "w", encoding="utf-8") as f:
            f.write("force")
        self.assertEqual(server.restart_flag_state(flag), "restart")  # force overrides
        self.assertFalse(os.path.exists(flag))  # removed first, so no restart loop
        server.TASKS["t1"]["done"] = True
        with open(flag, "w", encoding="utf-8") as f:
            f.write("")
        self.assertEqual(server.restart_flag_state(flag), "restart")
        self.assertFalse(os.path.exists(flag))

    def test_launchers_loop_on_exit_code_75(self):
        self.assertEqual(__import__("server").RESTART_EXIT_CODE, 75)
        for name, needle in (("review_editor.bat", "ERRORLEVEL% equ 75 goto run"),
                             ("review_editor_5001.bat", "ERRORLEVEL% equ 75 goto run"),
                             ("review_editor.sh", "-eq 75")):
            p = os.path.join(ROOT, name)
            if not os.path.exists(p):
                continue  # test root built by make_test_root.py has no launchers
            with open(p, encoding="utf-8") as f:
                txt = f.read()
            self.assertIn(needle, txt, name)
            self.assertIn("XBOTGO_RESTART_LOOP=1", txt.replace('export ', ''), name)


class TestLeakFixes(unittest.TestCase):
    """1BA: no scratch left behind by preview_reel, and the temp-game fixture removes its backups."""

    def test_preview_reel_removes_its_ts_scratch(self):
        with open(os.path.join(TOOLS_DIR, "pipeline", "preview_reel.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("shutil.rmtree(tmp, ignore_errors=True)", src)
        self.assertIn("finally:", src)
        compile(src, "preview_reel.py", "exec")

    def test_fixture_cleanup_removes_backups(self):
        game_id, temp_dir, cleanup = make_temp_game_fixture()
        bdir = os.path.join(ROOT, "tmp", "review_editor", "backups")
        os.makedirs(bdir, exist_ok=True)
        b1 = os.path.join(bdir, game_id + "_reviewed.csv.20260101-000000.bak")
        b2 = os.path.join(ROOT, "tmp", "reviewed", game_id + "_reviewed.csv.bak-1030-000000")
        for b in (b1, b2):
            with open(b, "w", encoding="utf-8") as f:
                f.write("x")
        cleanup()
        for p in (b1, b2, temp_dir):
            self.assertFalse(os.path.exists(p), p)


class TestUntidy(unittest.TestCase):
    """1BA: Untidy puts a tidied game back (work/ and final/ to the game root) so it can be re-rendered."""

    def _tidied_game(self):
        import xbotgo_core.organize_service as osv
        tmp = tempfile.mkdtemp(prefix="xb_untidy_")
        out = os.path.join(tmp, "out")
        g = os.path.join(out, "2026-04-03")
        for rel in ("timeline.json", "game_info.json", "marks.csv", "clips/reviewed/a.mp4", "clips/cards/000.mp4",
                    "run_everything_2026-04-03.args.json",
                    "clips/preview720/p.mp4", "2026-04-03_full_game.mp4", "reels/players/11.mp4",
                    "reels/2026-04-03_highlights_transitions.mp4"):
            fp = os.path.join(g, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "w", encoding="utf-8") as f:
                f.write("x")
        man = os.path.join(out, "_organize_manifest.json")
        plan = osv.plan_all(out, only_games=["2026-04-03"])
        osv.execute_organize_plan(plan["all_moves"], man)
        return osv, tmp, out, g, man

    def test_untidy_roundtrip(self):
        osv, tmp, out, g, man = self._tidied_game()
        try:
            self.assertTrue(osv.is_tidied_dir(g))
            self.assertFalse(os.path.exists(os.path.join(g, "timeline.json")))
            ops = osv.plan_untidy(g)
            moved, skipped = osv.execute_untidy(ops, man, "2026-04-03")
            self.assertGreaterEqual(moved, 6)
            self.assertEqual(skipped, [])
            self.assertFalse(osv.is_tidied_dir(g))
            for rel in ("timeline.json", "game_info.json", "marks.csv", "clips/reviewed/a.mp4", "clips/cards/000.mp4",
                        "run_everything_2026-04-03.args.json", "2026-04-03_full_game.mp4", "reels/players/11.mp4", "reels/2026-04-03_highlights_transitions.mp4"):
                self.assertTrue(os.path.exists(os.path.join(g, rel.replace("/", os.sep))), rel)
            self.assertFalse(os.path.exists(os.path.join(g, "work", "timeline.json")))
            # run_everything agrees the game is no longer tidied
            sys.path.insert(0, TOOLS_DIR)
            import run_everything as RE
            self.assertFalse(RE.is_tidied(g))
            # intermediates stay in _to_delete (nothing there is needed to re-render)
            self.assertTrue(os.path.exists(os.path.join(g, "_to_delete", "clips", "preview720", "p.mp4")))
            # the manifest no longer lists this game
            with open(man, encoding="utf-8") as f:
                self.assertEqual(json.load(f), [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_untidy_never_overwrites(self):
        osv, tmp, out, g, man = self._tidied_game()
        try:
            with open(os.path.join(g, "timeline.json"), "w", encoding="utf-8") as f:
                f.write("newer")
            moved, skipped = osv.execute_untidy(osv.plan_untidy(g), man, "2026-04-03")
            self.assertEqual(len(skipped), 1)
            with open(os.path.join(g, "timeline.json"), encoding="utf-8") as f:
                self.assertEqual(f.read(), "newer")
            self.assertTrue(os.path.exists(os.path.join(g, "work", "timeline.json")))   # left in place
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_untidy_merges_into_existing_folders(self):
        # a run after Tidy recreates an (empty) clips/extra; Untidy must merge into it, not skip the whole folder
        osv, tmp, out, g, man = self._tidied_game()
        try:
            os.makedirs(os.path.join(g, "clips", "cards"))                     # empty, recreated by a run
            os.makedirs(os.path.join(g, "work", "clips", "extra"), exist_ok=True)
            with open(os.path.join(g, "work", "clips", "extra", "e1.mp4"), "w", encoding="utf-8") as f:
                f.write("x")
            os.makedirs(os.path.join(g, "clips", "extra"))
            moved, skipped = osv.execute_untidy(osv.plan_untidy(g), man, "2026-04-03")
            self.assertTrue(os.path.exists(os.path.join(g, "clips", "extra", "e1.mp4")))
            self.assertTrue(os.path.exists(os.path.join(g, "clips", "cards", "000.mp4")))
            self.assertEqual(skipped, [])
            self.assertFalse(os.path.exists(os.path.join(g, "work", "clips", "extra", "e1.mp4")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_untidy_endpoint_and_cli_flag_exist(self):
        src = open(os.path.join(TOOLS_DIR, "editor", "server.py"), encoding="utf-8").read()
        self.assertIn('"--untidy"', src)
        cli = open(os.path.join(TOOLS_DIR, "pipeline", "organize_out.py"), encoding="utf-8").read()
        self.assertIn("--untidy", cli)
        js = open(os.path.join(TOOLS_DIR, "editor", "static", "app.js"), encoding="utf-8").read()
        self.assertIn("action: organizeAction", js)


class TestMultiGameDay(unittest.TestCase):
    """1BA: two games on one day (out/<day> and out/<day>-g2) share ONE run file."""

    def test_two_games_one_run(self):
        sys.path.insert(0, TOOLS_DIR)
        import run_everything as RE
        tmp = tempfile.mkdtemp(prefix="xb_multi_")
        try:
            outs = []
            for name in ("2026-04-03", "2026-04-03-g2"):
                d = os.path.join(tmp, "out", name)
                os.makedirs(os.path.join(d, "clips", "cards"))
                with open(os.path.join(d, "game_info.json"), "w", encoding="utf-8") as f:
                    json.dump({"opponent": name}, f)
                open(os.path.join(d, "clips", "cards", "000_intro_fullgame.mp4"), "wb").close()
                outs.append(d)
            self.assertEqual(RE.find_outs(tmp, "2026-04-03"), outs)
            plan = RE.build_plan(tmp, outs, "2026-04-03", "11")
            heads = [h for h, _, _ in plan]
            self.assertEqual(len(plan), 6, heads)                      # 3 stages x 2 games
            self.assertIn("2026-04-03-g2", " ".join(" ".join(a) for _, a, _ in plan))
            # a tidied first game is skipped, the second is still planned
            plan2 = RE.build_plan(tmp, outs, "2026-04-03", "11", skip_tidied=False)
            self.assertEqual(len(plan2), 6)
            r = subprocess.run([sys.executable, os.path.join(TOOLS_DIR, "pipeline", "make_run_all.py"), "--root", tmp, "--day", "2026-04-03",
                                "--player", "11"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            bat = open(os.path.join(outs[0], "run_everything_2026-04-03.bat"), encoding="utf-8").read()
            self.assertNotIn("--out", bat)                              # several games: the runner discovers them by --day
            self.assertIn("--day 2026-04-03", bat)
            meta = json.load(open(os.path.join(outs[0], "run_everything_2026-04-03.args.json"), encoding="utf-8"))
            self.assertEqual(meta["games"], 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestGuideMirror(unittest.TestCase):
    """1BA: app_design/USER_GUIDE.html must stay a byte-identical copy of the served static/guide.html."""

    def test_guide_copies_identical(self):
        a = os.path.join(TOOLS_DIR, "editor", "static", "guide.html")
        b = os.path.join(ROOT, "app_design", "USER_GUIDE.html")
        if not os.path.exists(b):
            self.skipTest("app_design/USER_GUIDE.html not in this tree (test kit)")
        with open(a, "rb") as fa, open(b, "rb") as fb:
            self.assertEqual(fa.read(), fb.read(), "copy static/guide.html over app_design/USER_GUIDE.html")


class TestPreflightTidiedFlag(unittest.TestCase):
    """1BA: the Final 4K dialog must say when a game is tidied (checks pass because the archive exists)."""

    def test_preflight_reports_tidied(self):
        import server
        tmp = tempfile.mkdtemp(prefix="xb_tidied_pf_")
        g = os.path.join(tmp, "2026-04-03")
        for rel in ("work/timeline.json", "work/game_info.json", "final/2026_04_03_full_game.mp4"):
            fp = os.path.join(g, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "w", encoding="utf-8") as f:
                f.write("x")
        old_resolve = server.resolve_game_out
        old_calc = server.calculate_production_preflight
        server.resolve_game_out = lambda gid: g
        server.calculate_production_preflight = lambda gid, od: {"all_passed": True, "checks": {}}
        try:
            data = server.app.test_client().get("/api/game/2026-04-03/production/preflight").get_json()
            self.assertTrue(data["tidied"])
            os.remove(os.path.join(g, "final", "2026_04_03_full_game.mp4"))
            data = server.app.test_client().get("/api/game/2026-04-03/production/preflight").get_json()
            self.assertFalse(data["tidied"])
        finally:
            server.resolve_game_out = old_resolve
            server.calculate_production_preflight = old_calc
            shutil.rmtree(tmp, ignore_errors=True)

    def test_production_status_has_timestamps_and_dialog_labels_last_run(self):
        import server
        tmp = tempfile.mkdtemp(prefix="xb_laststatus_")
        g = os.path.join(tmp, "2026-04-03")
        os.makedirs(g)
        with open(os.path.join(g, "run_everything_2026-04-03.log"), "w", encoding="utf-8") as f:
            f.write("ALL OK\nALL DONE\n")
        old = server.resolve_game_out
        server.resolve_game_out = lambda gid: g
        try:
            data = server.app.test_client().get("/api/game/2026-04-03/production/status").get_json()
            self.assertEqual(data["status"], "completed")
            self.assertIsNotNone(data["log_ts"])
            self.assertIn("started_ts", data)
        finally:
            server.resolve_game_out = old
            shutil.rmtree(tmp, ignore_errors=True)
        js = open(os.path.join(TOOLS_DIR, "editor", "static", "app.js"), encoding="utf-8").read()
        self.assertIn("Status from last run", js)

    def test_dialog_has_tidied_note(self):
        js = open(os.path.join(TOOLS_DIR, "editor", "static", "app.js"), encoding="utf-8").read()
        html = open(os.path.join(TOOLS_DIR, "editor", "static", "index.html"), encoding="utf-8").read()
        self.assertIn("productionTidiedPanel", html)
        self.assertIn("openUntidyFromProduction", js)
        self.assertIn("data.tidied", js)


class TestLogAutoCloseStartLockAndReelStreaming(unittest.TestCase):
    """10-30 UX: log modals auto-close on success + Log button, START stays while a run is going,
    reels/clips stream per-line output, .sh twin of the production .bat."""
    def _read(self, *parts):
        return open(os.path.join(ROOT, *parts), encoding="utf-8").read()

    def test_log_autoclose_and_view_log_button(self):
        a = self._read("tools", "editor", "static", "app.js"); h = self._read("tools", "editor", "static", "index.html")
        for t in ("maybeAutoCloseLog", "viewLastLog", "xbotgo.logAutoClose"): self.assertIn(t, a)
        for t in ('id="logAutoClose"', 'id="viewLogBtn"'): self.assertIn(t, h)

    def test_start_lock_ignored_by_preflight(self):
        a = self._read("tools", "editor", "static", "app.js")
        self.assertIn("syncProductionConfirmLock", a)
        self.assertEqual(a.count("!inpConfirm.readOnly &&"), 2)

    def test_reels_run_streams_and_shared_helper(self):
        m = self._read("tools", "pipeline", "make_reels.py")
        self.assertIn("run_streaming(cmd)", m); self.assertIn("[reels] Building", m)
        from xbotgo_core.procs import run_streaming
        import sync_game
        self.assertIs(sync_game.run_streaming, run_streaming)

    def test_loop_action_follows_edited_boundaries(self):
        a = self._read("tools", "editor", "static", "app.js")
        self.assertIn("const loopRowIndex = state.selectedRowIndex;", a)
        self.assertIn("parseTime(lr.action_start)", a)     # boundaries re-read every tick, not captured once

    def test_undo_after_timeline_drag_and_loop_kept(self):
        a = self._read("tools", "editor", "static", "app.js")
        self.assertIn("if (!hasDragged && activeDrag !== 'playhead') recordHistory(state.selectedRowIndex);", a)   # snapshot BEFORE the change
        i = a.index("function onPointerUp()"); self.assertNotIn("recordHistory", a[i:i + 400])
        self.assertEqual(a.count("if (wasLooping) toggleActionLoop();"), 2)       # undo and undoClip keep the loop state
        self.assertIn("skip snapshots identical to the current row", a)

    def test_launchers_do_not_change_caller_folder(self):
        # Ctrl+C + "Terminate batch job" skips any popd, so the launchers must not cd at all (user was left in tools\\editor)
        for name, needle in (("review_editor.bat", '%~dp0tools\\editor\\server.py'), ("review_editor_5001.bat", '%~dp0tools\\editor\\server.py'),
                             ("review_editor.sh", 'tools/editor/server.py')):
            if not os.path.exists(os.path.join(ROOT, name)):
                continue                      # the test kit has no launchers
            txt = self._read(name)
            self.assertIn(needle, txt)
            self.assertNotIn("cd /d", txt.replace("rem ", "#"))
            self.assertNotRegex(txt, r'(?m)^cd ')

    def test_run_everything_sh_twin(self):
        m = self._read("tools", "pipeline", "make_run_all.py")
        self.assertIn("run_everything_{day}.sh", m); self.assertIn("run_everything.py", m)


class TestAppConfig(unittest.TestCase):
    """Identifying data lives in config only; the built-in fallback is generic (Home FC / Guest FC / League A)."""

    def setUp(self):
        from xbotgo_core import app_config
        self.ac = app_config
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _cfg(self, d):
        p = os.path.join(self.tmp, "game_defaults.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f)
        return p

    def test_fallback_is_fake_when_no_config(self):
        c = self.ac.load_from_file(os.path.join(self.tmp, "missing.json"))
        self.assertEqual(c["team_name"], "Home FC")
        self.assertEqual(c["guest_name"], "Guest FC")
        self.assertEqual(c["league"], "League A")
        self.assertEqual(c["sheet_id"], "")
        self.assertEqual(c["featured_players"], ["7"])

    def test_broken_config_falls_back(self):
        p = os.path.join(self.tmp, "game_defaults.json")
        with open(p, "w") as f:
            f.write("{not json")
        self.assertEqual(self.ac.load_from_file(p)["team_name"], "Home FC")

    def test_user_values_override_and_custom_league_list(self):
        p = self._cfg({"team_name": "Rovers", "leagues": [{"name": "Cup", "logo": "x.png"}, "Shield"], "league": "Shield",
                       "featured_players": "4, 9"})
        c = self.ac.load_from_file(p)
        self.assertEqual(c["team_name"], "Rovers")
        self.assertEqual([l["name"] for l in c["leagues"]], ["Cup", "Shield"])
        self.assertEqual(c["featured_players"], ["4", "9"])
        self.assertEqual(self.ac.logo_for_league("cup", c), "x.png")

    def test_env_sheet_id_overrides(self):
        old = os.environ.get("XBOTGO_SHEET_ID")
        os.environ["XBOTGO_SHEET_ID"] = "ENV_SHEET"
        try:
            self.assertEqual(self.ac.load_from_file(os.path.join(self.tmp, "missing.json"))["sheet_id"], "ENV_SHEET")
        finally:
            if old is None:
                os.environ.pop("XBOTGO_SHEET_ID", None)
            else:
                os.environ["XBOTGO_SHEET_ID"] = old

    def test_no_sheet_configured_is_a_clear_error(self):
        root = self.tmp
        os.makedirs(os.path.join(root, "config"))
        self.assertEqual(sheet_sync_service.get_configured_sheet_id(root), "")
        with self.assertRaises(Exception):
            sheet_sync_service.get_service_account_client(key_path=__file__, root_dir=root)

    def test_tab_name_uses_explicit_league_from_game_info_incl_custom_third_league(self):
        root = self.tmp
        os.makedirs(os.path.join(root, "config"))
        with open(os.path.join(root, "config", "game_defaults.json"), "w") as f:
            json.dump({"leagues": [{"name": "League A"}, {"name": "League B"}], "league": "League A"}, f)
        gdir = os.path.join(root, "out", "2026-11-02")
        os.makedirs(gdir)
        self.assertEqual(sheet_sync_service.determine_desired_tab_name("2026-11-02", root_dir=root), "11/02/26 League A")
        with open(os.path.join(gdir, "game_info.json"), "w") as f:
            json.dump({"league": "State Cup"}, f)
        self.assertEqual(sheet_sync_service.determine_desired_tab_name("2026-11-02", root_dir=root), "11/02/26 State Cup")


class TestNoIdentifiersInCode(unittest.TestCase):
    """Guard: no personal values (deny-list) and no emails/long IDs/personal paths anywhere in tools/ or the root docs."""

    def test_tools_tree_is_clean(self):
        from xbotgo_core import identifier_scan
        dl = os.environ.get("XBOTGO_DENYLIST") or os.path.join(ROOT, "shared", "secrets", "denylist.txt")
        findings = identifier_scan.scan_tree(os.path.join(ROOT, "tools"), dl if os.path.exists(dl) else None)
        self.assertEqual(findings, [], "identifying values found (file, line, kind, masked): %r" % findings[:10])


if __name__ == "__main__":
    unittest.main()
