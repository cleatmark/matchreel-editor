#!/usr/bin/env python3
"""Re-capture the 8 user-guide screenshots from the RUNNING editor, depersonalized.

  capture_guide_screenshots.bat                      (Windows; or)
  python tools/editor/capture_guide_screenshots.py [--base http://127.0.0.1:5000] [--game 2026-03-29]

Needs:  pip install playwright   (no browser download: it drives the installed Edge/Chrome; falls back to Playwright's Chromium)
The editor must be running with the game loaded. Writes tools/editor/static/guide/images/*.png, bumps the ?v= cache buster in
guide.html and copies guide.html over app_design/USER_GUIDE.html (the byte-identical mirror, see TestGuideMirror).
Depersonalization: video blurred (faces, numbers, banners unreadable), team/opponent names replaced by fictional ones,
roster names replaced by "Player N". Nothing is written to the game, sheet or CSV; the page is only restyled in the browser.
"""
import argparse, json, os, re, shutil, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
IMG = os.path.join(HERE, "static", "guide", "images")
GUIDE = os.path.join(HERE, "static", "guide.html")
MIRROR = os.path.join(ROOT, "app_design", "USER_GUIDE.html")
FAKE_HOME, FAKE_AWAY = "Apex Rovers", "Metro Stars"

BLUR_JS = """() => { document.querySelectorAll('video, #mainVideo').forEach(v => { v.style.filter = 'blur(16px)'; }); }"""
# replace real names in text nodes, input values, option labels, page title and the video file name label
SCRUB_JS = """(pairs) => {
  const esc = s => s.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
  const map = pairs.filter(p => p[0]).map(([real, fake]) => [new RegExp('\\\\b' + esc(real) + '\\\\b', 'gi'), fake]);
  const fix = s => map.reduce((t, [re, to]) => t.replace(re, to), s);
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n; while ((n = w.nextNode())) { const t = fix(n.nodeValue); if (t !== n.nodeValue) n.nodeValue = t; }
  document.querySelectorAll('input, textarea').forEach(i => { if (i.type === 'text' && i.value) { const t = fix(i.value); if (t !== i.value) i.value = t; } });
  document.querySelectorAll('option').forEach(o => { o.textContent = fix(o.textContent); });
  document.querySelectorAll('[id*=ideoName], [id*=ileName], .player-filename, .video-filename').forEach(e => { e.textContent = '2026-03-29-match-video.mp4'; });
}"""
ROSTER_JS = """() => {
  let k = 0;
  document.querySelectorAll('#rosterEditorTableBody tr, #rosterTableBody tr').forEach(tr => {
    k += 1;
    const set = (sel, val) => tr.querySelectorAll(sel).forEach(c => { c.value = val; });
    set('.roster-input-name', 'Player ' + k); set('.roster-input-short', 'P' + k); set('.roster-input-contact', 'parent' + k + '@example.com');
  });
}"""


def jget(url):
    return json.load(urllib.request.urlopen(url, timeout=20))


def scrub_pairs(a):
    """[real, fake] pairs built at run time from the running editor's own config + game (no names live in this file)."""
    pairs = []
    try:
        d = jget(f"{a.base}/api/defaults")
        pairs.append([d.get("team_name"), FAKE_HOME])
        pairs += [[lg.get("name"), "LEAGUE"] for lg in d.get("leagues", [])]
        gi = jget(f"{a.base}/api/game/{a.game}/info").get("game_info", {})
        pairs += [[gi.get("home"), FAKE_HOME], [gi.get("opponent"), FAKE_AWAY]]
    except Exception as e:
        print("  scrub list incomplete:", e)
    return pairs


def launch(p):
    for kw in ({"channel": "msedge"}, {"channel": "chrome"}, {}):
        try:
            return p.chromium.launch(headless=True, **kw)
        except Exception as e:                       # try the next browser
            print("  browser", kw or "playwright-chromium", "unavailable:", str(e).splitlines()[0][:90])
    sys.exit("No browser could be started. Install Edge/Chrome or run: python -m playwright install chromium")


def shot(page, name, selector=None, pad=0):
    dst = os.path.join(IMG, name)
    if selector:
        page.locator(selector).first.screenshot(path=dst)
    else:
        page.screenshot(path=dst)
    print("  wrote", os.path.relpath(dst, ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:5000")
    ap.add_argument("--game", default="2026-03-29")
    a = ap.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Missing playwright: run  pip install playwright")
    try:
        zoom = jget(f"{a.base}/api/zoom/{a.game}")
    except Exception as e:
        sys.exit(f"Editor not reachable at {a.base} ({e}). Start review_editor.bat first.")
    reps = [r for r in zoom.get("replays", []) if r.get("crop")]
    if not reps:
        sys.exit("This game has no placed zoom replays to photograph; pick a game with zoom work (--game).")
    rep = reps[0]
    os.makedirs(IMG, exist_ok=True)
    with sync_playwright() as p:
        br = launch(p)
        pg = br.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1).new_page()
        # ---- review page
        pg.goto(f"{a.base}/?game={a.game}"); pg.wait_for_selector("#timesTableBody tr"); time.sleep(2)
        pg.evaluate("() => { const v=document.getElementById('mainVideo'); if (v && v.readyState>0) v.currentTime = Math.max(0, v.currentTime); }")
        pg.evaluate(BLUR_JS); pg.evaluate(SCRUB_JS, scrub_pairs(a))
        shot(pg, "review_main.png")
        shot(pg, "review_table_detail.png", "#timesPanel")
        shot(pg, "review_timeline_detail.png", "#timelineContainer")
        pg.evaluate("() => window.openRosterModal && window.openRosterModal()"); time.sleep(1.5)
        pg.evaluate(ROSTER_JS)
        shot(pg, "roster_modal_detail.png", "#rosterModal .modal-dialog, #rosterModal > div")
        # ---- zoom page
        pg.goto(f"{a.base}/zoom/{a.game}/{rep['token']}"); time.sleep(3.5)
        pg.evaluate(BLUR_JS); pg.evaluate(SCRUB_JS, scrub_pairs(a))
        shot(pg, "zoom_main.png")
        shot(pg, "zoom_stage_detail.png", "#videoStageContainer")
        shot(pg, "zoom_inspector_detail.png", ".inspector-col")
        shot(pg, "zoom_actions_detail.png", ".zoom-bottom-bar")
        br.close()
    # cache buster + mirror
    g = open(GUIDE, encoding="utf-8").read()
    v = time.strftime("%Y%m%d%H%M")
    g2 = re.sub(r"(guide/images/[A-Za-z0-9_.-]+\.png)(\?v=[0-9A-Za-z.]*)?", lambda m: m.group(1) + "?v=" + v, g)
    open(GUIDE, "w", encoding="utf-8", newline="").write(g2)
    shutil.copyfile(GUIDE, MIRROR)
    print(f"Done. Cache buster ?v={v}; app_design\\USER_GUIDE.html refreshed. Open guide.html and check the 8 figures.")


if __name__ == "__main__":
    main()
