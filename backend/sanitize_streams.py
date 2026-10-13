import json
from database import get_connection

def main():
    conn = get_connection()
    cur = conn.cursor()
    rows = cur.execute("SELECT id, quality_streams FROM episodes WHERE quality_streams IS NOT NULL AND quality_streams != ''").fetchall()
    
    cleaned = 0
    bad_keywords = ["solidfiles", "zippyshare", "racaty", "tusfiles", "mediafire", "acefile", "mega.nz", "mirrorace", "hxfile"]
    
    for r in rows:
        ep_id = r["id"]
        qs_raw = r["quality_streams"]
        try:
            data = json.loads(qs_raw)
            sanitized = {}
            has_bad = False
            for k, v in data.items():
                if any(b in v.lower() for b in bad_keywords):
                    has_bad = True
                else:
                    sanitized[k] = v
            if has_bad:
                cur.execute("UPDATE episodes SET quality_streams = ? WHERE id = ?", (json.dumps(sanitized) if sanitized else None, ep_id))
                cleaned += 1
        except Exception as e:
            pass
            
    conn.commit()
    conn.close()
    print(f"Berhasil membersihkan link mati dari {cleaned} episode!")

if __name__ == "__main__":
    main()
