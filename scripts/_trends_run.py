"""Temporary Trends run script - 2 batches, GB, positive growth only."""
import sys, json, time
sys.stdout.reconfigure(encoding='utf-8')
from pytrends.request import TrendReq

pytrends = TrendReq(hl='en-GB', tz=0)

BATCH1 = ['weight loss', 'ozempic', 'mounjaro', 'belly fat', 'GLP-1']
BATCH2 = ['natural ozempic', 'salt trick weight loss', 'ice hack weight loss',
          'bariatric trick', 'night ritual weight loss']

positive = []

def run_batch(keywords, label):
    results = []
    for kw in keywords:
        time.sleep(3)
        try:
            pytrends.build_payload([kw], timeframe='now 7-d', geo='GB')
            df = pytrends.interest_over_time()
            if df.empty:
                print(f'  {kw:<38} -> no data')
                continue
            vals = df[kw].tolist()
            first = vals[0] if vals[0] != 0 else 1
            last  = vals[-1]
            growth = round((last - first) / first * 100, 1)
            arrow = '+' if growth > 0 else ''
            print(f'  {kw:<38} score={last:>3}  growth={arrow}{growth}%')
            if growth > 0:
                results.append({
                    'keyword': kw, 'geo': 'GB', 'timeframe': 'now 7-d',
                    'score_atual': last, 'score_maximo': max(vals),
                    'score_minimo': min(vals), 'crescimento_pct': growth,
                })
        except Exception as e:
            print(f'  {kw:<38} -> ERROR: {e}')
            time.sleep(6)
    return results

print('=== Batch 1 ===')
positive += run_batch(BATCH1, 'B1')

print('\n--- waiting 15 seconds ---\n')
time.sleep(15)

print('=== Batch 2 ===')
positive += run_batch(BATCH2, 'B2')

print(f'\nPositive growth keywords: {len(positive)}')
print(json.dumps(positive, ensure_ascii=False, indent=2))

import os
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', '_trends_new.json')
with open(out, 'w', encoding='utf-8') as f:
    json.dump(positive, f, ensure_ascii=False, indent=2)
print(f'Saved -> {out}')
