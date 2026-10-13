"""
scraper.py — Otomatisasi pengambilan data anime dari situs sumber
Menggunakan requests + BeautifulSoup dan AJAX dynamic decoding untuk OtakuDesu/Samehadaku stream.
"""

import time
import re
import sys
import os
import json
import base64

import requests
from bs4 import BeautifulSoup

# Pastikan terminal Windows mendukung semua simbol, kanji, dan karakter bintang (★)
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Tambahkan folder backend ke path agar bisa import modul lain
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import init_db
from models import upsert_anime, upsert_episode, make_slug

# ─────────────────────────────────────────────
#  KONFIGURASI — SESUAIKAN DI SINI
# ─────────────────────────────────────────────

CONFIG = {
    # URL halaman utama/daftar anime sumber
    "base_url": "https://otakudesu.blog",

    # URL halaman daftar anime lengkap
    "anime_list_url": "https://otakudesu.blog/anime-list/",

    # Jeda antar request (detik)
    "request_delay": 1.5,

    # Maximum anime yang di-scrape per sesi (0 = semua)
    "max_animes": 5,

    # Maximum episode per anime yang di-scrape (0 = semua)
    "max_episodes_per_anime": 0,

    # Header HTTP agar terlihat seperti browser biasa
    "headers": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
}

# ─────────────────────────────────────────────
#  FUNGSI HTTP
# ─────────────────────────────────────────────

# Gunakan cloudscraper jika terinstall untuk bypass proteksi Cloudflare
try:
    import cloudscraper
    scraper_client = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
except ImportError:
    scraper_client = requests.Session()

def fetch_page(url: str) -> BeautifulSoup | None:
    """Ambil halaman web dan parse dengan BeautifulSoup."""
    try:
        print(f"  [FETCH] {url}")
        resp = scraper_client.get(url, headers=CONFIG["headers"], timeout=15)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"  [ERROR] Gagal fetch {url}: {e}")
        return None


# ─────────────────────────────────────────────
#  SCRAPER: DAFTAR ANIME
# ─────────────────────────────────────────────

def scrape_anime_list(source: str = "ongoing") -> list[dict]:
    """Scrape daftar anime dari halaman list, ongoing, complete, atau popular."""
    if source == "popular":
        all_links = scrape_anime_list("list")
        popular_keywords = [
            'boku no hero', 'bleach', 'black clover', 'blue lock', 'dandadan',
            'boruto', 'chainsaw', 'naruto', 'one piece', 'hunter x hunter',
            'haikyuu', 'shingeki no kyojin', 'attack on titan', 'fate', 'overlord',
            'tensei shitara slime', 'solo leveling', 're:zero', 'konosuba',
            'mushoku tensei', 'death note', 'tokyo ghoul', 'sword art online',
            'mashle', 'kaiju', 'wind breaker', 'vinland', 'dr. stone', 'baki',
            'classroom of the elite', 'youkoso jitsuryoku', 'oshi no ko'
        ]
        pop_list = []
        for a in all_links:
            t = a["title"].lower()
            if any(k in t for k in popular_keywords):
                pop_list.append(a)
        print(f"  [INFO] Ditemukan {len(pop_list)} anime kategori POPULER.")
        return pop_list

    urls = {
        "ongoing": "https://otakudesu.blog/ongoing-anime/",
        "complete": "https://otakudesu.blog/complete-anime/",
        "list": CONFIG["anime_list_url"],
    }
    target_url = urls.get(source, CONFIG["anime_list_url"])
    print(f"  [SOURCE] Mengambil daftar dari: {target_url}")
    soup = fetch_page(target_url)
    if not soup:
        return []

    anime_list = []
    if source == "list":
        links = soup.find_all("a", href=lambda h: h and "/anime/" in h)
        for link in links:
            title = link.get_text(strip=True)
            url = link.get("href", "")
            if not url.startswith("http"):
                url = CONFIG["base_url"] + url
            if title and "/genre/" not in url and not any(a["url"] == url for a in anime_list):
                anime_list.append({"title": title, "url": url})
    else:
        items = soup.select(".venz ul li")
        if not items:
            links = soup.find_all("a", href=lambda h: h and "/anime/" in h)
            for link in links:
                title = link.get_text(strip=True)
                url = link.get("href", "")
                if not url.startswith("http"):
                    url = CONFIG["base_url"] + url
                if title and not any(a["url"] == url for a in anime_list):
                    anime_list.append({"title": title, "url": url})
        else:
            for item in items:
                link = item.find("a")
                if not link:
                    continue
                title = link.get_text(strip=True)
                url = link.get("href", "")
                if not url.startswith("http"):
                    url = CONFIG["base_url"] + url
                if title and not any(a["url"] == url for a in anime_list):
                    anime_list.append({"title": title, "url": url})

    print(f"  [INFO] Ditemukan {len(anime_list)} anime dari sumber '{source}'.")
    return anime_list


# ─────────────────────────────────────────────
#  SCRAPER: DETAIL ANIME
# ─────────────────────────────────────────────

def scrape_anime_detail(anime_url: str, anime_title: str) -> dict | None:
    """Scrape detail satu halaman anime (sinopsis, genre, thumbnail, daftar episode nyata)."""
    soup = fetch_page(anime_url)
    if not soup:
        return None

    # Thumbnail
    thumbnail = ""
    img_tag = soup.select_one(".fotoanime img") or soup.select_one(".thumb img")
    if img_tag:
        thumbnail = img_tag.get("src") or img_tag.get("data-src", "")

    # Sinopsis
    synopsis = ""
    synopsis_tag = (
        soup.select_one(".sinopc")
        or soup.select_one(".synopsis")
        or soup.select_one("[itemprop='description']")
    )
    if synopsis_tag:
        synopsis = synopsis_tag.get_text(separator=" ", strip=True)

    # Genre
    genre = ""
    genre_tags = soup.select(".infozin .infozingle b:-soup-contains('Genre')") 
    if not genre_tags:
        for tag in soup.find_all("b"):
            if "Genre" in tag.get_text():
                parent = tag.find_parent()
                if parent:
                    genre = parent.get_text(strip=True).replace("Genre:", "").strip()
                break

    # Status & Score
    status = "Ongoing"
    score = 0.0
    for b_tag in soup.find_all("b"):
        text = b_tag.get_text(strip=True)
        parent_text = b_tag.find_parent().get_text(strip=True) if b_tag.find_parent() else ""
        if "Status" in text:
            status = parent_text.replace("Status:", "").strip()[:50]
        if "Score" in text or "Rating" in text:
            score_match = re.search(r"[\d.]+", parent_text)
            if score_match:
                try:
                    score = float(score_match.group())
                except ValueError:
                    pass

    # Daftar Episode (Filter batch & lengkap, hanya episode nyata)
    episode_links = []
    ep_containers = soup.select(".episodelist ul li") or soup.select(".eps-wrap a")

    for ep_item in ep_containers:
        link = ep_item.find("a") or ep_item
        if not hasattr(link, "get"):
            continue
        href = link.get("href", "")
        if not href.startswith("http"):
            href = CONFIG["base_url"] + href
        ep_text = link.get_text(strip=True)

        # Abaikan batch & lengkap
        if "/batch/" in href or "/lengkap/" in href or "[batch]" in ep_text.lower():
            continue

        ep_num = 0
        ep_match = re.search(r"(?:episode|ep)[\s\-]?(\d+)", ep_text, re.IGNORECASE)
        if ep_match:
            ep_num = int(ep_match.group(1))
        elif "ova" in ep_text.lower():
            ep_num = 99
        else:
            continue

        if href:
            episode_links.append({"url": href, "ep_number": ep_num, "title": ep_text})

    # Urutkan dari episode 1 ke akhir
    episode_links.sort(key=lambda x: x["ep_number"])

    print(f"  [INFO] Ditemukan {len(episode_links)} episode nyata untuk '{anime_title}'.")

    return {
        "title": anime_title,
        "slug": make_slug(anime_title),
        "synopsis": synopsis or "Tidak ada sinopsis.",
        "genre": genre or "Tidak diketahui",
        "status": status,
        "score": score,
        "thumbnail": thumbnail,
        "source_url": anime_url,
        "total_eps": len(episode_links),
        "episode_links": episode_links,
    }


# ─────────────────────────────────────────────
#  SCRAPER: EMBED VIDEO DARI HALAMAN EPISODE
# ─────────────────────────────────────────────

def scrape_episode_embed(episode_url: str, session: requests.Session = None) -> tuple[str, dict]:
    """
    Scrape URL embed video dari halaman episode dengan prioritas KUALITAS TINGGI (720p HD / 1080p).
    Mengembalikan (best_hd_url, quality_streams_dict).
    """
    if not episode_url:
        return "", {}

    if session is None:
        session = requests.Session()

    session.headers.update({
        "User-Agent": CONFIG["headers"]["User-Agent"],
        "Referer": episode_url
    })

    quality_streams = {}
    best_url = ""

    try:
        resp = session.get(episode_url, timeout=12)
        if resp.status_code != 200:
            return "", {}
        soup = BeautifulSoup(resp.text, "html.parser")

        # 1. Cek iframe langsung non-maintenance
        for f in soup.find_all("iframe"):
            src = f.get("src") or f.get("data-src", "")
            if src and "maintenance" not in src and "about:blank" not in src:
                best_url = src
                break

        # 2. Dynamic AJAX resolution
        scripts = [s.get_text() for s in soup.find_all("script") if "__x__nonce" in s.get_text()]
        if scripts:
            script = scripts[0]
            actions = re.findall(r'action:[\"\']([a-f0-9]{32})[\"\']', script)
            if len(actions) >= 2:
                action_stream = actions[0]
                action_nonce = actions[1]

                rn = session.post("https://otakudesu.blog/wp-admin/admin-ajax.php", data={"action": action_nonce}, timeout=10)
                nonce = rn.json().get("data")
                if nonce:
                    # Ambil resolusi dari tertinggi ke terendah: 720p HD -> 480p -> 360p
                    for q in ["720p", "1080p", "480p", "360p"]:
                        q_links = soup.select(f".mirrorstream ul.m{q} a[data-content]")
                        for l in q_links:
                            raw_b64 = l.get("data-content")
                            if not raw_b64:
                                continue
                            try:
                                payload = json.loads(base64.b64decode(raw_b64).decode())
                                rs = session.post(
                                    "https://otakudesu.blog/wp-admin/admin-ajax.php",
                                    data={**payload, "nonce": nonce, "action": action_stream},
                                    headers={"Referer": "https://otakudesu.blog/"},
                                    timeout=10
                                )
                                res_data = rs.json().get("data")
                                if res_data:
                                    html = base64.b64decode(res_data).decode("utf-8", errors="ignore")
                                    m = re.search(r'src=[\"\']([^\"\']+)[\"\']', html)
                                    if m:
                                        src = m.group(1)
                                        bad_domains = ["solidfiles", "zippyshare", "racaty", "tusfiles", "mediafire", "acefile", "mega.nz", "mirrorace", "maintenance", "about:blank"]
                                        if not any(bad in src.lower() for bad in bad_domains):
                                            quality_streams[q] = src
                                            if not best_url and q in ["720p", "1080p"]:
                                                best_url = src
                                            break
                            except Exception:
                                continue

                    if not best_url and quality_streams:
                        for pref in ["720p", "1080p", "480p", "360p"]:
                            if pref in quality_streams:
                                best_url = quality_streams[pref]
                                break
    except Exception as e:
        print(f"  [ERROR] scrape_episode_embed gagal: {e}")

    return best_url, quality_streams


# ─────────────────────────────────────────────
#  FUNGSI UTAMA: JALANKAN SCRAPER
# ─────────────────────────────────────────────

def run_scraper(limit: int = 10, source: str = "ongoing", max_eps: int = 0):
    """Fungsi utama yang menjalankan seluruh proses scraping."""
    print("=" * 60)
    print(f"  ANIME STREAMING SCRAPER — Sumber: {source.upper()} (Limit: {limit})")
    print("=" * 60)

    init_db()
    from database import get_connection
    print()

    print("[STEP 1] Mengambil daftar anime...")
    sources_to_scrape = [source] if source != "all" else ["ongoing", "complete", "list"]
    anime_list = []
    for src in sources_to_scrape:
        anime_list.extend(scrape_anime_list(src))

    if not anime_list:
        print("[WARN] Tidak ada anime yang ditemukan.")
        return

    print(f"  Total calon anime: {len(anime_list)}\n")
    session = requests.Session()
    conn = get_connection()

    scraped_count = 0
    for i, anime_info in enumerate(anime_list, 1):
        if limit > 0 and scraped_count >= limit:
            print(f"[SELESAI] Target limit ({limit} anime baru) telah tercapai!")
            break

        anime_slug = make_slug(anime_info["title"])
        existing = conn.execute("SELECT id FROM animes WHERE slug = ?", (anime_slug,)).fetchone()
        if existing:
            ep_count = conn.execute("SELECT COUNT(*) FROM episodes WHERE anime_id = ?", (existing["id"],)).fetchone()[0]
            if ep_count > 0:
                print(f"[{i}/{len(anime_list)}] [SKIP] '{anime_info['title']}' sudah ada {ep_count} episode.")
                continue

        print(f"\n[{i}/{len(anime_list)}] [SCRAPING BARU {scraped_count + 1}/{limit}] {anime_info['title']}")
        time.sleep(CONFIG["request_delay"])

        try:
            detail = scrape_anime_detail(anime_info["url"], anime_info["title"])
            if not detail:
                print(f"  [SKIP] Gagal mendapatkan detail untuk: {anime_info['title']}")
                continue

            episode_links = detail.pop("episode_links", [])
            anime_id = upsert_anime(detail)
            print(f"  [DB] Anime tersimpan ID: {anime_id}")

            if max_eps > 0:
                episode_links = episode_links[:max_eps]

            for j, ep_info in enumerate(episode_links, 1):
                print(f"  [EP {j}/{len(episode_links)}] Ep {ep_info['ep_number']} - {ep_info['title']}")
                time.sleep(CONFIG["request_delay"])
                try:
                    embed_url, quality_streams = scrape_episode_embed(ep_info["url"], session)
                except Exception as e:
                    print(f"  [WARN] Embed error: {e}")
                    embed_url, quality_streams = "", {}

                episode_data = {
                    "anime_id": anime_id,
                    "ep_number": ep_info["ep_number"] or j,
                    "title": ep_info.get("title", f"Episode {j}"),
                    "embed_url": embed_url,
                    "source_url": ep_info["url"],
                    "quality_streams": quality_streams,
                }
                ep_id = upsert_episode(episode_data)
                print(f"  [DB] Ep ID: {ep_id} | HD Embed: {embed_url[:60] if embed_url else 'Video Stream'}")

            scraped_count += 1
        except Exception as e:
            print(f"  [ERROR] Gagal memproses anime: {e}")
            continue

    conn.close()
    print("=" * 60)
    print(f"  SCRAPING SELESAI! Total {scraped_count} anime baru berhasil ditambahkan.")
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Scraper Anime Streaming")
    parser.add_argument("--limit", type=int, default=15, help="Jumlah anime baru yang ingin di-scrape")
    parser.add_argument("--source", type=str, default="popular", choices=["popular", "ongoing", "complete", "list", "all"], help="Kategori anime: popular, ongoing, complete, list, all")
    parser.add_argument("--max-eps", type=int, default=0, help="Batas episode per anime (0 = semua episode)")
    args = parser.parse_args()

    run_scraper(limit=args.limit, source=args.source, max_eps=args.max_eps)
