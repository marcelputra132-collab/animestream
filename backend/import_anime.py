"""
import_anime.py
Mengimpor SELURUH data anime (metadata) dari AniList ke tabel `animes`
di database SQLite proyek anime_streaming.

AniList hanya mengizinkan 5000 anime per pencarian, jadi script ini
mengambil anime PER TAHUN RILIS (1917 sampai tahun depan), lalu satu
putaran tambahan untuk anime yang belum punya tanggal rilis.

Cara pakai (dari folder backend):
    python import_anime.py                       # semua anime
    python import_anime.py --db path/ke/file.db  # kalau nama database beda
    python import_anime.py --from-year 2020 --to-year 2020   # tes 1 tahun saja

Aman dijalankan berulang kali: data yang sudah ada diperbarui, bukan
diduplikasi. Hanya butuh Python bawaan (tanpa pip install).
"""
import argparse
import datetime
import json
import re
import sqlite3
import time
import urllib.error
import urllib.request

API_URL = "https://graphql.anilist.co"
MAX_PAGES = 100  # batas AniList: 100 halaman x 50 = 5000 anime per pencarian
FORMATS = ["TV", "TV_SHORT", "MOVIE", "SPECIAL", "OVA", "ONA", "MUSIC"]
EXTRA_STATUSES = ["NOT_YET_RELEASED", "CANCELLED", "HIATUS"]

QUERY_TEMPLATE = """
query ($page: Int) {
  Page(page: $page, perPage: 50) {
    pageInfo { hasNextPage }
    media(__ARGS__) {
      id
      title { romaji english }
      description(asHtml: false)
      genres
      status
      averageScore
      episodes
      coverImage { large }
      siteUrl
      trailer { id site }
      externalLinks { site url type }
    }
  }
}
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS animes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL UNIQUE,
    synopsis TEXT,
    genre VARCHAR(255),
    status VARCHAR(50) DEFAULT 'Ongoing',
    score FLOAT DEFAULT 0.0,
    thumbnail TEXT,
    source_url TEXT,
    total_eps INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_animes_slug ON animes(slug);
CREATE TABLE IF NOT EXISTS anime_extras (
    anime_id INTEGER PRIMARY KEY,
    anilist_id INTEGER,
    trailer_site VARCHAR(30),
    trailer_id VARCHAR(100),
    links_json TEXT,
    FOREIGN KEY (anime_id) REFERENCES animes(id) ON DELETE CASCADE
);
"""

STATUS_MAP = {
    "FINISHED": "Completed",
    "RELEASING": "Ongoing",
    "NOT_YET_RELEASED": "Upcoming",
    "CANCELLED": "Cancelled",
    "HIATUS": "Hiatus",
}


def slugify(text, anilist_id):
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return f"{base}-{anilist_id}" if base else f"anime-{anilist_id}"


def clean_text(text):
    if not text:
        return None
    return re.sub(r"<[^>]+>", "", text).strip()


def fetch_page(page, filter_args):
    args = "type: ANIME, sort: ID"
    if filter_args:
        args += ", " + filter_args
    query = QUERY_TEMPLATE.replace("__ARGS__", args)
    payload = json.dumps({"query": query, "variables": {"page": page}}).encode()
    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; AnimeImporter/1.0)",
        },
    )
    while True:
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)["data"]["Page"]
        except urllib.error.HTTPError as e:
            if e.code == 429:  # kena rate limit, tunggu lalu ulangi
                wait = int(e.headers.get("Retry-After", 60))
                print(f"  rate limit, menunggu {wait} detik...")
                time.sleep(wait + 1)
                continue
            body = e.read().decode("utf-8", errors="replace")[:500]
            print(f"\n[ERROR] AniList membalas HTTP {e.code}: {body}\n")
            raise SystemExit(1)
        except urllib.error.URLError as e:
            print(f"  koneksi gagal ({e}), coba lagi 10 detik...")
            time.sleep(10)


def save_extras(conn, slug, m):
    """Simpan trailer resmi dan link platform streaming resmi (dari AniList)."""
    row = conn.execute("SELECT id FROM animes WHERE slug = ?", (slug,)).fetchone()
    if not row:
        return
    trailer = m.get("trailer") or {}
    links = [
        {"site": l["site"], "url": l["url"]}
        for l in (m.get("externalLinks") or [])
        if l.get("type") == "STREAMING" and l.get("url") and l.get("site")
    ]
    conn.execute(
        """
        INSERT INTO anime_extras (anime_id, anilist_id, trailer_site, trailer_id, links_json)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(anime_id) DO UPDATE SET
            anilist_id=excluded.anilist_id, trailer_site=excluded.trailer_site,
            trailer_id=excluded.trailer_id, links_json=excluded.links_json
        """,
        (row[0], m["id"], trailer.get("site"), trailer.get("id"), json.dumps(links)),
    )


def save(conn, items):
    for m in items:
        title = m["title"]["english"] or m["title"]["romaji"]
        if not title:
            continue
        score = (m["averageScore"] or 0) / 10  # skala 0-10
        slug = slugify(title, m["id"])
        conn.execute(
            """
            INSERT INTO animes (title, slug, synopsis, genre, status, score,
                                thumbnail, source_url, total_eps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                title=excluded.title, synopsis=excluded.synopsis,
                genre=excluded.genre, status=excluded.status,
                score=excluded.score, thumbnail=excluded.thumbnail,
                total_eps=excluded.total_eps, updated_at=CURRENT_TIMESTAMP
            """,
            (
                title,
                slug,
                clean_text(m["description"]),
                ", ".join(m["genres"] or []),
                STATUS_MAP.get(m["status"], "Ongoing"),
                score,
                (m["coverImage"] or {}).get("large"),
                m["siteUrl"],
                m["episodes"] or 0,
            ),
        )
        save_extras(conn, slug, m)
    conn.commit()


def crawl(conn, filter_args):
    """Ambil semua halaman untuk satu filter.
    Mengembalikan True kalau sampai batas 100 halaman dan masih ada sisa."""
    for page in range(1, MAX_PAGES + 1):
        data = fetch_page(page, filter_args)
        if data["media"]:
            save(conn, data["media"])
        if not data["pageInfo"]["hasNextPage"]:
            return False
        time.sleep(0.8)  # jaga di bawah batas 90 request/menit
    return True


def crawl_with_split(conn, filter_args, label):
    """Seperti crawl, tapi kalau hasilnya melebihi 5000, dipecah per format."""
    if not crawl(conn, filter_args):
        return
    print(f"  {label}: lebih dari 5000, dipecah per format...")
    for fmt in FORMATS:
        sub = f"{filter_args}, format: {fmt}" if filter_args else f"format: {fmt}"
        if crawl(conn, sub):
            print(f"  PERINGATAN: {label} format {fmt} masih melebihi 5000")


def count_rows(conn):
    return conn.execute("SELECT COUNT(*) FROM animes").fetchone()[0]


def main():
    this_year = datetime.date.today().year
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="anime_streaming.db")
    ap.add_argument("--from-year", type=int, default=1917)
    ap.add_argument("--to-year", type=int, default=this_year + 2)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.executescript(SCHEMA)

    for year in range(args.from_year, args.to_year + 1):
        # semua anime yang mulai tayang di tahun `year` (format tanggal YYYYMMDD)
        f = f"startDate_greater: {(year - 1) * 10000 + 1231}, startDate_lesser: {(year + 1) * 10000 + 101}"
        before = count_rows(conn)
        crawl_with_split(conn, f, f"Tahun {year}")
        print(f"Tahun {year} selesai - total di database: {count_rows(conn)} (baru: {count_rows(conn) - before})")

    # anime yang belum punya tanggal rilis (belum rilis / batal / hiatus)
    for st in EXTRA_STATUSES:
        before = count_rows(conn)
        crawl_with_split(conn, f"status: {st}", f"Status {st}")
        print(f"Status {st} selesai - total di database: {count_rows(conn)} (baru: {count_rows(conn) - before})")

    print(f"Selesai. Jumlah anime di database sekarang: {count_rows(conn)}")
    conn.close()


if __name__ == "__main__":
    main()
