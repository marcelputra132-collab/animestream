"""
seed_bleach_sennen_all.py — Seed Lengkap Seluruh Episode Bleach Sennen Kessen-hen
Memastikan Part 1 (13 Ep), Part 2 (13 Ep), Part 3 (14 Ep), dan Kashin-tan (8 Ep)
terisi 100% penuh, tidak ada episode bolong/kosong, dan siap diputar di player.
"""

import sqlite3
import json
import os

SEASONS_DATA = [
    {
        "id": 236,
        "anilist_id": 116674,
        "title": "Bleach: Sennen Kessen-hen",
        "slug": "bleach-sennen-kessen-hen",
        "total_eps": 13,
        "sub_prefix": "Bleach: Sennen Kessen-hen Episode",
        "source_base": "https://otakudesu.blog/anime/blch-kesen-hen-sub-indo/"
    },
    {
        "id": 233,
        "anilist_id": 159322,
        "title": "Bleach: Sennen Kessen-hen Part 2",
        "slug": "bleach-sennen-kessen-hen-part-2",
        "total_eps": 13,
        "sub_prefix": "Bleach: Sennen Kessen-hen - Ketsubetsu-tan Episode",
        "source_base": "https://otakudesu.blog/anime/blch-kesen-hen-p2-sub-indo/"
    },
    {
        "id": 234,
        "anilist_id": 169755,
        "title": "Bleach: Sennen Kessen-hen Part 3",
        "slug": "bleach-sennen-kessen-hen-part-3",
        "total_eps": 14,
        "sub_prefix": "Bleach: Sennen Kessen-hen - Soukoku-tan Episode",
        "source_base": "https://otakudesu.blog/anime/bleach-oukoku-tan-sub-indo/"
    },
    {
        "id": 81603,
        "anilist_id": 185874,
        "title": "Bleach: Sennen Kessen-hen - Kashin-tan",
        "slug": "bleach-sennen-kessen-hen-kashin-tanon-going",
        "total_eps": 8,
        "sub_prefix": "Bleach: Sennen Kessen-hen - Kashin-tan Episode",
        "source_base": "https://otakudesu.blog/anime/bleach-kashin-tan-sub-indo/"
    }
]

def seed_sennen_to_db(db_path: str):
    if not os.path.exists(db_path):
        print(f"[SKIP] DB tidak ditemukan: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Bersihkan duplikat kosong [235] jika ada
    cursor.execute("DELETE FROM episodes WHERE anime_id = 235")
    cursor.execute("DELETE FROM animes WHERE id = 235")

    for s in SEASONS_DATA:
        anime_id = s["id"]
        total_eps = s["total_eps"]
        anilist_id = s["anilist_id"]
        sub_prefix = s["sub_prefix"]

        # Update metadata anime
        cursor.execute("""
            UPDATE animes
            SET total_eps = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (total_eps, anime_id))

        # Cek episode yang sudah ada
        cursor.execute("SELECT ep_number, embed_url, quality_streams FROM episodes WHERE anime_id = ?", (anime_id,))
        existing_eps = {row["ep_number"]: dict(row) for row in cursor.fetchall()}

        for ep in range(1, total_eps + 1):
            title = f"{sub_prefix} {ep} Subtitle Indonesia"
            if ep == total_eps and total_eps > 1:
                title = f"{sub_prefix} {ep} (End) Subtitle Indonesia"

            primary_embed = f"https://vidsrc.me/embed/anime?id={anilist_id}&ep={ep}"
            backup_embed = f"https://2embed.cc/embed/anime/{anilist_id}/{ep}"

            quality_streams = json.dumps({
                "1080p": primary_embed,
                "720p": primary_embed,
                "480p": backup_embed,
                "360p": backup_embed
            })

            source_url = f"{s['source_base']}episode-{ep}/"

            if ep in existing_eps:
                cur = existing_eps[ep]
                # Jika embed_url kosong atau rusak atau sama persis dengan ep 1 di ep 13
                needs_update = not cur.get("embed_url") or "MGwxZG9NVDY0VG" in (cur.get("embed_url") or "")
                if needs_update:
                    cursor.execute("""
                        UPDATE episodes
                        SET title = ?, embed_url = ?, quality_streams = ?, duration = '24 min'
                        WHERE anime_id = ? AND ep_number = ?
                    """, (title, primary_embed, quality_streams, anime_id, ep))
            else:
                cursor.execute("""
                    INSERT INTO episodes (anime_id, ep_number, title, embed_url, source_url, duration, quality_streams)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (anime_id, ep, title, primary_embed, source_url, "24 min", quality_streams))

        cursor.execute("SELECT count(*) FROM episodes WHERE anime_id = ?", (anime_id,))
        count = cursor.fetchone()[0]
        print(f"[OK] {s['title']} (ID {anime_id}) -> Total episode: {count}/{total_eps} Episode.")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    primary_db = os.path.join(base_dir, "anime_streaming.db")
    github_db = os.path.abspath(os.path.join(base_dir, "..", "SIAP_UPLOAD_GITHUB", "backend", "anime_streaming.db"))

    print("=== SEEDING BLEACH SENNEN KESSEN-HEN ALL PARTS ===")
    seed_sennen_to_db(primary_db)
    print("\n=== SINKRONISASI KE SIAP_UPLOAD_GITHUB ===")
    seed_sennen_to_db(github_db)
