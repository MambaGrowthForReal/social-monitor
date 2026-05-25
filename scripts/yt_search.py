"""
yt_search.py — YouTube Data API v3 search with automatic deduplication.

Usage (from project root):
    python scripts/yt_search.py

Searches celebrity weight-loss keywords for GB region, filters results
by title relevance, deduplicates against previously saved data, then saves
to data/YYYY-MM-DD.json, data/latest.json, and updates data/history.json.
"""
import sys
import os
import json
import re
import urllib.request
import urllib.parse
from datetime import date, datetime

# Allow importing sibling module dedup.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dedup

sys.stdout.reconfigure(encoding='utf-8')

# ── Config ────────────────────────────────────────────────────────────────────
API_KEY         = "AIzaSyD1Cevw3c962uSGezwVaZYHp3SUKz6BTTo"
PUBLISHED_AFTER = "2026-05-08T00:00:00Z"   # ← update each run as needed
REGION          = "GB"
MIN_VIEWS       = 50_000
TODAY           = date.today()

KEYWORDS = [
    "celebrity weight loss 2026",
    "celebrity lost weight",
    "weight loss transformation celebrity",
    "celebrity ozempic",
    "celebrity mounjaro",
    "Jelly Roll weight loss",
    "celebrity before after weight loss",
    "lost weight celebrity interview",
    "celebrity weight loss journey",
    "celebrity weight loss shocking",
]

# ── Title filter ──────────────────────────────────────────────────────────────
INCLUDE_WORDS = [
    "weight", "loss", "lost", "fat", "ozempic", "mounjaro", "slim",
    "diet", "glp", "bariatric", "pounds", "belly", "lbs", " lb ",
    "calorie", "keto", "fasting", "bmi", "obese", "obesity",
    "overweight", "waist", "stone ", "stones",
]

EXCLUDE_RE = re.compile(
    r"bollywood|movie cast|film cast|cast then|then vs now|then and now|"
    r"cast ka|\bipl\b|\bnba\b|\bnfl\b|\bnhl\b|cricket|footballer|"
    r"\d{4}\s*[→\-–]\s*\d{4}|\d{4}\s+to\s+\d{4}|"
    r"\bactor\b|\bactress\b|viralreels|hindi|telugu|tamil|bhojpuri|#bollywood",
    re.IGNORECASE,
)


# ── API helpers ───────────────────────────────────────────────────────────────
def api_get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def search_keyword(kw):
    params = urllib.parse.urlencode({
        "part":              "id",
        "q":                 kw,
        "type":              "video",
        "regionCode":        REGION,
        "relevanceLanguage": "en",
        "publishedAfter":    PUBLISHED_AFTER,
        "maxResults":        15,
        "order":             "viewCount",
        "key":               API_KEY,
    })
    data = api_get(f"https://www.googleapis.com/youtube/v3/search?{params}")
    return [item["id"]["videoId"] for item in data.get("items", [])]


def get_details(video_ids):
    if not video_ids:
        return []
    params = urllib.parse.urlencode({
        "part": "snippet,statistics",
        "id":   ",".join(video_ids),
        "key":  API_KEY,
    })
    data = api_get(f"https://www.googleapis.com/youtube/v3/videos?{params}")
    results = []
    for item in data.get("items", []):
        sn   = item["snippet"]
        stat = item.get("statistics", {})
        views = int(stat.get("viewCount", 0))
        if views < MIN_VIEWS:
            continue
        pub = sn.get("publishedAt", "")[:10]
        try:
            dias = (TODAY - datetime.strptime(pub, "%Y-%m-%d").date()).days
        except Exception:
            dias = 0
        results.append({
            "titulo":                sn.get("title", ""),
            "canal":                 sn.get("channelTitle", ""),
            "views":                 views,
            "likes":                 int(stat.get("likeCount", 0)),
            "comentarios":           int(stat.get("commentCount", 0)),
            "data":                  pub,
            "dias_desde_publicacao": dias,
            "url":                   f"https://youtube.com/watch?v={item['id']}",
            "thumbnail":             sn.get("thumbnails", {}).get("medium", {}).get("url", ""),
            "keyword":               "",
            "analise":               "",
        })
    return results


def is_relevant(title):
    if EXCLUDE_RE.search(title):
        return False
    tl = title.lower()
    return any(w in tl for w in INCLUDE_WORDS)


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":

    print("── YouTube search ──────────────────────────────────────────────")
    print(f"   Region: {REGION} | After: {PUBLISHED_AFTER} | Min views: {MIN_VIEWS:,}")
    print()

    # 1. Collect video IDs per keyword
    id_to_kw = {}
    for kw in KEYWORDS:
        print(f"  Searching: {kw}")
        for vid in search_keyword(kw):
            if vid not in id_to_kw:
                id_to_kw[vid] = kw

    print(f"\n  Unique IDs collected: {len(id_to_kw)}")

    # 2. Fetch video details in batches of 50
    id_list = list(id_to_kw.keys())
    raw     = []
    for i in range(0, len(id_list), 50):
        batch = id_list[i:i + 50]
        vids  = get_details(batch)
        for v in vids:
            v["keyword"] = id_to_kw.get(v["url"].split("v=")[-1], "")
        raw.extend(vids)

    # 3. Dedup within this batch + sort by views
    seen, batch_deduped = set(), []
    for v in sorted(raw, key=lambda x: x["views"], reverse=True):
        if v["url"] not in seen:
            seen.add(v["url"])
            batch_deduped.append(v)

    print(f"  Videos passing view threshold ({MIN_VIEWS:,}): {len(batch_deduped)}")

    # 4. Title filter (remove Bollywood / sports / non-weight content)
    final   = [v for v in batch_deduped if is_relevant(v["titulo"])]
    removed = [v for v in batch_deduped if not is_relevant(v["titulo"])]

    print(f"  After title filter: {len(final)} kept, {len(removed)} removed")

    # 5. Build payload
    payload = {
        "data_execucao": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "youtube":  final,
        "tiktok":   [],
        "facebook": [],
        "trends":   [],
        "analise": {
            "tendencias":         "",
            "mecanismos_em_alta": "",
            "avatares_em_alta":   "",
            "recomendacoes":      "",
        },
    }

    # 6. Save with cross-run URL deduplication
    stats = dedup.save(payload, verbose=True)

    # 7. Print final table
    if payload["youtube"]:
        print("\n── Final results ───────────────────────────────────────────────")
        print(f"  {'Views':>9}  {'Title':<55}  {'Days':>4}  Keyword")
        print(f"  {'-'*9}  {'-'*55}  {'-'*4}  {'-'*25}")
        for v in payload["youtube"]:
            print(f"  {v['views']:>9,}  {v['titulo'][:55]:<55}  {v['dias_desde_publicacao']:>4}d  {v['keyword']}")
    else:
        print("\n  No videos passed all filters.")
