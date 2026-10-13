import re
from database import get_connection

def main():
    conn = get_connection()
    cur = conn.cursor()
    
    rows = cur.execute("SELECT id, title, genre FROM animes WHERE genre = 'Tidak diketahui' OR genre = '' OR genre IS NULL").fetchall()
    print(f"Total anime tanpa genre: {len(rows)}")
    
    updated = 0
    for r in rows:
        anime_id = r["id"]
        title = r["title"]
        # Ambil nama dasar judul (hapus season, ova, the animation, dll)
        clean = re.split(r"[:\-\(]| Season| Part| Movie", title)[0].strip()
        if len(clean) < 3:
            continue
            
        match = cur.execute(
            "SELECT genre FROM animes WHERE id != ? AND title LIKE ? AND genre != '' AND genre != 'Tidak diketahui' LIMIT 1",
            (anime_id, f"{clean}%")
        ).fetchone()
        
        if match and match["genre"]:
            cur.execute("UPDATE animes SET genre = ? WHERE id = ?", (match["genre"], anime_id))
            updated += 1
            
    conn.commit()
    conn.close()
    print(f"Berhasil memperbarui genre untuk {updated} anime!")

if __name__ == "__main__":
    main()
