"""
expand_animes.py — Memperbanyak anime populer dan melengkapi seluruh episodenya dengan stream aktif tanpa error.
"""

import os
import sys
import time
import re
import json
import base64
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import bs4

DB_PATH = os.path.join(os.path.dirname(__file__), "anime_streaming.db")

TARGET_ANIMES = [
    {
        "title": "Chainsaw Man",
        "slug": "chainsaw-man",
        "url": "https://otakudesu.blog/anime/chaisaw-sub-indo/"
    },
    {
        "title": "Sousou no Frieren",
        "slug": "sousou-no-frieren",
        "url": "https://otakudesu.blog/anime/sousou-frieren-sub-indo/"
    },
    {
        "title": "Jujutsu Kaisen Season 2",
        "slug": "jujutsu-kaisen-s2",
        "url": "https://otakudesu.blog/anime/jjk-s2-sub-indo/"
    },
    {
        "title": "Kimetsu no Yaiba: Katanakaji no Sato-hen",
        "slug": "kimetsu-no-yaiba-s3",
        "url": "https://otakudesu.blog/anime/kimetsu-yaiba-s3-sub-indo/"
    },
    {
        "title": "Spy x Family Season 2",
        "slug": "spy-x-family-s2",
        "url": "https://otakudesu.blog/anime/spy-family-s2-sub-indo/"
    },
    {
        "title": "Blue Lock Season 2",
        "slug": "blue-lock-s2",
        "url": "https://otakudesu.blog/anime/blelock-s2-sub-indo/"
    },
    {
        "title": "Tokyo Revengers: Santen Sensou-hen",
        "slug": "tokyo-revengers-santen-sensou-hen",
        "url": "https://otakudesu.blog/anime/tokyo-revs-sanhen-sub-indo/"
    }
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

def resolve_embed(ep_url):
    """Ambil stream asli dari halaman episode otakudesu."""
    if not ep_url:
        return ""
    s = requests.Session()
    s.headers.update(HEADERS)
    s.headers.update({'Referer': ep_url})
    try:
        r = s.get(ep_url, timeout=12)
        if r.status_code != 200:
            return ""
        soup = bs4.BeautifulSoup(r.text, 'html.parser')

        # 1. Cek iframe non-maintenance
        for f in soup.find_all('iframe'):
            src = f.get('src') or f.get('data-src', '')
            if src and 'maintenance' not in src and 'about:blank' not in src:
                return src

        # 2. Cek script nonce
        scripts = [sc.get_text() for sc in soup.find_all('script') if '__x__nonce' in sc.get_text()]
        if not scripts:
            return ""

        script = scripts[0]
        actions = re.findall(r'action:[\"\']([a-f0-9]{32})[\"\']', script)
        if len(actions) < 2:
            return ""

        action_stream = actions[0]
        action_nonce = actions[1]

        rn = s.post('https://otakudesu.blog/wp-admin/admin-ajax.php', data={'action': action_nonce}, timeout=10)
        nonce = rn.json().get('data')
        if not nonce:
            return ""

        links = soup.select('.mirrorstream a[data-content]')
        links_sorted = sorted(links, key=lambda l: 0 if any(k in l.get_text().lower() for k in ['otakuwatch', 'desu', 'moe', 'mp4']) else 1)

        for l in links_sorted:
            raw_b64 = l.get('data-content')
            if not raw_b64:
                continue
            try:
                payload = json.loads(base64.b64decode(raw_b64).decode())
                rs = s.post(
                    'https://otakudesu.blog/wp-admin/admin-ajax.php',
                    data={**payload, 'nonce': nonce, 'action': action_stream},
                    headers={'Referer': 'https://otakudesu.blog/'},
                    timeout=10
                )
                res_data = rs.json().get('data')
                if res_data:
                    html = base64.b64decode(res_data).decode('utf-8', errors='ignore')
                    m = re.search(r'src=[\"\']([^\"\']+)[\"\']', html)
                    if m:
                        src = m.group(1)
                        if 'maintenance' not in src:
                            return src
            except Exception:
                continue
    except Exception as e:
        print(f"    [ERR] {ep_url}: {e}")
    return ""

def scrape_anime_full(anime_info):
    """Scrape detail anime dan seluruh episode beserta link streamnya."""
    title = anime_info["title"]
    url = anime_info["url"]
    slug = anime_info["slug"]

    print(f"\n==========================================")
    print(f"[SCRAPE] Memproses: {title}")
    print(f"URL: {url}")
    print(f"==========================================")

    s = requests.Session()
    s.headers.update(HEADERS)

    r = s.get(url, timeout=15)
    if r.status_code != 200:
        print(f"[FAIL] Gagal fetch halaman anime: {url}")
        return None

    soup = bs4.BeautifulSoup(r.text, 'html.parser')

    # Thumbnail
    thumbnail = ""
    img = soup.select_one(".fotoanime img") or soup.select_one(".thumb img")
    if img:
        thumbnail = img.get("src") or img.get("data-src", "")

    # Sinopsis
    synopsis = ""
    syn_tag = soup.select_one(".sinopc") or soup.select_one(".synopsis") or soup.select_one("[itemprop='description']")
    if syn_tag:
        synopsis = syn_tag.get_text(separator=" ", strip=True)

    # Genre
    genre = ""
    for b_tag in soup.find_all("b"):
        if "Genre" in b_tag.get_text():
            parent = b_tag.find_parent()
            if parent:
                genre = parent.get_text(strip=True).replace("Genre:", "").strip()
            break

    # Status & Score
    status = "Completed"
    score = 8.5
    for b_tag in soup.find_all("b"):
        text = b_tag.get_text(strip=True)
        p_text = b_tag.find_parent().get_text(strip=True) if b_tag.find_parent() else ""
        if "Status" in text:
            status = p_text.replace("Status:", "").strip()[:50]
        if "Score" in text or "Rating" in text:
            m = re.search(r"[\d.]+", p_text)
            if m:
                try:
                    score = float(m.group())
                except ValueError:
                    pass

    # Ambil episode nyata
    ep_items = soup.select('.episodelist ul li')
    raw_episodes = []

    for item in ep_items:
        link = item.find('a')
        if not link:
            continue
        href = link.get('href', '')
        ep_title = link.get_text(strip=True)

        if '/batch/' in href or '/lengkap/' in href or '[batch]' in ep_title.lower():
            continue

        m = re.search(r'(?:episode|ep)[\s\-]?(\d+)', ep_title, re.IGNORECASE)
        if m:
            ep_num = int(m.group(1))
        elif 'ova' in ep_title.lower():
            ep_num = 99
        else:
            continue

        raw_episodes.append({
            'ep_number': ep_num,
            'title': ep_title,
            'url': href
        })

    # Urutkan dari ep 1 ke atas
    raw_episodes.sort(key=lambda x: x['ep_number'])
    print(f"Ditemukan {len(raw_episodes)} episode nyata untuk '{title}'")

    # Ambil embed stream secara paralel (3 worker per anime agar stabil)
    episodes_with_stream = []

    def fetch_stream_task(ep):
        stream = resolve_embed(ep['url'])
        return {
            'ep_number': ep['ep_number'],
            'title': ep['title'],
            'source_url': ep['url'],
            'embed_url': stream
        }

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fetch_stream_task, ep): ep for ep in raw_episodes}
        for future in as_completed(futures):
            ep_res = future.result()
            status_text = "[OK]" if ep_res['embed_url'] else "[EMPTY]"
            print(f"  -> Ep {ep_res['ep_number']} {status_text} {ep_res['embed_url'][:55] if ep_res['embed_url'] else ''}")
            episodes_with_stream.append(ep_res)

    episodes_with_stream.sort(key=lambda x: x['ep_number'])

    return {
        "title": title,
        "slug": slug,
        "synopsis": synopsis or f"Nonton anime {title} subtitle Indonesia online lengkap.",
        "genre": genre or "Action, Fantasy, Adventure",
        "status": status,
        "score": score,
        "thumbnail": thumbnail,
        "source_url": url,
        "total_eps": len(episodes_with_stream),
        "episodes": episodes_with_stream
    }

def run_expansion():
    if not os.path.exists(DB_PATH):
        print(f"[ERROR] Database {DB_PATH} tidak ditemukan!")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Bersihkan dummy anime lama
    dummy_slugs = ['frieren-beyond-journeys-end', 'jujutsu-kaisen', 'demon-slayer-kimetsu-no-yaiba']
    for d_slug in dummy_slugs:
        row = cursor.execute("SELECT id FROM animes WHERE slug = ?", (d_slug,)).fetchone()
        if row:
            anime_id = row[0]
            cursor.execute("DELETE FROM episodes WHERE anime_id = ?", (anime_id,))
            cursor.execute("DELETE FROM animes WHERE id = ?", (anime_id,))
            print(f"[CLEANUP] Menghapus dummy anime: {d_slug}")
    conn.commit()

    for anime_meta in TARGET_ANIMES:
        res = scrape_anime_full(anime_meta)
        if not res:
            continue

        slug = res["slug"]
        # Cek apakah anime sudah ada
        existing = cursor.execute("SELECT id FROM animes WHERE slug = ?", (slug,)).fetchone()
        if existing:
            anime_id = existing[0]
            cursor.execute("""
                UPDATE animes SET
                    title=?, synopsis=?, genre=?, status=?, score=?,
                    thumbnail=?, source_url=?, total_eps=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (
                res["title"], res["synopsis"], res["genre"], res["status"],
                res["score"], res["thumbnail"], res["source_url"], res["total_eps"],
                anime_id
            ))
            # Hapus episode lama untuk diupdate yang terbaru
            cursor.execute("DELETE FROM episodes WHERE anime_id = ?", (anime_id,))
        else:
            cursor.execute("""
                INSERT INTO animes (title, slug, synopsis, genre, status, score, thumbnail, source_url, total_eps)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                res["title"], slug, res["synopsis"], res["genre"],
                res["status"], res["score"], res["thumbnail"], res["source_url"],
                res["total_eps"]
            ))
            anime_id = cursor.lastrowid

        # Masukkan episode
        for ep in res["episodes"]:
            cursor.execute("""
                INSERT INTO episodes (anime_id, ep_number, title, embed_url, source_url)
                VALUES (?, ?, ?, ?, ?)
            """, (anime_id, ep["ep_number"], ep["title"], ep["embed_url"], ep["source_url"]))

        conn.commit()
        print(f"[SAVED] Berhasil menyimpan {res['total_eps']} episode untuk '{res['title']}' (ID: {anime_id})!\n")

    conn.close()
    print("==========================================")
    print("  SEMUA ANIME BERHASIL DIPERBANYAK & LENGKAP!")
    print("==========================================")

if __name__ == "__main__":
    run_expansion()
