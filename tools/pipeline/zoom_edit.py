#!/usr/bin/env python3
"""Zoom replays driven by a state file (out/<game>/zoom_state.json): plan, crop, edit, render, list.

  python3 tools/pipeline/zoom_edit.py plan   --out out/2026-03-14-g1            # add every `zoom` row, default windows
  python3 tools/pipeline/zoom_edit.py set 3  --out ... --tile 360,135            # crop from a tile position (or --crop x,y)
  python3 tools/pipeline/zoom_edit.py edit 7 --out ... --trim-end 4 --start-earlier 1
  python3 tools/pipeline/zoom_edit.py render --out ... [--budget 70] [--only 3,5] [--height 720]
  python3 tools/pipeline/zoom_edit.py list   --out ...
  python3 tools/pipeline/zoom_edit.py adopt  --out ... --json zoom_adopt.json    # register replays rendered before this tool existed

Numbers are CLIP numbers (the sheet's `clip` column). Units follow how the user talks:
  --trim-end / --trim-start     replay (slowed) seconds        (0.5x: 2 replay s = 1 s of play)
  --start-earlier / --start-later / --end-later   real (source) seconds
Trims never re-render: every replay keeps an untrimmed master in clips/extra/master and the visible clip is cut from it.
Only a new window start, a longer window or a new crop re-renders (new work folder every time - no stale parts).
Replaced files move to clips/extra/vN (never deleted). Default window: event-2.5 .. event+2.0 (4.5 s), action_end wins.
"""
import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
from xbotgo_core import xb_env  # helper programs in utils\ on PATH
import argparse, hashlib, json, os, shutil, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xbotgo_core.xbl import Game, sh, probe_dur, is_zoom, default_window, move_aside, PY
from xbotgo_core.zoom_state import (
    CROP_W,
    lab,
    jobs_by_clip,
    names,
    sig,
    parse_crop as parse_crop_core,
    apply_zoom_spec_to_state,
)


def parse_crop(a):
    return parse_crop_core(crop_str=getattr(a, "crop", None), tile_str=getattr(a, "tile", None))



def finalize(g, st, tok, height, log=print):
    r = st["replays"][tok]
    master, final = names(g, r, tok, height)
    if not os.path.exists(master) or r.get("master_key") != sig(r, height):
        return False
    m = probe_dur(master)
    out_len = m - r["cut_start"] - r["cut_end"]
    if out_len < 1.0:
        sys.exit(f"clip {r['n']}: trims leave {out_len:.1f}s - too short (master is {m:.1f}s)")
    fkey = f"{r['master_key']}|{r['cut_start']}|{r['cut_end']}" + (f"|hold{r['hold_end']}" if r.get("hold_end") else "")
    if os.path.exists(final) and r.get("final_key") == fkey:
        return True
    if os.path.exists(final):
        k = len(r["history"]) + 1
        move_aside(final, os.path.join(g.extra, f"v{k}"))
    if r["cut_start"] == 0 and r["cut_end"] == 0:
        shutil.copy(master, final)
    else:
        sh(["ffmpeg", "-v", "error", "-y", "-ss", f"{r['cut_start']:.3f}", "-i", master, "-t", f"{out_len:.3f}",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", final])
    if r.get("hold_end"):                                   # freeze the last frame (and pad the audio) for N s
        h = float(r["hold_end"]); tmp = final + ".hold.mp4"
        sh(["ffmpeg", "-v", "error", "-y", "-i", final, "-vf", f"tpad=stop_mode=clone:stop_duration={h}",
            "-af", f"apad=pad_dur={h}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-t", f"{out_len + h:.3f}", tmp])
        os.replace(tmp, final); out_len += h
    r["final_key"] = fkey
    r["history"].append({"t": time.strftime("%F %T"), "window": [r["start"], r["dur"]], "crop": r["crop"],
                         "cut": [r["cut_start"], r["cut_end"]], "len": round(out_len, 2)})
    g.save_state(st)
    log(f"  clip {r['n']} {tok}: {os.path.basename(final)}  {out_len:.2f}s")
    return True


def render_master(g, st, tok, height, log=print):
    r = st["replays"][tok]
    master, _ = names(g, r, tok, height)
    key = sig(r, height)
    work = os.path.join(xb_env.tmp_for(g.out), "zw", f"{tok}_{hashlib.md5(key.encode()).hexdigest()[:8]}")
    os.makedirs(work, exist_ok=True); os.makedirs(os.path.dirname(master), exist_ok=True)
    base = [PY, os.path.join("tools", "pipeline", "zoom_clip.py"), "--src", r["path"], "--start", str(r["start"]), "--dur", str(r["dur"]),
            "--ref", str(r["event"]), "--crop", f"{r['crop'][0]},{r['crop'][1]},{r.get('crop_w', CROP_W)}", "--ease", "0.6",
            "--height", str(height), "--work", os.path.abspath(work)]
    if r.get("zoom_to"):
        base += ["--zoom-to", ",".join(str(v) for v in r["zoom_to"])]
    if r.get("pan"):
        pk = r["pan"] if isinstance(r["pan"][0], list) else [r["pan"]]
        base += ["--pan=" + ";".join(",".join(str(v) for v in k) for k in pk)]   # "--pan=" form: negative x must not look like a flag
    if not os.path.exists(os.path.join(work, "H.json")):
        sh(base + ["--step", "h"])
    for k in (1, 2):
        sh(base + ["--step", "render", "--part", f"{k}/2"])
    if os.path.exists(master):
        move_aside(master, os.path.join(g.extra, "master", "old"))
    res = sh(base + ["--step", "mux", "--out", os.path.abspath(master)])
    d = probe_dur(master)
    if d is None or abs(d - 2 * r["dur"]) > 0.3:
        sys.exit(f"clip {r['n']}: render failed or wrong length ({d} vs {2*r['dur']}): {res.stdout[-200:]} {res.stderr[-300:]}")
    r["master_key"] = key
    g.save_state(st)
    log(f"  rendered master clip {r['n']} {tok}: {d:.2f}s")


def cmd_render(g, a, only=None):
    st = g.state(); js_n, js_t = jobs_by_clip(g)
    t0 = time.time(); did = 0; waiting = []
    replays_to_render = [
        (tok, r) for tok, r in sorted(st["replays"].items(), key=lambda kv: kv[1]["n"])
        if not only or r["n"] in only
    ]
    total_count = len(replays_to_render)
    print(f"[render] Starting render pass: {total_count} replays in queue", flush=True)

    for idx, (tok, r) in enumerate(replays_to_render, 1):
        if r["crop"] is None:
            waiting.append(f"clip {r['n']} {tok}: no crop yet"); continue
        if r["start"] is None:
            j = js_t[tok]; r["start"], r["dur"] = default_window(r["event"], g.action_end(j))
        master, final = names(g, r, tok, a.height)
        needs_render = not os.path.exists(master) or r.get("master_key") != sig(r, a.height) or a.force
        if needs_render:
            if time.time() - t0 > a.budget:
                print("budget reached - run again", flush=True); g.save_state(st); return False
            print(f"[render] [{idx}/{total_count}] Rendering clip {r['n']} ({tok}) at {a.height}p...", flush=True)
            render_master(g, st, tok, a.height)
            did += 1
            print(f"[render] [{idx}/{total_count}] Finished master for clip {r['n']} ({tok})", flush=True)
        else:
            print(f"[render] [{idx}/{total_count}] Clip {r['n']} ({tok}) up to date", flush=True)
        finalize(g, st, tok, a.height)
        print(f"[render] [{idx}/{total_count}] Replay {r['n']} ready", flush=True)

    g.save_state(st)
    for w in waiting:
        print("  waiting:", w, flush=True)
    print(f"pass done ({did} rendered, {time.time()-t0:.0f}s)", flush=True)
    return True


def cmd_edit(g, a):
    st = g.state(); js_n, js_t = jobs_by_clip(g)
    if a.n not in js_n:
        sys.exit(f"no clip {a.n}")
    tok = g.token(js_n[a.n]); r = st["replays"].get(tok)
    if r is None:
        sys.exit(f"clip {a.n} has no replay (is `zoom` in the sheet? run plan)")
    if r["start"] is None:
        r["start"], r["dur"] = default_window(r["event"], g.action_end(js_n[a.n]))
    before = (r["start"], r["dur"], r["cut_start"], r["cut_end"], r["crop"])
    if a.reset_cuts:
        r["cut_start"] = r["cut_end"] = 0.0
    if a.trim_end:
        r["cut_end"] += a.trim_end
    if a.trim_start:
        r["cut_start"] += a.trim_start
    if a.start_later:                                    # real seconds -> replay seconds, no re-render
        r["cut_start"] += 2 * a.start_later
    if a.start_earlier:                                  # needs the window to grow at the front
        r["start"] = round(r["start"] - a.start_earlier, 3); r["dur"] = round(r["dur"] + a.start_earlier, 3)
        if r["start"] < 0:
            r["dur"] = round(r["dur"] + r["start"], 3); r["start"] = 0.0
    if a.end_later:
        take = min(r["cut_end"], 2 * a.end_later); r["cut_end"] -= take
        extra = a.end_later - take / 2
        if extra > 0:
            r["dur"] = round(r["dur"] + extra, 3)
    if a.window:
        s, d = map(float, a.window.split(",")); r["start"], r["dur"] = s, d
    if a.crop or a.tile:
        r["crop"] = parse_crop(a)
    if a.pan:
        if a.pan == "off": r.pop("pan", None)
        else:                                                         # x,y,at (master replay seconds); several: x,y,at;x,y,at
            ks = [[float(v) for v in k.split(",")] for k in a.pan.split(";")]
            r["pan"] = ks[0] if len(ks) == 1 else ks
    if a.zoom is not None:                                  # overall zoom, e.g. 2.5 (3 = default)
        if abs(a.zoom - 3) < 1e-6: r.pop("crop_w", None)
        else: r["crop_w"] = int(round(3840 / a.zoom))
    if a.hold_end is not None:
        if a.hold_end > 0: r["hold_end"] = a.hold_end
        else: r.pop("hold_end", None)
    if a.zoom_to:
        if a.zoom_to == "off": r.pop("zoom_to", None)
        else: r["zoom_to"] = [float(v) for v in a.zoom_to.split(",")]
    g.save_state(st)
    print(f"clip {a.n} {tok}: window {r['start']}+{r['dur']}s cut(start {r['cut_start']}, end {r['cut_end']}) replay s, crop {r['crop']}")
    if r["crop"] is None:
        print("  no crop yet - use `set`"); return
    master, _ = names(g, r, tok, a.height)
    if not os.path.exists(master) or r.get("master_key") != sig(r, a.height):
        print("  re-rendering master (~1 min)...")
        render_master(g, st, tok, a.height)
    finalize(g, st, tok, a.height)


def parse_crop(a):
    return parse_crop_core(crop_str=getattr(a, "crop", None), tile_str=getattr(a, "tile", None))


def cmd_set(g, a):
    st = g.state(); js_n, js_t = jobs_by_clip(g)
    tok = g.token(js_n[a.n]); r = st["replays"].get(tok)
    if r is None:
        sys.exit("run `plan` first")
    r["crop"] = parse_crop(a)
    g.save_state(st); print(f"clip {a.n} {tok}: crop {r['crop']}")


def cmd_plan(g, a):
    st = g.state(); js_n, js_t = jobs_by_clip(g)
    for tok, j in sorted(js_t.items(), key=lambda kv: kv[1]["n"]):
        if not is_zoom(j["row"]):
            continue
        s, d = default_window(j["event"], g.action_end(j))
        r = st["replays"].setdefault(tok, {"n": j["n"], "event": j["event"], "file": j["file"], "path": j["path"],
                                           "crop": None, "start": s, "dur": d, "cut_start": 0.0, "cut_end": 0.0,
                                           "master_key": None, "final_key": None, "history": []})
        r["n"] = j["n"]
        if r["start"] is None:
            r["start"], r["dur"] = s, d
    g.save_state(st); cmd_list(g, a)


def cmd_list(g, a):
    st = g.state(); js_n, js_t = jobs_by_clip(g)
    print(f"{'clip':>4} {'token':<12}{'event':>7} {'window':>14} {'cut s/e':>9} {'crop':>11} {'len':>6}  status")
    for tok, r in sorted(st["replays"].items(), key=lambda kv: kv[1]["n"]):
        master, final = names(g, r, tok, a.height)
        L = probe_dur(final) if os.path.exists(final) else None
        if r["crop"] is None: status = "needs crop"
        elif not os.path.exists(master) or r.get("master_key") != sig(r, a.height): status = "needs render"
        elif not os.path.exists(final) or r.get("final_key") != f"{r['master_key']}|{r['cut_start']}|{r['cut_end']}": status = "needs cut"
        else: status = "ok"
        win = f"{r['start']}+{r['dur']}" if r["start"] is not None else "-"
        print(f"{r['n']:>4} {tok:<12}{r['event']:>7} {win:>14} {r['cut_start']:>4.1f}/{r['cut_end']:<4.1f} "
              f"{str(r['crop'] or '-'):>11} {('%.1f' % L) if L else '-':>6}  {status}")


def cmd_adopt(g, a):
    """Register replays rendered before this tool: json {"<token>": {"crop":[x,y], "start":s, "dur":d}} ; the
    existing final becomes the master (so trims keep working without a re-render)."""
    st = g.state(); js_n, js_t = jobs_by_clip(g)
    data = json.load(open(a.json, encoding="utf-8"))
    for tok, p in data.items():
        j = js_t.get(tok)
        if j is None:
            print("  skip (no such clip):", tok); continue
        _, final = names(g, {"n": j["n"]}, tok, a.height)
        master, _ = names(g, {"n": j["n"]}, tok, a.height)
        if not os.path.exists(final):
            print("  no file for", tok, final); continue
        os.makedirs(os.path.dirname(master), exist_ok=True)
        shutil.copy(final, master)
        r = {"n": j["n"], "event": j["event"], "file": j["file"], "path": j["path"], "crop": p["crop"],
             "start": p["start"], "dur": p["dur"], "cut_start": 0.0, "cut_end": 0.0, "history": []}
        r["master_key"] = sig(r, a.height); r["final_key"] = f"{r['master_key']}|0.0|0.0"
        st["replays"][tok] = r
        print(f"  adopted clip {j['n']} {tok}")
    g.save_state(st)


def cmd_apply(g, a):
    """Single-pass atomic apply of a JSON replay specification to zoom_state.json."""
    if not a.spec or not os.path.exists(a.spec):
        sys.exit(f"spec file not found: {a.spec}")
    with open(a.spec, "r", encoding="utf-8") as f:
        spec = json.load(f)

    target = a.n or spec.get("clip")
    try:
        tok, r, is_changed = apply_zoom_spec_to_state(g, spec, token_or_target=target)
    except Exception as e:
        sys.exit(str(e))

    st = g.state()
    if is_changed:
        print(f"clip {r['n']} {tok}: applied spec, window {r['start']}+{r['dur']}s, crop {r['crop']}")
    else:
        print(f"clip {r['n']} {tok}: spec unchanged (no-op)")

    if getattr(a, "render", False):
        master, _ = names(g, r, tok, a.height)
        if not os.path.exists(master) or r.get("master_key") != sig(r, a.height) or getattr(a, "force", False):
            print("  rendering master...")
            render_master(g, st, tok, a.height)
        finalize(g, st, tok, a.height)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "set", "edit", "render", "list", "adopt", "apply"])
    ap.add_argument("n", nargs="?", type=str, help="clip number or token (set / edit / apply)")
    ap.add_argument("clip_or_tok", nargs="?", type=str, help="optional clip number if first arg was game")
    ap.add_argument("--out")
    ap.add_argument("--spec", help="path to JSON spec file for apply")
    ap.add_argument("--render", action="store_true", help="render master and final immediately")
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--budget", type=float, default=70)
    ap.add_argument("--only"); ap.add_argument("--force", action="store_true")
    ap.add_argument("--crop"); ap.add_argument("--tile"); ap.add_argument("--window")
    ap.add_argument("--trim-end", type=float, default=0); ap.add_argument("--trim-start", type=float, default=0)
    ap.add_argument("--start-earlier", type=float, default=0); ap.add_argument("--start-later", type=float, default=0)
    ap.add_argument("--end-later", type=float, default=0); ap.add_argument("--reset-cuts", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--zoom", type=float, help="overall zoom factor for this replay (default 3; 2.5 = wider)")
    ap.add_argument("--hold-end", type=float, help="freeze the final frame for N seconds (0 clears)")
    ap.add_argument("--zoom-to", help="w,at  ease crop width to w (768 = 5x) from master-replay second `at` to the end; `off` clears")
    ap.add_argument("--pan", help="x,y,at  glide the crop to x,y (4K ref px) at master-replay second `at` and hold; `off` clears")
    a = ap.parse_args()

    # Handle flexible CLI forms:
    # 1. apply <game> <clip> --spec ...
    # 2. apply <clip> --out <game> --spec ...
    if not a.out and a.clip_or_tok:
        out_cand = a.n if (a.n.startswith("out/") or a.n.startswith("out\\")) else os.path.join("out", a.n)
        a.out = out_cand
        a.n = a.clip_or_tok
    elif not a.out:
        sys.exit("need --out")

    g = Game(a.out)
    if a.n and a.n.isdigit() and a.cmd in ("set", "edit"):
        a.n = int(a.n)

    if a.cmd == "plan": cmd_plan(g, a)
    elif a.cmd == "set": cmd_set(g, a)
    elif a.cmd == "edit": cmd_edit(g, a)
    elif a.cmd == "list": cmd_list(g, a)
    elif a.cmd == "adopt": cmd_adopt(g, a)
    elif a.cmd == "apply": cmd_apply(g, a)
    else:
        cmd_render(g, a, {int(x) for x in a.only.split(",")} if a.only else None)
