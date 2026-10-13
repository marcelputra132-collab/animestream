import sqlite3

conn = sqlite3.connect('anime_streaming.db')
cursor = conn.cursor()

# Cari anime Bleach
cursor.execute("SELECT id, title FROM animes WHERE title LIKE '%Bleach%' LIMIT 1")
anime = cursor.fetchone()

if anime:
    anime_id, title = anime
    print(f"Menambahkan episode untuk: {title} (ID: {anime_id})")
    
    sample_video = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
    for ep in range(1, 6):
        cursor.execute("""
            INSERT OR REPLACE INTO episodes (anime_id, ep_number, title, embed_url)
            VALUES (?, ?, ?, ?)
        """, (anime_id, ep, f"Episode {ep}", sample_video))
        
    conn.commit()
    print("Episode Bleach berhasil ditambahkan!")
else:
    print("Anime Bleach tidak ditemukan di database.")

conn.close()