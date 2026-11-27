"""Background painters for Quran verse videos (1080x1920)."""
import math
import random

from PIL import Image, ImageDraw, ImageFilter

W, H = 1080, 1920

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


def _glow(img, cx, cy, r, color, alpha):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (alpha,))
    layer = layer.filter(ImageFilter.GaussianBlur(r // 2))
    img.paste(layer, (0, 0), layer)


def bg_night():
    img = vgrad([(6, 10, 24), (15, 25, 56), (10, 15, 34)])
    d = ImageDraw.Draw(img, "RGBA")
    rnd = random.Random(7)
    for _ in range(190):
        x, y = rnd.randint(0, W), rnd.randint(0, int(H * 0.78))
        r = rnd.choice([1, 1, 1, 2, 2, 3])
        a = rnd.randint(60, 200)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(235, 240, 255, a))
        if r == 3:
            d.line([x - 8, y, x + 8, y], fill=(235, 240, 255, a // 2), width=1)
            d.line([x, y - 8, x, y + 8], fill=(235, 240, 255, a // 2), width=1)
    _glow(img, W - 215, 215, 150, (244, 233, 200), 60)
    d = ImageDraw.Draw(img, "RGBA")
    d.ellipse([W - 300, 130, W - 130, 300], fill=(244, 233, 200, 235))
    d.ellipse([W - 265, 118, W - 108, 275], fill=(11, 18, 42, 255))
    _vignette(img)
    return img


def _star8(cx, cy, r):
    pts = []
    for i in range(16):
        ang = math.pi / 8 * i - math.pi / 2
        rr = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    return pts


def bg_ornament():
    img = vgrad([(6, 52, 40), (11, 76, 57), (5, 34, 26)])
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    step = 150
    for row, y in enumerate(range(-step, H + step, step)):
        off = step // 2 if row % 2 else 0
        for x in range(-step + off, W + step, step):
            d.polygon(_star8(x, y, 52), outline=(212, 175, 55, 44), width=2)
            d.ellipse([x - 4, y - 4, x + 4, y + 4], outline=(212, 175, 55, 50), width=1)
    img.paste(layer, (0, 0), layer)
    _vignette(img, 130)
    return img


def _ridge(d, base_y, amp, color, seed):
    rnd = random.Random(seed)
    pts = [(0, H)]
    x = 0
    peak_phase = rnd.uniform(0, 6)
    while x <= W:
        t = x / W
        y = base_y - amp * (0.55 * math.sin(t * math.pi * 2.2 + peak_phase)
                            + 0.45 * math.sin(t * math.pi * 5.1 + peak_phase * 1.7))
        pts.append((x, y))
        x += 24
    pts.append((W, H))
    d.polygon(pts, fill=color)


def bg_nature():
    # dusk sky -> warm horizon
    img = vgrad([(16, 12, 40), (58, 26, 66), (140, 62, 72), (214, 128, 84)], h=H)
    sx, sy = int(W * 0.74), int(H * 0.66)
    _glow(img, sx, sy, 150, (255, 196, 120), 80)
    d = ImageDraw.Draw(img, "RGBA")
    d.ellipse([sx - 78, sy - 78, sx + 78, sy + 78], fill=(255, 214, 150, 255))
    # distant birds
    rnd = random.Random(3)
    for _ in range(7):
        bx, by = rnd.randint(80, W - 80), rnd.randint(int(H * 0.18), int(H * 0.45))
        s = rnd.randint(8, 14)
        d.arc([bx - s, by - s, bx, by + s], 300, 20, fill=(30, 18, 40, 200), width=3)
        d.arc([bx, by - s, bx + s, by + s], 320, 60, fill=(30, 18, 40, 200), width=3)
    _ridge(d, int(H * 0.66), 130, (44, 24, 52), 11)
    _ridge(d, int(H * 0.74), 160, (30, 16, 38), 22)
    _ridge(d, int(H * 0.84), 140, (18, 10, 24), 33)
    _vignette(img, 100)
    return img


def bg_solid(rgb, light=False):
    top = rgb
    bottom = tuple(max(0, int(c * 0.88)) for c in rgb) if not light \
        else tuple(min(255, int(c * 1.04)) for c in rgb)
    img = vgrad([top, bottom])
    _vignette(img, 60 if not light else 26)
    return img


def add_frame(img, light=False):
    """Thin double gold frame with corner diamonds."""
    d = ImageDraw.Draw(img, "RGBA")
    gold = GOLD + (200,) if not light else (150, 118, 55, 210)
    m1, m2 = 34, 46
    d.rectangle([m1, m1, W - m1, H - m1], outline=gold, width=2)
    d.rectangle([m2, m2, W - m2, H - m2], outline=gold, width=1)
    for cx, cy in [(m1, m1), (W - m1, m1), (m1, H - m1), (W - m1, H - m1)]:
        d.polygon([(cx, cy - 12), (cx + 12, cy), (cx, cy + 12), (cx - 12, cy)], outline=gold, width=2)
    return img


def make_bg(style, solid=None):
    if style == "night":
        img = bg_night()
        return add_frame(img), False
    if style == "ornament":
        img = bg_ornament()
        return add_frame(img), False
    if style == "nature":
        img = bg_nature()
        return add_frame(img), False
    c = solid or "navy"
    from quran_meta import SOLID_COLORS
    spec = SOLID_COLORS[c]
    img = bg_solid(spec["bg"], spec["light"])
    return add_frame(img, spec["light"]), spec["light"]
