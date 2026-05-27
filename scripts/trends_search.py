"""
trends_search.py — Google Trends search via pytrends.

Usage (from project root):
    python scripts/trends_search.py

Fetches interest-over-time for weight-loss keywords (GB region, 7-day window),
applies tiered threshold filter, then merges into data/YYYY-MM-DD.json and
data/latest.json while preserving all other platform data.
"""
import sys
import os
import json
import time
sys.stdout.reconfigure(encoding='utf-8')

from pytrends.request import TrendReq
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dedup

# ── Config ───────────────────────────────────────────────────────────────────
GEO       = 'GB'
TIMEFRAME = 'now 7-d'
DELAY_KW  = 4      # seconds between keywords
DELAY_BATCH = 60   # seconds between batches

BATCHES = [
    [
        'weight loss',
        'ozempic',
        'mounjaro',
        'belly fat',
        'GLP-1',
    ],
    [
        'natural ozempic',
        'natural mounjaro',
        'salt trick weight loss',
        'pink salt trick',
        'gelatin trick',
    ],
    [
        'ice hack weight loss',
        'ice water hack',
        'morning ritual weight loss',
        'lose weight fast',
        'burn fat',
    ],
]


# ── Fetch one keyword ─────────────────────────────────────────────────────────
def fetch_keyword(pytrends, kw):
    for attempt in range(3):
        try:
            time.sleep(DELAY_KW)
            pytrends.build_payload([kw], timeframe=TIMEFRAME, geo=GEO)
            df = pytrends.interest_over_time()
            if df.empty:
                return None
            vals  = df[kw].tolist()
            first = vals[0] if vals[0] != 0 else 1
            last  = vals[-1]
            growth = round((last - first) / first * 100, 1)
            return {
                'keyword':         kw,
                'geo':             GEO,
                'timeframe':       TIMEFRAME,
                'score_atual':     last,
                'score_maximo':    max(vals),
                'score_minimo':    min(vals),
                'crescimento_pct': growth,
            }
        except Exception as e:
            wait = 15 * (attempt + 1)
            print(f'    ERROR (attempt {attempt+1}): {e} — retrying in {wait}s')
            time.sleep(wait)
    return None


# ── Tiered threshold filter ───────────────────────────────────────────────────
def apply_threshold(results):
    for threshold in [100, 50, 30, 0]:
        if threshold > 0:
            filtered = [r for r in results if r['crescimento_pct'] >= threshold]
        else:
            filtered = [r for r in results if r['crescimento_pct'] > 0]
        if filtered:
            print(f'\n  Threshold applied: crescimento_pct >= {threshold}% → {len(filtered)} keywords kept')
            return filtered
    print('\n  No keywords with positive growth — keeping all results')
    return results


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print('── Google Trends search ────────────────────────────────────────')
    print(f'   Region: {GEO} | Timeframe: {TIMEFRAME}')
    total_kw = sum(len(b) for b in BATCHES)
    print(f'   Keywords: {total_kw} across {len(BATCHES)} batches')
    print()

    pytrends = TrendReq(hl='en-GB', tz=0)
    all_results = []

    for b_idx, batch in enumerate(BATCHES, 1):
        print(f'── Batch {b_idx}/{len(BATCHES)} ──────────────────────────────────────────')
        for kw in batch:
            print(f'  {kw:<40}', end=' ', flush=True)
            result = fetch_keyword(pytrends, kw)
            if result:
                arrow = '+' if result['crescimento_pct'] > 0 else ''
                print(f'score={result["score_atual"]:>3}  growth={arrow}{result["crescimento_pct"]}%')
                all_results.append(result)
            else:
                print('→ no data')

        if b_idx < len(BATCHES):
            print(f'\n  Waiting {DELAY_BATCH}s before next batch...\n')
            time.sleep(DELAY_BATCH)

    print(f'\n  Total fetched: {len(all_results)} / {total_kw}')
    print(f'  Positive growth: {sum(1 for r in all_results if r["crescimento_pct"] > 0)}')
    print(f'  Negative growth: {sum(1 for r in all_results if r["crescimento_pct"] < 0)}')
    print(f'  Flat (0%):       {sum(1 for r in all_results if r["crescimento_pct"] == 0)}')

    # Apply tiered threshold
    filtered = apply_threshold(all_results)

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
        'tiktok':   _existing.get('tiktok',   []),
        'facebook': _existing.get('facebook', []),
        'trends':   filtered,
        'analise':  _existing.get('analise',  {
            'tendencias':         '',
            'mecanismos_em_alta': '',
            'avatares_em_alta':   '',
            'recomendacoes':      '',
        }),
    }

    dedup.save(payload, verbose=True)

    print('\n── Final trends ────────────────────────────────────────────────')
    print(f'  {"Keyword":<40}  {"Score":>5}  {"Growth":>8}')
    print(f'  {"-"*40}  {"-"*5}  {"-"*8}')
    for r in sorted(filtered, key=lambda x: x['crescimento_pct'], reverse=True):
        arrow = '+' if r['crescimento_pct'] > 0 else ''
        print(f'  {r["keyword"]:<40}  {r["score_atual"]:>5}  {arrow}{r["crescimento_pct"]:>7}%')
