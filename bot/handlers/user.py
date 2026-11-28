"""History, favorites, settings handlers."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from database import db
from downloader.info import ar_num
from .. import keyboards as kb
from ..text import t


async def show_history(q, lang):
    rows = db.history(q.from_user.id, 10)
    if not rows:
        await q.edit_message_text(t(lang, "no_history"), reply_markup=kb.back_kb(lang))
        return
    lines = []
    for r in rows:
        icon = "✅" if r["status"] == "ok" else ("🚫" if r["status"] == "cancelled" else "❌")
        lines.append(f"{icon} {(r['title'] or r['url'])[:60]}")
    await q.edit_message_text("🕘 <b>" + t(lang, "btn_history") + "</b>\n\n" + "\n".join(lines),
                              parse_mode="HTML", reply_markup=kb.back_kb(lang))


async def show_favorites(q, lang):
    rows = db.favorites(q.from_user.id, 20)
    if not rows:
        await q.edit_message_text(t(lang, "no_favorites"), reply_markup=kb.back_kb(lang))
        return
    kb_rows = []
    for i, r in enumerate(rows):
        kb_rows.append([InlineKeyboardButton(f"⭐ {(r['title'] or r['url'])[:40]}",
                                             callback_data=f"f:dl:{i}")])
        kb_rows.append([InlineKeyboardButton("🗑 حذف", callback_data=f"f:rm:{i}")])
    kb_rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="m:menu")])
    # stash urls in context-free way: rebuild from db on click by index
    from ..state import pending
    pending.setdefault(q.from_user.id, {})["fav_urls"] = [r["url"] for r in rows]
    await q.edit_message_text("⭐ <b>" + t(lang, "btn_favorites") + "</b>",
                              parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb_rows))


async def on_favorite(q, uid, lang, arg):
    action, _, idx = arg.partition(":")
    from ..state import pending
    urls = (pending.get(uid) or {}).get("fav_urls") or []
    if not idx.isdigit() or int(idx) >= len(urls):
        await q.answer("؟")
        return
    url = urls[int(idx)]
    if action == "rm":
        db.remove_favorite(uid, url)
        await q.answer(t(lang, "fav_removed"))
        await show_favorites(q, lang)
    elif action == "dl":
        from . import downloads
        await q.edit_message_text(t(lang, "probing"))
        await downloads.start_probe(q.message, None, url, lang)


async def show_settings(q, uid, lang):
    user = db.get_user(uid)
    await q.edit_message_text(t(lang, "settings"), parse_mode="HTML",
                              reply_markup=kb.settings_kb(user, lang))


async def on_setting(q, uid, lang, action):
    if action == "lang":
        new = "en" if lang == "ar" else "ar"
        db.set_lang(uid, new)
        await q.answer(t(new, "lang_set"), show_alert=True)
        await show_settings(q, uid, new)
    elif action == "q":
        user = db.get_user(uid)
        order = [144, 240, 360, 480, 720, 1080]
        cur = user["def_quality"] if user else 720
        nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else 720
        db.set_def_quality(uid, nxt)
        await show_settings(q, uid, lang)
    elif action == "a":
        user = db.get_user(uid)
        order = ["mp3", "m4a", "wav", "flac"]
        cur = user["def_audio"] if user else "mp3"
        nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else "mp3"
        db.set_def_audio(uid, nxt)
        await show_settings(q, uid, lang)
