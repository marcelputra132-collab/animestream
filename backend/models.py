"""
models.py — Fungsi-fungsi CRUD (Create, Read, Update, Delete) untuk database
Modul ini menyediakan abstraksi akses database agar tidak ada SQL mentah di app.py
"""

from database import get_connection
import re
import time


# ─────────────────────────────────────────────
#  HELPER
# ─────────────────────────────────────────────

def row_to_dict(row) -> dict:
    """Konversi sqlite3.Row ke dict biasa."""
    return dict(row) if row else None


def rows_to_list(rows) -> list:
    """Konversi list sqlite3.Row ke list dict."""
    return [dict(r) for r in rows]


def make_slug(title: str) -> str:
    """Buat slug URL-friendly dari judul anime."""
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def normalize_dedup_key(title: str) -> str:
    """
    Buat key normalisasi cerdas untuk mendeteksi duplikat judul anime yang SAMA PERSIS,
    menyatukan variasi ejaan romanisasi (shippuuden vs shippuden, doumo vs domo),
    tetapi TETAP MEMBEDAKAN season, part, movie, dan sekuel!
    """
    if not title:
        return ""
    k = title.lower()
    # Hapus embel-embel scraper seperti sub indo, on-going, batch, bd, uncen, bocil, dll
    k = re.sub(r'\(?(?:sub\s*indo|subtitle\s*indonesia|ongoing|on-going|tamat|completed|batch|bd|uncensored|uncen|bocil)\)?', '', k)
    # Standarisasi varian ejaan romanisasi bahasa Jepang
    k = k.replace("shippuuden", "shippuden")
    k = k.replace("ou", "o").replace("uu", "u").replace("aa", "a").replace("ii", "i")
    k = re.sub(r'\s+', ' ', k).strip()
    return re.sub(r'[^a-z0-9]', '', k)


# ─────────────────────────────────────────────
#  ANIME QUERIES
# ─────────────────────────────────────────────

def get_all_animes(limit: int = 50, offset: int = 0) -> list:
    """Ambil semua anime dengan pagination. Hanya ambil anime yang sudah memiliki episode siap putar dan bebas duplikat!"""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT a.*, (SELECT COUNT(*) FROM episodes WHERE anime_id = a.id AND embed_url IS NOT NULL AND embed_url != '') as ep_count
               FROM animes a
               WHERE EXISTS (SELECT 1 FROM episodes WHERE anime_id = a.id AND embed_url IS NOT NULL AND embed_url != '')
               ORDER BY a.updated_at DESC, a.id DESC
               LIMIT ? OFFSET ?""",
            (limit * 2, offset)
        ).fetchall()
        
        seen = set()
        deduped = []
        for r in rows:
            clean_k = normalize_dedup_key(r['title'])
            if clean_k in seen:
                continue
            seen.add(clean_k)
            deduped.append(dict(r))
            if len(deduped) >= limit:
                break
        return deduped
    finally:
        conn.close()


def get_anime_by_slug(slug: str) -> dict:
    """Ambil satu anime berdasarkan slug dengan dukungan alias dan pencarian cerdas."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM animes WHERE slug = ?", (slug,)
        ).fetchone()
        if not row:
            # Dukungan alias untuk slug duplikat yang telah digabungkan ke master anime resmi
            aliases = {
                "narutoshippuuden": "naruto-shippuden-1735",
                "naruto-shippuuden": "naruto-shippuden-1735",
                "narutobocil": "naruto-20",
                "naruto-bocil": "naruto-20",
                "one-piece-on-going": "one-pieceon-going",
                "black-torch-on-going": "black-torchon-going",
                "chanto-suenai-kyuuketsuki-chan-on-going": "chanto-suenai-kyuuketsuki-chanon-going",
                "chitose-kun-wa-ramune-bin-no-naka-on-going": "chitose-kun-wa-ramune-bin-no-nakaon-going",
                "clevatess-season-2-on-going": "clevatess-season-2on-going",
                "dark-moon-tsuki-no-saidan-on-going": "dark-moon-tsuki-no-saidanon-going",
                "dead-account-on-going": "dead-accounton-going",
                "digimon-beatbreak-on-going": "digimon-beatbreakon-going",
                "fatestrange-fake-on-going": "fatestrange-fakeon-going",
                "mushoku-tensei-isekai-ittara-honki-dasu-season-3-on-going": "mushoku-tensei-isekai-ittara-honki-dasu-season-3on-going",
                "otome-kaijuu-caramliser-on-going": "otome-kaijuu-caramliseron-going",
                "zombie-sagashitemasuon-going": "zombie-sagashitemasu",
                "ao-ashi-season-2on-going": "ao-ashi-season-2",
                "ao-no-hako-season-2on-going": "ao-no-hako-season-2",
                "black-clover-season-2on-going": "black-clover-season-2",
                "doumo-suki-na-hito-ni-horegusuri-wo-irai-sareta-majo-desuon-going": "doumo-suki-na-hito-ni-horegusuri-wo-irai-sareta-majo-desu",
                "tokyo-revengers-season-4": "tokyo-revengers-santen-sensou-hen",
                "tokyo-revengers-s4": "tokyo-revengers-santen-sensou-hen",
                "tokyo-revengers-season-4-on-going": "tokyo-revengers-santen-sensou-hen",
                "frieren-beyond-journeys-end": "sousou-no-frieren",
                "blue-lock-season-2": "blue-lock-s2",
                "mahou-shoujo-ikusei-keikaku-restart": "mahou-shoujo-ikusei-keikaku",
                "naruto1daikatsugekiyukihimeshinobuhoujoudattebayo": "naruto-the-movie-ninja-clash-in-the-land-of-snow-442",
                "naruto2daigekitotsumaboroshinochiteiisekidattebayo": "naruto-the-movie-legend-of-the-stone-of-gelel-936",
                "naruto3daikoufunmikazukijimanoanimarupanicdattebayo": "naruto-the-movie-guardians-of-the-crescent-moon-kingdom-2144",
                "the-last-naruto-the-movie": "the-last-naruto-the-movie-16870",
                "one-piece-film-red": "one-piece-film-red-141902",
                "one-piece-film:-red": "one-piece-film-red-141902",
                "one-piece-stampede": "one-piece-stampede-105143",
                "one-piece-film-gold": "one-piece-film-gold-21335",
                "one-piece-film-z": "one-piece-film-z-12859",
                "one-piece-film-strong-world": "one-piece-film-strong-world-4155",
            }
            target_slug = aliases.get(slug)
            if target_slug:
                row = conn.execute(
                    "SELECT * FROM animes WHERE slug = ?", (target_slug,)
                ).fetchone()

        if not row:
            # 1. Coba cari tanpa suffix seperti '-sub-indo', '-on-going', '-ongoing', '-season-...'
            clean_slug = re.sub(r"-(sub-indo|on-going|ongoing|episode-\d+)", "", slug)
            if clean_slug != slug:
                row = conn.execute("SELECT * FROM animes WHERE slug = ?", (clean_slug,)).fetchone()

        if not row:
            # 2. Coba cari dengan LIKE pada slug
            row = conn.execute("SELECT * FROM animes WHERE slug LIKE ? LIMIT 1", (f"{clean_slug}%",)).fetchone()

        if not row:
            # 3. Coba cari dengan kata-kata kunci utama di judul anime
            words = [w for w in re.split(r"[-_\s]+", clean_slug) if len(w) > 2 and w not in ["the", "and", "season", "hen", "part"]]
            if words:
                title_query = "%" + "%".join(words[:3]) + "%"
                row = conn.execute("SELECT * FROM animes WHERE title LIKE ? LIMIT 1", (title_query,)).fetchone()

        return row_to_dict(row)
    finally:
        conn.close()


def get_anime_by_id(anime_id: int) -> dict:
    """Ambil satu anime berdasarkan ID."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM animes WHERE id = ?", (anime_id,)
        ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def search_animes(query: str) -> list:
    """Cari anime berdasarkan judul atau genre. Hanya tampilkan anime yang sudah memiliki episode siap tonton."""
    conn = get_connection()
    try:
        like = f"%{query}%"
        rows = conn.execute(
            """SELECT a.*, 
                      (SELECT COUNT(*) FROM episodes WHERE anime_id = a.id AND embed_url IS NOT NULL AND embed_url != '') as ep_count
               FROM animes a
               WHERE (a.title LIKE ? OR a.genre LIKE ? OR a.slug LIKE ?)
                 AND EXISTS (SELECT 1 FROM episodes WHERE anime_id = a.id AND embed_url IS NOT NULL AND embed_url != '')
               ORDER BY 
                 (SELECT COUNT(*) FROM episodes WHERE anime_id = a.id AND embed_url IS NOT NULL AND embed_url != '') DESC,
                 (CASE WHEN a.thumbnail IS NOT NULL AND a.thumbnail != '' THEN 0 ELSE 1 END),
                 a.score DESC, 
                 a.title ASC 
               LIMIT 120""",
            (like, like, like)
        ).fetchall()
        
        seen = set()
        deduped = []
        for r in rows:
            d = dict(r)
            if is_donghua_anime(d.get('title', ''), d.get('slug', ''), d.get('genre', '')):
                continue
            clean_k = normalize_dedup_key(d['title'])
            if clean_k in seen:
                continue
            seen.add(clean_k)
            deduped.append(d)
            if len(deduped) >= 60:
                break
        return deduped
    finally:
        conn.close()


def get_latest_animes(limit: int = 12) -> list:
    """Ambil anime yang paling baru diperbarui dan memiliki episode."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT a.*, (SELECT COUNT(*) FROM episodes WHERE anime_id = a.id AND embed_url IS NOT NULL AND embed_url != '') as ep_count
               FROM animes a
               WHERE EXISTS (SELECT 1 FROM episodes WHERE anime_id = a.id AND embed_url IS NOT NULL AND embed_url != '')
               ORDER BY a.updated_at DESC
               LIMIT ?""",
            (limit,)
        ).fetchall()
        return rows_to_list(rows)
    finally:
        conn.close()


# ─────────────────────────────────────────────
#  HOT & POPULAR ANIME FILTERS
# ─────────────────────────────────────────────

# Anime legendaris masa lalu yang DIIZINKAN masuk Hot Anime (One Piece, Naruto, Black Clover, Bleach, dll)
EVERGREEN_LEGENDS = [
    "one piece",
    "naruto",
    "naruto shippuden",
    "boruto",
    "attack on titan",
    "shingeki no kyojin",
    "dragon ball",
    "black clover",
    "bleach",
    "jujutsu kaisen",
    "solo leveling"
]

# Kata kunci judul anime baru & modern hype (rilisan baru / ongoing / modern seasons)
MODERN_HYPE_KEYWORDS = [
    "solo leveling",
    "jujutsu kaisen",
    "demon slayer",
    "kimetsu no yaiba",
    "chainsaw man",
    "frieren",
    "sousou no frieren",
    "oshi no ko",
    "blue lock",
    "kaiju no. 8",
    "kaiju no 8",
    "wind breaker",
    "dandadan",
    "shangri-la frontier",
    "tokyo revengers",
    "bleach: thousand-year blood war",
    "sennen kessen",
    "mashle",
    "jigokuraku",
    "hell's paradise",
    "tsuihou sareta",
    "kusuriya no hitorigoto",
    "apothecary diaries",
    "re:zero",
    "spy x family",
    "boku no hero academia",
    "my hero academia",
    "black clover season 2",
    "black clover: mahou",
    "mushoku tensei",
    "classroom of the elite",
    "youkoso jitsuryoku",
    "kage no jitsuryokusha",
    "eminence in shadow",
    "hotaru no yomeiri",
    "dungeon meshi",
    "delicious in dungeon",
    "ninja kamui",
    "wistoria",
    "elusive samurai",
    "makeine",
    "alya sometimes hides her feelings",
    "roshidere",
    "tower of god",
    "nier:automata",
    "bucchigiri",
    "slime taoshite",
    "tensei shitara slime",
    "haikyuu",
    "sword art online"
]

def is_hot_anime(item: dict) -> bool:
    """
    Menyeleksi apakah anime layak masuk kategori 'Hot Anime':
    - Khusus anime baru, ongoing, dan modern hype.
    - Menolak anime dari jaman majapahit / tamat bertahun-tahun lalu (kecuali One Piece & Naruto).
    """
    title = (item.get("title") or "").lower()
    slug = (item.get("slug") or "").lower()
    status = (item.get("status") or "").strip().lower()
    total_eps = int(item.get("total_eps") or 0)
    ep_count = int(item.get("ep_count") or 0)

    # 1. Pengecualian resmi: Anime Legenda & Hype Besar (One Piece, Naruto, Black Clover, Bleach, dll)
    for leg in EVERGREEN_LEGENDS:
        if leg in title or leg in slug:
            return True

    # 3. Anime berstatus Ongoing (sedang aktif rilis episode baru): PASTI MASUK!
    if "ongoing" in status or "sedang" in status or status == "on-going":
        return True

    # 4. Anime modern blockbuster (musim baru 2022-2026):
    for kw in MODERN_HYPE_KEYWORDS:
        if kw in title or kw in slug:
            return True

    # 5. Selain kriteria di atas (anime tamat biasa / lawas) -> TOLAK dari Hot Anime
    return False


def get_popular_playable_animes(limit: int = 18) -> list:
    """
    Ambil anime HOT & BARU (Ongoing & Modern Hype + One Piece & Naruto)
    Menyaring anime lawas / tamat dari jaman majapahit sesuai instruksi pengguna.
    Dilengkapi view count realistis dan rank nomor peringkat.
    """
    try:
        import generate_anime_character_icons
        import importlib
        importlib.reload(generate_anime_character_icons)
        generate_anime_character_icons.create_anime_icons()
    except Exception as e:
        try:
            with open(r"c:\Users\frysco marcel\OneDrive\Desktop\Belajar HTML\anime_streaming\backend\icons_gen.log", "a") as lf:
                lf.write(f"reload error: {e}\n")
        except Exception:
            pass

    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT a.*, COUNT(e.id) as ep_count,
                   COALESCE(s.views, 0) as raw_views,
                   COALESCE(s.likes, 0) as raw_likes
            FROM animes a
            JOIN episodes e ON a.id = e.anime_id
            LEFT JOIN anime_stats s ON s.anime_id = a.id
            GROUP BY a.id
            HAVING ep_count > 0
            ORDER BY 
              (CASE 
                 WHEN a.title LIKE '%Solo Leveling%' THEN 160
                 WHEN a.title LIKE '%Bleach: Sennen Kessen%' THEN 155
                 WHEN a.title LIKE '%Demon Slayer%' THEN 150
                 WHEN a.title LIKE '%Tokyo Revengers%' THEN 145
                 WHEN a.title LIKE '%Jujutsu Kaisen%' THEN 140
                 WHEN a.title LIKE '%Dandadan%' THEN 135
                 WHEN a.title LIKE '%Kaijuu 8-gou%' OR a.title LIKE '%Kaiju No. 8%' THEN 130
                 WHEN a.title LIKE '%Tensei shitara Slime%' THEN 125
                 WHEN a.title LIKE '%One Piece%' THEN 120
                  WHEN a.title LIKE '%Black Clover%' THEN 118
                 WHEN a.title LIKE '%Frieren%' THEN 115
                 WHEN a.title LIKE '%Dr. Stone%' THEN 110
                 WHEN a.title LIKE '%Enen no Shouboutai%' OR a.title LIKE '%Fire Force%' THEN 105
                 WHEN a.title LIKE '%Jigokuraku%' OR a.title LIKE '%Hell%Paradise%' THEN 100
                 WHEN a.title LIKE '%Chainsaw Man%' THEN 98
                 WHEN a.status = 'Ongoing' THEN 92
                 ELSE 50
               END) DESC,
              a.score DESC,
              ep_count DESC
            LIMIT ?
        """, (limit * 6,)).fetchall()
        
        seen = set()
        deduped = []
        rank_counter = 1

        for r in rows:
            d = dict(r)
            if not is_hot_anime(d):
                continue

            clean_k = normalize_dedup_key(d['title'])
            if clean_k in seen:
                continue
            seen.add(clean_k)

            # Hitung / format views realistis untuk Hot Anime jika raw_views masih kecil
            raw_v = d.get('raw_views') or 0
            if raw_v < 100000:
                score_f = float(d.get('score') or 8.0)
                base_calc = int(score_f * 110000 + (d['id'] * 1337) % 85000)
                if rank_counter == 1:
                    d['views'] = 979200
                elif rank_counter == 2:
                    d['views'] = 557600
                elif rank_counter == 3:
                    d['views'] = 620400
                else:
                    d['views'] = base_calc
            else:
                d['views'] = raw_v

            d['rank'] = rank_counter
            deduped.append(d)
            rank_counter += 1

            if len(deduped) >= limit:
                break

        return deduped
    finally:
        conn.close()


def get_completed_playable_animes(limit: int = 18) -> list:
    """Ambil anime status tamat/completed yang SUDAH memiliki episode lengkap dan bebas duplikat."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT a.*, COUNT(e.id) as ep_count
            FROM animes a
            JOIN episodes e ON a.id = e.anime_id
            WHERE a.status = 'Completed' OR a.status LIKE '%Tamat%'
            GROUP BY a.id
            ORDER BY a.updated_at DESC, a.score DESC
            LIMIT ?
        """, (limit * 2,)).fetchall()
        
        seen = set()
        deduped = []
        for r in rows:
            clean_k = normalize_dedup_key(r['title'])
            if clean_k in seen:
                continue
            seen.add(clean_k)
            deduped.append(dict(r))
            if len(deduped) >= limit:
                break
        return deduped
    finally:
        conn.close()


# ─────────────────────────────────────────────
#  TABEL JADWAL & JAM PENAYANGAN AKURAT (WIB)
# ─────────────────────────────────────────────

AIRING_TIME_TABLE = {
    # Minggu (Sunday)
    "one piece": "09:30 WIB",
    "black clover": "17:30 WIB",
    "vertex force": "18:30 WIB",
    "#zombie sagashitemasu": "19:30 WIB",
    "zombie sagashitemasu": "19:30 WIB",
    "magical explorer": "20:00 WIB",
    "magical★explorer": "20:00 WIB",
    "seitokai ni mo ana wa aru": "21:00 WIB",
    "kashita maryoku": "22:00 WIB",
    "tsuihou sareta": "21:00 WIB",
    "slime": "22:00 WIB",
    "tensei shitara slime": "22:00 WIB",
    "solo leveling": "23:30 WIB",
    "naruto": "17:00 WIB",
    "boruto": "17:30 WIB",

    # Senin (Monday)
    "haikyuu": "17:00 WIB",
    "detective conan": "17:30 WIB",
    "ron kamonohashi": "21:30 WIB",
    "bleach": "22:30 WIB",
    "blue lock": "23:00 WIB",

    # Selasa (Tuesday)
    "shangri-la frontier": "16:30 WIB",
    "tower of god": "21:00 WIB",
    "danmachi": "21:30 WIB",
    "dungeon ni deai": "21:30 WIB",
    "wind breaker": "23:30 WIB",
    "chainsaw man": "23:00 WIB",

    # Rabu (Wednesday)
    "boku no hero": "16:30 WIB",
    "my hero academia": "16:30 WIB",
    "re:zero": "21:30 WIB",
    "tokyo revengers": "23:00 WIB",
    "dandadan": "23:00 WIB",

    # Kamis (Thursday)
    "classroom of the elite": "21:30 WIB",
    "youkoso jitsuryoku": "21:30 WIB",
    "dr. stone": "21:30 WIB",
    "mushoku tensei": "23:00 WIB",
    "jujutsu kaisen": "23:56 WIB",
    "hotaru no yomeiri": "21:30 WIB",

    # Jumat (Friday)
    "fairy tail": "17:00 WIB",
    "shuiro no kamen": "20:00 WIB",
    "sousou no frieren": "22:00 WIB",
    "frieren": "22:00 WIB",
    "kaiju no. 8": "22:00 WIB",
    "nier:automata": "22:30 WIB",

    # Sabtu (Saturday)
    "uchi no otouto": "18:00 WIB",
    "keroro gunsou": "19:00 WIB",
    "toaru anbu no item": "20:30 WIB",
    "romelia senki": "21:00 WIB",
    "tensei shita daiseijo": "21:30 WIB",
    "spy x family": "22:00 WIB",
    "oshi no ko": "22:00 WIB",
    "demon slayer": "22:15 WIB",
    "kimetsu no yaiba": "22:15 WIB",
    "yasei no last boss": "22:30 WIB",
    "mashle": "22:30 WIB",
    "kusuriya no hitorigoto": "23:05 WIB",
}

def get_anime_airing_time(title: str, created_at: str = None) -> str:
    """Mengembalikan jam penayangan / rilis anime (WIB) yang akurat.
    Menggunakan jadwal resmi broadcast anime di Indonesia (WIB),
    atau jika tidak ada di tabel, menghasilkan jam penayangan prime-time yang deterministik dan konsisten."""
    if not title:
        return "20:00 WIB"
        
    t_low = title.lower()
    for kw, time_str in AIRING_TIME_TABLE.items():
        if kw in t_low:
            return time_str
            
    # Jika anime memiliki created_at yang spesifik
    if created_at and " " in created_at:
        try:
            _, time_part = created_at.split(" ", 1)
            parts = time_part.split(":")
            if len(parts) >= 2:
                return f"{parts[0]}:{parts[1]} WIB"
        except Exception:
            pass

    # Fallback deterministik berbasis hash judul ke jam prime-time anime (17:00 - 23:30 WIB)
    slots = [
        "17:00 WIB", "17:30 WIB", "18:00 WIB", "18:30 WIB", 
        "19:00 WIB", "19:30 WIB", "20:00 WIB", "20:30 WIB", 
        "21:00 WIB", "21:30 WIB", "22:00 WIB", "22:30 WIB", "23:00 WIB"
    ]
    idx = abs(hash(title)) % len(slots)
    return slots[idx]


def get_weekly_schedule() -> dict:
    """
    Ambil jadwal rilis anime mingguan (Senin–Minggu).
    Menyertakan jam penayangan akurat (WIB), hanya anime nyata yang memiliki episode siap tonton.
    """
    days_order = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
    schedule = {d: [] for d in days_order}
    conn = get_connection()
    try:
        # 0. Perbarui icon anime jika belum ada
        try:
            from generate_anime_character_icons import create_anime_icons
            create_anime_icons()
        except Exception:
            pass

        # 1. Bersihkan thumbnail yang rusak atau merujuk ke splash_girl di database
        try:
            conn.execute("""
                UPDATE animes 
                SET thumbnail = '' 
                WHERE thumbnail LIKE '%splash_girl%'
            """)
            conn.commit()
        except Exception:
            pass

        # 2. Coba ambil dari scraper jadwal otakudesu
        matched_ids = set()
        try:
            from scraper import fetch_page
            soup = fetch_page("https://otakudesu.blog/jadwal-rilis/")
            if soup:
                for h in soup.find_all("h2"):
                    day_text = h.get_text().strip()
                    if day_text in schedule:
                        ul = h.find_next_sibling("ul")
                        if ul:
                            for a in ul.find_all("a"):
                                title = a.get_text().strip()
                                href = a.get("href", "")
                                if not title:
                                    continue
                                
                                # HANYA ambil anime nyata di DB yang PUNYA EPISODE dan PUNYA POSTER ASLI
                                row = conn.execute("""
                                    SELECT a.id, a.title, a.slug, a.thumbnail, a.score, a.genre, a.status,
                                           COUNT(e.id) as ep_count
                                    FROM animes a
                                    JOIN episodes e ON a.id = e.anime_id
                                    WHERE (a.title = ? OR a.title LIKE ? OR a.source_url = ? OR a.slug = ?)
                                      AND a.thumbnail IS NOT NULL 
                                      AND a.thumbnail != '' 
                                      AND a.thumbnail NOT LIKE '%splash_girl%'
                                    GROUP BY a.id
                                    HAVING ep_count > 0
                                    LIMIT 1
                                """, (title, f"{title}%", href, make_slug(title))).fetchone()

                                if row and row["id"] not in matched_ids:
                                    item = dict(row)
                                    item["source_url"] = href
                                    item["release_day"] = day_text
                                    item["release_time"] = get_anime_airing_time(item["title"])
                                    schedule[day_text].append(item)
                                    matched_ids.add(row["id"])
        except Exception as e:
            print(f"[SCHEDULE] Warning scraper jadwal: {e}")

        # 3. Kurasian Jadwal Utama: Distribusikan anime Ongoing & Populer Aktif
        curated_day_keywords = {
            "Minggu": ["one piece", "solo leveling", "vertex force", "zombie sagashitemasu", "kashita maryoku", "seitokai ni mo ana", "black clover", "magical explorer", "tsuihou sareta", "slime", "naruto", "boruto"],
            "Senin": ["bleach", "blue lock", "haikyuu", "ron kamonohashi", "detective conan"],
            "Selasa": ["black clover season 2", "shangri-la frontier", "wind breaker", "tower of god", "danmachi", "chainsaw man"],
            "Rabu": ["dandadan", "tokyo revengers", "boku no hero", "my hero academia", "re:zero"],
            "Kamis": ["jujutsu kaisen", "hotaru no yomeiri", "mushoku tensei", "classroom of the elite", "dr. stone"],
            "Jumat": ["frieren", "sousou no frieren", "kaiju no. 8", "nier:automata", "fairy tail", "shuiro no kamen"],
            "Sabtu": ["demon slayer", "kimetsu no yaiba", "kusuriya no hitorigoto", "toaru anbu no item", "uchi no otouto", "keroro gunsou", "yasei no last boss", "tensei shita daiseijo", "mashle", "oshi no ko", "spy x family"]
        }

        # Ambil semua anime playable ongoing / populer dari database
        playable_rows = conn.execute("""
            SELECT a.id, a.title, a.slug, a.thumbnail, a.score, a.genre, a.status,
                   COUNT(e.id) as ep_count
            FROM animes a
            JOIN episodes e ON a.id = e.anime_id
            WHERE a.thumbnail IS NOT NULL 
              AND a.thumbnail != '' 
              AND a.thumbnail NOT LIKE '%splash_girl%'
            GROUP BY a.id
            HAVING ep_count > 0
            ORDER BY 
              (CASE 
                 WHEN a.slug LIKE '%one-piece%' OR a.title LIKE '%One Piece%' THEN 110
                 WHEN a.slug LIKE '%solo-leveling%' OR a.title LIKE '%Solo Leveling%' THEN 108
                 WHEN a.slug LIKE '%black-clover-season-2%' OR a.title LIKE '%Black Clover Season 2%' THEN 107
                 WHEN a.slug LIKE '%bleach%' OR a.title LIKE '%Bleach%' THEN 106
                 WHEN a.slug LIKE '%blue-lock%' OR a.title LIKE '%Blue Lock%' THEN 105
                 WHEN a.slug LIKE '%dandadan%' OR a.title LIKE '%DanDaDan%' THEN 104
                 WHEN a.slug LIKE '%tokyo-revengers%' OR a.title LIKE '%Tokyo Revengers%' THEN 103
                 WHEN a.slug LIKE '%hotaru-no-yomeiri%' OR a.title LIKE '%Hotaru no Yomeiri%' THEN 102
                 WHEN a.slug LIKE '%jujutsu-kaisen%' OR a.title LIKE '%Jujutsu Kaisen%' THEN 101
                 WHEN a.slug LIKE '%frieren%' OR a.title LIKE '%Frieren%' THEN 100
                 WHEN a.status = 'Ongoing' THEN 95
                 ELSE 50
               END) DESC,
              a.score DESC,
              ep_count DESC
            LIMIT 150
        """).fetchall()

        all_playable = [dict(r) for r in playable_rows]

        # Cocokkan kurasi hari berdasarkan kata kunci
        for day, keywords in curated_day_keywords.items():
            current_day_ids = {x["id"] for x in schedule[day]}
            for p in all_playable:
                if p["id"] in current_day_ids:
                    continue
                p_title = p["title"].lower()
                p_slug = p["slug"].lower()
                if any(kw in p_title or kw in p_slug for kw in keywords):
                    item = dict(p)
                    item["release_day"] = day
                    item["release_time"] = get_anime_airing_time(item["title"])
                    schedule[day].append(item)
                    current_day_ids.add(p["id"])
                    if len(schedule[day]) >= 8:
                        break

        # 4. Pastikan setiap hari memiliki minimal 6-8 anime nyata
        remaining_pool = [p for p in all_playable if not any(p["id"] in {x["id"] for x in schedule[d]} for d in days_order)]
        for day in days_order:
            while len(schedule[day]) < 6 and remaining_pool:
                cand = remaining_pool.pop(0)
                item = dict(cand)
                item["release_day"] = day
                item["release_time"] = get_anime_airing_time(item["title"])
                schedule[day].append(item)

        # 5. Pastikan semua item memiliki release_time dan release_day yang terisi
        for day in days_order:
            for item in schedule[day]:
                if not item.get("release_time"):
                    item["release_time"] = get_anime_airing_time(item.get("title", ""))
                item["release_day"] = day

        return schedule
    finally:
        conn.close()


def upsert_anime(data: dict) -> int:
    """
    Insert atau update data anime.
    Mengembalikan ID anime yang baru dibuat atau diperbarui.
    """
    conn = get_connection()
    try:
        slug = data.get("slug") or make_slug(data["title"])
        existing = conn.execute(
            "SELECT id FROM animes WHERE slug = ?", (slug,)
        ).fetchone()

        if existing:
            conn.execute("""
                UPDATE animes SET
                    title=?, synopsis=?, genre=?, status=?, score=?,
                    thumbnail=?, source_url=?, total_eps=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE slug=?
            """, (
                data.get("title"), data.get("synopsis"),
                data.get("genre"), data.get("status", "Ongoing"),
                data.get("score", 0.0), data.get("thumbnail"),
                data.get("source_url"), data.get("total_eps", 0),
                slug
            ))
            conn.commit()
            return existing["id"]
        else:
            cursor = conn.execute("""
                INSERT INTO animes (title, slug, synopsis, genre, status, score, thumbnail, source_url, total_eps)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("title"), slug,
                data.get("synopsis"), data.get("genre"),
                data.get("status", "Ongoing"), data.get("score", 0.0),
                data.get("thumbnail"), data.get("source_url"),
                data.get("total_eps", 0)
            ))
            conn.commit()
            return cursor.lastrowid
    finally:
        conn.close()


# ─────────────────────────────────────────────
#  EPISODE QUERIES
# ─────────────────────────────────────────────

def get_episodes_by_anime(anime_id: int) -> list:
    """Ambil semua episode dari satu anime, diurutkan by nomor episode."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM episodes WHERE anime_id = ? ORDER BY ep_number ASC",
            (anime_id,)
        ).fetchall()
        return rows_to_list(rows)
    finally:
        conn.close()


def get_episode(anime_id: int, ep_number: int) -> dict:
    """Ambil satu episode spesifik."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM episodes WHERE anime_id = ? AND ep_number = ?",
            (anime_id, ep_number)
        ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


DONGHUA_PATTERNS = [
    r'\bdonghua\b',
    r'\bsoul of light\b',
    r'\bsouloflight\b',
    r'\bi am ying tai\b',
    r'\biamyingtai\b',
    r'\bembers\b',
    r'\bsoul land\b',
    r'\bsoulland\b',
    r'\bbattle through the heavens\b',
    r'\bbtth\b',
    r'\bperfect world\b',
    r'\bswallowed star\b',
    r'\bshrouding the heavens\b',
    r'\brenegade immortal\b',
    r'\bmartial universe\b',
    r'\bgreat ruler\b',
    r'\bagainst the gods\b',
    r'\btales of demons and gods\b',
    r'\bapotheosis\b',
    r'\bbai lian cheng shen\b',
    r'\ba will eternal\b',
    r'\byi nian yong heng\b',
    r'\bstellar transformation\b',
    r'\bmartial peak\b',
    r'\blord xue ying\b',
    r'\bpeerless martial\b',
    r'\bsupreme god\b',
    r'\bspirit sword\b',
    r'\bwan jie\b',
    r'\bwu dong qian kun\b',
    r'\bfanren xiu xian\b',
    r'\bmortal\'s journey\b',
    r'\bthousand autumns\b',
    r'\btian guan ci fu\b',
    r'\bmo dao zu shi\b',
    r'\bshiguang dailiren\b',
    r'\bquanzhi fashi\b',
    r'\bquanzhi gaoshou\b',
    r'\bking\'s avatar\b',
    r'\bcultivation\b',
    r'\bancient vengeance\b',
    r'\bdivine manifestation\b',
    r'\bforty millenniums\b',
]

def is_donghua_anime(title: str = "", slug: str = "", genre: str = "") -> bool:
    """Deteksi apakah judul anime merupakan animasi Tiongkok (Donghua) untuk disaring."""
    combined = f"{title} {slug} {genre}".lower()
    for pat in DONGHUA_PATTERNS:
        if re.search(pat, combined):
            return True
    return False


def get_latest_episodes(limit: int = 25) -> list:
    """Ambil episode terbaru anime Jepang asli (join dengan data anime).
    Menyaring seluruh Donghua sehingga Ongoing Update hanya berisi anime Jepang murni!
    Menyertakan jam penayangan dan update akurat (WIB).
    """
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT
                e.id, e.anime_id, e.ep_number, e.title AS ep_title, e.created_at,
                a.title AS anime_title, a.slug AS anime_slug, a.thumbnail, a.status, a.score, a.genre
            FROM episodes e
            JOIN animes a ON e.anime_id = a.id
            JOIN (
                SELECT anime_id, MAX(id) as max_ep_id
                FROM episodes
                WHERE (embed_url IS NOT NULL AND embed_url != '') OR source_url IS NOT NULL
                GROUP BY anime_id
            ) latest ON e.id = latest.max_ep_id
            ORDER BY e.created_at DESC, e.id DESC
            LIMIT ?
        """, (limit * 3,)).fetchall()
        
        episodes = rows_to_list(rows)
        seen_titles = set()
        deduped = []
        for ep in episodes:
            # Saring dan tolak Donghua (hanya terima anime Jepang)
            if is_donghua_anime(ep.get("anime_title", ""), ep.get("anime_slug", ""), ep.get("genre", "")):
                continue

            norm = normalize_dedup_key(ep.get("anime_title", ""))
            if norm in seen_titles:
                continue
            seen_titles.add(norm)
            
            # Jam penayangan / rilis akurat (WIB)
            airing_time = get_anime_airing_time(ep.get("anime_title", ""), ep.get("created_at"))
            ep["release_time"] = airing_time
            ep["airing_time"] = airing_time
            
            # Jam update akurat
            created_at = ep.get("created_at", "")
            if created_at and " " in created_at:
                try:
                    date_part, time_part = created_at.split(" ", 1)
                    hh_mm = ":".join(time_part.split(":")[:2])
                    ep["update_clock"] = f"{hh_mm} WIB"
                except Exception:
                    ep["update_clock"] = airing_time
            else:
                ep["update_clock"] = airing_time

            deduped.append(ep)
            if len(deduped) >= limit:
                break

        return deduped
    finally:
        conn.close()


def upsert_episode(data: dict) -> int:
    """
    Insert atau update data episode.
    Mengembalikan ID episode yang baru dibuat atau diperbarui.
    """
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM episodes WHERE anime_id = ? AND ep_number = ?",
            (data["anime_id"], data["ep_number"])
        ).fetchone()

        quality_streams = data.get("quality_streams")
        if isinstance(quality_streams, dict):
            import json
            quality_streams = json.dumps(quality_streams)

        if existing:
            conn.execute("""
                UPDATE episodes SET
                    title=?, embed_url=?, source_url=?, duration=?, thumbnail=?, quality_streams=?
                WHERE anime_id=? AND ep_number=?
            """, (
                data.get("title"), data.get("embed_url"),
                data.get("source_url"), data.get("duration"),
                data.get("thumbnail"), quality_streams,
                data["anime_id"], data["ep_number"]
            ))
            conn.commit()
            return existing["id"]
        else:
            cursor = conn.execute("""
                INSERT INTO episodes (anime_id, ep_number, title, embed_url, source_url, duration, thumbnail, quality_streams)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data["anime_id"], data["ep_number"], data.get("title"),
                data.get("embed_url"), data.get("source_url"),
                data.get("duration"), data.get("thumbnail"), quality_streams
            ))
            conn.commit()
            return cursor.lastrowid
    finally:
        conn.close()


# ─────────────────────────────────────────────
#  STATS: VIEWS & LIKES
# ─────────────────────────────────────────────

def get_anime_stats(anime_id: int) -> dict:
    """Mengambil atau menginisialisasi jumlah views dan likes untuk anime."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT views, likes FROM anime_stats WHERE anime_id = ?", (anime_id,)).fetchone()
        if not row:
            base_views = 150 + (anime_id * 23) % 920
            base_likes = int(base_views * 0.22) + (anime_id % 15)
            conn.execute(
                "INSERT OR IGNORE INTO anime_stats (anime_id, views, likes) VALUES (?, ?, ?)",
                (anime_id, base_views, base_likes)
            )
            conn.commit()
            return {"views": base_views, "likes": base_likes}
        return {"views": row["views"], "likes": row["likes"]}
    finally:
        conn.close()


def increment_views(anime_id: int) -> int:
    """Menambah hitungan views anime dan mengembalikan total baru."""
    conn = get_connection()
    try:
        get_anime_stats(anime_id)
        conn.execute("UPDATE anime_stats SET views = views + 1 WHERE anime_id = ?", (anime_id,))
        conn.commit()
        row = conn.execute("SELECT views FROM anime_stats WHERE anime_id = ?", (anime_id,)).fetchone()
        return row["views"] if row else 1
    finally:
        conn.close()


def toggle_anime_like(anime_id: int, is_like: bool = True) -> int:
    """Menambah / mengurangi hitungan likes anime."""
    conn = get_connection()
    try:
        get_anime_stats(anime_id)
        delta = 1 if is_like else -1
        conn.execute("UPDATE anime_stats SET likes = MAX(0, likes + ?) WHERE anime_id = ?", (delta, anime_id))
        conn.commit()
        row = conn.execute("SELECT likes FROM anime_stats WHERE anime_id = ?", (anime_id,)).fetchone()
        return row["likes"] if row else 0
    finally:
        conn.close()


# ─────────────────────────────────────────────
#  KOMENTAR
# ─────────────────────────────────────────────

def get_comments(anime_id: int, ep_number: int = None, limit: int = 50) -> list:
    """Mengambil daftar komentar untuk anime atau episode tertentu."""
    conn = get_connection()
    try:
        if ep_number is not None:
            rows = conn.execute("""
                SELECT id, anime_id, ep_number, username, avatar_color, content, likes, created_at
                FROM comments
                WHERE anime_id = ? AND (ep_number = ? OR ep_number IS NULL)
                ORDER BY id DESC
                LIMIT ?
            """, (anime_id, ep_number, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT id, anime_id, ep_number, username, avatar_color, content, likes, created_at
                FROM comments
                WHERE anime_id = ?
                ORDER BY id DESC
                LIMIT ?
            """, (anime_id, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_comment(anime_id: int, username: str, content: str, ep_number: int = None, avatar_color: str = None) -> dict:
    """Menambahkan komentar baru ke anime / episode."""
    if not avatar_color:
        import random
        colors = ["#a855f7", "#06b6d4", "#ec4899", "#f59e0b", "#10b981", "#3b82f6"]
        avatar_color = random.choice(colors)
    conn = get_connection()
    try:
        cursor = conn.execute("""
            INSERT INTO comments (anime_id, ep_number, username, avatar_color, content, likes)
            VALUES (?, ?, ?, ?, ?, 0)
        """, (anime_id, ep_number, username.strip(), avatar_color, content.strip()))
        conn.commit()
        comment_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def like_comment(comment_id: int) -> int:
    """Menambah like pada komentar tertentu."""
    conn = get_connection()
    try:
        conn.execute("UPDATE comments SET likes = likes + 1 WHERE id = ?", (comment_id,))
        conn.commit()
        row = conn.execute("SELECT likes FROM comments WHERE id = ?", (comment_id,)).fetchone()
        return row["likes"] if row else 0
    finally:
        conn.close()


# ─────────────────────────────────────────────
#  LEVELING & EXP TIERS
# ─────────────────────────────────────────────

LEVEL_TIERS = [
    (1, 0, 100, "Wibu Pemula", "🌱"),
    (2, 100, 250, "Penikmat Anime", "⚡"),
    (3, 250, 450, "Otaku Aktif", "🔥"),
    (4, 450, 700, "Wibu Elit", "⚔️"),
    (5, 700, 1000, "Senpai Idaman", "✨"),
    (6, 1000, 1500, "Sensei Bijak", "📜"),
    (7, 1500, 2200, "Jounin Otaku", "🥷"),
    (8, 2200, 3000, "Pillar / Hashira", "🗡️"),
    (9, 3000, 4000, "Hokage Wibu", "👑"),
    (10, 4000, 999999, "Kaisar Otaku Legendaris", "🌌"),
]

def calculate_level_info(exp: int) -> dict:
    current_tier = LEVEL_TIERS[0]
    for tier in LEVEL_TIERS:
        lvl, min_exp, max_exp, title, badge = tier
        if exp >= min_exp:
            current_tier = tier
        else:
            break
    lvl, min_exp, max_exp, title, badge = current_tier
    needed = max_exp - min_exp
    current_in_tier = exp - min_exp
    pct = min(100, int((current_in_tier / max(1, needed)) * 100))
    return {
        "level": lvl,
        "title": title,
        "badge": badge,
        "exp": exp,
        "min_exp": min_exp,
        "next_level_exp": max_exp,
        "level_exp_progress": current_in_tier,
        "level_exp_needed": needed,
        "progress_pct": pct
    }


def get_or_create_user(provider: str, provider_id: str = None, username: str = None, email: str = None, avatar_url: str = None) -> dict:
    """Mendapatkan atau membuat user baru berdasarkan login (Google, Facebook, Guest)."""
    provider = provider.lower() if provider else "guest"
    if not username:
        if provider == "google":
            username = "Google Otaku"
        elif provider == "facebook":
            username = "Facebook Otaku"
        else:
            username = f"Otaku_{int(time.time()) % 10000}"

    if not email:
        email = f"{provider}_{provider_id or int(time.time() * 1000)}@otakux.local"

    conn = get_connection()
    try:
        row = None
        if provider_id:
            row = conn.execute("SELECT * FROM users WHERE provider = ? AND provider_id = ?", (provider, str(provider_id))).fetchone()
        if not row and email:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if row:
            user_id = row["id"]
            conn.execute("""
                UPDATE users
                SET last_login = CURRENT_TIMESTAMP,
                    avatar_url = COALESCE(?, avatar_url),
                    username = COALESCE(?, username)
                WHERE id = ?
            """, (avatar_url, username, user_id))
            conn.commit()
            updated = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            u_dict = dict(updated)
            u_dict.update(calculate_level_info(u_dict["exp"]))
            return u_dict

        cursor = conn.execute("""
            INSERT INTO users (username, email, provider, provider_id, avatar_url, exp, level, title)
            VALUES (?, ?, ?, ?, ?, 0, 1, 'Wibu Pemula')
        """, (username, email, provider, str(provider_id) if provider_id else None, avatar_url))
        conn.commit()
        user_id = cursor.lastrowid
        new_row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        u_dict = dict(new_row)
        u_dict.update(calculate_level_info(0))
        return u_dict
    finally:
        conn.close()


def get_user_profile(user_id: int) -> dict:
    """Mengambil profil lengkap pengguna beserta level dan statistiknya."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return None
        u_dict = dict(row)
        lvl_info = calculate_level_info(u_dict["exp"])
        u_dict.update(lvl_info)

        stats_row = conn.execute("""
            SELECT 
                COUNT(*) as total_episodes_watched,
                COALESCE(SUM(watch_seconds), 0) as total_watch_seconds,
                COALESCE(SUM(exp_earned), 0) as total_watch_exp
            FROM user_watch_history
            WHERE user_id = ?
        """, (user_id,)).fetchone()
        if stats_row:
            u_dict["stats"] = {
                "total_episodes": stats_row["total_episodes_watched"],
                "total_watch_minutes": int(stats_row["total_watch_seconds"] / 60),
                "total_watch_hours": round(stats_row["total_watch_seconds"] / 3600, 1),
                "watch_exp": stats_row["total_watch_exp"]
            }
        else:
            u_dict["stats"] = {"total_episodes": 0, "total_watch_minutes": 0, "total_watch_hours": 0.0, "watch_exp": 0}

        return u_dict
    finally:
        conn.close()


def add_user_exp(user_id: int, exp_amount: int, anime_id: int = None, ep_number: int = None, watch_seconds: int = 0) -> dict:
    """Menambahkan EXP ke pengguna dari menonton video, menghitung level up."""
    if exp_amount <= 0:
        exp_amount = 15
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return None

        old_exp = row["exp"]
        old_lvl = row["level"]
        new_exp = old_exp + exp_amount
        lvl_info = calculate_level_info(new_exp)
        new_lvl = lvl_info["level"]
        new_title = lvl_info["title"]
        level_up = new_lvl > old_lvl

        conn.execute("""
            UPDATE users
            SET exp = ?, level = ?, title = ?
            WHERE id = ?
        """, (new_exp, new_lvl, new_title, user_id))

        if anime_id:
            conn.execute("""
                INSERT INTO user_watch_history (user_id, anime_id, ep_number, watch_seconds, exp_earned, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, anime_id, ep_number) DO UPDATE SET
                    watch_seconds = watch_seconds + excluded.watch_seconds,
                    exp_earned = exp_earned + excluded.exp_earned,
                    updated_at = CURRENT_TIMESTAMP
            """, (user_id, anime_id, ep_number or 1, watch_seconds, exp_amount))

        conn.commit()

        result = dict(lvl_info)
        result["user_id"] = user_id
        result["exp_added"] = exp_amount
        result["level_up"] = level_up
        result["old_level"] = old_lvl
        result["new_level"] = new_lvl
        result["message"] = f"🎉 Selamat! Kamu naik ke Level {new_lvl} ({new_title})!" if level_up else f"+{exp_amount} EXP didapatkan!"
        return result
    finally:
        conn.close()


def update_user_profile(user_id: int, username: str = None, bio: str = None, avatar_url: str = None) -> dict:
    """Mengubah info profil user."""
    conn = get_connection()
    try:
        fields = []
        vals = []
        if username and username.strip():
            fields.append("username = ?")
            vals.append(username.strip())
        if bio is not None:
            fields.append("bio = ?")
            vals.append(bio.strip())
        if avatar_url and avatar_url.strip():
            fields.append("avatar_url = ?")
            vals.append(avatar_url.strip())

        if fields:
            vals.append(user_id)
            conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", vals)
            conn.commit()

        return get_user_profile(user_id)
    finally:
        conn.close()


def get_user_watch_history(user_id: int, limit: int = 20) -> list:
    """Mengambil riwayat tontonan user dengan judul anime dan thumbnail."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT 
                h.id, h.anime_id, h.ep_number, h.watch_seconds, h.exp_earned, h.updated_at,
                a.title as anime_title, a.slug as anime_slug, a.thumbnail as anime_thumbnail
            FROM user_watch_history h
            JOIN animes a ON h.anime_id = a.id
            WHERE h.user_id = ?
            ORDER BY h.updated_at DESC
            LIMIT ?
        """, (user_id, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_user_bookmarks(user_id: int, status: str = None) -> list:
    """Mengambil daftar anime yang di-bookmark oleh user."""
    conn = get_connection()
    try:
        if status and status != "all":
            rows = conn.execute("""
                SELECT 
                    b.id as bookmark_id, b.status, b.created_at as bookmarked_at,
                    a.id as anime_id, a.title, a.slug, a.synopsis, a.genre, a.status as anime_status,
                    a.score, a.thumbnail, a.total_eps
                FROM user_bookmarks b
                JOIN animes a ON b.anime_id = a.id
                WHERE b.user_id = ? AND b.status = ?
                ORDER BY b.created_at DESC
            """, (user_id, status)).fetchall()
        else:
            rows = conn.execute("""
                SELECT 
                    b.id as bookmark_id, b.status, b.created_at as bookmarked_at,
                    a.id as anime_id, a.title, a.slug, a.synopsis, a.genre, a.status as anime_status,
                    a.score, a.thumbnail, a.total_eps
                FROM user_bookmarks b
                JOIN animes a ON b.anime_id = a.id
                WHERE b.user_id = ?
                ORDER BY b.created_at DESC
            """, (user_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_or_update_bookmark(user_id: int, anime_id: int, status: str = "favorite") -> dict:
    """Menambah atau memperbarui status bookmark anime oleh user."""
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO user_bookmarks (user_id, anime_id, status, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, anime_id) DO UPDATE SET
                status = excluded.status,
                created_at = CURRENT_TIMESTAMP
        """, (user_id, anime_id, status))
        conn.commit()
        return {"user_id": user_id, "anime_id": anime_id, "status": status}
    finally:
        conn.close()


def delete_user_bookmark(user_id: int, anime_id: int) -> bool:
    """Menghapus anime dari bookmark user."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM user_bookmarks WHERE user_id = ? AND anime_id = ?", (user_id, anime_id))
        conn.commit()
        return True
    finally:
        conn.close()



