"""Step 2 - fetch 2 batches, apply threshold filter, merge with existing."""
import sys, json, time, os
sys.stdout.reconfigure(encoding='utf-8')
from pytrends.request import TrendReq
from datetime import datetime, date

pytrends = TrendReq(hl='en-GB', tz=0)

BATCH1 = ['weight loss', 'ozempic', 'mounjaro', 'belly fat', 'GLP-1']
BATCH2 = ['natural ozempic', 'salt trick weight loss', 'ice hack weight loss', 'jelly trick', 'pink salt trick']

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'latest.json')

def fetch_batch(keywords):
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
                    'keyword': kw, 'geo': 'GB', 'timeframe': 'now 7-d',
                    'score_atual': last, 'score_maximo': max(vals),
                    'score_minimo': min(vals), 'crescimento_pct': growth,
                })
                break
            except Exception as e:
                wait = 15 * (attempt + 1)
                print(f'  {kw:<38} -> ERROR (attempt {attempt+1}): {e} — retry in {wait}s')
                time.sleep(wait)
        else:
            print(f'  {kw:<38} -> FAILED after 3 attempts')
    return results

def apply_threshold(trends):
    for threshold in [100, 50, 30]:
        result = [t for t in trends if t.get('crescimento_pct', 0) >= threshold]
        if result:
            print(f'  Threshold {threshold}% -> {len(result)} keyword(s) kept')
            return result
        print(f'  Threshold {threshold}% -> 0 matches')
    print('  No threshold matched — keeping all with growth > 0')
    return [t for t in trends if t.get('crescimento_pct', 0) > 0]

# ── Batch 1 ──
print('=== Batch 1 ===')
raw1 = fetch_batch(BATCH1)

print(f'\n--- waiting 60 seconds ---\n')
time.sleep(60)

# ── Batch 2 ──
print('=== Batch 2 ===')
raw2 = fetch_batch(BATCH2)

all_new = raw1 + raw2
print(f'\nTotal fetched: {len(all_new)}')

# Apply threshold to new results
print('\nApplying threshold filter to new results:')
filtered_new = apply_threshold(all_new)

# Load current data and merge (new results override by keyword)
with open(DATA_FILE, encoding='utf-8') as f:
    data = json.load(f)

existing = {t['keyword']: t for t in data.get('trends', [])}
for t in filtered_new:
    existing[t['keyword']] = t

data['trends'] = list(existing.values())
data['data_execucao'] = datetime.now().strftime('%d/%m/%Y %H:%M')

today = date.today().isoformat()
dated = os.path.join(os.path.dirname(DATA_FILE), f'{today}.json')
for path in (DATA_FILE, dated):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

print(f'\nFinal trends array ({len(data["trends"])} keywords):')
for t in data['trends']:
    arrow = '+' if t['crescimento_pct'] > 0 else ''
    print(f'  {t["keyword"]:<38} score={t["score_atual"]:>3}  growth={arrow}{t["crescimento_pct"]}%')
print(f'\nSaved -> latest.json + {today}.json')
