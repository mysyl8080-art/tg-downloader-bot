"""Quran verse video section: keyboards, flow state, and generation handler."""
import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from quran_meta import (RECITERS, SOLID_COLORS, STYLE_NAMES, SURAH_SIMPLE,
                        ar_num, parse_ref)
from quran_video import MAX_SECONDS, VideoError, make_verse_video

log = logging.getLogger("bot.quran")
_gen_sem = asyncio.Semaphore(1)

PER_PAGE = 8
PAGES = (len(RECITERS) + PER_PAGE - 1) // PER_PAGE


def _qv(ctx):
    return ctx.user_data.setdefault("qv", {})


def style_kb():
    rows = [[InlineKeyboardButton(f"💬 {STYLE_NAMES['chat']}", callback_data="qb|chat")],
            [InlineKeyboardButton(f"🌌 {STYLE_NAMES['night']}", callback_data="qb|night")],
            [InlineKeyboardButton(f"🕌 {STYLE_NAMES['ornament']}", callback_data="qb|ornament")],
            [InlineKeyboardButton(f"🌅 {STYLE_NAMES['nature']}", callback_data="qb|nature")],
            [InlineKeyboardButton(f"🎨 {STYLE_NAMES['solid']}", callback_data="qb|solid")]]
    return InlineKeyboardMarkup(rows)


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


async def _ask_ref(q, cfg):
    st, rec = _settings_summary(cfg)
    cfg["await"] = True
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
        await q.edit_message_text("🎬 فيديو آية قرآنية\n\nاختر الخلفية:", reply_markup=style_kb())
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
        await _ask_ref(q, cfg)
    elif data == "qagain":
        await _ask_ref(q, cfg)


async def quran_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    """Handle a text message if the user is in the verse flow. True if consumed."""
    cfg = _qv(ctx)
    if not cfg.get("await"):
        return False
    text = (update.message.text or "").strip()
    if "http://" in text or "https://" in text:
        return False
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
