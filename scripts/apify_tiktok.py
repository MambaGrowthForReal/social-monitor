"""
apify_tiktok.py — TikTok search via Apify clockworks~tiktok-scraper.

Usage (from project root):
    python scripts/apify_tiktok.py

Searches weight-loss keywords on TikTok, deduplicates against previously
saved data, then merges into data/YYYY-MM-DD.json and data/latest.json.
"""
import sys
import os
import json
import time
import urllib.request
import urllib.parse
from datetime import date, datetime

sys.stdout.reconfigure(encoding='utf-8')

# ── Load .env ────────────────────────────────────────────────────────────────
_ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
if os.path.exists(_ENV):
    with open(_ENV, encoding='utf-8') as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                os.environ.setdefault(_k.strip(), _v.strip())

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dedup

# ── Config ───────────────────────────────────────────────────────────────────
APIFY_TOKEN  = os.environ.get('APIFY_TOKEN', '')
ACTOR_ID     = 'clockworks~tiktok-scraper'
MAX_RESULTS  = 5       # videos per keyword
MIN_VIEWS    = 50_000
TODAY        = date.today()

KEYWORDS = [
    "weightloss",
    "weight loss",
    "natural recipe",
    "natural mounjaro",
    "natural ozempic",
    "morning ritual recipe",
    "lose weight",
    "burn fat",
    "pudding recipe",
    "pudding trick",
    "gelatin trick",
    "pink salt trick",
    "pink gelatin recipe",
    "pink gelatin trick",
    "pink salt recipe",
    "drop pounds",
    "belly fat",
]


# ── Apify helpers ─────────────────────────────────────────────────────────────
def _api_post(url, body):
    data = json.dumps(body).encode('utf-8')
    req  = urllib.request.Request(
        url, data=data,
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _api_get(url):
    req = urllib.request.Request(url, headers={'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def run_actor(keyword):
    """Start actor run and return dataset items for one keyword."""
    base = f'https://api.apify.com/v2/acts/{ACTOR_ID}'
    run_url = f'{base}/runs?token={APIFY_TOKEN}'

    body = {
        'hashtags':    [keyword.replace(' ', '')],
        'resultsType': 'videos',
        'maxResults':  MAX_RESULTS,
    }
    run = _api_post(run_url, body)
    run_id = run.get('data', {}).get('id', '')
    if not run_id:
        return []

    # Poll until finished
    status_url = f'https://api.apify.com/v2/actor-runs/{run_id}?token={APIFY_TOKEN}'
    for _ in range(30):
        time.sleep(10)
        status = _api_get(status_url)
        st = status.get('data', {}).get('status', '')
        if st in ('SUCCEEDED', 'FAILED', 'ABORTED', 'TIMED-OUT'):
            break

    if st != 'SUCCEEDED':
        return []

    dataset_id = status['data'].get('defaultDatasetId', '')
    items_url  = (f'https://api.apify.com/v2/datasets/{dataset_id}/items'
                  f'?token={APIFY_TOKEN}&format=json&clean=true')
    items = _api_get(items_url)
    return items if isinstance(items, list) else []


def parse_item(item, keyword):
    """Normalise a raw TikTok item into the project schema."""
    views = int(item.get('playCount') or item.get('videoMeta', {}).get('playCount') or 0)
    if views < MIN_VIEWS:
        return None

    video_id  = item.get('id', '')
    author    = item.get('authorMeta', {}).get('name', '') or item.get('author', {}).get('uniqueId', '')
    desc      = item.get('text', '') or item.get('desc', '')
    pub_ts    = item.get('createTime') or item.get('createTimeISO', '')
    thumbnail = (item.get('videoMeta', {}) or {}).get('coverUrl', '') or item.get('covers', {}).get('default', '')

    # Parse date
    pub_date = ''
    dias = 0
    try:
        if isinstance(pub_ts, (int, float)):
            pub_date = datetime.utcfromtimestamp(pub_ts).strftime('%Y-%m-%d')
        elif isinstance(pub_ts, str) and pub_ts:
            pub_date = pub_ts[:10]
        if pub_date:
            dias = (TODAY - datetime.strptime(pub_date, '%Y-%m-%d').date()).days
    except Exception:
        pass

    url = f'https://www.tiktok.com/@{author}/video/{video_id}' if video_id else ''

    return {
        'titulo':                desc[:200],
        'canal':                 author,
        'views':                 views,
        'likes':                 int(item.get('diggCount') or item.get('stats', {}).get('diggCount') or 0),
        'comentarios':           int(item.get('commentCount') or item.get('stats', {}).get('commentCount') or 0),
        'data':                  pub_date,
        'dias_desde_publicacao': dias,
        'url':                   url,
        'thumbnail':             thumbnail,
        'keyword':               keyword,
        'analise':               '',
    }


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if not APIFY_TOKEN:
        print('ERROR: APIFY_TOKEN not set. Add it to .env file.')
        sys.exit(1)

    print('── TikTok search (Apify) ───────────────────────────────────────')
    print(f'   Keywords : {len(KEYWORDS)}')
    print(f'   Min views: {MIN_VIEWS:,}')
    print()

    raw = []
    for i, kw in enumerate(KEYWORDS, 1):
        print(f'  [{i:>2}/{len(KEYWORDS)}] {kw:<30}', end=' ', flush=True)
        try:
            items = run_actor(kw)
            parsed = [parse_item(x, kw) for x in items]
            parsed = [p for p in parsed if p]
            raw.extend(parsed)
            print(f'→ {len(parsed)} videos')
        except Exception as e:
            print(f'→ ERROR: {e}')
        time.sleep(2)

    # Dedup within batch
    seen, batch = set(), []
    for v in sorted(raw, key=lambda x: x['views'], reverse=True):
        if v['url'] not in seen:
            seen.add(v['url'])
            batch.append(v)

    print(f'\n  Unique videos (≥{MIN_VIEWS:,} views): {len(batch)}')

    # Load existing data and preserve other platforms
    _latest = os.path.join(dedup.DATA_DIR, 'latest.json')
    _existing = {}
    try:
        with open(_latest, encoding='utf-8') as f:
            _existing = json.load(f)
    except Exception:
        pass

    payload = {
        'data_execucao': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'youtube':  _existing.get('youtube',  []),
        'tiktok':   batch,
        'facebook': _existing.get('facebook', []),
        'trends':   _existing.get('trends',   []),
        'analise':  _existing.get('analise',  {
            'tendencias':         '',
            'mecanismos_em_alta': '',
            'avatares_em_alta':   '',
            'recomendacoes':      '',
        }),
    }

    dedup.save(payload, verbose=True)

    if batch:
        print('\n── Results ─────────────────────────────────────────────────────')
        print(f'  {"Views":>9}  {"Title":<50}  {"Days":>4}  Keyword')
        print(f'  {"-"*9}  {"-"*50}  {"-"*4}  {"-"*20}')
        for v in batch:
            print(f'  {v["views"]:>9,}  {v["titulo"][:50]:<50}  {v["dias_desde_publicacao"]:>4}d  {v["keyword"]}')
    else:
        print('\n  No videos passed all filters.')
