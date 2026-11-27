"""Chat voice-message style: realistic chat UI with verse bubble and animated player."""
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

from quran_bg import W, H
from quran_meta import SURAH_SIMPLE, ar_num, ayah_text

BASE = os.path.dirname(os.path.abspath(__file__))
FONT_QURAN = os.path.join(BASE, "fonts", "AmiriQuran-Regular.ttf")
FONT_AMIRI = os.path.join(BASE, "fonts", "Amiri-Regular.ttf")

_rtl = dict(direction="rtl", language="ar")

BG = (11, 20, 26)          # whatsapp-dark background
BUBBLE = (32, 44, 51)      # incoming bubble
PILL = (24, 34, 40)
TXT = (233, 237, 239)
SUB = (134, 150, 160)
GREEN = (0, 168, 132)

BUB_X, BUB_W = 70, 830
VOICE_H = 150
BAR_N = 46
BAR_W_ZONE = 560          # waveform zone width inside voice bubble
BAR_X0 = 220              # waveform zone left edge (after avatar circle)
TIMER_X = 108             # countdown text x inside bubble


def _font(path, size):
    return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.RAQM)


def audio_bars(mp3_path, n=BAR_N):
    """RMS bar heights 0..1 from the actual recitation audio."""
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", mp3_path, "-ac", "1", "-ar", "4000",
                        "-f", "s16le", "-"], capture_output=True, timeout=120)
    raw = p.stdout
    n_s = len(raw) // 2
    if n_s < n * 4:
        return [0.5] * n
    import array
    a = array.array("h")
    a.frombytes(raw[: n_s * 2])
    bars = []
    step = n_s // n
    for i in range(n):
        chunk = a[i * step:(i + 1) * step]
        rms = (sum(v * v for v in chunk) / len(chunk)) ** 0.5 if len(chunk) else 0
        bars.append(min(1.0, rms / 9000))
    lo, hi = min(bars), max(bars)
    if hi - lo > 0.05:
        bars = [(b - lo) / (hi - lo) * 0.85 + 0.15 for b in bars]
    return bars


def _wrap(draw, tokens, font, max_w):
    lines, cur, cur_w = [], [], 0.0
    sp = draw.textlength(" ", font=font, **_rtl)
    for tok in tokens:
        w_ = draw.textlength(tok, font=font, **_rtl)
        add = w_ + (sp if cur else 0)
        if cur and cur_w + add > max_w:
            lines.append(cur)
            cur, cur_w = [tok], w_
        else:
            cur.append(tok)
            cur_w += add
    if cur:
        lines.append(cur)
    return lines


def render_chat_base(surah, ayah, a1, a2, bars, out_path):
    """Full static frame: bg, date pill, verse bubble, voice bubble (gray waveform, play icon).

    Returns (path, verse_bottom_y) — the voice bubble geometry is fixed off the verse bubble.
    """
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img, "RGBA")

    # date pill
    f_pill = _font(FONT_AMIRI, 30)
    label = "اليوم"
    pw = draw.textlength(label, font=f_pill, **_rtl)
    draw.rounded_rectangle([(W - pw) / 2 - 26, 60, (W + pw) / 2 + 26, 116], radius=16,
                           fill=PILL + (255,))
    draw.text((W // 2, 88), label, font=f_pill, fill=SUB, anchor="mm", **_rtl)

    # verse bubble
    text = ayah_text(surah, ayah) + f" ﴿{ar_num(ayah)}﴾"
    tokens = text.split(" ")
    size = 52
    max_text_w = BUB_W - 90
    while True:
        f_v = _font(FONT_QURAN, size)
        lines = _wrap(draw, tokens, f_v, max_text_w)
        line_h = int(size * 1.7)
        if len(lines) * line_h <= 760 or size <= 30:
            break
        size -= 2
    text_h = len(lines) * line_h
    ref_h = 56
    bub_h = 44 + text_h + ref_h + 30
    y0 = max(160, (H - (bub_h + 28 + VOICE_H)) // 2)
    draw.rounded_rectangle([BUB_X, y0, BUB_X + BUB_W, y0 + bub_h], radius=26, fill=BUBBLE + (255,))
    draw.polygon([(BUB_X, y0 + 6), (BUB_X - 22, y0 - 2), (BUB_X, y0 + 44)], fill=BUBBLE + (255,))
    ty = y0 + 44
    for line in lines:
        draw.text((W // 2, ty), " ".join(line), font=f_v, fill=TXT, anchor="ma", **_rtl)
        ty += line_h
    f_ref = _font(FONT_AMIRI, 30)
    ref = f"سورة {SURAH_SIMPLE[surah-1]} • الآية {ar_num(ayah)}"
    draw.text((BUB_X + BUB_W - 40, y0 + bub_h - 30), ref, font=f_ref, fill=SUB, anchor="rs", **_rtl)

    # voice bubble
    vy = y0 + bub_h + 28
    draw.rounded_rectangle([BUB_X, vy, BUB_X + BUB_W, vy + VOICE_H], radius=26, fill=BUBBLE + (255,))
    # avatar circle (icon drawn per patch: play/pause swap)
    cx, cy, cr = BUB_X + 78, vy + VOICE_H // 2, 52
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=GREEN + (255,))
    # speed
    f_ui = _font(FONT_AMIRI, 34)
    draw.text((BUB_X + BUB_W - 66, cy), "1x", font=f_ui, fill=SUB, anchor="mm")
    img.save(out_path)
    return out_path, (cx, cy, cr, vy)


def render_player_patch(bars, progress, dur_left, geom, out_path, playing=True):
    """Voice-bubble content patch: avatar icon + waveform (white played part) + countdown."""
    cx, cy, cr, vy = geom
    pw = BAR_X0 + BAR_W_ZONE + 40
    img = Image.new("RGBA", (BUB_X + pw, vy + VOICE_H + 6), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # icon
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=GREEN + (255,))
    if playing:
        draw.rectangle([cx - 14, cy - 18, cx - 4, cy + 18], fill=(255, 255, 255, 255))
        draw.rectangle([cx + 4, cy - 18, cx + 14, cy + 18], fill=(255, 255, 255, 255))
    else:
        draw.polygon([(cx - 10, cy - 20), (cx - 10, cy + 20), (cx + 20, cy)], fill=(255, 255, 255, 255))
    # waveform
    n = len(bars)
    bw = BAR_W_ZONE / n
    mid = cy - 10
    max_h = 58
    played = int(progress * n + 0.5)
    for i, b in enumerate(bars):
        h_ = max(6, int(b * max_h))
        x = BAR_X0 + i * bw + bw * 0.25
        col = (255, 255, 255, 255) if i < played else (134, 150, 160, 255)
        draw.rounded_rectangle([x, mid - h_ // 2, x + bw * 0.5, mid + h_ // 2],
                               radius=bw * 0.25, fill=col)
    # countdown m:ss (western digits like the real player)
    m = int(dur_left) // 60
    s = int(dur_left) % 60
    f_t = _font(FONT_AMIRI, 32)
    draw.text((BAR_X0, vy + VOICE_H - 28), f"{m}:{s:02d}", font=f_t, fill=SUB, anchor="ls")
    img.save(out_path)
    return out_path
