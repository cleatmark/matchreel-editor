#!/usr/bin/env python3
"""Push / pull a game's review tab to the season Google Sheet. Needs: pip install gspread
and the service-account key in shared\\secrets\\*.json (the workbook must be shared with that account as Editor).

  sheet_sync.py tabs
  sheet_sync.py push --day 03-29-26                 # out\\2026-03-29\\review.csv -> NEW tab "03/29/26 League A"
  sheet_sync.py push --day 03-29-26 --tab "03/29/26 League A G1" --gs -g1
  sheet_sync.py pull --day 03-29-26                 # tab -> out\\2026-03-29\\tab.csv   (feed to sync_game.py --csv)
  sheet_sync.py clip --day 03-29-26                 # out\\2026-03-29\\clip_column.json -> column P of the tab
  sheet_sync.py fit  --day 03-29-26                 # auto-fit the column widths of the tab (push does this too)
"""
import argparse
import csv
import json
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from xbotgo_core.sheet_sync_service import (
    ROOT,
    DEFAULT_SHEET_ID,
    TEXT_RANGES,
    INT_COLS,
    get_configured_sheet_id,
    get_service_account_client,
    fit_columns,
    list_tabs,
    pull_from_google_sheet,
    push_clip_column,
    rename_google_sheet_tab,
)

SHEET_ID = get_configured_sheet_id()

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('cmd', choices=['tabs', 'push', 'pull', 'clip', 'fit', 'update', 'rename'])
ap.add_argument('--day', help='dump folder MM-DD-YY')
ap.add_argument('--gs', default='', help='out folder suffix for two-game days, e.g. -g1')
ap.add_argument('--tab', help='tab name; default "MM/DD/YY <league>"')
ap.add_argument('--new-tab', help='new tab name for rename command')
ap.add_argument('--csv', help='push: csv to upload (default out\\<date><gs>\\review.csv)')
ap.add_argument('--out', help='pull: csv to write (default out\\<date><gs>\\tab.csv)')
ap.add_argument('--key', help='service-account json (default: first shared\\secrets\\*.json)')
ap.add_argument('--sheet', default=SHEET_ID)
a = ap.parse_args()


def die(m):
    sys.exit('sheet_sync: ' + m)


def date_of(day):
    mm, dd, yy = day.split('-')
    return f'20{yy}-{mm}-{dd}', f'{mm}/{dd}/{yy}'


def paths():
    if not a.day:
        die('--day MM-DD-YY is required')
    iso, us = date_of(a.day)
    od = os.path.join(ROOT, 'out', iso + a.gs)
    from xbotgo_core import app_config
    league = app_config.load()['league']
    try:
        gi = json.load(open(os.path.join(od, 'game_info.json'), encoding="utf-8"))
        league = (gi.get('league') or '').strip() or league
    except Exception:
        pass
    return od, a.tab or f'{us} {league}'


def connect():
    try:
        client, target_sheet = get_service_account_client(key_path=a.key, sheet_id=a.sheet)
        return client.open_by_key(target_sheet)
    except Exception as e:
        die(f'cannot open the workbook ({type(e).__name__}: {e}). Is it shared with the service-account email as Editor?')


sh = connect()

if a.cmd == 'tabs':
    for wid, title in list_tabs(sheet_key=a.sheet):
        print(f'{wid:>12}  {title}')
    sys.exit(0)

od, tab = paths()

if a.cmd == 'push':
    src = a.csv or os.path.join(od, 'review.csv')
    if not os.path.exists(src):
        die('no csv: ' + src)
    rows = list(csv.reader(open(src, newline='', encoding='utf-8')))
    hdr, body = rows[0], rows[1:]
    if tab in [w.title for w in sh.worksheets()]:
        die(f'tab "{tab}" already exists - not touching it (use --tab for another name)')
    ws = sh.add_worksheet(title=tab, rows=max(1000, len(rows) + 50), cols=max(16, len(hdr)))

    def text_format():
        reqs = [{
            'repeatCell': {
                'range': {
                    'sheetId': ws.id,
                    'startRowIndex': 1,
                    'endRowIndex': 999,
                    'startColumnIndex': ord(r.split(':')[0]) - 65,
                    'endColumnIndex': ord(r.split(':')[-1]) - 64
                },
                'cell': {'userEnteredFormat': {'numberFormat': {'type': 'TEXT'}}},
                'fields': 'userEnteredFormat.numberFormat'
            }
        } for r in TEXT_RANGES]
        sh.batch_update({'requests': reqs})

    text_format()
    out = [hdr]
    for r in body:
        r = r + [''] * (len(hdr) - len(r))
        out.append([int(float(v)) if hdr[i] in INT_COLS and v not in ('', None) else v for i, v in enumerate(r)])
    ws.update(values=out, range_name='A1', value_input_option='RAW')
    text_format()
    ws.freeze(rows=1)
    fit_columns(sh, ws.id, len(hdr))
    back = ws.get_all_values()
    bad = [(i + 2, j) for i, r in enumerate(back[1:]) for j in (5, 7, 8, 10, 11, 12) if j < len(r) and r[j].startswith("'")]
    print(f'pushed {len(body)} rows to tab "{tab}"; read-back rows {len(back) - 1}; apostrophe cells {len(bad)}')
    print('open:', f'https://docs.google.com/spreadsheets/d/{a.sheet}/edit#gid={ws.id}')

elif a.cmd == 'pull':
    dst = a.out or os.path.join(od, 'tab.csv')
    try:
        cnt = pull_from_google_sheet(tab, dst, sheet_key=a.sheet)
        print(f'pulled tab "{tab}": {cnt - 1} rows -> {dst}')
        print(f'next: python tools\\pipeline\\sync_game.py --out {os.path.relpath(od, ROOT)} --csv {os.path.relpath(dst, ROOT)}')
    except Exception as e:
        die(str(e))

elif a.cmd == 'clip':
    f = os.path.join(od, 'clip_column.json')
    try:
        cnt = push_clip_column(tab, f, sheet_key=a.sheet)
        print(f'wrote {cnt} rows to column P of "{tab}"')
    except Exception as e:
        die(str(e))

elif a.cmd == 'fit':
    try:
        ws = sh.worksheet(tab)
        fit_columns(sh, ws.id)
        print(f'auto-fitted columns A-P of "{tab}"')
    except Exception as e:
        die(str(e))

elif a.cmd == 'rename':
    if not a.new_tab:
        die('--new-tab is required for rename')
    ok = rename_google_sheet_tab(tab, a.new_tab, sheet_key=a.sheet)
    if ok:
        print(f'renamed tab "{tab}" -> "{a.new_tab}"')
    else:
        die(f'could not rename tab "{tab}" -> "{a.new_tab}"')
