"""Full trends run - 3 batches, GB, all results, 60s delay between batches."""
import sys, json, time, os
sys.stdout.reconfigure(encoding='utf-8')
from pytrends.request import TrendReq
from datetime import datetime

pytrends = TrendReq(hl='en-GB', tz=0)

BATCH1 = ['weight loss', 'ozempic', 'mounjaro', 'belly fat', 'GLP-1']
BATCH2 = ['natural ozempic', 'salt trick weight loss', 'ice hack weight loss', 'jelly trick', 'pink salt trick']
BATCH3 = ['bariatric trick', 'night ritual weight loss', 'morning ritual weight loss', 'natural mounjaro', 'lose weight fast']

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', '_trends_full.json')

def run_batch(keywords, label):
    results = []
    for kw in keywords:
        time.sleep(4)
        for attempt in range(3):
            try:
                pytrends.build_payload([kw], timeframe='now 7-d', geo='GB')
                df = pytrends.interest_over_time()
                if df.empty:
                    print(f'  {kw:<38} -> no data')
                    break
                vals = df[kw].tolist()
                first = vals[0] if vals[0] != 0 else 1
                last  = vals[-1]
                growth = round((last - first) / first * 100, 1)
                arrow = '+' if growth > 0 else ''
                print(f'  {kw:<38} score={last:>3}  growth={arrow}{growth}%')
                results.append({
                    'keyword':        kw,
                    'geo':            'GB',
                    'timeframe':      'now 7-d',
                    'score_atual':    last,
                    'score_maximo':   max(vals),
                    'score_minimo':   min(vals),
                    'crescimento_pct': growth,
                })
                break
            except Exception as e:
                wait = 15 * (attempt + 1)
                print(f'  {kw:<38} -> ERROR (attempt {attempt+1}): {e} — retrying in {wait}s')
                time.sleep(wait)
        else:
            print(f'  {kw:<38} -> FAILED after 3 attempts')
    return results

all_results = []

print('=== Batch 1 ===')
all_results += run_batch(BATCH1, 'B1')

print(f'\n--- waiting 60 seconds ---\n')
time.sleep(60)

print('=== Batch 2 ===')
all_results += run_batch(BATCH2, 'B2')

print(f'\n--- waiting 60 seconds ---\n')
time.sleep(60)

print('=== Batch 3 ===')
all_results += run_batch(BATCH3, 'B3')

print(f'\nTotal keywords fetched: {len(all_results)} / 15')
print(f'Positive growth: {sum(1 for t in all_results if t["crescimento_pct"] > 0)}')
print(f'Negative growth: {sum(1 for t in all_results if t["crescimento_pct"] < 0)}')
print(f'Flat (0%):       {sum(1 for t in all_results if t["crescimento_pct"] == 0)}')

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)
print(f'\nSaved -> {OUT}')
