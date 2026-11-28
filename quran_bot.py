"""Quran verse video section: keyboards, flow state, and generation handler."""
import asyncio
import logging
import os
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from quran_meta import (AR_DIGITS_IN, RECITERS, SOLID_COLORS, STYLE_NAMES,
                        SURAH_SIMPLE, SURAHS, ar_num, parse_ref)
from quran_video import MAX_SECONDS, VideoError, make_verse_video

log = logging.getLogger("bot.quran")
_gen_sem = asyncio.Semaphore(1)

PER_PAGE = 8
PAGES = (len(RECITERS) + PER_PAGE - 1) // PER_PAGE
SURAH_PER_PAGE = 12
SURAH_PAGES = (114 + SURAH_PER_PAGE - 1) // SURAH_PER_PAGE


def _qv(ctx):
    return ctx.user_data.setdefault("qv", {})


STYLE_ORDER = ["chat", "dark", "night", "ornament", "nature", "solid"]
STYLE_EMOJI = {"chat": "💬", "night": "🌌", "ornament": "🕌", "nature": "🌅", "solid": "🎨", "dark": "⚫"}
PREVIEW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "previews")
_preview_ids = {}


def style_caption(i, style):
    extra = " (٦ ألوان)" if style == "solid" else ""
    return f"{ar_num(i + 1)} {STYLE_EMOJI[style]} {STYLE_NAMES[style]}{extra}"


def style_kb():
    rows = []
    for i, style in enumerate(STYLE_ORDER):
        rows.append([InlineKeyboardButton(style_caption(i, style), callback_data=f"qb|{style}")])
    return InlineKeyboardMarkup(rows)


async def send_style_gallery(bot, chat_id):
    """Send the 5 design previews as one album; caches Telegram file_ids in memory."""
    def media(use_ids):
        out = []
        for i, style in enumerate(STYLE_ORDER):
            fid = _preview_ids.get(style) if use_ids else None
            if fid:
                out.append(InputMediaPhoto(fid, caption=style_caption(i, style)))
            else:
                with open(os.path.join(PREVIEW_DIR, f"{style}.jpg"), "rb") as f:
                    out.append(InputMediaPhoto(f.read(), caption=style_caption(i, style)))
        return out

    use_ids = all(s in _preview_ids for s in STYLE_ORDER)
    try:
        msgs = await bot.send_media_group(chat_id, media(use_ids),
                                          read_timeout=120, write_timeout=120)
    except Exception:
        if not use_ids:
            log.exception("style gallery failed")
            return
        _preview_ids.clear()
        try:
            msgs = await bot.send_media_group(chat_id, media(False),
                                              read_timeout=120, write_timeout=120)
        except Exception:
            log.exception("style gallery retry failed")
            return
    if not use_ids:
        for style, m in zip(STYLE_ORDER, msgs):
            if m.photo:
                _preview_ids[style] = m.photo[-1].file_id


def solid_kb():
    rows, row = [], []
    for key, spec in SOLID_COLORS.items():
        row.append(InlineKeyboardButton(spec["ar"], callback_data=f"qc|{key}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data="qmenu")])
    return InlineKeyboardMarkup(rows)


def reciter_kb(page):
    page = max(0, min(page, PAGES - 1))
    rows, row = [], []
    for i in range(page * PER_PAGE, min((page + 1) * PER_PAGE, len(RECITERS))):
        row.append(InlineKeyboardButton(RECITERS[i][1], callback_data=f"qs|{i}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ السابق", callback_data=f"qr|{page-1}"))
    nav.append(InlineKeyboardButton(f"{ar_num(page+1)}/{ar_num(PAGES)}", callback_data="qr|noop"))
    if page < PAGES - 1:
        nav.append(InlineKeyboardButton("التالي ▶️", callback_data=f"qr|{page+1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton("⬅️ تغيير الخلفية", callback_data="qmenu")])
    return InlineKeyboardMarkup(rows)


def surah_kb(page):
    page = max(0, min(page, SURAH_PAGES - 1))
    rows, row = [], []
    for i in range(page * SURAH_PER_PAGE, min((page + 1) * SURAH_PER_PAGE, 114)):
        n = i + 1
        row.append(InlineKeyboardButton(f"{ar_num(n)}. {SURAH_SIMPLE[i]}", callback_data=f"qn|{n}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ السابق", callback_data=f"qf|{page-1}"))
    nav.append(InlineKeyboardButton(f"{ar_num(page+1)}/{ar_num(SURAH_PAGES)}", callback_data="qf|noop"))
    if page < SURAH_PAGES - 1:
        nav.append(InlineKeyboardButton("التالي ▶️", callback_data=f"qf|{page+1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton("⬅️ تغيير القارئ", callback_data="qrec")])
    return InlineKeyboardMarkup(rows)


def after_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 آية أخرى بنفس الإعدادات", callback_data="qagain")],
        [InlineKeyboardButton("🎨 تغيير الخلفية", callback_data="qmenu"),
         InlineKeyboardButton("🎙 تغيير القارئ", callback_data="qrec")],
    ])


def _settings_summary(cfg):
    st = STYLE_NAMES[cfg.get("style", "night")]
    if cfg.get("style") == "solid":
        st += f" ({SOLID_COLORS[cfg.get('solid', 'navy')]['ar']})"
    rec = RECITERS[cfg.get("reciter", 0)][1]
    return st, rec


ASK_REF = ("أرسل الآية أو النطاق بهذه الصيغة:\n"
           "• <code>2:255</code> لآية واحدة\n"
           "• <code>36:1-5</code> لنطاق آيات\n"
           "• أو باسم السورة: <code>الفاتحة 1-7</code>\n\n"
           f"الحد الأقصى لطول الفيديو {ar_num(MAX_SECONDS)} ثانية.")


async def _ask_surah(q, cfg, page=0):
    st, rec = _settings_summary(cfg)
    cfg["await"] = True
    cfg.pop("surah", None)
    await q.edit_message_text(
        f"✅ الخلفية: {st}\n🎙 القارئ: {rec}\n\n"
        f"📖 اختر السورة من القائمة، أو اكتب المرجع مباشرة مثل <code>2:255</code>:",
        parse_mode="HTML", reply_markup=surah_kb(page))


async def _ask_ref(q, cfg):
    st, rec = _settings_summary(cfg)
    cfg["await"] = True
    s = cfg.get("surah")
    if s:
        n_ayahs = len(SURAHS[s]["ayahs"])
        await q.edit_message_text(
            f"✅ الخلفية: {st}\n🎙 القارئ: {rec}\n"
            f"📖 السورة: {SURAH_SIMPLE[s-1]} ({ar_num(n_ayahs)} آية)\n\n"
            f"أرسل رقم الآية أو النطاق:\n"
            f"• <code>255</code> لآية واحدة\n"
            f"• <code>1-5</code> لنطاق آيات\n\n"
            f"الحد الأقصى لطول الفيديو {ar_num(MAX_SECONDS)} ثانية.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ تغيير السورة", callback_data="qsurah")]]))
    else:
        await q.edit_message_text(
            f"✅ الخلفية: {st}\n🎙 القارئ: {rec}\n\n{ASK_REF}",
            parse_mode="HTML")


async def quran_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass  # stale callback after a cold start; still handle the tap
    data = q.data or ""
    cfg = _qv(ctx)

    if data == "qmenu":
        cfg["await"] = False
        await q.edit_message_text("🎬 فيديو آية قرآنية\n\nاختر التصميم من المعرض بالأسفل:",
                                  reply_markup=style_kb())
        await send_style_gallery(q.get_bot(), q.message.chat_id)
    elif data.startswith("qb|"):
        style = data.split("|", 1)[1]
        if style not in STYLE_NAMES:
            return
        cfg["style"] = style
        if style == "solid":
            await q.edit_message_text("🎨 اختر اللون:", reply_markup=solid_kb())
        else:
            cfg["solid"] = None
            await q.edit_message_text("🎙 اختر القارئ:", reply_markup=reciter_kb(0))
    elif data.startswith("qc|"):
        color = data.split("|", 1)[1]
        if color not in SOLID_COLORS:
            return
        cfg["solid"] = color
        await q.edit_message_text("🎙 اختر القارئ:", reply_markup=reciter_kb(0))
    elif data.startswith("qr|"):
        p = data.split("|", 1)[1]
        if p == "noop":
            return
        await q.edit_message_text("🎙 اختر القارئ:", reply_markup=reciter_kb(int(p)))
    elif data == "qrec":
        cfg["await"] = False
        page = cfg.get("reciter", 0) // PER_PAGE
        await q.edit_message_text("🎙 اختر القارئ:", reply_markup=reciter_kb(page))
    elif data.startswith("qs|"):
        idx = int(data.split("|", 1)[1])
        if not (0 <= idx < len(RECITERS)):
            return
        cfg["reciter"] = idx
        await _ask_surah(q, cfg)
    elif data.startswith("qf|"):
        p = data.split("|", 1)[1]
        if p == "noop":
            return
        await _ask_surah(q, cfg, int(p))
    elif data == "qsurah":
        page = (cfg.get("surah", 1) - 1) // SURAH_PER_PAGE
        await _ask_surah(q, cfg, page)
    elif data.startswith("qn|"):
        s = int(data.split("|", 1)[1])
        if not (1 <= s <= 114):
            return
        cfg["surah"] = s
        await _ask_ref(q, cfg)
    elif data == "qagain":
        await _ask_surah(q, cfg)


async def quran_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    """Handle a text message if the user is in the verse flow. True if consumed."""
    cfg = _qv(ctx)
    if not cfg.get("await"):
        return False
    text = (update.message.text or "").strip()
    if "http://" in text or "https://" in text:
        return False
    s = cfg.get("surah")
    if s and re.fullmatch(r"[0-9٠-٩]{1,3}(\s*[-–]\s*[0-9٠-٩]{1,3})?", text):
        text = f"{s}:{text}"
    try:
        surah, a1, a2 = parse_ref(text)
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}")
        return True

    status = await update.message.reply_text(
        "⏳ جاري تحميل التلاوة وتصميم الفيديو... قد يستغرق حوالي دقيقة.")
    await ctx.bot.send_chat_action(update.message.chat_id, ChatAction.RECORD_VIDEO)
    async with _gen_sem:
        try:
            path, dur = await asyncio.to_thread(
                make_verse_video, cfg.get("reciter", 0), surah, a1, a2,
                cfg.get("style", "night"), cfg.get("solid"))
        except VideoError as e:
            if e.code == "toolong":
                await status.edit_text(
                    f"⚠️ هذا الاختيار طوله {ar_num(e.detail)} ثانية، والحد الأقصى "
                    f"{ar_num(MAX_SECONDS)} ثانية.\nقلّل النطاق (مثلًا آية أو آيتين) وأرسل مرة أخرى.")
            elif e.code == "audio":
                await status.edit_text("❌ تعذر تحميل التلاوة لهذه الآية. جرّب قارئًا آخر أو أعد المحاولة.")
            else:
                log.error("video error: %s %s", e.code, e.detail)
                await status.edit_text("❌ حدث خطأ أثناء إنشاء الفيديو. أعد المحاولة.")
            return True
        except Exception:
            log.exception("verse video failed")
            await status.edit_text("❌ حدث خطأ غير متوقع. أعد المحاولة.")
            return True

    rng = f"الآية {ar_num(a1)}" if a1 == a2 else f"الآيات {ar_num(a1)} – {ar_num(a2)}"
    cap = (f"🎬 سورة {SURAH_SIMPLE[surah-1]} – {rng}\n"
           f"🎙 الشيخ {RECITERS[cfg.get('reciter', 0)][1]}\n"
           f"⏱ {ar_num(round(dur))} ثانية")
    try:
        await status.edit_text("📤 جاري إرسال الفيديو...")
        await ctx.bot.send_chat_action(update.message.chat_id, ChatAction.UPLOAD_VIDEO)
        with open(path, "rb") as f:
            await ctx.bot.send_video(update.message.chat_id, f, caption=cap,
                                     width=1080, height=1920, supports_streaming=True,
                                     read_timeout=300, write_timeout=300)
        await status.delete()
        await update.message.reply_text("هل تريد فيديو آخر؟", reply_markup=after_kb())
    except Exception:
        log.exception("send video failed")
        await status.edit_text("❌ تم إنشاء الفيديو لكن فشل الإرسال.")
    return True
