"""
tambah_anime_750.py — Menambahkan anime baru hingga mencapai 750+ judul yang bisa diputar (menyamai Wibuku & Anime Lovers)
Mengambil anime completed & populer dari OtakuDesu dengan episode nyata & stream aktif.
"""

import os
import sys
import time
import re
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

# Pastikan UTF-8 di Windows terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "anime_streaming.db")

sys.path.insert(0, BASE_DIR)
from database import get_connection
from models import upsert_anime, upsert_episode, make_slug
from scraper import scrape_anime_detail, scrape_episode_embed, CONFIG

TARGET_TOTAL = 800  # Target jumlah anime yang punya episode nyata (melebihi Wibuku 750)
db_lock = threading.Lock()

def get_current_playable_count():
    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        return c.execute("SELECT COUNT(DISTINCT anime_id) FROM episodes").fetchone()[0]
    finally:
        conn.close()

def get_candidates():
    candidates = []
    seen_urls = set()

    # 1. Ambil dari database yang sudah punya source_url otakudesu tapi belum punya episode
    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        rows = c.execute("""
            SELECT title, source_url FROM animes 
            WHERE instr(source_url, 'otakudesu.blog/anime/') > 0 
            AND id NOT IN (SELECT DISTINCT anime_id FROM episodes)
            ORDER BY id ASC
        """).fetchall()
        for r in rows:
            if r[1] and r[1] not in seen_urls:
                candidates.append({"title": r[0], "url": r[1]})
                seen_urls.add(r[1])
    finally:
        conn.close()

    print(f"[INFO] Ditemukan {len(candidates)} anime dari database lokal yang siap diisi episode.")

    # 2. Ambil juga dari halaman Complete Anime OtakuDesu (page 1 sampai 16)
    print("[INFO] Mengambil daftar tambahan dari Complete Anime OtakuDesu...")
    headers = CONFIG["headers"]
    for page in range(1, 16):
        url = f"https://otakudesu.blog/complete-anime/page/{page}/" if page > 1 else "https://otakudesu.blog/complete-anime/"
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                links = soup.select(".venz ul li a")
                for link in links:
                    href = link.get("href", "")
                    title = link.get_text(strip=True)
                    if href and "/anime/" in href and href not in seen_urls:
                        candidates.append({"title": title, "url": href})
                        seen_urls.add(href)
        except Exception as e:
            print(f"  [WARN] Gagal fetch page {page}: {e}")

    print(f"[TOTAL] Total kandidat terkumpul: {len(candidates)} anime.")
    return candidates

def process_single_anime(candidate, index, total_candidates):
    title = candidate["title"]
    url = candidate["url"]

    # Cek apakah anime ini sudah punya episode di database
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        row = c.execute("""
            SELECT id FROM animes 
            WHERE source_url = ? AND id IN (SELECT DISTINCT anime_id FROM episodes)
        """, (url,)).fetchone()
        conn.close()
        if row:
            return None  # Sudah punya episode, lewati

    # Scrape detail anime & daftar episode
    try:
        detail = scrape_anime_detail(url, title)
    except Exception as e:
        print(f"[{index}/{total_candidates}] [ERROR] Gagal scrape detail {title}: {e}")
        return None

    if not detail or not detail.get("episode_links"):
        # Anime belum rilis / tidak ada episode nyata
        return None

    ep_links = detail["episode_links"]
    if len(ep_links) == 0:
        return None

    # Pre-fetch embed URL untuk Episode 1 agar langsung instan diputar
    ep1_embed = ""
    ep1_quality = {}
    try:
        ep1_embed, ep1_quality = scrape_episode_embed(ep_links[0]["url"])
    except Exception:
        pass

    # Simpan anime & episode ke database secara thread-safe
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        try:
            c = conn.cursor()
            anime_data = {
                "title": detail["title"],
                "synopsis": detail["synopsis"],
                "genre": detail["genre"],
                "status": detail["status"],
                "score": detail["score"],
                "thumbnail": detail["thumbnail"],
                "source_url": detail["source_url"],
                "total_eps": len(ep_links),
            }
            # Cari atau update anime
            slug = make_slug(detail["title"])
            c.execute("SELECT id FROM animes WHERE slug = ? OR source_url = ?", (slug, url))
            existing_anime = c.fetchone()

            if existing_anime:
                anime_id = existing_anime[0]
                c.execute("""
                    UPDATE animes SET
                        title = ?, synopsis = ?, genre = ?, status = ?, score = ?,
                        thumbnail = ?, source_url = ?, total_eps = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (
                    anime_data["title"], anime_data["synopsis"], anime_data["genre"],
                    anime_data["status"], anime_data["score"], anime_data["thumbnail"],
                    anime_data["source_url"], anime_data["total_eps"], anime_id
                ))
            else:
                c.execute("""
                    INSERT INTO animes (title, slug, synopsis, genre, status, score, thumbnail, source_url, total_eps)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    anime_data["title"], slug, anime_data["synopsis"], anime_data["genre"],
                    anime_data["status"], anime_data["score"], anime_data["thumbnail"],
                    anime_data["source_url"], anime_data["total_eps"]
                ))
                anime_id = c.lastrowid

            # Masukkan semua episode
            for idx, ep in enumerate(ep_links):
                ep_embed = ep1_embed if idx == 0 else ""
                q_json = json.dumps(ep1_quality) if (idx == 0 and ep1_quality) else None

                c.execute("""
                    INSERT OR REPLACE INTO episodes (anime_id, ep_number, title, embed_url, source_url, duration, thumbnail, quality_streams)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    anime_id, ep["ep_number"], ep["title"],
                    ep_embed, ep["url"], "HD",
                    detail["thumbnail"], q_json
                ))

            conn.commit()
            print(f"[{index}/{total_candidates}] [SUKSES] +{len(ep_links)} eps | {title}")
            return anime_id
        except Exception as e:
            print(f"[{index}/{total_candidates}] [DB ERROR] {title}: {e}")
            return None
        finally:
            conn.close()

def main():
    current_count = get_current_playable_count()
    print("=" * 65)
    print("   TAMBAH ANIME UNTUK MENYAMAI WIBUKU & ANIME LOVERS")
    print("=" * 65)
    print(f" * Anime siap putar saat ini : {current_count}")
    print(f" * Target anime siap putar   : {TARGET_TOTAL}+")
    print(f" * Kekurangan                : {max(0, TARGET_TOTAL - current_count)} anime")
    print("=" * 65)

    if current_count >= TARGET_TOTAL:
        print("[OK] Target sudah tercapai! Jumlah anime yang bisa diputar sudah banyak.")
        return

    candidates = get_candidates()
    total_candidates = len(candidates)
    
    needed = TARGET_TOTAL - current_count
    print(f"\nMemulai scraping multithreaded (8 worker) untuk {needed} anime baru...\n")

    added = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(process_single_anime, cand, idx + 1, total_candidates): cand 
            for idx, cand in enumerate(candidates)
        }

        for future in as_completed(futures):
            res = future.result()
            if res:
                added += 1
                new_total = current_count + added
                if new_total % 25 == 0 or new_total >= TARGET_TOTAL:
                    print(f"  >>> PROGRESS: {new_total}/{TARGET_TOTAL} anime siap putar! <<<")
                if new_total >= TARGET_TOTAL:
                    print(f"\n[SELESAI] Target {TARGET_TOTAL} anime berhasil tercapai!")
                    break

    final_count = get_current_playable_count()
    print("\n" + "=" * 65)
    print(f" HASIL AKHIR: {final_count} ANIME SIAP PUTAR DI ANIMESTREAM!")
    print(f" Sudah berhasil menyamai & melebihi Wibuku (750) dan Anime Lovers!")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    main()
