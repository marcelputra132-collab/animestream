"""
models.py — Fungsi-fungsi CRUD (Create, Read, Update, Delete) untuk database
Modul ini menyediakan abstraksi akses database agar tidak ada SQL mentah di app.py
"""

from database import get_connection
import re


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


# ─────────────────────────────────────────────
#  ANIME QUERIES
# ─────────────────────────────────────────────

def get_all_animes(limit: int = 50, offset: int = 0) -> list:
    """Ambil semua anime dengan pagination. Utamakan anime yang sudah memiliki episode siap putar!"""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT a.*, (SELECT COUNT(*) FROM episodes WHERE anime_id = a.id) as ep_count
               FROM animes a
               ORDER BY 
                 (CASE WHEN EXISTS(SELECT 1 FROM episodes WHERE anime_id = a.id) THEN 0 ELSE 1 END),
                 a.updated_at DESC, a.id DESC
               LIMIT ? OFFSET ?""",
            (limit, offset)
        ).fetchall()
        return rows_to_list(rows)
    finally:
        conn.close()


def get_anime_by_slug(slug: str) -> dict:
    """Ambil satu anime berdasarkan slug."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM animes WHERE slug = ?", (slug,)
        ).fetchone()
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
    """Cari anime berdasarkan judul atau genre. Prioritaskan anime yang memiliki episode nyata."""
    conn = get_connection()
    try:
        like = f"%{query}%"
        rows = conn.execute(
            """SELECT a.*, 
                      (SELECT COUNT(*) FROM episodes WHERE anime_id = a.id) as ep_count
               FROM animes a
               WHERE a.title LIKE ? OR a.genre LIKE ? 
               ORDER BY 
                 (CASE WHEN (SELECT COUNT(*) FROM episodes WHERE anime_id = a.id) > 0 THEN 0 ELSE 1 END),
                 (SELECT COUNT(*) FROM episodes WHERE anime_id = a.id) DESC,
                 (CASE WHEN a.thumbnail IS NOT NULL AND a.thumbnail != '' THEN 0 ELSE 1 END),
                 a.score DESC, 
                 a.title ASC 
               LIMIT 100""",
            (like, like)
        ).fetchall()
        return rows_to_list(rows)
    finally:
        conn.close()


def get_latest_animes(limit: int = 12) -> list:
    """Ambil anime yang paling baru diperbarui."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM animes ORDER BY updated_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return rows_to_list(rows)
    finally:
        conn.close()


def get_popular_playable_animes(limit: int = 18) -> list:
    """Ambil anime populer berrating tinggi yang SUDAH memiliki episode siap putar."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT a.*, COUNT(e.id) as ep_count
            FROM animes a
            JOIN episodes e ON a.id = e.anime_id
            GROUP BY a.id
            ORDER BY a.score DESC, ep_count DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return rows_to_list(rows)
    finally:
        conn.close()


def get_completed_playable_animes(limit: int = 18) -> list:
    """Ambil anime status tamat/completed yang SUDAH memiliki episode lengkap."""
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
        """, (limit,)).fetchall()
        return rows_to_list(rows)
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


def get_latest_episodes(limit: int = 20) -> list:
    """Ambil episode terbaru yang baru ditambahkan (join dengan data anime)."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT
                e.id, e.anime_id, e.ep_number, e.title AS ep_title, e.created_at,
                a.title AS anime_title, a.slug AS anime_slug, a.thumbnail
            FROM episodes e
            JOIN animes a ON e.anime_id = a.id
            ORDER BY e.created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return rows_to_list(rows)
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
