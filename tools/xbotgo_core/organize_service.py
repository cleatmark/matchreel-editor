"""Tidy out/<game> folders: final reels -> final/, inputs needed to regenerate -> work/, intermediates -> _to_delete/.
Provides pure planning and move execution without Flask or CLI dependencies.
Nothing is deleted. Every move is recorded in out/_organize_manifest.json and can be undone with restore.
"""
from .diag import swallowed as _swallowed
import fnmatch
import json
import os
import re
import shutil
from typing import List, Tuple, Dict, Any, Optional

GAME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}(-g\d)?$")

FINAL_FILES = ["*_full_game.mp4", "*_highlights_transitions.mp4", "*_goals_transitions.mp4", "*_highlights.mp4"]
WORK_FILES = [
    "timeline.json", "clockmap.json", "marks.csv", "marker_debug.csv", "review.csv", "review_prefilled.csv",
    "cut_plan.json", "game_info.json", "zoom_state.json", "zoom_adopt.json", "clip_column.json", "full_game.m3u",
    "reels_list.txt", "list_4k_*.txt", "run_everything_*.bat", "run_everything_*.sh", "run_everything_*.args.json", "tab.csv", "extras.json"
]
DEL_FILES = ["zoomcheck.jpg", "clockcheck.png", "preview_list*.txt", "*.bak-*", "*.log", "*.tmp", "tab_sync*.csv"]
DEL_DIRS = ["zw*", "zoomtest", "zoom_sheets", "zoom_verify", "fullgame_tmp", "zoom[0-9]*", "zq", "diag*"]


def file_or_dir_size(p: str) -> int:
    """Compute recursive disk size of a file or directory in bytes."""
    if os.path.isfile(p):
        return os.path.getsize(p)
    if not os.path.exists(p):
        return 0
    return sum(
        os.path.getsize(os.path.join(d, f))
        for d, _, fs in os.walk(p)
        for f in fs
        if os.path.exists(os.path.join(d, f))
    )


def match_patterns(name: str, pats: List[str]) -> bool:
    """Return True if name matches any glob pattern in pats."""
    return any(fnmatch.fnmatch(name, p) for p in pats)


def plan_game(g: str) -> Tuple[List[Tuple[str, str, str]], List[str]]:
    """Return (ops, unknown) where each op is (src, dest_relative_to_game, bucket)."""
    ops = []
    unknown = []

    def add(src, bucket, dest):
        ops.append((src, dest, bucket))

    if not os.path.isdir(g):
        return ops, unknown

    for name in sorted(os.listdir(g)):
        p = os.path.join(g, name)
        if name in ("final", "work", "_to_delete"):
            continue
        if os.path.isfile(p):
            if match_patterns(name, FINAL_FILES) and "preview" not in name and "nomusic" not in name:
                add(p, "final", os.path.join("final", name))
            elif match_patterns(name, WORK_FILES):
                add(p, "work", os.path.join("work", name))
            elif match_patterns(name, DEL_FILES):
                add(p, "delete", os.path.join("_to_delete", name))
            else:
                unknown.append(p)
        elif name == "reels":
            for r in sorted(os.listdir(p)):
                rp = os.path.join(p, r)
                if r == "players" and os.path.isdir(rp):
                    add(rp, "final", os.path.join("final", "players"))
                elif re.fullmatch(r"v\d+", r) and os.path.isdir(rp):
                    add(rp, "delete", os.path.join("_to_delete", "reels", r))
                elif r.endswith(".work") or r.startswith("old_") or "preview" in r or "nomusic" in r:
                    add(rp, "delete", os.path.join("_to_delete", "reels", r))
                elif os.path.isfile(rp) and match_patterns(r, FINAL_FILES):
                    add(rp, "final", os.path.join("final", r))
                elif os.path.isfile(rp) and match_patterns(r, WORK_FILES):
                    add(rp, "work", os.path.join("work", r))
                else:
                    unknown.append(rp)
        elif name == "clips":
            for c in sorted(os.listdir(p)):
                cp = os.path.join(p, c)
                if c in ("reviewed", "reviewed4k", "cards", "var"):
                    add(cp, "work", os.path.join("work", "clips", c))
                elif c in ("preview720", "preview720_dropped", "dropped", "stale"):
                    add(cp, "delete", os.path.join("_to_delete", "clips", c))
                elif c == "extra":
                    for e in sorted(os.listdir(cp)):
                        ep = os.path.join(cp, e)
                        if e == "master" and os.path.isdir(ep):
                            for mm in sorted(os.listdir(ep)):
                                mp = os.path.join(ep, mm)
                                if os.path.isfile(mp) and ("_720" in mm or mm == "old"):
                                    add(mp, "delete", os.path.join("_to_delete", "clips", "extra", "master", mm))
                                else:
                                    add(mp, "work", os.path.join("work", "clips", "extra", "master", mm))
                        elif re.fullmatch(r"v\d+", e) or "_720" in e:
                            add(ep, "delete", os.path.join("_to_delete", "clips", "extra", e))
                        else:
                            add(ep, "work", os.path.join("work", "clips", "extra", e))
                else:
                    unknown.append(cp)
        elif match_patterns(name, DEL_DIRS):
            add(p, "delete", os.path.join("_to_delete", name))
        elif name in ("var", "announcer"):
            add(p, "work", os.path.join("work", name))
        else:
            unknown.append(p)
    return ops, unknown


def plan_all(root_out: str, only_games: Optional[List[str]] = None):
    """Generate the full organization plan across all games and shared top-level out items.
    
    Returns:
        dict with:
            games: dict[game_id, { ops: list, unknown: list, sizes: dict }]
            shared: list of (src, dst, bucket)
            all_moves: list of (src, dst)
            totals: dict[bucket, bytes]
    """
    root_out = os.path.abspath(root_out)
    if not os.path.exists(root_out):
        return {"games": {}, "shared": [], "all_moves": [], "totals": {"final": 0, "work": 0, "delete": 0}}

    candidates = [
        d for d in sorted(os.listdir(root_out))
        if GAME_PATTERN.match(d) and os.path.isdir(os.path.join(root_out, d))
    ]
    if only_games:
        candidates = [d for d in candidates if d in only_games]

    game_results = {}
    tot = {"final": 0, "work": 0, "delete": 0}
    all_moves = []

    for d in candidates:
        g = os.path.join(root_out, d)
        ops, unk = plan_game(g)
        s = {"final": 0, "work": 0, "delete": 0}
        for src, dst, b in ops:
            sz = file_or_dir_size(src)
            s[b] += sz
            tot[b] += sz
            all_moves.append((src, os.path.join(g, dst)))
        game_results[d] = {
            "path": g,
            "ops": ops,
            "unknown": unk,
            "sizes": s
        }

    shared = []
    if not only_games:
        for name in sorted(os.listdir(root_out)):
            p = os.path.join(root_out, name)
            if name in ("reviewed", "bat", "README.md"):
                shared.append((p, os.path.join(root_out, "work_shared", name), "work"))
            elif (os.path.isfile(p) or os.path.isdir(p)) and not GAME_PATTERN.match(name) and not name.startswith(("_organize", "work_shared", "_to_delete", "_music_history")):
                shared.append((p, os.path.join(root_out, "_to_delete", name), "delete"))
        for src, dst, b in shared:
            sz = file_or_dir_size(src)
            tot[b] += sz
            all_moves.append((src, dst))

    return {
        "games": game_results,
        "shared": shared,
        "all_moves": all_moves,
        "totals": tot
    }


def execute_organize_plan(allops: List[Tuple[str, str]], manifest_path: str) -> Tuple[int, List[str]]:
    """Execute the file and folder moves and record in the manifest file.
    
    Returns:
        (moved_count, skipped_list)
    """
    done = json.load(open(manifest_path, encoding="utf-8")) if os.path.exists(manifest_path) else []
    moved = 0
    skipped = []

    for src, dst in allops:
        if not os.path.exists(src):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            skipped.append(dst)
            continue
        shutil.move(src, dst)
        done.append([src, dst])
        moved += 1

    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    from .atomic_io import write_json_atomic
    write_json_atomic(manifest_path, done, indent=1)

    return moved, skipped


def restore_organize_manifest(manifest_path: str) -> int:
    """Restore previously organized files back to their original locations from manifest.
    
    Returns:
        restored_count
    """
    if not os.path.exists(manifest_path):
        return 0
    with open(manifest_path, "r", encoding="utf-8") as f:
        man = json.load(f)

    restored = 0
    for src, dst in reversed(man):
        if os.path.exists(dst):
            os.makedirs(os.path.dirname(src), exist_ok=True)
            shutil.move(dst, src)
            restored += 1
    return restored


def is_tidied_dir(g: str) -> bool:
    """True when the game folder has been tidied: no timeline.json at the root but one in work/."""
    return (not os.path.exists(os.path.join(g, "timeline.json"))
            and os.path.exists(os.path.join(g, "work", "timeline.json")))


def plan_untidy(g: str) -> List[Tuple[str, str]]:
    """Inverse of Tidy for ONE game, by rules (not by the manifest, whose absolute paths are not portable).
    work/<x> -> <x>, work/clips/<c> -> clips/<c>, final/players -> reels/players, final/*_full_game.mp4 -> <file>, other final reels -> reels/<file>.
    _to_delete/ is left alone (it holds only intermediates). Returns [(src, dst)]; moves whose dst exists are
    left out by execute_untidy."""
    ops = []
    if not os.path.isdir(g):
        return ops
    work = os.path.join(g, "work")
    if os.path.isdir(work):
        for name in sorted(os.listdir(work)):
            p = os.path.join(work, name)
            if name == "clips" and os.path.isdir(p):
                for c in sorted(os.listdir(p)):
                    ops.append((os.path.join(p, c), os.path.join(g, "clips", c)))
            else:
                ops.append((p, os.path.join(g, name)))
    final = os.path.join(g, "final")
    if os.path.isdir(final):
        for name in sorted(os.listdir(final)):
            p = os.path.join(final, name)
            if name == "players" and os.path.isdir(p):
                ops.append((p, os.path.join(g, "reels", "players")))
            elif fnmatch.fnmatch(name, "*_full_game.mp4"):
                ops.append((p, os.path.join(g, name)))                       # the full game lives at the game root
            elif os.path.isfile(p) and match_patterns(name, FINAL_FILES):
                ops.append((p, os.path.join(g, "reels", name)))              # reels live in reels/
            else:
                ops.append((p, os.path.join(g, name)))
    return ops


def execute_untidy(ops: List[Tuple[str, str]], manifest_path: Optional[str] = None, game_name: str = "") -> Tuple[int, List[str]]:
    """Do the moves from plan_untidy. Never overwrites; empty work/ and final/ folders are removed when possible.
    Manifest entries of this game (matched by folder name) are dropped so a later --restore stays consistent."""
    moved, skipped = 0, []
    parents = set()

    def merge(src, dst):
        """Move src to dst. A folder that already exists at dst (a run after Tidy recreates empty clips/ folders)
        is merged item by item; a file or item that already exists is never overwritten, it is reported."""
        nonlocal moved
        if not os.path.exists(src):
            return
        if os.path.isdir(src) and os.path.isdir(dst):
            for name in sorted(os.listdir(src)):
                merge(os.path.join(src, name), os.path.join(dst, name))
            try:
                os.rmdir(src)                     # only succeeds when everything moved
            except OSError:
                pass
            return
        if os.path.exists(dst):
            skipped.append(dst)
            return
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        moved += 1

    for src, dst in ops:
        merge(src, dst)
        parents.add(os.path.dirname(src))
    for p in sorted(parents, key=len, reverse=True):
        for d in (p, os.path.dirname(p)):
            try:
                if os.path.basename(d) in ("work", "final", "clips") and not os.listdir(d):
                    os.rmdir(d)
            except OSError:
                pass
    if manifest_path and game_name and os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                man = json.load(f)
            keep = [m for m in man if game_name not in re.split(r"[\\/]", m[0])]
            if len(keep) != len(man):
                from .atomic_io import write_json_atomic
                write_json_atomic(manifest_path, keep, indent=1)
        except Exception:
            _swallowed()
    return moved, skipped
