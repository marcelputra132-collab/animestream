import urllib.request
import json

try:
    # Test endpoint latest animes
    url = "http://localhost:5000/api/animes/latest"
    res = urllib.request.urlopen(url)
    data = json.loads(res.read())
    
    print("=" * 50)
    print("  TEST: GET /api/animes/latest")
    print("=" * 50)
    print(f"Status   : {data['status']}")
    print(f"Message  : {data['message']}")
    print(f"Total    : {len(data['data'])} anime")
    print()
    for a in data["data"]:
        print(f"  [{a['id']}] {a['title']}")
        print(f"       Status: {a['status']} | Score: {a['score']} | Eps: {a['total_eps']}")
    
    print()
    
    # Test endpoint episodes
    url2 = "http://localhost:5000/api/episodes/latest"
    res2 = urllib.request.urlopen(url2)
    data2 = json.loads(res2.read())
    
    print("=" * 50)
    print("  TEST: GET /api/episodes/latest")
    print("=" * 50)
    print(f"Status   : {data2['status']}")
    print(f"Total    : {len(data2['data'])} episode")
    for ep in data2["data"]:
        print(f"  [Ep {ep['ep_number']}] {ep['anime_title']}")

    print()
    print("[OK] Semua endpoint berfungsi dengan baik!")
    
except Exception as e:
    print(f"[ERROR] {e}")
