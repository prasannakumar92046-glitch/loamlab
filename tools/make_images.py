"""Generates the original artwork used by LoamLab (no stock photos, no downloads).
Run:  python tools/make_images.py     (needs: pip install pillow numpy)
Replace any file in static/img/ with a real photograph of the same name to upgrade the look.
"""
import os, math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = os.path.join(os.path.dirname(__file__), '..', 'static', 'img')
os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(7)

def fbm(h, w, octaves=6, base=4, persistence=.55):
    """Fractal value noise in [0,1]."""
    total = np.zeros((h, w), np.float32); amp = 1.0; norm = 0
    for o in range(octaves):
        n = base * 2 ** o
        g = rng.random((n + 1, int(n * w / h) + 2)).astype(np.float32)
        im = Image.fromarray((g * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
        total += np.asarray(im, np.float32) / 255 * amp; norm += amp; amp *= persistence
    return total / norm

def to_img(a):
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

def save(im, name, q=82):
    im.convert('RGB').save(os.path.join(OUT, name), quality=q, optimize=True, progressive=True)
    print('wrote', name, im.size)

# 1 ── hero-field: dark furrowed farmland receding to a hazy horizon ───────────────────
def hero_field(W=1080, H=1080):
    horizon = int(H * .32)
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    dy = np.maximum(y - horizon, 1)
    persp = dy / (H - horizon)                       # 0 at horizon → 1 at bottom
    u = (x - W * .62) / (dy * 1.15 + 20)             # furrow coordinate in perspective
    furrow = .5 + .5 * np.sin(u * 5.2)
    noise = fbm(H, W, 7, 6)
    ground = .22 + .5 * furrow * (0.35 + persp * .65) + .35 * (noise - .5)
    r = 22 + 70 * ground * persp ** .4 + 14 * noise
    g = 26 + 58 * ground * persp ** .4 + 12 * noise
    b = 16 + 26 * ground * persp ** .4
    sky_t = np.clip(y / horizon, 0, 1)
    sr = 18 + 36 * (1 - sky_t) ** 2 + 12 * sky_t
    sg = 24 + 44 * (1 - sky_t) ** 2 + 16 * sky_t
    sb = 16 + 18 * (1 - sky_t) ** 2 + 8 * sky_t
    mask = (y >= horizon).astype(np.float32)
    rgb = np.stack([r * mask + sr * (1 - mask), g * mask + sg * (1 - mask), b * mask + sb * (1 - mask)], -1)
    haze = np.exp(-((y - horizon) / 60.0) ** 2)[..., None] * np.array([46, 58, 30])
    rgb += haze
    vign = 1 - .55 * (((x - W / 2) / (W / 2)) ** 2 * .6 + ((y - H / 2) / (H / 2)) ** 2 * .4)
    rgb *= vign[..., None]
    left = np.clip(1.15 - x / (W * .8), .25, 1)[..., None]     # darker on the left where text sits
    rgb *= left
    return to_img(rgb * 1.7).filter(ImageFilter.Color3DLUT(0.2))

# 2 ── soil-hand: warm macro of crumbly soil held in a cupped hand (abstract, no face) ─
def soil_hand(W=1100, H=1400):
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    bg = np.stack([60 + 90 * (1 - y / H), 44 + 62 * (1 - y / H), 34 + 40 * (1 - y / H)], -1)
    # skin shape: a tilted rounded blob from the top right
    cx, cy = W * .66, H * .28
    d = (((x - cx) / (W * .5)) ** 2 + ((y - cy) / (H * .42)) ** 2)
    skin = np.clip(1.15 - d, 0, 1) ** .7
    skin_col = np.stack([236 * np.ones_like(x), 186 * np.ones_like(x), 160 * np.ones_like(x)], -1)
    skin_shade = (0.62 + .38 * np.clip(1 - (y - cy) / (H * .5), 0, 1))[..., None]
    img = bg * (1 - skin[..., None]) + skin_col * skin_shade * skin[..., None]
    # soil heap
    hx, hy = W * .56, H * .66
    hd = (((x - hx) / (W * .52)) ** 2 + ((y - hy) / (H * .26)) ** 2)
    heap = np.clip(1.25 - hd, 0, 1) ** .6
    n1 = fbm(H, W, 7, 10); n2 = fbm(H, W, 6, 32)
    crumbs = np.clip((n1 - .35) * 2.2, 0, 1) * .6 + n2 * .5
    soil = np.stack([28 + 96 * crumbs, 18 + 58 * crumbs, 12 + 36 * crumbs], -1)
    # highlight grain on crumb tops
    spec = np.clip((n2 - .66) * 6, 0, 1)[..., None] * np.array([90, 70, 50])
    soil = soil + spec
    img = img * (1 - heap[..., None]) + soil * heap[..., None]
    img *= (1 - .45 * (((x - W / 2) / (W / 2)) ** 2 + ((y - H / 2) / (H / 2)) ** 2) * .5)[..., None]
    return to_img(img).filter(ImageFilter.GaussianBlur(.8))

# 3 ── lab-beakers: pale lab bench with glass beakers holding green seedlings ──────────
def lab_beakers(W=1400, H=760):
    S = 2; w, h = W * S, H * S
    base = np.linspace(0, 1, h, dtype=np.float32)[:, None] * np.ones((1, w), np.float32)
    bg = np.stack([232 - 36 * base, 238 - 34 * base, 230 - 44 * base], -1)
    im = to_img(bg).convert('RGBA'); d = ImageDraw.Draw(im, 'RGBA')
    n = 6; gap = w / n
    for i in range(n):
        cx = gap * (i + .5); bw = gap * .58; top = h * .14; bot = h * .86
        # plant: several curved leaves
        for k in range(9):
            ang = rng.uniform(-.7, .7); length = rng.uniform(.3, .62) * (bot - top)
            x0, y0 = cx + rng.uniform(-bw * .2, bw * .2), bot - 20
            pts = []
            for t in np.linspace(0, 1, 18):
                pts.append((x0 + math.sin(ang) * length * t + math.sin(t * 3 + k) * 12 * t,
                            y0 - math.cos(ang) * length * t))
            g = (int(60 + rng.uniform(0, 50)), int(100 + rng.uniform(0, 60)), int(50 + rng.uniform(0, 30)), 230)
            d.line(pts, fill=g, width=int(rng.uniform(10, 22)), joint='curve')
        # glass body
        ov = Image.new('RGBA', (w, h), (0, 0, 0, 0)); od = ImageDraw.Draw(ov)
        od.rounded_rectangle((cx - bw / 2, top, cx + bw / 2, bot), radius=34, fill=(255, 255, 255, 40), outline=(255, 255, 255, 190), width=5)
        od.rectangle((cx - bw / 2 + 12, top + 26, cx - bw / 2 + 30, bot - 26), fill=(255, 255, 255, 90))
        for m in range(1, 5):                          # graduation marks
            yy = top + (bot - top) * (.2 + .15 * m)
            od.line((cx + bw / 2 - 52, yy, cx + bw / 2 - 12, yy), fill=(90, 105, 90, 170), width=4)
        im = Image.alpha_composite(im, ov); d = ImageDraw.Draw(im, 'RGBA')
    d.rectangle((0, h * .86, w, h), fill=(210, 214, 204, 255))
    d.rectangle((0, h * .86, w, h * .865), fill=(255, 255, 255, 200))
    im = im.resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(.6))
    return im

# 4 ── lab-growlight: magenta grow-light bay with glowing tubes and leafy canopy ───────
def lab_growlight(W=1400, H=760):
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    t = x / W
    r = 60 + 150 * t ** 1.1 + 40 * (1 - y / H)
    g = 18 + 40 * t
    b = 80 + 90 * t + 20 * (1 - y / H)
    rgb = np.stack([r, g, b], -1)
    im = to_img(rgb).convert('RGBA')
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(glow)
    for i in range(5):
        y0 = 40 + i * 42; d.line((-40 + i * 60, y0 + 140, W * .8, y0 - 30), fill=(255, 235, 250, 255), width=16)
    blur = glow.filter(ImageFilter.GaussianBlur(26)); im = Image.alpha_composite(im, blur)
    im = Image.alpha_composite(im, glow.filter(ImageFilter.GaussianBlur(2)))
    d = ImageDraw.Draw(im, 'RGBA')
    for k in range(160):                              # canopy of leafy blobs at the bottom
        cx = rng.uniform(0, W); cy = H * rng.uniform(.68, 1.05); rr = rng.uniform(26, 70)
        col = (int(230 + rng.uniform(-20, 25)), int(150 + rng.uniform(-40, 60)), int(90 + rng.uniform(-30, 60)), 235)
        d.ellipse((cx - rr, cy - rr * .6, cx + rr, cy + rr * .6), fill=col)
    im = im.filter(ImageFilter.GaussianBlur(1.1))
    v = 1 - .35 * (((x - W / 2) / (W / 2)) ** 2)
    a = np.asarray(im.convert('RGB'), np.float32) * v[..., None]
    return to_img(a)

if __name__ == '__main__':
    save(hero_field(), 'hero-field.jpg', 80)
    save(soil_hand(), 'soil-hand.jpg', 82)
    save(lab_beakers(), 'lab-beakers.jpg', 84)
    save(lab_growlight(), 'lab-growlight.jpg', 84)
