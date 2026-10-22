"""
animeverse_resolver.py — Resolver Otomatis untuk Mengambil Stream Direct MP4 dari AnimeVerse CDN (AnimeLovers / AnimeKita API).
Mendukung caching in-memory katalog 4,816 anime dan pre-fetching chapter.
"""

import urllib.request
import ssl
import gzip
import json
import re
import unicodedata
import threading
import time

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Dart/3.1 (dart:io)',
    'Host': 'apps.animekita.org'
}

_CATALOG_CACHE = []
_CATALOG_LOCK = threading.Lock()
_SERIES_CACHE = {}
_SERIES_LOCK = threading.Lock()

def get_season_number(t):
    if not t:
        return 1
    t_low = str(t).lower()
    m = re.search(r'\bseason\s*(\d+)\b|\bs(\d+)\b', t_low)
    if m:
        return int(m.group(1) or m.group(2))
    return 1

def clean_title(t):
    if not t:
        return ""
    t = unicodedata.normalize('NFKD', str(t)).lower()
    t = re.sub(r'\(.*?\)|\[.*?\]', '', t)
    t = re.sub(r'subtitle\s*indonesia|sub\s*indo|season\s*\d+|s\d+|movie|the\s*movie', '', t)
    t = re.sub(r'[^a-z0-9]', '', t)
    return t.strip()

def load_animekita_catalog():
    global _CATALOG_CACHE
    if _CATALOG_CACHE:
        return _CATALOG_CACHE
    with _CATALOG_LOCK:
        if _CATALOG_CACHE:
            return _CATALOG_CACHE
        try:
            req = urllib.request.Request('https://apps.animekita.org/api/v1.1.9/search.php?q=a', headers=HEADERS)
            res = urllib.request.urlopen(req, context=ctx, timeout=12)
            raw = res.read()
            if raw[:2] == b'\x1f\x8b':
                raw = gzip.decompress(raw)
            text = raw.decode('utf-8', errors='ignore')
            pattern = re.compile(r'\{\s*"id":\s*(\d+),\s*"url":\s*"([^"]+)",\s*"judul":\s*"(.*?)",\s*"cover":\s*"([^"]*)",\s*"lastch":\s*"([^"]*)"\s*\}')
            _CATALOG_CACHE = pattern.findall(text)
            print(f"[ANIMAVERSE-RESOLVER] Berhasil memuat {len(_CATALOG_CACHE)} katalog anime dari AnimeKita.")
        except Exception as e:
            print(f"[ANIMAVERSE-RESOLVER] Gagal memuat katalog: {e}")
        return _CATALOG_CACHE

def find_animekita_series(title, slug=""):
    catalog = load_animekita_catalog()
    if not catalog:
        return None, None

    is_movie = "movie" in str(title).lower() or "film" in str(title).lower() or "movie" in str(slug).lower()

    c_title = clean_title(title)
    c_slug = clean_title(slug)
    s_req = get_season_number(title)

    SPECIAL_ALIASES = {
        'naruto': ('naruto-alredy-fixed', 'Naruto Bocil'),
        'naruto20': ('naruto-alredy-fixed', 'Naruto Bocil'),
        'narutobocil': ('naruto-alredy-fixed', 'Naruto Bocil'),
        'narutoshippuden': ('naruto-shippuuden-all-fixed', 'Naruto: Shippuuden'),
        'narutoshippuuden': ('naruto-shippuuden-all-fixed', 'Naruto: Shippuuden'),
        'narutoshippuden1735': ('naruto-shippuuden-all-fixed', 'Naruto: Shippuuden'),
        'boruto': ('boruto-naruto-next-generations-fixed', 'Boruto: Naruto Next Generations'),
        'borutonarutonextgenerations': ('boruto-naruto-next-generations-fixed', 'Boruto: Naruto Next Generations'),
        'borutonarutonextgenerations97938': ('boruto-naruto-next-generations-fixed', 'Boruto: Naruto Next Generations'),
    }

    if not is_movie:
        if c_title in SPECIAL_ALIASES:
            return SPECIAL_ALIASES[c_title]
        if c_slug in SPECIAL_ALIASES:
            return SPECIAL_ALIASES[c_slug]

    def item_matches_type(curl, cjudul):
        item_is_movie = "movie" in cjudul.lower() or "film" in cjudul.lower() or "movie" in curl.lower()
        return item_is_movie == is_movie

    # 1. Exact cleaned match with SAME season & type
    for cid, curl, cjudul, ccover, clast in catalog:
        if item_matches_type(curl, cjudul) and (c_title == clean_title(cjudul) or c_slug == clean_title(curl)) and get_season_number(cjudul) == s_req:
            return curl, cjudul

    # 2. Exact cleaned match (fallback any season, same type)
    for cid, curl, cjudul, ccover, clast in catalog:
        if item_matches_type(curl, cjudul) and (c_title == clean_title(cjudul) or c_slug == clean_title(curl)):
            return curl, cjudul

    # 3. Substring match with SAME season & type
    for cid, curl, cjudul, ccover, clast in catalog:
        if item_matches_type(curl, cjudul):
            clean_j = clean_title(cjudul)
            if len(c_title) >= 4 and (c_title in clean_j or clean_j in c_title) and get_season_number(cjudul) == s_req:
                return curl, cjudul

    # 4. Substring match (fallback same type)
    for cid, curl, cjudul, ccover, clast in catalog:
        if item_matches_type(curl, cjudul):
            clean_j = clean_title(cjudul)
            if len(c_title) >= 4 and (c_title in clean_j or clean_j in c_title):
                return curl, cjudul

    return None, None

def get_series_chapters(series_url):
    if not series_url:
        return []
    with _SERIES_LOCK:
        if series_url in _SERIES_CACHE:
            return _SERIES_CACHE[series_url]

    try:
        clean_url = series_url.strip()
        api_url = f"https://apps.animekita.org/api/v1.1.9/series.php?url={clean_url}"
        req = urllib.request.Request(api_url, headers=HEADERS)
        res = urllib.request.urlopen(req, context=ctx, timeout=8)
        raw = res.read()
        if raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
        data = json.loads(raw.decode('utf-8', errors='ignore'))
        chapters = data.get('data', [{}])[0].get('chapter', [])
        with _SERIES_LOCK:
            _SERIES_CACHE[series_url] = chapters
        return chapters
    except Exception as e:
        print(f"[ANIMAVERSE-RESOLVER] Gagal memuat chapter untuk {series_url}: {e}")
        return []

def resolve_animeverse_stream(title, slug, ep_number):
    """
    Menyelesaikan URL episode ke link direct MP4 dari server AnimeVerse CDN (AnimeLovers).
    Mengembalikan direct MP4 URL (string) atau None jika tidak ditemukan.
    """
    series_url, series_title = find_animekita_series(title, slug)
    if not series_url:
        return None

    chapters = get_series_chapters(series_url)
    if not chapters:
        return None

    # Cari chapter yang sesuai dengan nomor episode
    target_ch = None
    ep_int = int(ep_number)
    for ch in chapters:
        m = re.search(r'\b\d+\b', str(ch.get('ch', '')))
        if m and int(m.group(0)) == ep_int:
            target_ch = ch
            break

    if not target_ch:
        # Fallback index jika penomoran berbasis urutan
        try:
            if len(chapters) >= ep_int > 0:
                if str(chapters[-1].get('ch', '')).startswith('1'):
                    target_ch = chapters[-ep_int]
                else:
                    target_ch = chapters[ep_int - 1]
        except Exception:
            pass

    if not target_ch:
        return None

    ch_url = target_ch.get('url')
    # Ambil link stream dari resolusi tertinggi ke terendah
    for reso in ['720p', '480p', '360p']:
        for attempt in range(2):
            try:
                stream_api = f"https://apps.animekita.org/api/v1.1.9/chapter.php?url={ch_url}&reso={reso}"
                req = urllib.request.Request(stream_api, headers=HEADERS)
                res = urllib.request.urlopen(req, context=ctx, timeout=6)
                raw = res.read()
                if raw[:2] == b'\x1f\x8b':
                    raw = gzip.decompress(raw)
                d = json.loads(raw.decode('utf-8', errors='ignore'))
                streams = d.get('data', [{}])[0].get('stream', [])
                for s in streams:
                    link = s.get('link', '')
                    if 'animeverse.id' in link or 'animekita.org' in link or 'pixeldrain' in link or link.endswith('.mp4'):
                        return link
            except Exception:
                time.sleep(0.2)

    return None

if __name__ == "__main__":
    test = resolve_animeverse_stream("Bleach", "bleach", 228)
    print("Test Bleach 228:", test)
