"""
scraper_samehadaku.py
Modul scraper Samehadaku terintegrasi dengan database anime_streaming.
"""

import os
import sys
from urllib.parse import urljoin
import cloudscraper
from bs4 import BeautifulSoup

# Memastikan terminal Windows mendukung karakter khusus
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import init_db
from models import upsert_anime, make_slug

DOMAIN_AKTIF = "https://v2.samehadaku.how"

def ambil_dan_simpan_samehadaku(url_target=DOMAIN_AKTIF):
    init_db()
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )
    
    print(f"Sedang mengakses Samehadaku: {url_target}...")
    try:
        response = scraper.get(url_target, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        daftar_anime = []
        
        # Cek tag article
        kartu_anime = soup.find_all("article")
        if kartu_anime:
            for kartu in kartu_anime:
                tag_link = kartu.find("a")
                tag_judul = kartu.find("h2") or kartu.find("h3") or kartu.find(class_="title")
                img_tag = kartu.find("img")
                if tag_link and tag_judul:
                    judul = tag_judul.get_text(strip=True)
                    url_anime = urljoin(url_target, tag_link.get("href", ""))
                    thumb = img_tag.get("src") or img_tag.get("data-src", "") if img_tag else ""
                    daftar_anime.append({"judul": judul, "url": url_anime, "thumbnail": thumb})
        else:
            for h3 in soup.find_all("h3"):
                parent_a = h3.find_parent("a") or h3.find("a")
                judul = h3.get_text(strip=True)
                if parent_a and parent_a.get("href") and judul:
                    url_anime = urljoin(url_target, parent_a.get("href"))
                    parent_card = h3.find_parent("div") or parent_a
                    img_tag = parent_card.find("img") if parent_card else None
                    thumb = img_tag.get("src") or img_tag.get("data-src", "") if img_tag else ""
                    if not any(a["url"] == url_anime for a in daftar_anime):
                        daftar_anime.append({"judul": judul, "url": url_anime, "thumbnail": thumb})

        print(f"Ditemukan {len(daftar_anime)} anime.")
        total_tersimpan = 0
        for item in daftar_anime:
            data = {
                "title": item["judul"],
                "slug": make_slug(item["judul"]),
                "synopsis": f"Anime {item['judul']} dari Samehadaku.",
                "genre": "Anime",
                "status": "Ongoing",
                "score": 0.0,
                "thumbnail": item.get("thumbnail", ""),
                "source_url": item["url"],
                "total_eps": 0
            }
            try:
                anime_id = upsert_anime(data)
                total_tersimpan += 1
                print(f"  [DB] Sukses simpan/update ID {anime_id}: {item['judul']}")
            except Exception as e:
                print(f"  [ERROR] {item['judul']}: {e}")

        print(f"\nSelesai! {total_tersimpan} anime berhasil masuk ke anime_streaming.db")
        return total_tersimpan

    except Exception as e:
        print(f"Terjadi kesalahan: {e}")
        return 0

if __name__ == "__main__":
    ambil_dan_simpan_samehadaku()
