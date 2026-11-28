"""Cinematic layered backgrounds for Quran verse videos (1080x1920).

Each style produces a base still plus drifting particle layers and light rays
that ffmpeg animates (parallax) during encoding.
"""
import math
import random

from PIL import Image, ImageDraw, ImageFilter

W, H = 1080, 1920
DRIFT = 480  # extra width on particle layers so they can travel

GOLD = (212, 175, 55)
GOLD_SOFT = (190, 158, 92)


def _lerp(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def vgrad(colors, h=H):
    img = Image.new("RGB", (1, h))
    px = img.load()
    n = len(colors) - 1
    for y in range(h):
        t = y / (h - 1) * n
        i = min(int(t), n - 1)
        px[0, y] = _lerp(colors[i], colors[i + 1], t - i)
    return img.resize((W, h))


def _vignette(img, strength=110):
    mask = Image.radial_gradient("L").resize((W, H))
    mask = mask.point(lambda v: int(v * strength / 255))
    img.paste(Image.new("RGB", (W, H), (0, 0, 0)), (0, 0), mask)


def _glow(img, cx, cy, r, color, alpha, blur=None):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (alpha,))
    layer = layer.filter(ImageFilter.GaussianBlur(blur or r // 2))
    img.paste(layer, (0, 0), layer)


def _noise(img, amount=6):
    rnd = random.Random(5)
    px = img.load()
    step = 2
    for y in range(0, H, step):
        for x in range(0, W, step):
            v = rnd.randint(-amount, amount)
            r, g, b = px[x, y][:3]
            px[x, y] = (max(0, min(255, r + v)), max(0, min(255, g + v)), max(0, min(255, b + v)))


def _beams(color, origin, angles, width=130, alpha=26):
    """Soft light beams fanning from an origin point, on transparent canvas."""
    layer = Image.new("RGBA", (W + 480, H + 480), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    ox, oy = origin
    for a in angles:
        dx, dy = math.cos(math.radians(a)), math.sin(math.radians(a))
        px_, py_ = -dy, dx
        d.polygon([(ox + px_ * width, oy + py_ * width),
                   (ox - px_ * width, oy - py_ * width),
                   (ox + dx * 2600 - px_ * width * 3, oy + dy * 2600 - py_ * width * 3),
                   (ox + dx * 2600 + px_ * width * 3, oy + dy * 2600 + py_ * width * 3)],
                  fill=color + (alpha,))
    layer = layer.filter(ImageFilter.GaussianBlur(60))
    return layer.crop((240, 240, 240 + W, 240 + H))


def _bokeh_layer(seed, count, rmin, rmax, alpha, colors, warm=False):
    layer = Image.new("RGBA", (W + DRIFT, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rnd = random.Random(seed)
    for _ in range(count):
        x, y = rnd.randint(0, W + DRIFT), rnd.randint(0, H)
        r = rnd.randint(rmin, rmax)
        c = colors[rnd.randrange(len(colors))]
        d.ellipse([x - r, y - r, x + r, y + r], fill=c + (rnd.randint(alpha // 2, alpha),))
    return layer.filter(ImageFilter.GaussianBlur(3 if rmax <= 3 else 6))


def _star8(cx, cy, r):
    pts = []
    for i in range(16):
        ang = math.pi / 8 * i - math.pi / 2
        rr = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    return pts


def _ridge(d, base_y, amp, color, seed, w=W, h=H):
    rnd = random.Random(seed)
    pts = [(0, h)]
    x = 0
    ph = rnd.uniform(0, 6)
    while x <= w:
        t = x / w
        y = base_y - amp * (0.55 * math.sin(t * math.pi * 2.2 + ph)
                            + 0.45 * math.sin(t * math.pi * 5.1 + ph * 1.7))
        pts.append((x, y))
        x += 24
    pts.append((w, h))
    d.polygon(pts, fill=color)


def add_frame(img, light=False):
    d = ImageDraw.Draw(img, "RGBA")
    gold = GOLD + (190,) if not light else (150, 118, 55, 200)
    m1, m2 = 34, 46
    d.rectangle([m1, m1, W - m1, H - m1], outline=gold, width=2)
    d.rectangle([m2, m2, W - m2, H - m2], outline=gold, width=1)
    for cx, cy in [(m1, m1), (W - m1, m1), (m1, H - m1), (W - m1, H - m1)]:
        d.polygon([(cx, cy - 12), (cx + 12, cy), (cx, cy + 12), (cx - 12, cy)], outline=gold, width=2)
    return img


def _night():
    base = vgrad([(4, 7, 18), (13, 20, 48), (20, 28, 62), (8, 12, 30)])
    _glow(base, int(W * 0.25), int(H * 0.35), 320, (56, 90, 160), 36)   # blue nebula
    _glow(base, int(W * 0.75), int(H * 0.62), 300, (96, 60, 140), 28)   # violet nebula
    _glow(base, W - 215, 205, 170, (244, 233, 200), 66)                 # moon halo
    d = ImageDraw.Draw(base, "RGBA")
    rnd = random.Random(7)
    for _ in range(150):
        x, y = rnd.randint(0, W), rnd.randint(0, int(H * 0.8))
        r = rnd.choice([1, 1, 1, 2, 2])
        d.ellipse([x - r, y - r, x + r, y + r], fill=(235, 240, 255, rnd.randint(50, 170)))
    d.ellipse([W - 296, 122, W - 134, 284], fill=(246, 236, 205, 245))
    d.ellipse([W - 262, 110, W - 112, 260], fill=(11, 17, 40, 255))
    _vignette(base)
    _noise(base)
    far = _bokeh_layer(21, 120, 1, 2, 150, [(225, 232, 255)])
    near = _bokeh_layer(22, 26, 3, 6, 110, [(240, 230, 200), (212, 175, 55), (200, 215, 255)])
    rays = _beams((230, 225, 200), (W - 220, 180), [96, 104, 113], width=90, alpha=16)
    return base, far, near, rays


def _ornament():
    base = vgrad([(5, 44, 33), (10, 72, 54), (16, 92, 68), (5, 30, 22)])
    _glow(base, W // 2, int(H * 0.42), 480, (40, 130, 95), 40)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    step = 150
    for row, y in enumerate(range(-step, H + step, step)):
        off = step // 2 if row % 2 else 0
        for x in range(-step + off, W + step, step):
            d.polygon(_star8(x, y, 52), outline=(212, 175, 55, 40), width=2)
            d.ellipse([x - 4, y - 4, x + 4, y + 4], outline=(212, 175, 55, 46), width=1)
    step2 = 75
    for row, y in enumerate(range(0, H + step2, step2)):
        off = step2 // 2 if row % 2 else 0
        for x in range(off, W + step2, step2):
            d.polygon(_star8(x, y, 22), outline=(230, 200, 120, 22), width=1)
    base.paste(layer, (0, 0), layer)
    _vignette(base, 125)
    _noise(base)
    far = _bokeh_layer(31, 60, 1, 3, 120, [(230, 205, 140)])
    near = _bokeh_layer(32, 22, 3, 6, 100, [(240, 215, 140), (212, 175, 55)])
    rays = _beams((255, 240, 200), (W // 2, -40), [80, 90, 100], width=150, alpha=14)
    return base, far, near, rays


def _nature():
    base = vgrad([(14, 10, 38), (52, 24, 64), (110, 48, 70), (186, 96, 78), (228, 150, 96)])
    sx, sy = int(W * 0.74), int(H * 0.66)
    _glow(base, sx, sy, 210, (255, 190, 110), 95)
    d = ImageDraw.Draw(base, "RGBA")
    # cloud wisps
    for cy, ca, cw_ in [(int(H * 0.30), 26, 420), (int(H * 0.42), 20, 520), (int(H * 0.52), 24, 380)]:
        _glow(base, W // 2, cy, cw_ // 2, (255, 170, 140), ca, blur=90)
    d = ImageDraw.Draw(base, "RGBA")
    d.ellipse([sx - 82, sy - 82, sx + 82, sy + 82], fill=(255, 218, 155, 255))
    rnd = random.Random(3)
    for _ in range(8):
        bx, by = rnd.randint(80, W - 80), rnd.randint(int(H * 0.16), int(H * 0.45))
        s = rnd.randint(8, 14)
        d.arc([bx - s, by - s, bx, by + s], 300, 20, fill=(28, 16, 38, 210), width=3)
        d.arc([bx, by - s, bx + s, by + s], 320, 60, fill=(28, 16, 38, 210), width=3)
    _ridge(d, int(H * 0.68), 120, (56, 30, 62), 11)
    _ridge(d, int(H * 0.76), 150, (36, 20, 44), 22)
    _ridge(d, int(H * 0.86), 140, (20, 12, 28), 33)
    _vignette(base, 95)
    _noise(base)
    far = _bokeh_layer(41, 50, 1, 2, 110, [(255, 220, 170)])
    near = _bokeh_layer(42, 18, 3, 6, 95, [(255, 205, 140), (255, 230, 180)])
    rays = _beams((255, 210, 150), (sx, sy), [202, 214, 226, 238], width=70, alpha=15)
    return base, far, near, rays


def _solid(rgb, light=False):
    top = rgb
    bottom = tuple(max(0, int(c * 0.85)) for c in rgb) if not light \
        else tuple(min(255, int(c * 1.05)) for c in rgb)
    base = vgrad([top, bottom])
    if light:
        _glow(base, W // 2, int(H * 0.3), 500, (255, 252, 240), 60)
    else:
        _glow(base, W // 2, int(H * 0.3), 520, tuple(min(255, int(c * 2.2)) for c in rgb), 46)
    _vignette(base, 70 if not light else 30)
    _noise(base, 4)
    if light:
        far = _bokeh_layer(51, 40, 1, 2, 60, [(150, 120, 70)])
        near = _bokeh_layer(52, 14, 3, 5, 45, [(160, 130, 80)])
    else:
        far = _bokeh_layer(51, 60, 1, 2, 90, [(220, 215, 200)])
        near = _bokeh_layer(52, 16, 3, 5, 70, [(212, 175, 55), (230, 225, 205)])
    return base, far, near, None


def _dark():
    base = vgrad([(6, 6, 9), (0, 0, 0)])
    _vignette(base, 85)
    empty = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    return base, empty, empty.copy(), None


def make_layers(style, solid=None):
    """Return (base RGB with frame, far RGBA, near RGBA, rays RGBA|None, light bool)."""
    from quran_meta import SOLID_COLORS
    if style == "dark":
        base, far, near, rays = _dark()
        return base, far, near, rays, False  # no frame: pure black
    elif style == "night":
        base, far, near, rays = _night()
        light = False
    elif style == "ornament":
        base, far, near, rays = _ornament()
        light = False
    elif style == "nature":
        base, far, near, rays = _nature()
        light = False
    else:
        spec = SOLID_COLORS[solid or "navy"]
        base, far, near, rays = _solid(spec["bg"], spec["light"])
        light = spec["light"]
    return add_frame(base, light), far, near, rays, light
