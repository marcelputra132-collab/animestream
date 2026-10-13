import os
from PIL import Image, ImageDraw, ImageFont

ICONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "icons"))
os.makedirs(ICONS_DIR, exist_ok=True)

def create_app_icon(size):
    # Canvas hitam gelap dengan rounded corners
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Background rounded rect dengan warna ungu-indigo futuristik
    # Buat gradasi atau warna solid yang elegan
    padding = size // 16
    draw.rounded_rectangle(
        [padding, padding, size - padding, size - padding],
        radius=size // 4,
        fill=(108, 92, 231, 255),  # #6c5ce7
        outline=(162, 155, 254, 255),  # #a29bfe
        width=max(2, size // 64)
    )
    
    # Lingkaran dalam gelap
    inner_pad = size // 5
    draw.ellipse(
        [inner_pad, inner_pad, size - inner_pad, size - inner_pad],
        fill=(15, 17, 23, 230),  # #0f1117
        outline=(108, 92, 231, 200),
        width=max(1, size // 80)
    )
    
    # Ikon Segitiga Play Putih di tengah
    cx, cy = size // 2, size // 2
    r = size // 5
    # Titik sudut segitiga play
    p1 = (cx - r // 2, cy - r)
    p2 = (cx - r // 2, cy + r)
    p3 = (cx + r, cy)
    draw.polygon([p1, p2, p3], fill=(255, 255, 255, 255))
    
    # Tambah aksen glowing kecil
    draw.ellipse([cx + r - size//20, cy - size//20, cx + r + size//20, cy + size//20], fill=(0, 206, 201, 220))
    
    return img

icon_192 = create_app_icon(192)
icon_192.save(os.path.join(ICONS_DIR, "icon-192.png"))

icon_512 = create_app_icon(512)
icon_512.save(os.path.join(ICONS_DIR, "icon-512.png"))

# Simpan favicon.ico
icon_64 = create_app_icon(64)
icon_64.save(os.path.join(ICONS_DIR, "favicon.ico"), format="ICO")

print(f"Ikon berhasil dibuat di: {ICONS_DIR}")
