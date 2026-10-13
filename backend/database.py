"""
database.py — Konfigurasi dan inisialisasi database SQLite
Modul ini bertanggung jawab untuk membuat koneksi dan tabel database.
"""

import sqlite3
import os

# Path file database SQLite (dibuat otomatis di folder ini)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "anime_streaming.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "..", "database", "schema.sql")


def get_connection() -> sqlite3.Connection:
    """Membuat dan mengembalikan koneksi database SQLite."""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row  # Hasil query bisa diakses seperti dict
    conn.execute("PRAGMA journal_mode = WAL")  # Izinkan concurrent read & write tanpa lock
    conn.execute("PRAGMA busy_timeout = 30000")  # Tunggu hingga 30 detik sebelum timeout
    conn.execute("PRAGMA foreign_keys = ON")  # Aktifkan foreign key di SQLite
    return conn


def init_db():
    """Menginisialisasi database dengan schema SQL dari file schema.sql."""
    conn = get_connection()
    try:
        if os.path.exists(SCHEMA_PATH):
            with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                schema_sql = f.read()
            conn.executescript(schema_sql)
            conn.commit()
            print(f"[DB] Database berhasil diinisialisasi di: {DB_PATH}")
        else:
            # Buat tabel secara langsung jika file schema tidak ditemukan
            conn.executescript("""
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
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    anime_id INTEGER NOT NULL,
                    ep_number INTEGER NOT NULL,
                    title VARCHAR(255),
                    embed_url TEXT,
                    source_url TEXT,
                    duration VARCHAR(50),
                    thumbnail TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (anime_id) REFERENCES animes(id) ON DELETE CASCADE,
                    UNIQUE (anime_id, ep_number)
                );
                CREATE INDEX IF NOT EXISTS idx_episodes_anime_id ON episodes(anime_id);
                CREATE INDEX IF NOT EXISTS idx_animes_slug ON animes(slug);
            """)
            conn.commit()
            print(f"[DB] Tabel berhasil dibuat secara inline.")
    except Exception as e:
        print(f"[DB] Error saat inisialisasi: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
