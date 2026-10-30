"""xbotgo_core: Shared business logic, state models, and utilities for XbotGo.

This package contains pure Python modules with zero Flask or web-framework dependencies:
- csv_io: Atomic CSV read/write, renumbering, row insertion, and dirty tracking.
- time_utils: Time string parsing ('mm:ss', '0:mm:ss', Sheets-mangled) and formatting.
- game_state: Match discovery, game info, config defaults, timeline/video resolution, and roster management.
- zoom_state: Zoom replay data models, candidate listing, auto-framing, homography resolution, and spec apply.
- clip_bookkeeping: 4K production output staleness checking and preflight validation.
- reel_selection: Reel player grouping, clip selection, and cheer detection rules.
- organize_service: Game and shared output directory tidying, planning, applying, and restoring.
- sync_service: Multi-source reviewed CSV reconciliation, clip and replay staleness/renames, and clip column updates.
- sheet_sync_service: Google Sheet tab management, plain text formatting, matrix push, and clip column write.
- log_importer: Ingest MP4 MatchInfo uuid box and app logs into initial review table, clockmap, and timeline.
- reel_service: Highlight reel clip sequencing, card placement, cheers, and halftime score.
- output_checker: Finished video/audio stream duration consistency verification.
"""
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(TOOLS_DIR)
PIPELINE_DIR = os.path.join(TOOLS_DIR, "pipeline")
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)   # pipeline scripts (cut_reviewed, dumplayout, zoom_edit ...) import by bare name

from . import csv_io
from . import time_utils
from . import game_state
from . import zoom_state
from . import clip_bookkeeping
from . import reel_selection
from . import organize_service
from . import sync_service
from . import sheet_sync_service
from . import log_importer
from . import reel_service
from . import output_checker

# Re-export most commonly used utilities directly from package root
from .time_utils import secs, format_time, validate_timing_order
fmt_time = format_time
from .csv_io import read_reviewed_csv, write_reviewed_csv, compute_clip_numbers, STANDARD_COLUMNS
from .game_state import (
    DEFAULTS_FILE,
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
    normalize_and_repair_paths
)
from .zoom_state import (
    CROP_W,
    lab,
    jobs_by_clip,
    names,
    sig,
    parse_crop,
    resolve_token,
    get_zoom_replays_data,
    get_zoom_replay_details_data,
    auto_frame_zoom_replays_data,
    get_zoom_homographies_data,
    remove_zoom_replay_data,
    restore_zoom_replay_data,
    apply_zoom_spec_to_state
)
from .clip_bookkeeping import (
    check_4k_outputs_staleness,
    calculate_production_preflight
)
from .reel_selection import (
    ours_goals,
    matches_player,
    get_player_clip_counts,
    get_default_featured_player
)
from .organize_service import (
    plan_game,
    plan_all,
    execute_organize_plan,
    restore_organize_manifest
)
from .sync_service import (
    sync_game_state,
    two_phase_rename
)
from .sheet_sync_service import (
    push_to_google_sheet,
    pull_from_google_sheet,
    push_clip_column,
    rename_google_sheet_tab,
    list_tabs
)
from .log_importer import (
    build_review_from_log
)
from .reel_service import (
    calculate_reel_manifest
)
from .output_checker import (
    check_game_outputs
)
