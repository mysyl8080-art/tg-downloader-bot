"""Design renderer v2: base card + per-word transparent overlays for word reveal."""
import os
import unicodedata

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from quran_bg import W, H, GOLD, GOLD_SOFT, make_layers
from quran_meta import BASMALA, SURAHS, ar_num, ayah_text

BASE = os.path.dirname(os.path.abspath(__file__))
FONT_QURAN = os.path.join(BASE, "fonts", "AmiriQuran-Regular.ttf")
FONT_AMIRI = os.path.join(BASE, "fonts", "Amiri-Regular.ttf")
FONT_AMIRI_B = os.path.join(BASE, "fonts", "Amiri-Bold.ttf")

CREAM = (245, 240, 225)   # spec #F5F0E1
DARK_TEXT = (56, 46, 32)
DARK_GOLD = (140, 110, 58)

_rtl = dict(direction="rtl", language="ar")

Y_CARTOUCHE = 205
Y_RANGE = 320
VERSE_TOP = 440
VERSE_BOTTOM = 1490
Y_FOOT_DIV = 1600
Y_RECITER = 1662
Y_BRAND = 1824
MAX_W = 940
BASMALA_H = 150


def _font(path, size):
    return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.RAQM)


def _wrap(draw, tokens, font, max_w):
    lines, cur, cur_w = [], [], 0.0
    space_w = draw.textlength(" ", font=font, **_rtl)
    for tok in tokens:
        w_ = draw.textlength(tok, font=font, **_rtl)
        add = w_ + (space_w if cur else 0)
        if cur and (cur_w + add > max_w or len(cur) >= 7):
            lines.append(cur)
            cur, cur_w = [tok], w_
        else:
            cur.append(tok)
            cur_w += add
    if cur:
        lines.append(cur)
    return lines


def _letters(tok):
    n = 0
    for ch in tok:
        if unicodedata.category(ch) != "Mn" and ch.strip():
            n += 1
    return max(1, n)


def layout_ayah(draw, text, dur):
    """Return font, positioned tokens [(token, x_right, y_top, t_start)], block fits verse zone."""
    tokens = text.split(" ")
    weights = [_letters(t) for t in tokens]
    total_w = sum(weights)
    start, usable = 0.12, max(0.4, dur - 0.9)
    times, acc = [], 0.0
    for w_ in weights:
        times.append(start + usable * acc / total_w)
        acc += w_

    v_top = VERSE_TOP
    size = 100
    while True:
        font = _font(FONT_QURAN, size)
        lines = _wrap(draw, tokens, font, MAX_W)
        line_h = int(size * 1.66)
        if len(lines) * line_h <= VERSE_BOTTOM - v_top or size <= 36:
            break
        size -= 3
    block_h = len(lines) * line_h
    y = v_top + (VERSE_BOTTOM - v_top - block_h) // 2
    space_w = draw.textlength(" ", font=font, **_rtl)

    placed = []
    idx = 0
    for line in lines:
        line_w = sum(draw.textlength(t, font=font, **_rtl) for t in line) + space_w * (len(line) - 1)
        x_right = (W + line_w) / 2
        for tok in line:
            w_ = draw.textlength(tok, font=font, **_rtl)
            placed.append((tok, x_right, y, times[idx]))
            x_right -= w_ + space_w
            idx += 1
        y += line_h
    return font, placed


def _draw_furniture(draw, reciter_ar, surah, a1, a2, light):
    gold = DARK_GOLD if light else GOLD
    gold_soft = (120, 96, 50) if light else GOLD_SOFT

    f_surah = _font(FONT_AMIRI_B, 56)
    name = SURAHS[surah]["ar"]
    tw = draw.textlength(name, font=f_surah, **_rtl)
    cw_, ch_ = tw + 110, 100
    x0, y0 = (W - cw_) / 2, Y_CARTOUCHE - ch_ // 2
    draw.rounded_rectangle([x0, y0, x0 + cw_, y0 + ch_], radius=26,
                           outline=gold + (215,), width=2)
    draw.text((W // 2, Y_CARTOUCHE), name, font=f_surah, fill=gold, anchor="mm", **_rtl)

    f_range = _font(FONT_AMIRI, 40)
    label = f"الآية {ar_num(a1)}" if a1 == a2 else f"الآيات {ar_num(a1)} – {ar_num(a2)}"
    draw.text((W // 2, Y_RANGE), label, font=f_range, fill=gold_soft, anchor="mm", **_rtl)

    cx = W // 2
    draw.line([cx - 150, Y_FOOT_DIV, cx - 26, Y_FOOT_DIV], fill=gold + (190,), width=2)
    draw.line([cx + 26, Y_FOOT_DIV, cx + 150, Y_FOOT_DIV], fill=gold + (190,), width=2)
    draw.polygon([(cx, Y_FOOT_DIV - 11), (cx + 11, Y_FOOT_DIV), (cx, Y_FOOT_DIV + 11),
                  (cx - 11, Y_FOOT_DIV)], outline=gold + (190,), width=2)
    f_rec = _font(FONT_AMIRI, 46)
    draw.text((W // 2, Y_RECITER), f"الشيخ {reciter_ar}", font=f_rec, fill=gold_soft, anchor="mm", **_rtl)


def render_base(reciter_ar, surah, a1, a2, style, solid, out_path, minimal=False):
    """Background + header + footer, without the verse words. minimal: verse only."""
    base, _far, _near, _rays, light = make_layers(style, solid)
    img = base.convert("RGB")
    if minimal:
        img.save(out_path)
        return out_path, light
    draw = ImageDraw.Draw(img, "RGBA")
    _draw_furniture(draw, reciter_ar, surah, a1, a2, light)
    img.save(out_path)
    return out_path, light


def render_furniture(reciter_ar, surah, a1, a2, out_path):
    """Transparent frame + header + footer layer for video backgrounds."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    gold = GOLD + (200,)
    m1, m2 = 34, 46
    d.rectangle([m1, m1, W - m1, H - m1], outline=gold, width=2)
    d.rectangle([m2, m2, W - m2, H - m2], outline=gold, width=1)
    for cx, cy in [(m1, m1), (W - m1, m1), (m1, H - m1), (W - m1, H - m1)]:
        d.polygon([(cx, cy - 12), (cx + 12, cy), (cx, cy + 12), (cx - 12, cy)], outline=gold, width=2)
    _draw_furniture(d, reciter_ar, surah, a1, a2, False)
    img.save(out_path)
    return out_path


def render_word_overlays(surah, ayah, a1, dur, light, workdir, tag, shadow=False):
    """Render the basmala (if any) and each word as transparent crops.

    Returns list of (png_path, x, y, t_start, fade_dur).
    """
    ink = DARK_TEXT if light else CREAM
    out = []

    full = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(full)

    text = ayah_text(surah, ayah) + f" ﴿{ar_num(ayah)}﴾"
    v_top = VERSE_TOP
    has_bas = ayah == 1 and surah not in (1, 9)
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    if has_bas:
        v_top += BASMALA_H

    # layout within adjusted zone
    tokens = text.split(" ")
    weights = [_letters(t) for t in tokens]
    total_w = sum(weights)
    start, usable = 0.12, max(0.4, dur - 0.9)
    times, acc = [], 0.0
    for w_ in weights:
        times.append(start + usable * acc / total_w)
        acc += w_

    size = 100
    while True:
        font = _font(FONT_QURAN, size)
        lines = _wrap(probe, tokens, font, MAX_W)
        line_h = int(size * 1.66)
        if len(lines) * line_h <= VERSE_BOTTOM - v_top or size <= 36:
            break
        size -= 3
    block_h = len(lines) * line_h
    y = v_top + (VERSE_BOTTOM - v_top - block_h) // 2
    space_w = probe.textlength(" ", font=font, **_rtl)

    boxes = []
    idx = 0
    for line in lines:
        line_w = sum(probe.textlength(t, font=font, **_rtl) for t in line) + space_w * (len(line) - 1)
        x_right = (W + line_w) / 2
        for tok in line:
            w_ = probe.textlength(tok, font=font, **_rtl)
            draw.text((x_right, y), tok, font=font, fill=ink, anchor="ra", **_rtl)
            bb = draw.textbbox((x_right, y), tok, font=font, anchor="ra", **_rtl)
            boxes.append((bb, times[idx]))
            x_right -= w_ + space_w
            idx += 1
        y += line_h

    if has_bas:
        f_bas = _font(FONT_QURAN, 78)
        by = max(VERSE_TOP + 10, (v_top + (VERSE_BOTTOM - v_top - block_h) // 2) - 110)
        draw.text((W // 2, by), BASMALA, font=f_bas, fill=ink, anchor="ma", **_rtl)
        bb = draw.textbbox((W // 2, by), BASMALA, font=f_bas, anchor="ma", **_rtl)
        boxes.insert(0, (bb, 0.05))

    pad = 26 if shadow else 14
    for i, (bb, t) in enumerate(boxes):
        x0, y0, x1, y1 = (int(round(v)) for v in bb)
        x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
        x1, y1 = min(W, x1 + pad), min(H, y1 + pad)
        crop = full.crop((x0, y0, x1, y1))
        if shadow:
            halo = Image.new("RGBA", crop.size, (0, 0, 0, 0))
            halo.putalpha(crop.getchannel("A").point(lambda v: int(v * 0.55)))
            halo = halo.filter(ImageFilter.GaussianBlur(6))
            dark = Image.new("RGBA", crop.size, (6, 9, 18, 255))
            dark.putalpha(halo.getchannel("A"))
            canvas = Image.new("RGBA", crop.size, (0, 0, 0, 0))
            canvas.alpha_composite(dark, (0, 3))
            canvas.alpha_composite(crop, (0, 0))
            crop = canvas
        p = os.path.join(workdir, f"w_{tag}_{i}.png")
        crop.save(p)
        out.append((p, x0, y0, round(t, 3), 0.6 if (has_bas and i == 0) else 0.35))
    return out


def particle_paths(style, solid, workdir):
    """Save the drifting layers and rays for ffmpeg; returns (far, near, rays|None)."""
    _base, far, near, rays, _l = make_layers(style, solid)
    fp = os.path.join(workdir, "layer_far.png")
    np_ = os.path.join(workdir, "layer_near.png")
    far.save(fp)
    near.save(np_)
    rp = None
    if rays is not None:
        rp = os.path.join(workdir, "layer_rays.png")
        rays.save(rp)
    return fp, np_, rp


# ---------- cinematic system (shorts style) ----------
FONT_HAFS = os.path.join(BASE, "fonts", "UthmanicHafs.ttf")
GOLD_HI = (238, 211, 89)      # karaoke highlight
Y_HEADER = 138
Y_CHUNK = 830
Y_KARAOKE = 1430
CHUNK_WORDS = 4
CINE_MAX_W = 980


def _halo(crop, strength=0.6, blur=7, dy=4):
    """Soft dark halo behind a text crop."""
    halo = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    halo.putalpha(crop.getchannel("A").point(lambda v: int(v * strength)))
    halo = halo.filter(ImageFilter.GaussianBlur(blur))
    dark = Image.new("RGBA", crop.size, (5, 8, 16, 255))
    dark.putalpha(halo.getchannel("A"))
    canvas = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    canvas.alpha_composite(dark, (0, dy))
    canvas.alpha_composite(crop, (0, 0))
    return canvas


def _line_crop(tokens, font, fill, y_center, pad=34):
    """One centered RTL line on a transparent frame; returns (crop, x0, y0)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    space_w = d.textlength(" ", font=font, **_rtl)
    line_w = sum(d.textlength(t, font=font, **_rtl) for t in tokens) + space_w * (len(tokens) - 1)
    x_right = (W + line_w) / 2
    line_h = int(font.size * 1.66)
    y_top = y_center - line_h // 2
    for tok in tokens:
        d.text((x_right, y_top), tok, font=font, fill=fill, anchor="ra", **_rtl)
        x_right -= d.textlength(tok, font=font, **_rtl) + space_w
    bb = img.getbbox()
    x0, y0 = max(0, bb[0] - pad), max(0, bb[1] - pad)
    x1, y1 = min(W, bb[2] + pad), min(H, bb[3] + pad)
    return img.crop((x0, y0, x1, y1)), x0, y0


def _fit_size(probe, tokens, max_w, start=126, floor=80):
    size = start
    while size > floor:
        font = _font(FONT_HAFS, size)
        space_w = probe.textlength(" ", font=font, **_rtl)
        if sum(probe.textlength(t, font=font, **_rtl) for t in tokens) + space_w * (len(tokens) - 1) <= max_w:
            return font
        size -= 4
    return _font(FONT_HAFS, floor)


def render_cine_header(surah, workdir, tag):
    """Tiny plain surah label, top center. Returns (path, x, y)."""
    font = _font(FONT_AMIRI, 48)
    crop, x0, y0 = _line_crop([SURAHS[surah]["ar"]], font, (245, 240, 225, 225), Y_HEADER, pad=18)
    p = os.path.join(workdir, f"hdr_{tag}.png")
    crop.save(p)
    return p, x0, y0


def render_cine_overlays(surah, ayah, a1, dur, workdir, tag):
    """Phrase-chunk verse text + karaoke current word, timed to the audio.

    Returns list of window items: (png_path, x, y, t0, t1, fade_in, fade_out).
    """
    marker = f"﴿{ar_num(ayah)}﴾"
    tokens = ayah_text(surah, ayah).split(" ")
    has_bas = ayah == 1 and surah not in (1, 9)

    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))

    # timing weights: basmala counts as one (slower) unit, marker shares the last word's slot
    units = ([BASMALA] if has_bas else []) + tokens + [marker]
    weights = [_letters(t) for t in units]
    if has_bas:
        weights[0] = int(weights[0] * 1.6)
    weights[-1] = 1
    total_w = sum(weights)
    start, usable = 0.12, max(0.5, dur - 0.42)
    times, acc = [], 0.0
    for w_ in weights:
        times.append(start + usable * acc / total_w)
        acc += w_
    ends = times[1:] + [start + usable]

    # chunks of <=CHUNK_WORDS tokens that fit one line; marker rides the last chunk
    chunks, cur = [], []
    base_off = 1 if has_bas else 0
    for tok in tokens:
        trial = cur + [tok]
        if len(trial) > CHUNK_WORDS:
            chunks.append(cur)
            cur = [tok]
        else:
            font = _fit_size(probe, trial, CINE_MAX_W)
            if len(trial) > 1 and font.size <= 80 and _fit_size(probe, cur, CINE_MAX_W).size > 80:
                chunks.append(cur)
                cur = [tok]
            else:
                cur = trial
    if cur:
        chunks.append(cur)
    chunks[-1] = chunks[-1] + [marker]
    if has_bas:
        chunks.insert(0, [BASMALA])

    items = []
    # token index of each chunk start (in `units` space)
    idx = 0
    for ci, chunk in enumerate(chunks):
        t0 = times[idx]
        t1 = ends[idx + len(chunk) - 1]
        if ci + 1 < len(chunks):
            t1 = times[idx + len(chunk)] + 0.05
        else:
            t1 = max(t1, dur - 0.12)
        font = _fit_size(probe, chunk, CINE_MAX_W)
        crop, x0, y0 = _line_crop(chunk, font, CREAM, Y_CHUNK)
        crop = _halo(crop)
        p = os.path.join(workdir, f"c_{tag}_{ci}.png")
        crop.save(p)
        items.append((p, x0, y0, round(max(0.0, t0 - 0.12), 3), round(t1, 3), 0.3, 0.22))
        idx += len(chunk)

    # karaoke: every ayah word (skip basmala unit and the ﴿N﴾ marker)
    k_indices = range(base_off, len(units) - 1)
    for ki, ui in enumerate(k_indices):
        tok = units[ui]
        font = _fit_size(probe, [tok], CINE_MAX_W, start=148, floor=108)
        crop, x0, y0 = _line_crop([tok], font, GOLD_HI, Y_KARAOKE)
        crop = _halo(crop, strength=0.5)
        p = os.path.join(workdir, f"k_{tag}_{ki}.png")
        crop.save(p)
        k_end = ends[ui] + 0.05
        if ui == len(units) - 2:
            k_end = max(k_end, dur - 0.12)
        items.append((p, x0, y0, round(times[ui], 3), round(k_end, 3), 0.08, 0.08))
    return items
