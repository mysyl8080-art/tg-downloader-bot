"""Compose one verse image: background + header + Uthmani verse + footer."""
import os

from PIL import Image, ImageDraw, ImageFont

from quran_bg import W, H, GOLD, GOLD_SOFT, make_bg
from quran_meta import BASMALA, SURAHS, ar_num, ayah_text, show_basmala

BASE = os.path.dirname(os.path.abspath(__file__))
FONT_QURAN = os.path.join(BASE, "fonts", "AmiriQuran-Regular.ttf")
FONT_AMIRI = os.path.join(BASE, "fonts", "Amiri-Regular.ttf")
FONT_AMIRI_B = os.path.join(BASE, "fonts", "Amiri-Bold.ttf")

CREAM = (247, 243, 232)
DARK_TEXT = (58, 46, 32)
DARK_GOLD = (140, 110, 58)

_rtl = dict(direction="rtl", language="ar")

# vertical layout
Y_SURAH = 190
Y_RANGE = 268
Y_DIVIDER = 330
VERSE_TOP = 400
VERSE_BOTTOM = 1500
Y_FOOT_DIV = 1600
Y_RECITER = 1660
Y_BRAND = 1820

MAX_W = 920


def _font(path, size):
    return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.RAQM)


def _wrap(draw, text, font, max_w):
    words = text.split()
    lines, cur = [], ""
    for w_ in words:
        trial = (cur + " " + w_).strip()
        if draw.textlength(trial, font=font, **_rtl) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines


def _fit(draw, text, max_w, max_h, start=96, floor=34):
    size = start
    while size > floor:
        font = _font(FONT_QURAN, size)
        lines = _wrap(draw, text, font, max_w)
        line_h = int(size * 1.62)
        if len(lines) * line_h <= max_h:
            return font, lines, line_h
        size -= 3
    font = _font(FONT_QURAN, floor)
    return font, _wrap(draw, text, font, max_w), int(floor * 1.62)


def _divider(draw, y, color, half=210):
    cx = W // 2
    draw.line([cx - half, y, cx - 26, y], fill=color, width=2)
    draw.line([cx + 26, y, cx + half, y], fill=color, width=2)
    draw.polygon([(cx, y - 11), (cx + 11, y), (cx, y + 11), (cx - 11, y)], outline=color, width=2)


def render_ayah_image(reciter_ar, surah, ayah, a1, a2, style, solid=None, out_path=None):
    """Render one ayah's design to PNG. Returns the path."""
    bg, light = make_bg(style, solid)
    img = bg.convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")

    ink = DARK_TEXT if light else CREAM
    gold = DARK_GOLD if light else GOLD
    gold_soft = (120, 96, 50) if light else GOLD_SOFT

    # header: surah name + ayah position
    f_surah = _font(FONT_AMIRI_B, 58)
    draw.text((W // 2, Y_SURAH), SURAHS[surah]["ar"], font=f_surah, fill=gold, anchor="mm", **_rtl)
    f_range = _font(FONT_AMIRI, 40)
    label = f"الآية {ar_num(ayah)}" if a1 == a2 else f"الآيات {ar_num(a1)} – {ar_num(a2)}"
    draw.text((W // 2, Y_RANGE), label, font=f_range, fill=gold_soft, anchor="mm", **_rtl)
    _divider(draw, Y_DIVIDER, gold + (220,) if not light else gold + (235,))

    # verse text
    text = ayah_text(surah, ayah)
    text = f"{text} ﴿{ar_num(ayah)}﴾"

    basmala = show_basmala(surah, ayah) and surah != 1
    v_top = VERSE_TOP
    f_bas = None
    if basmala:
        f_bas = _font(FONT_QURAN, 72)
        v_top += 120

    font, lines, line_h = _fit(draw, text, MAX_W, VERSE_BOTTOM - v_top)
    block_h = len(lines) * line_h
    y = v_top + (VERSE_BOTTOM - v_top - block_h) // 2

    if basmala:
        draw.text((W // 2, y - 60), BASMALA, font=f_bas, fill=ink, anchor="mm", **_rtl)
    for ln in lines:
        draw.text((W // 2, y), ln, font=font, fill=ink, anchor="ma", **_rtl)
        y += line_h

    # footer: reciter + brand
    _divider(draw, Y_FOOT_DIV, gold + (200,) if not light else gold + (220,), half=150)
    f_rec = _font(FONT_AMIRI, 46)
    draw.text((W // 2, Y_RECITER), f"الشيخ {reciter_ar}", font=f_rec, fill=gold_soft, anchor="mm", **_rtl)
    f_brand = _font(FONT_AMIRI, 32)
    brand_col = gold_soft + (150,) if not light else gold_soft + (170,)
    draw.text((W // 2, Y_BRAND), "@Music_remover22bot", font=f_brand, fill=brand_col, anchor="mm")

    if not out_path:
        out_path = os.path.join("/tmp", f"qv_{surah}_{ayah}_{style}_{solid or ''}.png")
    img.save(out_path)
    return out_path
