"""
dedup.py — URL deduplication and data-saving utilities for social-monitor.

Rules:
  - An item is a DUPLICATE if its exact URL already exists in any
    previously saved dated file (data/YYYY-MM-DD.json).
  - Same content on a different channel/account is NOT a duplicate
    (URLs differ → both are kept).
  - When re-running on the SAME day, today's file is excluded from the
    duplicate check so the run fully replaces that day's data.
"""
import json
import os
import glob
from datetime import date as _date

# ── Paths ──────────────────────────────────────────────────────────────────
_HERE    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.normpath(os.path.join(_HERE, '..', 'data'))

PLATFORMS = ['youtube', 'tiktok', 'facebook']


# ── Core helpers ────────────────────────────────────────────────────────────

def _dated_files():
    """Return all data/YYYY-MM-DD.json paths sorted newest first."""
    paths = glob.glob(os.path.join(DATA_DIR, '????-??-??.json'))
    return sorted(paths, reverse=True)


def load_existing_urls(exclude_date=None):
    """
    Return a set of every URL found across all dated JSON files,
    optionally skipping the file for *exclude_date* (e.g. today's date
    when doing a fresh same-day run).

    Parameters
    ----------
    exclude_date : str | None
        ISO date string 'YYYY-MM-DD' of the file to skip.
    """
    urls = set()
    for path in _dated_files():
        this_date = os.path.basename(path).replace('.json', '')
        if exclude_date and this_date == exclude_date:
            continue
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            for plat in PLATFORMS:
                for item in data.get(plat, []):
                    url = item.get('url', '').strip()
                    if url:
                        urls.add(url)
        except Exception:
            pass
    return urls


def deduplicate(new_items, existing_urls):
    """
    Split *new_items* into (kept, removed).

    An item is removed only when its 'url' field exactly matches a URL
    already present in *existing_urls*.  Items with no URL are kept.
    """
    kept, removed = [], []
    for item in new_items:
        url = item.get('url', '').strip()
        if url and url in existing_urls:
            removed.append(item)
        else:
            kept.append(item)
    return kept, removed


# ── History management ──────────────────────────────────────────────────────

def _history_path():
    return os.path.join(DATA_DIR, 'history.json')


def load_history():
    try:
        with open(_history_path(), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {'dates': []}


def update_history(date_str):
    """Append *date_str* to history.json (no-op if already present)."""
    history = load_history()
    dates   = history.get('dates', [])
    if date_str not in dates:
        dates.append(date_str)
        dates.sort(reverse=True)
        history['dates'] = dates
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(_history_path(), 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    return history['dates']


# ── Main save function ───────────────────────────────────────────────────────

def save(data, date_str=None, verbose=True):
    """
    Deduplicate *data* against all previously saved files, then write:
      • data/<date_str>.json   — dated snapshot
      • data/latest.json       — always overwritten with latest run
      • data/history.json      — date appended if new

    Parameters
    ----------
    data : dict
        Output payload with keys youtube / tiktok / facebook / trends / analise.
    date_str : str | None
        ISO date 'YYYY-MM-DD'; defaults to today.
    verbose : bool
        Print dedup summary to stdout.

    Returns
    -------
    dict with keys: date, kept, removed, platforms, paths, history
    """
    if date_str is None:
        date_str = _date.today().isoformat()

    os.makedirs(DATA_DIR, exist_ok=True)

    # Load URLs from all OTHER days (same-day re-run replaces, not dedupes)
    existing_urls = load_existing_urls(exclude_date=date_str)

    stats = {
        'date':      date_str,
        'kept':      0,
        'removed':   0,
        'platforms': {},
    }

    if verbose:
        print(f'\n── Deduplication ({date_str}) ──────────────────────────────')
        print(f'   Known URLs from previous runs: {len(existing_urls)}')

    for plat in PLATFORMS:
        if plat not in data:
            continue
        kept, removed = deduplicate(data[plat], existing_urls)
        data[plat] = kept

        stats['kept']    += len(kept)
        stats['removed'] += len(removed)
        stats['platforms'][plat] = {'kept': len(kept), 'removed': len(removed)}

        if verbose:
            if removed:
                print(f'   [{plat}] {len(kept)} kept, {len(removed)} duplicate(s) removed:')
                for r in removed:
                    label = r.get('titulo') or r.get('page') or r.get('url', '?')
                    print(f'     ✗ {str(label)[:70]}')
            else:
                print(f'   [{plat}] {len(kept)} items — no duplicates found')

    # ── Save files ──
    dated_path  = os.path.join(DATA_DIR, f'{date_str}.json')
    latest_path = os.path.join(DATA_DIR, 'latest.json')

    for path in (dated_path, latest_path):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    dates = update_history(date_str)

    stats['paths']   = [dated_path, latest_path]
    stats['history'] = dates

    if verbose:
        print(f'\n✅ Saved → {os.path.basename(dated_path)} + latest.json')
        print(f'   Kept: {stats["kept"]}  |  Removed: {stats["removed"]}')
        print(f'   History: {dates}')

    return stats


# ── CLI: run standalone to re-process existing files ─────────────────────────

if __name__ == '__main__':
    import sys

    print('social-monitor — dedup utility')
    print(f'DATA_DIR = {DATA_DIR}')
    print()

    files = _dated_files()
    if not files:
        print('No dated JSON files found.')
        sys.exit(0)

    print(f'Dated files found: {len(files)}')
    for p in files:
        print(f'  {os.path.basename(p)}')

    history = load_history()
    print(f'\nhistory.json dates: {history.get("dates", [])}')

    # Show URL counts per file
    print('\nURL counts per file:')
    for p in files:
        try:
            with open(p, encoding='utf-8') as f:
                d = json.load(f)
            total = sum(len(d.get(pl, [])) for pl in PLATFORMS)
            print(f'  {os.path.basename(p)}: {total} items')
        except Exception as e:
            print(f'  {os.path.basename(p)}: ERROR — {e}')
