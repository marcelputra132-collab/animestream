import requests, base64, json, re
from bs4 import BeautifulSoup

session = requests.Session()
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://otakudesu.blog/episode/bklclvr-episode-1-sub-indo/'
}
resp = session.get('https://otakudesu.blog/episode/bklclvr-episode-1-sub-indo/', headers=headers, timeout=12)
soup = BeautifulSoup(resp.text, 'html.parser')

scripts = [s.get_text() for s in soup.find_all('script') if '__x__nonce' in s.get_text()]
if scripts:
    actions = re.findall(r'action:[\"\']([a-f0-9]{32})[\"\']', scripts[0])
    if len(actions) >= 2:
        action_stream, action_nonce = actions[0], actions[1]
        rn = session.post('https://otakudesu.blog/wp-admin/admin-ajax.php', data={'action': action_nonce}, timeout=10)
        nonce = rn.json().get('data')
        print('Nonce acquired:', nonce)
        for q in ['720p', '480p', '360p']:
            links = soup.select(f'.mirrorstream ul.m{q} a[data-content]')
            for l in links:
                raw_b64 = l.get('data-content')
                payload = json.loads(base64.b64decode(raw_b64).decode())
                rs = session.post('https://otakudesu.blog/wp-admin/admin-ajax.php', data={**payload, 'nonce': nonce, 'action': action_stream}, headers={'Referer': 'https://otakudesu.blog/'}, timeout=10)
                res_data = rs.json().get('data')
                if res_data:
                    html = base64.b64decode(res_data).decode('utf-8', errors='ignore')
                    m = re.search(r'src=[\"\']([^\"\']+)[\"\']', html)
                    if m and 'maintenance' not in m.group(1):
                        server_name = l.text.strip()
                        print(f"Quality {q} [{server_name}]: {m.group(1)}")
                        break
