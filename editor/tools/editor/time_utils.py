"""Backward-compatibility shim for tools/editor/time_utils.py.

Core logic has migrated to tools/xbotgo_core/time_utils.py.
This module re-exports all symbols to preserve 100% compatibility with existing tools and tests.
"""
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from xbotgo_core.time_utils import *  # noqa: F401, F403
