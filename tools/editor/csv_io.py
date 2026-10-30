"""Backward-compatibility shim for tools/editor/csv_io.py.

Core logic has migrated to tools/xbotgo_core/csv_io.py.
This module re-exports all symbols to preserve 100% compatibility with existing tools and tests.
"""
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from xbotgo_core.csv_io import *  # noqa: F401, F403
import xbotgo_core.csv_io as _impl

STANDARD_COLUMNS = _impl.STANDARD_COLUMNS
HEADER_SYNONYMS = _impl.HEADER_SYNONYMS
TMP_BACKUPS = _impl.TMP_BACKUPS
