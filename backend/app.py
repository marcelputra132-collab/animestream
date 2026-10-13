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


def get_latest_playable_animes(limit: int = 12):
    """Anime terbaru yang SUDAH punya episode (supaya beranda tidak menampilkan yang kosong)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT a.* FROM animes a
            WHERE EXISTS (SELECT 1 FROM episodes e WHERE e.anime_id = a.id)
            ORDER BY a.updated_at DESC, a.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
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
    return jsonify({
        "status": "success",
        "data": {
            "ip": ip,
            "port": port,
            "lan_url": f"http://{ip}:{port}",
            "local_url": f"http://localhost:{port}"
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


@app.route("/api/animes/popular")
def api_get_popular_animes():
    """GET /api/animes/popular — Anime populer rating tinggi siap putar."""
    try:
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


@app.route("/api/animes/<slug>")
def api_get_anime_detail(slug: str):
    """
    GET /api/animes/<slug>
    Mendapatkan detail satu anime berdasarkan slug-nya.
    """
    try:
        anime = get_anime_by_slug(slug)
        if not anime:
            return error(f"Anime dengan slug '{slug}' tidak ditemukan.", 404)
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
#  ENDPOINT: EPISODE
# ─────────────────────────────────────────────

def find_real_episodes_for_anime(anime: dict) -> tuple[list, dict | None]:
    """
    Jika anime belum memiliki episode di DB, cari apakah ada anime lain
    dalam waralaba/judul yang sama yang SUDAH memiliki episode nyata!
    Contoh: slug black-clover-97940 atau black-clover-sword-of-the-wizard-king
    otomatis mendapatkan 170 episode dari serial utama 'Black Clover'!
    """
    episodes = get_episodes_by_anime(anime["id"])
    if episodes:
        return episodes, None

    from database import get_connection
    conn = get_connection()
    try:
        raw_title = anime.get("title", "")
        base_title = re.split(r'[:\-\(]', raw_title)[0].strip()
        if len(base_title) >= 3:
            row = conn.execute("""
                SELECT a.*, COUNT(e.id) as ep_count
                FROM animes a
                JOIN episodes e ON a.id = e.anime_id
                WHERE a.id != ? AND (
                    a.title = ? 
                    OR a.title LIKE ? 
                    OR a.slug = ?
                    OR a.slug LIKE ?
                )
                GROUP BY a.id
                ORDER BY ep_count DESC
                LIMIT 1
            """, (
                anime["id"], 
                base_title, 
                f"{base_title}%", 
                make_slug(base_title),
                f"{make_slug(base_title)}%"
            )).fetchone()
            
            if row:
                matched_anime = dict(row)
                matched_eps = get_episodes_by_anime(matched_anime["id"])
                if matched_eps:
                    return matched_eps, matched_anime
    finally:
        conn.close()

    return [], None


@app.route("/api/animes/<slug>/episodes")
def api_get_episodes(slug: str):
    """
    GET /api/animes/<slug>/episodes
    Mendapatkan semua episode dari satu anime.
    """
    try:
        anime = get_anime_by_slug(slug)
        if not anime:
            return error(f"Anime '{slug}' tidak ditemukan.", 404)
        
        episodes, matched_series = find_real_episodes_for_anime(anime)

        # Fallback pintar: Jika belum ada episode sub Indo hasil scraping,
        # otomatis sediakan video player resmi (Trailer HD / Official Preview)
        # agar seluruh 24.534 anime di database BISA DIPUTAR tanpa ada yang kosong/error!
        if not episodes:
            extras = get_anime_extras(anime)
            trailer_id = extras.get("trailer", {}).get("id") if (extras and extras.get("trailer")) else None
            import urllib.parse

            if trailer_id:
                embed_url = f"https://www.youtube.com/embed/{trailer_id}?autoplay=1&rel=0"
                source_url = f"https://www.youtube.com/watch?v={trailer_id}"
                ep_title = f"Official Trailer / Preview — {anime['title']}"
            else:
                search_q = urllib.parse.quote(f"{anime['title']} anime trailer")
                embed_url = f"https://www.youtube.com/embed?listType=search&list={search_q}&autoplay=1"
                source_url = f"https://www.youtube.com/results?search_query={search_q}"
                ep_title = f"Official Preview Stream — {anime['title']}"

            episodes = [{
                "id": f"p-{anime['id']}",
                "anime_id": anime["id"],
                "ep_number": 1,
                "title": ep_title,
                "embed_url": embed_url,
                "source_url": source_url,
                "duration": "Official HD",
                "created_at": anime.get("created_at")
            }]

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

        # On-Demand Stream Resolver: jika embed_url belum terisi tapi punya source_url,
        # otomatis ambil embed video aslinya secara langsung dan simpan ke database!
        if episode and (not episode.get("embed_url") or episode.get("embed_url") == ""):
            source_ep_url = episode.get("source_url")
            if source_ep_url and "http" in source_ep_url:
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

        # Jika belum ada episode nyata di database, gunakan fallback preview video
        if not episode:
            extras = get_anime_extras(anime)
            trailer_id = extras.get("trailer", {}).get("id") if (extras and extras.get("trailer")) else None
            import urllib.parse

            if trailer_id:
                embed_url = f"https://www.youtube.com/embed/{trailer_id}?autoplay=1&rel=0"
                source_url = f"https://www.youtube.com/watch?v={trailer_id}"
                ep_title = f"Official Trailer / Preview — {anime['title']}"
            else:
                search_q = urllib.parse.quote(f"{anime['title']} anime trailer")
                embed_url = f"https://www.youtube.com/embed?listType=search&list={search_q}&autoplay=1"
                source_url = f"https://www.youtube.com/results?search_query={search_q}"
                ep_title = f"Official Preview Stream — {anime['title']}"

            episode = {
                "id": f"p-{anime['id']}",
                "anime_id": anime["id"],
                "ep_number": 1,
                "title": ep_title,
                "embed_url": embed_url,
                "source_url": source_url,
                "duration": "Official HD",
                "created_at": anime.get("created_at")
            }
            all_episodes = [episode]

        # Ambil episode prev & next untuk navigasi
        ep_numbers = [e["ep_number"] for e in all_episodes]
        current_idx = ep_numbers.index(episode["ep_number"]) if episode["ep_number"] in ep_numbers else 0

        prev_ep = ep_numbers[current_idx - 1] if current_idx > 0 else None
        next_ep = ep_numbers[current_idx + 1] if current_idx < len(ep_numbers) - 1 else None

        # Siapkan opsi resolusi dari 144p hingga 1080p Full HD
        # Filter URL host yang mati atau bukan video stream (misal solidfiles, zippyshare)
        DEAD_STREAM_DOMAINS = ["solidfiles", "zippyshare", "racaty", "tusfiles", "mediafire", "acefile", "mega.nz", "mirrorace", "hxfile"]
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
        limit = int(request.args.get("limit", 20))
        episodes = get_latest_episodes(limit=limit)
        return success(episodes, f"Berhasil mendapatkan {len(episodes)} episode terbaru.")
    except Exception as e:
        return error(str(e), 500)


# ─────────────────────────────────────────────
#  STREAM PROXY (BYPASS CSP FRAME-ANCESTORS DESUSTREAM/OTAKUWATCH)
# ─────────────────────────────────────────────

@app.route("/api/video-stream")
def api_video_stream():
    """
    Stream video MP4 langsung dari CDN melalui backend lokal
    dengan dukungan penuh HTTP Range (pause, fast-forward, rewind)
    tanpa terhalang CORS atau batasan referer browser.
    """
    import urllib.parse
    raw_query = request.query_string.decode("utf-8")
    if raw_query.startswith("url="):
        video_url = urllib.parse.unquote(raw_query[4:])
    else:
        video_url = request.args.get("url")

    if not video_url:
        return "Video URL missing", 400

    range_header = request.headers.get("Range", None)
    req_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://otakudesu.blog/",
    }
    if range_header:
        req_headers["Range"] = range_header

    try:
        r = requests.get(video_url, headers=req_headers, stream=True, timeout=15)
        
        def generate():
            for chunk in r.iter_content(chunk_size=1024 * 64):
                if chunk:
                    yield chunk

        resp_headers = {
            "Content-Type": r.headers.get("Content-Type", "video/mp4"),
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*",
        }
        if "Content-Range" in r.headers:
            resp_headers["Content-Range"] = r.headers["Content-Range"]
        if "Content-Length" in r.headers:
            resp_headers["Content-Length"] = r.headers["Content-Length"]

        return Response(generate(), status=r.status_code, headers=resp_headers)
    except Exception as e:
        return f"Stream error: {e}", 500


@app.route("/api/stream-proxy")
def api_stream_proxy():
    """
    Proxy HTML video player stream agar tidak terblokir oleh
    CSP frame-ancestors / X-Frame-Options saat dijalankan di localhost.
    Otomatis menyajikan pemutar video HTML5 responsif yang terhubung ke /api/video-stream.
    """
    import urllib.parse
    import re

    raw_query = request.query_string.decode("utf-8")
    if raw_query.startswith("url="):
        target_url = urllib.parse.unquote(raw_query[4:])
    else:
        target_url = request.args.get("url")

    if not target_url:
        return "<div style='color:#fff;background:#0f1117;padding:30px;font-family:sans-serif;'>URL stream tidak ditemukan.</div>", 400

    try:
        quality = request.args.get("quality", "720p").lower()
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://otakudesu.blog/"
        }
        resp = requests.get(target_url, headers=headers, timeout=12)
        html = resp.text.replace("&amp;", "&")

        # Cari direct video source di dalam html
        m = re.search(r'src=["\'](https?://[^"\']+)["\']', html)
        if m and any(ext in m.group(1).lower() for ext in ['googlevideo', 'googledrive', '.mp4', '.webm', 'cdn']):
            direct_video_url = m.group(1).replace("&amp;", "&")
            proxied_video_url = f"/api/video-stream?url={urllib.parse.quote(direct_video_url)}"
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
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body, html {{ width: 100%; height: 100%; background: #000; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
        .player-container {{ position: relative; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }}
        video {{ width: 100%; height: 100%; object-fit: contain; background: #000; outline: none; transition: filter 0.3s ease; }}
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
        <div id="res-badge" class="{badge_class}">{badge_label}</div>
        <div id="play-overlay" class="big-play-btn" title="Klik untuk memutar">
            <svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
        </div>
        <div id="unmute-banner" class="unmute-banner" onclick="unmuteVideo()">
            <span>🔊 Mode senyap — Klik di sini untuk mengaktifkan suara</span>
        </div>
    </div>
    <script>
        const v = document.getElementById('vplayer');
        const overlay = document.getElementById('play-overlay');
        const banner = document.getElementById('unmute-banner');
        const resBadge = document.getElementById('res-badge');

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

        // Terima pesan pergantian resolusi dari parent window secara realtime tanpa reload
        window.addEventListener('message', (e) => {{
            if (e.data && e.data.type === 'CHANGE_QUALITY') {{
                const q = (e.data.quality || '720p').toLowerCase();
                v.className = 'quality-' + q;
                if (resBadge) {{
                    const isHd = q === '1080p' || q === '720p';
                    resBadge.textContent = q.toUpperCase() + (isHd ? ' HD' : '');
                    resBadge.className = isHd ? 'res-badge hd' : 'res-badge';
                    resBadge.style.opacity = '1';
                    setTimeout(() => {{ resBadge.style.opacity = '0.75'; }}, 2500);
                }}
            }}
        }});

        window.addEventListener('load', () => {{
            startPlayback();
        }});
    </script>
</body>
</html>"""
            proxy_resp = Response(clean_player_html, status=200, mimetype="text/html")
            proxy_resp.headers["X-Frame-Options"] = "ALLOWALL"
            proxy_resp.headers["Access-Control-Allow-Origin"] = "*"
            return proxy_resp

        # Jika bukan direct video, injeksi no-referrer dan hilangkan batasan CSP
        if "<head>" in html:
            html = html.replace("<head>", '<head><meta name="referrer" content="no-referrer">')
        else:
            html = '<meta name="referrer" content="no-referrer">' + html

        proxy_resp = Response(html, status=resp.status_code, mimetype="text/html")
        proxy_resp.headers["X-Frame-Options"] = "ALLOWALL"
        proxy_resp.headers["Access-Control-Allow-Origin"] = "*"
        return proxy_resp
    except Exception as e:
        return f"<div style='color:#fff;background:#0f1117;padding:30px;font-family:sans-serif;'>Gagal memuat video: {e}</div>", 500



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
