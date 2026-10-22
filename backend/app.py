"""
app.py — Flask REST API Server untuk Anime Streaming Platform
Menyediakan endpoint untuk melayani data ke frontend.

Jalankan dengan: python app.py
API berjalan di: http://localhost:5000
"""

import json
import os
import sys
import re
import socket
import urllib.parse
import requests
from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS

# Pastikan modul backend bisa diimport
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import init_db, get_connection
from models import (
    get_all_animes,
    get_anime_by_slug,
    get_anime_by_id,
    search_animes,
    get_latest_animes,
    get_popular_playable_animes,
    get_completed_playable_animes,
    get_episodes_by_anime,
    get_episode,
    get_latest_episodes,
    make_slug,
    normalize_dedup_key,
    get_anime_stats,
    increment_views,
    toggle_anime_like,
    get_comments,
    add_comment,
    like_comment,
    calculate_level_info,
    get_or_create_user,
    get_user_profile,
    add_user_exp,
    update_user_profile,
    get_user_watch_history,
    get_weekly_schedule,
    get_anime_airing_time,
    get_user_bookmarks,
    add_or_update_bookmark,
    delete_user_bookmark,
)

# ─────────────────────────────────────────────
#  INISIALISASI APP
# ─────────────────────────────────────────────

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

app = Flask(__name__, static_folder=FRONTEND_DIR)
CORS(app)  # Izinkan request dari frontend (localhost:3000 atau file:// dll)

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    if (request.path.endswith('.js') or request.path.endswith('.css') or 
        request.path.endswith('.html') or request.path == '/' or 
        request.path == '/sw.js' or 'manifest.json' in request.path or
        request.path.startswith('/icons/')):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# Inisialisasi database saat aplikasi pertama dijalankan
with app.app_context():
    init_db()


# ─────────────────────────────────────────────
#  EXTRAS: TRAILER & LINK PLATFORM RESMI
# ─────────────────────────────────────────────

def ensure_extras_table():
    """Buat tabel anime_extras kalau belum ada (diisi oleh import_anime.py)."""
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS anime_extras (
                anime_id INTEGER PRIMARY KEY,
                anilist_id INTEGER,
                trailer_site VARCHAR(30),
                trailer_id VARCHAR(100),
                links_json TEXT,
                FOREIGN KEY (anime_id) REFERENCES animes(id) ON DELETE CASCADE
            )
        """)
        conn.commit()
    finally:
        conn.close()


ensure_extras_table()

# Jalankan background auto-updater untuk menyinkronkan episode anime terbaru setiap jam
try:
    from auto_updater import start_auto_updater
    start_auto_updater(interval_seconds=3600)
except Exception as _e:
    print(f"[WARN] Gagal memulai auto-updater: {_e}")


def get_latest_playable_animes(limit: int = 12):
    """Anime terbaru yang SUDAH punya episode (supaya beranda tidak menampilkan yang kosong). Bebas duplikat."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT a.* FROM animes a
            WHERE EXISTS (SELECT 1 FROM episodes e WHERE e.anime_id = a.id)
            ORDER BY a.updated_at DESC, a.id DESC
            LIMIT ?
            """,
            (limit * 2,),
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


def get_anime_extras(anime: dict):
    """Jumlah episode nyata, trailer resmi, dan link platform streaming resmi."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT anilist_id, trailer_site, trailer_id, links_json FROM anime_extras WHERE anime_id = ?",
            (anime["id"],),
        ).fetchone()
        ep_count = conn.execute(
            "SELECT COUNT(*) FROM episodes WHERE anime_id = ?", (anime["id"],)
        ).fetchone()[0]
    finally:
        conn.close()

    trailer, links, anilist_url = None, [], None
    if row:
        if row[1] and row[2]:
            trailer = {"site": row[1], "id": row[2]}
        try:
            links = json.loads(row[3] or "[]")
        except ValueError:
            links = []
        if row[0]:
            anilist_url = f"https://anilist.co/anime/{row[0]}"
    return {
        "episode_count": ep_count,
        "trailer": trailer,
        "watch_links": links,
        "anilist_url": anilist_url,
    }


# ─────────────────────────────────────────────
#  HELPER RESPONSE
# ─────────────────────────────────────────────

def success(data, message: str = "OK", status_code: int = 200):
    """Standar response sukses."""
    return jsonify({"status": "success", "message": message, "data": data}), status_code


def error(message: str, status_code: int = 404):
    """Standar response error."""
    return jsonify({"status": "error", "message": message, "data": None}), status_code


# ─────────────────────────────────────────────
#  ENDPOINT: FRONTEND & UMUM
# ─────────────────────────────────────────────

@app.route("/")
def serve_root():
    """Buka halaman utama frontend."""
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:path>")
def serve_static(path):
    """Layani file HTML, CSS, JS, gambar dari folder frontend."""
    file_path = os.path.join(FRONTEND_DIR, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(FRONTEND_DIR, path)
    return jsonify({"status": "error", "message": f"Path '{path}' tidak ditemukan."}), 404


def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@app.route("/api")
def api_info():
    """Cek status API."""
    return jsonify({
        "name": "Anime Streaming API",
        "version": "1.0.0",
        "status": "online"
    })


@app.route("/api/server-info")
def server_info():
    """Mengembalikan info IP LAN dan URL untuk perangkat seluler / APK."""
    ip = get_lan_ip()
    port = 5000
    ngrok_url = None
    try:
        t_path = os.path.join(os.path.dirname(__file__), "tunnel_url.txt")
        if os.path.exists(t_path):
            with open(t_path, "r", encoding="utf-8") as f:
                ngrok_url = f.read().strip()
    except Exception:
        pass
    return jsonify({
        "status": "success",
        "data": {
            "ip": ip,
            "port": port,
            "lan_url": f"http://{ip}:{port}",
            "local_url": f"http://localhost:{port}",
            "ngrok_url": ngrok_url or "https://unafraid-hydrated-slighting.ngrok-free.dev"
        }
    })


# ─────────────────────────────────────────────
#  ENDPOINT: ANIME
# ─────────────────────────────────────────────

@app.route("/api/animes")
def api_get_all_animes():
    """
    GET /api/animes
    Query params: limit (default 50), offset (default 0)
    """
    try:
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
        animes = get_all_animes(limit=limit, offset=offset)
        return success(animes, f"Berhasil mendapatkan {len(animes)} anime.")
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/animes/latest")
def api_get_latest_animes():
    """
    GET /api/animes/latest
    Query params: limit (default 12)
    """
    try:
        limit = int(request.args.get("limit", 12))
        animes = get_latest_playable_animes(limit=limit)
        return success(animes, f"Berhasil mendapatkan {len(animes)} anime terbaru.")
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/animes/hot")
@app.route("/api/animes/popular")
def api_get_popular_animes():
    """GET /api/animes/hot & /api/animes/popular — Anime HOT & Baru siap putar."""
    try:
        try:
            merge_tokyo_revengers_and_duplicates()
        except Exception:
            pass
        limit = int(request.args.get("limit", 18))
        animes = get_popular_playable_animes(limit=limit)
        return success(animes, f"Berhasil mendapatkan {len(animes)} anime populer.")
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/animes/completed")
def api_get_completed_animes():
    """GET /api/animes/completed — Anime tamat dengan episode lengkap siap putar."""
    try:
        limit = int(request.args.get("limit", 18))
        animes = get_completed_playable_animes(limit=limit)
        return success(animes, f"Berhasil mendapatkan {len(animes)} anime tamat.")
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/stats")
def api_get_stats():
    """GET /api/stats — Total anime dan episode siap putar."""
    try:
        conn = get_connection()
        total_playable = conn.execute("SELECT COUNT(DISTINCT anime_id) FROM episodes").fetchone()[0]
        total_episodes = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
        total_catalog = conn.execute("SELECT COUNT(*) FROM animes").fetchone()[0]
        conn.close()
        return success({
            "total_playable": total_playable,
            "total_episodes": total_episodes,
            "total_catalog": total_catalog
        })
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/animes/search")
def api_search_animes():
    """
    GET /api/animes/search?q=<query>
    """
    query = request.args.get("q", "").strip()
    if not query:
        return error("Parameter 'q' wajib diisi.", 400)
    try:
        results = search_animes(query)
        return success(results, f"Ditemukan {len(results)} hasil untuk '{query}'.")
    except Exception as e:
        return error(str(e), 500)


# ─────────────────────────────────────────────
#  GENRE & SCHEDULE (JADWAL RILIS)
# ─────────────────────────────────────────────

GENRE_METADATA = [
    {"name": "Action", "icon": "⚔️", "desc": "Pertarungan seru & adegan aksi intens"},
    {"name": "Adventure", "icon": "🗺️", "desc": "Petualangan menjelajah dunia baru"},
    {"name": "Comedy", "icon": "😂", "desc": "Humor kocak pengocok perut"},
    {"name": "Drama", "icon": "🎭", "desc": "Kisah emosional & konflik mendalam"},
    {"name": "Fantasy", "icon": "🧙‍♂️", "desc": "Sihir, monster & dunia fantasi"},
    {"name": "Isekai", "icon": "🌀", "desc": "Reinkarnasi ke dunia lain"},
    {"name": "Horror", "icon": "👻", "desc": "Misteri mencekam & teror menegangkan"},
    {"name": "Mystery", "icon": "🕵️", "desc": "Teka-teki & misteri investigasi"},
    {"name": "Romance", "icon": "💖", "desc": "Kisah cinta manis & romantis"},
    {"name": "Sci-Fi", "icon": "🚀", "desc": "Teknologi masa depan & luar angkasa"},
    {"name": "Shounen", "icon": "⚡", "desc": "Perjuangan pantang menyerah & persahabatan"},
    {"name": "Slice of Life", "icon": "☕", "desc": "Keseharian santai yang menghangatkan"},
    {"name": "Sports", "icon": "⚽", "desc": "Kompetisi olahraga penuh semangat"},
    {"name": "Supernatural", "icon": "🔮", "desc": "Kekuatan gaib & makhluk misterius"},
    {"name": "Psychological", "icon": "🧠", "desc": "Permainan pikiran & thriller psikologis"},
    {"name": "Mecha", "icon": "🤖", "desc": "Robot raksasa & pertempuran canggih"},
    {"name": "School", "icon": "🏫", "desc": "Kehidupan remaja & persahabatan sekolah"},
    {"name": "Historical", "icon": "🏯", "desc": "Era samurai & sejarah masa lalu"},
]

@app.route("/api/genres")
def api_get_genres():
    """GET /api/genres — Daftar genre lengkap beserta ikon dan jumlah anime siap tonton."""
    try:
        conn = get_connection()
        result = []
        for g in GENRE_METADATA:
            if g["name"].lower() == "isekai":
                count = conn.execute(
                    "SELECT COUNT(*) FROM animes a WHERE (a.genre LIKE '%Isekai%' OR a.title LIKE '%isekai%' OR a.synopsis LIKE '%isekai%' OR a.title LIKE '%tensei%' OR a.synopsis LIKE '%dunia lain%' OR a.synopsis LIKE '%reinkarnasi%') AND EXISTS (SELECT 1 FROM episodes e WHERE e.anime_id = a.id AND e.embed_url IS NOT NULL AND e.embed_url != '')"
                ).fetchone()[0]
            else:
                count = conn.execute(
                    "SELECT COUNT(*) FROM animes a WHERE a.genre LIKE ? AND EXISTS (SELECT 1 FROM episodes e WHERE e.anime_id = a.id AND e.embed_url IS NOT NULL AND e.embed_url != '')", (f"%{g['name']}%",)
                ).fetchone()[0]
            result.append({
                **g,
                "count": count
            })
        conn.close()
        return success(result, f"Berhasil mendapatkan {len(result)} genre.")
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/animes/genre/<genre_name>")
def api_get_animes_by_genre(genre_name: str):
    """GET /api/animes/genre/<genre_name> — Ambil anime berdasarkan genre tertentu yang memiliki episode."""
    try:
        limit = int(request.args.get("limit", 24))
        page = int(request.args.get("page", 1))
        offset = (page - 1) * limit
        conn = get_connection()

        if genre_name.lower() == "isekai":
            where_sql = "(a.genre LIKE '%Isekai%' OR a.title LIKE '%isekai%' OR a.synopsis LIKE '%isekai%' OR a.title LIKE '%tensei%' OR a.synopsis LIKE '%dunia lain%' OR a.synopsis LIKE '%reinkarnasi%')"
            rows = conn.execute(f"""
                SELECT a.id, a.title, a.slug, a.thumbnail, a.score, a.genre, a.status,
                       COUNT(e.id) as ep_count
                FROM animes a
                JOIN episodes e ON a.id = e.anime_id AND e.embed_url IS NOT NULL AND e.embed_url != ''
                WHERE {where_sql}
                GROUP BY a.id
                HAVING ep_count > 0
                ORDER BY (CASE WHEN a.score > 0 THEN a.score ELSE 7.0 END) DESC,
                         ep_count DESC, a.updated_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset)).fetchall()

            total = conn.execute(
                f"SELECT COUNT(*) FROM animes a WHERE {where_sql} AND EXISTS (SELECT 1 FROM episodes e WHERE e.anime_id = a.id AND e.embed_url IS NOT NULL AND e.embed_url != '')"
            ).fetchone()[0]
        else:
            rows = conn.execute("""
                SELECT a.id, a.title, a.slug, a.thumbnail, a.score, a.genre, a.status,
                       COUNT(e.id) as ep_count
                FROM animes a
                JOIN episodes e ON a.id = e.anime_id AND e.embed_url IS NOT NULL AND e.embed_url != ''
                WHERE a.genre LIKE ?
                GROUP BY a.id
                HAVING ep_count > 0
                ORDER BY (CASE WHEN a.score > 0 THEN a.score ELSE 7.0 END) DESC,
                         ep_count DESC, a.updated_at DESC
                LIMIT ? OFFSET ?
            """, (f"%{genre_name}%", limit, offset)).fetchall()

            total = conn.execute(
                "SELECT COUNT(*) FROM animes a WHERE a.genre LIKE ? AND EXISTS (SELECT 1 FROM episodes e WHERE e.anime_id = a.id AND e.embed_url IS NOT NULL AND e.embed_url != '')", (f"%{genre_name}%",)
            ).fetchone()[0]

        conn.close()

        seen = set()
        animes = []
        for r in rows:
            clean_k = normalize_dedup_key(r['title'])
            if clean_k in seen:
                continue
            seen.add(clean_k)
            animes.append(dict(r))

        return success({
            "genre": genre_name,
            "total": total,
            "page": page,
            "limit": limit,
            "animes": animes
        }, f"Berhasil mendapatkan {len(animes)} anime genre {genre_name}.")
    except Exception as e:
        return error(str(e), 500)


_SCHEDULE_CACHE = {"timestamp": 0, "data": None}

@app.route("/api/schedule")
def api_get_schedule():
    """GET /api/schedule — Jadwal rilis anime mingguan (Senin–Minggu) lengkap dengan thumbnail asli & playable."""
    global _SCHEDULE_CACHE
    import time
    now = time.time()
    if _SCHEDULE_CACHE["data"] and (now - _SCHEDULE_CACHE["timestamp"]) < 600:
        return success(_SCHEDULE_CACHE["data"], "Jadwal rilis mingguan (dari cache).")

    try:
        schedule = get_weekly_schedule()
        _SCHEDULE_CACHE = {"timestamp": now, "data": schedule}
        return success(schedule, "Berhasil mendapatkan jadwal rilis mingguan.")
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/animes/<slug>")
def api_get_anime_detail(slug: str):
    """
    GET /api/animes/<slug>
    Mendapatkan detail satu anime berdasarkan slug-nya dengan fallback cerdas.
    """
    try:
        anime = get_anime_by_slug(slug)
        if not anime:
            # Fallback cerdas: cari anime terdekat di database berdasarkan kata kunci slug
            query = slug.replace("-", " ")
            search_results = search_animes(query)
            if search_results:
                anime = search_results[0]
            else:
                return error(f"Anime dengan slug '{slug}' tidak ditemukan.", 404)
        if anime:
            anime["release_time"] = get_anime_airing_time(anime.get("title", ""))
        return success(anime, "Berhasil mendapatkan detail anime.")
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/animes/<slug>/extras")
def api_get_anime_extras(slug: str):
    """
    GET /api/animes/<slug>/extras
    Trailer resmi + link platform streaming resmi + jumlah episode yang tersedia.
    """
    try:
        anime = get_anime_by_slug(slug)
        if not anime:
            return error(f"Anime dengan slug '{slug}' tidak ditemukan.", 404)
        return success(get_anime_extras(anime), "Berhasil mendapatkan data tambahan.")
    except Exception as e:
        return error(str(e), 500)


# ─────────────────────────────────────────────
#  ENDPOINT: STATS, LIKES & KOMENTAR
# ─────────────────────────────────────────────

@app.route("/api/animes/<slug>/stats")
def api_get_anime_stats(slug: str):
    try:
        anime = get_anime_by_slug(slug)
        if not anime:
            return error("Anime tidak ditemukan.", 404)
        return success(get_anime_stats(anime["id"]), "Statistik anime.")
    except Exception as e:
        return error(str(e), 500)

@app.route("/api/animes/<slug>/view", methods=["POST"])
def api_increment_view(slug: str):
    try:
        anime = get_anime_by_slug(slug)
        if not anime:
            return error("Anime tidak ditemukan.", 404)
        new_views = increment_views(anime["id"])
        return success({"views": new_views}, "View bertambah.")
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/animes/<slug>/like", methods=["POST"])
def api_toggle_like(slug: str):
    try:
        anime = get_anime_by_slug(slug)
        if not anime:
            return error("Anime tidak ditemukan.", 404)
        data = request.get_json(silent=True) or {}
        is_like = bool(data.get("is_like", True))
        new_likes = toggle_anime_like(anime["id"], is_like)
        return success({"likes": new_likes}, "Status suka diperbarui.")
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/animes/<slug>/comments", methods=["GET", "POST"])
def api_anime_comments(slug: str):
    try:
        anime = get_anime_by_slug(slug)
        if not anime:
            return error("Anime tidak ditemukan.", 404)

        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            username = data.get("username", "").strip() or "Otaku Fans"
            content = data.get("content", "").strip()
            if not content:
                return error("Komentar tidak boleh kosong.", 400)
            ep_num = data.get("ep_number")
            if ep_num is not None:
                try: ep_num = int(ep_num)
                except ValueError: ep_num = None
            comment = add_comment(anime["id"], username, content, ep_num)
            return success(comment, "Komentar berhasil dikirim.")
        else:
            ep_num = request.args.get("ep")
            if ep_num is not None:
                try: ep_num = int(ep_num)
                except ValueError: ep_num = None
            comments = get_comments(anime["id"], ep_num)
            return success(comments, f"Berhasil mendapatkan {len(comments)} komentar.")
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/comments/<int:comment_id>/like", methods=["POST"])
def api_like_comment(comment_id: int):
    try:
        new_likes = like_comment(comment_id)
        return success({"likes": new_likes}, "Like komentar berhasil.")
    except Exception as e:
        return error(str(e), 500)


# ─────────────────────────────────────────────
#  ENDPOINT: USER, AUTH & LEVELING EXP
# ─────────────────────────────────────────────

@app.route("/api/auth/social-login", methods=["POST"])
def api_social_login():
    """Login dengan Google, Facebook, atau Guest."""
    try:
        data = request.get_json(silent=True) or {}
        provider = str(data.get("provider") or "guest").strip().lower()
        provider_id = str(data.get("provider_id") or "").strip() or None
        username = str(data.get("username") or "").strip() or None
        email = str(data.get("email") or "").strip() or None
        avatar_url = str(data.get("avatar_url") or "").strip() or None

        user = get_or_create_user(
            provider=provider,
            provider_id=provider_id,
            username=username,
            email=email,
            avatar_url=avatar_url
        )
        return success(user, f"Berhasil masuk sebagai {user['username']}!")
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/user/<int:user_id>/profile", methods=["GET"])
def api_get_user_profile(user_id: int):
    """Mendapatkan detail profil, level, dan statistik tontonan user."""
    try:
        profile = get_user_profile(user_id)
        if not profile:
            return error("User tidak ditemukan.", 404)
        return success(profile, "Data profil berhasil diambil.")
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/user/<int:user_id>/add-exp", methods=["POST"])
def api_add_user_exp(user_id: int):
    """
    Menambahkan EXP saat pengguna menonton video.
    Mendukung tracking per episode, watch seconds, dan deteksi Level Up!
    """
    try:
        data = request.get_json(silent=True) or {}
        exp_amount = int(data.get("exp_amount", 15))
        anime_slug = data.get("anime_slug")
        ep_number = data.get("ep_number")
        watch_seconds = int(data.get("watch_seconds", 30))

        anime_id = None
        if anime_slug:
            anime = get_anime_by_slug(anime_slug)
            if anime:
                anime_id = anime["id"]

        result = add_user_exp(
            user_id=user_id,
            exp_amount=exp_amount,
            anime_id=anime_id,
            ep_number=ep_number,
            watch_seconds=watch_seconds
        )
        if not result:
            return error("User tidak ditemukan.", 404)
        return success(result, result.get("message", "EXP berhasil ditambahkan."))
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/user/<int:user_id>/update-profile", methods=["POST"])
def api_update_user_profile(user_id: int):
    """Mengubah username, bio, atau avatar."""
    try:
        data = request.get_json(silent=True) or {}
        username = data.get("username")
        bio = data.get("bio")
        avatar_url = data.get("avatar_url")

        profile = update_user_profile(user_id, username, bio, avatar_url)
        if not profile:
            return error("User tidak ditemukan.", 404)
        return success(profile, "Profil berhasil diperbarui.")
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/user/<int:user_id>/history", methods=["GET"])
def api_get_user_history(user_id: int):
    """Mengambil riwayat episode yang telah ditonton user."""
    try:
        limit = int(request.args.get("limit", 20))
        history = get_user_watch_history(user_id, limit=limit)
        return success(history, f"Berhasil memuat {len(history)} riwayat tontonan.")
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/user/<int:user_id>/bookmarks", methods=["GET"])
def api_get_user_bookmarks(user_id: int):
    """Mengambil daftar anime yang disimpan/dibookmark user."""
    try:
        status = request.args.get("status")
        bookmarks = get_user_bookmarks(user_id, status=status)
        return success(bookmarks, f"Berhasil memuat {len(bookmarks)} bookmark.")
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/user/<int:user_id>/bookmarks", methods=["POST"])
def api_save_user_bookmark(user_id: int):
    """Menambahkan atau memperbarui anime ke bookmark user."""
    try:
        data = request.get_json(silent=True) or {}
        anime_id = data.get("anime_id")
        anime_slug = data.get("anime_slug")
        status = data.get("status", "favorite")

        if not anime_id and anime_slug:
            anime = get_anime_by_slug(anime_slug)
            if anime:
                anime_id = anime["id"]

        if not anime_id:
            return error("anime_id atau anime_slug wajib disertakan.", 400)

        res = add_or_update_bookmark(user_id, int(anime_id), status)
        return success(res, "Berhasil menyimpan bookmark.")
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/user/<int:user_id>/bookmarks/<int:anime_id>", methods=["DELETE"])
def api_delete_user_bookmark(user_id: int, anime_id: int):
    """Menghapus anime dari bookmark user."""
    try:
        ok = delete_user_bookmark(user_id, anime_id)
        return success({"deleted": ok}, "Bookmark berhasil dihapus.")
    except Exception as e:
        return error(str(e), 500)



#  ENDPOINT: EPISODE
# ─────────────────────────────────────────────

def heal_anime_episodes_impl(anime: dict) -> list:
    """
    Memastikan episode anime tidak melompat (misal langsung mulai dari episode 14).
    Melakukan backfill episode yang hilang (1..N) dari source_url atau OtakuDesu,
    sinkronisasi dari anime sibling di DB, atau menormalkan penomoran episode jika perlu.
    """
    anime_id = anime["id"]
    from database import get_connection
    from scraper import fetch_page, scrape_anime_detail, scrape_episode_embed
    import urllib.parse
    import json

    cur_eps = get_episodes_by_anime(anime_id)
    ep_nums = [e["ep_number"] for e in cur_eps] if cur_eps else []

    needs_heal = False
    if not cur_eps:
        needs_heal = True
    else:
        min_ep = min(ep_nums)
        max_ep = max(ep_nums)
        # Jika nomor episode melompat (misal mulai dari >1) atau ada celah di tengah urutan episode
        if min_ep > 1 or len(cur_eps) < (max_ep - min_ep + 1):
            needs_heal = True

    if not needs_heal:
        return cur_eps

    print(f"[HEAL-EP] Memperbaiki urutan episode untuk anime ID {anime_id}: '{anime.get('title')}' (current eps: {ep_nums})")

    conn = get_connection()
    try:
        raw_title = anime.get("title", "")
        base_title = re.split(r'[:\-\(]|Season|\bPart\b', raw_title, flags=re.IGNORECASE)[0].strip()

        # 1. Cek anime duplikat di DB yang memiliki episode lengkap (HANYA jika judul benar-benar identik, misal beda -on-going atau spasi)
        clean_raw_title = re.sub(r'[\(\[\{].*?[\)\]\}]', '', raw_title).strip().lower()
        clean_raw_title = re.sub(r'\b(on-going|ongoing|sub indo|tamat|completed)\b', '', clean_raw_title).strip()
        clean_raw_title = re.sub(r'[-_\s]+', ' ', clean_raw_title).strip()

        if len(clean_raw_title) >= 3:
            cand_rows = conn.execute("""
                SELECT a.id, a.title, a.slug, COUNT(e.id) as ep_count
                FROM animes a
                JOIN episodes e ON a.id = e.anime_id
                WHERE a.id != ?
                GROUP BY a.id
                HAVING ep_count > 0
                ORDER BY ep_count DESC
            """, (anime_id,)).fetchall()

            for s_row in cand_rows:
                s_title_clean = re.sub(r'[\(\[\{].*?[\)\]\}]', '', s_row["title"]).strip().lower()
                s_title_clean = re.sub(r'\b(on-going|ongoing|sub indo|tamat|completed)\b', '', s_title_clean).strip()
                s_title_clean = re.sub(r'[-_\s]+', ' ', s_title_clean).strip()

                if s_title_clean == clean_raw_title:
                    key_markers = {'season', 'part', 'movie', 'cour', 'sennen', 'kessen', 'geiko', 'hashira', 'shippuden', 's1', 's2', 's3', 's4'}
                    s_words = set(re.findall(r'\b[a-z0-9]+\b', s_row["title"].lower()))
                    my_words = set(re.findall(r'\b[a-z0-9]+\b', raw_title.lower()))
                    if (s_words.intersection(key_markers) == my_words.intersection(key_markers)):
                        s_eps = get_episodes_by_anime(s_row["id"])
                        if s_eps:
                            for sep in s_eps:
                                if sep["ep_number"] not in ep_nums:
                                    conn.execute("""
                                        INSERT OR IGNORE INTO episodes (anime_id, ep_number, title, embed_url, source_url, duration, thumbnail)
                                        VALUES (?, ?, ?, ?, ?, ?, ?)
                                    """, (anime_id, sep["ep_number"], sep.get("title"), sep.get("embed_url"), sep.get("source_url"), sep.get("duration", "24 min"), sep.get("thumbnail") or anime.get("thumbnail")))
                                    ep_nums.append(sep["ep_number"])
                            conn.commit()
                            break

        # Update ep_nums setelah cek duplikat
        cur_eps = get_episodes_by_anime(anime_id)
        ep_nums = [e["ep_number"] for e in cur_eps] if cur_eps else []

        # 2. Coba ambil dari source_url anime jika ada
        detail = None
        source_url = anime.get("source_url") or ""
        if source_url and "otakudesu" in source_url:
            detail = scrape_anime_detail(source_url, anime["title"])

        # 3. Jika belum dapat detail atau episode masih melompat, cari di OtakuDesu
        # HANYA ambil jika judul OtakuDesu benar-benar cocok (jangan comot beda season/part)
        if not detail or not detail.get("episode_links") or (ep_nums and min(ep_nums) > 1):
            title_candidates = [raw_title]
            clean_t = re.sub(r'[\(\[].*?[\)\]]', '', raw_title).strip()
            if clean_t and clean_t not in title_candidates:
                title_candidates.append(clean_t)

            for q in title_candidates:
                if len(q) < 3:
                    continue
                s_url = f"https://otakudesu.blog/?s={urllib.parse.quote(q)}&post_type=anime"
                soup = fetch_page(s_url)
                if not soup:
                    continue
                items = soup.select("ul.chivsrc li h2 a")
                for it in items:
                    t_low = it.get_text().lower()
                    if "batch" in t_low or "lengkap" in t_low:
                        continue
                    key_markers = ['sennen', 'kessen', 'season', 'part', 'movie', 'shippuden', 'hashira', 'geiko']
                    target_has = any(m in raw_title.lower() for m in key_markers)
                    it_has = any(m in t_low for m in key_markers)
                    if target_has != it_has:
                        continue
                    detail = scrape_anime_detail(it["href"], anime["title"])
                    if detail and detail.get("episode_links"):
                        break
                if detail and detail.get("episode_links"):
                    break

        # 4. Masukkan semua episode dari hasil scrape (1..N) ke database
        if detail and detail.get("episode_links"):
            for ep in detail["episode_links"]:
                ep_n = ep["ep_number"]
                conn.execute("""
                    INSERT OR IGNORE INTO episodes (anime_id, ep_number, title, embed_url, source_url, duration, thumbnail, created_at)
                    VALUES (?, ?, ?, '', ?, '24 min', ?, CURRENT_TIMESTAMP)
                """, (anime_id, ep_n, ep["title"], ep["url"], detail.get("thumbnail") or anime.get("thumbnail")))
            conn.commit()

        # 5. Cek ulang: Jika setelah scrape tetap melompat (misal sumber hanya memuat episode 14..16 tanpa ada episode 1..13 sama sekali di web),
        # normalisasi penomoran secara berurutan mulai dari 1 agar tampilan rapi
        final_eps = get_episodes_by_anime(anime_id)
        if final_eps:
            f_nums = [e["ep_number"] for e in final_eps]
            if min(f_nums) > 1:
                print(f"[NORMALIZE-EP] Menormalkan penomoran episode untuk anime ID {anime_id} dari {f_nums} menjadi 1..{len(final_eps)}")
                for idx, e_row in enumerate(final_eps, start=1):
                    conn.execute("UPDATE episodes SET ep_number = ? WHERE id = ?", (idx, e_row["id"]))
                conn.commit()

        # 6. Pre-scrape stream embed untuk Episode 1 jika belum memiliki embed_url agar pengguna langsung bisa memutar
        latest_eps = get_episodes_by_anime(anime_id)
        if latest_eps:
            ep1 = next((e for e in latest_eps if e["ep_number"] == 1), latest_eps[0])
            if ep1 and (not ep1.get("embed_url") or "maintenance" in (ep1.get("embed_url") or "").lower()):
                src_u = ep1.get("source_url")
                if src_u and "http" in src_u:
                    try:
                        best_u, q_s = scrape_episode_embed(src_u)
                        if best_u:
                            q_json = json.dumps(q_s) if q_s else None
                            conn.execute(
                                "UPDATE episodes SET embed_url = ?, quality_streams = ? WHERE id = ?",
                                (best_u, q_json, ep1["id"])
                            )
                            conn.commit()
                    except Exception as err_ep1:
                        print(f"[WARN] Gagal pre-scrape Ep 1: {err_ep1}")

    except Exception as ex:
        print(f"[WARN] heal_anime_episodes_impl error for '{anime.get('title')}': {ex}")
    finally:
        conn.close()

    return get_episodes_by_anime(anime_id)


def find_real_episodes_for_anime(anime: dict) -> tuple[list, dict | None]:
    """
    Mengambil semua episode anime. Jika nomor episode melompat atau tidak berurutan,
    otomatis memperbaiki dan mem-backfill seluruh episode yang hilang (1..N).
    """
    episodes = get_episodes_by_anime(anime["id"])
    if episodes:
        ep_nums = [e["ep_number"] for e in episodes]
        min_ep = min(ep_nums)
        max_ep = max(ep_nums)
        # Jika rapi dan berurutan dari 1 tanpa melompat, langsung return
        if min_ep == 1 and len(episodes) == (max_ep - min_ep + 1):
            return episodes, None

    # Jika episode melompat atau belum lengkap atau kosong, jalankan healer otomatis
    healed_eps = heal_anime_episodes_impl(anime)
    if healed_eps:
        return healed_eps, None

    # Jika tetap belum ada episode nyata, coba cari duplicate yang benar-benar identik di database
    from database import get_connection
    conn = get_connection()
    raw_title = anime.get("title", "")
    clean_raw_title = re.sub(r'[\(\[\{].*?[\)\]\}]', '', raw_title).strip().lower()
    clean_raw_title = re.sub(r'\b(on-going|ongoing|sub indo|tamat|completed)\b', '', clean_raw_title).strip()
    clean_raw_title = re.sub(r'[-_\s]+', ' ', clean_raw_title).strip()

    try:
        if len(clean_raw_title) >= 3:
            cand_rows = conn.execute("""
                SELECT a.*, COUNT(e.id) as ep_count
                FROM animes a
                JOIN episodes e ON a.id = e.anime_id
                WHERE a.id != ?
                GROUP BY a.id
                HAVING ep_count > 0
                ORDER BY ep_count DESC
            """, (anime["id"],)).fetchall()

            for cand in cand_rows:
                cand_clean = re.sub(r'[\(\[\{].*?[\)\]\}]', '', cand["title"]).strip().lower()
                cand_clean = re.sub(r'\b(on-going|ongoing|sub indo|tamat|completed)\b', '', cand_clean).strip()
                cand_clean = re.sub(r'[-_\s]+', ' ', cand_clean).strip()
                if cand_clean == clean_raw_title:
                    key_markers = {'season', 'part', 'movie', 'cour', 'sennen', 'kessen', 'geiko', 'hashira', 'shippuden', 's1', 's2', 's3', 's4'}
                    c_words = set(re.findall(r'\b[a-z0-9]+\b', cand["title"].lower()))
                    my_words = set(re.findall(r'\b[a-z0-9]+\b', raw_title.lower()))
                    if (c_words.intersection(key_markers) == my_words.intersection(key_markers)):
                        matched_anime = dict(cand)
                        matched_eps = get_episodes_by_anime(matched_anime["id"])
                        if matched_eps:
                            return matched_eps, matched_anime
    finally:
        conn.close()

    return [], None


def merge_tokyo_revengers_and_duplicates():
    """
    Menggabungkan duplikat Tokyo Revengers Season 4 / Santen Sensou-hen:
    Menyatukan episode 1, 2, 3 ke dalam satu entri resmi tanpa duplikat,
    memastikan semua episode siap putar dan bebas error.
    """
    from database import get_connection
    from scraper import scrape_anime_detail, scrape_episode_embed
    import json

    conn = get_connection()
    try:
        # Cari semua entri Tokyo Revengers Santen Sensou atau Season 4
        rows = conn.execute("""
            SELECT id, title, slug, source_url, thumbnail, score, synopsis, genre
            FROM animes
            WHERE LOWER(title) LIKE '%santen sensou%' 
               OR LOWER(slug) LIKE '%santen-sensou%'
               OR (LOWER(title) LIKE '%tokyo revengers%' AND (LOWER(title) LIKE '%season 4%' OR LOWER(title) LIKE '%s4%'))
               OR (LOWER(slug) LIKE '%tokyo-revengers%' AND LOWER(slug) LIKE '%season-4%')
            ORDER BY id ASC
        """).fetchall()

        if not rows:
            return

        print(f"[MERGE-TR] Memproses {len(rows)} entri Tokyo Revengers Season 4 / Santen Sensou-hen...")

        # Cari entri utama dengan slug tokyo-revengers-santen-sensou-hen
        target_row = rows[0]
        for r in rows:
            if "santen-sensou" in r["slug"].lower():
                target_row = r
                break

        target_id = target_row["id"]
        other_ids = [r["id"] for r in rows if r["id"] != target_id]

        # 1. Pindahkan semua episode dari entri lain ke target_id
        for oid in other_ids:
            other_eps = conn.execute("""
                SELECT ep_number, title, embed_url, source_url, duration, thumbnail, quality_streams
                FROM episodes WHERE anime_id = ?
            """, (oid,)).fetchall()

            for ep in other_eps:
                existing = conn.execute(
                    "SELECT id, embed_url FROM episodes WHERE anime_id = ? AND ep_number = ?",
                    (target_id, ep["ep_number"])
                ).fetchone()

                if not existing:
                    conn.execute("""
                        INSERT INTO episodes (anime_id, ep_number, title, embed_url, source_url, duration, thumbnail, quality_streams)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (target_id, ep["ep_number"], ep["title"], ep["embed_url"], ep["source_url"], ep["duration"] or "24 min", ep["thumbnail"] or target_row["thumbnail"], ep["quality_streams"]))
                elif (not existing["embed_url"] or "maintenance" in (existing["embed_url"] or "").lower()) and ep["embed_url"]:
                    conn.execute("""
                        UPDATE episodes SET embed_url = ?, quality_streams = ? WHERE id = ?
                    """, (ep["embed_url"], ep["quality_streams"], existing["id"]))

            # Hapus episode dari entri duplikat dan hapus entri anime duplikat
            conn.execute("DELETE FROM episodes WHERE anime_id = ?", (oid,))
            conn.execute("DELETE FROM animes WHERE id = ?", (oid,))
            conn.commit()

        # 2. Update info record utama agar jelas dan lengkap
        sanhen_url = "https://otakudesu.blog/anime/tokyo-revs-sanhen-sub-indo/"
        conn.execute("""
            UPDATE animes SET
                title = 'Tokyo Revengers: Santen Sensou-hen (Season 4)',
                slug = 'tokyo-revengers-santen-sensou-hen',
                source_url = ?,
                status = 'Ongoing',
                score = 8.5,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (sanhen_url, target_id))
        conn.commit()

        # 3. Sinkronkan episode 1, 2, 3 dari sumber OtakuDesu jika ada yang belum lengkap
        detail = scrape_anime_detail(sanhen_url, "Tokyo Revengers: Santen Sensou-hen (Season 4)")
        if detail and detail.get("episode_links"):
            for ep_info in detail["episode_links"]:
                ep_n = ep_info["ep_number"]
                exists = conn.execute(
                    "SELECT id, embed_url FROM episodes WHERE anime_id = ? AND ep_number = ?",
                    (target_id, ep_n)
                ).fetchone()

                if not exists:
                    best_u, q_s = scrape_episode_embed(ep_info["url"])
                    q_json = json.dumps(q_s) if q_s else None
                    conn.execute("""
                        INSERT INTO episodes (anime_id, ep_number, title, embed_url, source_url, duration, thumbnail, quality_streams)
                        VALUES (?, ?, ?, ?, ?, '24 min', ?, ?)
                    """, (target_id, ep_n, ep_info["title"], best_u, ep_info["url"], detail.get("thumbnail") or target_row["thumbnail"], q_json))
                elif not exists["embed_url"] or "maintenance" in (exists["embed_url"] or "").lower():
                    best_u, q_s = scrape_episode_embed(ep_info["url"])
                    if best_u:
                        q_json = json.dumps(q_s) if q_s else None
                        conn.execute("""
                            UPDATE episodes SET embed_url = ?, quality_streams = ? WHERE id = ?
                        """, (best_u, q_json, exists["id"]))
            conn.commit()

        print(f"[MERGE-TR] Selesai menyatukan Tokyo Revengers ke ID {target_id}!")

    except Exception as ex:
        print(f"[WARN] Error dalam merge_tokyo_revengers_and_duplicates: {ex}")
    finally:
        conn.close()


def sweep_and_heal_all_jumping_animes():
    """
    Background worker: Menyisir seluruh database anime dan memperbaiki
    semua anime yang nomor episodenya melompat atau bolong.
    """
    import time
    time.sleep(1)
    # Satukan duplikat Tokyo Revengers
    try:
        merge_tokyo_revengers_and_duplicates()
    except Exception as _e_tr:
        print(f"[WARN] Error merge TR: {_e_tr}")

    print("[SWEEP-EP] Memeriksa seluruh anime untuk memperbaiki episode yang melompat...")
    from database import get_connection
    conn = get_connection()
    broken_animes = []
    try:
        rows = conn.execute("""
            SELECT a.id, a.title, a.slug, a.source_url,
                   MIN(e.ep_number) as min_ep,
                   MAX(e.ep_number) as max_ep,
                   COUNT(e.id) as cnt
            FROM animes a
            JOIN episodes e ON a.id = e.anime_id
            GROUP BY a.id
            HAVING min_ep > 1 OR cnt < (max_ep - min_ep + 1)
        """).fetchall()
        for r in rows:
            broken_animes.append(dict(r))
    except Exception as e:
        print(f"[SWEEP-EP] Query error: {e}")
    finally:
        conn.close()

    if not broken_animes:
        print("[SWEEP-EP] Semua anime memiliki episode berurutan dan rapi!")
        return

    print(f"[SWEEP-EP] Ditemukan {len(broken_animes)} anime dengan episode melompat. Memperbaiki otomatis...")
    for item in broken_animes:
        try:
            print(f"[SWEEP-EP] Memperbaiki '{item['title']}' (Eps {item['min_ep']}..{item['max_ep']})...")
            healed = heal_anime_episodes_impl(item)
            h_nums = [e["ep_number"] for e in healed] if healed else []
            print(f"[SWEEP-EP] Berhasil: '{item['title']}' -> {len(healed)} episode ({h_nums[:2]}...{h_nums[-1:]})")
            time.sleep(0.5)
        except Exception as err:
            print(f"[SWEEP-EP] Gagal memperbaiki '{item.get('title')}': {err}")

    print("[SWEEP-EP] Selesai memeriksa dan memperbaiki semua anime yang melompat!")


# Jalankan pemindaian otomatis di latar belakang saat server berjalan
try:
    import threading
    threading.Thread(target=sweep_and_heal_all_jumping_animes, daemon=True).start()
except Exception as _e_sweep:
    print(f"[WARN] Gagal memulai worker pemindaian episode: {_e_sweep}")


@app.route("/api/animes/<slug>/repair-episodes", methods=["POST", "GET"])
def api_repair_anime_episodes(slug: str):
    """
    POST/GET /api/animes/<slug>/repair-episodes
    Memperbaiki dan melengkapi nomor episode yang melompat pada anime.
    """
    try:
        anime = get_anime_by_slug(slug)
        if not anime:
            return error(f"Anime '{slug}' tidak ditemukan.", 404)
        healed_eps = heal_anime_episodes_impl(anime)
        return success({
            "anime": anime,
            "episodes": healed_eps,
            "total": len(healed_eps)
        }, f"Berhasil memperbaiki {len(healed_eps)} episode untuk '{anime['title']}'.")
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/animes/<slug>/episodes")
def api_get_episodes(slug: str):
    """
    GET /api/animes/<slug>/episodes
    Mendapatkan semua episode dari satu anime.
    """
    try:
        if "tokyo-revengers" in slug.lower() or "santen-sensou" in slug.lower():
            try:
                merge_tokyo_revengers_and_duplicates()
            except Exception:
                pass

        anime = get_anime_by_slug(slug)
        if not anime:
            return error(f"Anime '{slug}' tidak ditemukan.", 404)
        
        episodes, matched_series = find_real_episodes_for_anime(anime)

        if not episodes:
            episodes = []

        resp_data = {
            "anime": anime,
            "episodes": episodes,
            "total": len(episodes)
        }
        if matched_series:
            resp_data["matched_series"] = {
                "title": matched_series["title"],
                "slug": matched_series["slug"],
                "total_eps": len(episodes)
            }

        return success(resp_data, "Berhasil mendapatkan daftar episode.")
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/animes/<slug>/episodes/<int:ep_number>")
def api_get_single_episode(slug: str, ep_number: int):
    """
    GET /api/animes/<slug>/episodes/<ep_number>
    Mendapatkan detail satu episode termasuk embed URL.
    """
    try:
        if "tokyo-revengers" in slug.lower() or "santen-sensou" in slug.lower():
            try:
                merge_tokyo_revengers_and_duplicates()
            except Exception:
                pass

        anime = get_anime_by_slug(slug)
        if not anime:
            return error(f"Anime '{slug}' tidak ditemukan.", 404)

        all_episodes, matched_series = find_real_episodes_for_anime(anime)
        episode = None

        if all_episodes:
            for ep in all_episodes:
                if ep["ep_number"] == ep_number:
                    episode = ep
                    break
            if not episode and all_episodes:
                episode = all_episodes[0]

        if not episode:
            episode = {
                "id": f"p-{anime['id']}",
                "anime_id": anime["id"],
                "ep_number": ep_number,
                "title": f"{anime['title']} — Episode {ep_number}",
                "embed_url": "",
                "source_url": anime.get("source_url") or "",
                "duration": "24 min",
                "quality_streams": "{}"
            }

        # On-Demand Stream Resolver: jika embed_url belum terisi, rusak, dummy, atau force refresh diminta,
        # AnimeVerse CDN Resolver: Prioritaskan stream direct MP4 resmi dari AnimeVerse CDN (AnimeLovers)
        force_refresh = request.args.get("force", "0") == "1" or request.args.get("refresh", "0") == "1"
        cur_embed = episode.get("embed_url") or "" if episode else ""
        cur_low = cur_embed.lower()
        has_animeverse = any(h in cur_low for h in ["animeverse.id", "animekita.org"])
        is_bad_embed = not cur_embed or any(d in cur_low for d in ["maintenance", "bigbuckbunny", "commondatastorage", "solidfiles", "zippyshare", "racaty", "tusfiles", "mediafire", "acefile", "mega.nz", "mirrorace", "hxfile"])

        if episode and (is_bad_embed or force_refresh):
            try:
                from animeverse_resolver import resolve_animeverse_stream
                av_link = resolve_animeverse_stream(anime.get("title", ""), slug, ep_number)
                if av_link:
                    episode["embed_url"] = av_link
                    q_streams = {
                        "1080p": av_link,
                        "720p": av_link,
                        "480p": av_link,
                        "360p": av_link,
                        "144p": av_link
                    }
                    q_json = json.dumps(q_streams)
                    episode["quality_streams"] = q_json
                    conn = get_connection()
                    conn.execute(
                        "UPDATE episodes SET embed_url = ?, quality_streams = ?, source_url = ? WHERE id = ?",
                        (av_link, q_json, f"https://apps.animekita.org/api/v1.1.9/chapter.php?url=al-{anime['id']}-{ep_number}", episode["id"])
                    )
                    conn.commit()
                    conn.close()
                    cur_embed = av_link
                    cur_low = av_link.lower()
                    has_animeverse = True
            except Exception as _e_av:
                print(f"[WARN] Gagal resolve AnimeVerse CDN untuk {slug} ep {ep_number}: {_e_av}")

        # Fallback cadangan jika AnimeVerse CDN tidak menyediakan judul anime ini
        is_bad_embed = not cur_embed or any(d in cur_low for d in ["maintenance", "bigbuckbunny", "commondatastorage", "solidfiles", "zippyshare", "racaty", "tusfiles", "mediafire", "acefile", "mega.nz", "mirrorace", "hxfile"])
        if episode and not has_animeverse and (force_refresh or is_bad_embed):
            source_ep_url = episode.get("source_url")
            if source_ep_url and "http" in source_ep_url and "youtube" not in source_ep_url:
                try:
                    from scraper import scrape_episode_embed
                    best_url, q_streams = scrape_episode_embed(source_ep_url)
                    if best_url:
                        episode["embed_url"] = best_url
                        q_json = json.dumps(q_streams) if q_streams else None
                        episode["quality_streams"] = q_json
                        conn = get_connection()
                        conn.execute(
                            "UPDATE episodes SET embed_url = ?, quality_streams = ? WHERE id = ?",
                            (best_url, q_json, episode["id"])
                        )
                        conn.commit()
                        conn.close()
                except Exception as ex:
                    print(f"On-demand resolver error: {ex}")

        # Jika belum ada episode nyata di database
        if not episode:
            episode = {
                "id": f"p-{anime['id']}",
                "anime_id": anime["id"],
                "ep_number": 1,
                "title": f"{anime['title']} — Episode 1",
                "embed_url": "",
                "source_url": anime.get("source_url") or "",
                "duration": "24 min",
                "created_at": anime.get("created_at")
            }
            all_episodes = [episode]

        # Ambil episode prev & next untuk navigasi
        ep_numbers = [e["ep_number"] for e in all_episodes]
        current_idx = ep_numbers.index(episode["ep_number"]) if episode["ep_number"] in ep_numbers else 0

        prev_ep = ep_numbers[current_idx - 1] if current_idx > 0 else None
        next_ep = ep_numbers[current_idx + 1] if current_idx < len(ep_numbers) - 1 else None

        # Siapkan opsi resolusi dari 144p hingga 1080p Full HD
        # Filter URL host yang mati atau bukan video stream anime (misal solidfiles, zippyshare, BigBuckBunny, YouTube, Callistanise/VidHide mati)
        DEAD_STREAM_DOMAINS = [
            "solidfiles", "zippyshare", "racaty", "tusfiles", "mediafire", 
            "acefile", "mega.nz", "mirrorace", "hxfile", "commondatastorage", 
            "bigbuckbunny", "youtube.com", "youtu.be", "ytimg", "youtube",
            "blogger.com", "blogger", "blogspot", "callistanise.com", "callistanise"
        ]
        def is_usable_stream(u: str) -> bool:
            if not u or not isinstance(u, str) or not u.startswith("http"):
                return False
            u_low = u.lower()
            return not any(d in u_low for d in DEAD_STREAM_DOMAINS)

        quality_streams = {}
        if episode.get("quality_streams"):
            try:
                raw_qs = json.loads(episode["quality_streams"]) if isinstance(episode["quality_streams"], str) else episode["quality_streams"]
                if isinstance(raw_qs, dict):
                    quality_streams = {k: v for k, v in raw_qs.items() if is_usable_stream(v)}
            except Exception:
                quality_streams = {}

        base_embed = episode.get("embed_url") or ""
        if not is_usable_stream(base_embed):
            base_embed = ""
            for q_candidate in ["720p", "1080p", "480p", "360p"]:
                if quality_streams.get(q_candidate):
                    base_embed = quality_streams[q_candidate]
                    break

        episode["embed_url"] = base_embed

        qualities = [
            {"quality": "1080p", "label": "1080p Full HD", "embed_url": quality_streams.get("1080p") or quality_streams.get("720p") or base_embed, "is_hd": True},
            {"quality": "720p", "label": "720p HD (Default)", "embed_url": quality_streams.get("720p") or base_embed, "is_hd": True},
            {"quality": "480p", "label": "480p SD", "embed_url": quality_streams.get("480p") or base_embed, "is_hd": False},
            {"quality": "360p", "label": "360p Hemat", "embed_url": quality_streams.get("360p") or base_embed, "is_hd": False},
            {"quality": "144p", "label": "144p Super Hemat", "embed_url": quality_streams.get("360p") or base_embed, "is_hd": False},
        ]

        resp_data = {
            "anime": anime,
            "episode": episode,
            "navigation": {
                "prev": prev_ep,
                "next": next_ep,
                "total": len(all_episodes)
            },
            "all_episodes": all_episodes,
            "qualities": qualities,
        }
        if matched_series:
            resp_data["matched_series"] = {
                "title": matched_series["title"],
                "slug": matched_series["slug"],
                "total_eps": len(all_episodes)
            }

        return success(resp_data, "Berhasil mendapatkan detail episode.")
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/animes/<slug>/scrape-fast")
def api_scrape_fast(slug: str):
    """
    Scrape episode secara instan di backend untuk judul tertentu.
    Jika ada anime yang belum memiliki episode nyata, pengguna bisa klik
    'Ambil Episode Sekarang' dan backend akan mengambil link streaming dari OtakuDesu.
    """
    anime = get_anime_by_slug(slug)
    if not anime:
        return error(f"Anime '{slug}' tidak ditemukan.", 404)
    
    try:
        from scraper import fetch_page, scrape_anime_detail, scrape_episode_embed
        import urllib.parse
        
        # Cari judul di OtakuDesu
        query = re.split(r'[:\-\(]', anime["title"])[0].strip()
        search_url = f"https://otakudesu.blog/?s={urllib.parse.quote(query)}&post_type=anime"
        soup = fetch_page(search_url)
        if not soup:
            return error("Gagal menghubungi server sumber.", 502)
        
        items = soup.select("ul.chivsrc li h2 a")
        if not items:
            return error(f"Anime '{query}' tidak ditemukan di situs sumber.", 404)
        
        target_link = items[0]["href"]
        detail = scrape_anime_detail(target_link)
        if not detail or not detail.get("episode_links"):
            return error("Tidak ada episode yang dapat diambil dari sumber.", 404)
        
        from models import upsert_episode
        eps_added = 0
        for ep_info in detail["episode_links"][:12]:
            embed_url = scrape_episode_embed(ep_info["url"])
            if embed_url:
                upsert_episode({
                    "anime_id": anime["id"],
                    "ep_number": ep_info["ep_number"],
                    "title": ep_info["title"],
                    "embed_url": embed_url,
                    "source_url": ep_info["url"],
                })
                eps_added += 1
        
        if eps_added > 0:
            return success({"added": eps_added}, f"Berhasil menambahkan {eps_added} episode nyata!")
        else:
            return error("Server stream sedang dalam antrian pembaruan.", 503)
    except Exception as e:
        return error(f"Error scraping: {e}", 500)


@app.route("/api/episodes/latest")
def api_get_latest_episodes():
    """
    GET /api/episodes/latest
    Query params: limit (default 20)
    Episode terbaru yang diupload (join dengan data anime).
    """
    try:
        try:
            merge_tokyo_revengers_and_duplicates()
        except Exception:
            pass
        limit = int(request.args.get("limit", 20))
        episodes = get_latest_episodes(limit=limit)
        return success(episodes, f"Berhasil mendapatkan {len(episodes)} episode terbaru.")
    except Exception as e:
        return error(str(e), 500)


# ─────────────────────────────────────────────
#  ENDPOINT: SINKRONISASI OTOMATIS ANIME HARIAN
# ─────────────────────────────────────────────

@app.route("/api/sync/status")
def api_get_sync_status():
    """GET /api/sync/status — Mengetahui status pembaruan otomatis."""
    try:
        from auto_updater import get_sync_status
        return success(get_sync_status(), "Status sinkronisasi otomatis.")
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/sync/latest", methods=["GET", "POST"])
def api_sync_latest_now():
    """
    GET/POST /api/sync/latest
    Memicu pemeriksaan dan upload anime baru yang update hari ini secara langsung.
    """
    try:
        import threading
        from auto_updater import sync_latest_ongoing
        async_mode = request.args.get("async", "true").lower() == "true"
        if async_mode:
            threading.Thread(target=sync_latest_ongoing, kwargs={"limit": 25}, daemon=True).start()
            return success({"started": True}, "Pemeriksaan update anime sedang berlangsung di latar belakang.")
        else:
            res = sync_latest_ongoing(limit=25)
            return success(res, res.get("message", "Sinkronisasi selesai."))
    except Exception as e:
        return error(str(e), 500)


# ─────────────────────────────────────────────
#  STREAM PROXY (BYPASS CSP FRAME-ANCESTORS DESUSTREAM/OTAKUWATCH)
# ─────────────────────────────────────────────

@app.route("/api/video-stream", methods=["GET", "HEAD", "OPTIONS"])
def api_video_stream():
    """
    Stream video MP4 langsung dari CDN melalui backend lokal
    dengan dukungan penuh HTTP Range (pause, fast-forward, rewind)
    tanpa terhalang CORS atau batasan referer browser.
    """
    if request.method == "OPTIONS":
        opt_resp = Response("", status=200)
        opt_resp.headers["Access-Control-Allow-Origin"] = "*"
        opt_resp.headers["Access-Control-Allow-Methods"] = "GET, HEAD, OPTIONS"
        opt_resp.headers["Access-Control-Allow-Headers"] = "*"
        opt_resp.headers["Access-Control-Expose-Headers"] = "Content-Range, Content-Length, Accept-Ranges"
        return opt_resp

    import urllib.parse
    raw_query = request.query_string.decode("utf-8") if request.query_string else ""
    video_url = request.args.get("url")
    ref_param = request.args.get("ref", "")

    if not video_url and "url=" in raw_query:
        url_part = raw_query.split("url=", 1)[1]
        url_part = re.sub(r'&ref=[^&]*', '', url_part)
        url_part = re.sub(r'&ngrok-skip-browser-warning=[^&]*', '', url_part)
        url_part = re.sub(r'&quality=[^&]*', '', url_part)
        url_part = re.sub(r'&_t=[^&]*', '', url_part)
        video_url = urllib.parse.unquote(url_part)

    if not video_url:
        return "Video URL missing", 400

    # Pastikan spasi di video_url tidak menyebabkan InvalidURL di python requests
    video_url = video_url.strip().replace(" ", "%20")

    range_header = request.headers.get("Range", None)

    # Prioritaskan tanpa Referer (paling kompatibel dengan GoogleVideo/Blogger/Archive),
    # lalu coba referer target, dan referer umum CDN jika diperlukan
    referer_candidates = [
        None,
        ref_param if ref_param else None,
        "https://archive.org/",
        "https://desustream.net/",
        "https://desustream.com/",
        "https://otakudesu.blog/",
    ]
    candidates = []
    for c in referer_candidates:
        if c not in candidates:
            candidates.append(c)

    r = None
    for cand_ref in candidates:
        try:
            req_headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            }
            if cand_ref:
                req_headers["Referer"] = cand_ref
            if range_header:
                req_headers["Range"] = range_header

            resp = requests.get(
                video_url,
                headers=req_headers,
                stream=True,
                timeout=15,
                allow_redirects=True,
                proxies={"http": None, "https": None}
            )
            if resp.status_code in [200, 206]:
                r = resp
                break
        except Exception as e:
            continue

    if not r:
        return "Gagal memuat video stream dari sumber", 502

    content_type = r.headers.get("Content-Type", "video/mp4")
    if not content_type or content_type in ["application/octet-stream", "binary/octet-stream"] or ".mp4" in video_url:
        content_type = "video/mp4"

    resp_headers = {
        "Content-Type": content_type,
        "Accept-Ranges": "bytes",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Expose-Headers": "Content-Range, Content-Length, Accept-Ranges",
    }
    if "Content-Range" in r.headers:
        resp_headers["Content-Range"] = r.headers["Content-Range"]
    if "Content-Length" in r.headers:
        resp_headers["Content-Length"] = r.headers["Content-Length"]

    # Dukungan unduhan direct MP4 ke memori perangkat
    if request.args.get("download") == "1":
        raw_fn = request.args.get("filename", "anime_episode.mp4")
        safe_fn = re.sub(r'[\\/*?:"<>|]', "", raw_fn).strip()
        if not safe_fn.endswith(".mp4"):
            safe_fn += ".mp4"
        safe_ascii_fn = re.sub(r'[^\w\s\-\.]', '', safe_fn).strip() or "episode.mp4"
        encoded_fn = urllib.parse.quote(safe_fn)
        resp_headers["Content-Disposition"] = f'attachment; filename="{safe_ascii_fn}"; filename*=UTF-8\'\'{encoded_fn}'

    if request.method == "HEAD":
        return Response("", status=r.status_code, headers=resp_headers)

    try:
        def generate():
            for chunk in r.iter_content(chunk_size=1024 * 64):
                if chunk:
                    yield chunk

        return Response(generate(), status=r.status_code, headers=resp_headers)
    except Exception as e:
        return f"Stream error: {e}", 500


@app.route("/api/playerjs.js")
@app.route("/playerjs.js")
def api_serve_playerjs():
    """Melayani library Playerjs lokal agar embed yang memanggil playerjs.js tidak mengalami 404."""
    return send_from_directory(FRONTEND_DIR, "playerjs.js", mimetype="application/javascript")


@app.route("/api/stream-proxy")
def api_stream_proxy():
    """
    Proxy HTML video player stream agar tidak terblokir oleh
    CSP frame-ancestors / X-Frame-Options saat dijalankan di browser / mobile.
    Otomatis menyajikan pemutar video HTML5 responsif yang terhubung ke /api/video-stream.
    """
    import urllib.parse
    import re

    raw_query = request.query_string.decode("utf-8") if request.query_string else ""
    target_url = request.args.get("url")
    if not target_url and "url=" in raw_query:
        url_part = raw_query.split("url=", 1)[1]
        url_part = re.sub(r'&quality=[^&]*', '', url_part)
        url_part = re.sub(r'&_t=[^&]*', '', url_part)
        target_url = urllib.parse.unquote(url_part)
    if target_url:
        target_url = re.sub(r'&quality=[^&]*', '', target_url)
        target_url = re.sub(r'&_t=[^&]*', '', target_url)

    if not target_url:
        return "<div style='color:#fff;background:#0f1117;padding:30px;font-family:sans-serif;'>URL stream tidak ditemukan.</div>", 400

    def render_stream_recovery_html(failed_url: str, error_msg: str = "") -> Response:
        recovery_html = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Stream Recovery</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: #0b0e17;
            color: #f1f5f9;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            text-align: center;
            padding: 20px;
        }}
        .recovery-card {{
            background: rgba(18, 22, 34, 0.95);
            border: 1px solid rgba(124, 58, 237, 0.35);
            border-radius: 16px;
            padding: 28px 24px;
            max-width: 420px;
            width: 100%;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.8), 0 0 20px rgba(124, 58, 237, 0.2);
            animation: fadeIn 0.3s ease;
        }}
        .icon-pulse {{
            font-size: 38px;
            margin-bottom: 12px;
            display: inline-block;
            animation: bounce 1.8s infinite ease-in-out;
        }}
        h3 {{
            font-size: 1.05rem;
            color: #fca5a5;
            margin-bottom: 8px;
            font-weight: 700;
        }}
        p {{
            font-size: 0.82rem;
            color: #94a3b8;
            line-height: 1.45;
            margin-bottom: 18px;
        }}
        .timer-bar {{
            height: 4px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 2px;
            overflow: hidden;
            margin-bottom: 18px;
        }}
        .timer-progress {{
            height: 100%;
            width: 100%;
            background: linear-gradient(90deg, #7c3aed, #06b6d4);
            animation: shrinkProgress 2s linear forwards;
        }}
        .btn-group {{
            display: flex;
            gap: 10px;
            justify-content: center;
            flex-wrap: wrap;
        }}
        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 9px 16px;
            border-radius: 8px;
            font-size: 0.82rem;
            font-weight: 600;
            cursor: pointer;
            border: none;
            text-decoration: none;
            transition: all 0.2s ease;
        }}
        .btn-primary {{
            background: linear-gradient(135deg, #7c3aed, #06b6d4);
            color: #fff;
            box-shadow: 0 4px 14px rgba(124, 58, 237, 0.4);
        }}
        .btn-secondary {{
            background: rgba(255, 255, 255, 0.08);
            color: #cbd5e1;
            border: 1px solid rgba(255, 255, 255, 0.15);
        }}
        @keyframes bounce {{
            0%, 100% {{ transform: translateY(0); }}
            50% {{ transform: translateY(-6px); }}
        }}
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: scale(0.96); }}
            to {{ opacity: 1; transform: scale(1); }}
        }}
        @keyframes shrinkProgress {{
            from {{ width: 100%; }}
            to {{ width: 0%; }}
        }}
    </style>
</head>
<body>
    <div class="recovery-card">
        <div class="icon-pulse">⚡</div>
        <h3>Server Sedang Gangguan (502 / Offline)</h3>
        <p>Penyedia video utama sedang bermasalah. Mengalihkan ke Server Cadangan lain secara otomatis...</p>
        <div class="timer-bar"><div class="timer-progress"></div></div>
        <div class="btn-group">
            <button class="btn btn-primary" onclick="triggerSwitch()">🔀 Ganti Server Cadangan</button>
            <button class="btn btn-secondary" onclick="window.location.reload()">🔄 Coba Lagi</button>
        </div>
    </div>
    <script>
        function triggerSwitch() {{
            try {{ window.parent.postMessage({{ type: 'STREAM_FAILED', error: '502', targetUrl: '{failed_url}' }}, '*'); }} catch(e) {{}}
            try {{ window.parent.postMessage({{ type: 'SWITCH_SERVER' }}, '*'); }} catch(e) {{}}
        }}
        setTimeout(triggerSwitch, 1600);
    </script>
</body>
</html>"""
        resp = Response(recovery_html, status=200, mimetype="text/html")
        resp.headers["X-Frame-Options"] = "ALLOWALL"
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp

    def is_genuine_video_url(url: str) -> bool:
        if not url or not isinstance(url, str) or not url.startswith("http"):
            return False
        u = url.lower().split("?")[0]
        # Filter ketat: gambar, storyboard thumbnail mosaic, preview, sprite, subtitle BUKAN video!
        ASSET_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.vtt', '.srt', '.svg', '.css', '.js')
        if any(u.endswith(ext) for ext in ASSET_EXTS):
            return False
        if any(bad in u for bad in ['storyboard', 'preview.jpg', 'thumbnail', 'sprite', 'poster', 'thumb/', 'previews']):
            return False
        # Harus mengandung format stream video valid
        VIDEO_EXTS = ('.mp4', '.webm', '.m3u8', '/stream/', 'googlevideo.com', 'playlist.m3u8', 'master.m3u8', 'archive.org/download')
        return any(v in u for v in VIDEO_EXTS)

    def unpack_dean_edwards(packed_str: str) -> str:
        m = re.search(r"\}\('(.*)',\s*(\d+),\s*(\d+),\s*'([^']*)'\.split\('\|'\)", packed_str)
        if not m:
            return None
        p, a, c, k = m.groups()
        a = int(a)
        c = int(c)
        k = k.split('|')
        digits = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        def base_decode(num_str: str, base: int) -> int:
            val = 0
            for char in num_str:
                idx = digits.find(char)
                if idx == -1 or idx >= base:
                    return -1
                val = val * base + idx
            return val
        def lookup(val_str):
            val = base_decode(val_str, a)
            if 0 <= val < len(k) and k[val]:
                return k[val]
            return val_str
        return re.sub(r'\b\w+\b', lambda m: lookup(m.group(0)), p)

    try:
        quality = request.args.get("quality", "720p").lower()
        direct_video_url = None

        if is_genuine_video_url(target_url):
            direct_video_url = target_url
        else:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": "https://otakudesu.blog/"
            }

            try:
                resp = requests.get(
                    target_url,
                    headers=headers,
                    timeout=12,
                    proxies={"http": None, "https": None}
                )
            except Exception as conn_err:
                return render_stream_recovery_html(target_url, str(conn_err))

            html = resp.text.replace("&amp;", "&")

            # Deteksi jika server penyedia stream down (Cloudflare 502/503/504, 404, bad gateway, file expired/deleted)
            html_lower = html.lower()
            is_server_down = (
                resp.status_code >= 500 or
                resp.status_code in [403, 404, 502, 503, 504] or
                "502 bad gateway" in html_lower or
                "error code 502" in html_lower or
                "error code 521" in html_lower or
                "error code 520" in html_lower or
                "error code 522" in html_lower or
                "error code 524" in html_lower or
                "player_blank.jpg" in html_lower or
                "no image available" in html_lower or
                "file is no longer available" in html_lower or
                "has been deleted" in html_lower or
                "file was deleted" in html_lower or
                ("cloudflare" in html_lower and ("502 bad gateway" in html_lower or "503 service unavailable" in html_lower or "error 521" in html_lower or "web server is down" in html_lower))
            )
            if is_server_down:
                return render_stream_recovery_html(target_url, f"Server status {resp.status_code}")

            # Unpack script untuk mencari stream asli VidHide/StreamWish
            unpacked_code = ""
            for sm in re.finditer(r'<script[^>]*>(.*?)</script>', html, flags=re.DOTALL):
                sb = sm.group(1)
                if "eval(function" in sb:
                    unp = unpack_dean_edwards(sb)
                    if unp:
                        unpacked_code += " " + unp

            search_pool = html + " " + unpacked_code

            # 1. Cari direct video source yang valid (BUKAN thumbnail / preview storyboard)
            for m_cand in re.finditer(r'file\s*:\s*["\'](https?://[^"\']+)["\']', search_pool):
                cand = m_cand.group(1).replace("&amp;", "&")
                if is_genuine_video_url(cand):
                    direct_video_url = cand
                    break

            if not direct_video_url:
                for m_cand in re.finditer(r'src=["\'](https?://[^"\']+)["\']', search_pool):
                    cand = m_cand.group(1).replace("&amp;", "&")
                    if is_genuine_video_url(cand):
                        direct_video_url = cand
                        break

            if not direct_video_url:
                m_mp4 = re.search(r'(https?://[^"\'\s<>]+\.(?:mp4|webm|m3u8)[^"\'\s<>]*)', search_pool)
                if m_mp4 and is_genuine_video_url(m_mp4.group(1)):
                    direct_video_url = m_mp4.group(1).replace("&amp;", "&")

        if direct_video_url:
            proxied_video_url = f"/api/video-stream?ngrok-skip-browser-warning=1&url={urllib.parse.quote(direct_video_url)}&ref={urllib.parse.quote(target_url)}"
            is_hd = quality in ["1080p", "720p"]
            badge_label = f"{quality.upper()} HD" if is_hd else f"{quality.upper()}"
            badge_class = "res-badge hd" if is_hd else "res-badge"

            clean_player_html = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="referrer" content="no-referrer">
    <title>Video Player</title>
    <script src="https://cdn.jsdelivr.net/npm/hls.js@1.5.8/dist/hls.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; -webkit-touch-callout: none !important; user-select: none !important; -webkit-user-select: none !important; }}
        body, html {{ width: 100%; height: 100%; background: #000; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; -webkit-touch-callout: none !important; }}
        .player-container {{ position: relative; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; -webkit-touch-callout: none !important; }}
        video {{ width: 100%; height: 100%; object-fit: contain; background: #000; outline: none; transition: filter 0.3s ease; -webkit-touch-callout: none !important; user-select: none !important; -webkit-user-select: none !important; }}
        video.quality-1080p {{
            image-rendering: -webkit-optimize-contrast;
            filter: contrast(1.06) saturate(1.08) brightness(1.01);
        }}
        video.quality-720p {{
            image-rendering: -webkit-optimize-contrast;
            filter: contrast(1.02) saturate(1.04);
        }}
        video.quality-480p {{
            filter: none;
        }}
        video.quality-360p {{
            filter: contrast(0.98);
        }}
        video.quality-144p {{
            image-rendering: pixelated;
            filter: contrast(0.92) brightness(0.95);
        }}
        .speed-badge {{
            position: absolute;
            top: 20px;
            left: 50%;
            transform: translateX(-50%) scale(0.85);
            background: rgba(15, 17, 23, 0.92);
            border: 1px solid #00cec9;
            color: #00cec9;
            padding: 7px 18px;
            border-radius: 25px;
            font-size: 13px;
            font-weight: 800;
            letter-spacing: 0.5px;
            display: none;
            align-items: center;
            gap: 8px;
            z-index: 35;
            box-shadow: 0 0 25px rgba(0, 206, 201, 0.6);
            backdrop-filter: blur(10px);
            transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.2s ease;
            pointer-events: none;
        }}
        .speed-badge.show {{
            display: flex;
            transform: translateX(-50%) scale(1);
        }}
        .res-badge {{
            position: absolute;
            top: 14px;
            right: 14px;
            background: rgba(15, 17, 23, 0.8);
            backdrop-filter: blur(8px);
            color: #00cec9;
            border: 1px solid rgba(0, 206, 201, 0.4);
            padding: 5px 12px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.5px;
            z-index: 15;
            pointer-events: none;
            transition: all 0.3s ease;
            box-shadow: 0 2px 10px rgba(0,0,0,0.5);
        }}
        .res-badge.hd {{
            color: #fff;
            background: rgba(124, 58, 237, 0.85);
            border: 1px solid rgba(167, 139, 250, 0.6);
            box-shadow: 0 0 14px rgba(124, 58, 237, 0.5);
        }}
        .big-play-btn {{
            position: absolute;
            width: 80px;
            height: 80px;
            border-radius: 50%;
            background: rgba(108, 92, 231, 0.85);
            box-shadow: 0 0 30px rgba(108, 92, 231, 0.6);
            border: 2px solid rgba(255, 255, 255, 0.4);
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.25s ease;
            z-index: 10;
        }}
        .big-play-btn:hover {{
            transform: scale(1.1);
            background: rgba(108, 92, 231, 1);
            box-shadow: 0 0 40px rgba(108, 92, 231, 0.9);
        }}
        .big-play-btn svg {{
            width: 36px;
            height: 36px;
            fill: #fff;
            margin-left: 4px;
        }}
        .unmute-banner {{
            position: absolute;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(15, 17, 23, 0.88);
            border: 1px solid #6c5ce7;
            color: #fff;
            padding: 8px 18px;
            border-radius: 20px;
            font-size: 13px;
            display: none;
            align-items: center;
            gap: 8px;
            cursor: pointer;
            z-index: 20;
            box-shadow: 0 4px 15px rgba(0,0,0,0.5);
            backdrop-filter: blur(8px);
            animation: pulse 2s infinite;
        }}
        .error-fallback {{
            position: absolute;
            inset: 0;
            background: rgba(15, 17, 23, 0.95);
            display: none;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            padding: 24px;
            z-index: 30;
        }}
        .error-fallback p {{
            color: #fff;
            margin-bottom: 12px;
            font-size: 14px;
        }}
        .error-fallback a {{
            background: #6c5ce7;
            color: #fff;
            padding: 8px 18px;
            border-radius: 8px;
            text-decoration: none;
            font-size: 13px;
            font-weight: 600;
        }}
        .in-player-next-btn {{
            position: absolute;
            top: 14px;
            left: 14px;
            background: rgba(124, 58, 237, 0.88);
            color: #fff;
            border: 1px solid rgba(255, 255, 255, 0.35);
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: 700;
            cursor: pointer;
            z-index: 20;
            backdrop-filter: blur(8px);
            transition: all 0.25s ease;
            box-shadow: 0 4px 14px rgba(0, 0, 0, 0.6);
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }}
        .in-player-next-btn:hover {{
            background: #06b6d4;
            transform: scale(1.05);
        }}
        @keyframes pulse {{
            0%, 100% {{ transform: translateX(-50%) scale(1); }}
            50% {{ transform: translateX(-50%) scale(1.03); }}
        }}
    </style>
</head>
<body>
    <div class="player-container">
        <video id="vplayer" class="quality-{quality}" controls playsinline preload="auto" src="{proxied_video_url}">
            Browser Anda tidak mendukung video HTML5.
        </video>
        <div id="speed-badge" class="speed-badge">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M13 2.05v3.03c3.39.49 6 3.39 6 6.92 0 .9-.18 1.75-.48 2.54l2.6 1.53c.56-1.24.88-2.62.88-4.07 0-5.18-3.95-9.45-9-9.95zM12 19c-3.87 0-7-3.13-7-7 0-3.53 2.61-6.43 6-6.92V2.05c-5.05.5-9 4.77-9 9.95 0 5.52 4.47 10 9.99 10 3.31 0 6.24-1.61 8.01-4.09l-2.49-1.46C16.14 17.84 14.2 19 12 19zm1-8.5v4.5l3.5-2.25L13 10.5z"/></svg>
            <span>⚡ 2X Kecepatan</span>
        </div>
        <button id="in-player-next-btn" class="in-player-next-btn" onclick="triggerNext()" title="Putar Episode Selanjutnya">
            <span>⏭ Next Eps</span>
        </button>
        <div id="res-badge" class="{badge_class}">{badge_label}</div>
        <div id="play-overlay" class="big-play-btn" title="Klik untuk memutar">
            <svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
        </div>
        <div id="unmute-banner" class="unmute-banner" onclick="unmuteVideo()">
            <span>🔊 Mode senyap — Klik di sini untuk mengaktifkan suara</span>
        </div>
        <div id="error-fallback" class="error-fallback">
            <p>⚠️ Stream sedang buffering atau memerlukan akses langsung.</p>
            <a href="{target_url}" target="_blank">↗ Buka Player Sumber Langsung</a>
        </div>
    </div>
    <script>
        const v = document.getElementById('vplayer');
        const overlay = document.getElementById('play-overlay');
        const banner = document.getElementById('unmute-banner');
        const resBadge = document.getElementById('res-badge');
        const errFallback = document.getElementById('error-fallback');
        const speedBadge = document.getElementById('speed-badge');

        // Blokir total contextmenu bawaan (Download video, Picture-in-Picture)
        window.addEventListener('contextmenu', (e) => {{ e.preventDefault(); return false; }}, {{ capture: true }});
        document.addEventListener('contextmenu', (e) => {{ e.preventDefault(); return false; }}, {{ capture: true }});
        v.addEventListener('contextmenu', (e) => {{ e.preventDefault(); return false; }}, {{ capture: true }});

        // Fitur Long Press -> Kecepatan 2X Lipat
        let speedTimer = null;
        let is2xActive = false;
        let normalSpeed = 1.0;

        function activate2xSpeed() {{
            if (v.paused) return;
            normalSpeed = v.playbackRate || 1.0;
            v.playbackRate = 2.0;
            is2xActive = true;
            if (speedBadge) speedBadge.classList.add('show');
            try {{ if (navigator.vibrate) navigator.vibrate(35); }} catch(e) {{}}
        }}

        function deactivate2xSpeed() {{
            if (speedTimer) {{
                clearTimeout(speedTimer);
                speedTimer = null;
            }}
            if (is2xActive) {{
                v.playbackRate = normalSpeed || 1.0;
                is2xActive = false;
                if (speedBadge) speedBadge.classList.remove('show');
            }}
        }}

        const container = document.querySelector('.player-container');
        container.addEventListener('pointerdown', (e) => {{
            if (e.target.closest('button') || e.target.closest('.res-badge')) return;
            deactivate2xSpeed();
            speedTimer = setTimeout(activate2xSpeed, 260);
        }});
        container.addEventListener('pointerup', deactivate2xSpeed);
        container.addEventListener('pointercancel', deactivate2xSpeed);
        container.addEventListener('pointerleave', deactivate2xSpeed);
        container.addEventListener('touchend', deactivate2xSpeed);
        container.addEventListener('touchcancel', deactivate2xSpeed);

        function startPlayback() {{
            v.play().then(() => {{
                overlay.style.display = 'none';
            }}).catch(() => {{
                v.muted = true;
                v.play().then(() => {{
                    overlay.style.display = 'none';
                    banner.style.display = 'flex';
                }}).catch(() => {{
                    overlay.style.display = 'flex';
                }});
            }});
        }}

        function triggerNext() {{
            try {{ window.parent.postMessage({{ type: 'NEXT_EPISODE' }}, '*'); }} catch(e) {{}}
        }}

        v.addEventListener('ended', () => {{
            triggerNext();
        }});

        function unmuteVideo() {{
            v.muted = false;
            banner.style.display = 'none';
        }}

        overlay.addEventListener('click', () => {{
            v.muted = false;
            v.play();
            overlay.style.display = 'none';
        }});

        v.addEventListener('play', () => {{
            overlay.style.display = 'none';
        }});

        v.addEventListener('pause', () => {{
            overlay.style.display = 'flex';
        }});

        v.addEventListener('error', () => {{
            console.warn('Video stream error, trying direct video...');
            if (!v.dataset.retried) {{
                v.dataset.retried = '1';
                v.src = '{direct_video_url}';
                v.play().catch(() => {{
                    if (errFallback) errFallback.style.display = 'flex';
                    try {{ window.parent.postMessage({{ type: 'STREAM_FAILED' }}, '*'); }} catch(e) {{}}
                }});
            }} else {{
                if (errFallback) errFallback.style.display = 'flex';
                try {{ window.parent.postMessage({{ type: 'STREAM_FAILED' }}, '*'); }} catch(e) {{}}
            }}
        }});

        // Terima pesan kontrol dari parent window (resolusi, skip opening, pip)
        window.addEventListener('message', (e) => {{
            if (!e.data) return;
            if (e.data.type === 'CHANGE_QUALITY') {{
                const q = (e.data.quality || '720p').toLowerCase();
                v.className = 'quality-' + q;
                if (resBadge) {{
                    const isHd = q === '1080p' || q === '720p';
                    resBadge.textContent = q.toUpperCase() + (isHd ? ' HD' : '');
                    resBadge.className = isHd ? 'res-badge hd' : 'res-badge';
                    resBadge.style.opacity = '1';
                    setTimeout(() => {{ resBadge.style.opacity = '0.75'; }}, 2500);
                }}
            }} else if (e.data.type === 'SEEK_FORWARD') {{
                const secs = e.data.seconds || 85;
                v.currentTime = Math.min((v.duration || Infinity), (v.currentTime || 0) + secs);
            }} else if (e.data.type === 'SEEK_BACKWARD') {{
                const secs = e.data.seconds || 10;
                v.currentTime = Math.max(0, (v.currentTime || 0) - secs);
            }} else if (e.data.type === 'REQUEST_PIP') {{
                try {{
                    if (document.pictureInPictureElement) {{
                        document.exitPictureInPicture();
                    }} else if (v.requestPictureInPicture) {{
                        v.requestPictureInPicture();
                    }}
                }} catch(err) {{}}
            }}
        }});

        let hlsObj = null;
        function setupVideoSource() {{
            const rawUrl = "{direct_video_url}";
            const isM3u8 = rawUrl.includes('.m3u8') || rawUrl.includes('/stream/') || rawUrl.includes('master');
            if (isM3u8 && window.Hls && Hls.isSupported()) {{
                try {{
                    hlsObj = new Hls({{ enableWorker: true, lowLatencyMode: true }});
                    hlsObj.loadSource(rawUrl);
                    hlsObj.attachMedia(v);
                    hlsObj.on(Hls.Events.MANIFEST_PARSED, () => {{
                        startPlayback();
                    }});
                    hlsObj.on(Hls.Events.ERROR, (event, data) => {{
                        if (data.fatal) {{
                            switch(data.type) {{
                                case Hls.ErrorTypes.NETWORK_ERROR:
                                    hlsObj.startLoad();
                                    break;
                                case Hls.ErrorTypes.MEDIA_ERROR:
                                    hlsObj.recoverMediaError();
                                    break;
                                default:
                                    v.src = '{proxied_video_url}';
                                    startPlayback();
                                    break;
                            }}
                        }}
                    }});
                    return;
                }} catch(e) {{
                    console.warn('Hls setup error:', e);
                }}
            }}
            v.src = '{proxied_video_url}';
            startPlayback();
        }}

        window.addEventListener('load', () => {{
            setupVideoSource();
        }});
    </script>
</body>
</html>"""
            proxy_resp = Response(clean_player_html, status=200, mimetype="text/html")
            proxy_resp.headers["X-Frame-Options"] = "ALLOWALL"
            proxy_resp.headers["Access-Control-Allow-Origin"] = "*"
            return proxy_resp

        # Jika bukan direct video, tangani provider embed seperti VidHide, EarnVids, DesuStream, StreamWish, Callistanise
        base_domain = f"{urllib.parse.urlparse(target_url).scheme}://{urllib.parse.urlparse(target_url).netloc}"
        if any(h in target_url.lower() for h in ['vidhide', 'callistanise', 'earnvids', 'streamwish', 'filelions', 'desustream']):
            html = html.replace('href="/', f'href="{base_domain}/')
            html = html.replace('src="/', f'src="{base_domain}/')
            def replacer(match):
                script_body = match.group(1)
                if "eval(function" in script_body:
                    unp = unpack_dean_edwards(script_body)
                    if unp:
                        unp = unp.replace('"/stream/', f'"{base_domain}/stream/')
                        unp = unp.replace("'/stream/", f"'{base_domain}/stream/")
                        return f"<script>{unp}</script>"
                return match.group(0)
            html = re.sub(r'<script[^>]*>(.*?)</script>', replacer, html, flags=re.DOTALL)

        # Hilangkan meta CSP & batasan X-Frame-Options
        html = re.sub(r'<meta[^>]*http-equiv=["\']Content-Security-Policy["\'][^>]*>', '', html, flags=re.IGNORECASE)
        # Arahkan script playerjs lokal agar tidak 404
        html = re.sub(r'''src=['"](?:\./)?playerjs\.js['"]''', 'src="/playerjs.js"', html, flags=re.IGNORECASE)

        injected_controls = """<style>
            * { -webkit-touch-callout: none !important; user-select: none !important; -webkit-user-select: none !important; }
            .in-player-next-btn {
                position: fixed; top: 12px; left: 12px;
                background: rgba(124, 58, 237, 0.88); color: #fff;
                border: 1px solid rgba(255, 255, 255, 0.35); padding: 6px 14px;
                border-radius: 20px; font-size: 11px; font-weight: 700; cursor: pointer;
                z-index: 99999; backdrop-filter: blur(8px);
                box-shadow: 0 4px 14px rgba(0, 0, 0, 0.6); display: inline-flex; align-items: center; gap: 4px;
            }
            .in-player-next-btn:hover { background: #06b6d4; }
        </style>
        <button class="in-player-next-btn" onclick="try{window.parent.postMessage({type:'NEXT_EPISODE'},'*');}catch(e){}" title="Putar Episode Selanjutnya">
            <span>⏭ Next Eps</span>
        </button>
        <script>
            window.addEventListener('contextmenu', (e) => { e.preventDefault(); return false; }, { capture: true });
            document.addEventListener('contextmenu', (e) => { e.preventDefault(); return false; }, { capture: true });
        </script>"""

        # Injeksi base, referrer, dan kontrol ke provider embed
        base_tag = f'<base href="{target_url}"><meta name="referrer" content="origin-when-cross-origin">' + injected_controls
        if "<head>" in html:
            html = html.replace("<head>", f'<head>{base_tag}')
        else:
            html = base_tag + html

        proxy_resp = Response(html, status=resp.status_code, mimetype="text/html")
        proxy_resp.headers["X-Frame-Options"] = "ALLOWALL"
        proxy_resp.headers["Access-Control-Allow-Origin"] = "*"
        proxy_resp.headers.pop("Content-Security-Policy", None)
        return proxy_resp
    except Exception as e:
        return render_stream_recovery_html(target_url, str(e))


@app.route("/stream/<path:subpath>")
def proxy_vidhide_stream_subpath(subpath):
    """Fallback proxy untuk stream relative /stream/... yang diminta browser ke origin."""
    target = f"https://odvidhide.com/stream/{subpath}"
    if request.query_string:
        target += f"?{request.query_string.decode('utf-8')}"
    headers = {
        "User-Agent": request.headers.get("User-Agent", "Mozilla/5.0"),
        "Referer": "https://odvidhide.com/"
    }
    try:
        r = requests.get(target, headers=headers, stream=True, timeout=15)
        return Response(r.iter_content(chunk_size=65536), status=r.status_code, content_type=r.headers.get("Content-Type", "application/vnd.apple.mpegurl"))
    except Exception as e:
        return f"Stream error: {e}", 502



# ─────────────────────────────────────────────
#  ERROR HANDLER GLOBAL
# ─────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return jsonify({"status": "error", "message": "Endpoint tidak ditemukan."}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"status": "error", "message": "Terjadi kesalahan di server."}), 500


# ─────────────────────────────────────────────
#  JALANKAN SERVER
# ─────────────────────────────────────────────

if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    port = int(os.environ.get("PORT", 5000))
    print("=" * 50)
    print("  Anime Streaming API Server")
    print(f"  Local URL : http://localhost:{port}")
    print(f"  LAN URL   : http://{get_lan_ip()}:{port}")
    print("=" * 50)
    app.run(debug=debug_mode, host="0.0.0.0", port=port, threaded=True)
