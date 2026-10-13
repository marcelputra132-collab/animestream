"""
fix_video.py — Perbaiki dan perbarui link embed stream video asli dari sumber anime
Menghilangkan link YouTube dummy/error dan menggantinya dengan stream asli (OtakuWatch, DesuStream, MP4Upload, dll).
"""

import sqlite3
import os
import re
import json
import base64
import requests
import bs4

DB_PATH = os.path.join(os.path.dirname(__file__), "anime_streaming.db")

def resolve_otakudesu_embed(episode_url, session=None):
    if not episode_url:
        return ""
    if session is None:
        session = requests.Session()
    
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': episode_url
    })
    
    try:
        r = session.get(episode_url, timeout=12)
        if r.status_code != 200:
            return ""
        soup = bs4.BeautifulSoup(r.text, 'html.parser')
        
        # 1. Cek jika ada iframe langsung yang bukan maintenance
        for f in soup.find_all('iframe'):
            src = f.get('src') or f.get('data-src', '')
            if src and 'maintenance' not in src and 'about:blank' not in src:
                return src
                
        # 2. Cek script untuk admin-ajax
        scripts = [s.get_text() for s in soup.find_all('script') if '__x__nonce' in s.get_text()]
        if not scripts:
            return ""
            
        script = scripts[0]
        actions = re.findall(r'action:[\"\']([a-f0-9]{32})[\"\']', script)
        if len(actions) < 2:
            return ""
            
        action_stream = actions[0]
        action_nonce = actions[1]
        
        # Dapatkan nonce
        rn = session.post('https://otakudesu.blog/wp-admin/admin-ajax.php', data={'action': action_nonce}, timeout=10)
        nonce = rn.json().get('data')
        if not nonce:
            return ""
            
        # Ambil link mirror
        links = soup.select('.mirrorstream a[data-content]')
        # Prioritaskan otakuwatch / desustream
        links_sorted = sorted(links, key=lambda l: 0 if 'otakuwatch' in l.get_text().lower() or 'desu' in l.get_text().lower() else 1)
        
        for l in links_sorted:
            raw_b64 = l.get('data-content')
            if not raw_b64:
                continue
            try:
                payload = json.loads(base64.b64decode(raw_b64).decode())
                rs = session.post(
                    'https://otakudesu.blog/wp-admin/admin-ajax.php',
                    data={**payload, 'nonce': nonce, 'action': action_stream},
                    headers={'Referer': 'https://otakudesu.blog/'},
                    timeout=10
                )
                res_data = rs.json().get('data')
                if res_data:
                    html = base64.b64decode(res_data).decode('utf-8', errors='ignore')
                    m = re.search(r'src=[\"\']([^\"\']+)[\"\']', html)
                    if m:
                        src = m.group(1)
                        if 'maintenance' not in src:
                            return src
            except Exception:
                continue
    except Exception as e:
        print(f"  [ERROR] {episode_url}: {e}")
    return ""

def update_embed_links():
    if not os.path.exists(DB_PATH):
        print(f"[ERROR] Database tidak ditemukan di {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    animes = cursor.execute("SELECT id, slug, title, source_url FROM animes").fetchall()
    session = requests.Session()

    for anime in animes:
        anime_id = anime["id"]
        slug = anime["slug"]
        title = anime["title"]
        source_url = anime["source_url"]

        if source_url and "otakudesu" in source_url:
            print(f"Memproses anime: {title} ({slug})...")
            try:
                r = session.get(source_url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'
                }, timeout=12)
                soup = bs4.BeautifulSoup(r.text, 'html.parser')
                ep_items = soup.select('.episodelist ul li')
                
                ep_list = []
                for item in ep_items:
                    link = item.find('a')
                    if not link:
                        continue
                    href = link.get('href', '')
                    ep_title = link.get_text(strip=True)
                    
                    if '/batch/' in href or '/lengkap/' in href or '[batch]' in ep_title.lower():
                        continue
                        
                    m = re.search(r'(?:episode|ep)[\s\-]?(\d+)', ep_title, re.IGNORECASE)
                    if m:
                        ep_num = int(m.group(1))
                    elif 'ova' in ep_title.lower():
                        ep_num = 99
                    else:
                        continue
                        
                    ep_list.append({
                        'ep_number': ep_num,
                        'title': ep_title,
                        'url': href
                    })

                ep_list.sort(key=lambda x: x['ep_number'])

                if ep_list:
                    cursor.execute("DELETE FROM episodes WHERE anime_id = ?", (anime_id,))
                    conn.commit()

                    for ep in ep_list:
                        embed = resolve_otakudesu_embed(ep['url'], session)
                        cursor.execute("""
                            INSERT INTO episodes (anime_id, ep_number, title, embed_url, source_url)
                            VALUES (?, ?, ?, ?, ?)
                        """, (anime_id, ep['ep_number'], ep['title'], embed, ep['url']))
                        conn.commit()

                    cursor.execute("UPDATE animes SET total_eps = ? WHERE id = ?", (len(ep_list), anime_id))
                    conn.commit()
                    print(f"  -> {len(ep_list)} episode berhasil disimpan untuk {title}")

            except Exception as e:
                print(f"[ERROR] Gagal scrape anime {title}: {e}")

    conn.close()
    print("[SUKSES] Semua tautan stream episode telah diperbarui!")

if __name__ == "__main__":
    update_embed_links()