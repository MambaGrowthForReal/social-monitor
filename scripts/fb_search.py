"""
fb_search.py — Facebook Ad Library scraper with deduplication.

Usage (from project root):
    python scripts/fb_search.py

Scrapes Meta Ad Library for weight-loss ads across US / GB / DE,
filters by days active (10–30), detects avatar type and language,
merges with existing latest.json (preserving YouTube/TikTok/Trends data),
then saves to data/YYYY-MM-DD.json + data/latest.json.
"""
import sys
import os
import re
import json
import asyncio
import base64
import urllib.parse
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dedup

sys.stdout.reconfigure(encoding='utf-8')

TODAY    = date.today()
DATA_DIR = dedup.DATA_DIR

# ── Config ────────────────────────────────────────────────────────────────────
COUNTRIES = ["US", "GB", "DE"]

KEYWORDS = [
    "salt trick",
    "pink salt trick",
    "pink salt recipe",
    "gelatin trick",
    "gelatin recipe",
    "gelatine trick",
    "gelatine recipe",
    "ice water hack",
    "ice trick",
    "pink ice trick",
    "natural mounjaro",
    "natural ozempic",
]

MIN_DAYS   = 10
MAX_DAYS   = 30
SCROLL_PX  = 3       # number of scroll passes per search page
DELAY_SEC  = 1.5     # seconds between requests

# ── Date parser ───────────────────────────────────────────────────────────────
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4,
    "june": 6, "july": 7, "august": 8, "september": 9,
    "october": 10, "november": 11, "december": 12,
}

def _parse_date(s):
    """Parse 'May 19, 2026', 'May 19 2026', '19 May 2026' → date or None."""
    s = (s or "").strip()
    # Month Day, Year
    m = re.search(r"\b([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\b", s)
    if m:
        mon = _MONTHS.get(m.group(1).lower()[:3])
        if mon:
            try: return date(int(m.group(3)), mon, int(m.group(2)))
            except ValueError: pass
    # Day Month Year
    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})\b", s)
    if m:
        mon = _MONTHS.get(m.group(2).lower()[:3])
        if mon:
            try: return date(int(m.group(3)), mon, int(m.group(1)))
            except ValueError: pass
    return None

# ── Text helpers ──────────────────────────────────────────────────────────────
_SKIP = {
    "Learn more", "Shop now", "See more", "Watch more", "Sign up",
    "Book now", "Contact us", "Download", "Like", "Comment", "Share",
    "Follow", "Subscribe", "Get offer", "Apply now", "Order now",
}

def _clean_text(raw):
    """Strip noise lines and truncate ad copy."""
    lines = [l.strip() for l in raw.split("\n") if l.strip() and l.strip() != "​"]
    out = []
    for line in lines:
        if re.match(r"^\d+:\d+\s*/\s*\d+:\d+", line): continue  # video timestamp
        if re.match(r"^[A-Z]{2,}\.[A-Z]{2,}", line):  continue  # bare domain
        if line in _SKIP:                              continue
        out.append(line)
        if len(out) >= 8:
            break
    return " ".join(out)[:400]

def _is_english(text):
    """Reject ads that lack a minimum number of common English words."""
    markers = {
        "the", "a", "an", "and", "or", "is", "are", "was", "to",
        "you", "your", "we", "our", "this", "that", "with", "for",
        "weight", "loss", "fat", "natural", "help", "get", "now",
        "my", "of", "in", "it", "i", "have", "not", "do", "lose",
    }
    words = set(re.findall(r'\b[a-z]{2,}\b', text.lower()))
    return len(words & markers) >= 4

def _detect_avatar(text):
    """Classify the avatar/angle present in the ad copy."""
    t = text.lower()
    tags = []
    if re.search(r"\bdr\.?\b|doctor|physician|medical|clinically|specialist|nurse", t):
        tags.append("médico/autoridade")
    if re.search(r"\bbefore\b.{0,30}\bafter\b|\btransformation\b", t):
        tags.append("antes/depois")
    if any(w in t for w in ["mom", "mother", "wife", " she ", "her "]):
        tags.append("mulher")
    if any(w in t for w in [" man ", "husband", " he ", " his "]):
        tags.append("homem")
    if any(w in t for w in ["recipe", "kitchen", "ingredient", "mix",
                             "dissolve", "drink", "trick", "ritual"]):
        tags.append("receita/truque")
    if any(w in t for w in ["natural", "herb", "plant", "supplement", "extract"]):
        tags.append("produto natural")
    return ", ".join(tags) if tags else "geral"

# ── Ad parser ─────────────────────────────────────────────────────────────────
def _parse_body(body_text, country, keyword):
    """
    Extract individual ads from document.body.innerText.

    The English Ad Library produces blocks like:
        Active
        Library ID: <id>
        Started running on <date>
        Platforms ...
        See ad details
        <Page Name>
        Sponsored
        <ad copy>
    """
    results = []
    segments = re.split(r"\nActive\n", body_text)

    for seg in segments[1:]:
        # ── Library ID ──
        lib_m = re.search(r"Library ID[:\s]+(\d{10,})", seg)
        lib_id = lib_m.group(1).strip() if lib_m else ""

        # ── Start date → days active ──
        date_m = re.search(r"Started running on\s+(.+?)(?:\n|$)", seg)
        start_dt = _parse_date(date_m.group(1)) if date_m else None
        if not start_dt:
            continue
        dias_ativo = (TODAY - start_dt).days
        if not (MIN_DAYS <= dias_ativo <= MAX_DAYS):
            continue

        # ── Page name + ad text ──
        # Primary pattern: "See ad details\n<PAGE>\nSponsored\n<TEXT>"
        detail_m = re.search(
            r"See ad details\n(.+?)\nSponsored\n([\s\S]*?)(?=\nActive\n|Library ID:|$)",
            seg
        )
        if detail_m:
            page_name   = detail_m.group(1).strip()
            ad_text_raw = detail_m.group(2)
        else:
            # Fallback: find "Sponsored\n<TEXT>"
            spon_m = re.search(
                r"\nSponsored\n([\s\S]*?)(?=\nActive\n|Library ID:|$)", seg
            )
            if not spon_m:
                continue
            page_name   = ""
            ad_text_raw = spon_m.group(1)

        ad_text = _clean_text(ad_text_raw)
        if len(ad_text) < 15:
            continue
        if not _is_english(ad_text):
            continue

        # ── Media type ──
        has_video = bool(re.search(r"\d+:\d+\s*/\s*\d+:\d+", seg))
        tipo = "VIDEO" if has_video else "IMAGE"

        snap_url = (
            f"https://www.facebook.com/ads/library/?id={lib_id}"
            if lib_id else ""
        )

        results.append({
            "page":        page_name,
            "texto":       ad_text,
            "data_inicio": start_dt.strftime("%b %d, %Y"),
            "dias_ativo":  dias_ativo,
            "tipo_media":  tipo,
            "url":         snap_url,
            "pais":        country,
            "keyword":     keyword,
            "avatar":      _detect_avatar(ad_text),
            "analise":     "",
        })

    return results

# ── Ad screenshot ─────────────────────────────────────────────────────────────
async def _screenshot_ad(page, snap_url, retries=1):
    """
    Navigate to the Ad Library snapshot page and return a base64-encoded
    JPEG thumbnail (data URI string), or empty string on failure.
    """
    if not snap_url:
        return ""
    for attempt in range(retries + 1):
        try:
            await page.goto(snap_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            # Dismiss cookie banners if present
            for sel in [
                'button:has-text("Allow all cookies")',
                'button:has-text("Accept")',
                '[data-cookiebanner="accept_button"]',
            ]:
                try:
                    btn = page.locator(sel)
                    if await btn.count() > 0:
                        await btn.first.click(timeout=2000)
                        await page.wait_for_timeout(600)
                        break
                except Exception:
                    pass

            # Try to isolate the ad card; fall back to viewport crop
            ad_el = None
            for sel in [
                '[class*="AdLibraryAdDetails"]',
                '[class*="x1qjc9v5"]',   # common FB ad card wrapper
                '[data-testid="ad-library-ad-details"]',
            ]:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0:
                        ad_el = el
                        break
                except Exception:
                    pass

            if ad_el:
                raw = await ad_el.screenshot(type="jpeg", quality=60)
            else:
                raw = await page.screenshot(
                    type="jpeg", quality=60,
                    clip={"x": 0, "y": 0, "width": 600, "height": 500},
                )

            b64 = base64.b64encode(raw).decode("ascii")
            return f"data:image/jpeg;base64,{b64}"

        except Exception as e:
            if attempt < retries:
                await asyncio.sleep(2)
                continue
            print(f"  [screenshot FAILED: {e}]")
            return ""


# ── Playwright scraper ────────────────────────────────────────────────────────
async def _scrape_one(page, country, keyword, retries=2):
    """Navigate to one country/keyword search and return parsed ads."""
    url = (
        "https://www.facebook.com/ads/library/"
        f"?active_status=active&ad_type=all"
        f"&country={country}"
        f"&q={urllib.parse.quote(keyword)}"
        f"&search_type=keyword_unordered&media_type=all"
    )
    for attempt in range(retries + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=35000)
            await page.wait_for_timeout(2500)

            # Dismiss cookie / consent banners
            for sel in [
                '[data-cookiebanner="accept_button"]',
                'button[title="Accept All"]',
                'button:has-text("Allow all cookies")',
                'button:has-text("Accept")',
                '[aria-label="Allow all cookies"]',
            ]:
                try:
                    btn = page.locator(sel)
                    if await btn.count() > 0:
                        await btn.first.click(timeout=2000)
                        await page.wait_for_timeout(800)
                        break
                except Exception:
                    pass

            # Scroll to trigger lazy-loaded results
            for _ in range(SCROLL_PX):
                await page.keyboard.press("End")
                await page.wait_for_timeout(1200)

            body = await page.evaluate("document.body.innerText")
            return _parse_body(body, country, keyword)

        except Exception as e:
            if attempt < retries:
                await asyncio.sleep(3)
                continue
            print(f"FAILED ({e})")
            return []

# ── Main ──────────────────────────────────────────────────────────────────────
async def _main():
    date_str = TODAY.isoformat()

    print("── Facebook Ad Library Scraper ─────────────────────────────────")
    print(f"   Date        : {date_str}")
    print(f"   Countries   : {', '.join(COUNTRIES)}")
    print(f"   Keywords    : {len(KEYWORDS)}")
    print(f"   Days active : {MIN_DAYS}–{MAX_DAYS}")
    print()

    from playwright.async_api import async_playwright

    all_ads = []
    total   = len(COUNTRIES) * len(KEYWORDS)
    done    = 0

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        ctx = await browser.new_context(
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            viewport={"width": 1280, "height": 900},
        )
        page = await ctx.new_page()

        for country in COUNTRIES:
            print(f"\n── {country} ─────────────────────────────────────────────")
            for keyword in KEYWORDS:
                done += 1
                print(f"  [{done:>2}/{total}] {keyword:<35}", end=" ", flush=True)
                ads = await _scrape_one(page, country, keyword)
                print(f"→ {len(ads)} ads")
                all_ads.extend(ads)
                await asyncio.sleep(DELAY_SEC)

        # ── Dedup happens below; screenshots taken after dedup ──
        # (keep browser open until after screenshot pass)

        # ── Batch dedup (same library URL / page+text combo) ──
        seen, unique = set(), []
        for ad in all_ads:
            key = ad.get("url") or (ad["page"] + ad["texto"][:40])
            if key not in seen:
                seen.add(key)
                unique.append(ad)

        # ── Cross-run dedup ──
        prev_urls = set()
        for path in dedup._dated_files():
            if os.path.basename(path).replace(".json", "") == date_str:
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                for item in d.get("facebook", []):
                    if item.get("url"):
                        prev_urls.add(item["url"])
            except Exception:
                pass

        final   = [a for a in unique if not (a.get("url") and a["url"] in prev_urls)]

        # ── Screenshot each unique ad ──
        print(f"\n── Screenshots ({len(final)} ads) ──────────────────────────────")
        for i, ad in enumerate(final):
            snap = ad.get("url", "")
            print(f"  [{i+1}/{len(final)}] {ad['page'][:30]}", end=" ", flush=True)
            ad["thumbnail"] = await _screenshot_ad(page, snap)
            kb = len(ad["thumbnail"]) // 1024
            print(f"→ {kb} KB" if ad["thumbnail"] else "→ no image")
            await asyncio.sleep(1.0)

        await browser.close()

    removed = len(unique) - len(final)

    # ── Summary ──
    print(f"\n── Summary ─────────────────────────────────────────────────────")
    print(f"   Total scraped          : {len(all_ads)}")
    print(f"   After batch dedup      : {len(unique)}")
    print(f"   Cross-run duplicates   : {removed}")
    print(f"   Saving                 : {len(final)} ads")

    if final:
        print("\n   Top results:")
        for ad in final[:6]:
            flag = {"US": "🇺🇸", "GB": "🇬🇧", "DE": "🇩🇪"}.get(ad["pais"], "")
            print(f"   {flag} [{ad['dias_ativo']}d · {ad['tipo_media']}] "
                  f"{ad['page'][:25]}: {ad['texto'][:55]}...")

    # ── Merge with existing data (preserve YouTube / TikTok / Trends) ──
    latest_path = os.path.join(DATA_DIR, "latest.json")
    dated_path  = os.path.join(DATA_DIR, f"{date_str}.json")

    existing = {}
    try:
        with open(latest_path, encoding="utf-8") as f:
            existing = json.load(f)
    except Exception:
        pass

    payload = {
        "data_execucao": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "youtube":  existing.get("youtube",  []),
        "tiktok":   existing.get("tiktok",   []),
        "facebook": final,
        "trends":   existing.get("trends",   []),
        "analise":  existing.get("analise",  {
            "tendencias": "", "mecanismos_em_alta": "",
            "avatares_em_alta": "", "recomendacoes": "",
        }),
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    for path in (dated_path, latest_path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    dedup.update_history(date_str)

    print(f"\n✅ Saved → {date_str}.json + latest.json")
    print(f"   History: {dedup.load_history().get('dates', [])}")


if __name__ == "__main__":
    asyncio.run(_main())
