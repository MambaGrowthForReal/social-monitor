"""FB refined keywords - 17 keywords, GB+US, max 3 ads each, screenshots, merge into latest.json."""
import sys, os, re, json, asyncio, base64, urllib.parse
from datetime import date, datetime, timezone
sys.stdout.reconfigure(encoding='utf-8')

TODAY     = date.today()
MIN_DAYS  = 10
MAX_DAYS  = 30
MAX_ADS   = 3
COUNTRIES = ['GB', 'US']
KEYWORDS  = [
    'salt trick', 'pink salt', 'pink salt trick', 'pink trick',
    'salt recipe', 'jelly trick', 'gelatin trick', 'gelatine trick',
    'ice trick', 'pink ice trick', 'salt ice trick', 'pink ice',
    'ice water hack', 'ice hack', 'cocoa trick', 'himalayan salt', 'himalayan trick',
]

DATA_FILE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'latest.json'))

_MONTHS = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,
           'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}

def _parse_date(s):
    s = (s or '').strip()
    m = re.search(r'\b([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\b', s)
    if m:
        mon = _MONTHS.get(m.group(1).lower()[:3])
        if mon:
            try: return date(int(m.group(3)), mon, int(m.group(2)))
            except: pass
    return None

_SKIP = {'Learn more','Shop now','See more','Watch more','Sign up','Book now',
         'Contact us','Download','Like','Comment','Share','Follow','Subscribe',
         'Get offer','Apply now','Order now'}

def _clean_text(raw):
    lines = [l.strip() for l in raw.split('\n') if l.strip() and l.strip() != '​']
    out = []
    for line in lines:
        if re.match(r'^\d+:\d+\s*/\s*\d+:\d+', line): continue
        if re.match(r'^[A-Z]{2,}\.[A-Z]{2,}', line): continue
        if line in _SKIP: continue
        out.append(line)
        if len(out) >= 8: break
    return ' '.join(out)[:400]

def _is_english(text):
    markers = {'the','a','an','and','or','is','are','was','to','you','your','we','our',
               'this','that','with','for','weight','loss','fat','natural','help','get',
               'now','my','of','in','it','i','have','not','do','lose','salt','trick',
               'pink','ice','jelly','gelatin','cocoa','himalayan','hack','recipe'}
    words = set(re.findall(r'\b[a-z]{2,}\b', text.lower()))
    return len(words & markers) >= 3

def _detect_avatar(text):
    t = text.lower(); tags = []
    if re.search(r'\bdr\.?\b|doctor|physician|medical|clinically|nurse', t): tags.append('medico')
    if re.search(r'\bbefore\b.{0,30}\bafter\b|\btransformation\b', t): tags.append('antes/depois')
    if any(w in t for w in ['mom','mother','wife',' she ','her ']): tags.append('mulher')
    if any(w in t for w in [' man ','husband',' he ',' his ']): tags.append('homem')
    if any(w in t for w in ['recipe','ingredient','mix','dissolve','drink','trick','ritual','hack']):
        tags.append('receita/truque')
    if any(w in t for w in ['natural','herb','plant','supplement','extract']): tags.append('natural')
    return ', '.join(tags) if tags else 'geral'

def _parse_body(body_text, country, keyword):
    results = []
    segments = re.split(r'\nActive\n', body_text)
    for seg in segments[1:]:
        if len(results) >= MAX_ADS: break
        lib_m = re.search(r'Library ID[:\s]+(\d{10,})', seg)
        lib_id = lib_m.group(1).strip() if lib_m else ''
        date_m = re.search(r'Started running on\s+(.+?)(?:\n)', seg)
        start_dt = _parse_date(date_m.group(1)) if date_m else None
        if not start_dt: continue
        dias_ativo = (TODAY - start_dt).days
        if not (MIN_DAYS <= dias_ativo <= MAX_DAYS): continue
        detail_m = re.search(r'See ad details\n(.+?)\nSponsored\n([\s\S]*?)(?=\nActive\n|Library ID:|$)', seg)
        if detail_m:
            page_name = detail_m.group(1).strip()
            ad_text_raw = detail_m.group(2)
        else:
            spon_m = re.search(r'\nSponsored\n([\s\S]*?)(?=\nActive\n|Library ID:|$)', seg)
            if not spon_m: continue
            page_name = ''; ad_text_raw = spon_m.group(1)
        ad_text = _clean_text(ad_text_raw)
        if len(ad_text) < 15 or not _is_english(ad_text): continue
        snap_url = f'https://www.facebook.com/ads/library/?id={lib_id}' if lib_id else ''
        results.append({
            'page': page_name, 'texto': ad_text,
            'data_inicio': start_dt.strftime('%b %d, %Y'),
            'dias_ativo': dias_ativo,
            'tipo_media': 'VIDEO' if bool(re.search(r'\d+:\d+\s*/\s*\d+:\d+', seg)) else 'IMAGE',
            'url': snap_url, 'pais': country, 'keyword': keyword,
            'avatar': _detect_avatar(ad_text), 'analise': '', 'thumbnail': '',
        })
    return results

async def screenshot_ad(page, snap_url):
    if not snap_url: return ''
    for attempt in range(2):
        try:
            await page.goto(snap_url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(2000)
            for sel in ['button:has-text("Allow all cookies")', 'button:has-text("Accept")',
                        '[data-cookiebanner="accept_button"]']:
                try:
                    btn = page.locator(sel)
                    if await btn.count() > 0:
                        await btn.first.click(timeout=2000)
                        await page.wait_for_timeout(500)
                        break
                except Exception: pass
            ad_el = None
            for sel in ['[class*="AdLibraryAdDetails"]', '[data-testid="ad-library-ad-details"]']:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0: ad_el = el; break
                except Exception: pass
            raw = await ad_el.screenshot(type='jpeg', quality=60) if ad_el else \
                  await page.screenshot(type='jpeg', quality=60,
                                        clip={'x': 0, 'y': 0, 'width': 600, 'height': 500})
            return 'data:image/jpeg;base64,' + base64.b64encode(raw).decode('ascii')
        except Exception as e:
            if attempt == 0: await asyncio.sleep(2); continue
            return ''

async def scrape_one(page, country, keyword):
    url = ('https://www.facebook.com/ads/library/?active_status=active&ad_type=all'
           f'&country={country}&q={urllib.parse.quote(keyword)}'
           '&search_type=keyword_unordered&media_type=all')
    for attempt in range(3):
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=35000)
            await page.wait_for_timeout(2500)
            for sel in ['button:has-text("Allow all cookies")', 'button:has-text("Accept")',
                        '[data-cookiebanner="accept_button"]']:
                try:
                    btn = page.locator(sel)
                    if await btn.count() > 0:
                        await btn.first.click(timeout=2000)
                        await page.wait_for_timeout(800)
                        break
                except Exception: pass
            for _ in range(4):
                await page.keyboard.press('End')
                await page.wait_for_timeout(1200)
            body = await page.evaluate('document.body.innerText')
            return _parse_body(body, country, keyword)
        except Exception as e:
            if attempt < 2: await asyncio.sleep(3); continue
            return []

async def main():
    from playwright.async_api import async_playwright

    # Load existing data
    with open(DATA_FILE, encoding='utf-8') as f:
        data = json.load(f)

    existing_fb   = data.get('facebook', [])
    existing_urls = {a['url'] for a in existing_fb if a.get('url')}
    print(f'Existing FB ads: {len(existing_fb)}')

    total   = len(COUNTRIES) * len(KEYWORDS)
    done    = 0
    all_new = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        ctx = await browser.new_context(
            locale='en-US',
            extra_http_headers={'Accept-Language': 'en-US,en;q=0.9'},
            viewport={'width': 1280, 'height': 900},
        )
        page = await ctx.new_page()

        for country in COUNTRIES:
            print(f'\n=== {country} ===')
            for kw in KEYWORDS:
                done += 1
                print(f'  [{done:>2}/{total}] {kw:<22}', end=' ', flush=True)
                ads = await scrape_one(page, country, kw)
                # Filter out URLs already in existing data
                fresh = [a for a in ads if not (a.get('url') and a['url'] in existing_urls)]
                print(f'-> {len(ads)} found, {len(fresh)} new')
                all_new.extend(fresh)
                for a in fresh:
                    existing_urls.add(a['url'])
                await asyncio.sleep(1.5)

        # Dedup within new batch by URL
        seen, unique_new = set(), []
        for ad in all_new:
            key = ad.get('url') or (ad['page'] + ad['texto'][:40])
            if key not in seen:
                seen.add(key)
                unique_new.append(ad)

        print(f'\n=== Screenshots ({len(unique_new)} new unique ads) ===')
        for i, ad in enumerate(unique_new):
            print(f'  [{i+1:>2}/{len(unique_new)}] {ad["page"][:28]:<28}', end=' ', flush=True)
            ad['thumbnail'] = await screenshot_ad(page, ad.get('url', ''))
            kb = len(ad['thumbnail']) // 1024
            print(f'-> {kb} KB' if ad['thumbnail'] else '-> no image')
            await asyncio.sleep(1.0)

        await browser.close()

    # Merge and save
    data['facebook'] = existing_fb + unique_new
    data['data_execucao'] = datetime.now().strftime('%d/%m/%Y %H:%M')

    today = date.today().isoformat()
    dated = os.path.join(os.path.dirname(DATA_FILE), f'{today}.json')
    for path in (DATA_FILE, dated):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    print(f'\n{"="*60}')
    print(f'DONE. Added {len(unique_new)} new ads. Total FB: {len(data["facebook"])}')
    print(f'{"="*60}')
    print(f'\n{"Country":<6} {"Keyword":<22} {"Days":>4} {"Type":<6} {"Page"}')
    print(f'{"-"*6} {"-"*22} {"-"*4} {"-"*6} {"-"*30}')
    for ad in unique_new:
        print(f'{ad["pais"]:<6} {ad["keyword"]:<22} {ad["dias_ativo"]:>4}d {ad["tipo_media"]:<6} {ad["page"][:35]}')

if __name__ == '__main__':
    asyncio.run(main())
