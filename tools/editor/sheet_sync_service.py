"""Backward-compatibility shim re-exporting Google Sheet synchronization service from xbotgo_core."""
import os
import sys

CORE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "xbotgo_core")
if os.path.dirname(CORE_DIR) not in sys.path:
    sys.path.insert(0, os.path.dirname(CORE_DIR))

from xbotgo_core.sheet_sync_service import (
    ROOT,
    DEFAULT_SHEET_ID,
    SHEET_ID,
    TEXT_RANGES,
    INT_COLS,
    get_configured_sheet_id,
    get_service_account_client,
    determine_desired_tab_name,
    determine_tab_name,
    list_tabs,
    rename_google_sheet_tab,
    build_sheet_push_payload,
    fit_columns,
    push_to_google_sheet,
    pull_from_google_sheet,
    push_clip_column,
)

__all__ = [
    "ROOT",
    "DEFAULT_SHEET_ID",
    "SHEET_ID",
    "TEXT_RANGES",
    "INT_COLS",
    "get_configured_sheet_id",
    "get_service_account_client",
    "determine_desired_tab_name",
    "determine_tab_name",
    "list_tabs",
    "rename_google_sheet_tab",
    "build_sheet_push_payload",
    "fit_columns",
    "push_to_google_sheet",
    "pull_from_google_sheet",
    "push_clip_column",
]
